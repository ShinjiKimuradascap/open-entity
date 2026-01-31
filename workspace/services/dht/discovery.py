"""
DHT-based peer discovery for Peer Protocol v1.2

Integrates DHTRouter with peer discovery mechanisms:
- Bootstrap node discovery
- Random peer sampling
- Active/passive discovery
"""

import asyncio
import logging
from typing import List, Optional, Callable
from .router import DHTRouter
from .node import NodeID, NodeInfo

logger = logging.getLogger(__name__)


class DHTDiscovery:
    """
    DHT-based peer discovery service
    
    Usage:
        discovery = DHTDiscovery(router)
        await discovery.start()
        peers = discovery.get_random_peers(10)
    """
    
    def __init__(
        self,
        router: DHTRouter,
        bootstrap_nodes: Optional[List[str]] = None,
    ):
        self.router = router
        self.bootstrap_nodes = bootstrap_nodes or []
        self.discovery_callbacks: List[Callable[[NodeInfo], None]] = []
        
        # Background tasks
        self._discovery_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Start discovery service"""
        self._running = True
        
        # Bootstrap if nodes provided
        if self.bootstrap_nodes:
            await self.router.bootstrap(self.bootstrap_nodes)
        
        # Start periodic discovery
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        logger.info("DHTDiscovery started")
    
    async def stop(self):
        """Stop discovery service"""
        self._running = False
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass
        logger.info("DHTDiscovery stopped")
    
    async def _discovery_loop(self):
        """Periodic discovery of new peers"""
        while self._running:
            try:
                # Random walk discovery
                await self._random_walk()
                
                # Wait before next round
                await asyncio.sleep(300)  # 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Discovery error: {e}")
                await asyncio.sleep(60)
    
    async def _random_walk(self):
        """Perform random walk to discover new peers"""
        # Generate random target
        random_id = NodeID()
        
        # Find closest nodes
        closest = await self.router.find_node(random_id)
        
        for node in closest:
            # Add to routing table
            await self.router.add_node(node)
            
            # Notify callbacks
            for callback in self.discovery_callbacks:
                try:
                    callback(node)
                except Exception as e:
                    logger.warning(f"Discovery callback error: {e}")
    
    def on_peer_discovered(self, callback: Callable[[NodeInfo], None]):
        """Register callback for new peer discovery"""
        self.discovery_callbacks.append(callback)
    
    def get_random_peers(self, count: int = 10) -> List[NodeInfo]:
        """Get random sample of known peers"""
        all_nodes = self.router.routing_table.get_all_nodes()
        
        # Shuffle and return subset
        import random
        random.shuffle(all_nodes)
        return all_nodes[:count]
    
    def get_closest_peers(self, target_id: bytes, count: int = 10) -> List[NodeInfo]:
        """Get peers closest to target ID"""
        target = NodeID(target_id)
        return self.router.routing_table.find_closest(target, count)
    
    async def announce(self, node_info: NodeInfo) -> bool:
        """Announce ourselves to the network"""
        # Store our info in DHT (keyed by node ID)
        key = node_info.id_bytes
        value = node_info.to_dict()
        
        import json
        return await self.router.store(
            key,
            json.dumps(value).encode()
        )
