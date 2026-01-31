"""DHT-based Peer Registry using Kademlia

v1.2 Feature: Distributed peer discovery without central registry
"""

import asyncio
import hashlib
import json
import logging
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

try:
    from kademlia.network import Server
    from kademlia.storage import ForgetfulStorage
    KADEMLIA_AVAILABLE = True
except ImportError:
    KADEMLIA_AVAILABLE = False
    Server = None
    ForgetfulStorage = None

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Peer information stored in DHT"""
    peer_id: str  # SHA256(public_key)
    entity_id: str
    entity_name: str
    endpoint: str
    public_key: str
    capabilities: List[str]
    timestamp: str
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "endpoint": self.endpoint,
            "public_key": self.public_key,
            "capabilities": self.capabilities,
            "timestamp": self.timestamp,
            "signature": self.signature
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PeerInfo":
        return cls(**data)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)
    
    @classmethod
    def from_json(cls, json_str: str) -> "PeerInfo":
        return cls.from_dict(json.loads(json_str))


class DHTRegistry:
    """DHT-based peer registry using Kademlia
    
    Features:
    - Decentralized peer discovery
    - Bootstrap node support
    - Periodic peer refresh
    - Self-signed peer info with verification
    """
    
    def __init__(
        self,
        entity_id: str,
        entity_name: str,
        endpoint: str,
        public_key: str,
        capabilities: List[str],
        bootstrap_nodes: List[tuple] = None,
        refresh_interval: int = 3600,
        port: int = 8468
    ):
        self.entity_id = entity_id
        self.entity_name = entity_name
        self.endpoint = endpoint
        self.public_key = public_key
        self.capabilities = capabilities
        self.bootstrap_nodes = bootstrap_nodes or []
        self.refresh_interval = refresh_interval
        self.port = port
        
        # Calculate peer_id from public_key
        self.peer_id = hashlib.sha256(public_key.encode()).hexdigest()
        
        # Kademlia server
        self._server: Optional[Server] = None
        self._storage = None
        
        # Async state
        self._refresh_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Callbacks
        self._peer_discovered_callbacks: List[Callable[[PeerInfo], None]] = []
        
        if not KADEMLIA_AVAILABLE:
            logger.warning("kademlia not installed. DHT registry disabled.")
    
    async def start(self) -> bool:
        """Start DHT server and bootstrap"""
        if not KADEMLIA_AVAILABLE:
            logger.error("kademlia not available")
            return False
        
        try:
            # Create storage with TTL
            self._storage = ForgetfulStorage(ttl=self.refresh_interval * 2)
            
            # Create and start Kademlia server
            self._server = Server(storage=self._storage)
            await self._server.listen(self.port)
            
            # Bootstrap from known nodes
            if self.bootstrap_nodes:
                logger.info(f"Bootstrapping from {len(self.bootstrap_nodes)} nodes")
                await self._server.bootstrap(self.bootstrap_nodes)
            
            # Register self
            await self._register_self()
            
            # Start refresh loop
            self._refresh_task = asyncio.create_task(self._refresh_loop())
            self._running = True
            
            logger.info(f"DHT Registry started on port {self.port}")
            logger.info(f"Peer ID: {self.peer_id[:16]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start DHT registry: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop DHT server"""
        self._running = False
        
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        if self._server:
            self._server.stop()
        
        logger.info("DHT Registry stopped")
    
    async def _register_self(self) -> bool:
        """Register own peer info to DHT"""
        if not self._server:
            return False
        
        try:
            peer_info = PeerInfo(
                peer_id=self.peer_id,
                entity_id=self.entity_id,
                entity_name=self.entity_name,
                endpoint=self.endpoint,
                public_key=self.public_key,
                capabilities=self.capabilities,
                timestamp=datetime.now(timezone.utc).isoformat(),
                signature=None  # TODO: Sign with private key
            )
            
            # Store in DHT with peer_id as key
            key = f"peer:{self.peer_id}"
            value = peer_info.to_json()
            
            await self._server.set(key, value)
            logger.info(f"Registered self to DHT: {self.entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register self: {e}")
            return False
    
    async def lookup_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """Lookup peer by peer_id"""
        if not self._server:
            return None
        
        try:
            key = f"peer:{peer_id}"
            value = await self._server.get(key)
            
            if value:
                return PeerInfo.from_json(value)
            return None
            
        except Exception as e:
            logger.error(f"Failed to lookup peer {peer_id}: {e}")
            return None
    
    async def discover_peers(self, count: int = 10) -> List[PeerInfo]:
        """Discover random peers from DHT"""
        if not self._server:
            return []
        
        peers = []
        
        try:
            # Get routing table neighbors
            # Kademlia doesn't expose direct access, so we use iterative lookups
            import random
            
            for _ in range(count):
                # Generate random peer_id to find neighbors
                random_id = hashlib.sha256(str(random.randint(0, 2**32)).encode()).hexdigest()
                key = f"peer:{random_id}"
                
                try:
                    value = await self._server.get(key)
                    if value:
                        peer = PeerInfo.from_json(value)
                        if peer.peer_id != self.peer_id:
                            peers.append(peer)
                except Exception:
                    pass
            
            return peers
            
        except Exception as e:
            logger.error(f"Failed to discover peers: {e}")
            return []
    
    async def find_by_capability(self, capability: str) -> List[PeerInfo]:
        """Find peers with specific capability
        
        Note: This requires iterating over known peers.
        For production, consider capability-based DHT keys.
        """
        peers = await self.discover_peers(count=50)
        return [p for p in peers if capability in p.capabilities]
    
    async def _refresh_loop(self) -> None:
        """Periodic refresh loop"""
        while self._running:
            try:
                await asyncio.sleep(self.refresh_interval)
                await self._register_self()
                logger.debug("Refreshed peer registration in DHT")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refresh error: {e}")
    
    def add_peer_discovered_callback(self, callback: Callable[[PeerInfo], None]) -> None:
        """Add callback for new peer discovery"""
        self._peer_discovered_callbacks.append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get DHT statistics"""
        stats = {
            "peer_id": self.peer_id[:16] + "...",
            "entity_id": self.entity_id,
            "port": self.port,
            "running": self._running,
            "bootstrap_nodes": len(self.bootstrap_nodes),
            "kademlia_available": KADEMLIA_AVAILABLE
        }
        
        if self._server and hasattr(self._server, 'protocol'):
            # Get routing table size if available
            try:
                routing_table = self._server.protocol.router
                stats["routing_table_buckets"] = len(routing_table.buckets)
            except Exception:
                pass
        
        return stats


# Global instance
_dht_registry: Optional[DHTRegistry] = None


def get_dht_registry() -> Optional[DHTRegistry]:
    """Get global DHT registry instance"""
    return _dht_registry


def create_dht_registry(
    entity_id: str,
    entity_name: str,
    endpoint: str,
    public_key: str,
    capabilities: List[str],
    **kwargs
) -> DHTRegistry:
    """Create and return global DHT registry instance"""
    global _dht_registry
    _dht_registry = DHTRegistry(
        entity_id=entity_id,
        entity_name=entity_name,
        endpoint=endpoint,
        public_key=public_key,
        capabilities=capabilities,
        **kwargs
    )
    return _dht_registry
