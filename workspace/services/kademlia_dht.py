#!/usr/bin/env python3
"""
Kademlia DHT-based Peer Discovery and Registry

Implements decentralized peer discovery using Kademlia DHT protocol.
- Peer registration with signed PeerInfo
- Distributed peer lookup
- Bootstrap node support
- Periodic refresh and cleanup

Requirements: kademlia>=2.0.0
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

# Kademlia imports
try:
    from kademlia.network import Server
    from kademlia.node import Node
    from kademlia.routing import RoutingTable
    KADEMLIA_AVAILABLE = True
except ImportError:
    KADEMLIA_AVAILABLE = False
    Server = None
    Node = None
    RoutingTable = None

# Crypto imports
try:
    from services.crypto import KeyPair, MessageSigner, SignatureVerifier
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        from crypto import KeyPair, MessageSigner, SignatureVerifier
        CRYPTO_AVAILABLE = True
    except ImportError:
        CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Peer information stored in DHT"""
    peer_id: str
    public_key: str  # Base64 encoded Ed25519 public key
    endpoint: str  # host:port
    capabilities: List[str]
    timestamp: float  # Unix timestamp
    signature: Optional[str] = None  # Base64 signature of the above fields
    
    def to_bytes(self) -> bytes:
        """Convert to bytes for signing/verification (excluding signature)"""
        data = {
            "peer_id": self.peer_id,
            "public_key": self.public_key,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "timestamp": self.timestamp
        }
        return json.dumps(data, sort_keys=True).encode()
    
    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, data: str) -> "PeerInfo":
        """Deserialize from JSON string"""
        obj = json.loads(data)
        return cls(**obj)
    
    def is_expired(self, max_age_seconds: int = 3600) -> bool:
        """Check if peer info is expired"""
        return (time.time() - self.timestamp) > max_age_seconds


