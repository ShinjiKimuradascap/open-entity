"""
Control Plane for AI Service Mesh
Manages service discovery, configuration distribution, and mesh topology
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import time

logger = logging.getLogger(__name__)


@dataclass
class MeshAgent:
    """Agent registered in the mesh"""
    agent_id: str
    host: str
    port: int
    capabilities: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    joined_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: float = field(default_factory=time.time)
    reputation_score: float = 1.0
    

@dataclass
class MeshTopology:
    """Topology of the service mesh"""
    agents: Dict[str, MeshAgent] = field(default_factory=dict)
    connections: Dict[str, Set[str]] = field(default_factory=dict)  # agent_id -> connected_agents
    service_map: Dict[str, List[str]] = field(default_factory=dict)  # service_type -> agent_ids
    
    def add_agent(self, agent: MeshAgent):
        """Add agent to topology"""
        self.agents[agent.agent_id] = agent
        if agent.agent_id not in self.connections:
            self.connections[agent.agent_id] = set()
            
        # Update service map
        for service in agent.services:
            if service not in self.service_map:
                self.service_map[service] = []
            if agent.agent_id not in self.service_map[service]:
                self.service_map[service].append(agent.agent_id)
                
    def remove_agent(self, agent_id: str):
        """Remove agent from topology"""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            
            # Remove from service map
            for service in agent.services:
                if service in self.service_map:
                    self.service_map[service] = [
                        aid for aid in self.service_map[service] 
                        if aid != agent_id
                    ]
            
            # Remove connections
            del self.agents[agent_id]
            if agent_id in self.connections:
                del self.connections[agent_id]
                
            # Remove from other agents' connections
            for conn_set in self.connections.values():
                conn_set.discard(agent_id)
                
    def update_connections(self, agent_id: str, connected_to: List[str]):
        """Update agent connections"""
        if agent_id in self.connections:
            self.connections[agent_id] = set(connected_to)
            
    def get_service_providers(self, service_type: str) -> List[MeshAgent]:
        """Get agents providing a specific service"""
        agent_ids = self.service_map.get(service_type, [])
        return [self.agents[aid] for aid in agent_ids if aid in self.agents]
        
    def get_neighbors(self, agent_id: str) -> List[MeshAgent]:
        """Get neighboring agents"""
        if agent_id not in self.connections:
            return []
        return [
            self.agents[aid] for aid in self.connections[agent_id]
            if aid in self.agents
        ]


class ControlPlane:
    """
    Control plane for the AI Service Mesh
    
    Responsibilities:
    - Service discovery and registry
    - Configuration distribution
    - Mesh topology management
    - Agent lifecycle management
    """
    
    def __init__(self, mesh_id: str = "default"):
        self.mesh_id = mesh_id
        self.topology = MeshTopology()
        self.agents: Dict[str, MeshAgent] = {}
        self.config_store: Dict[str, Dict] = {}
        self.subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._running = False
        self._cleanup_task = None
        
    async def start(self):
        """Start the control plane"""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_stale_agents())
        logger.info(f"Control plane started for mesh {self.mesh_id}")
        
    async def stop(self):
        """Stop the control plane"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Control plane stopped for mesh {self.mesh_id}")
        
    async def register_agent(
        self,
        agent_id: str,
        host: str,
        port: int,
        capabilities: List[str] = None,
        services: List[str] = None,
        metadata: Dict = None
    ) -> bool:
        """
        Register an agent in the mesh
        
        Args:
            agent_id: Unique agent identifier
            host: Agent host address
            port: Agent port
            capabilities: List of agent capabilities
            services: List of services provided
            metadata: Additional agent metadata
            
        Returns:
            True if registration successful
        """
        try:
            agent = MeshAgent(
                agent_id=agent_id,
                host=host,
                port=port,
                capabilities=capabilities or [],
                services=services or [],
                metadata=metadata or {},
                last_seen=time.time()
            )
            
            self.agents[agent_id] = agent
            self.topology.add_agent(agent)
            
            logger.info(f"Agent {agent_id} registered in mesh {self.mesh_id}")
            
            # Notify subscribers
            await self._notify_subscribers('agent_joined', {
                'agent_id': agent_id,
                'services': services or [],
                'capabilities': capabilities or []
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to register agent {agent_id}: {e}")
            return False
            
    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the mesh"""
        if agent_id not in self.agents:
            return False
            
        try:
            del self.agents[agent_id]
            self.topology.remove_agent(agent_id)
            
            logger.info(f"Agent {agent_id} unregistered from mesh {self.mesh_id}")
            
            # Notify subscribers
            await self._notify_subscribers('agent_left', {
                'agent_id': agent_id
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister agent {agent_id}: {e}")
            return False
            
    async def heartbeat(self, agent_id: str, metadata: Dict = None) -> bool:
        """Process agent heartbeat"""
        if agent_id not in self.agents:
            return False
            
        agent = self.agents[agent_id]
        agent.last_seen = time.time()
        
        if metadata:
            agent.metadata.update(metadata)
            
        return True
        
    def discover_services(
        self,
        service_type: Optional[str] = None,
        capabilities: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Discover services in the mesh
        
        Args:
            service_type: Filter by service type
            capabilities: Filter by required capabilities
            
        Returns:
            List of available service endpoints
        """
        results = []
        
        agents_to_check = list(self.agents.values())
        
        # Filter by service type
        if service_type:
            agent_ids = self.topology.service_map.get(service_type, [])
            agents_to_check = [
                self.agents[aid] for aid in agent_ids 
                if aid in self.agents
            ]
        
        # Filter by capabilities
        for agent in agents_to_check:
            if capabilities:
                if not all(c in agent.capabilities for c in capabilities):
                    continue
            
            results.append({
                'agent_id': agent.agent_id,
                'host': agent.host,
                'port': agent.port,
                'services': agent.services,
                'capabilities': agent.capabilities,
                'reputation_score': agent.reputation_score,
                'metadata': agent.metadata
            })
        
        # Sort by reputation score
        results.sort(key=lambda x: x['reputation_score'], reverse=True)
        
        return results
        
    def get_mesh_topology(self) -> Dict:
        """Get current mesh topology"""
        return {
            'mesh_id': self.mesh_id,
            'agent_count': len(self.agents),
            'agents': [
                {
                    'agent_id': a.agent_id,
                    'services': a.services,
                    'capabilities': a.capabilities,
                    'reputation': a.reputation_score,
                    'last_seen': a.last_seen
                }
                for a in self.agents.values()
            ],
            'service_map': {
                service: len(agent_ids)
                for service, agent_ids in self.topology.service_map.items()
            }
        }
        
    async def distribute_config(
        self,
        config_key: str,
        config_value: Dict,
        target_agents: Optional[List[str]] = None
    ) -> int:
        """
        Distribute configuration to agents
        
        Args:
            config_key: Configuration key
            config_value: Configuration value
            target_agents: Specific agents to target (None = all)
            
        Returns:
            Number of agents notified
        """
        self.config_store[config_key] = config_value
        
        notification = {
            'type': 'config_update',
            'key': config_key,
            'value': config_value,
            'timestamp': time.time()
        }
        
        # Notify target agents
        agents_to_notify = target_agents or list(self.agents.keys())
        notified = 0
        
        for agent_id in agents_to_notify:
            if agent_id in self.agents:
                await self._notify_agent(agent_id, notification)
                notified += 1
        
        return notified
        
    def subscribe(self, event_type: str, queue: asyncio.Queue):
        """Subscribe to mesh events"""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(queue)
        
    def unsubscribe(self, event_type: str, queue: asyncio.Queue):
        """Unsubscribe from mesh events"""
        if event_type in self.subscribers:
            if queue in self.subscribers[event_type]:
                self.subscribers[event_type].remove(queue)
                
    async def _notify_subscribers(self, event_type: str, data: Dict):
        """Notify all subscribers of an event"""
        if event_type not in self.subscribers:
            return
            
        message = {
            'type': event_type,
            'data': data,
            'timestamp': time.time()
        }
        
        # Remove dead queues
        dead_queues = []
        for queue in self.subscribers[event_type]:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead_queues.append(queue)
            except Exception as e:
                logger.warning(f"Failed to notify subscriber: {e}")
                dead_queues.append(queue)
        
        # Clean up dead queues
        for queue in dead_queues:
            self.unsubscribe(event_type, queue)
            
    async def _notify_agent(self, agent_id: str, message: Dict):
        """Send notification to specific agent"""
        # This would use actual network communication
        # For now, just log
        logger.debug(f"Notifying agent {agent_id}: {message['type']}")
        
    async def _cleanup_stale_agents(self):
        """Periodically remove stale agents"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                now = time.time()
                stale_threshold = 180  # 3 minutes
                
                stale_agents = [
                    aid for aid, agent in self.agents.items()
                    if now - agent.last_seen > stale_threshold
                ]
                
                for agent_id in stale_agents:
                    logger.warning(f"Removing stale agent {agent_id}")
                    await self.unregister_agent(agent_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(5)
                
    def update_reputation(self, agent_id: str, delta: float):
        """Update agent reputation score"""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            agent.reputation_score = max(0.0, min(1.0, agent.reputation_score + delta))
            
    def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """Get information about a specific agent"""
        if agent_id not in self.agents:
            return None
            
        agent = self.agents[agent_id]
        return {
            'agent_id': agent.agent_id,
            'host': agent.host,
            'port': agent.port,
            'services': agent.services,
            'capabilities': agent.capabilities,
            'reputation_score': agent.reputation_score,
            'metadata': agent.metadata,
            'joined_at': agent.joined_at.isoformat(),
            'last_seen': agent.last_seen
        }
