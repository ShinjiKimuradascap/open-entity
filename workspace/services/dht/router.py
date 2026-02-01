"""
DHT Router - High-level interface for DHT operations

Wraps DHTNode from dht_node.py to provide a clean async interface
for peer discovery and distributed storage.

Usage:
    from services.dht.router import DHTRouter
    from services.dht_node import DHTNode, NodeID
    
    node = DHTNode(host="0.0.0.0", port=8000)
    await node.start()
    
    router = DHTRouter(node)
    await router.bootstrap(["192.168.1.1:8001", "192.168.1.2:8002"])
    
    # Store a value
    await router.store(b"my_key", b"my_value")
    
    # Find nodes
    target = NodeID()
    closest = await router.find_node(target)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from .node import NodeID, NodeInfo


@dataclass
class DHTValue:
    """Value stored in DHT"""
    key: bytes
    value: bytes
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    publisher_id: Optional[NodeID] = None
    ttl: int = 86400  # 24 hours default
    
    def is_expired(self) -> bool:
        """Check if the value has expired"""
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "key": self.key.hex(),
            "value": self.value.hex(),
            "timestamp": self.timestamp.isoformat(),
            "publisher_id": self.publisher_id.hex if self.publisher_id else None,
            "ttl": self.ttl,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DHTValue':
        """Create from dictionary"""
        return cls(
            key=bytes.fromhex(data["key"]),
            value=bytes.fromhex(data["value"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            publisher_id=NodeID.from_hex(data["publisher_id"]) if data.get("publisher_id") else None,
            ttl=data.get("ttl", 86400),
        )

# Import from dht_node.py - the canonical DHT implementation
from ..dht_node import DHTNode as _DHTNode
from ..dht_node import NodeID as _NodeID, NodeInfo as _NodeInfo

logger = logging.getLogger(__name__)


class DHTRouter:
    """
    High-level DHT router interface
    
    Wraps DHTNode to provide standardized async methods for:
    - Node discovery (find_node)
    - Value storage/retrieval (store, find_value)
    - Network maintenance (ping, bootstrap, add_node)
    """
    
    def __init__(self, node: _DHTNode):
        """
        Initialize router with a DHTNode instance
        
        Args:
            node: Initialized and started DHTNode instance
        """
        self._node = node
        logger.debug(f"DHTRouter initialized with node {node.node_id}")
    
    @property
    def routing_table(self):
        """Access the underlying routing table"""
        return self._node.routing_table
    
    @property
    def node_id(self) -> NodeID:
        """Get this router's node ID"""
        # Convert internal NodeID to services.dht.node.NodeID
        return NodeID(self._node.node_id.bytes)
    
    async def bootstrap(self, bootstrap_nodes: List[str]) -> bool:
        """
        Bootstrap the DHT by connecting to known nodes
        
        Args:
            bootstrap_nodes: List of "host:port" strings
            
        Returns:
            True if at least one bootstrap node was reached
        """
        if not bootstrap_nodes:
            return False
        
        # Convert string addresses to node info format
        nodes = []
        for addr in bootstrap_nodes:
            try:
                host, port_str = addr.rsplit(":", 1)
                nodes.append({"host": host, "port": int(port_str)})
            except ValueError:
                logger.warning(f"Invalid bootstrap address: {addr}")
                continue
        
        # Store for the underlying node to use
        self._node.bootstrap_nodes = nodes
        
        # Perform bootstrap
        try:
            await self._node._bootstrap()
            logger.info(f"Bootstrap completed with {len(nodes)} nodes")
            return True
        except Exception as e:
            logger.error(f"Bootstrap failed: {e}")
            return False
    
    async def find_node(self, target_id: NodeID) -> List[NodeInfo]:
        """
        Find nodes closest to the target ID
        
        Args:
            target_id: Target node ID to search for
            
        Returns:
            List of NodeInfo objects closest to target
        """
        # Convert to internal NodeID type
        internal_target = _NodeID(target_id.bytes)
        
        # Query the DHT
        results = await self._node.find_node(internal_target)
        
        # Convert results to external NodeInfo type
        return [_convert_node_info(n) for n in results]
    
    async def add_node(self, node: NodeInfo) -> bool:
        """
        Add a node to the routing table
        
        Args:
            node: NodeInfo to add
            
        Returns:
            True if node was added successfully
        """
        internal_node = _convert_to_internal_node_info(node)
        return self._node.routing_table.add_node(internal_node)
    
    async def store(self, key: bytes, value: bytes) -> bool:
        """
        Store a value in the DHT
        
        Args:
            key: Key to store under
            value: Value to store
            
        Returns:
            True if value was stored successfully
        """
        return await self._node.store(key, value)
    
    async def find_value(self, key: bytes) -> Optional[bytes]:
        """
        Find a value in the DHT
        
        Args:
            key: Key to search for
            
        Returns:
            Value bytes if found, None otherwise
        """
        return await self._node.find_value(key)
    
    async def ping(self, node: NodeInfo) -> bool:
        """
        Ping a node to check connectivity
        
        Args:
            node: Node to ping
            
        Returns:
            True if node responded
        """
        internal_node = _convert_to_internal_node_info(node)
        return await self._node.ping(internal_node)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics"""
        return self._node.get_stats()


def _convert_node_info(internal: _NodeInfo) -> NodeInfo:
    """Convert internal NodeInfo to external NodeInfo"""
    return NodeInfo(
        node_id=NodeID(internal.node_id.bytes),
        host=internal.host,
        port=internal.port,
        last_seen=internal.last_seen,
        failed_pings=internal.failed_pings
    )


def _convert_to_internal_node_info(external: NodeInfo) -> _NodeInfo:
    """Convert external NodeInfo to internal NodeInfo"""
    return _NodeInfo(
        node_id=_NodeID(external.node_id.bytes),
        host=external.host,
        port=external.port,
        last_seen=external.last_seen,
        failed_pings=external.failed_pings
    )
