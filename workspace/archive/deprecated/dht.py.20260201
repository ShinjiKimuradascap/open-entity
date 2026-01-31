#!/usr/bin/env python3
"""
Kademlia DHT (Distributed Hash Table) Implementation

分散ハッシュテーブルによるピア発見システム。
Protocol v1.1仕様に準拠。

Features:
- Kademlia routing with k-buckets
- Parallel lookups (alpha=3)
- Node discovery and routing
- Value storage and retrieval
- Automatic bucket refresh

Protocol Parameters:
- k = 20 (bucket size)
- alpha = 3 (parallel lookups)
- tExpire = 86400s (key expiration)
- tRefresh = 3600s (bucket refresh interval)

DHT Key Structure:
key = SHA256(entity_id + ":" + capability_hash)
value = {entity_id, addresses[], public_key, capabilities[], last_seen, ttl}
"""

import asyncio
import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from collections import defaultdict
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Kademlia parameters
K_BUCKET_SIZE = 20
ALPHA_PARALLELISM = 3
T_EXPIRE = 86400
T_REFRESH = 3600
T_REPLICATE = 3600
T_REPUBLISH = 86400


class DHTError(Exception):
    """DHT関連エラー"""
    pass


def generate_node_id() -> bytes:
    """160ビットのランダムノードIDを生成"""
    return bytes([random.randint(0, 255) for _ in range(20)])


def node_id_to_hex(node_id: bytes) -> str:
    """ノードIDを16進文字列に変換"""
    return node_id.hex()


def hex_to_node_id(hex_str: str) -> bytes:
    """16進文字列をノードIDに変換"""
    return bytes.fromhex(hex_str)


def xor_distance(a: bytes, b: bytes) -> int:
    """2つのノードID間のXOR距離を計算"""
    return int.from_bytes(a, 'big') ^ int.from_bytes(b, 'big')


def compute_dht_key(entity_id: str, capability: str = "") -> bytes:
    """DHTキーを計算: SHA256(entity_id + ":" + capability_hash)"""
    capability_hash = hashlib.sha256(capability.encode()).hexdigest()[:16]
    key_string = f"{entity_id}:{capability_hash}"
    return hashlib.sha256(key_string.encode()).digest()


@dataclass
class NodeInfo:
    """DHTノード情報"""
    node_id: bytes
    address: str
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    public_key: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    
    @property
    def node_id_hex(self) -> str:
        return node_id_to_hex(self.node_id)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id_hex,
            "address": self.address,
            "last_seen": self.last_seen.isoformat(),
            "public_key": self.public_key,
            "capabilities": self.capabilities
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeInfo":
        return cls(
            node_id=hex_to_node_id(data["node_id"]),
            address=data["address"],
            last_seen=datetime.fromisoformat(data["last_seen"]),
            public_key=data.get("public_key"),
            capabilities=data.get("capabilities", [])
        )
    
    def is_stale(self, timeout: int = T_REFRESH) -> bool:
        delta = datetime.now(timezone.utc) - self.last_seen
        return delta.total_seconds() > timeout


@dataclass
class DHTValue:
    """DHTに保存される値"""
    entity_id: str
    addresses: List[str]
    public_key: str
    capabilities: List[str]
    last_seen: datetime
    ttl: int = T_EXPIRE
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "addresses": self.addresses,
            "public_key": self.public_key,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen.isoformat(),
            "ttl": self.ttl
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DHTValue":
        return cls(
            entity_id=data["entity_id"],
            addresses=data["addresses"],
            public_key=data["public_key"],
            capabilities=data["capabilities"],
            last_seen=datetime.fromisoformat(data["last_seen"]),
            ttl=data.get("ttl", T_EXPIRE)
        )
    
    def is_expired(self) -> bool:
        delta = datetime.now(timezone.utc) - self.last_seen
        return delta.total_seconds() > self.ttl


class KBucket:
    """Kademlia k-bucket - 同じ距離範囲のノードを保持"""
    
    def __init__(self, k: int = K_BUCKET_SIZE):
        self.k = k
        self.nodes: List[NodeInfo] = []
        self.lock = asyncio.Lock()
    
    async def add(self, node: NodeInfo) -> bool:
        """ノードを追加（LRU eviction）"""
        async with self.lock:
            for i, existing in enumerate(self.nodes):
                if existing.node_id == node.node_id:
                    self.nodes.pop(i)
                    self.nodes.append(node)
                    return True
            
            if len(self.nodes) < self.k:
                self.nodes.append(node)
                return True
            
            oldest = self.nodes[0]
            if oldest.is_stale():
                self.nodes.pop(0)
                self.nodes.append(node)
                return True
            
            return False
    
    async def remove(self, node_id: bytes) -> bool:
        """ノードを削除"""
        async with self.lock:
            for i, node in enumerate(self.nodes):
                if node.node_id == node_id:
                    self.nodes.pop(i)
                    return True
            return False
    
    def get_node(self, node_id: bytes) -> Optional[NodeInfo]:
        """ノードを取得"""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None
    
    def get_all_nodes(self) -> List[NodeInfo]:
        """全ノードを取得"""
        return self.nodes.copy()
    
    def get_closest_nodes(self, target: bytes, count: int = K_BUCKET_SIZE) -> List[NodeInfo]:
        """ターゲットに最も近いノードを取得"""
        sorted_nodes = sorted(self.nodes, key=lambda n: xor_distance(n.node_id, target))
        return sorted_nodes[:count]


