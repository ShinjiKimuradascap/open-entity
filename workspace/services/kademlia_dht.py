#!/usr/bin/env python3
"""
Kademlia DHT Registry Wrapper
DHTラッパークラス - Peer Discovery統合用

Protocol v1.2 Phase 1 Implementation
- DHTRegistry: DHT操作の高レベルラッパー
- PeerInfo: ピア情報データクラス
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from pathlib import Path

# Import existing DHT implementation
from services.dht_node import DHTNode, NodeID, NodeInfo, K

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """ピア情報データクラス"""
    peer_id: str
    endpoint: str
    public_key: str
    capabilities: List[str] = field(default_factory=list)
    last_seen: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.last_seen is None:
            self.last_seen = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "endpoint": self.endpoint,
            "public_key": self.public_key,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PeerInfo':
        return cls(
            peer_id=data["peer_id"],
            endpoint=data["endpoint"],
            public_key=data["public_key"],
            capabilities=data.get("capabilities", []),
            last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None,
            metadata=data.get("metadata", {})
        )
    
    def is_stale(self, timeout_seconds: int = 3600) -> bool:
        """ピア情報が古いかチェック"""
        if not self.last_seen:
            return True
        delta = datetime.now(timezone.utc) - self.last_seen
        return delta.total_seconds() > timeout_seconds


class DHTRegistry:
    """
    DHTベースのピアレジストリ
    
    機能:
    - ピアの登録・検索
    - ランダムピア発見
    - 定期リフレッシュ
    - 統計情報収集
    
    Usage:
        registry = DHTRegistry(
            entity_id="entity-a",
            keypair=keypair,
            listen_port=8468,
            bootstrap_nodes=[("bootstrap.example.com", 8468)]
        )
        await registry.start()
        
        # ピアを検索
        peer = await registry.lookup_peer("entity-b")
        
        # ランダムピア発見
        peers = await registry.discover_random_peers(10)
    """
    
    # 設定パラメータ
    DEFAULT_REFRESH_INTERVAL = 600  # 10分
    DEFAULT_TTL = 3600  # 1時間
    PEER_KEY_PREFIX = "peer:"
    CAPABILITY_KEY_PREFIX = "cap:"
    
    def __init__(
        self,
        entity_id: str,
        keypair: Optional[Any] = None,
        listen_port: int = 0,
        bootstrap_nodes: Optional[List[Tuple[str, int]]] = None,
        refresh_interval: int = DEFAULT_REFRESH_INTERVAL,
        data_dir: Optional[str] = None
    ):
        """
        初期化
        
        Args:
            entity_id: このエンティティのID
            keypair: 署名用キーペア
            listen_port: DHTリッスンポート (0で自動)
            bootstrap_nodes: ブートストラップノードリスト [(host, port), ...]
            refresh_interval: リフレッシュ間隔（秒）
            data_dir: データ保存ディレクトリ
        """
        self.entity_id = entity_id
        self.keypair = keypair
        self.listen_port = listen_port
        self.bootstrap_nodes = bootstrap_nodes or []
        self.refresh_interval = refresh_interval
        self.data_dir = Path(data_dir) if data_dir else Path("data/dht_registry")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # DHTノード
        self._dht_node: Optional[DHTNode] = None
        self._node_id: NodeID = NodeID(entity_id)
        
        # キャッシュ
        self._peers: Dict[str, PeerInfo] = {}
        self._capabilities: Dict[str, Set[str]] = {}  # capability -> set of peer_ids
        
        # コールバック
        self._peer_callbacks: List[Callable[[PeerInfo], None]] = []
        
        # タスク
        self._refresh_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 統計
        self._started_at: Optional[datetime] = None
        self._registrations_sent = 0
        self._lookups_performed = 0
        
        logger.info(f"DHTRegistry initialized for {entity_id}")
    
    @property
    def is_running(self) -> bool:
        """DHTが実行中か"""
        return self._running and self._dht_node is not None
    
    @property
    def node_id(self) -> str:
        """DHTノードID"""
        return self._node_id.hex
    
    async def start(self) -> bool:
        """
        DHTレジストリを開始
        
        Returns:
            True if successful
        """
        if self._running:
            return True
        
        try:
            # ブートストラップノードを整形
            bootstrap_list = [
                {"host": host, "port": port}
                for host, port in self.bootstrap_nodes
            ]
            
            # DHTノードを作成・開始
            self._dht_node = DHTNode(
                host="0.0.0.0",
                port=self.listen_port,
                node_id=self._node_id,
                bootstrap_nodes=bootstrap_list,
                data_dir=str(self.data_dir)
            )
            
            await self._dht_node.start()
            self._running = True
            self._started_at = datetime.now(timezone.utc)
            
            # リフレッシュタスク開始
            self._refresh_task = asyncio.create_task(self._refresh_loop())
            
            logger.info(f"DHTRegistry started on port {self._dht_node.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start DHTRegistry: {e}")
            self._dht_node = None
            return False
    
    async def stop(self) -> None:
        """DHTレジストリを停止"""
        if not self._running:
            return
        
        self._running = False
        
        # タスクをキャンセル
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        # DHTノードを停止
        if self._dht_node:
            await self._dht_node.stop()
            self._dht_node = None
        
        # キャッシュを保存
        self._save_cache()
        
        logger.info("DHTRegistry stopped")
    
    async def register_peer(
        self,
        peer_id: str,
        endpoint: str,
        public_key: str,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        ピアをDHTに登録
        
        Args:
            peer_id: ピアID
            endpoint: エンドポイントURL
            public_key: Ed25519公開鍵（Base64）
            capabilities: 対応機能リスト
            metadata: 追加メタデータ
            
        Returns:
            True if successful
        """
        if not self._dht_node:
            logger.warning("DHT not started")
            return False
        
        try:
            # PeerInfoを作成
            peer_info = PeerInfo(
                peer_id=peer_id,
                endpoint=endpoint,
                public_key=public_key,
                capabilities=capabilities or [],
                metadata=metadata or {}
            )
            
            # DHTキーを計算
            key = self._compute_peer_key(peer_id)
            
            # 値をシリアライズ
            value = json.dumps(peer_info.to_dict()).encode('utf-8')
            
            # DHTに保存
            success = await self._dht_node.store(key, value, self._node_id)
            
            if success:
                # キャッシュを更新
                self._peers[peer_id] = peer_info
                
                # capabilityインデックスを更新
                for cap in (capabilities or []):
                    if cap not in self._capabilities:
                        self._capabilities[cap] = set()
                    self._capabilities[cap].add(peer_id)
                
                self._registrations_sent += 1
                logger.debug(f"Registered peer: {peer_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to register peer: {e}")
            return False
    
    async def lookup_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """
        ピアを検索
        
        Args:
            peer_id: 検索するピアID
            
        Returns:
            PeerInfo or None
        """
        if not self._dht_node:
            logger.warning("DHT not started")
            return None
        
        # キャッシュをチェック
        if peer_id in self._peers:
            cached = self._peers[peer_id]
            if not cached.is_stale():
                return cached
        
        try:
            # DHTキーを計算
            key = self._compute_peer_key(peer_id)
            
            # DHTから検索
            value_bytes = await self._dht_node.find_value(key)
            
            self._lookups_performed += 1
            
            if value_bytes:
                # デシリアライズ
                data = json.loads(value_bytes.decode('utf-8'))
                peer_info = PeerInfo.from_dict(data)
                
                # キャッシュを更新
                self._peers[peer_id] = peer_info
                
                logger.debug(f"Found peer: {peer_id}")
                return peer_info
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to lookup peer: {e}")
            return None
    
    async def discover_random_peers(self, count: int = 10) -> List[PeerInfo]:
        """
        ランダムピアを発見
        
        DHTのルーティングテーブルからピアを収集
        
        Args:
            count: 目標ピア数
            
        Returns:
            発見したピアリスト
        """
        if not self._dht_node:
            logger.warning("DHT not started")
            return []
        
        peers = []
        
        try:
            # ルーティングテーブルからノードを収集
            all_nodes = self._dht_node.routing_table.get_all_nodes()
            
            # 重複を排除してシャッフル
            seen_ids = {self.entity_id}
            candidates = []
            
            for node in all_nodes:
                # ノードIDからピアIDを導出（実際の実装ではメタデータを取得する必要がある）
                # 簡易実装: ノードIDをピアIDとして使用
                peer_id = f"node-{node.node_id.hex[:16]}"
                
                if peer_id not in seen_ids:
                    seen_ids.add(peer_id)
                    candidates.append((peer_id, node))
            
            # ランダムに選択
            import random
            random.shuffle(candidates)
            selected = candidates[:count]
            
            # PeerInfoを作成
            for peer_id, node in selected:
                # 実際のピア情報を取得（DHT lookup）
                peer_info = await self.lookup_peer(peer_id)
                if peer_info:
                    peers.append(peer_info)
                else:
                    # フォールバック: ノード情報から推定
                    peer_info = PeerInfo(
                        peer_id=peer_id,
                        endpoint=f"http://{node.host}:{node.port}",
                        public_key="",  # 不明
                        last_seen=node.last_seen
                    )
                    peers.append(peer_info)
            
            logger.debug(f"Discovered {len(peers)} peers")
            return peers
            
        except Exception as e:
            logger.error(f"Failed to discover peers: {e}")
            return []
    
    async def find_peers_by_capability(self, capability: str, count: int = 10) -> List[PeerInfo]:
        """
        機能でピアを検索
        
        Args:
            capability: 検索する機能
            count: 最大結果数
            
        Returns:
            マッチするピアリスト
        """
        if not self._dht_node:
            return []
        
        # キャッシュインデックスをチェック
        if capability in self._capabilities:
            peer_ids = list(self._capabilities[capability])[:count]
            peers = []
            for peer_id in peer_ids:
                peer = await self.lookup_peer(peer_id)
                if peer:
                    peers.append(peer)
            return peers
        
        # DHT検索（完全な実装にはcapabilityベースのキーが必要）
        # 簡易実装: ランダムピアからフィルタリング
        peers = await self.discover_random_peers(count * 2)
        return [p for p in peers if capability in p.capabilities][:count]
    
    def add_peer_discovered_callback(self, callback: Callable[[PeerInfo], None]) -> None:
        """ピア発見コールバックを登録"""
        self._peer_callbacks.append(callback)
    
    def remove_peer_discovered_callback(self, callback: Callable[[PeerInfo], None]) -> None:
        """ピア発見コールバックを削除"""
        if callback in self._peer_callbacks:
            self._peer_callbacks.remove(callback)
    
    def _compute_peer_key(self, peer_id: str) -> bytes:
        """ピアIDからDHTキーを計算"""
        key_string = f"{self.PEER_KEY_PREFIX}{peer_id}"
        return hashlib.sha256(key_string.encode()).digest()
    
    def _compute_capability_key(self, capability: str) -> bytes:
        """機能名からDHTキーを計算"""
        key_string = f"{self.CAPABILITY_KEY_PREFIX}{capability}"
        return hashlib.sha256(key_string.encode()).digest()
    
    async def _refresh_loop(self) -> None:
        """定期リフレッシュループ"""
        while self._running:
            try:
                await asyncio.sleep(self.refresh_interval)
                
                # 古いキャッシュエントリを削除
                now = datetime.now(timezone.utc)
                stale_peers = [
                    peer_id for peer_id, peer in self._peers.items()
                    if peer.is_stale(self.refresh_interval * 2)
                ]
                for peer_id in stale_peers:
                    del self._peers[peer_id]
                    logger.debug(f"Removed stale peer from cache: {peer_id}")
                
                # 自分自身を再登録
                if self.keypair:
                    await self.register_peer(
                        peer_id=self.entity_id,
                        endpoint=f"0.0.0.0:{self._dht_node.port if self._dht_node else 0}",
                        public_key=self.keypair.public_key if hasattr(self.keypair, 'public_key') else "",
                        capabilities=[]
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refresh error: {e}")
    
    def _save_cache(self) -> None:
        """キャッシュを保存"""
        try:
            cache_file = self.data_dir / "peer_cache.json"
            data = {
                "peers": {k: v.to_dict() for k, v in self._peers.items()},
                "saved_at": datetime.now(timezone.utc).isoformat()
            }
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved peer cache: {len(self._peers)} peers")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def _load_cache(self) -> None:
        """キャッシュを読み込み"""
        try:
            cache_file = self.data_dir / "peer_cache.json"
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                for peer_id, peer_data in data.get("peers", {}).items():
                    self._peers[peer_id] = PeerInfo.from_dict(peer_data)
                logger.info(f"Loaded peer cache: {len(self._peers)} peers")
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        uptime = None
        if self._started_at:
            delta = datetime.now(timezone.utc) - self._started_at
            uptime = delta.total_seconds()
        
        dht_stats = {}
        if self._dht_node:
            dht_stats = self._dht_node.get_stats()
        
        return {
            "running": self._running,
            "entity_id": self.entity_id,
            "node_id": self.node_id,
            "uptime_seconds": uptime,
            "peers_cached": len(self._peers),
            "registrations_sent": self._registrations_sent,
            "lookups_performed": self._lookups_performed,
            "dht": dht_stats
        }
    
    def get_cached_peers(self) -> List[PeerInfo]:
        """キャッシュされたピアリストを取得"""
        return list(self._peers.values())


# Convenience functions
async def create_dht_registry(
    entity_id: str,
    keypair: Optional[Any] = None,
    listen_port: int = 0,
    bootstrap_nodes: Optional[List[Tuple[str, int]]] = None
) -> Optional[DHTRegistry]:
    """
    DHTRegistryを作成して開始
    
    Args:
        entity_id: エンティティID
        keypair: 署名用キーペア
        listen_port: DHTポート (0で自動)
        bootstrap_nodes: ブートストラップノード [(host, port), ...]
    
    Returns:
        開始したDHTRegistryまたはNone
    """
    registry = DHTRegistry(
        entity_id=entity_id,
        keypair=keypair,
        listen_port=listen_port,
        bootstrap_nodes=bootstrap_nodes
    )
    
    success = await registry.start()
    if success:
        return registry
    return None


if __name__ == "__main__":
    # テスト
    async def test():
        print("=== DHTRegistry Test ===")
        
        # レジストリ1を作成
        registry1 = DHTRegistry(
            entity_id="test-entity-1",
            listen_port=8468
        )
        
        success = await registry1.start()
        print(f"Registry1 started: {success}")
        print(f"Node ID: {registry1.node_id}")
        
        # レジストリ2を作成（レジストリ1をブートストラップ）
        registry2 = DHTRegistry(
            entity_id="test-entity-2",
            listen_port=0,  # 自動割り当て
            bootstrap_nodes=[("127.0.0.1", registry1._dht_node.port)]
        )
        
        success = await registry2.start()
        print(f"Registry2 started: {success}")
        
        # 少し待つ
        await asyncio.sleep(2)
        
        # ピアを登録
        await registry1.register_peer(
            peer_id="test-entity-1",
            endpoint="http://127.0.0.1:8000",
            public_key="test-pubkey-1",
            capabilities=["chat", "code"]
        )
        print("Registered entity-1")
        
        # ピアを検索
        peer = await registry2.lookup_peer("test-entity-1")
        if peer:
            print(f"Found peer: {peer.to_dict()}")
        else:
            print("Peer not found (expected in local test)")
        
        # 統計を表示
        print(f"\nRegistry1 stats:")
        print(json.dumps(registry1.get_stats(), indent=2))
        
        # 停止
        await registry1.stop()
        await registry2.stop()
        
        print("\n=== Test Complete ===")
    
    asyncio.run(test())
