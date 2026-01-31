"""Decentralized agent registry using DHT."""
import asyncio
import hashlib
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from .protocol import AgentIdentity, AgentRecord


@dataclass
class KBucket:
    """Kademlia k-bucket for routing."""
    k: int = 20
    nodes: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    
    def add(self, node_id: str) -> bool:
        """Add node to bucket. Returns True if added."""
        if node_id in self.nodes:
            self.nodes.remove(node_id)
            self.nodes.append(node_id)
            self.last_updated = time.time()
            return True
        
        if len(self.nodes) < self.k:
            self.nodes.append(node_id)
            self.last_updated = time.time()
            return True
        
        return False
    
    def remove(self, node_id: str):
        """Remove node from bucket."""
        if node_id in self.nodes:
            self.nodes.remove(node_id)


class DHTRegistry:
    """Distributed Hash Table for agent registry."""
    
    def __init__(self, node_id: str, k: int = 20, alpha: int = 3):
        self.node_id = node_id
        self.k = k  # Bucket size
        self.alpha = alpha  # Parallelism
        self.buckets: Dict[int, KBucket] = {}
        self.storage: Dict[str, dict] = {}  # Local storage
        self.bootstrap_nodes: Set[str] = set()
    
    def _distance(self, a: str, b: str) -> int:
        """XOR distance between two node IDs."""
        a_int = int(a, 16)
        b_int = int(b, 16)
        return a_int ^ b_int
    
    def _bucket_index(self, node_id: str) -> int:
        """Get bucket index for node_id."""
        distance = self._distance(self.node_id, node_id)
        if distance == 0:
            return -1
        return distance.bit_length() - 1
    
    def add_node(self, node_id: str) -> bool:
        """Add node to routing table."""
        if node_id == self.node_id:
            return False
        
        idx = self._bucket_index(node_id)
        if idx < 0:
            return False
        
        if idx not in self.buckets:
            self.buckets[idx] = KBucket(k=self.k)
        
        return self.buckets[idx].add(node_id)
    
    def find_closest(self, target_id: str, count: int = None) -> List[str]:
        """Find k closest nodes to target."""
        if count is None:
            count = self.k
        
        all_nodes = []
        for bucket in self.buckets.values():
            all_nodes.extend(bucket.nodes)
        
        all_nodes.sort(key=lambda n: self._distance(n, target_id))
        return all_nodes[:count]
    
    def store(self, key: str, value: dict, ttl: int = 3600):
        """Store value in local storage."""
        self.storage[key] = {
            "value": value,
            "timestamp": time.time(),
            "ttl": ttl,
        }
    
    def retrieve(self, key: str) -> Optional[dict]:
        """Retrieve value from local storage."""
        if key not in self.storage:
            return None
        
        entry = self.storage[key]
        age = time.time() - entry["timestamp"]
        
        if age > entry["ttl"]:
            del self.storage[key]
            return None
        
        return entry["value"]
    
    async def find_value(self, key: str) -> Optional[dict]:
        """Find value in DHT."""
        # Check local first
        local = self.retrieve(key)
        if local:
            return local
        
        # Query closest nodes
        closest = self.find_closest(key, self.alpha)
        
        for node_id in closest:
            # In real implementation, would query remote node
            pass
        
        return None
    
    def register_agent(self, record: AgentRecord):
        """Register agent in DHT."""
        key = record.agent_id
        self.store(key, record.to_dict())
        
        # Also store in capability index
        for capability in record.capabilities:
            cap_key = f"cap:{capability}"
            agents = self.retrieve(cap_key) or []
            if record.agent_id not in agents:
                agents.append(record.agent_id)
                self.store(cap_key, agents)
    
    def find_by_capability(self, capability: str) -> List[str]:
        """Find agents by capability."""
        cap_key = f"cap:{capability}"
        return self.retrieve(cap_key) or []


class AgentRegistry:
    """High-level agent registry interface."""
    
    def __init__(self, identity: AgentIdentity, bootstrap_nodes: List[str] = None):
        self.identity = identity
        self.dht = DHTRegistry(identity.agent_id)
        self.bootstrap_nodes = bootstrap_nodes or []
    
    async def start(self):
        """Start registry and join network."""
        for node in self.bootstrap_nodes:
            self.dht.add_node(node)
    
    async def register(self, record: AgentRecord):
        """Register agent in network."""
        self.dht.register_agent(record)
        # In real implementation, would replicate to k closest nodes
    
    async def find_agent(self, agent_id: str) -> Optional[AgentRecord]:
        """Find agent by ID."""
        data = await self.dht.find_value(agent_id)
        if data:
            return AgentRecord.from_dict(data)
        return None
    
    async def search_by_capability(
        self,
        capability: str,
        min_reputation: float = 0.0
    ) -> List[AgentRecord]:
        """Search agents by capability."""
        agent_ids = self.dht.find_by_capability(capability)
        results = []
        
        for aid in agent_ids:
            record = await self.find_agent(aid)
            if record and record.reputation >= min_reputation:
                results.append(record)
        
        return sorted(results, key=lambda r: r.reputation, reverse=True)
