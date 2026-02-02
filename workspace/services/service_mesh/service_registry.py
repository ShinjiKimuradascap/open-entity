"""
Service Registry for AI Service Mesh
DHT-based decentralized service discovery
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import hashlib
import time

logger = logging.getLogger(__name__)


@dataclass
class ServiceDefinition:
    """Definition of a service in the mesh"""
    service_id: str
    service_type: str
    agent_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    pricing: Dict[str, Any] = field(default_factory=dict)
    schema: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ServiceDefinition':
        return cls(**data)
    
    def get_key(self) -> str:
        """Generate DHT key for this service"""
        key_string = f"{self.service_type}:{self.agent_id}:{self.service_id}"
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]


@dataclass
class ServiceInstance:
    """Active instance of a service"""
    service_id: str
    agent_id: str
    endpoint: str
    status: str = "active"  # active, degraded, unavailable
    load: float = 0.0  # Current load (0-1)
    latency_ms: float = 0.0
    success_rate: float = 1.0
    last_heartbeat: float = field(default_factory=time.time)
    

class MeshServiceRegistry:
    """
    Decentralized service registry using DHT
    
    Features:
    - DHT-based service storage
    - Local cache for fast lookups
    - Service health tracking
    - Intent-based service matching
    """
    
    def __init__(self, dht_node=None, local_only: bool = False):
        self.dht_node = dht_node
        self.local_only = local_only
        
        # Local storage
        self.services: Dict[str, ServiceDefinition] = {}
        self.instances: Dict[str, ServiceInstance] = {}
        self.agent_services: Dict[str, List[str]] = {}  # agent_id -> service_ids
        self.service_types: Dict[str, List[str]] = {}  # service_type -> service_ids
        
        # Callbacks
        self.on_service_registered: Optional[Callable] = None
        self.on_service_unregistered: Optional[Callable] = None
        
        # Health check
        self._running = False
        self._health_check_task = None
        
    async def start(self):
        """Start the service registry"""
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Service registry started")
        
    async def stop(self):
        """Stop the service registry"""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("Service registry stopped")
        
    async def register_service(
        self,
        service_def: ServiceDefinition,
        endpoint: str
    ) -> bool:
        """
        Register a service in the mesh
        
        Args:
            service_def: Service definition
            endpoint: Service endpoint URL
            
        Returns:
            True if registration successful
        """
        try:
            # Update timestamps
            service_def.updated_at = datetime.utcnow().isoformat()
            
            # Store locally
            self.services[service_def.service_id] = service_def
            
            # Track by agent
            if service_def.agent_id not in self.agent_services:
                self.agent_services[service_def.agent_id] = []
            if service_def.service_id not in self.agent_services[service_def.agent_id]:
                self.agent_services[service_def.agent_id].append(service_def.service_id)
            
            # Track by type
            if service_def.service_type not in self.service_types:
                self.service_types[service_def.service_type] = []
            if service_def.service_id not in self.service_types[service_def.service_type]:
                self.service_types[service_def.service_type].append(service_def.service_id)
            
            # Create instance
            instance = ServiceInstance(
                service_id=service_def.service_id,
                agent_id=service_def.agent_id,
                endpoint=endpoint,
                status="active"
            )
            self.instances[service_def.service_id] = instance
            
            # Store in DHT if available
            if self.dht_node and not self.local_only:
                await self._store_in_dht(service_def)
            
            logger.info(f"Service {service_def.service_id} registered")
            
            # Notify callback
            if self.on_service_registered:
                await self.on_service_registered(service_def)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to register service {service_def.service_id}: {e}")
            return False
            
    async def unregister_service(self, service_id: str) -> bool:
        """Unregister a service"""
        if service_id not in self.services:
            return False
            
        try:
            service_def = self.services[service_id]
            
            # Remove from local storage
            del self.services[service_id]
            if service_id in self.instances:
                del self.instances[service_id]
            
            # Remove from agent tracking
            if service_def.agent_id in self.agent_services:
                self.agent_services[service_def.agent_id] = [
                    sid for sid in self.agent_services[service_def.agent_id]
                    if sid != service_id
                ]
            
            # Remove from type tracking
            if service_def.service_type in self.service_types:
                self.service_types[service_def.service_type] = [
                    sid for sid in self.service_types[service_def.service_type]
                    if sid != service_id
                ]
            
            # Remove from DHT if available
            if self.dht_node and not self.local_only:
                await self._remove_from_dht(service_def)
            
            logger.info(f"Service {service_id} unregistered")
            
            # Notify callback
            if self.on_service_unregistered:
                await self.on_service_unregistered(service_def)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister service {service_id}: {e}")
            return False
            
    def find_services(
        self,
        service_type: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
        min_reputation: float = 0.0
    ) -> List[Dict]:
        """
        Find services matching criteria
        
        Args:
            service_type: Filter by service type
            capabilities: Required capabilities
            agent_id: Filter by agent
            min_reputation: Minimum reputation score
            
        Returns:
            List of matching service definitions
        """
        results = []
        
        # Get candidate service IDs
        if agent_id and agent_id in self.agent_services:
            candidate_ids = self.agent_services[agent_id]
        elif service_type and service_type in self.service_types:
            candidate_ids = self.service_types[service_type]
        else:
            candidate_ids = list(self.services.keys())
        
        # Filter and score
        for service_id in candidate_ids:
            if service_id not in self.services:
                continue
                
            service = self.services[service_id]
            instance = self.instances.get(service_id)
            
            # Filter by capabilities
            if capabilities:
                if not all(c in service.capabilities for c in capabilities):
                    continue
            
            # Filter by agent reputation (from metadata)
            reputation = service.metadata.get('reputation_score', 1.0)
            if reputation < min_reputation:
                continue
            
            # Build result
            result = service.to_dict()
            if instance:
                result['status'] = instance.status
                result['load'] = instance.load
                result['latency_ms'] = instance.latency_ms
                result['success_rate'] = instance.success_rate
            
            results.append(result)
        
        # Sort by quality (success_rate / latency)
        results.sort(
            key=lambda x: x.get('success_rate', 1.0) / (1 + x.get('latency_ms', 0)),
            reverse=True
        )
        
        return results
        
    def find_service_by_intent(
        self,
        intent: str,
        required_capabilities: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Find services based on intent description
        
        Args:
            intent: Natural language intent description
            required_capabilities: Required capabilities
            
        Returns:
            List of matching services
        """
        # Simple keyword matching for now
        # In production, this would use semantic matching
        intent_lower = intent.lower()
        keywords = set(intent_lower.split())
        
        results = []
        
        for service in self.services.values():
            # Check capabilities match
            if required_capabilities:
                if not all(c in service.capabilities for c in required_capabilities):
                    continue
            
            # Calculate relevance score based on keywords
            service_text = f"{service.name} {service.description} {' '.join(service.capabilities)}"
            service_text = service_text.lower()
            
            match_count = sum(1 for keyword in keywords if keyword in service_text)
            relevance = match_count / len(keywords) if keywords else 0
            
            if relevance > 0:
                result = service.to_dict()
                result['relevance_score'] = relevance
                
                instance = self.instances.get(service.service_id)
                if instance:
                    result['status'] = instance.status
                    result['load'] = instance.load
                
                results.append(result)
        
        # Sort by relevance
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return results
        
    def get_service(self, service_id: str) -> Optional[Dict]:
        """Get a specific service by ID"""
        if service_id not in self.services:
            return None
            
        service = self.services[service_id]
        result = service.to_dict()
        
        instance = self.instances.get(service_id)
        if instance:
            result['endpoint'] = instance.endpoint
            result['status'] = instance.status
            result['load'] = instance.load
            result['latency_ms'] = instance.latency_ms
            result['success_rate'] = instance.success_rate
        
        return result
        
    async def update_service_health(
        self,
        service_id: str,
        status: Optional[str] = None,
        load: Optional[float] = None,
        latency_ms: Optional[float] = None,
        success_rate: Optional[float] = None
    ):
        """Update service health metrics"""
        if service_id not in self.instances:
            return
            
        instance = self.instances[service_id]
        instance.last_heartbeat = time.time()
        
        if status:
            instance.status = status
        if load is not None:
            instance.load = load
        if latency_ms is not None:
            instance.latency_ms = latency_ms
        if success_rate is not None:
            instance.success_rate = success_rate
            
    def get_agent_services(self, agent_id: str) -> List[Dict]:
        """Get all services for an agent"""
        service_ids = self.agent_services.get(agent_id, [])
        return [
            self.services[sid].to_dict()
            for sid in service_ids
            if sid in self.services
        ]
        
    def get_service_types(self) -> List[str]:
        """Get all registered service types"""
        return list(self.service_types.keys())
        
    def get_stats(self) -> Dict:
        """Get registry statistics"""
        return {
            'total_services': len(self.services),
            'active_instances': len([
                i for i in self.instances.values()
                if i.status == 'active'
            ]),
            'service_types': len(self.service_types),
            'registered_agents': len(self.agent_services)
        }
        
    async def _store_in_dht(self, service_def: ServiceDefinition):
        """Store service in DHT"""
        if not self.dht_node:
            return
            
        try:
            key = service_def.get_key()
            value = json.dumps(service_def.to_dict())
            # This would call DHT store method
            logger.debug(f"Storing service {service_def.service_id} in DHT")
        except Exception as e:
            logger.error(f"Failed to store in DHT: {e}")
            
    async def _remove_from_dht(self, service_def: ServiceDefinition):
        """Remove service from DHT"""
        if not self.dht_node:
            return
            
        try:
            key = service_def.get_key()
            logger.debug(f"Removing service {service_def.service_id} from DHT")
        except Exception as e:
            logger.error(f"Failed to remove from DHT: {e}")
            
    async def _health_check_loop(self):
        """Periodic health check of services"""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                now = time.time()
                stale_threshold = 120  # 2 minutes
                
                stale_services = [
                    sid for sid, instance in self.instances.items()
                    if now - instance.last_heartbeat > stale_threshold
                ]
                
                for service_id in stale_services:
                    if service_id in self.instances:
                        self.instances[service_id].status = "unavailable"
                        logger.warning(f"Service {service_id} marked unavailable")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(5)
