"""
DHT Foundation Package - Peer Protocol v1.2

Unified Kademlia DHT implementation consolidating:
- services/dht.py (KademliaDHT) - DEPRECATED, use DHTRouter
- services/dht_node.py (DHTNode, DHTClient)
- services/distributed_registry.py (CRDT integration)

Usage:
    from services.dht import DHTRouter, NodeID, NodeInfo
    
    router = DHTRouter(node_id=NodeID.from_entity("entity_a"))
    await router.bootstrap(["bootstrap.example.com:8080"])
"""

__version__ = "1.2.0"

import hashlib

# Core types
from .node import NodeID, NodeInfo
from .kbucket import KBucket
from .routing import RoutingTable

# Main router
from .router import DHTRouter, DHTValue

# Discovery
from .discovery import DHTDiscovery

def compute_dht_key(key: str) -> bytes:
    """
    Compute DHT key hash using SHA-1.
    
    Args:
        key: String key to hash
        
    Returns:
        20-byte SHA-1 hash
    """
    return hashlib.sha1(key.encode('utf-8')).digest()


# Backward compatibility aliases
# These will be removed in v1.3, migrate to DHTRouter/DHTDiscovery
KademliaDHT = DHTRouter
DHTPeerDiscovery = DHTDiscovery

__all__ = [
    "NodeID",
    "NodeInfo",
    "KBucket",
    "RoutingTable",
    "DHTRouter",
    "DHTValue",
    "DHTDiscovery",
    "compute_dht_key",
    # Backward compatibility aliases
    "KademliaDHT",
    "DHTPeerDiscovery",
]
