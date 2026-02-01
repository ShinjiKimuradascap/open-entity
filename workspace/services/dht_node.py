#!/usr/bin/env python3
"""
DHT Node - Kademlia Protocol Implementation
分散ハッシュテーブル（DHT）ノード実装

機能:
- 160-bit NodeID（SHA-1ハッシュ）
- XOR距離メトリック
- K-bucket（k=20）ルーティングテーブル
- PING, STORE, FIND_NODE, FIND_VALUEメッセージ
- ブートストラップノード接続

Protocol v1.0対応:
- ピア発見・レジストリ機能
- 分散型キー値ストア
"""

import asyncio
import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from pathlib import Path

import aiohttp
from aiohttp import ClientTimeout, web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Kademlia constants
K = 20  # K-bucket size
ALPHA = 3  # 並行探索数
KEY_SIZE = 160  # SHA-1 hash size in bits
BUCKET_REFRESH_INTERVAL = 3600  # 1 hour
REPLICATION_FACTOR = 3  # データ複製数
EXPIRATION_TIME = 86400  # 24 hours


class NodeID:
    """160-bit DHTノードID"""
    
    def __init__(self, data: Optional[bytes] = None):
        if data is None:
            # ランダムに生成
            data = bytes([random.randint(0, 255) for _ in range(KEY_SIZE // 8)])
        elif isinstance(data, str):
            # 文字列からSHA-1ハッシュ生成
            data = hashlib.sha1(data.encode()).digest()
        elif isinstance(data, int):
            # 整数をバイト列に変換
            data = data.to_bytes(KEY_SIZE // 8, byteorder='big')
        
        self._data = data[:KEY_SIZE // 8]  # Ensure correct size
        self._int = int.from_bytes(self._data, byteorder='big')
    
    @property
    def bytes(self) -> bytes:
        return self._data
    
    @property
    def int(self) -> int:
        return self._int
    
    @property
    def hex(self) -> str:
        return self._data.hex()
    
    def distance_to(self, other: 'NodeID') -> int:
        """XOR距離を計算"""
        return self._int ^ other._int
    
    def distance_bytes(self, other: 'NodeID') -> bytes:
        """XOR距離をバイト列で返す"""
        xor = self._int ^ other._int
        return xor.to_bytes(KEY_SIZE // 8, byteorder='big')
    
    def __eq__(self, other) -> bool:
        if isinstance(other, NodeID):
            return self._data == other._data
        return False
    
    def __hash__(self) -> int:
        return hash(self._data)
    
    def __lt__(self, other: 'NodeID') -> bool:
        return self._int < other._int
    
    def __repr__(self) -> str:
        return f"NodeID({self.hex[:16]}...)"
    
    def __str__(self) -> str:
        return self.hex[:16]
    
    @classmethod
    def from_hex(cls, hex_str: str) -> 'NodeID':
        return cls(bytes.fromhex(hex_str))
    
    def bit_length(self) -> int:
        """最上位ビット位置（0-indexed）"""
        if self._int == 0:
            return 0
        return self._int.bit_length() - 1


@dataclass
class NodeInfo:
    """DHTノード情報"""
    node_id: NodeID
    host: str
    port: int
    last_seen: Optional[datetime] = None
    failed_pings: int = 0
    
    def __post_init__(self):
        if self.last_seen is None:
            self.last_seen = datetime.utcnow()
    
    @property
    def id_bytes(self) -> bytes:
        return self.node_id.bytes
    
    @property
    def endpoint(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    def distance_to(self, target_id: NodeID) -> int:
        return self.node_id.distance_to(target_id)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id.hex,
            "host": self.host,
            "port": self.port,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NodeInfo':
        return cls(
            node_id=NodeID.from_hex(data["node_id"]),
            host=data["host"],
            port=data["port"],
            last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None
        )


@dataclass
class ValueEntry:
    """DHTに格納される値"""
    key: bytes
    value: bytes
    timestamp: datetime = field(default_factory=datetime.utcnow)
    publisher_id: Optional[NodeID] = None
    expiration: Optional[datetime] = None
    
    def __post_init__(self):
        if self.expiration is None:
            self.expiration = datetime.utcnow() + timedelta(seconds=EXPIRATION_TIME)
    
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expiration
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key.hex(),
            "value": self.value.hex(),
            "timestamp": self.timestamp.isoformat(),
            "publisher_id": self.publisher_id.hex if self.publisher_id else None,
            "expiration": self.expiration.isoformat() if self.expiration else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValueEntry':
        return cls(
            key=bytes.fromhex(data["key"]),
            value=bytes.fromhex(data["value"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            publisher_id=NodeID.from_hex(data["publisher_id"]) if data.get("publisher_id") else None,
            expiration=datetime.fromisoformat(data["expiration"]) if data.get("expiration") else None
        )


class KBucket:
    """K-bucket: 距離に基づくノードコンテナ"""
    
    def __init__(self, min_distance: int, max_distance: int, k: int = K):
        self.min_distance = min_distance
        self.max_distance = max_distance
        self.k = k
        self.nodes: List[NodeInfo] = []
        self.last_updated = datetime.utcnow()
    
    def __contains__(self, node) -> bool:
        # Handle both NodeID and NodeInfo
        if isinstance(node, NodeID):
            node_id = node
        else:
            node_id = node.node_id
        return any(n.node_id == node_id for n in self.nodes)
    
    def add_node(self, node: NodeInfo) -> bool:
        """ノードを追加。満杯ならFalseを返す"""
        if node in self:
            # 既存ノードを先頭に移動（LRU）
            self.nodes = [n for n in self.nodes if n.node_id != node.node_id]
            self.nodes.insert(0, node)
            self.last_updated = datetime.utcnow()
            return True
        
        if len(self.nodes) < self.k:
            self.nodes.insert(0, node)
            self.last_updated = datetime.utcnow()
            return True
        
        return False  # 満杯
    
    def remove_node(self, node_id: NodeID) -> bool:
        """ノードを削除"""
        original_len = len(self.nodes)
        self.nodes = [n for n in self.nodes if n.node_id != node_id]
        return len(self.nodes) < original_len
    
    def get_least_recently_seen(self) -> Optional[NodeInfo]:
        """最も古いノードを返す"""
        if not self.nodes:
            return None
        return self.nodes[-1]
    
    def split(self) -> Tuple['KBucket', 'KBucket']:
        """バケットを2分割"""
        mid = (self.min_distance + self.max_distance) // 2
        left = KBucket(self.min_distance, mid, self.k)
        right = KBucket(mid + 1, self.max_distance, self.k)
        
        for node in self.nodes:
            distance = node.node_id.bit_length()
            if distance <= mid:
                left.add_node(node)
            else:
                right.add_node(node)
        
        return left, right


class RoutingTable:
    """Kademliaルーティングテーブル"""
    
    def __init__(self, node_id: NodeID, k: int = K):
        self.node_id = node_id
        self.k = k
        self.buckets: List[KBucket] = [
            KBucket(0, KEY_SIZE - 1, k)
        ]
    
    def get_bucket_index(self, distance: int) -> int:
        """距離に対応するバケットインデックスを取得"""
        if distance == 0:
            return -1  # 自分自身
        
        bit_pos = distance.bit_length() - 1
        
        for i, bucket in enumerate(self.buckets):
            if bucket.min_distance <= bit_pos <= bucket.max_distance:
                return i
        
        return len(self.buckets) - 1
    
    def add_node(self, node: NodeInfo) -> bool:
        """ノードをルーティングテーブルに追加"""
        distance = self.node_id.distance_to(node.node_id)
        if distance == 0:
            return True  # 自分自身
        
        bucket_idx = self.get_bucket_index(distance)
        bucket = self.buckets[bucket_idx]
        
        if bucket.add_node(node):
            return True
        
        # バケットが満杯で自分のID範囲なら分割
        if bucket.min_distance <= self.node_id.bit_length() <= bucket.max_distance:
            left, right = bucket.split()
            self.buckets[bucket_idx] = left
            self.buckets.insert(bucket_idx + 1, right)
            return self.add_node(node)
        
        return False
    
    def remove_node(self, node_id: NodeID) -> bool:
        """ノードを削除"""
        distance = self.node_id.distance_to(node_id)
        bucket_idx = self.get_bucket_index(distance)
        if bucket_idx >= 0:
            return self.buckets[bucket_idx].remove_node(node_id)
        return False
    
    def find_closest(self, target_id: NodeID, count: int = K) -> List[NodeInfo]:
        """ターゲットに最も近いノードを取得"""
        all_nodes = []
        for bucket in self.buckets:
            all_nodes.extend(bucket.nodes)
        
        # XOR距離でソート
        all_nodes.sort(key=lambda n: n.distance_to(target_id))
        return all_nodes[:count]
    
    def get_all_nodes(self) -> List[NodeInfo]:
        """全ノードを取得"""
        result = []
        for bucket in self.buckets:
            result.extend(bucket.nodes)
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """統計情報"""
        return {
            "total_nodes": sum(len(b.nodes) for b in self.buckets),
            "buckets": len(self.buckets),
            "bucket_sizes": [len(b.nodes) for b in self.buckets]
        }


class DHTNode:
    """Kademlia DHTノード"""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 0,
        node_id: Optional[NodeID] = None,
        bootstrap_nodes: Optional[List[Dict]] = None,
        data_dir: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.node_id = node_id or NodeID()
        self.bootstrap_nodes = bootstrap_nodes or []
        self.data_dir = Path(data_dir) if data_dir else Path("data/dht")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # ルーティングテーブル
        self.routing_table = RoutingTable(self.node_id, K)
        
        # データストア
        self.storage: Dict[bytes, ValueEntry] = {}
        self.replication_cache: Dict[bytes, ValueEntry] = {}
        
        # 進行中のクエリ
        self._pending_queries: Dict[str, asyncio.Future] = {}
        
        # サーバ
        self._server: Optional[web.Server] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        
        # バックグラウンドタスク
        self._refresh_task: Optional[asyncio.Task] = None
        self._replicate_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # 起動状態
        self._started = False
        self._started_at: Optional[datetime] = None
        
        logger.info(f"DHTNode initialized: {self.node_id}")
    
    async def start(self) -> None:
        """DHTノードを起動"""
        if self._started:
            return
        
        # HTTPサーバを開始
        app = web.Application()
        app.router.add_get("/dht/ping", self._handle_ping)
        app.router.add_get("/dht/store", self._handle_store)
        app.router.add_get("/dht/find_node", self._handle_find_node)
        app.router.add_get("/dht/find_value", self._handle_find_value)
        app.router.add_get("/dht/stats", self._handle_stats)
        app.router.add_get("/dht/nodes", self._handle_nodes)
        
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        
        # 実際のポートを取得
        self.port = self._site._server.sockets[0].getsockname()[1]
        
        self._started = True
        self._started_at = datetime.utcnow()
        
        # バックグラウンドタスクを開始
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        self._replicate_task = asyncio.create_task(self._replicate_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # ブートストラップ
        if self.bootstrap_nodes:
            await self._bootstrap()
        
        logger.info(f"DHTNode started: {self.endpoint}")
    
    async def stop(self) -> None:
        """DHTノードを停止"""
        if not self._started:
            return
        
        self._started = False
        
        # タスクをキャンセル
        for task in [self._refresh_task, self._replicate_task, self._cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # サーバを停止
        if self._runner:
            await self._runner.cleanup()
        
        # データを保存
        await self._save_data()
        
        logger.info("DHTNode stopped")
    
    @property
    def endpoint(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    async def _bootstrap(self) -> None:
        """ブートストラップノードに接続"""
        logger.info(f"Bootstrapping with {len(self.bootstrap_nodes)} nodes")
        
        for node_info in self.bootstrap_nodes:
            try:
                host = node_info.get("host", "localhost")
                port = node_info.get("port", 8000)
                
                # PINGで接続確認
                if await self._ping_node(host, port):
                    # 自分自身を紹介
                    await self._announce_to_node(host, port)
                    
                    # 自分の近傍ノードを探索
                    await self._find_node_nearby()
                
            except Exception as e:
                logger.debug(f"Bootstrap failed for {node_info}: {e}")
    
    async def _ping_node(self, host: str, port: int) -> bool:
        """ノードにPING"""
        try:
            timeout = ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"http://{host}:{port}/dht/ping"
                params = {
                    "node_id": self.node_id.hex,
                    "host": self.host,
                    "port": self.port
                }
                async with session.get(url, params=params) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.debug(f"PING failed to {host}:{port}: {e}")
            return False
    
    async def _announce_to_node(self, host: str, port: int) -> bool:
        """自分の存在をノードに告知"""
        try:
            timeout = ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"http://{host}:{port}/dht/find_node"
                params = {
                    "target_id": self.node_id.hex,
                    "sender_id": self.node_id.hex,
                    "sender_host": self.host,
                    "sender_port": self.port
                }
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # 返ってきたノードを追加
                        for node_data in data.get("nodes", []):
                            await self._add_node_from_dict(node_data)
                        return True
        except Exception as e:
            logger.debug(f"Announce failed: {e}")
        return False
    
    async def _find_node_nearby(self) -> None:
        """自分の近傍ノードを探索"""
        await self.find_node(self.node_id)
    
    async def _add_node_from_dict(self, data: Dict) -> bool:
        """辞書からノードを追加"""
        try:
            node = NodeInfo.from_dict(data)
            return self.routing_table.add_node(node)
        except Exception as e:
            logger.debug(f"Failed to add node: {e}")
            return False
    
    # ===== HTTP Handlers =====
    
    async def _handle_ping(self, request: web.Request) -> web.Response:
        """PINGリクエストを処理"""
        try:
            params = request.query
            node_id_hex = params.get("node_id")
            host = params.get("host")
            port = int(params.get("port", 0))
            
            if node_id_hex and host and port:
                node = NodeInfo(
                    node_id=NodeID.from_hex(node_id_hex),
                    host=host,
                    port=port
                )
                self.routing_table.add_node(node)
            
            return web.json_response({
                "status": "ok",
                "node_id": self.node_id.hex,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)
    
    async def _handle_store(self, request: web.Request) -> web.Response:
        """STOREリクエストを処理"""
        try:
            params = request.query
            key_hex = params.get("key")
            value_hex = params.get("value")
            publisher_id_hex = params.get("publisher_id")
            
            if not key_hex or not value_hex:
                return web.json_response({"error": "Missing key or value"}, status=400)
            
            key = bytes.fromhex(key_hex)
            value = bytes.fromhex(value_hex)
            publisher_id = NodeID.from_hex(publisher_id_hex) if publisher_id_hex else None
            
            # 値を保存
            entry = ValueEntry(
                key=key,
                value=value,
                publisher_id=publisher_id
            )
            self.storage[key] = entry
            
            return web.json_response({
                "status": "stored",
                "key": key_hex
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)
    
    async def _handle_find_node(self, request: web.Request) -> web.Response:
        """FIND_NODEリクエストを処理"""
        try:
            params = request.query
            target_id_hex = params.get("target_id")
            sender_id_hex = params.get("sender_id")
            sender_host = params.get("sender_host")
            sender_port = params.get("sender_port")
            
            if not target_id_hex:
                return web.json_response({"error": "Missing target_id"}, status=400)
            
            # 送信者を追加
            if sender_id_hex and sender_host and sender_port:
                sender = NodeInfo(
                    node_id=NodeID.from_hex(sender_id_hex),
                    host=sender_host,
                    port=int(sender_port)
                )
                self.routing_table.add_node(sender)
            
            target_id = NodeID.from_hex(target_id_hex)
            closest = self.routing_table.find_closest(target_id, K)
            
            return web.json_response({
                "nodes": [n.to_dict() for n in closest]
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)
    
    async def _handle_find_value(self, request: web.Request) -> web.Response:
        """FIND_VALUEリクエストを処理"""
        try:
            params = request.query
            key_hex = params.get("key")
            sender_id_hex = params.get("sender_id")
            sender_host = params.get("sender_host")
            sender_port = params.get("sender_port")
            
            if not key_hex:
                return web.json_response({"error": "Missing key"}, status=400)
            
            # 送信者を追加
            if sender_id_hex and sender_host and sender_port:
                sender = NodeInfo(
                    node_id=NodeID.from_hex(sender_id_hex),
                    host=sender_host,
                    port=int(sender_port)
                )
                self.routing_table.add_node(sender)
            
            key = bytes.fromhex(key_hex)
            
            # ローカルに値があれば返す
            if key in self.storage:
                entry = self.storage[key]
                if not entry.is_expired():
                    return web.json_response({
                        "value": entry.value.hex(),
                        "publisher_id": entry.publisher_id.hex if entry.publisher_id else None,
                        "timestamp": entry.timestamp.isoformat()
                    })
            
            # なければ近傍ノードを返す
            target_id = NodeID(key)
            closest = self.routing_table.find_closest(target_id, K)
            
            return web.json_response({
                "nodes": [n.to_dict() for n in closest]
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)
    
    async def _handle_stats(self, request: web.Request) -> web.Response:
        """統計情報を返す"""
        return web.json_response(self.get_stats())
    
    async def _handle_nodes(self, request: web.Request) -> web.Response:
        """全ノードを返す"""
        nodes = self.routing_table.get_all_nodes()
        return web.json_response({
            "nodes": [n.to_dict() for n in nodes]
        })
    
    # ===== Public API =====
    
    async def ping(self, node: NodeInfo) -> bool:
        """ノードにPINGを送信"""
        return await self._ping_node(node.host, node.port)
    
    async def store(self, key: bytes, value: bytes, publisher_id: Optional[NodeID] = None) -> bool:
        """値をDHTに保存"""
        target_id = NodeID(key)
        
        # ローカルに保存
        entry = ValueEntry(key=key, value=value, publisher_id=publisher_id)
        self.storage[key] = entry
        
        # 近傍ノードに複製
        closest = self.routing_table.find_closest(target_id, REPLICATION_FACTOR)
        
        success_count = 1  # 自分自身
        for node in closest:
            if node.node_id == self.node_id:
                continue
            
            try:
                timeout = ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    url = f"{node.endpoint}/dht/store"
                    params = {
                        "key": key.hex(),
                        "value": value.hex(),
                        "publisher_id": (publisher_id or self.node_id).hex
                    }
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            success_count += 1
            except Exception as e:
                logger.debug(f"Store to {node} failed: {e}")
        
        return success_count >= REPLICATION_FACTOR
    
    async def find_node(self, target_id: NodeID) -> List[NodeInfo]:
        """ノードを探索"""
        # まずローカルから検索
        closest = self.routing_table.find_closest(target_id, ALPHA)
        
        # リモートノードに問い合わせ
        queried: Set[str] = {self.node_id.hex}
        to_query = [n for n in closest if n.node_id.hex not in queried][:ALPHA]
        
        while to_query:
            tasks = []
            for node in to_query:
                queried.add(node.node_id.hex)
                tasks.append(self._query_find_node(node, target_id))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            new_nodes = []
            for result in results:
                if isinstance(result, list):
                    for node_data in result:
                        node = NodeInfo.from_dict(node_data)
                        self.routing_table.add_node(node)
                        if node.node_id not in [n.node_id for n in closest]:
                            new_nodes.append(node)
            
            closest = self.routing_table.find_closest(target_id, K)
            
            # 次の問い合わせ先を決定
            to_query = []
            for node in closest:
                if node.node_id.hex not in queried:
                    to_query.append(node)
                    if len(to_query) >= ALPHA:
                        break
        
        return closest
    
    async def _query_find_node(self, node: NodeInfo, target_id: NodeID) -> List[Dict]:
        """FIND_NODEを実行"""
        try:
            timeout = ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{node.endpoint}/dht/find_node"
                params = {
                    "target_id": target_id.hex,
                    "sender_id": self.node_id.hex,
                    "sender_host": self.host,
                    "sender_port": self.port
                }
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("nodes", [])
        except Exception as e:
            logger.debug(f"FIND_NODE query failed: {e}")
        return []
    
    async def find_value(self, key: bytes) -> Optional[bytes]:
        """値を検索"""
        # ローカルにあれば返す
        if key in self.storage:
            entry = self.storage[key]
            if not entry.is_expired():
                return entry.value
        
        # リモートに問い合わせ
        target_id = NodeID(key)
        closest = await self.find_node(target_id)
        
        for node in closest[:ALPHA]:
            if node.node_id == self.node_id:
                continue
            
            try:
                timeout = ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    url = f"{node.endpoint}/dht/find_value"
                    params = {
                        "key": key.hex(),
                        "sender_id": self.node_id.hex,
                        "sender_host": self.host,
                        "sender_port": self.port
                    }
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if "value" in data:
                                return bytes.fromhex(data["value"])
            except Exception as e:
                logger.debug(f"FIND_VALUE query failed: {e}")
        
        return None
    
    # ===== Background Tasks =====
    
    async def _refresh_loop(self) -> None:
        """ルーティングテーブルを定期的にリフレッシュ"""
        while self._started:
            try:
                await asyncio.sleep(BUCKET_REFRESH_INTERVAL)
                
                # 各バケットをリフレッシュ
                for i, bucket in enumerate(self.routing_table.buckets):
                    if (datetime.utcnow() - bucket.last_updated).seconds > BUCKET_REFRESH_INTERVAL:
                        # ランダムなIDを生成して探索
                        random_id = NodeID()
                        await self.find_node(random_id)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refresh error: {e}")
    
    async def _replicate_loop(self) -> None:
        """データを定期的に複製"""
        while self._started:
            try:
                await asyncio.sleep(3600)  # 1時間ごと
                
                for key, entry in list(self.storage.items()):
                    if entry.publisher_id == self.node_id:
                        await self.store(key, entry.value, self.node_id)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Replicate error: {e}")
    
    async def _cleanup_loop(self) -> None:
        """期限切れデータを削除"""
        while self._started:
            try:
                await asyncio.sleep(3600)  # 1時間ごと
                
                expired_keys = [
                    key for key, entry in self.storage.items()
                    if entry.is_expired()
                ]
                
                for key in expired_keys:
                    del self.storage[key]
                    logger.info(f"Removed expired entry: {key.hex()[:16]}...")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _save_data(self) -> None:
        """データを保存"""
        try:
            data = {
                "storage": {k.hex(): v.to_dict() for k, v in self.storage.items()},
                "nodes": [n.to_dict() for n in self.routing_table.get_all_nodes()]
            }
            
            filepath = self.data_dir / f"node_{self.node_id.hex[:16]}.json"
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved data to {filepath}")
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    # ===== Utility =====
    
    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        uptime = None
        if self._started_at:
            uptime = (datetime.utcnow() - self._started_at).total_seconds()
        
        return {
            "node_id": self.node_id.hex,
            "endpoint": self.endpoint,
            "started": self._started,
            "uptime_seconds": uptime,
            "routing_table": self.routing_table.get_stats(),
            "storage_entries": len(self.storage),
            "bootstrap_nodes": len(self.bootstrap_nodes)
        }
    
    def get_local_value(self, key: bytes) -> Optional[bytes]:
        """ローカルに保存された値を取得"""
        if key in self.storage:
            entry = self.storage[key]
            if not entry.is_expired():
                return entry.value
        return None


class DHTClient:
    """DHTクライアント（読み取り専用アクセス）"""
    
    def __init__(self, bootstrap_nodes: List[Dict]):
        self.bootstrap_nodes = bootstrap_nodes
        self._nodes: List[NodeInfo] = []
    
    async def connect(self) -> bool:
        """ブートストラップノードに接続"""
        for node_info in self.bootstrap_nodes:
            try:
                host = node_info.get("host", "localhost")
                port = node_info.get("port", 8000)
                
                timeout = ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    url = f"http://{host}:{port}/dht/stats"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            self._nodes.append(NodeInfo(
                                node_id=NodeID.from_hex(data["node_id"]),
                                host=host,
                                port=port
                            ))
            except Exception as e:
                logger.debug(f"Connect failed: {e}")
        
        return len(self._nodes) > 0
    
    async def get(self, key: bytes) -> Optional[bytes]:
        """値を取得"""
        key_hex = key.hex()
        
        for node in self._nodes:
            try:
                timeout = ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    url = f"{node.endpoint}/dht/find_value"
                    params = {"key": key_hex}
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if "value" in data:
                                return bytes.fromhex(data["value"])
                            elif "nodes" in data:
                                # さらに探索
                                for node_data in data["nodes"]:
                                    value = await self._query_value(node_data, key_hex)
                                    if value:
                                        return value
            except Exception as e:
                logger.debug(f"Get failed: {e}")
        
        return None
    
    async def _query_value(self, node_data: Dict, key_hex: str) -> Optional[bytes]:
        """特定ノードに値を問い合わせ"""
        try:
            host = node_data["host"]
            port = node_data["port"]
            
            timeout = ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"http://{host}:{port}/dht/find_value"
                params = {"key": key_hex}
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "value" in data:
                            return bytes.fromhex(data["value"])
        except Exception:
            pass
        return None


# グローバルインスタンス
_node_instances: Dict[str, DHTNode] = {}


def get_dht_node(node_id: Optional[str] = None) -> Optional[DHTNode]:
    """DHTノードインスタンスを取得"""
    if node_id:
        return _node_instances.get(node_id)
    return next(iter(_node_instances.values()), None)


def create_dht_node(
    host: str = "0.0.0.0",
    port: int = 0,
    node_id: Optional[NodeID] = None,
    bootstrap_nodes: Optional[List[Dict]] = None
) -> DHTNode:
    """DHTノードを作成"""
    node = DHTNode(
        host=host,
        port=port,
        node_id=node_id,
        bootstrap_nodes=bootstrap_nodes
    )
    _node_instances[node.node_id.hex] = node
    return node


async def main():
    """テスト実行"""
    import sys
    
    # ノード1を作成
    node1 = create_dht_node(
        host="127.0.0.1",
        port=8001,
        node_id=NodeID("test-node-1")
    )
    await node1.start()
    print(f"Node1 started: {node1.endpoint}")
    
    # ノード2を作成（ノード1をブートストラップ）
    node2 = create_dht_node(
        host="127.0.0.1",
        port=8002,
        node_id=NodeID("test-node-2"),
        bootstrap_nodes=[{"host": "127.0.0.1", "port": 8001}]
    )
    await node2.start()
    print(f"Node2 started: {node2.endpoint}")
    
    # 少し待つ
    await asyncio.sleep(2)
    
    # 値を保存
    test_key = b"test-key"
    test_value = b"Hello DHT!"
    
    print(f"\nStoring value...")
    success = await node2.store(test_key, test_value)
    print(f"Store result: {success}")
    
    # 値を取得
    print(f"\nRetrieving value...")
    retrieved = await node1.find_value(test_key)
    print(f"Retrieved: {retrieved}")
    
    # 統計を表示
    print(f"\nNode1 stats:")
    print(json.dumps(node1.get_stats(), indent=2))
    print(f"\nNode2 stats:")
    print(json.dumps(node2.get_stats(), indent=2))
    
    # 停止
    await node1.stop()
    await node2.stop()


if __name__ == "__main__":
    asyncio.run(main())
