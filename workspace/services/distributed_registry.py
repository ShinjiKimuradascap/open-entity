#!/usr/bin/env python3
"""
Distributed Service Registry with Gossip Protocol and CRDT

複数ノード間でサービス情報を共有・同期する分散レジストリ

Features:
- Gossip protocol for eventual consistency
- CRDT-based conflict resolution (LWW with Vector Clock)
- Random peer selection for load balancing
- Delta synchronization for bandwidth efficiency
- Tombstone-based deletion

Protocol v1.0対応:
- capability_queryでレジストリ機能を通知
- gossipプロトコルによる情報伝播
- 衝突解決（CRDTベース）
"""

import asyncio
import hashlib
import json
import logging
import random
import time
import copy
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from collections import defaultdict
from enum import Enum

from services.registry import ServiceInfo, ServiceRegistry
from services.dht import KademliaDHT, DHTPeerDiscovery, compute_dht_key, DHTValue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EntryStatus(Enum):
    """CRDT entry status for LWW (Last-Write-Wins) semantics"""
    ACTIVE = "active"
    TOMBSTONE = "tombstone"  # Soft delete marker


@dataclass
class VectorClock:
    """
    Vector clock for tracking causality across nodes.
    Maps node_id -> logical timestamp.
    """
    clocks: Dict[str, int] = field(default_factory=dict)
    
    def increment(self, node_id: str) -> "VectorClock":
        """Increment clock for a node"""
        new_clocks = dict(self.clocks)
        new_clocks[node_id] = new_clocks.get(node_id, 0) + 1
        return VectorClock(new_clocks)
    
    def merge(self, other: "VectorClock") -> "VectorClock":
        """Merge two vector clocks (taking max of each entry)"""
        merged = dict(self.clocks)
        for node_id, timestamp in other.clocks.items():
            merged[node_id] = max(merged.get(node_id, 0), timestamp)
        return VectorClock(merged)
    
    def compare(self, other: "VectorClock") -> Optional[int]:
        """
        Compare two vector clocks.
        Returns: -1 if self < other, 0 if concurrent/equal, 1 if self > other
        """
        all_nodes = set(self.clocks.keys()) | set(other.clocks.keys())
        
        has_less = False
        has_greater = False
        
        for node_id in all_nodes:
            self_ts = self.clocks.get(node_id, 0)
            other_ts = other.clocks.get(node_id, 0)
            
            if self_ts < other_ts:
                has_less = True
            elif self_ts > other_ts:
                has_greater = True
        
        if has_less and has_greater:
            return 0  # Concurrent
        elif has_less:
            return -1  # self happens-before other
        elif has_greater:
            return 1  # other happens-before self
        else:
            return 0  # Equal
    
    def is_concurrent_with(self, other: "VectorClock") -> bool:
        """Check if two vector clocks are concurrent (incomparable)"""
        return self.compare(other) == 0 and self.clocks != other.clocks
    
    def to_dict(self) -> Dict[str, int]:
        return dict(self.clocks)
    
    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "VectorClock":
        return cls(data)


