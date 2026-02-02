"""
AI Service Mesh Node
Unified interface for agent participation in the mesh
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from .proxy import SidecarProxy, ServiceEndpoint, RoutingRule
from .control_plane import ControlPlane, MeshAgent
from .service_registry import MeshServiceRegistry, ServiceDefinition
from .intent_router import IntentRouter, IntentResult

logger = logging.getLogger(__name__)


@dataclass
class MeshConfig:
    """Configuration for mesh node"""
    agent_id: str
    host: str = "localhost"
    port: int = 0
    mesh_id: str = "default"
    capabilities: List[str] = None
    enable_proxy: bool = True
    enable_registry: bool = True
    enable_intent_routing: bool = True
    dht_node = None


class MeshNode:
    """
    AI Service Mesh Node
    
    Provides unified interface for agents to:
    - Join/leave the mesh
    - Register/discover services
    - Route intents to services
    - Handle incoming requests
    """
    
    def __init__(self, config: MeshConfig):
        self.config = config
        self.agent_id = config.agent_id
        
        # Components
        self.control_plane = ControlPlane(mesh_id=config.mesh_id)
        self.proxy = SidecarProxy(agent_id=config.agent_id) if config.enable_proxy else None
        self.registry = MeshServiceRegistry(dht_node=config.dht_node) if config.enable_registry else None
        self.intent_router = IntentRouter(
            service_registry=self.registry,
            control_plane=self.control_plane
        ) if config.enable_intent_routing else None
        
        self._running = False
        self._local_handlers: Dict[str, Callable] = {}
        
    async def start(self):
        """Start the mesh node"""
        if self._running:
            return
            
        logger.info(f"Starting mesh node for agent {self.agent_id}")
        
        # Start control plane
        await self.control_plane.start()
        
        # Register self
        await self.control_plane.register_agent(
            agent_id=self.agent_id,
            host=self.config.host,
            port=self.config.port,
            capabilities=self.config.capabilities or []
        )
        
        # Start proxy
        if self.proxy:
            await self.proxy.start()
        
        # Start registry
        if self.registry:
            await self.registry.start()
        
        self._running = True
        logger.info(f"Mesh node {self.agent_id} started successfully")
        
    async def stop(self):
        """Stop the mesh node"""
        if not self._running:
            return
            
        logger.info(f"Stopping mesh node {self.agent_id}")
        
        # Unregister from control plane
        await self.control_plane.unregister_agent(self.agent_id)
        
        # Stop components
        if self.proxy:
            await self.proxy.stop()
        if self.registry:
            await self.registry.stop()
        await self.control_plane.stop()
        
        self._running = False
        logger.info(f"Mesh node {self.agent_id} stopped")
        
    async def register_service(
        self,
        service_type: str,
        name: str,
        description: str = "",
        capabilities: List[str] = None,
        pricing: Dict = None,
        handler: Callable = None
    ) -> str:
        """
        Register a service in the mesh
        
        Args:
            service_type: Type of service
            name: Service name
            description: Service description
            capabilities: Service capabilities
            pricing: Pricing information
            handler: Request handler function
            
        Returns:
            service_id
        """
        service_id = f"{self.agent_id}:{service_type}:{name}"
        
        # Create service definition
        service_def = ServiceDefinition(
            service_id=service_id,
            service_type=service_type,
            agent_id=self.agent_id,
            name=name,
            description=description,
            capabilities=capabilities or [],
            pricing=pricing or {}
        )
        
        # Register in registry
        if self.registry:
            endpoint = f"{self.config.host}:{self.config.port}"
            await self.registry.register_service(service_def, endpoint)
        
        # Register handler in proxy
        if handler and self.proxy:
            self.proxy.register_handler(service_type, handler)
            self._local_handlers[service_type] = handler
        
        # Update control plane
        await self.control_plane.register_agent(
            agent_id=self.agent_id,
            host=self.config.host,
            port=self.config.port,
            capabilities=capabilities or [],
            services=[service_type]
        )
        
        logger.info(f"Service {service_id} registered")
        return service_id
        
    async def discover_services(
        self,
        service_type: Optional[str] = None,
        capabilities: Optional[List[str]] = None
    ) -> List[Dict]:
        """Discover available services"""
        if self.registry:
            return self.registry.find_services(service_type, capabilities)
        return []
        
    async def submit_intent(
        self,
        description: str,
        required_capabilities: Optional[List[str]] = None,
        strategy: str = 'best_match'
    ) -> str:
        """
        Submit an intent for execution
        
        Args:
            description: Intent description
            required_capabilities: Required capabilities
            strategy: Routing strategy
            
        Returns:
            intent_id for tracking
        """
        if self.intent_router:
            return await self.intent_router.submit_intent(
                description=description,
                required_capabilities=required_capabilities,
                strategy=strategy
            )
        raise RuntimeError("Intent routing not enabled")
        
    def get_intent_status(self, intent_id: str) -> Optional[Dict]:
        """Get intent execution status"""
        if self.intent_router:
            return self.intent_router.get_intent_status(intent_id)
        return None
        
    async def call_service(
        self,
        service_type: str,
        request: Dict[str, Any]
    ) -> Dict:
        """
        Call a service through the mesh
        
        Args:
            service_type: Type of service to call
            request: Request payload
            
        Returns:
            Response from service
        """
        if self.proxy:
            return await self.proxy.route_request(service_type, request)
        raise RuntimeError("Proxy not enabled")
        
    def get_stats(self) -> Dict:
        """Get mesh node statistics"""
        return {
            'agent_id': self.agent_id,
            'running': self._running,
            'control_plane': self.control_plane.get_mesh_topology(),
            'proxy': self.proxy.get_stats() if self.proxy else None,
            'registry': self.registry.get_stats() if self.registry else None,
            'intent_router': self.intent_router.get_routing_stats() if self.intent_router else None
        }
        
    async def heartbeat(self):
        """Send heartbeat to control plane"""
        await self.control_plane.heartbeat(self.agent_id)
        
    def is_healthy(self) -> bool:
        """Check if node is healthy"""
        return self._running
