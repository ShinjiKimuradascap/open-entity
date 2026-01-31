"""DHT-based Peer Registry using Kademlia

v1.2 Feature: Distributed peer discovery without central registry
Unified implementation consolidating multiple DHT modules.
"""

import asyncio
import hashlib
import json
import logging
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

# Kademlia imports
try:
    from kademlia.network import Server
    from kademlia.storage import ForgetfulStorage
    KADEMLIA_AVAILABLE = True
except ImportError:
    KADEMLIA_AVAILABLE = False
    Server = None
    ForgetfulStorage = None

# Crypto imports
try:
    from services.crypto import (
        KeyPair,
        MessageSigner,
        SignatureVerifier,
        generate_entity_keypair,
    )
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        from crypto import (
            KeyPair,
            MessageSigner,
            SignatureVerifier,
            generate_entity_keypair,
        )
        CRYPTO_AVAILABLE = True
    except ImportError:
        CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Peer information stored in DHT with signature verification"""
    peer_id: str  # SHA256(public_key)
    entity_id: str
    entity_name: str
    endpoint: str
    public_key: str  # Base64 Ed25519 public key
    capabilities: List[str]
    timestamp: str
    ttl: int = 3600
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding signature for signing)"""
        return {
            "peer_id": self.peer_id,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "endpoint": self.endpoint,
            "public_key": self.public_key,
            "capabilities": self.capabilities,
            "timestamp": self.timestamp,
            "ttl": self.ttl
        }
    
    def get_signing_data(self) -> bytes:
        """Get data for signing/verification"""
        data = self.to_dict()
        return json.dumps(data, sort_keys=True).encode()
    
    def sign(self, private_key: str) -> str:
        """Sign PeerInfo with private key
        
        Args:
            private_key: Base64 encoded Ed25519 private key
            
        Returns:
            Base64 encoded signature
        """
        if not CRYPTO_AVAILABLE:
            logger.warning("Crypto module not available, cannot sign")
            return ""
        
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            
            # Decode private key
            private_key_bytes = private_key.encode() if isinstance(private_key, str) else private_key
            if not private_key_bytes.startswith(b'-----'):
                # Assume base64 encoded raw key
                import base64
                private_key_bytes = base64.b64decode(private_key)
                private_key_obj = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
            else:
                # PEM format
                private_key_obj = serialization.load_pem_private_key(
                    private_key_bytes, password=None
                )
            
            # Sign the data
            signing_data = self.get_signing_data()
            signature = private_key_obj.sign(signing_data)
            
            import base64
            return base64.b64encode(signature).decode('ascii')
            
        except Exception as e:
            logger.error(f"Failed to sign PeerInfo: {e}")
            return ""
    
    def verify(self) -> bool:
        """Verify PeerInfo signature
        
        Returns:
            True if signature is valid or no crypto available
            False if signature verification fails
        """
        if not CRYPTO_AVAILABLE:
            logger.warning("Crypto module not available, skipping verification")
            return True
        
        if not self.signature:
            logger.warning(f"No signature for peer {self.entity_id}")
            return False
        
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.exceptions import InvalidSignature
            import base64
            
            # Decode public key
            public_key_bytes = base64.b64decode(self.public_key)
            public_key_obj = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            # Decode signature
            signature_bytes = base64.b64decode(self.signature)
            
            # Verify
            signing_data = self.get_signing_data()
            public_key_obj.verify(signature_bytes, signing_data)
            
            return True
            
        except InvalidSignature:
            logger.warning(f"Invalid signature for peer {self.entity_id}")
            return False
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PeerInfo":
        """Create PeerInfo from dictionary"""
        # Filter only valid fields
        valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid_fields)
    
    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(asdict(self), sort_keys=True)
    
    @classmethod
    def from_json(cls, json_str: str) -> "PeerInfo":
        """Deserialize from JSON"""
        return cls.from_dict(json.loads(json_str))
    
    def is_expired(self) -> bool:
        """Check if PeerInfo has expired"""
        try:
            ts = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            return (now - ts).total_seconds() > self.ttl
        except Exception:
            return True