class KademliaDHT:
    """
    Kademlia DHTメインクラス
    
    - 160ビットID空間
    - k-bucketによるルーティングテーブル
    - 並列ルックアップ
    """
    
    def __init__(
        self,
        node_id: Optional[bytes] = None,
        listen_address: str = "0.0.0.0:0",
        k: int = K_BUCKET_SIZE,
        alpha: int = ALPHA_PARALLELISM
    ):
        self.node_id = node_id or generate_node_id()
        self.listen_address = listen_address
        self.k = k
        self.alpha = alpha
        
        # Routing table: 160 buckets (one per bit)
        self.buckets: List[KBucket] = [KBucket(k) for _ in range(160)]
        
        # Storage
        self.storage: Dict[bytes, DHTValue] = {}
        self.storage_lock = asyncio.Lock()
        
        # Callbacks for network operations
        self.find_node_callback: Optional[Callable[[str, bytes], List[NodeInfo]]] = None
        self.find_value_callback: Optional[Callable[[str, bytes], Optional[DHTValue]]] = None
        self.store_callback: Optional[Callable[[str, bytes, DHTValue], bool]] = None
        
        # Tasks
        self._refresh_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"KademliaDHT initialized: node_id={self.node_id_hex[:16]}...")
    
    @property
    def node_id_hex(self) -> str:
        return node_id_to_hex(self.node_id)
    
    def _get_bucket_index(self, node_id: bytes) -> int:
        """ノードIDに対するbucketインデックスを計算"""
        distance = xor_distance(self.node_id, node_id)
        if distance == 0:
            return 0
        return 160 - distance.bit_length()
    
    async def add_node(self, node: NodeInfo) -> bool:
        """ノードをルーティングテーブルに追加"""
        if node.node_id == self.node_id:
            return False
        
        bucket_index = self._get_bucket_index(node.node_id)
        bucket = self.buckets[bucket_index]
        
        success = await bucket.add(node)
        if success:
            logger.debug(f"Added node {node.node_id_hex[:8]}... to bucket {bucket_index}")
        return success
    
    async def remove_node(self, node_id: bytes) -> bool:
        """ノードを削除"""
        bucket_index = self._get_bucket_index(node_id)
        bucket = self.buckets[bucket_index]
        return await bucket.remove(node_id)
    
    def get_node(self, node_id: bytes) -> Optional[NodeInfo]:
        """ノードを検索"""
        bucket_index = self._get_bucket_index(node_id)
        bucket = self.buckets[bucket_index]
        return bucket.get_node(node_id)
    
    def get_closest_nodes(self, target: bytes, count: int = K_BUCKET_SIZE) -> List[NodeInfo]:
        """ターゲットに最も近いk個のノードを取得"""
        all_nodes: List[NodeInfo] = []
        for bucket in self.buckets:
            all_nodes.extend(bucket.get_all_nodes())
        
        sorted_nodes = sorted(all_nodes, key=lambda n: xor_distance(n.node_id, target))
        return sorted_nodes[:count]
    
    async def store(self, key: bytes, value: DHTValue) -> bool:
        """値をDHTに保存"""
        async with self.storage_lock:
            self.storage[key] = value
        
        # 最も近いk個のノードに複製
        closest = self.get_closest_nodes(key, self.k)
        stored_count = 1  # 自分
        
        for node in closest:
            if self.store_callback:
                try:
                    success = await asyncio.wait_for(
                        self._store_remote(node, key, value),
                        timeout=5.0
                    )
                    if success:
                        stored_count += 1
                except Exception as e:
                    logger.warning(f"Failed to store to {node.address}: {e}")
        
        logger.info(f"Stored key {key.hex()[:16]}... to {stored_count} nodes")
        return stored_count > 0
    
    async def _store_remote(self, node: NodeInfo, key: bytes, value: DHTValue) -> bool:
        """リモートノードに保存（コールバック使用）"""
        if self.store_callback:
            return await self.store_callback(node.address, key, value)
        return False
    
    async def find_value(self, key: bytes) -> Optional[DHTValue]:
        """値を検索"""
        # ローカルから検索
        async with self.storage_lock:
            if key in self.storage:
                value = self.storage[key]
                if not value.is_expired():
                    return value
                del self.storage[key]
        
        # リモートから検索
        return await self._find_value_remote(key)
    
    async def _find_value_remote(self, key: bytes) -> Optional[DHTValue]:
        """リモートから値を検索"""
        closest = self.get_closest_nodes(key, self.alpha)
        
        for node in closest:
            if self.find_value_callback:
                try:
                    value = await asyncio.wait_for(
                        self.find_value_callback(node.address, key),
                        timeout=5.0
                    )
                    if value:
                        return value
                except Exception as e:
                    logger.warning(f"Failed to find value from {node.address}: {e}")
        
        return None
    
    async def find_node(self, target_id: bytes) -> Optional[NodeInfo]:
        """特定のノードを検索"""
        # ローカルから検索
        node = self.get_node(target_id)
        if node:
            return node
        
        # リモートから検索
        closest = self.get_closest_nodes(target_id, self.alpha)
        
        for node in closest:
            if self.find_node_callback:
                try:
                    nodes = await asyncio.wait_for(
                        self.find_node_callback(node.address, target_id),
                        timeout=5.0
                    )
                    for found in nodes:
                        if found.node_id == target_id:
                            await self.add_node(found)
                            return found
                        await self.add_node(found)
                except Exception as e:
                    logger.warning(f"Failed to find node from {node.address}: {e}")
        
        return None
    
    async def bootstrap(self, bootstrap_nodes: List[str]) -> bool:
        """ブートストラップノードから開始"""
        logger.info(f"Bootstrapping with {len(bootstrap_nodes)} nodes")
        
        connected = 0
        for address in bootstrap_nodes:
            try:
                # 自分自身への問い合わせで相手のノード情報を取得
                node = await self._ping_node(address)
                if node:
                    await self.add_node(node)
                    connected += 1
            except Exception as e:
                logger.warning(f"Bootstrap failed for {address}: {e}")
        
        logger.info(f"Bootstrap complete: {connected} nodes connected")
        return connected > 0
    
    async def _ping_node(self, address: str) -> Optional[NodeInfo]:
        """ノードにpingして情報を取得（コールバック使用）"""
        # 実装はnetwork layerで提供
        return None
    
    async def start(self):
        """DHTを開始"""
        self._running = True
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("KademliaDHT started")
    
    async def stop(self):
        """DHTを停止"""
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        logger.info("KademliaDHT stopped")
    
    async def _refresh_loop(self):
        """定期的なバケットリフレッシュ"""
        while self._running:
            try:
                await asyncio.sleep(T_REFRESH)
                await self._refresh_buckets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refresh error: {e}")
    
    async def _refresh_buckets(self):
        """古いバケットをリフレッシュ"""
        for i, bucket in enumerate(self.buckets):
            nodes = bucket.get_all_nodes()
            if not nodes:
                continue
            
            # 古いノードを削除
            stale_nodes = [n for n in nodes if n.is_stale()]
            for node in stale_nodes:
                await bucket.remove(node.node_id)
                logger.debug(f"Removed stale node from bucket {i}")
    
    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        total_nodes = sum(len(b.get_all_nodes()) for b in self.buckets)
        non_empty_buckets = sum(1 for b in self.buckets if b.get_all_nodes())
        
        return {
            "node_id": self.node_id_hex[:16] + "...",
            "total_nodes": total_nodes,
            "non_empty_buckets": non_empty_buckets,
            "stored_keys": len(self.storage),
            "listen_address": self.listen_address
        }


