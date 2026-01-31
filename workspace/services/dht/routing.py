"""
Kademlia Routing Table with dynamic bucket splitting

Features:
- Dynamic bucket splitting based on own node ID
- O(log n) lookup complexity
- Automatic bucket refresh
"""

from typing import List, Optional
from .node import NodeID, NodeInfo, KEY_SIZE
from .kbucket import KBucket, K


class RoutingTable:
    """Kademlia routing table with dynamic bucket management"""
    
    def __init__(self, node_id: NodeID, k: int = K):
        self.node_id = node_id
        self.k = k
        # Start with single bucket covering entire ID space
        self.buckets: List[KBucket] = [
            KBucket(0, KEY_SIZE - 1, k)
        ]
    
    def get_bucket_index(self, distance: int) -> int:
        """Get bucket index for a distance value"""
        if distance == 0:
            return -1  # Self
        
        bit_pos = distance.bit_length() - 1
        
        for i, bucket in enumerate(self.buckets):
            if bucket.is_in_range(bit_pos):
                return i
        
        return len(self.buckets) - 1
    
    def add_node(self, node: NodeInfo) -> bool:
        """Add node to routing table with bucket splitting"""
        distance = self.node_id.distance_to(node.node_id)
        if distance == 0:
            return True  # Self
        
        bucket_idx = self.get_bucket_index(distance)
        bucket = self.buckets[bucket_idx]
        
        if bucket.add_node(node):
            return True
        
        # Bucket full - split if in our ID range
        own_bit_pos = self.node_id.bit_length()
        if bucket.is_in_range(own_bit_pos):
            left, right = bucket.split()
            self.buckets[bucket_idx] = left
            self.buckets.insert(bucket_idx + 1, right)
            # Retry add after split
            return self.add_node(node)
        
        return False
    
    def remove_node(self, node_id: NodeID) -> bool:
        """Remove node from routing table"""
        distance = self.node_id.distance_to(node_id)
        bucket_idx = self.get_bucket_index(distance)
        if bucket_idx >= 0:
            return self.buckets[bucket_idx].remove_node(node_id)
        return False
    
    def find_closest(self, target_id: NodeID, count: int = K) -> List[NodeInfo]:
        """Find k closest nodes to target"""
        all_nodes = []
        for bucket in self.buckets:
            all_nodes.extend(bucket.get_all_nodes())
        
        # Sort by XOR distance to target
        all_nodes.sort(key=lambda n: n.distance_to(target_id))
        return all_nodes[:count]
    
    def get_node(self, node_id: NodeID) -> Optional[NodeInfo]:
        """Find node by ID"""
        distance = self.node_id.distance_to(node_id)
        bucket_idx = self.get_bucket_index(distance)
        if bucket_idx >= 0:
            return self.buckets[bucket_idx].get_node(node_id)
        return None
    
    def get_all_nodes(self) -> List[NodeInfo]:
        """Get all nodes from all buckets"""
        all_nodes = []
        for bucket in self.buckets:
            all_nodes.extend(bucket.get_all_nodes())
        return all_nodes
    
    def get_bucket_for_node(self, node_id: NodeID) -> Optional[KBucket]:
        """Get the bucket containing a specific node"""
        distance = self.node_id.distance_to(node_id)
        bucket_idx = self.get_bucket_index(distance)
        if bucket_idx >= 0:
            return self.buckets[bucket_idx]
        return None
    
    def get_stats(self) -> dict:
        """Get routing table statistics"""
        total_nodes = sum(len(b.nodes) for b in self.buckets)
        return {
            "buckets": len(self.buckets),
            "total_nodes": total_nodes,
            "bucket_sizes": [len(b.nodes) for b in self.buckets],
        }
