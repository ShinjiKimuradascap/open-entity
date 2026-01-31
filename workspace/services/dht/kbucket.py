"""
KBucket implementation with dynamic splitting support

Based on dht_node.py with improvements:
- Configurable k-size
- Split capability for dynamic routing tables
- LRU eviction
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple
from .node import NodeID, NodeInfo

K = 20  # Default bucket size


@dataclass
class KBucket:
    """K-bucket: distance-based node container with split support"""
    
    min_distance: int
    max_distance: int
    k: int = K
    
    def __init__(self, min_distance: int, max_distance: int, k: int = K):
        self.min_distance = min_distance
        self.max_distance = max_distance
        self.k = k
        self.nodes: List[NodeInfo] = []
        self.last_updated = datetime.utcnow()
    
    def __contains__(self, node_id: NodeID) -> bool:
        return any(n.node_id == node_id for n in self.nodes)
    
    def add_node(self, node: NodeInfo) -> bool:
        """Add node. Returns False if bucket is full"""
        if node in self:
            # Move existing node to front (LRU)
            self.nodes = [n for n in self.nodes if n.node_id != node.node_id]
            self.nodes.insert(0, node)
            self.last_updated = datetime.utcnow()
            return True
        
        if len(self.nodes) < self.k:
            self.nodes.insert(0, node)
            self.last_updated = datetime.utcnow()
            return True
        
        return False  # Full
    
    def remove_node(self, node_id: NodeID) -> bool:
        """Remove node by ID"""
        original_len = len(self.nodes)
        self.nodes = [n for n in self.nodes if n.node_id != node_id]
        return len(self.nodes) < original_len
    
    def get_node(self, node_id: NodeID) -> Optional[NodeInfo]:
        """Get node by ID"""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None
    
    def get_least_recently_seen(self) -> Optional[NodeInfo]:
        """Return oldest node (LRU eviction candidate)"""
        if not self.nodes:
            return None
        return self.nodes[-1]
    
    def split(self) -> Tuple['KBucket', 'KBucket']:
        """Split bucket into two at midpoint"""
        mid = (self.min_distance + self.max_distance) // 2
        left = KBucket(self.min_distance, mid, self.k)
        right = KBucket(mid, self.max_distance, self.k)
        
        for node in self.nodes:
            # Use node's ID bit length for distance
            distance = node.node_id.bit_length()
            if distance <= mid:
                left.add_node(node)
            else:
                right.add_node(node)
        
        return left, right
    
    def get_all_nodes(self) -> List[NodeInfo]:
        """Return all nodes in bucket"""
        return self.nodes.copy()
    
    def is_full(self) -> bool:
        """Check if bucket is at capacity"""
        return len(self.nodes) >= self.k
    
    def is_in_range(self, distance: int) -> bool:
        """Check if distance falls within this bucket's range"""
        return self.min_distance <= distance <= self.max_distance
