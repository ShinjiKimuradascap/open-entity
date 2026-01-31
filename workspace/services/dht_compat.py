#!/usr/bin/env python3
"""
DHT Compatibility Layer
Unifies dht.py, dht_registry.py, dht_node.py into single interface
Uses dht_node.py as primary implementation
"""

import logging
from typing import Dict, List, Optional

try:
    from services.dht_node import DHTNode, NodeInfo, DHTError
    PRIMARY_DHT_AVAILABLE = True
except ImportError:
    PRIMARY_DHT_AVAILABLE = False

try:
    from services.dht import DHT
    LEGACY_DHT_AVAILABLE = True
except ImportError:
    LEGACY_DHT_AVAILABLE = False

try:
    from services.dht_registry import DHTRegistry
    REGISTRY_DHT_AVAILABLE = True
except ImportError:
    REGISTRY_DHT_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UnifiedDHT:
    """
    Unified DHT interface
    Provides compatibility layer for all DHT implementations
    """
    
    def __init__(
        self,
        node_id: str,
        listen_port: int = 8468,
        bootstrap_nodes: Optional[List[str]] = None
    ):
        self.node_id = node_id
        self.listen_port = listen_port
        self.bootstrap_nodes = bootstrap_nodes or []
        
        self._dht = None
        self._init_dht()
    
    def _init_dht(self):
        """Initialize primary DHT implementation"""
        if PRIMARY_DHT_AVAILABLE:
            logger.info(f"Using dht_node.py as primary DHT")
            self._dht = DHTNode(
                node_id=self.node_id,
                listen_port=self.listen_port
            )
        elif LEGACY_DHT_AVAILABLE:
            logger.warning("Using legacy dht.py fallback")
            self._dht = DHT(
                node_id=self.node_id,
                listen_port=self.listen_port
            )
        elif REGISTRY_DHT_AVAILABLE:
            logger.warning("Using dht_registry.py fallback")
            self._dht = DHTRegistry(
                node_id=self.node_id
            )
        else:
            raise RuntimeError("No DHT implementation available")
    
    async def start(self):
        """Start DHT node"""
        if hasattr(self._dht, 'start'):
            await self._dht.start()
        logger.info(f"DHT node {self.node_id} started on port {self.listen_port}")
    
    async def stop(self):
        """Stop DHT node"""
        if hasattr(self._dht, 'stop'):
            await self._dht.stop()
        logger.info(f"DHT node {self.node_id} stopped")
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from DHT"""
        if hasattr(self._dht, 'get'):
            return await self._dht.get(key)
        return None
    
    async def set(self, key: str, value: str) -> bool:
        """Set value in DHT"""
        if hasattr(self._dht, 'set'):
            return await self._dht.set(key, value)
        return False
    
    async def find_node(self, target_id: str) -> List[dict]:
        """Find nodes closest to target"""
        if hasattr(self._dht, 'find_node'):
            return await self._dht.find_node(target_id)
        return []
    
    def get_routing_table(self) -> List[dict]:
        """Get routing table info"""
        if hasattr(self._dht, 'get_routing_table'):
            return self._dht.get_routing_table()
        return []
    
    def get_stats(self) -> dict:
        """Get DHT statistics"""
        if hasattr(self._dht, 'get_stats'):
            return self._dht.get_stats()
        return {}


def migrate_to_unified_dht(
    old_dht_instance,
    node_id: str,
    listen_port: int = 8468
) -> UnifiedDHT:
    """
    Migrate from old DHT instance to unified DHT
    
    Usage:
        old_dht = DHTRegistry(...)
        new_dht = migrate_to_unified_dht(old_dht, "node-001")
    """
    logger.info(f"Migrating {type(old_dht_instance).__name__} to UnifiedDHT")
    
    # Extract bootstrap nodes from old instance
    bootstrap_nodes = []
    if hasattr(old_dht_instance, 'bootstrap_nodes'):
        bootstrap_nodes = old_dht_instance.bootstrap_nodes
    
    return UnifiedDHT(
        node_id=node_id,
        listen_port=listen_port,
        bootstrap_nodes=bootstrap_nodes
    )


# Deprecation warnings for old modules
import warnings

def _warn_deprecated(old_module: str):
    """Emit deprecation warning"""
    warnings.warn(
        f"{old_module} is deprecated. Use dht_compat.UnifiedDHT instead.",
        DeprecationWarning,
        stacklevel=3
    )


# Export unified interface
__all__ = [
    'UnifiedDHT',
    'migrate_to_unified_dht',
    'PRIMARY_DHT_AVAILABLE',
    'LEGACY_DHT_AVAILABLE',
    'REGISTRY_DHT_AVAILABLE'
]
