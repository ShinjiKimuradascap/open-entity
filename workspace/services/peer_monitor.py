#!/usr/bin/env python3
"""
Peer Monitor Service

AIエンティティ間の自動ピア発見、接続監視、自動再接続機能を提供するモジュール。

機能:
- 自動ピア発見: レジストリから定期的にピアを検索・自動追加
- 接続状態監視: 各ピアへの定期的なヘルスチェック（30秒間隔）
- 自動再接続: 接続が切れたピアへの再接続ロジック（指数バックオフ）
- 接続統計: 各ピアの接続成功率、レイテンシ、最後の通信時刻を記録
- 接続イベント通知: 接続/切断/再接続時のコールバック機能

Protocol v0.3対応:
- Ed25519署名によるメッセージ認証
- リプレイ攻撃防止（タイムスタンプ+ノンス）
"""

import asyncio
import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Callable, Awaitable, Dict, List, Any, Set, Tuple

import aiohttp
from aiohttp import ClientTimeout, ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 型エイリアス
ConnectionEventHandler = Callable[[str, str, Optional[dict]], Awaitable[None]]
PeerDiscoveryHandler = Callable[[str, str, Optional[str]], Awaitable[bool]]


class ConnectionEvent(Enum):
    """接続イベントタイプ"""
    CONNECTED = "connected"           # ピアが接続された
    DISCONNECTED = "disconnected"     # ピアが切断された
    RECONNECTED = "reconnected"       # ピアが再接続された
    DISCOVERED = "discovered"         # 新しいピアが発見された
    HEALTH_CHECK_FAILED = "health_check_failed"  # ヘルスチェック失敗
    HEALTH_CHECK_PASSED = "health_check_passed"  # ヘルスチェック成功


@dataclass
class ConnectionMetrics:
    """接続メトリクス"""
    entity_id: str
    address: str
    
    # 接続試行統計
    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    
    # レイテンシ統計（ミリ秒）
    latencies_ms: List[float] = field(default_factory=list)
    avg_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    
    # 接続状態
    is_connected: bool = False
    last_connected_at: Optional[datetime] = None
    last_disconnected_at: Optional[datetime] = None
    last_health_check_at: Optional[datetime] = None
    
    # 再接続統計
    reconnect_attempts: int = 0
    last_reconnect_at: Optional[datetime] = None
    
    # エラー履歴（最新10件）
    error_history: List[Tuple[datetime, str]] = field(default_factory=list)
    
    def record_latency(self, latency_ms: float) -> None:
        """レイテンシを記録"""
        self.latencies_ms.append(latency_ms)
        # 最新100件のみ保持
        if len(self.latencies_ms) > 100:
            self.latencies_ms = self.latencies_ms[-100:]
        
        # 統計を再計算
        self.avg_latency_ms = sum(self.latencies_ms) / len(self.latencies_ms)
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
    
    def record_success(self) -> None:
        """成功を記録"""
        self.total_attempts += 1
        self.successful_attempts += 1
        self.is_connected = True
        self.last_connected_at = datetime.now(timezone.utc)
    
    def record_failure(self, error: str) -> None:
        """失敗を記録"""
        self.total_attempts += 1
        self.failed_attempts += 1
        
        # エラー履歴に追加
        now = datetime.now(timezone.utc)
        self.error_history.append((now, error))
        # 最新10件のみ保持
        if len(self.error_history) > 10:
            self.error_history = self.error_history[-10:]
        
        # 接続状態を更新
        if self.is_connected:
            self.is_connected = False
            self.last_disconnected_at = now
    
    def record_reconnect_attempt(self) -> None:
        """再接続試行を記録"""
        self.reconnect_attempts += 1
        self.last_reconnect_at = datetime.now(timezone.utc)
    
    def get_success_rate(self) -> float:
        """接続成功率を取得（0.0〜1.0）"""
        if self.total_attempts == 0:
            return 0.0
        return self.successful_attempts / self.total_attempts
    
    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "entity_id": self.entity_id,
            "address": self.address,
            "success_rate": round(self.get_success_rate(), 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2) if self.latencies_ms else None,
            "min_latency_ms": round(self.min_latency_ms, 2) if self.latencies_ms else None,
            "max_latency_ms": round(self.max_latency_ms, 2) if self.latencies_ms else None,
            "is_connected": self.is_connected,
            "total_attempts": self.total_attempts,
            "successful_attempts": self.successful_attempts,
            "failed_attempts": self.failed_attempts,
            "reconnect_attempts": self.reconnect_attempts,
            "last_connected_at": self.last_connected_at.isoformat() if self.last_connected_at else None,
            "last_disconnected_at": self.last_disconnected_at.isoformat() if self.last_disconnected_at else None,
            "last_health_check_at": self.last_health_check_at.isoformat() if self.last_health_check_at else None,
            "recent_errors": [(t.isoformat(), e) for t, e in self.error_history[-5:]]
        }


