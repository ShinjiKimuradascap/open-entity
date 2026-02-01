"""
DHT Router - Main entry point for DHT operations

Consolidates:
- Kademlia routing
- Value storage/retrieval
- Bootstrap and discovery
- Integration with PeerService
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable

from .node import NodeID, NodeInfo
from .routing import RoutingTable
from .kbucket import K

logger = logging.getLogger(__name__)


@dataclass
class DHTValue:
    """Value stored in DHT"""
    key: bytes
    value: bytes
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    publisher_id: Optional[NodeID] = None
    ttl: int = 86400  # 24 hours default
    
    def is_expired(self) -> bool:
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key.hex(),
            "value": self.value.hex(),
            "timestamp": self.timestamp.isoformat(),
            "publisher_id": self.publisher_id.hex if self.publisher_id else None,
            "ttl": self.ttl,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DHTValue':
        return cls(
            key=bytes.fromhex(data["key"]),
            value=bytes.fromhex(data["value"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            publisher_id=NodeID.from_hex(data["publisher_id"]) if data.get("publisher_id") else None,
            ttl=data.get("ttl", 86400),
        )


class DHTRouter:
    """
    Unified DHT Router for Peer Protocol v1.2
    
    Usage:
        router = DHTRouter(NodeID.from_entity("entity_a"))
        await router.bootstrap(["bootstrap.example.com:8080"])
        await router.store(key, value)
        result = await router.find_value(key)
    """
    
    def __init__(
        self,
        node_id: Optional[NodeID] = None,
        k: int = K,
        alpha: int = 3,
    ):
        self.node_id = node_id or NodeID()
        self.k = k
        self.alpha = alpha  # Parallelism factor
        
        # Routing table
        self.routing_table = RoutingTable(self.node_id, k)
        
        # Local storage
        self.storage: Dict[bytes, DHTValue] = {}
        self.storage_lock = asyncio.Lock()
        
        # Callbacks for network operations
        self.find_node_handler: Optional[Callable[[NodeID], List[NodeInfo]]] = None
        self.find_value_handler: Optional[Callable[[bytes], Optional[DHTValue]]] = None
        self.store_handler: Optional[Callable[[bytes, DHTValue], bool]] = None
        
        # Background tasks
        self._refresh_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"DHTRouter initialized: node_id={self.node_id}")
    
    # === Storage Operations ===
    
    async def store(self, key: bytes, value: bytes, ttl: int = 86400) -> bool:
        """Store value in DHT (local + replicate to closest nodes)"""
        dht_value = DHTValue(
            key=key,
            value=value,
            publisher_id=self.node_id,
            ttl=ttl,
        )
        
        # Store locally
        async with self.storage_lock:
            self.storage[key] = dht_value
        
        # Replicate to k closest nodes
        value_id = NodeID(key)
        closest = self.routing_table.find_closest(value_id, self.k)
        
        success_count = 1  # Local store counts
        for node in closest:
            if self.store_handler:
                try:
                    if await self.store_handler(key, dht_value):
                        success_count += 1
                except Exception as e:
                    logger.warning(f"Failed to replicate to {node}: {e}")
        
        logger.debug(f"Stored {key.hex()[:16]}... to {success_count} nodes")
        return success_count > 0
    
    async def find_value(self, key: bytes) -> Optional[bytes]:
        """Find value in DHT"""
        # Check local storage first
        async with self.storage_lock:
            if key in self.storage:
                value = self.storage[key]
                if not value.is_expired():
                    return value.value
                del self.storage[key]
        
        # Search in network
        value_id = NodeID(key)
        closest = self.routing_table.find_closest(value_id, self.alpha)
        
        for node in closest:
            if self.find_value_handler:
                try:
                    result = await self.find_value_handler(key)
                    if result and not result.is_expired():
                        return result.value
                except Exception as e:
                    logger.warning(f"Failed to query {node}: {e}")
        
        return None
    
    # === Node Operations ===
    
    async def find_node(self, target_id: NodeID) -> List[NodeInfo]:
        """Find k closest nodes to target"""
        return self.routing_table.find_closest(target_id, self.k)
    
    async def add_node(self, node: NodeInfo) -> bool:
        """Add node to routing table"""
        return self.routing_table.add_node(node)
    
    async def remove_node(self, node_id: NodeID) -> bool:
        """Remove node from routing table"""
        return self.routing_table.remove_node(node_id)
    
    # === Bootstrap ===
    
    async def bootstrap(self, bootstrap_nodes: List[str]) -> bool:
        """Connect to bootstrap nodes and populate routing table"""
        for addr in bootstrap_nodes:
            try:
                # Parse host:port
                host, port = addr.rsplit(":", 1)
                port = int(port)
                
                # TODO: Query bootstrap node for its ID and neighbors
                logger.info(f"Bootstrapped via {addr}")
            except Exception as e:
                logger.warning(f"Bootstrap failed for {addr}: {e}")
        
        return len(self.routing_table.get_all_nodes()) > 0
    
    # === Lifecycle ===
    
    async def start(self):
        """Start background tasks"""
        self._running = True
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("DHTRouter started")
    
    async def stop(self):
        """Stop background tasks"""
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        logger.info("DHTRouter stopped")
    
    async def _refresh_loop(self):
        """Periodically refresh routing table"""
        while self._running:
            try:
                await asyncio.sleep(3600)  # 1 hour
                await self._refresh_buckets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refresh error: {e}")
    
    async def _refresh_buckets(self):
        """Refresh least recently seen nodes in each bucket"""
        for bucket in self.routing_table.buckets:
            if not bucket.nodes:
                continue
            oldest = bucket.get_least_recently_seen()
            if oldest:
                # TODO: Ping node and update or remove
                pass
    
    # === Stats ===
    
    def get_stats(self) -> dict:
        """Get router statistics"""
        return {
            "node_id": str(self.node_id),
            "routing_table": self.routing_table.get_stats(),
            "stored_keys": len(self.storage),
        }