class DHTPeerDiscovery:
    """
    DHTベースのピア発見サービス
    
    Protocol v1.1仕様:
    - entity_idで検索可能
    - capabilityで検索可能
    - 分散型レジストリとの統合
    """
    
    def __init__(
        self,
        dht: KademliaDHT,
        entity_id: str,
        public_key: str,
        capabilities: List[str]
    ):
        self.dht = dht
        self.entity_id = entity_id
        self.public_key = public_key
        self.capabilities = capabilities
        self.addresses: List[str] = []
        
        # Registration task
        self._register_task: Optional[asyncio.Task] = None
        self._running = False
    
    def add_address(self, address: str):
        """公開アドレスを追加"""
        if address not in self.addresses:
            self.addresses.append(address)
    
    async def register(self) -> bool:
        """自分の情報をDHTに登録"""
        if not self.addresses:
            logger.warning("No addresses to register")
            return False
        
        value = DHTValue(
            entity_id=self.entity_id,
            addresses=self.addresses,
            public_key=self.public_key,
            capabilities=self.capabilities,
            last_seen=datetime.now(timezone.utc),
            ttl=T_REPUBLISH
        )
        
        # Entity IDで登録
        key = compute_dht_key(self.entity_id)
        success = await self.dht.store(key, value)
        
        # 各capabilityでも登録
        for capability in self.capabilities:
            cap_key = compute_dht_key(self.entity_id, capability)
            await self.dht.store(cap_key, value)
        
        logger.info(f"Registered entity {self.entity_id} to DHT")
        return success
    
    async def start(self):
        """定期的な再登録を開始"""
        self._running = True
        self._register_task = asyncio.create_task(self._register_loop())
        
        # 初回登録
        await self.register()
    
    async def stop(self):
        """停止"""
        self._running = False
        if self._register_task:
            self._register_task.cancel()
            try:
                await self._register_task
            except asyncio.CancelledError:
                pass
    
    async def _register_loop(self):
        """定期的に再登録"""
        while self._running:
            try:
                await asyncio.sleep(T_REPUBLISH / 2)  # 半分の間隔で再登録
                await self.register()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Registration error: {e}")
    
    async def find_entity(self, entity_id: str) -> Optional[DHTValue]:
        """エンティティを検索"""
        key = compute_dht_key(entity_id)
        return await self.dht.find_value(key)
    
    async def find_by_capability(self, capability: str) -> List[DHTValue]:
        """capabilityで検索（複数結果）"""
        # 注: 完全な実装にはiterative lookupが必要
        # 簡易実装ではローカルと近傍ノードのみ検索
        results = []
        
        key = compute_dht_key("", capability)  # capabilityのみで検索
        value = await self.dht.find_value(key)
        if value:
            results.append(value)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """統計情報"""
        return {
            "entity_id": self.entity_id,
            "addresses": self.addresses,
            "capabilities": self.capabilities,
            "dht_stats": self.dht.get_stats()
        }


