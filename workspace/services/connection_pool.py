#!/usr/bin/env python3
"""
Connection Pool for Peer Communication
ピア通信向けコネクションプール管理

Features:
- HTTP keep-alive connection pooling
- Per-peer connection limits
- Connection health checking
- Automatic retry with circuit breaker
- Metrics and monitoring
"""

import asyncio
import logging
import threading
import time
from typing import Dict, Optional, List, Set, Any, Union
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

import aiohttp
from aiohttp import ClientTimeout, ClientError, ClientSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class ConnectionPoolError(Exception):
    """Base exception for connection pool errors"""
    pass


class PeerNotRegisteredError(ConnectionPoolError):
    """Raised when peer is not registered"""
    pass


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class ConnectionMetrics:
    """Connection pool metrics"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    retry_count: int = 0
    circuit_breaks: int = 0
    avg_response_time_ms: float = 0.0
    last_failure: Optional[float] = None
    
    def record_success(self, response_time_ms: float) -> None:
        """Record a successful request"""
        self.total_requests += 1
        self.successful_requests += 1
        # Update rolling average
        self.avg_response_time_ms = (
            (self.avg_response_time_ms * (self.total_requests - 1) + response_time_ms)
            / self.total_requests
        )
    
    def record_failure(self) -> None:
        """Record a failed request"""
        self.total_requests += 1
        self.failed_requests += 1
        self.last_failure = time.time()
    
    def record_retry(self) -> None:
        """Record a retry attempt"""
        self.retry_count += 1
    
    def record_circuit_break(self) -> None:
        """Record a circuit breaker trip"""
        self.circuit_breaks += 1


@dataclass
class PeerConnectionPool:
    """Per-peer connection pool configuration"""
    peer_id: str
    base_url: str
    max_connections: int = 10
    max_keepalive: int = 5
    keepalive_timeout: int = 30
    connect_timeout: float = 5.0
    total_timeout: float = 30.0
    max_retries: int = 3
    
    # Circuit breaker settings
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3


class CircuitBreaker:
    """
    Circuit breaker pattern implementation
    
    Prevents cascading failures by stopping requests to a failing service.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self._in_flight = 0  # Track requests in HALF_OPEN state
        self._lock = asyncio.Lock()
    
    async def can_execute(self) -> bool:
        """Check if request can be executed"""
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            
            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if self.last_failure_time and \
                   (time.time() - self.last_failure_time) > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.failure_count = 0
                    self._in_flight = 0
                    logger.info("Circuit breaker entering HALF_OPEN state")
                    return True
                return False
            
            if self.state == CircuitState.HALF_OPEN:
                # Allow limited requests in half-open state with race condition protection
                if self.success_count + self.failure_count + self._in_flight < self.half_open_max_calls:
                    self._in_flight += 1
                    return True
                return False
            
            return False
    
    async def record_completion(self) -> None:
        """Record request completion (decrement in-flight counter)"""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN and self._in_flight > 0:
                self._in_flight -= 1
    
    async def record_success(self) -> None:
        """Record a successful execution"""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.half_open_max_calls:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    logger.info("Circuit breaker CLOSED (recovered)")
            else:
                self.failure_count = 0
    
    async def record_failure(self) -> None:
        """Record a failed execution"""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning("Circuit breaker OPEN (failed in half-open)")
            elif self.failure_count >= self.failure_threshold:
                if self.state != CircuitState.OPEN:
                    self.state = CircuitState.OPEN
                    logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")


