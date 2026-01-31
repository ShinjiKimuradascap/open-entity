#!/usr/bin/env python3
"""
Bootstrap Auto-Discovery Manager
再帰的ブートストラップノード発見機能

Design: docs/network_architecture_l2_design.md (Entity B)
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Callable, Any
from pathlib import Path
from enum import Enum

import aiohttp
from aiohttp import ClientTimeout

# DHT imports (optional)
try:
    from services.kademlia_dht import DHTRegistry, PeerInfo as DHTPeerInfo
    KADEMLIA_AVAILABLE = True
except ImportError:
    try:
        from kademlia_dht import DHTRegistry, PeerInfo as DHTPeerInfo
        KADEMLIA_AVAILABLE = True
    except ImportError:
        KADEMLIA_AVAILABLE = False
        DHTRegistry = None
        DHTPeerInfo = None

# Crypto imports
try:
    from services.crypto import KeyPair
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        from crypto import KeyPair
        CRYPTO_AVAILABLE = True
    except ImportError:
        CRYPTO_AVAILABLE = False
        KeyPair = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DiscoveryMode(Enum):
    """Discovery operation modes"""
    HTTP_ONLY = "http_only"      # HTTP recursive discovery only
    DHT_ONLY = "dht_only"        # DHT discovery only
    HYBRID = "hybrid"            # Both HTTP and DHT discovery


@dataclass
class BootstrapNodeInfo:
    """ブートストラップノード情報"""
    node_id: str
    endpoint: str
    public_key: Optional[str] = None
    signature: Optional[str] = None
    last_seen: Optional[datetime] = None
    reachability_score: float = 0.0  # 0-100
    latency_ms: Optional[float] = None
    is_verified: bool = False
    is_reachable: bool = False
    # Extended fields for recursive discovery scoring
    discovered_from: Optional[str] = None  # 発見元ノードID
    discovery_depth: int = 0  # 探索深度（0=シードノード）
    trust_score: float = 0.0  # 総合信頼スコア（0-100）
    dht_endpoint: Optional[str] = None  # DHTエンドポイント


@dataclass
class DiscoveryStats:
    """発見統計"""
    nodes_discovered: int
    nodes_verified: int
    avg_latency_ms: float
    discovery_time_ms: float
    max_depth_reached: int


class BootstrapDiscoveryManager:
    """ブートストラップ自動発見マネージャー
    
    機能:
    - 再帰的ブートストラップ発見（最大深度3）
    - Ed25519署名検証
    - 到達可能性スコアリング（レイテンシ + 安定性 + 多様性）
    - 自動デッドノード剪定
    
    Usage:
        manager = BootstrapDiscoveryManager()
        await manager.discover_from_seed("https://bootstrap-1.example.com")
        nodes = manager.get_best_nodes(count=5)
    """
    
    MAX_DISCOVERY_DEPTH = 3
    DEFAULT_TIMEOUT = ClientTimeout(total=5.0, connect=2.0)
    REACHABILITY_TIMEOUT_MS = 5000  # 5秒
    
    def __init__(
        self,
        verify_signatures: bool = True,
        max_depth: int = 3,
        cache_file: Optional[str] = None,
        # DHT parameters (v1.2)
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        endpoint: Optional[str] = None,
        public_key: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        keypair: Optional[Any] = None,
        dht_port: int = 0,
        discovery_mode: DiscoveryMode = DiscoveryMode.HYBRID,
        bootstrap_config_path: str = "config/bootstrap_nodes.json"
    ):
        """初期化
        
        Args:
            verify_signatures: 署名検証を有効化
            max_depth: 最大再帰深度
            cache_file: ノードキャッシュファイルパス
            entity_id: Local entity identifier (for DHT)
            entity_name: Human-readable name (for DHT)
            endpoint: API endpoint host:port (for DHT)
            public_key: Base64 Ed25519 public key (for DHT)
            capabilities: Supported capabilities (for DHT)
            keypair: KeyPair for signing (for DHT)
            dht_port: UDP port for DHT (0 for auto)
            discovery_mode: HTTP_ONLY, DHT_ONLY, or HYBRID
            bootstrap_config_path: Path to bootstrap_nodes.json
        """
        self.verify_signatures = verify_signatures
        self.max_depth = min(max_depth, self.MAX_DISCOVERY_DEPTH)
        self.cache_file = cache_file or "data/bootstrap_cache.json"
        
        # DHT parameters
        self.entity_id = entity_id
        self.entity_name = entity_name
        self.endpoint = endpoint
        self.public_key = public_key
        self.capabilities = capabilities or []
        self.keypair = keypair
        self.dht_port = dht_port
        self.discovery_mode = discovery_mode
        self.bootstrap_config_path = bootstrap_config_path
        
        self._nodes: Dict[str, BootstrapNodeInfo] = {}
        self._visited_endpoints: Set[str] = set()
        self._session: Optional[aiohttp.ClientSession] = None
        
        # DHT state
        self._dht_registry: Optional[DHTRegistry] = None
        self._dht_peers: Dict[str, DHTPeerInfo] = {}
        self._peer_discovered_callbacks: List[Callable[[DHTPeerInfo], None]] = []
        
        # キャッシュ読み込み
        self._load_cache()
    
    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=self.DEFAULT_TIMEOUT)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None
    
    async def discover_from_seed(
        self,
        seed_endpoint: str,
        target_count: int = 10
    ) -> DiscoveryStats:
        """シードノードから再帰的発見
        
        Args:
            seed_endpoint: 初期シードノードのURL
            target_count: 目標発見ノード数
            
        Returns:
            DiscoveryStats: 発見統計
        """
        start_time = time.time()
        self._visited_endpoints.clear()
        
        if not self._session:
            self._session = aiohttp.ClientSession(timeout=self.DEFAULT_TIMEOUT)
        
        try:
            # 再帰的発見を開始
            await self._recursive_discover(
                seed_endpoint,
                current_depth=0,
                target_count=target_count
            )
            
            # 到達可能性テスト
            await self._test_reachability()
            
            # キャッシュ保存
            self._save_cache()
            
        except Exception as e:
            logger.error(f"Discovery error: {e}")
        
        discovery_time = (time.time() - start_time) * 1000
        
        return DiscoveryStats(
            nodes_discovered=len(self._nodes),
            nodes_verified=sum(1 for n in self._nodes.values() if n.is_verified),
            avg_latency_ms=self._calculate_avg_latency(),
            discovery_time_ms=discovery_time,
            max_depth_reached=self.max_depth
        )
    
    async def _recursive_discover(
        self,
        endpoint: str,
        current_depth: int,
        target_count: int
    ):
        """再帰的ノード発見（内部メソッド）"""
        if current_depth >= self.max_depth:
            return
        
        if endpoint in self._visited_endpoints:
            return
        
        self._visited_endpoints.add(endpoint)
        
        # ノードリストを取得
        nodes = await self._fetch_bootstrap_nodes(endpoint)
        
        for node_data in nodes:
            node_id = node_data.get("node_id")
            if not node_id or node_id in self._nodes:
                continue
            
            # ノード情報を作成
            node = BootstrapNodeInfo(
                node_id=node_id,
                endpoint=node_data.get("endpoint", ""),
                public_key=node_data.get("public_key"),
                signature=node_data.get("signature"),
                last_seen=datetime.now(timezone.utc)
            )
            
            # 署名検証
            if self.verify_signatures and node.signature:
                node.is_verified = await self._verify_signature(node)
            
            self._nodes[node_id] = node
            logger.debug(f"Discovered node: {node_id} at {node.endpoint}")
            
            # 目標数に達したら終了
            if len(self._nodes) >= target_count:
                return
            
            # 再帰的に発見
            if node.endpoint and node.endpoint not in self._visited_endpoints:
                await self._recursive_discover(
                    node.endpoint,
                    current_depth + 1,
                    target_count
                )
    
    async def _fetch_bootstrap_nodes(self, endpoint: str) -> List[Dict]:
        """ブートストラップノードリストを取得"""
        try:
            url = f"{endpoint}/bootstrap/nodes"
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("nodes", [])
                else:
                    logger.warning(f"Failed to fetch nodes from {endpoint}: {response.status}")
                    return []
        except Exception as e:
            logger.debug(f"Error fetching from {endpoint}: {e}")
            return []
    
    async def _verify_signature(self, node: BootstrapNodeInfo) -> bool:
        """ノード署名を検証"""
        if not node.public_key or not node.signature:
            return False
        
        try:
            # Ed25519署名検証
            from services.crypto import SignatureVerifier
            
            payload = f"{node.node_id}:{node.endpoint}"
            verifier = SignatureVerifier()
            return verifier.verify(payload, node.signature, node.public_key)
        except Exception as e:
            logger.debug(f"Signature verification failed for {node.node_id}: {e}")
            return False
    
    async def _test_reachability(self):
        """到達可能性テストとスコアリング"""
        tasks = []
        for node in self._nodes.values():
            tasks.append(self._ping_node(node))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _ping_node(self, node: BootstrapNodeInfo):
        """単一ノードのpingテスト"""
        try:
            start = time.time()
            url = f"{node.endpoint}/health"
            
            async with self._session.get(url, timeout=ClientTimeout(total=2.0)) as response:
                latency = (time.time() - start) * 1000
                node.latency_ms = latency
                
                if response.status == 200:
                    # 到達可能性スコア計算
                    # レイテンシスコア (0-40): 低いほど良い
                    latency_score = max(0, 40 - (latency / 50))
                    
                    # 検証スコア (0-30): 検証済みなら満点
                    verify_score = 30 if node.is_verified else 0
                    
                    # 新鮮さスコア (0-30)
                    freshness_score = 30  # 新しく発見されたノード
                    
                    node.reachability_score = latency_score + verify_score + freshness_score
                    node.is_reachable = True
                else:
                    node.reachability_score = 0
                    node.is_reachable = False
                    
        except Exception as e:
            node.reachability_score = 0
            node.is_reachable = False
            node.latency_ms = None
    
    def _calculate_avg_latency(self) -> float:
        """平均レイテンシを計算"""
        latencies = [
            n.latency_ms for n in self._nodes.values()
            if n.latency_ms is not None
        ]
        return sum(latencies) / len(latencies) if latencies else 0.0
    
    def get_best_nodes(
        self,
        count: int = 5,
        require_verified: bool = False
    ) -> List[BootstrapNodeInfo]:
        """最適なブートストラップノードを取得
        
        Args:
            count: 取得するノード数
            require_verified: 検証済みノードのみ
            
        Returns:
            到達可能性スコア順にソートされたノードリスト
        """
        nodes = list(self._nodes.values())
        
        if require_verified:
            nodes = [n for n in nodes if n.is_verified]
        
        # 到達可能性スコアでソート
        nodes.sort(key=lambda n: n.reachability_score, reverse=True)
        
        return nodes[:count]
    
    def prune_dead_nodes(self, max_age_hours: int = 24):
        """デッドノードを剪定
        
        Args:
            max_age_hours: この時間以上応答がないノードを削除
        """
        now = datetime.now(timezone.utc)
        to_remove = []
        
        for node_id, node in self._nodes.items():
            if node.last_seen:
                age = (now - node.last_seen).total_seconds() / 3600
                if age > max_age_hours and not node.is_reachable:
                    to_remove.append(node_id)
        
        for node_id in to_remove:
            del self._nodes[node_id]
            logger.debug(f"Pruned dead node: {node_id}")
        
        if to_remove:
            self._save_cache()
            logger.info(f"Pruned {len(to_remove)} dead bootstrap nodes")
    
    def _load_cache(self):
        """キャッシュからノードを読み込み"""
        try:
            cache_path = Path(self.cache_file)
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                    for node_data in data.get("nodes", []):
                        node = BootstrapNodeInfo(**node_data)
                        self._nodes[node.node_id] = node
                logger.info(f"Loaded {len(self._nodes)} bootstrap nodes from cache")
        except Exception as e:
            logger.warning(f"Failed to load bootstrap cache: {e}")
    
    def _save_cache(self):
        """キャッシュにノードを保存"""
        try:
            cache_path = Path(self.cache_file)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "nodes": [
                    {
                        "node_id": n.node_id,
                        "endpoint": n.endpoint,
                        "public_key": n.public_key,
                        "signature": n.signature,
                        "last_seen": n.last_seen.isoformat() if n.last_seen else None,
                        "reachability_score": n.reachability_score,
                        "latency_ms": n.latency_ms,
                        "is_verified": n.is_verified
                    }
                    for n in self._nodes.values()
                ],
                "saved_at": datetime.now(timezone.utc).isoformat()
            }
            
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to save bootstrap cache: {e}")
    
    def get_stats(self) -> Dict:
        """統計情報を取得"""
        stats = {
            "total_nodes": len(self._nodes),
            "verified_nodes": sum(1 for n in self._nodes.values() if n.is_verified),
            "reachable_nodes": sum(1 for n in self._nodes.values() if n.is_reachable),
            "avg_reachability_score": sum(
                n.reachability_score for n in self._nodes.values()
            ) / len(self._nodes) if self._nodes else 0,
            "dht_available": KADEMLIA_AVAILABLE,
            "dht_running": self._dht_registry is not None and self._dht_registry.is_running,
            "dht_peers": len(self._dht_peers)
        }
        if self._dht_registry:
            stats["dht_stats"] = self._dht_registry.get_stats()
        return stats
    
    # ==================== DHT Methods (v1.2) ====================
    
    async def start_dht(self) -> bool:
        """Start DHT registry for peer discovery"""
        if not KADEMLIA_AVAILABLE:
            logger.warning("kademlia not installed. DHT discovery disabled.")
            return False
        
        if not all([self.entity_id, self.public_key]):
            logger.error("entity_id and public_key required for DHT")
            return False
        
        try:
            # Parse bootstrap addresses from config
            bootstrap_addrs = self._get_dht_bootstrap_addresses()
            
            self._dht_registry = DHTRegistry(
                entity_id=self.entity_id,
                keypair=self.keypair,
                listen_port=self.dht_port,
                bootstrap_nodes=bootstrap_addrs,
                refresh_interval=600
            )
            
            success = await self._dht_registry.start()
            if success:
                logger.info(f"DHT started on port {self.dht_port}")
            else:
                logger.error("Failed to start DHT registry")
                self._dht_registry = None
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to start DHT: {e}")
            return False
    
    async def stop_dht(self) -> None:
        """Stop DHT registry"""
        if self._dht_registry:
            await self._dht_registry.stop()
            self._dht_registry = None
            logger.info("DHT stopped")
    
    def _get_dht_bootstrap_addresses(self) -> List[Tuple[str, int]]:
        """Parse DHT bootstrap addresses from config"""
        addresses = []
        try:
            with open(self.bootstrap_config_path, 'r') as f:
                config = json.load(f)
            
            # Get from bootstrap_servers
            for node in config.get("bootstrap_servers", []):
                dht_ep = node.get("dht_endpoint", "")
                if ":" in dht_ep:
                    host, port_str = dht_ep.rsplit(":", 1)
                    try:
                        addresses.append((host, int(port_str)))
                    except ValueError:
                        pass
            
            # Get from local_bootstrap
            for node in config.get("local_bootstrap", []):
                dht_ep = node.get("dht_endpoint", "")
                if ":" in dht_ep:
                    host, port_str = dht_ep.rsplit(":", 1)
                    try:
                        addresses.append((host, int(port_str)))
                    except ValueError:
                        pass
                        
        except Exception as e:
            logger.warning(f"Failed to load bootstrap addresses: {e}")
        
        return addresses
    
    async def discover_dht_peers(self, count: int = 10) -> List[DHTPeerInfo]:
        """Discover peers via DHT"""
        if not self._dht_registry:
            logger.warning("DHT not started")
            return []
        
        try:
            peers = await self._dht_registry.discover_random_peers(count)
            
            # Filter out self and notify callbacks
            for peer in peers:
                if peer.peer_id == self.entity_id:
                    continue
                
                if peer.peer_id not in self._dht_peers:
                    self._dht_peers[peer.peer_id] = peer
                    for callback in self._peer_discovered_callbacks:
                        try:
                            callback(peer)
                        except Exception as e:
                            logger.error(f"Peer discovered callback error: {e}")
            
            return peers
        except Exception as e:
            logger.error(f"DHT peer discovery failed: {e}")
            return []
    
    async def lookup_dht_peer(self, peer_id: str) -> Optional[DHTPeerInfo]:
        """Lookup specific peer via DHT"""
        if not self._dht_registry:
            return None
        return await self._dht_registry.lookup_peer(peer_id)
    
    def add_peer_discovered_callback(self, callback: Callable[[DHTPeerInfo], None]) -> None:
        """Add callback for DHT peer discovery events"""
        self._peer_discovered_callbacks.append(callback)
    
    async def discover(
        self,
        seed_endpoint: Optional[str] = None,
        target_count: int = 10
    ) -> Dict:
        """Run discovery based on mode (HTTP/DHT/HYBRID)"""
        results = {
            "http_nodes": [],
            "dht_peers": [],
            "errors": []
        }
        
        # HTTP discovery
        if self.discovery_mode in (DiscoveryMode.HTTP_ONLY, DiscoveryMode.HYBRID):
            if seed_endpoint:
                try:
                    stats = await self.discover_from_seed(seed_endpoint, target_count)
                    results["http_nodes"] = self.get_best_nodes(count=target_count)
                    results["http_stats"] = {
                        "discovered": stats.nodes_discovered,
                        "verified": stats.nodes_verified,
                        "time_ms": stats.discovery_time_ms
                    }
                except Exception as e:
                    results["errors"].append(f"HTTP discovery failed: {e}")
        
        # DHT discovery
        if self.discovery_mode in (DiscoveryMode.DHT_ONLY, DiscoveryMode.HYBRID):
            if not self._dht_registry:
                await self.start_dht()
            
            if self._dht_registry:
                try:
                    dht_peers = await self.discover_dht_peers(count=target_count)
                    results["dht_peers"] = dht_peers
                except Exception as e:
                    results["errors"].append(f"DHT discovery failed: {e}")
            else:
                results["errors"].append("DHT not available")
        
        return results


# グローバルインスタンス
_discovery_manager: Optional[BootstrapDiscoveryManager] = None


def get_discovery_manager() -> BootstrapDiscoveryManager:
    """グローバルDiscoveryManagerを取得"""
    global _discovery_manager
    if _discovery_manager is None:
        _discovery_manager = BootstrapDiscoveryManager()
    return _discovery_manager


# v1.2 Convenience factory with DHT support
async def create_discovery_manager(
    entity_id: str,
    entity_name: str,
    endpoint: str,
    public_key: str,
    capabilities: List[str],
    keypair: Optional[Any] = None,
    discovery_mode: DiscoveryMode = DiscoveryMode.HYBRID,
    **kwargs
) -> Optional[BootstrapDiscoveryManager]:
    """Create and initialize BootstrapDiscoveryManager with DHT support
    
    Args:
        entity_id: Entity identifier
        entity_name: Human-readable name
        endpoint: API endpoint
        public_key: Ed25519 public key
        capabilities: Supported capabilities
        keypair: KeyPair for signing
        discovery_mode: HTTP_ONLY, DHT_ONLY, or HYBRID
        **kwargs: Additional options
    
    Returns:
        Initialized BootstrapDiscoveryManager or None if failed
    """
    manager = BootstrapDiscoveryManager(
        entity_id=entity_id,
        entity_name=entity_name,
        endpoint=endpoint,
        public_key=public_key,
        capabilities=capabilities,
        keypair=keypair,
        discovery_mode=discovery_mode,
        **kwargs
    )
    
    # Start DHT if needed
    if discovery_mode in (DiscoveryMode.DHT_ONLY, DiscoveryMode.HYBRID):
        success = await manager.start_dht()
        if not success and discovery_mode == DiscoveryMode.DHT_ONLY:
            return None
    
    return manager
