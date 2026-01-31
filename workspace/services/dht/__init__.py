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

# Core types
from .node import NodeID, NodeInfo
from .kbucket import KBucket
from .routing import RoutingTable

# Main router
from .router import DHTRouter, DHTValue

# Discovery
from .discovery import DHTDiscovery

# Backward compatibility - deprecated imports from services/dht.py
# These will be removed in v1.3, migrate to DHTRouter
try:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from dht import KademliaDHT, DHTPeerDiscovery, compute_dht_key
    _DEPRECATED_AVAILABLE = True
except ImportError:
    _DEPRECATED_AVAILABLE = False
    KademliaDHT = None
    DHTPeerDiscovery = None
    compute_dht_key = None

__all__ = [
    "NodeID",
    "NodeInfo", 
    "KBucket",
    "RoutingTable",
    "DHTRouter",
    "DHTValue",
    "DHTDiscovery",
    # Deprecated - for backward compatibility
    "KademliaDHT",
    "DHTPeerDiscovery", 
    "compute_dht_key",
]