# Global instance management
_dht_instances: Dict[str, KademliaDHT] = {}
_discovery_instances: Dict[str, DHTPeerDiscovery] = {}


def get_dht(node_id: Optional[str] = None) -> KademliaDHT:
    """DHTインスタンスを取得（singleton per node_id）"""
    key = node_id or "default"
    if key not in _dht_instances:
        node_id_bytes = hex_to_node_id(node_id) if node_id else None
        _dht_instances[key] = KademliaDHT(node_id=node_id_bytes)
    return _dht_instances[key]


def get_discovery(
    entity_id: str,
    public_key: str,
    capabilities: List[str]
) -> DHTPeerDiscovery:
    """Discoveryサービスを取得"""
    if entity_id not in _discovery_instances:
        dht = get_dht()
        _discovery_instances[entity_id] = DHTPeerDiscovery(
            dht=dht,
            entity_id=entity_id,
            public_key=public_key,
            capabilities=capabilities
        )
    return _discovery_instances[entity_id]


if __name__ == "__main__":
    # テスト
    async def test():
        print("=== DHT Module Test ===")
        
        # DHT作成
        dht1 = KademliaDHT()
        dht2 = KademliaDHT()
        
        print(f"DHT1 Node ID: {dht1.node_id_hex}")
        print(f"DHT2 Node ID: {dht2.node_id_hex}")
        
        # 距離計算
        dist = xor_distance(dht1.node_id, dht2.node_id)
        print(f"XOR Distance: {dist}")
        
        # ノード追加
        node2 = NodeInfo(
            node_id=dht2.node_id,
            address="127.0.0.1:8002"
        )
        await dht1.add_node(node2)
        print(f"Added node to DHT1 routing table")
        
        # 統計
        print(f"DHT1 Stats: {dht1.get_stats()}")
        
        # 値の保存
        value = DHTValue(
            entity_id="test-entity",
            addresses=["127.0.0.1:9000"],
            public_key="test-pubkey",
            capabilities=["chat", "code"],
            last_seen=datetime.now(timezone.utc)
        )
        key = compute_dht_key("test-entity")
        await dht1.store(key, value)
        print(f"Stored value for key: {key.hex()[:16]}...")
        
        # 値の検索
        found = await dht1.find_value(key)
        if found:
            print(f"Found value: {found.to_dict()}")
        
        # DHT Key計算テスト
        key1 = compute_dht_key("entity-a")
        key2 = compute_dht_key("entity-a", "chat")
        print(f"Key (entity only): {key1.hex()[:16]}...")
        print(f"Key (with capability): {key2.hex()[:16]}...")
        
        print("\n=== Test Complete ===")
    
    asyncio.run(test())