class PooledConnectionManager:
    """
    HTTP Connection Pool Manager for peer communication
    
    Features:
    - Persistent connections with keep-alive
    - Per-peer connection limits
    - Circuit breaker pattern
    - Automatic retry with exponential backoff
    - Connection health monitoring
    """
    
    def __init__(
        self,
        default_max_connections: int = 10,
        default_max_keepalive: int = 5,
        default_keepalive_timeout: int = 30
    ):
        self.default_max_connections = default_max_connections
        self.default_max_keepalive = default_max_keepalive
        self.default_keepalive_timeout = default_keepalive_timeout
        
        # Session storage: peer_id -> ClientSession
        self._sessions: Dict[str, ClientSession] = {}
        
        # Pool configuration: peer_id -> PeerConnectionPool
        self._pools: Dict[str, PeerConnectionPool] = {}
        
        # Circuit breakers: peer_id -> CircuitBreaker
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Metrics: peer_id -> ConnectionMetrics
        self._metrics: Dict[str, ConnectionMetrics] = {}
        
        # Retry tracking
        self._retry_counts: Dict[str, int] = defaultdict(int)
        
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the connection pool manager"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Connection pool manager started")
    
    async def stop(self) -> None:
        """Stop the connection pool manager and close all connections"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        async with self._lock:
            # Close all sessions
            close_tasks = []
            for peer_id, session in self._sessions.items():
                close_tasks.append(self._close_session(peer_id, session))
            
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
            
            self._sessions.clear()
            self._pools.clear()
            self._circuit_breakers.clear()
        
        logger.info("Connection pool manager stopped")
    
    async def _close_session(self, peer_id: str, session: ClientSession) -> None:
        """Close a session gracefully"""
        try:
            await session.close()
            logger.debug(f"Closed session for {peer_id}")
        except Exception as e:
            logger.warning(f"Error closing session for {peer_id}: {e}")
    
    def register_peer(
        self,
        peer_id: str,
        base_url: str,
        **kwargs
    ) -> PeerConnectionPool:
        """
        Register a peer with connection pool configuration
        
        Args:
            peer_id: Peer identifier
            base_url: Base URL for the peer
            **kwargs: Additional pool configuration options
            
        Returns:
            PeerConnectionPool configuration
        """
        pool = PeerConnectionPool(
            peer_id=peer_id,
            base_url=base_url.rstrip('/'),
            max_connections=kwargs.get('max_connections', self.default_max_connections),
            max_keepalive=kwargs.get('max_keepalive', self.default_max_keepalive),
            keepalive_timeout=kwargs.get('keepalive_timeout', self.default_keepalive_timeout),
            connect_timeout=kwargs.get('connect_timeout', 5.0),
            total_timeout=kwargs.get('total_timeout', 30.0),
            max_retries=kwargs.get('max_retries', 3),
            failure_threshold=kwargs.get('failure_threshold', 5),
            recovery_timeout=kwargs.get('recovery_timeout', 30.0)
        )
        
        self._pools[peer_id] = pool
        self._circuit_breakers[peer_id] = CircuitBreaker(
            failure_threshold=pool.failure_threshold,
            recovery_timeout=pool.recovery_timeout,
            half_open_max_calls=pool.half_open_max_calls
        )
        self._metrics[peer_id] = ConnectionMetrics()
        
        logger.info(f"Registered peer {peer_id} with connection pool")
        return pool
    
    def _handle_task_exception(self, task: asyncio.Task, peer_id: str) -> None:
        """Handle exceptions from async tasks"""
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Error in async task for peer {peer_id}: {e}")
    
    def unregister_peer(self, peer_id: str) -> None:
        """Unregister a peer and close its connections"""
        if peer_id in self._pools:
            del self._pools[peer_id]
        
        if peer_id in self._circuit_breakers:
            del self._circuit_breakers[peer_id]
        
        if peer_id in self._metrics:
            del self._metrics[peer_id]
        
        # Close session asynchronously with error handling
        if peer_id in self._sessions:
            session = self._sessions.pop(peer_id)
            task = asyncio.create_task(self._close_session(peer_id, session))
            task.add_done_callback(lambda t, pid=peer_id: self._handle_task_exception(t, pid))
        
        logger.info(f"Unregistered peer {peer_id}")
    
    async def _get_session(self, peer_id: str) -> ClientSession:
        """Get or create a ClientSession for a peer"""
        async with self._lock:
            if peer_id not in self._sessions or self._sessions[peer_id].closed:
                pool = self._pools.get(peer_id)
                if not pool:
                    raise ValueError(f"Peer {peer_id} not registered")
                
                # Create connector with pool limits
                connector = aiohttp.TCPConnector(
                    limit=pool.max_connections,
                    limit_per_host=pool.max_connections,
                    keepalive_timeout=pool.keepalive_timeout,
                    enable_cleanup_closed=True,
                    force_close=False
                )
                
                # Create session
                timeout = ClientTimeout(
                    total=pool.total_timeout,
                    connect=pool.connect_timeout
                )
                
                session = ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers={
                        "Connection": "keep-alive",
                        "Keep-Alive": f"timeout={pool.keepalive_timeout}"
                    }
                )
                
                self._sessions[peer_id] = session
                logger.debug(f"Created new session for {peer_id}")
            
            return self._sessions[peer_id]
    
    async def request(
        self,
        peer_id: str,
        method: str,
        path: str,
        read_response: bool = True,
        **kwargs
    ) -> Union[Dict[str, Any], str, aiohttp.ClientResponse]:
        """
        Make an HTTP request with connection pooling and circuit breaker
        
        Args:
            peer_id: Target peer identifier
            method: HTTP method (GET, POST, etc.)
            path: URL path
            read_response: If True, read response body and return json/text
                          If False, return ClientResponse (caller must manage context)
            **kwargs: Additional request arguments
            
        Returns:
            Dict/str if read_response=True, ClientResponse otherwise
            
        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
            PeerNotRegisteredError: If peer is not registered
            ClientError: On connection errors
        """
        pool = self._pools.get(peer_id)
        if not pool:
            raise PeerNotRegisteredError(f"Peer {peer_id} not registered")
        
        circuit = self._circuit_breakers.get(peer_id)
        metrics = self._metrics.get(peer_id)
        
        # Check circuit breaker
        if circuit and not await circuit.can_execute():
            metrics.record_circuit_break()
            raise CircuitBreakerOpenError(f"Circuit breaker is OPEN for peer {peer_id}")
        
        session = await self._get_session(peer_id)
        url = f"{pool.base_url}{path}"
        
        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(pool.max_retries):
            start_time = time.time()
            try:
                async with session.request(method, url, **kwargs) as response:
                    response_time = (time.time() - start_time) * 1000
                    
                    if response.status < 500:  # Success or client error
                        metrics.record_success(response_time)
                        if circuit:
                            await circuit.record_success()
                        
                        # Read response body within context manager
                        if read_response:
                            content_type = response.headers.get('Content-Type', '')
                            if 'application/json' in content_type:
                                result = await response.json()
                            else:
                                result = await response.text()
                            return result
                        else:
                            # Return response object (caller must handle context)
                            return response
                    else:
                        # Server error - might be retryable
                        raise ClientError(f"Server error: {response.status}")
                        
            except ClientError as e:
                last_error = e
                metrics.record_failure()
                
                if circuit:
                    await circuit.record_failure()
                
                if attempt < pool.max_retries - 1:
                    delay = min(2 ** attempt, 30)  # Exponential backoff, max 30s
                    metrics.record_retry()
                    logger.warning(
                        f"Request to {peer_id} failed (attempt {attempt + 1}), "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    break
            except Exception as e:
                last_error = e
                metrics.record_failure()
                if circuit:
                    await circuit.record_failure()
                raise
            finally:
                # Decrement in-flight counter if in HALF_OPEN state
                if circuit:
                    await circuit.record_completion()
        
        # All retries exhausted
        raise last_error or ConnectionPoolError(f"Request to {peer_id} failed after {pool.max_retries} retries")
    
    async def get(self, peer_id: str, path: str, **kwargs) -> aiohttp.ClientResponse:
        """Convenience method for GET requests"""
        return await self.request(peer_id, "GET", path, **kwargs)
    
    async def post(self, peer_id: str, path: str, **kwargs) -> aiohttp.ClientResponse:
        """Convenience method for POST requests"""
        return await self.request(peer_id, "POST", path, **kwargs)
    
    async def get_metrics(self, peer_id: Optional[str] = None) -> Dict:
        """Get connection metrics"""
        if peer_id:
            metrics = self._metrics.get(peer_id)
            if metrics:
                return {
                    "peer_id": peer_id,
                    "total_requests": metrics.total_requests,
                    "successful_requests": metrics.successful_requests,
                    "failed_requests": metrics.failed_requests,
                    "retry_count": metrics.retry_count,
                    "circuit_breaks": metrics.circuit_breaks,
                    "avg_response_time_ms": round(metrics.avg_response_time_ms, 2),
                    "last_failure": metrics.last_failure,
                    "success_rate": round(
                        metrics.successful_requests / max(metrics.total_requests, 1) * 100, 2
                    )
                }
            return {}
        
        # Return all metrics
        return {
            peer_id: await self.get_metrics(peer_id)
            for peer_id in self._metrics.keys()
        }
    
    async def get_circuit_states(self) -> Dict[str, str]:
        """Get circuit breaker states for all peers"""
        return {
            peer_id: circuit.state.value
            for peer_id, circuit in self._circuit_breakers.items()
        }
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup task"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._cleanup_idle_connections()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_idle_connections(self) -> None:
        """Clean up idle connections"""
        # aiohttp handles keep-alive automatically
        # This is a placeholder for custom cleanup if needed
        pass


# Global instance with thread-safe double-checked locking
_pool_manager: Optional[PooledConnectionManager] = None
_pool_manager_lock = threading.Lock()


def get_connection_pool() -> PooledConnectionManager:
    """Get global connection pool manager (thread-safe)"""
    global _pool_manager
    
    # First check without lock (fast path)
    if _pool_manager is None:
        # Acquire lock and check again (slow path)
        with _pool_manager_lock:
            if _pool_manager is None:
                _pool_manager = PooledConnectionManager()
    
    return _pool_manager


async def init_connection_pool() -> PooledConnectionManager:
    """Initialize and start connection pool"""
    pool = get_connection_pool()
    await pool.start()
    return pool


async def shutdown_connection_pool() -> None:
    """Shutdown connection pool"""
    global _pool_manager
    if _pool_manager:
        await _pool_manager.stop()
        _pool_manager = None


# Tests
async def _test_connection_pool():
    """Test connection pool"""
    print("=== Testing Connection Pool ===")
    
    # Test 1: Register peer
    print("\n--- Test 1: Register Peer ---")
    pool = PooledConnectionManager()
    await pool.start()
    
    config = pool.register_peer(
        "test-peer",
        "http://localhost:8001",
        max_connections=5,
        max_retries=2
    )
    print(f"Registered peer: {config.peer_id}")
    print(f"  Max connections: {config.max_connections}")
    print(f"  Max retries: {config.max_retries}")
    
        # Test 2: Circuit breaker
    print("\n--- Test 2: Circuit Breaker ---")
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=5)

    # Simulate failures
    for i in range(4):
        can_execute = await breaker.can_execute()
        print(f"  Attempt {i+1}: can_execute={can_execute}, state={breaker.state.value}")
        if can_execute:
            await breaker.record_failure()
            await breaker.record_completion()  # Decrement in-flight counter
    
    # Wait for recovery
    print("  Waiting 6 seconds for recovery...")
    await asyncio.sleep(6)
    can_execute = await breaker.can_execute()
    print(f"  After recovery: can_execute={can_execute}, state={breaker.state.value}")
    
    # Test 3: Metrics
    print("\n--- Test 3: Metrics ---")
    metrics = ConnectionMetrics()
    metrics.record_success(100)
    metrics.record_success(150)
    metrics.record_failure()
    print(f"  Total: {metrics.total_requests}")
    print(f"  Success: {metrics.successful_requests}")
    print(f"  Failed: {metrics.failed_requests}")
    print(f"  Avg response time: {metrics.avg_response_time_ms:.2f}ms")
    
    # Cleanup
    await pool.stop()
    print("\n=== Connection pool tests passed ===")


if __name__ == "__main__":
    asyncio.run(_test_connection_pool())