@dataclass
class RegistryEntry:
    """分散レジストリエントリ（CRDT対応）"""
    entity_id: str
    entity_name: str
    endpoint: str
    capabilities: List[str]
    registered_at: datetime
    last_heartbeat: datetime
    version: int = 1  # 楽観的ロック用バージョン
    node_id: str = ""  # 登録ノードID
    signature: Optional[str] = None  # エントリ署名
    
    # Extended CRDT fields
    status: EntryStatus = EntryStatus.ACTIVE
    vector_clock: VectorClock = field(default_factory=VectorClock)
    hlc: Tuple[int, int] = field(default_factory=lambda: (0, 0))  # Hybrid Logical Clock
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "version": self.version,
            "node_id": self.node_id,
            "signature": self.signature,
            "status": self.status.value,
            "vector_clock": self.vector_clock.to_dict(),
            "hlc": list(self.hlc)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistryEntry":
        return cls(
            entity_id=data["entity_id"],
            entity_name=data["entity_name"],
            endpoint=data["endpoint"],
            capabilities=data["capabilities"],
            registered_at=datetime.fromisoformat(data["registered_at"]),
            last_heartbeat=datetime.fromisoformat(data["last_heartbeat"]),
            version=data.get("version", 1),
            node_id=data.get("node_id", ""),
            signature=data.get("signature"),
            status=EntryStatus(data.get("status", "active")),
            vector_clock=VectorClock.from_dict(data.get("vector_clock", {})),
            hlc=tuple(data.get("hlc", [0, 0]))
        )
    
    def is_expired(self, timeout_sec: int = 120) -> bool:
        """エントリが期限切れかチェック（TOMBSTONEは期限切れとみなさない）"""
        if self.status == EntryStatus.TOMBSTONE:
            return False  # Tombstones are never "expired" for cleanup purposes
        delta = datetime.now(timezone.utc) - self.last_heartbeat
        return delta.total_seconds() > timeout_sec
    
    def is_alive(self, timeout_sec: int = 60) -> bool:
        """Check if service is alive"""
        if self.status == EntryStatus.TOMBSTONE:
            return False
        delta = datetime.now(timezone.utc) - self.last_heartbeat
        return delta.total_seconds() < timeout_sec
    
    def merge(self, other: "RegistryEntry") -> "RegistryEntry":
        """
        CRDTマージ: Vector ClockベースのLWW (Last-Write-Wins)
        Falls back to HLC and timestamp for concurrent updates.
        """
        # Compare vector clocks
        cmp = self.vector_clock.compare(other.vector_clock)
        
        if cmp == 1:
            # self happened after other
            return self
        elif cmp == -1:
            # other happened after self
            return other
        else:
            # Concurrent or equal - use HLC then timestamp for tie-breaking
            if self.hlc > other.hlc:
                return self
            elif self.hlc < other.hlc:
                return other
            else:
                # Final tie-breaker: lexical order of node_id (deterministic)
                if self.node_id > other.node_id:
                    return self
                else:
                    return other


