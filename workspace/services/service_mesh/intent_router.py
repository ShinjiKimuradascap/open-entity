"""
Intent Router for AI Service Mesh
Routes intents to appropriate services using semantic matching
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import time

logger = logging.getLogger(__name__)


class IntentStatus(Enum):
    PENDING = "pending"
    ROUTING = "routing"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class Intent:
    """User intent to be routed to services"""
    intent_id: str
    description: str
    required_capabilities: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher = more important
    max_budget: float = 0.0
    timeout_ms: float = 30000.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    

@dataclass
class IntentResult:
    """Result of intent execution"""
    intent_id: str
    status: IntentStatus
    service_id: Optional[str] = None
    agent_id: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    cost: float = 0.0
    completed_at: float = field(default_factory=time.time)


@dataclass
class RoutingDecision:
    """Decision for routing an intent"""
    intent_id: str
    service_id: str
    agent_id: str
    confidence: float
    estimated_cost: float
    estimated_latency_ms: float
    reasoning: str


class IntentRouter:
    """
    Routes intents to appropriate services in the mesh
    
    Features:
    - Semantic intent matching
    - Multi-hop routing
    - Fallback handling
    - Cost optimization
    - Execution tracking
    """
    
    def __init__(self, service_registry=None, control_plane=None):
        self.registry = service_registry
        self.control_plane = control_plane
        
        # Intent tracking
        self.active_intents: Dict[str, Intent] = {}
        self.intent_results: Dict[str, IntentResult] = {}
        self.intent_history: List[Dict] = []
        
        # Routing strategies
        self.routing_strategies: Dict[str, Callable] = {
            'best_match': self._route_best_match,
            'lowest_cost': self._route_lowest_cost,
            'fastest': self._route_fastest,
            'highest_reputation': self._route_highest_reputation,
        }
        
        # Callbacks
        self.on_intent_completed: Optional[Callable] = None
        self.on_intent_failed: Optional[Callable] = None
        
        # Metrics
        self.metrics = {
            'intents_routed': 0,
            'intents_completed': 0,
            'intents_failed': 0,
            'avg_routing_time_ms': 0.0,
        }
        
    async def submit_intent(
        self,
        description: str,
        required_capabilities: Optional[List[str]] = None,
        constraints: Optional[Dict] = None,
        priority: int = 0,
        max_budget: float = 0.0,
        strategy: str = 'best_match'
    ) -> str:
        """
        Submit an intent for routing and execution
        
        Args:
            description: Natural language description of intent
            required_capabilities: Required service capabilities
            constraints: Additional constraints (latency, region, etc.)
            priority: Intent priority (higher = more important)
            max_budget: Maximum budget for execution
            strategy: Routing strategy to use
            
        Returns:
            intent_id for tracking
        """
        intent_id = f"intent_{int(time.time() * 1000)}"
        
        intent = Intent(
            intent_id=intent_id,
            description=description,
            required_capabilities=required_capabilities or [],
            constraints=constraints or {},
            priority=priority,
            max_budget=max_budget
        )
        
        self.active_intents[intent_id] = intent
        
        # Start routing
        asyncio.create_task(self._route_and_execute(intent, strategy))
        
        logger.info(f"Intent {intent_id} submitted: {description[:50]}...")
        
        return intent_id
        
    async def _route_and_execute(self, intent: Intent, strategy: str):
        """Route intent and execute"""
        start_time = time.time()
        
        try:
            # Select routing strategy
            router = self.routing_strategies.get(strategy, self._route_best_match)
            
            # Make routing decision
            decision = await router(intent)
            
            if not decision:
                result = IntentResult(
                    intent_id=intent.intent_id,
                    status=IntentStatus.FAILED,
                    error="No suitable service found"
                )
                self.intent_results[intent.intent_id] = result
                await self._notify_failure(result)
                return
            
            # Execute
            execution_result = await self._execute_intent(intent, decision)
            
            # Record metrics
            routing_time = (time.time() - start_time) * 1000
            self.metrics['intents_routed'] += 1
            self._update_avg_routing_time(routing_time)
            
            if execution_result.status == IntentStatus.COMPLETED:
                self.metrics['intents_completed'] += 1
                await self._notify_completion(execution_result)
            else:
                self.metrics['intents_failed'] += 1
                await self._notify_failure(execution_result)
            
            # Store in history
            self.intent_history.append({
                'intent_id': intent.intent_id,
                'description': intent.description,
                'decision': {
                    'service_id': decision.service_id,
                    'agent_id': decision.agent_id,
                    'confidence': decision.confidence
                },
                'result': {
                    'status': execution_result.status.value,
                    'execution_time_ms': execution_result.execution_time_ms,
                    'cost': execution_result.cost
                },
                'timestamp': time.time()
            })
            
            # Clean up
            if intent.intent_id in self.active_intents:
                del self.active_intents[intent.intent_id]
                
        except Exception as e:
            logger.error(f"Error routing intent {intent.intent_id}: {e}")
            result = IntentResult(
                intent_id=intent.intent_id,
                status=IntentStatus.FAILED,
                error=str(e)
            )
            self.intent_results[intent.intent_id] = result
            await self._notify_failure(result)
            
    async def _route_best_match(self, intent: Intent) -> Optional[RoutingDecision]:
        """Route to best matching service"""
        if not self.registry:
            return None
        
        # Find matching services
        services = self.registry.find_service_by_intent(
            intent.description,
            intent.required_capabilities
        )
        
        if not services:
            return None
        
        # Score and select best
        best_service = None
        best_score = -1
        
        for service in services:
            # Calculate composite score
            relevance = service.get('relevance_score', 0.5)
            success_rate = service.get('success_rate', 1.0)
            load = service.get('load', 0.0)
            reputation = service.get('metadata', {}).get('reputation_score', 1.0)
            
            # Score: high relevance, success, reputation; low load
            score = (relevance * 0.4 + success_rate * 0.3 + reputation * 0.2) * (1 - load * 0.1)
            
            if score > best_score:
                best_score = score
                best_service = service
        
        if not best_service:
            return None
        
        return RoutingDecision(
            intent_id=intent.intent_id,
            service_id=best_service['service_id'],
            agent_id=best_service['agent_id'],
            confidence=best_score,
            estimated_cost=best_service.get('pricing', {}).get('base_cost', 0),
            estimated_latency_ms=best_service.get('latency_ms', 100),
            reasoning=f"Best semantic match with score {best_score:.2f}"
        )
        
    async def _route_lowest_cost(self, intent: Intent) -> Optional[RoutingDecision]:
        """Route to lowest cost service"""
        if not self.registry:
            return None
        
        services = self.registry.find_services(
            capabilities=intent.required_capabilities
        )
        
        if not services:
            return None
        
        # Find lowest cost
        cheapest = min(services, key=lambda x: x.get('pricing', {}).get('base_cost', float('inf')))
        
        return RoutingDecision(
            intent_id=intent.intent_id,
            service_id=cheapest['service_id'],
            agent_id=cheapest['agent_id'],
            confidence=0.7,
            estimated_cost=cheapest.get('pricing', {}).get('base_cost', 0),
            estimated_latency_ms=cheapest.get('latency_ms', 100),
            reasoning="Lowest cost option"
        )
        
    async def _route_fastest(self, intent: Intent) -> Optional[RoutingDecision]:
        """Route to fastest service"""
        if not self.registry:
            return None
        
        services = self.registry.find_services(
            capabilities=intent.required_capabilities
        )
        
        if not services:
            return None
        
        # Find lowest latency
        fastest = min(services, key=lambda x: x.get('latency_ms', float('inf')))
        
        return RoutingDecision(
            intent_id=intent.intent_id,
            service_id=fastest['service_id'],
            agent_id=fastest['agent_id'],
            confidence=0.8,
            estimated_cost=fastest.get('pricing', {}).get('base_cost', 0),
            estimated_latency_ms=fastest.get('latency_ms', 0),
            reasoning="Lowest latency option"
        )
        
    async def _route_highest_reputation(self, intent: Intent) -> Optional[RoutingDecision]:
        """Route to highest reputation service"""
        if not self.registry:
            return None
        
        services = self.registry.find_services(
            capabilities=intent.required_capabilities
        )
        
        if not services:
            return None
        
        # Find highest reputation
        best = max(
            services,
            key=lambda x: x.get('metadata', {}).get('reputation_score', 0)
        )
        
        return RoutingDecision(
            intent_id=intent.intent_id,
            service_id=best['service_id'],
            agent_id=best['agent_id'],
            confidence=0.85,
            estimated_cost=best.get('pricing', {}).get('base_cost', 0),
            estimated_latency_ms=best.get('latency_ms', 100),
            reasoning="Highest reputation provider"
        )
        
    async def _execute_intent(
        self,
        intent: Intent,
        decision: RoutingDecision
    ) -> IntentResult:
        """Execute intent on selected service"""
        execution_start = time.time()
        
        try:
            # This would make actual service call
            # For now, simulate execution
            await asyncio.sleep(0.05)  # Simulate network latency
            
            execution_time = (time.time() - execution_start) * 1000
            
            return IntentResult(
                intent_id=intent.intent_id,
                status=IntentStatus.COMPLETED,
                service_id=decision.service_id,
                agent_id=decision.agent_id,
                result={"status": "success", "data": "placeholder_result"},
                execution_time_ms=execution_time,
                cost=decision.estimated_cost
            )
            
        except Exception as e:
            return IntentResult(
                intent_id=intent.intent_id,
                status=IntentStatus.FAILED,
                service_id=decision.service_id,
                agent_id=decision.agent_id,
                error=str(e),
                execution_time_ms=(time.time() - execution_start) * 1000
            )
            
    def get_intent_status(self, intent_id: str) -> Optional[Dict]:
        """Get status of an intent"""
        if intent_id in self.active_intents:
            return {
                'intent_id': intent_id,
                'status': 'active',
                'description': self.active_intents[intent_id].description
            }
        
        if intent_id in self.intent_results:
            result = self.intent_results[intent_id]
            return {
                'intent_id': intent_id,
                'status': result.status.value,
                'service_id': result.service_id,
                'agent_id': result.agent_id,
                'result': result.result,
                'error': result.error,
                'execution_time_ms': result.execution_time_ms,
                'cost': result.cost
            }
        
        return None
        
    def get_routing_stats(self) -> Dict:
        """Get routing statistics"""
        return {
            **self.metrics,
            'active_intents': len(self.active_intents),
            'completed_intents': len(self.intent_results),
            'history_size': len(self.intent_history)
        }
        
    def get_intent_history(
        self,
        limit: int = 100,
        service_type: Optional[str] = None
    ) -> List[Dict]:
        """Get intent execution history"""
        history = self.intent_history
        
        if service_type:
            history = [
                h for h in history
                if h.get('service_type') == service_type
            ]
        
        return history[-limit:]
        
    def _update_avg_routing_time(self, new_time: float):
        """Update average routing time"""
        n = self.metrics['intents_routed']
        current_avg = self.metrics['avg_routing_time_ms']
        self.metrics['avg_routing_time_ms'] = (
            (current_avg * (n - 1) + new_time) / n if n > 0 else new_time
        )
        
    async def _notify_completion(self, result: IntentResult):
        """Notify intent completion"""
        if self.on_intent_completed:
            await self.on_intent_completed(result)
        logger.info(f"Intent {result.intent_id} completed successfully")
        
    async def _notify_failure(self, result: IntentResult):
        """Notify intent failure"""
        if self.on_intent_failed:
            await self.on_intent_failed(result)
        logger.warning(f"Intent {result.intent_id} failed: {result.error}")