class ExponentialBackoff:
    """指数バックオフリトライ間隔計算
    
    リトライ間隔: 1s, 2s, 4s, 8s... (最大60秒)
    jitter（±20%）を追加
    """
    
    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter_percent: float = 0.2
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter_percent = jitter_percent
    
    def get_delay(self, retry_count: int) -> float:
        """リトライ回数に基づく遅延時間を計算（jitter含む）"""
        delay = self.initial_delay * (self.multiplier ** retry_count)
        delay = min(delay, self.max_delay)
        jitter = delay * self.jitter_percent * (2 * random.random() - 1)
        delay += jitter
        return max(0.1, delay)


class PeerMonitor:
    """ピア接続監視サービス
    
    自動ピア発見、接続監視、自動再接続を管理する。
    
    Attributes:
        entity_id: このサービスのエンティティID
        registry: サービスレジストリ（オプション）
        health_check_interval: ヘルスチェック間隔（秒、デフォルト: 30）
        discovery_interval: ピア発見間隔（秒、デフォルト: 60）
        health_check_timeout: ヘルスチェックタイムアウト（秒、デフォルト: 5）
        max_reconnect_delay: 最大再接続遅延（秒、デフォルト: 60）
        max_reconnect_attempts: 最大再接続試行回数（デフォルト: 無制限）
    """
    
    def __init__(
        self,
        entity_id: str,
        registry: Optional[Any] = None,
        health_check_interval: float = 30.0,
        discovery_interval: float = 60.0,
        health_check_timeout: float = 5.0,
        max_reconnect_delay: float = 60.0,
        max_reconnect_attempts: int = 0  # 0 = 無制限
    ):
        self.entity_id = entity_id
        self.registry = registry
        self.health_check_interval = health_check_interval
        self.discovery_interval = discovery_interval
        self.health_check_timeout = health_check_timeout
        self.max_reconnect_delay = max_reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        
        # ピア管理
        self._monitored_peers: Dict[str, str] = {}  # entity_id -> address
        self._peer_metrics: Dict[str, ConnectionMetrics] = {}
        self._peer_reconnect_counts: Dict[str, int] = {}
        self._backoff = ExponentialBackoff(max_delay=max_reconnect_delay)
        
        # イベントハンドラ
        self._event_handlers: Dict[ConnectionEvent, List[ConnectionEventHandler]] = defaultdict(list)
        self._discovery_handler: Optional[PeerDiscoveryHandler] = None
        
        # タスク
        self._health_check_task: Optional[asyncio.Task] = None
        self._discovery_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 再接続対象キュー
        self._reconnect_queue: asyncio.Queue = asyncio.Queue()
        
        # 手動追加されたピア（発見で削除されないように）
        self._manual_peers: Set[str] = set()
    
    def set_discovery_handler(self, handler: PeerDiscoveryHandler) -> None:
        """新しいピア発見時のハンドラを設定
        
        Args:
            handler: (entity_id, address, public_key_hex) -> bool 形式のハンドラ
        """
        self._discovery_handler = handler
    
    def register_event_handler(
        self, 
        event: ConnectionEvent, 
        handler: ConnectionEventHandler
    ) -> None:
        """接続イベントハンドラを登録
        
        Args:
            event: イベントタイプ
            handler: ハンドラ関数 (entity_id, event_type, data) -> None
        """
        self._event_handlers[event].append(handler)
        logger.debug(f"Registered handler for {event.value}")
    
    def unregister_event_handler(
        self, 
        event: ConnectionEvent, 
        handler: ConnectionEventHandler
    ) -> None:
        """接続イベントハンドラを解除"""
        if handler in self._event_handlers[event]:
            self._event_handlers[event].remove(handler)
    
    async def _emit_event(
        self, 
        event: ConnectionEvent, 
        entity_id: str, 
        data: Optional[dict] = None
    ) -> None:
        """イベントを発行"""
        logger.debug(f"Emitting {event.value} for {entity_id}")
        
        for handler in self._event_handlers[event]:
            try:
                await handler(entity_id, event.value, data)
            except Exception as e:
                logger.error(f"Error in event handler for {event.value}: {e}")
    
    def add_peer(
        self, 
        entity_id: str, 
        address: str, 
        is_manual: bool = True,
        public_key_hex: Optional[str] = None
    ) -> None:
        """ピアを監視対象に追加
        
        Args:
            entity_id: ピアのエンティティID
            address: ピアのアドレス
            is_manual: 手動追加かどうか（発見による追加の場合はFalse）
            public_key_hex: ピアの公開鍵（オプション）
        """
        self._monitored_peers[entity_id] = address
        
        if entity_id not in self._peer_metrics:
            self._peer_metrics[entity_id] = ConnectionMetrics(
                entity_id=entity_id,
                address=address
            )
        else:
            # アドレスが変更された場合は更新
            self._peer_metrics[entity_id].address = address
        
        if is_manual:
            self._manual_peers.add(entity_id)
        
        # 再接続カウントをリセット
        self._peer_reconnect_counts[entity_id] = 0
        
        logger.info(f"Added peer to monitor: {entity_id} at {address}")
    
    def remove_peer(self, entity_id: str) -> bool:
        """ピアを監視対象から削除
        
        Args:
            entity_id: 削除するピアのエンティティID
            
        Returns:
            削除成功ならTrue
        """
        if entity_id not in self._monitored_peers:
            return False
        
        del self._monitored_peers[entity_id]
        self._manual_peers.discard(entity_id)
        
        # メトリクスは保持（履歴のため）
        if entity_id in self._peer_metrics:
            self._peer_metrics[entity_id].is_connected = False
        
        logger.info(f"Removed peer from monitor: {entity_id}")
        return True
    
    def get_peer_metrics(self, entity_id: Optional[str] = None) -> Optional[dict]:
        """ピアの接続メトリクスを取得
        
        Args:
            entity_id: ピアID（省略時は全ピア）
            
        Returns:
            メトリクス辞書
        """
        if entity_id:
            metrics = self._peer_metrics.get(entity_id)
            return metrics.to_dict() if metrics else None
        
        return {
            eid: metrics.to_dict()
            for eid, metrics in self._peer_metrics.items()
        }
    
    def get_connected_peers(self) -> List[str]:
        """接続中のピアリストを取得"""
        return [
            eid for eid, metrics in self._peer_metrics.items()
            if metrics.is_connected
        ]
    
    def get_disconnected_peers(self) -> List[str]:
        """切断中のピアリストを取得"""
        return [
            eid for eid in self._monitored_peers.keys()
            if eid in self._peer_metrics and not self._peer_metrics[eid].is_connected
        ]
    
    async def start(self) -> None:
        """監視を開始"""
        if self._running:
            return
        
        self._running = True
        
        # ヘルスチェックタスク
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        # ピア発見タスク（レジストリがある場合）
        if self.registry:
            self._discovery_task = asyncio.create_task(self._discovery_loop())
        
        # 再接続タスク
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        
        logger.info(f"PeerMonitor started for {self.entity_id}")
    
    async def stop(self) -> None:
        """監視を停止"""
        if not self._running:
            return
        
        self._running = False
        
        # タスクをキャンセル
        tasks = [
            self._health_check_task,
            self._discovery_task,
            self._reconnect_task
        ]
        
        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._health_check_task = None
        self._discovery_task = None
        self._reconnect_task = None
        
        logger.info(f"PeerMonitor stopped for {self.entity_id}")
    
    async def _health_check_loop(self) -> None:
        """ヘルスチェックループ"""
        while self._running:
            try:
                await self._check_all_peers()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(5.0)
    
    async def _check_all_peers(self) -> None:
        """全ピアのヘルスチェック"""
        if not self._monitored_peers:
            return
        
        tasks = [
            self._check_peer_health(entity_id, address)
            for entity_id, address in self._monitored_peers.items()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_peer_health(self, entity_id: str, address: str) -> None:
        """ピアのヘルスチェックを実行"""
        metrics = self._peer_metrics.get(entity_id)
        if not metrics:
            return
        
        url = f"{address}/health"
        timeout = ClientTimeout(total=self.health_check_timeout, connect=2)
        start_time = datetime.now(timezone.utc)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    if response.status == 200:
                        # ヘルスチェック成功
                        was_connected = metrics.is_connected
                        metrics.record_latency(elapsed_ms)
                        metrics.record_success()
                        metrics.last_health_check_at = datetime.now(timezone.utc)
                        
                        if not was_connected:
                            # 再接続成功
                            await self._emit_event(
                                ConnectionEvent.RECONNECTED, 
                                entity_id,
                                {"latency_ms": elapsed_ms, "address": address}
                            )
                        else:
                            await self._emit_event(
                                ConnectionEvent.HEALTH_CHECK_PASSED,
                                entity_id,
                                {"latency_ms": elapsed_ms}
                            )
                    else:
                        # ヘルスチェック失敗（HTTPエラー）
                        metrics.record_failure(f"HTTP {response.status}")
                        await self._emit_event(
                            ConnectionEvent.HEALTH_CHECK_FAILED,
                            entity_id,
                            {"error": f"HTTP {response.status}", "address": address}
                        )
                        
                        # 再接続キューに追加
                        if metrics.is_connected:
                            await self._reconnect_queue.put(entity_id)
                            await self._emit_event(
                                ConnectionEvent.DISCONNECTED,
                                entity_id,
                                {"reason": f"HTTP {response.status}"}
                            )
                        
        except asyncio.TimeoutError:
            elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            metrics.record_failure("Timeout")
            await self._emit_event(
                ConnectionEvent.HEALTH_CHECK_FAILED,
                entity_id,
                {"error": "Timeout", "elapsed_ms": elapsed_ms}
            )
            
            if metrics.is_connected:
                await self._reconnect_queue.put(entity_id)
                await self._emit_event(
                    ConnectionEvent.DISCONNECTED,
                    entity_id,
                    {"reason": "Timeout"}
                )
                
        except ClientError as e:
            metrics.record_failure(f"Connection error: {str(e)}")
            await self._emit_event(
                ConnectionEvent.HEALTH_CHECK_FAILED,
                entity_id,
                {"error": str(e), "address": address}
            )
            
            if metrics.is_connected:
                await self._reconnect_queue.put(entity_id)
                await self._emit_event(
                    ConnectionEvent.DISCONNECTED,
                    entity_id,
                    {"reason": str(e)}
                )
                
        except Exception as e:
            metrics.record_failure(f"Unexpected error: {str(e)}")
            logger.error(f"Health check error for {entity_id}: {e}")
    
    async def _discovery_loop(self) -> None:
        """ピア発見ループ"""
        while self._running:
            try:
                await self._discover_peers()
                await asyncio.sleep(self.discovery_interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(5.0)
    
    async def _discover_peers(self) -> None:
        """レジストリからピアを発見"""
        if not self.registry:
            return
        
        try:
            # レジストリから全サービスを取得
            services = self.registry.list_services()
            
            for service in services:
                entity_id = service.get("entity_id") or service.get("id")
                endpoint = service.get("endpoint") or service.get("address")
                public_key = service.get("public_key")
                
                # 自分自身はスキップ
                if entity_id == self.entity_id:
                    continue
                
                # 既存のピアはスキップ
                if entity_id in self._monitored_peers:
                    # アドレスが変更されている場合は更新
                    if endpoint and self._monitored_peers[entity_id] != endpoint:
                        logger.info(f"Updating peer address: {entity_id} -> {endpoint}")
                        self._monitored_peers[entity_id] = endpoint
                        if entity_id in self._peer_metrics:
                            self._peer_metrics[entity_id].address = endpoint
                    continue
                
                # ハンドラが設定されていれば確認
                if self._discovery_handler:
                    should_add = await self._discovery_handler(entity_id, endpoint, public_key)
                    if not should_add:
                        continue
                
                # ピアを追加
                self.add_peer(entity_id, endpoint, is_manual=False, public_key_hex=public_key)
                
                await self._emit_event(
                    ConnectionEvent.DISCOVERED,
                    entity_id,
                    {"address": endpoint, "public_key": public_key}
                )
                
                # 初期ヘルスチェック
                await self._check_peer_health(entity_id, endpoint)
                
        except Exception as e:
            logger.error(f"Error discovering peers: {e}")
    
    async def _reconnect_loop(self) -> None:
        """再接続ループ"""
        while self._running:
            try:
                entity_id = await self._reconnect_queue.get()
                
                # 最大試行回数チェック
                if self.max_reconnect_attempts > 0:
                    count = self._peer_reconnect_counts.get(entity_id, 0)
                    if count >= self.max_reconnect_attempts:
                        logger.warning(
                            f"Max reconnect attempts reached for {entity_id}, "
                            f"removing from monitor"
                        )
                        self.remove_peer(entity_id)
                        continue
                
                # 指数バックオフで待機
                retry_count = self._peer_reconnect_counts.get(entity_id, 0)
                delay = self._backoff.get_delay(retry_count)
                
                logger.info(
                    f"Scheduling reconnect for {entity_id} "
                    f"(attempt {retry_count + 1}, delay {delay:.1f}s)"
                )
                
                await asyncio.sleep(delay)
                
                # 再接続実行
                if entity_id in self._monitored_peers:
                    await self._attempt_reconnect(entity_id)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in reconnect loop: {e}")
    
    async def _attempt_reconnect(self, entity_id: str) -> None:
        """再接続を試行"""
        if entity_id not in self._monitored_peers:
            return
        
        address = self._monitored_peers[entity_id]
        metrics = self._peer_metrics.get(entity_id)
        
        if metrics:
            metrics.record_reconnect_attempt()
        
        # 再接続カウントを増加
        self._peer_reconnect_counts[entity_id] = self._peer_reconnect_counts.get(entity_id, 0) + 1
        
        # ヘルスチェックを実行
        await self._check_peer_health(entity_id, address)
        
        # 接続に成功した場合、カウントをリセット
        if metrics and metrics.is_connected:
            self._peer_reconnect_counts[entity_id] = 0
    
    async def force_reconnect(self, entity_id: str) -> bool:
        """強制的に再接続を試行
        
        Args:
            entity_id: 再接続するピアID
            
        Returns:
            成功したかどうか
        """
        if entity_id not in self._monitored_peers:
            logger.error(f"Cannot reconnect unknown peer: {entity_id}")
            return False
        
        self._peer_reconnect_counts[entity_id] = 0
        await self._attempt_reconnect(entity_id)
        
        metrics = self._peer_metrics.get(entity_id)
        return metrics.is_connected if metrics else False
    
    def get_summary(self) -> dict:
        """監視サマリーを取得"""
        total_peers = len(self._monitored_peers)
        connected = len(self.get_connected_peers())
        disconnected = len(self.get_disconnected_peers())
        
        avg_success_rate = 0.0
        if self._peer_metrics:
            rates = [m.get_success_rate() for m in self._peer_metrics.values()]
            avg_success_rate = sum(rates) / len(rates)
        
        return {
            "entity_id": self.entity_id,
            "total_monitored_peers": total_peers,
            "connected_peers": connected,
            "disconnected_peers": disconnected,
            "average_success_rate": round(avg_success_rate, 4),
            "is_running": self._running,
            "health_check_interval": self.health_check_interval,
            "discovery_interval": self.discovery_interval,
            "manual_peers": len(self._manual_peers),
            "discovered_peers": total_peers - len(self._manual_peers)
        }


# グローバルインスタンス
_monitor: Optional[PeerMonitor] = None


def init_monitor(
    entity_id: str,
    registry: Optional[Any] = None,
    **kwargs
) -> PeerMonitor:
    """モニターを初期化
    
    Args:
        entity_id: エンティティID
        registry: サービスレジストリ
        **kwargs: PeerMonitorのその他のパラメータ
        
    Returns:
        PeerMonitorインスタンス
    """
    global _monitor
    _monitor = PeerMonitor(entity_id, registry, **kwargs)
    return _monitor


def get_monitor() -> Optional[PeerMonitor]:
    """グローバルモニターインスタンスを取得"""
    return _monitor


if __name__ == "__main__":
    # テスト実行
    import sys
    sys.path.insert(0, "..")
    
    async def run_tests():
        print("=" * 60)
        print("Peer Monitor Test")
        print("=" * 60)
        
        # 1. 初期化テスト
        print("\n1. Initialization Test")
        monitor = PeerMonitor(
            entity_id="test-entity",
            health_check_interval=5.0,
            discovery_interval=10.0
        )
        
        # イベントハンドラを登録
        async def on_event(entity_id: str, event: str, data: Optional[dict]):
            print(f"   [EVENT] {event}: {entity_id}")
        
        for event in ConnectionEvent:
            monitor.register_event_handler(event, on_event)
        
        print(f"   Monitor initialized: {monitor.entity_id}")
        print(f"   Health check interval: {monitor.health_check_interval}s")
        
        # 2. ピア追加テスト
        print("\n2. Add Peers Test")
        monitor.add_peer("peer-1", "http://localhost:8001", is_manual=True)
        monitor.add_peer("peer-2", "http://localhost:8002", is_manual=True)
        print(f"   Added 2 peers")
        
        # 3. メトリクス記録テスト
        print("\n3. Metrics Recording Test")
        metrics = monitor._peer_metrics["peer-1"]
        metrics.record_latency(15.5)
        metrics.record_latency(12.3)
        metrics.record_latency(18.7)
        metrics.record_success()
        print(f"   Average latency: {metrics.avg_latency_ms:.2f}ms")
        print(f"   Success rate: {metrics.get_success_rate():.2%}")
        
        # 4. 辞書変換テスト
        print("\n4. Metrics to Dict Test")
        data = metrics.to_dict()
        print(f"   Entity ID: {data['entity_id']}")
        print(f"   Address: {data['address']}")
        print(f"   Connected: {data['is_connected']}")
        print(f"   Avg latency: {data['avg_latency_ms']}ms")
        
        # 5. サマリー取得テスト
        print("\n5. Summary Test")
        summary = monitor.get_summary()
        print(f"   Total peers: {summary['total_monitored_peers']}")
        print(f"   Connected: {summary['connected_peers']}")
        print(f"   Disconnected: {summary['disconnected_peers']}")
        
        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)
        
        return monitor
    
    # テスト実行
    monitor = asyncio.run(run_tests())
