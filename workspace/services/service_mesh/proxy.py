"""
Sidecar Proxy for AI Service Mesh
Handles traffic routing, load balancing, circuit breaking
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import time
import json

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class ServiceEndpoint:
    """Represents a service endpoint in the mesh"""
    agent_id: str
    service_type: str
    host: str
    port: int
    capabilities: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    success_rate: float = 1.0
    last_heartbeat: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class CircuitBreaker:
    """Circuit breaker for fault tolerance"""
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0.0
    half_open_calls: int = 0
    
    def can_execute(self) -> bool:
        """Check if request can be executed"""
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        else:  # HALF_OPEN
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False
    
    def record_success(self):
        """Record successful execution"""
        if self.state == CircuitState.HALF_OPEN:
            self.successes += 1
            if self.successes >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failures = 0
                self.successes = 0
        else:
            self.failures = 0
    
    def record_failure(self):
        """Record failed execution"""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN


@dataclass
class RoutingRule:
    """Routing rule for traffic management"""
    service_type: str
    priority: int = 0
    weight: int = 100
    required_capabilities: List[str] = field(default_factory=list)
    max_latency_ms: float = 1000.0
    retry_count: int = 3
    timeout_ms: float = 5000.0


class SidecarProxy:
    """
    Sidecar proxy for AI agents in the service mesh
    
    Provides:
    - Dynamic traffic routing
    - Load balancing
    - Circuit breaking
    - Request retry
    - Metrics collection
    """
    
    def __init__(self, agent_id: str, listen_port: int = 0):
        self.agent_id = agent_id
        self.listen_port = listen_port
        self.endpoints: Dict[str, List[ServiceEndpoint]] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.routing_rules: Dict[str, RoutingRule] = {}
        self.request_handlers: Dict[str, Callable] = {}
        self.metrics = {
            'requests_total': 0,
            'requests_success': 0,
            'requests_failed': 0,
            'latency_ms': [],
        }
        self._running = False
        self._server = None
        
    async def start(self):
        """Start the sidecar proxy"""
        self._running = True
        logger.info(f"Sidecar proxy started for agent {self.agent_id}")
        
        # Start background tasks
        asyncio.create_task(self._health_check_loop())
        asyncio.create_task(self._metrics_reporter())
        
    async def stop(self):
        """Stop the sidecar proxy"""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info(f"Sidecar proxy stopped for agent {self.agent_id}")
        
    def register_endpoint(self, endpoint: ServiceEndpoint):
        """Register a service endpoint"""
        service_type = endpoint.service_type
        if service_type not in self.endpoints:
            self.endpoints[service_type] = []
        
        # Update existing or add new
        existing = next(
            (e for e in self.endpoints[service_type] if e.agent_id == endpoint.agent_id),
            None
        )
        if existing:
            idx = self.endpoints[service_type].index(existing)
            self.endpoints[service_type][idx] = endpoint
        else:
            self.endpoints[service_type].append(endpoint)
            
        # Initialize circuit breaker
        cb_key = f"{service_type}:{endpoint.agent_id}"
        if cb_key not in self.circuit_breakers:
            self.circuit_breakers[cb_key] = CircuitBreaker()
            
        logger.debug(f"Registered endpoint {endpoint.agent_id} for {service_type}")
        
    def unregister_endpoint(self, agent_id: str, service_type: str):
        """Unregister a service endpoint"""
        if service_type in self.endpoints:
            self.endpoints[service_type] = [
                e for e in self.endpoints[service_type] 
                if e.agent_id != agent_id
            ]
        
        cb_key = f"{service_type}:{agent_id}"
        if cb_key in self.circuit_breakers:
            del self.circuit_breakers[cb_key]
            
    def set_routing_rule(self, rule: RoutingRule):
        """Set routing rule for a service type"""
        self.routing_rules[rule.service_type] = rule
        
    async def route_request(
        self, 
        service_type: str, 
        request: Dict[str, Any],
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Route a request to appropriate service endpoint
        
        Args:
            service_type: Type of service requested
            request: Request payload
            context: Optional routing context
            
        Returns:
            Response from service
        """
        self.metrics['requests_total'] += 1
        start_time = time.time()
        
        rule = self.routing_rules.get(service_type, RoutingRule(service_type))
        
        # Select endpoint using load balancing
        endpoint = self._select_endpoint(service_type, rule)
        if not endpoint:
            self.metrics['requests_failed'] += 1
            return {
                'success': False,
                'error': f'No available endpoint for service {service_type}'
            }
        
        # Check circuit breaker
        cb_key = f"{service_type}:{endpoint.agent_id}"
        cb = self.circuit_breakers.get(cb_key, CircuitBreaker())
        
        if not cb.can_execute():
            self.metrics['requests_failed'] += 1
            return {
                'success': False,
                'error': f'Circuit breaker open for {endpoint.agent_id}'
            }
        
        # Execute request with retry
        for attempt in range(rule.retry_count):
            try:
                response = await self._execute_request(endpoint, request, rule.timeout_ms)
                cb.record_success()
                
                latency = (time.time() - start_time) * 1000
                self.metrics['requests_success'] += 1
                self.metrics['latency_ms'].append(latency)
                
                # Update endpoint stats
                endpoint.latency_ms = latency
                
                return response
                
            except Exception as e:
                logger.warning(f"Request failed to {endpoint.agent_id} (attempt {attempt + 1}): {e}")
                if attempt == rule.retry_count - 1:
                    cb.record_failure()
                    self.metrics['requests_failed'] += 1
                    return {
                        'success': False,
                        'error': str(e)
                    }
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
        
        return {'success': False, 'error': 'Max retries exceeded'}
        
    def _select_endpoint(
        self, 
        service_type: str, 
        rule: RoutingRule
    ) -> Optional[ServiceEndpoint]:
        """
        Select best endpoint using weighted least connections
        """
        if service_type not in self.endpoints:
            return None
        
        candidates = self.endpoints[service_type]
        
        # Filter by capabilities
        if rule.required_capabilities:
            candidates = [
                e for e in candidates
                if all(c in e.capabilities for c in rule.required_capabilities)
            ]
        
        # Filter by latency
        candidates = [
            e for e in candidates
            if e.latency_ms <= rule.max_latency_ms
        ]
        
        # Filter out open circuits
        candidates = [
            e for e in candidates
            if self.circuit_breakers.get(
                f"{service_type}:{e.agent_id}", CircuitBreaker()
            ).state != CircuitState.OPEN
        ]
        
        if not candidates:
            return None
        
        # Weighted selection based on success rate and latency
        best_score = -1
        best_endpoint = None
        
        for endpoint in candidates:
            score = endpoint.success_rate * (1.0 / (1.0 + endpoint.latency_ms / 100))
            if score > best_score:
                best_score = score
                best_endpoint = endpoint
        
        return best_endpoint
        
    async def _execute_request(
        self, 
        endpoint: ServiceEndpoint, 
        request: Dict,
        timeout_ms: float
    ) -> Dict:
        """Execute request to endpoint"""
        # This would use WebSocket or HTTP to communicate
        # For now, simulate with direct handler call
        
        handler = self.request_handlers.get(endpoint.service_type)
        if handler:
            return await handler(request, endpoint)
        
        # Fallback to direct communication
        return await self._direct_request(endpoint, request, timeout_ms)
        
    async def _direct_request(
        self, 
        endpoint: ServiceEndpoint, 
        request: Dict,
        timeout_ms: float
    ) -> Dict:
        """Send direct request to endpoint"""
        # Implementation would use actual network call
        # Placeholder for now
        await asyncio.sleep(0.01)  # Simulate network latency
        return {'success': True, 'data': 'placeholder'}
        
    def register_handler(self, service_type: str, handler: Callable):
        """Register a handler for local service"""
        self.request_handlers[service_type] = handler
        
    async def _health_check_loop(self):
        """Periodic health check of endpoints"""
        while self._running:
            try:
                await self._check_endpoints_health()
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(5)
                
    async def _check_endpoints_health(self):
        """Check health of all endpoints"""
        now = time.time()
        for service_type, endpoints in self.endpoints.items():
            for endpoint in endpoints:
                # Remove stale endpoints
                if now - endpoint.last_heartbeat > 120:  # 2 minutes timeout
                    logger.warning(f"Removing stale endpoint {endpoint.agent_id}")
                    self.unregister_endpoint(endpoint.agent_id, service_type)
                    
    async def _metrics_reporter(self):
        """Report metrics periodically"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Report every minute
                
                if self.metrics['requests_total'] > 0:
                    success_rate = self.metrics['requests_success'] / self.metrics['requests_total']
                    avg_latency = sum(self.metrics['latency_ms']) / len(self.metrics['latency_ms']) if self.metrics['latency_ms'] else 0
                    
                    logger.info(
                        f"Mesh metrics - Requests: {self.metrics['requests_total']}, "
                        f"Success: {success_rate:.2%}, "
                        f"Avg latency: {avg_latency:.1f}ms"
                    )
                    
                    # Reset latency metrics
                    self.metrics['latency_ms'] = []
                    
            except Exception as e:
                logger.error(f"Metrics reporting error: {e}")
                
    def get_stats(self) -> Dict:
        """Get proxy statistics"""
        return {
            'agent_id': self.agent_id,
            'endpoints_count': sum(len(e) for e in self.endpoints.values()),
            'services_count': len(self.endpoints),
            'metrics': self.metrics.copy(),
            'circuit_states': {
                k: v.state.value for k, v in self.circuit_breakers.items()
            }
        }
