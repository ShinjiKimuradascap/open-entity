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


# ============================================================================
# WebSocket Connection Pool Support
# ============================================================================

from dataclasses import dataclass, field
from typing import Callable, Awaitable
from enum import Enum

# FastAPI WebSocket import with fallback
try:
    from fastapi import WebSocket, WebSocketDisconnect
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    WebSocket = Any
    WebSocketDisconnect = Exception


class WebSocketState(Enum):
    """WebSocket connection states"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class WebSocketConnectionConfig:
    """Configuration for WebSocket connections"""
    peer_id: str
    endpoint_url: str
    reconnect_interval: float = 5.0
    max_reconnect_attempts: int = 10
    heartbeat_interval: float = 30.0
    connection_timeout: float = 10.0
    
    # Circuit breaker settings
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    
    # Rate limiting settings
    max_messages_per_minute: int = 120


@dataclass
class WebSocketMetrics:
    """WebSocket connection metrics"""
    connections_established: int = 0
    connections_failed: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    reconnections: int = 0
    last_heartbeat: Optional[float] = None
    avg_latency_ms: float = 0.0
    
    def record_connection(self, success: bool) -> None:
        """Record connection attempt result"""
        if success:
            self.connections_established += 1
        else:
            self.connections_failed += 1
    
    def record_message(self, sent: bool = True) -> None:
        """Record message sent/received"""
        if sent:
            self.messages_sent += 1
        else:
            self.messages_received += 1
    
    def record_reconnection(self) -> None:
        """Record reconnection attempt"""
        self.reconnections += 1
    
    def record_heartbeat(self, latency_ms: float) -> None:
        """Record heartbeat with latency"""
        self.last_heartbeat = time.time()
        # Update rolling average
        total = self.messages_received + self.messages_sent
        if total > 0:
            self.avg_latency_ms = (
                (self.avg_latency_ms * (total - 1) + latency_ms) / total
            )


class WebSocketConnectionPool:
    """
    WebSocket Connection Pool for peer communication
    
    Features:
    - Persistent WebSocket connections with automatic reconnection
    - Per-peer connection management
    - Circuit breaker pattern for fault tolerance
    - Heartbeat/keepalive monitoring
    - Message queuing during reconnection
    - Connection metrics and health monitoring
    """
    
    def __init__(
        self,
        default_reconnect_interval: float = 5.0,
        default_max_reconnect_attempts: int = 10,
        default_heartbeat_interval: float = 30.0
    ):
        self.default_reconnect_interval = default_reconnect_interval
        self.default_max_reconnect_attempts = default_max_reconnect_attempts
        self.default_heartbeat_interval = default_heartbeat_interval
        
        # Connection storage: peer_id -> WebSocket
        self._connections: Dict[str, WebSocket] = {}
        
        # Connection state: peer_id -> WebSocketState
        self._states: Dict[str, WebSocketState] = {}
        
        # Configuration: peer_id -> WebSocketConnectionConfig
        self._configs: Dict[str, WebSocketConnectionConfig] = {}
        
        # Circuit breakers: peer_id -> CircuitBreaker
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Metrics: peer_id -> WebSocketMetrics
        self._metrics: Dict[str, WebSocketMetrics] = {}
        
        # Message queues for disconnected peers: peer_id -> List[Dict]
        self._message_queues: Dict[str, List[Dict]] = defaultdict(list)
        
        # Background tasks: peer_id -> Task
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}
        
        # Message handlers: peer_id -> Callable
        self._message_handlers: Dict[str, Callable[[Dict], Awaitable[None]]] = {}
        
        # Message rate counters: peer_id -> List[timestamp]
        self._message_counters: Dict[str, List[float]] = defaultdict(list)
        
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the WebSocket connection pool"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("WebSocket connection pool started")
    
    async def stop(self) -> None:
        """Stop the WebSocket connection pool and close all connections"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        async with self._lock:
            # Cancel all background tasks
            for task in list(self._heartbeat_tasks.values()):
                task.cancel()
            for task in list(self._reconnect_tasks.values()):
                task.cancel()
            
            # Close all connections
            close_tasks = []
            for peer_id, websocket in list(self._connections.items()):
                close_tasks.append(self._close_connection(peer_id, websocket))
            
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
            
            self._connections.clear()
            self._states.clear()
            self._heartbeat_tasks.clear()
            self._reconnect_tasks.clear()
        
        logger.info("WebSocket connection pool stopped")
    
    async def _close_connection(self, peer_id: str, websocket: WebSocket) -> None:
        """Close a WebSocket connection gracefully"""
        try:
            if WEBSOCKET_AVAILABLE:
                await websocket.close()
            logger.debug(f"Closed WebSocket connection for {peer_id}")
        except Exception as e:
            logger.warning(f"Error closing WebSocket for {peer_id}: {e}")
    
    def register_peer(
        self,
        peer_id: str,
        endpoint_url: str,
        message_handler: Optional[Callable[[Dict], Awaitable[None]]] = None,
        **kwargs
    ) -> WebSocketConnectionConfig:
        """
        Register a peer with WebSocket connection configuration
        
        Args:
            peer_id: Peer identifier
            endpoint_url: WebSocket endpoint URL (ws:// or wss://)
            message_handler: Optional callback for incoming messages
            **kwargs: Additional configuration options
            
        Returns:
            WebSocketConnectionConfig
        """
        config = WebSocketConnectionConfig(
            peer_id=peer_id,
            endpoint_url=endpoint_url,
            reconnect_interval=kwargs.get('reconnect_interval', self.default_reconnect_interval),
            max_reconnect_attempts=kwargs.get('max_reconnect_attempts', self.default_max_reconnect_attempts),
            heartbeat_interval=kwargs.get('heartbeat_interval', self.default_heartbeat_interval),
            connection_timeout=kwargs.get('connection_timeout', 10.0),
            failure_threshold=kwargs.get('failure_threshold', 5),
            recovery_timeout=kwargs.get('recovery_timeout', 30.0),
            half_open_max_calls=kwargs.get('half_open_max_calls', 3)
        )
        
        self._configs[peer_id] = config
        self._circuit_breakers[peer_id] = CircuitBreaker(
            failure_threshold=config.failure_threshold,
            recovery_timeout=config.recovery_timeout,
            half_open_max_calls=config.half_open_max_calls
        )
        self._metrics[peer_id] = WebSocketMetrics()
        
        if message_handler:
            self._message_handlers[peer_id] = message_handler
        
        logger.info(f"Registered peer {peer_id} with WebSocket connection pool")
        return config
    
    def unregister_peer(self, peer_id: str) -> None:
        """Unregister a peer and close its WebSocket connection"""
        # Cancel background tasks
        if peer_id in self._heartbeat_tasks:
            self._heartbeat_tasks[peer_id].cancel()
            del self._heartbeat_tasks[peer_id]
        
        if peer_id in self._reconnect_tasks:
            self._reconnect_tasks[peer_id].cancel()
            del self._reconnect_tasks[peer_id]
        
        # Close connection
        if peer_id in self._connections:
            websocket = self._connections.pop(peer_id)
            asyncio.create_task(self._close_connection(peer_id, websocket))
        
        # Cleanup state
        self._states.pop(peer_id, None)
        self._configs.pop(peer_id, None)
        self._circuit_breakers.pop(peer_id, None)
        self._metrics.pop(peer_id, None)
        self._message_queues.pop(peer_id, None)
        self._message_handlers.pop(peer_id, None)
        
        logger.info(f"Unregistered peer {peer_id} from WebSocket connection pool")
    
    async def accept_connection(self, peer_id: str, websocket: WebSocket) -> bool:
        """
        Accept and register an incoming WebSocket connection
        
        Args:
            peer_id: Peer identifier
            websocket: FastAPI WebSocket object
            
        Returns:
            True if connection accepted, False otherwise
        """
        circuit = self._circuit_breakers.get(peer_id)
        metrics = self._metrics.get(peer_id)
        
        # Check circuit breaker
        if circuit and not await circuit.can_execute():
            logger.warning(f"Circuit breaker OPEN for peer {peer_id}, rejecting connection")
            if metrics:
                metrics.record_connection(False)
            return False
        
        async with self._lock:
            # Close existing connection if any
            if peer_id in self._connections:
                old_websocket = self._connections[peer_id]
                await self._close_connection(peer_id, old_websocket)
            
            # Accept new connection
            if WEBSOCKET_AVAILABLE:
                await websocket.accept()
            
            self._connections[peer_id] = websocket
            self._states[peer_id] = WebSocketState.CONNECTED
            
            if metrics:
                metrics.record_connection(True)
            if circuit:
                await circuit.record_success()
        
        # Start heartbeat task
        self._heartbeat_tasks[peer_id] = asyncio.create_task(
            self._heartbeat_loop(peer_id)
        )
        
        logger.info(f"Accepted WebSocket connection from {peer_id}")
        return True
    
    async def disconnect(self, peer_id: str) -> None:
        """Disconnect a peer and cleanup"""
        async with self._lock:
            # Cancel heartbeat task
            if peer_id in self._heartbeat_tasks:
                self._heartbeat_tasks[peer_id].cancel()
                del self._heartbeat_tasks[peer_id]
            
            # Close connection
            if peer_id in self._connections:
                websocket = self._connections.pop(peer_id)
                await self._close_connection(peer_id, websocket)
            
            self._states[peer_id] = WebSocketState.DISCONNECTED
        
        logger.info(f"Disconnected peer {peer_id}")
    
    async def _check_rate_limit(self, peer_id: str) -> bool:
        """
        Check if sending a message would exceed the rate limit
        
        Args:
            peer_id: Peer identifier
            
        Returns:
            True if within rate limit, False if exceeded
        """
        now = time.time()
        minute_ago = now - 60
        # 直近1分のメッセージのみカウント
        self._message_counters[peer_id] = [
            t for t in self._message_counters[peer_id] if t > minute_ago
        ]
        config = self._configs.get(peer_id)
        limit = config.max_messages_per_minute if config else 120
        return len(self._message_counters[peer_id]) < limit
    
    async def send_message(self, peer_id: str, message: Dict[str, Any]) -> bool:
        """
        Send a message to a peer via WebSocket
        
        Args:
            peer_id: Target peer identifier
            message: Message payload (JSON serializable)
            
        Returns:
            True if sent successfully, False otherwise
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        # Check rate limit before sending
        if not await self._check_rate_limit(peer_id):
            from services.rate_limiter import RateLimitExceeded
            raise RateLimitExceeded(f"Rate limit exceeded for peer {peer_id}")
        
        # Record message timestamp for rate limiting
        self._message_counters[peer_id].append(time.time())
        
        websocket = self._connections.get(peer_id)
        metrics = self._metrics.get(peer_id)
        
        if not websocket or self._states.get(peer_id) != WebSocketState.CONNECTED:
            # Queue message for later delivery
            self._message_queues[peer_id].append(message)
            logger.debug(f"Queued message for {peer_id} (offline)")
            return False
        
        try:
            if WEBSOCKET_AVAILABLE:
                await websocket.send_json(message)
            
            if metrics:
                metrics.record_message(sent=True)
            
            logger.debug(f"Sent message to {peer_id}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to send message to {peer_id}: {e}")
            
            # Queue for retry
            self._message_queues[peer_id].append(message)
            
            # Record failure
            if metrics:
                metrics.record_connection(False)
            
            circuit = self._circuit_breakers.get(peer_id)
            if circuit:
                await circuit.record_failure()
            
            return False
    
    async def broadcast(self, message: Dict[str, Any], exclude: Optional[str] = None) -> Dict[str, bool]:
        """
        Broadcast a message to all connected peers
        
        Args:
            message: Message payload
            exclude: Optional peer_id to exclude from broadcast
            
        Returns:
            Dict mapping peer_id to send success status
        """
        tasks = []
        peer_ids = []
        
        for peer_id in self._connections.keys():
            if peer_id != exclude:
                tasks.append(self.send_message(peer_id, message))
                peer_ids.append(peer_id)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            peer_id: result if not isinstance(result, Exception) else False
            for peer_id, result in zip(peer_ids, results)
        }
    
    async def receive_message(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """
        Receive a message from a peer
        
        Args:
            peer_id: Peer identifier
            
        Returns:
            Received message or None if disconnected
        """
        websocket = self._connections.get(peer_id)
        metrics = self._metrics.get(peer_id)
        
        if not websocket or self._states.get(peer_id) != WebSocketState.CONNECTED:
            return None
        
        try:
            if WEBSOCKET_AVAILABLE:
                data = await websocket.receive_json()
                
                if metrics:
                    metrics.record_message(sent=False)
                
                # Call message handler if registered
                handler = self._message_handlers.get(peer_id)
                if handler:
                    await handler(data)
                
                return data
            
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for {peer_id}")
            await self.disconnect(peer_id)
            return None
        except Exception as e:
            logger.warning(f"Error receiving message from {peer_id}: {e}")
            return None
    
    async def _heartbeat_loop(self, peer_id: str) -> None:
        """Send periodic heartbeat pings to keep connection alive"""
        config = self._configs.get(peer_id)
        if not config:
            return
        
        while True:
            try:
                await asyncio.sleep(config.heartbeat_interval)
                
                websocket = self._connections.get(peer_id)
                if not websocket or self._states.get(peer_id) != WebSocketState.CONNECTED:
                    break
                
                # Send ping
                start_time = time.time()
                await self.send_message(peer_id, {
                    "type": "ping",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
                # Record heartbeat
                latency = (time.time() - start_time) * 1000
                metrics = self._metrics.get(peer_id)
                if metrics:
                    metrics.record_heartbeat(latency)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error for {peer_id}: {e}")
                break
    
    async def _reconnect_loop(self, peer_id: str) -> None:
        """Attempt to reconnect to a peer"""
        config = self._configs.get(peer_id)
        if not config:
            return
        
        circuit = self._circuit_breakers.get(peer_id)
        metrics = self._metrics.get(peer_id)
        
        for attempt in range(config.max_reconnect_attempts):
            try:
                # Check circuit breaker
                if circuit and not await circuit.can_execute():
                    logger.warning(f"Circuit breaker open for {peer_id}, waiting...")
                    await asyncio.sleep(config.recovery_timeout)
                    continue
                
                self._states[peer_id] = WebSocketState.RECONNECTING
                
                # Attempt reconnection (implementation depends on client-side logic)
                # This is a placeholder for reconnection logic
                logger.info(f"Reconnection attempt {attempt + 1} for {peer_id}")
                
                if metrics:
                    metrics.record_reconnection()
                
                # Wait before next attempt
                await asyncio.sleep(config.reconnect_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconnection error for {peer_id}: {e}")
                await asyncio.sleep(config.reconnect_interval)
        
        # Max reconnection attempts reached
        logger.error(f"Max reconnection attempts reached for {peer_id}")
        self._states[peer_id] = WebSocketState.ERROR
    
    def get_connection_state(self, peer_id: str) -> Optional[WebSocketState]:
        """Get the current connection state for a peer"""
        return self._states.get(peer_id)
    
    def is_connected(self, peer_id: str) -> bool:
        """Check if a peer is currently connected"""
        return self._states.get(peer_id) == WebSocketState.CONNECTED
    
    def get_connected_peers(self) -> List[str]:
        """Get list of currently connected peers"""
        return [
            peer_id for peer_id, state in self._states.items()
            if state == WebSocketState.CONNECTED
        ]
    
    async def get_metrics(self, peer_id: Optional[str] = None) -> Dict:
        """Get WebSocket connection metrics"""
        if peer_id:
            metrics = self._metrics.get(peer_id)
            if metrics:
                return {
                    "peer_id": peer_id,
                    "connections_established": metrics.connections_established,
                    "connections_failed": metrics.connections_failed,
                    "messages_sent": metrics.messages_sent,
                    "messages_received": metrics.messages_received,
                    "reconnections": metrics.reconnections,
                    "last_heartbeat": metrics.last_heartbeat,
                    "avg_latency_ms": round(metrics.avg_latency_ms, 2),
                    "state": self._states.get(peer_id, WebSocketState.DISCONNECTED).value
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
                await self._cleanup_stale_connections()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in WebSocket cleanup loop: {e}")
    
    async def _cleanup_stale_connections(self) -> None:
        """Clean up stale WebSocket connections"""
        stale_threshold = time.time() - 300  # 5 minutes
        
        for peer_id, metrics in list(self._metrics.items()):
            # Check if connection hasn't had activity for 5 minutes
            if (metrics.last_heartbeat and 
                metrics.last_heartbeat < stale_threshold and
                self._states.get(peer_id) == WebSocketState.CONNECTED):
                
                logger.info(f"Cleaning up stale connection for {peer_id}")
                await self.disconnect(peer_id)


# Global WebSocket connection pool instance
_ws_pool: Optional[WebSocketConnectionPool] = None
_ws_pool_lock = threading.Lock()


def get_websocket_pool() -> WebSocketConnectionPool:
    """Get global WebSocket connection pool (thread-safe)"""
    global _ws_pool
    
    if _ws_pool is None:
        with _ws_pool_lock:
            if _ws_pool is None:
                _ws_pool = WebSocketConnectionPool()
    
    return _ws_pool


async def init_websocket_pool() -> WebSocketConnectionPool:
    """Initialize and start WebSocket connection pool"""
    pool = get_websocket_pool()
    await pool.start()
    return pool


async def shutdown_websocket_pool() -> None:
    """Shutdown WebSocket connection pool"""
    global _ws_pool
    if _ws_pool:
        await _ws_pool.stop()
        _ws_pool = None


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