class DHTRegistry:
    """
    Kademlia DHT-based peer registry
    
    Provides decentralized peer discovery with:
    - Peer registration (signed PeerInfo)
    - Peer lookup by ID
    - Random peer discovery
    - Bootstrap node support
    """
    
    def __init__(
        self,
        entity_id: str,
        keypair: Optional[KeyPair] = None,
        listen_port: int = 0,
        bootstrap_nodes: Optional[List[tuple]] = None,
        refresh_interval: int = 600,  # 10 minutes
        max_peer_age: int = 3600  # 1 hour
    ):
        """
        Initialize DHT Registry
        
        Args:
            entity_id: Local entity identifier
            keypair: Ed25519 keypair for signing peer info
            listen_port: UDP port for DHT (0 for auto)
            bootstrap_nodes: List of (host, port) tuples
            refresh_interval: Seconds between refresh cycles
            max_peer_age: Maximum age of peer info before considered stale
        """
        if not KADEMLIA_AVAILABLE:
            raise RuntimeError("kademlia library not installed. Run: pip install kademlia")
        
        self.entity_id = entity_id
        self.keypair = keypair
        self.listen_port = listen_port
        self.bootstrap_nodes = bootstrap_nodes or []
        self.refresh_interval = refresh_interval
        self.max_peer_age = max_peer_age
        
        # Kademlia server
        self._server: Optional[Server] = None
        self._node_id = self._generate_node_id(entity_id)
        
        # Local cache
        self._peers: Dict[str, PeerInfo] = {}  # peer_id -> PeerInfo
        self._callbacks: List[Callable[[str, PeerInfo], None]] = []
        
        # Refresh task
        self._refresh_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"DHTRegistry initialized for {entity_id} (node_id: {self._node_id.hex()[:16]}...)")
    
    def _generate_node_id(self, entity_id: str) -> bytes:
        """Generate 20-byte node ID from entity_id (Kademlia standard)"""
        return hashlib.sha1(entity_id.encode()).digest()[:20]
    
    async def start(self) -> bool:
        """Start DHT server and bootstrap"""
        try:
            self._server = Server()
            await self._server.listen(self.listen_port)
            
            actual_port = self._server.transport.get_host().port
            logger.info(f"DHT server listening on port {actual_port}")
            
            # Bootstrap if nodes provided
            if self.bootstrap_nodes:
                await self._server.bootstrap(self.bootstrap_nodes)
                logger.info(f"Bootstrapped with {len(self.bootstrap_nodes)} nodes")
            
            self._running = True
            
            # Start refresh loop
            self._refresh_task = asyncio.create_task(self._refresh_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start DHT server: {e}")
            return False
    
    async def stop(self):
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
            logger.info("DHT server stopped")
    
    async def _refresh_loop(self):
        """Periodic refresh loop"""
        while self._running:
            try:
                await asyncio.sleep(self.refresh_interval)
                await self._refresh_peers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refresh loop error: {e}")
    
    async def _refresh_peers(self):
        """Refresh peer registrations"""
        # Republish our own info
        await self.register_self()
        
        # Clean up expired peers from local cache
        expired = [
            peer_id for peer_id, info in self._peers.items()
            if info.is_expired(self.max_peer_age)
        ]
        for peer_id in expired:
            del self._peers[peer_id]
            logger.debug(f"Removed expired peer: {peer_id}")
    
    def _create_peer_info(self) -> PeerInfo:
        """Create signed PeerInfo for self"""
        if not self.keypair:
            raise RuntimeError("Keypair required for peer registration")
        
        # Get endpoint info
        host = "127.0.0.1"  # TODO: Get actual public IP
        port = 8000  # TODO: Get actual port
        
        info = PeerInfo(
            peer_id=self.entity_id,
            public_key=self.keypair.public_key_hex,
            endpoint=f"{host}:{port}",
            capabilities=["peer_service", "dht", "v1.1"],
            timestamp=time.time()
        )
        
        # Sign the peer info
        if CRYPTO_AVAILABLE:
            signer = MessageSigner(self.keypair)
            signature = signer.sign(info.to_bytes())
            info.signature = signature
        
        return info
    
    async def register_self(self) -> bool:
        """Register own peer info to DHT"""
        try:
            info = self._create_peer_info()
            key = f"peer:{self.entity_id}"
            value = info.to_json()
            
            await self._server.set(key, value)
            logger.debug(f"Registered self to DHT: {self.entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register self: {e}")
            return False
    
    async def lookup_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """Lookup peer by ID from DHT"""
        try:
            # Check local cache first
            if peer_id in self._peers:
                info = self._peers[peer_id]
                if not info.is_expired(self.max_peer_age):
                    return info
            
            # Query DHT
            key = f"peer:{peer_id}"
            result = await self._server.get(key)
            
            if result:
                info = PeerInfo.from_json(result)
                
                # Verify signature if crypto available
                if CRYPTO_AVAILABLE and info.signature:
                    if not self._verify_peer_info(info):
                        logger.warning(f"Invalid signature for peer: {peer_id}")
                        return None
                
                # Update cache
                self._peers[peer_id] = info
                return info
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to lookup peer {peer_id}: {e}")
            return None
    
    def _verify_peer_info(self, info: PeerInfo) -> bool:
        """Verify peer info signature"""
        if not CRYPTO_AVAILABLE or not info.signature:
            return False
        
        try:
            from services.crypto import VerifyKey
            vk = VerifyKey.from_hex(info.public_key)
            verifier = SignatureVerifier(vk)
            return verifier.verify(info.to_bytes(), info.signature)
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False
    
    async def discover_random_peers(self, count: int = 10) -> List[PeerInfo]:
        """Discover random peers by querying random IDs"""
        discovered = []
        
        for _ in range(count):
            # Generate random ID
            random_id = hashlib.sha1(str(time.time()).encode()).hexdigest()[:20]
            
            try:
                # Query DHT for peers near this ID
                # Note: kademlia library doesn't expose direct node lookup
                # We use get on random keys to populate routing table
                result = await self._server.get(f"random:{random_id}")
                
                # Get peers from routing table
                if hasattr(self._server, 'protocol') and self._server.protocol:
                    router = self._server.protocol.router
                    if router:
                        # Get all nodes from routing table
                        nodes = []
                        for bucket in router.buckets:
                            nodes.extend(bucket.get_nodes())
                        
                        # Lookup each node's peer info
                        for node in nodes[:count]:
                            peer_id = node.id.hex()
                            info = await self.lookup_peer(peer_id)
                            if info and info not in discovered:
                                discovered.append(info)
                                
            except Exception as e:
                logger.debug(f"Discovery error: {e}")
                continue
        
        return discovered[:count]
    
    def get_all_peers(self) -> Dict[str, PeerInfo]:
        """Get all known peers from local cache"""
        # Remove expired entries
        expired = [
            pid for pid, info in self._peers.items()
            if info.is_expired(self.max_peer_age)
        ]
        for pid in expired:
            del self._peers[pid]
        
        return self._peers.copy()
    
    def on_peer_discovered(self, callback: Callable[[str, PeerInfo], None]):
        """Register callback for peer discovery events"""
        self._callbacks.append(callback)
    
    def _notify_callbacks(self, peer_id: str, info: PeerInfo):
        """Notify all registered callbacks"""
        for callback in self._callbacks:
            try:
                callback(peer_id, info)
            except Exception as e:
                logger.error(f"Peer discovery callback error: {e}")
    
    @property
    def is_running(self) -> bool:
        """Check if DHT is running"""
        return self._running and self._server is not None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get DHT statistics"""
        if not self._server or not self._server.protocol:
            return {"status": "not_running"}
        
        router = self._server.protocol.router
        buckets = len(router.buckets) if router else 0
        total_nodes = sum(len(b.get_nodes()) for b in (router.buckets if router else []))
        
        return {
            "status": "running" if self._running else "stopped",
            "node_id": self._node_id.hex(),
            "buckets": buckets,
            "known_nodes": total_nodes,
            "cached_peers": len(self._peers),
            "bootstrap_nodes": len(self.bootstrap_nodes)
        }


# Convenience functions for simple use cases

async def create_dht_registry(
    entity_id: str,
    keypair: Optional[KeyPair] = None,
    port: int = 0,
    bootstrap_nodes: Optional[List[tuple]] = None
) -> DHTRegistry:
    """
    Create and start DHT registry
    
    Args:
        entity_id: Entity identifier
        keypair: Ed25519 keypair for signing
        port: UDP port (0 for auto)
        bootstrap_nodes: List of (host, port) tuples
    
    Returns:
        Running DHTRegistry instance
    """
    registry = DHTRegistry(
        entity_id=entity_id,
        keypair=keypair,
        listen_port=port,
        bootstrap_nodes=bootstrap_nodes
    )
    
    success = await registry.start()
    if not success:
        raise RuntimeError("Failed to start DHT registry")
    
    return registry