def load_bootstrap_nodes(config_path: str = "config/bootstrap_nodes.json") -> List[Tuple[str, int]]:
    """Load bootstrap nodes from configuration file
    
    Args:
        config_path: Path to bootstrap nodes configuration
        
    Returns:
        List of (host, port) tuples for DHT bootstrap
    """
    nodes = []
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Load bootstrap servers
        for server in config.get('bootstrap_servers', []):
            dht_endpoint = server.get('dht_endpoint')
            if dht_endpoint:
                try:
                    host, port_str = dht_endpoint.rsplit(':', 1)
                    nodes.append((host, int(port_str)))
                except ValueError:
                    logger.warning(f"Invalid DHT endpoint format: {dht_endpoint}")
        
        # Load local bootstrap
        for server in config.get('local_bootstrap', []):
            dht_endpoint = server.get('dht_endpoint')
            if dht_endpoint:
                try:
                    host, port_str = dht_endpoint.rsplit(':', 1)
                    nodes.append((host, int(port_str)))
                except ValueError:
                    logger.warning(f"Invalid DHT endpoint format: {dht_endpoint}")
        
        logger.info(f"Loaded {len(nodes)} bootstrap nodes from {config_path}")
        
    except FileNotFoundError:
        logger.warning(f"Bootstrap config not found: {config_path}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in bootstrap config: {e}")
    except Exception as e:
        logger.error(f"Error loading bootstrap nodes: {e}")
    
    return nodes