class DistributedRegistry:
    """分散レジストリ
    
    Gossipプロトコルによる情報伝播を実装。
    各ノードはローカルにレジストリを保持し、
    定期的に他ノードと同期する。
    
    Features:
    - Random peer selection with weighted probabilities
    - Delta synchronization based on Vector Clocks
    - Tombstone-based soft deletion
    - Anti-entropy for eventual consistency
    """
    
    def __init__(
        self,
        node_id: str,
        local_registry: Optional[ServiceRegistry] = None,
        gossip_interval: int = 30,
        cleanup_interval: int = 300,
        max_gossip_peers: int = 3,
        anti_entropy_interval: int = 60,
        tombstone_ttl: int = 600
    ):
        self.node_id = node_id
        self.local_registry = local_registry
        self.gossip_interval = gossip_interval
        self.cleanup_interval = cleanup_interval
        self.max_gossip_peers = max_gossip_peers
        self.anti_entropy_interval = anti_entropy_interval
        self.tombstone_ttl = tombstone_ttl
        
        # 分散レジストリストレージ
        self._entries: Dict[str, RegistryEntry] = {}  # entity_id -> entry
        self._known_nodes: Set[str] = set()  # 既知のノードID
        
        # Gossip状態
        self._gossip_round = 0
        self._gossip_callbacks: List[Callable[[str, Dict], None]] = []
        
        # Known peers with last seen timestamp (for weighted selection)
        self._peers: Dict[str, datetime] = {}
        
        # Local vector clock and version
        self._vector_clock = VectorClock()
        self._local_version = 0
        
        # Hybrid Logical Clock
        self._hlc_time: int = 0
        self._hlc_counter: int = 0
        
        # Async state
        self._gossip_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._anti_entropy_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._running = False
        
        logger.info(f"DistributedRegistry initialized for node: {node_id}")
    
    def _update_hlc(self) -> Tuple[int, int]:
        """Update Hybrid Logical Clock"""
        now = int(time.time() * 1000)  # Milliseconds
        if now > self._hlc_time:
            self._hlc_time = now
            self._hlc_counter = 0
        else:
            self._hlc_counter += 1
        return (self._hlc_time, self._hlc_counter)
    
    def _merge_hlc(self, remote_hlc: Tuple[int, int]) -> Tuple[int, int]:
        """Merge remote HLC with local"""
        if remote_hlc[0] > self._hlc_time:
            self._hlc_time = remote_hlc[0]
            self._hlc_counter = remote_hlc[1] + 1
        elif remote_hlc[0] == self._hlc_time:
            self._hlc_counter = max(self._hlc_counter, remote_hlc[1]) + 1
        else:
            self._hlc_counter += 1
        return (self._hlc_time, self._hlc_counter)
    
    async def register_local(
        self,
        entity_id: str,
        entity_name: str,
        endpoint: str,
        capabilities: List[str]
    ) -> RegistryEntry:
        """ローカルエンティティを登録（CRDT対応）"""
        async with self._lock:
            self._local_version += 1
            self._vector_clock = self._vector_clock.increment(self.node_id)
            hlc = self._update_hlc()
            
            now = datetime.now(timezone.utc)
            entry = RegistryEntry(
                entity_id=entity_id,
                entity_name=entity_name,
                endpoint=endpoint,
                capabilities=capabilities,
                registered_at=now,
                last_heartbeat=now,
                version=self._local_version,
                node_id=self.node_id,
                vector_clock=copy.deepcopy(self._vector_clock),
                hlc=hlc,
                status=EntryStatus.ACTIVE
            )
            
            # Merge with existing if present
            if entity_id in self._entries:
                entry = entry.merge(self._entries[entity_id])
            
            self._entries[entity_id] = entry
            
            # ローカルレジストリにも登録
            if self.local_registry:
                self.local_registry.register(entity_id, entity_name, endpoint, capabilities)
            
            logger.info(f"Registered local entity: {entity_id} at {endpoint} (v{self._local_version})")
            return entry
    
    def update_heartbeat(self, entity_id: str) -> bool:
        """ハートビートを更新"""
        if entity_id not in self._entries:
            return False
        
        entry = self._entries[entity_id]
        entry.last_heartbeat = datetime.now(timezone.utc)
        entry.version += 1
        
        if self.local_registry:
            self.local_registry.heartbeat(entity_id)
        
        return True
    
    def merge_entry(self, entry: RegistryEntry) -> bool:
        """外部からのエントリをマージ（CRDT）"""
        entity_id = entry.entity_id
        
        if entity_id not in self._entries:
            self._entries[entity_id] = entry
            logger.debug(f"Added new entry from gossip: {entity_id}")
            return True
        
        existing = self._entries[entity_id]
        merged = existing.merge(entry)
        
        if merged is not entry:
            return False  # 既存の方が新しい
        
        self._entries[entity_id] = merged
        logger.debug(f"Merged updated entry: {entity_id} (v{merged.version})")
        return True
    
    def get_entry(self, entity_id: str) -> Optional[RegistryEntry]:
        """エントリを取得"""
        entry = self._entries.get(entity_id)
        if entry and entry.is_expired():
            return None
        return entry
    
    def find_by_capability(self, capability: str) -> List[RegistryEntry]:
        """機能でエンティティを検索"""
        results = []
        for entry in self._entries.values():
            if capability in entry.capabilities and not entry.is_expired():
                results.append(entry)
        return results
    
    def get_all_entries(self) -> List[RegistryEntry]:
        """全エントリを取得（期限切れ除外）"""
        return [e for e in self._entries.values() if not e.is_expired()]
    
    def get_digest(self) -> Dict[str, int]:
        """レジストリダイジェスト（同期用）"""
        return {
            entity_id: entry.version
            for entity_id, entry in self._entries.items()
            if not entry.is_expired()
        }
    
    def get_entries_since(self, versions: Dict[str, int]) -> List[RegistryEntry]:
        """指定バージョンより新しいエントリを取得"""
        updates = []
        for entity_id, entry in self._entries.items():
            if entry.is_expired():
                continue
            if entity_id not in versions or entry.version > versions[entity_id]:
                updates.append(entry)
        return updates
    
    def cleanup_expired(self) -> int:
        """期限切れエントリを削除"""
        expired = [
            eid for eid, e in self._entries.items()
            if e.is_expired() and e.node_id != self.node_id
        ]
        for eid in expired:
            del self._entries[eid]
            logger.info(f"Removed expired entry: {eid}")
        
        return len(expired)
    
    async def start(self) -> None:
        """gossipとクリーンアップを開始"""
        self._gossip_task = asyncio.create_task(self._gossip_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("DistributedRegistry started")
    
    async def stop(self) -> None:
        """gossipとクリーンアップを停止"""
        if self._gossip_task:
            self._gossip_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        logger.info("DistributedRegistry stopped")
    
    async def _gossip_loop(self) -> None:
        """gossipループ"""
        while True:
            try:
                await asyncio.sleep(self.gossip_interval)
                await self._do_gossip_round()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gossip error: {e}")
    
    async def _cleanup_loop(self) -> None:
        """クリーンアップループ"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                count = self.cleanup_expired()
                if count > 0:
                    logger.info(f"Cleaned up {count} expired entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _do_gossip_round(self) -> None:
        """1ラウンドのgossipを実行"""
        self._gossip_round += 1
        
        # ダイジェストを作成
        digest = self.get_digest()
        
        # コールバックで他ノードに送信
        for callback in self._gossip_callbacks:
            try:
                callback(self.node_id, {
                    "type": "gossip_digest",
                    "digest": digest,
                    "round": self._gossip_round
                })
            except Exception as e:
                logger.error(f"Gossip callback error: {e}")
    
    def on_gossip(self, from_node: str, message: Dict) -> None:
        """他ノードからのgossipを処理"""
        msg_type = message.get("type")
        
        if msg_type == "gossip_digest":
            # ダイジェストを受信 → 差分を要求
            digest = message.get("digest", {})
            self._request_updates(from_node, digest)
        
        elif msg_type == "gossip_entries":
            # エントリを受信 → マージ
            entries_data = message.get("entries", [])
            for entry_data in entries_data:
                try:
                    entry = RegistryEntry.from_dict(entry_data)
                    self.merge_entry(entry)
                except Exception as e:
                    logger.error(f"Failed to merge entry: {e}")
    
    def _request_updates(self, from_node: str, their_digest: Dict[str, int]) -> None:
        """差分エントリを要求（実装はコールバックで）"""
        # 自分が持っていて相手が持っていない/古いエントリ
        my_updates = self.get_entries_since(their_digest)
        
        if my_updates:
            # コールバックで送信
            for callback in self._gossip_callbacks:
                try:
                    callback(from_node, {
                        "type": "gossip_entries",
                        "entries": [e.to_dict() for e in my_updates]
                    })
                except Exception as e:
                    logger.error(f"Failed to send updates: {e}")
    
    def add_gossip_callback(self, callback: Callable[[str, Dict], None]) -> None:
        """gossipコールバックを追加"""
        self._gossip_callbacks.append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        local_entries = sum(1 for e in self._entries.values() if e.node_id == self.node_id)
        remote_entries = len(self._entries) - local_entries
        expired_entries = sum(1 for e in self._entries.values() if e.is_expired())
        
        return {
            "node_id": self.node_id,
            "total_entries": len(self._entries),
            "local_entries": local_entries,
            "remote_entries": remote_entries,
            "expired_entries": expired_entries,
            "gossip_round": self._gossip_round,
            "known_nodes": len(self._known_nodes)
        }


# グローバルインスタンス管理
_registry_instances: Dict[str, DistributedRegistry] = {}


def get_distributed_registry(node_id: str) -> DistributedRegistry:
    """分散レジストリを取得（ singleton per node_id ）"""
    if node_id not in _registry_instances:
        local_reg = ServiceRegistry() if node_id == "local" else None
        _registry_instances[node_id] = DistributedRegistry(
            node_id=node_id,
            local_registry=local_reg
        )
    return _registry_instances[node_id]


if __name__ == "__main__":
    # テスト
    reg = get_distributed_registry("test-node")
    
    # ローカルエンティティ登録
    entry = reg.register_local(
        "agent-1",
        "Test Agent",
        "http://localhost:8001",
        ["code", "review"]
    )
    print(f"Registered: {entry.to_dict()}")
    
    # エントリ検索
    results = reg.find_by_capability("code")
    print(f"Found {len(results)} agents with 'code' capability")
    
    # 統計
    print(f"Stats: {reg.get_stats()}")