class DHTRegistry:
    """DHT-based peer registry using Kademlia
    
    Features:
    - Decentralized peer discovery
    - Bootstrap node support
    - Periodic peer refresh
    - Self-signed peer info with verification
    - PeerService integration
    """
    
    def __init__(
        self,
        entity_id: str,
        entity_name: str,
        endpoint: str,
        public_key: str,
        private_key: Optional[str] = None,
        capabilities: List[str] = None,
        bootstrap_nodes: List[Tuple[str, int]] = None,
        bootstrap_config_path: str = "config/bootstrap_nodes.json",
        refresh_interval: int = 3600,
        port: int = 8468,
        auto_load_bootstrap: bool = True
    ):
        self.entity_id = entity_id
        self.entity_name = entity_name
        self.endpoint = endpoint
        self.public_key = public_key
        self.private_key = private_key
        self.capabilities = capabilities or []
        self.refresh_interval = refresh_interval
        self.port = port
        
        # Calculate peer_id from public_key
        self.peer_id = hashlib.sha256(public_key.encode()).hexdigest()
        
        # Load bootstrap nodes
        if bootstrap_nodes is not None:
            self.bootstrap_nodes = bootstrap_nodes
        elif auto_load_bootstrap and bootstrap_config_path:
            self.bootstrap_nodes = load_bootstrap_nodes(bootstrap_config_path)
        else:
            self.bootstrap_nodes = []
        
        # Kademlia server
        self._server: Optional[Server] = None
        self._storage = None
        
        # Async state
        self._refresh_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Callbacks for peer discovery
        self._peer_discovered_callbacks: List[Callable[[PeerInfo], None]] = []
        
        # Local peer info cache
        self._local_peer_info: Optional[PeerInfo] = None
        
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
                ttl=self.refresh_interval * 2
            )
            
            # Sign if private key available
            if self.private_key:
                peer_info.signature = peer_info.sign(self.private_key)
            
            # Store in DHT
            key = f"peer:{self.peer_id}"
            value = peer_info.to_json()
            
            await self._server.set(key, value)
            self._local_peer_info = peer_info
            
            logger.info(f"Registered self to DHT: {self.entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register self: {e}")
            return False
    
    async def register_peer(self, peer_info: PeerInfo) -> bool:
        """Register a peer to DHT
        
        Args:
            peer_info: PeerInfo to register
            
        Returns:
            True if successful
        """
        if not self._server:
            return False
        
        # Verify signature
        if peer_info.signature and not peer_info.verify():
            logger.warning(f"Signature verification failed for {peer_info.entity_id}")
            return False
        
        try:
            key = f"peer:{peer_info.peer_id}"
            value = peer_info.to_json()
            
            await self._server.set(key, value)
            
            # Notify callbacks
            for callback in self._peer_discovered_callbacks:
                try:
                    callback(peer_info)
                except Exception as e:
                    logger.error(f"Peer discovered callback error: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to register peer: {e}")
            return False
    
    async def lookup_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """Lookup peer by peer_id"""
        if not self._server:
            return None
        
        try:
            key = f"peer:{peer_id}"
            value = await self._server.get(key)
            
            if value:
                peer_info = PeerInfo.from_json(value)
                # Verify signature if present
                if peer_info.signature and not peer_info.verify():
                    logger.warning(f"Invalid signature for peer {peer_id}")
                    return None
                return peer_info
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
            for _ in range(count * 2):  # Try more to account for failures
                if len(peers) >= count:
                    break
                    
                # Generate random peer_id to find neighbors
                random_id = hashlib.sha256(str(hashlib.sha256(
                    str(asyncio.get_event_loop().time()).encode()
                ).hexdigest()).encode()).hexdigest()
                key = f"peer:{random_id}"
                
                try:
                    value = await self._server.get(key)
                    if value:
                        peer = PeerInfo.from_json(value)
                        # Skip self and verify signature
                        if peer.peer_id != self.peer_id:
                            if peer.signature and not peer.verify():
                                logger.debug(f"Skipping peer with invalid signature: {peer.entity_id}")
                                continue
                            if not peer.is_expired():
                                peers.append(peer)
                except Exception:
                    pass
            
            return peers[:count]
            
        except Exception as e:
            logger.error(f"Failed to discover peers: {e}")
            return []
    
    async def find_by_capability(self, capability: str, count: int = 50) -> List[PeerInfo]:
        """Find peers with specific capability
        
        Note: This requires iterating over discovered peers.
        For production, consider capability-based DHT keys.
        """
        peers = await self.discover_peers(count=count)
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
    
    # PeerService integration methods
    
    def get_local_peer_info(self) -> Optional[PeerInfo]:
        """Get local peer info for PeerService integration"""
        return self._local_peer_info
    
    def add_peer_discovered_callback(self, callback: Callable[[PeerInfo], None]) -> None:
        """Add callback for new peer discovery
        
        Args:
            callback: Function called when new peer is discovered
        """
        self._peer_discovered_callbacks.append(callback)
    
    def remove_peer_discovered_callback(self, callback: Callable[[PeerInfo], None]) -> None:
        """Remove peer discovery callback"""
        if callback in self._peer_discovered_callbacks:
            self._peer_discovered_callbacks.remove(callback)
    
    def get_bootstrap_nodes(self) -> List[Tuple[str, int]]:
        """Get current bootstrap nodes"""
        return self.bootstrap_nodes.copy()
    
    def add_bootstrap_node(self, host: str, port: int) -> None:
        """Add a bootstrap node dynamically"""
        if (host, port) not in self.bootstrap_nodes:
            self.bootstrap_nodes.append((host, port))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get DHT statistics"""
        stats = {
            "peer_id": self.peer_id[:16] + "...",
            "entity_id": self.entity_id,
            "port": self.port,
            "running": self._running,
            "bootstrap_nodes": len(self.bootstrap_nodes),
            "kademlia_available": KADEMLIA_AVAILABLE,
            "crypto_available": CRYPTO_AVAILABLE,
            "capabilities": self.capabilities
        }
        
        if self._server and hasattr(self._server, 'protocol'):
            # Get routing table size if available
            try:
                routing_table = self._server.protocol.router
                stats["routing_table_buckets"] = len(routing_table.buckets)
            except Exception:
                pass
        
        return stats


# Global instance for singleton pattern
_dht_registry: Optional[DHTRegistry] = None


def get_dht_registry() -> Optional[DHTRegistry]:
    """Get global DHT registry instance"""
    return _dht_registry


def create_dht_registry(
    entity_id: str,
    entity_name: str,
    endpoint: str,
    public_key: str,
    private_key: Optional[str] = None,
    capabilities: List[str] = None,
    **kwargs
) -> DHTRegistry:
    """Create and set global DHT registry instance
    
    Args:
        entity_id: Entity identifier
        entity_name: Human-readable name
        endpoint: API endpoint (host:port)
        public_key: Base64 Ed25519 public key
        private_key: Optional base64 Ed25519 private key for signing
        capabilities: List of capability strings
        **kwargs: Additional arguments passed to DHTRegistry
        
    Returns:
        Created DHTRegistry instance
    """
    global _dht_registry
    _dht_registry = DHTRegistry(
        entity_id=entity_id,
        entity_name=entity_name,
        endpoint=endpoint,
        public_key=public_key,
        private_key=private_key,
        capabilities=capabilities or [],
        **kwargs
    )
    return _dht_registry


def reset_dht_registry() -> None:
    """Reset global DHT registry instance (for testing)"""
    global _dht_registry
    _dht_registry = None
