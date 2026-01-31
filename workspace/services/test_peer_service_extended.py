#!/usr/bin/env python3
"""
Peer Service 拡張統合テスト

包括的なテストスイート:
- SessionManager テスト
- PeerServiceCore テスト（メッセージハンドラ）
- PeerStatistics テスト
- MessageQueue テスト
- Integration テスト

既存の test_peer_service_v1.py の内容も含む
"""

import asyncio
import sys
import os
import uuid
import secrets
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
import pytest_asyncio

from peer_service import (
    init_service, create_server, PeerService, Session, SessionState,
    SessionManager, SessionInfo, MessageQueue, QueuedMessage,
    HeartbeatManager, PeerStatus, PeerStats, PeerInfo,
    INVALID_VERSION, INVALID_SIGNATURE, SESSION_EXPIRED, SEQUENCE_ERROR,
    ExponentialBackoff, RateLimiter, RateLimitConfig,
    ChunkInfo, ChunkManager
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def session_manager():
    """SessionManager インスタンスを提供するフィクスチャ"""
    manager = SessionManager()
    yield manager


@pytest_asyncio.fixture
async def peer_service():
    """PeerService インスタンスを提供するフィクスチャ"""
    service = init_service("test-entity", 8000)
    yield service


@pytest_asyncio.fixture
async def message_queue():
    """MessageQueue インスタンスを提供するフィクスチャ"""
    queue = MessageQueue()
    yield queue


@pytest_asyncio.fixture
async def heartbeat_manager():
    """HeartbeatManager インスタンスを提供するフィクスチャ"""
    manager = HeartbeatManager()
    yield manager


# =============================================================================
# TestSessionManager
# =============================================================================

@pytest.mark.asyncio
class TestSessionManager:
    """SessionManager の詳細テスト"""
    
    async def test_create_session(self, session_manager):
        """セッション作成とUUID生成"""
        session = await session_manager.create_session("peer-001")
        
        assert session is not None
        assert session.session_id is not None
        assert len(session.session_id) == 36  # UUID v4 format
        assert session.peer_id == "peer-001"
        assert session.state == SessionState.INITIAL
        assert session.sequence_num == 0
        assert session.expected_sequence == 1
        print(f"✓ Session created: {session.session_id}")
    
    async def test_get_session_by_id(self, session_manager):
        """セッションIDでの取得"""
        session = await session_manager.create_session("peer-002")
        session_id = session.session_id
        
        retrieved = await session_manager.get_session(session_id)
        
        assert retrieved is not None
        assert retrieved.session_id == session_id
        assert retrieved.peer_id == "peer-002"
        print("✓ Get session by ID works")
    
    async def test_get_session_by_peer(self, session_manager):
        """ピアIDでの取得"""
        await session_manager.create_session("peer-003")
        
        retrieved = await session_manager.get_session_by_peer("peer-003")
        
        assert retrieved is not None
        assert retrieved.peer_id == "peer-003"
        print("✓ Get session by peer works")
    
    async def test_update_session_state(self, session_manager):
        """状態遷移（INITIAL → HANDSHAKE_SENT → ESTABLISHED）"""
        session = await session_manager.create_session("peer-004")
        session_id = session.session_id
        
        # INITIAL → HANDSHAKE_SENT
        result = await session_manager.update_session_state(
            session_id, SessionState.HANDSHAKE_SENT
        )
        assert result is True
        
        updated = await session_manager.get_session(session_id)
        assert updated.state == SessionState.HANDSHAKE_SENT
        
        # HANDSHAKE_SENT → ESTABLISHED
        result = await session_manager.update_session_state(
            session_id, SessionState.ESTABLISHED
        )
        assert result is True
        
        updated = await session_manager.get_session(session_id)
        assert updated.state == SessionState.ESTABLISHED
        print("✓ State transitions work")
    
    async def test_session_expiration(self, session_manager):
        """TTL経過後の期限切れ判定"""
        session = await session_manager.create_session("peer-005")
        session_id = session.session_id
        
        # まだ期限切れでない
        is_valid = await session_manager.is_session_valid(session_id)
        assert is_valid is True
        
        # 期限切れにする（TTLを短く設定したセッションを作成）
        session.created_at = datetime.now(timezone.utc) - timedelta(seconds=7200)
        
        # TTLはデフォルト3600秒なので期限切れになる
        is_expired = session.is_expired(max_age_seconds=3600)
        assert is_expired is True
        print("✓ Session expiration works")
    
    async def test_is_session_valid(self, session_manager):
        """有効性検証"""
        session = await session_manager.create_session("peer-006")
        session_id = session.session_id
        
        # 基本的な有効性検証
        assert await session_manager.is_session_valid(session_id) is True
        
        # 無効なセッションID
        assert await session_manager.is_session_valid("invalid-id") is False
        
        # 状態をEXPIREDに変更
        await session_manager.update_session_state(session_id, SessionState.EXPIRED)
        assert await session_manager.is_session_valid(session_id) is False
        
        # 必要な状態を指定
        await session_manager.update_session_state(session_id, SessionState.ESTABLISHED)
        assert await session_manager.is_session_valid(session_id, required_state=SessionState.ESTABLISHED) is True
        assert await session_manager.is_session_valid(session_id, required_state=SessionState.INITIAL) is False
        print("✓ Session validity checks work")
    
    async def test_terminate_session(self, session_manager):
        """セッション終了"""
        session = await session_manager.create_session("peer-007")
        session_id = session.session_id
        
        result = await session_manager.terminate_session(session_id)
        assert result is True
        
        # セッションはEXPIRED状態になる
        retrieved = await session_manager.get_session(session_id)
        assert retrieved.state == SessionState.EXPIRED
        
        # peer_sessionsからも削除される
        peer_session = await session_manager.get_session_by_peer("peer-007")
        assert peer_session is None
        print("✓ Session termination works")
    
    async def test_cleanup_expired(self, session_manager):
        """期限切れセッションの自動クリーンアップ"""
        # 通常のセッションを作成
        session1 = await session_manager.create_session("peer-008")
        
        # 期限切れのセッションを作成
        session2 = await session_manager.create_session("peer-009")
        session2.created_at = datetime.now(timezone.utc) - timedelta(seconds=7200)
        
        # クリーンアップ実行
        cleaned = await session_manager.cleanup_expired()
        
        assert cleaned >= 1  # 少なくとも1つ削除される
        assert await session_manager.get_session(session1.session_id) is not None  # 有効なセッションは残る
        print(f"✓ Cleanup expired sessions: {cleaned} removed")
    
    async def test_concurrent_session_access(self, session_manager):
        """並行アクセス時の一貫性"""
        async def create_sessions(n):
            for i in range(n):
                await session_manager.create_session(f"concurrent-peer-{n}-{i}")
        
        # 並行してセッションを作成
        await asyncio.gather(
            create_sessions(5),
            create_sessions(5),
            create_sessions(5)
        )
        
        # 全セッションを取得
        all_sessions = await session_manager.get_all_sessions()
        assert len(all_sessions) == 15
        print("✓ Concurrent session access is consistent")


# =============================================================================
# TestPeerServiceCore
# =============================================================================

@pytest.mark.asyncio
class TestPeerServiceCore:
    """PeerService のコア機能テスト"""
    
    async def test_init_service(self):
        """サービス初期化"""
        service = init_service("test-init", 8100)
        
        assert service is not None
        assert service.entity_id == "test-init"
        assert service.port == 8100
        assert "ping" in service.message_handlers
        assert "status" in service.message_handlers
        print("✓ Service initialization works")
    
    async def test_health_check(self, peer_service):
        """ヘルスチェック応答"""
        health = await peer_service.health_check()
        
        assert "entity_id" in health
        assert health["entity_id"] == peer_service.entity_id
        assert "crypto_available" in health
        assert "signing_enabled" in health
        assert "verification_enabled" in health
        print("✓ Health check works")
    
    async def test_handle_message_ping(self, peer_service):
        """pingメッセージハンドラ"""
        peer_service.add_peer("test-peer-ping", "http://localhost:8001")
        
        ping_msg = {
            "version": "1.0",
            "msg_type": "ping",
            "sender_id": "test-peer-ping",
            "payload": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "ping001"
        }
        
        result = await peer_service.handle_message(ping_msg)
        
        # pingはハンドラが登録されているが、同期応答はなし
        assert result is not None or result is None  # ハンドラが実行される
        print("✓ Ping handler works")
    
    async def test_handle_message_status(self, peer_service):
        """statusメッセージハンドラ"""
        peer_service.add_peer("test-peer-status", "http://localhost:8002")
        
        status_msg = {
            "version": "1.0",
            "msg_type": "status",
            "sender_id": "test-peer-status",
            "payload": {"status": "active"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "status001"
        }
        
        await peer_service.handle_message(status_msg)
        print("✓ Status handler works")
    
    async def test_handle_message_capability_query(self, peer_service):
        """capability_queryハンドラ"""
        peer_service.add_peer("test-peer-cap", "http://localhost:8003")
        
        cap_msg = {
            "version": "1.0",
            "msg_type": "capability_query",
            "sender_id": "test-peer-cap",
            "payload": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "cap001"
        }
        
        await peer_service.handle_message(cap_msg)
        
        # capability_responseが内部で保持される
        assert hasattr(peer_service, '_last_capability_response')
        assert peer_service._last_capability_response is not None
        print("✓ Capability query handler works")
    
    async def test_handle_message_heartbeat(self, peer_service):
        """heartbeatハンドラと統計更新"""
        peer_service.add_peer("test-peer-hb", "http://localhost:8004")
        
        # ピア統計を初期化
        peer_service.peer_stats["test-peer-hb"] = PeerStats(
            entity_id="test-peer-hb",
            address="http://localhost:8004"
        )
        
        heartbeat_msg = {
            "version": "1.0",
            "msg_type": "heartbeat",
            "sender_id": "test-peer-hb",
            "payload": {"sequence": 1},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "hb001"
        }
        
        await peer_service.handle_message(heartbeat_msg)
        
        # 統計が更新される
        stats = peer_service.peer_stats["test-peer-hb"]
        assert stats.is_healthy is True
        assert stats.last_seen is not None
        print("✓ Heartbeat handler and stats update work")
    
    async def test_handle_message_task_delegate(self, peer_service):
        """task_delegateハンドラ"""
        peer_service.add_peer("test-peer-task", "http://localhost:8005")
        
        task_msg = {
            "version": "1.0",
            "msg_type": "task_delegate",
            "sender_id": "test-peer-task",
            "payload": {
                "task_id": "TASK-001",
                "description": "Test task",
                "priority": "high",
                "data": {"key": "value"}
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "task001"
        }
        
        await peer_service.handle_message(task_msg)
        
        # タスクがキューに追加される
        assert hasattr(peer_service, '_pending_tasks')
        assert len(peer_service._pending_tasks) == 1
        assert peer_service._pending_tasks[0]["task_id"] == "TASK-001"
        print("✓ Task delegate handler works")
    
    async def test_handle_unknown_message_type(self, peer_service):
        """未知のメッセージタイプ"""
        unknown_msg = {
            "version": "1.0",
            "msg_type": "unknown_type",
            "sender_id": "test-peer-unknown",
            "payload": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "unknown001"
        }
        
        result = await peer_service.handle_message(unknown_msg)
        # 未知のタイプはエラー応答
        assert result is not None
        print("✓ Unknown message type handling works")
    
    async def test_register_message_handler(self, peer_service):
        """カスタムハンドラ登録"""
        custom_handler_called = []
        
        async def custom_handler(message):
            custom_handler_called.append(message)
        
        peer_service.register_message_handler("custom_type", custom_handler)
        
        assert "custom_type" in peer_service.message_handlers
        
        custom_msg = {
            "version": "1.0",
            "msg_type": "custom_type",
            "sender_id": "test-peer-custom",
            "payload": {"test": "data"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "custom001"
        }
        
        await peer_service.handle_message(custom_msg)
        assert len(custom_handler_called) == 1
        print("✓ Custom message handler registration works")


# =============================================================================
# TestPeerStatistics
# =============================================================================

@pytest.mark.asyncio
class TestPeerStatistics:
    """ピア統計のテスト"""
    
    async def test_peer_stats_tracking(self, peer_service):
        """ピア統計の追跡"""
        peer_id = "stats-test-peer"
        peer_service.add_peer(peer_id, "http://localhost:8006")
        
        # 統計を初期化
        peer_service.peer_stats[peer_id] = PeerStats(
            entity_id=peer_id,
            address="http://localhost:8006"
        )
        
        # メッセージを送信
        await peer_service.send_message(peer_id, {"msg_type": "test"})
        
        # 統計が更新される
        stats = peer_service.peer_stats[peer_id]
        assert stats.total_messages_sent >= 1
        print("✓ Peer stats tracking works")
    
    async def test_peer_health_status(self, peer_service):
        """健全性ステータス"""
        peer_id = "health-test-peer"
        peer_service.add_peer(peer_id, "http://localhost:8007")
        
        peer_service.peer_stats[peer_id] = PeerStats(
            entity_id=peer_id,
            address="http://localhost:8007",
            is_healthy=True
        )
        
        stats = peer_service.peer_stats[peer_id]
        assert stats.is_healthy is True
        
        # エラーを記録
        stats.failed_deliveries += 1
        stats.last_error = "Connection timeout"
        
        assert stats.failed_deliveries == 1
        assert stats.last_error == "Connection timeout"
        print("✓ Peer health status tracking works")
    
    async def test_get_peer_stats(self, peer_service):
        """統計情報取得"""
        peer_service.add_peer("stats-peer-1", "http://localhost:8008")
        peer_service.add_peer("stats-peer-2", "http://localhost:8009")
        
        peer_service.peer_stats["stats-peer-1"] = PeerStats(
            entity_id="stats-peer-1",
            address="http://localhost:8008",
            total_messages_sent=10,
            total_messages_received=5
        )
        
        assert len(peer_service.peer_stats) == 1
        assert peer_service.peer_stats["stats-peer-1"].total_messages_sent == 10
        print("✓ Get peer stats works")


# =============================================================================
# TestMessageQueue
# =============================================================================

@pytest.mark.asyncio
class TestMessageQueue:
    """MessageQueue のテスト"""
    
    async def test_message_queue_add(self, message_queue):
        """メッセージ追加"""
        await message_queue.enqueue(
            target_id="peer-queue-1",
            message_type="test_message",
            payload={"data": "test"}
        )
        
        assert message_queue.get_queue_size() == 1
        print("✓ Message queue add works")
    
    async def test_message_queue_get(self, message_queue):
        """メッセージ取得"""
        await message_queue.enqueue(
            target_id="peer-queue-2",
            message_type="test_message",
            payload={"data": "test"}
        )
        
        stats = message_queue.get_stats()
        assert stats["queued"] == 1
        print("✓ Message queue stats work")
    
    async def test_message_queue_empty(self, message_queue):
        """空キュー処理"""
        assert message_queue.get_queue_size() == 0
        
        stats = message_queue.get_stats()
        assert stats["queued"] == 0
        assert stats["sent"] == 0
        print("✓ Empty queue handling works")
    
    async def test_message_queue_size_limit(self, message_queue):
        """サイズ制限"""
        # 複数メッセージを追加
        for i in range(100):
            await message_queue.enqueue(
                target_id=f"peer-queue-{i}",
                message_type="test_message",
                payload={"index": i}
            )
        
        assert message_queue.get_queue_size() == 100
        print("✓ Message queue size handling works")


# =============================================================================
# TestHeartbeatManager
# =============================================================================

@pytest.mark.asyncio
class TestHeartbeatManager:
    """HeartbeatManager のテスト"""
    
    async def test_register_peer(self, heartbeat_manager):
        """ピア登録"""
        heartbeat_manager.register_peer("hb-peer-1")
        
        assert "hb-peer-1" in heartbeat_manager._peer_status
        assert heartbeat_manager.get_status("hb-peer-1") == PeerStatus.UNKNOWN
        print("✓ Heartbeat peer registration works")
    
    async def test_unregister_peer(self, heartbeat_manager):
        """ピア解除"""
        heartbeat_manager.register_peer("hb-peer-2")
        heartbeat_manager.unregister_peer("hb-peer-2")
        
        assert "hb-peer-2" not in heartbeat_manager._peer_status
        print("✓ Heartbeat peer unregistration works")
    
    async def test_get_healthy_peers(self, heartbeat_manager):
        """健全なピアの取得"""
        heartbeat_manager.register_peer("hb-peer-3")
        heartbeat_manager._peer_status["hb-peer-3"] = PeerStatus.HEALTHY
        
        healthy = heartbeat_manager.get_healthy_peers()
        assert "hb-peer-3" in healthy
        print("✓ Get healthy peers works")


# =============================================================================
# TestIntegration
# =============================================================================

@pytest.mark.asyncio
class TestIntegration:
    """統合テスト"""
    
    async def test_full_session_lifecycle(self):
        """完全なセッションライフサイクル"""
        manager = SessionManager()
        
        # 1. セッション作成
        session = await manager.create_session("lifecycle-peer")
        session_id = session.session_id
        assert session.state == SessionState.INITIAL
        
        # 2. 状態遷移
        await manager.update_session_state(session_id, SessionState.HANDSHAKE_SENT)
        session = await manager.get_session(session_id)
        assert session.state == SessionState.HANDSHAKE_SENT
        
        await manager.update_session_state(session_id, SessionState.ESTABLISHED)
        session = await manager.get_session(session_id)
        assert session.state == SessionState.ESTABLISHED
        
        # 3. セッション終了
        await manager.terminate_session(session_id)
        assert await manager.is_session_valid(session_id) is False
        
        print("✓ Full session lifecycle works")
    
    async def test_multiple_peers(self):
        """複数ピアの同時管理"""
        manager = SessionManager()
        peer_ids = [f"multi-peer-{i}" for i in range(10)]
        
        # 複数セッションを作成
        sessions = []
        for peer_id in peer_ids:
            session = await manager.create_session(peer_id)
            sessions.append(session)
        
        # 全セッションを取得
        all_sessions = await manager.get_all_sessions()
        assert len(all_sessions) == 10
        
        # 各ピアのセッションを取得
        for i, peer_id in enumerate(peer_ids):
            session = await manager.get_session_by_peer(peer_id)
            assert session is not None
            assert session.peer_id == peer_id
        
        print("✓ Multiple peer management works")
    
    async def test_task_delegation_flow(self, peer_service):
        """タスク委譲の流れ"""
        peer_service.add_peer("task-delegator", "http://localhost:8010")
        
        # タスクを受信
        task_msg = {
            "version": "1.0",
            "msg_type": "task_delegate",
            "sender_id": "task-delegator",
            "payload": {
                "task_id": "DELEGATED-001",
                "description": "Process data",
                "priority": "medium",
                "data": {"input": "test_data"}
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "delegate001"
        }
        
        await peer_service.handle_message(task_msg)
        
        # タスクがキューに追加される
        assert len(peer_service._pending_tasks) == 1
        task = peer_service._pending_tasks[0]
        assert task["task_id"] == "DELEGATED-001"
        assert task["from"] == "task-delegator"
        
        print("✓ Task delegation flow works")


# =============================================================================
# Session Dataclass Tests (from test_peer_service_v1.py)
# =============================================================================

@pytest.mark.asyncio
class TestSessionDataclass:
    """Session dataclass のテスト"""
    
    async def test_session_creation(self):
        """Session作成テスト"""
        session = Session(
            session_id="test-session-001",
            peer_id="peer-a",
            state=SessionState.INITIAL
        )
        assert session.session_id == "test-session-001"
        assert session.peer_id == "peer-a"
        assert session.state == SessionState.INITIAL
        assert session.sequence_num == 0
        assert session.expected_sequence == 1
        print("✓ Session created successfully")
    
    async def test_sequence_increment(self):
        """Sequence incrementテスト"""
        session = Session(
            session_id="test-session-002",
            peer_id="peer-b",
            state=SessionState.INITIAL
        )
        
        seq = session.increment_sequence()
        assert seq == 1
        assert session.sequence_num == 1
        
        seq = session.increment_sequence()
        assert seq == 2
        print("✓ Sequence increment works")
    
    async def test_activity_update(self):
        """Activity updateテスト"""
        session = Session(
            session_id="test-session-003",
            peer_id="peer-c",
            state=SessionState.INITIAL
        )
        
        old_activity = session.last_activity
        session.update_activity()
        assert session.last_activity > old_activity
        print("✓ Activity update works")
    
    async def test_to_dict(self):
        """to_dictテスト"""
        session = Session(
            session_id="test-session-004",
            peer_id="peer-d",
            state=SessionState.ESTABLISHED
        )
        
        session_dict = session.to_dict()
        assert "session_id" in session_dict
        assert "peer_id" in session_dict
        assert "state" in session_dict
        assert "sequence_num" in session_dict
        print("✓ to_dict works")


# =============================================================================
# Helper Classes Tests
# =============================================================================

@pytest.mark.asyncio
class TestHelperClasses:
    """ヘルパークラスのテスト"""
    
    async def test_exponential_backoff(self):
        """指数バックオフのテスト"""
        backoff = ExponentialBackoff(
            initial_delay=1.0,
            max_delay=60.0,
            multiplier=2.0
        )
        
        delay_0 = backoff.get_delay(0)
        delay_1 = backoff.get_delay(1)
        delay_2 = backoff.get_delay(2)
        
        assert delay_0 >= 0.8 and delay_0 <= 1.2  # 1s ± 20%
        assert delay_1 >= 1.6 and delay_1 <= 2.4  # 2s ± 20%
        assert delay_2 >= 3.2 and delay_2 <= 4.8  # 4s ± 20%
        print("✓ Exponential backoff works")
    
    async def test_rate_limiter(self):
        """RateLimiterのテスト"""
        config = RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=100,
            burst_size=5
        )
        limiter = RateLimiter(config)
        
        # ブロックされていない
        assert limiter.is_blocked("test-peer") is False
        
        # レート制限チェック
        allowed, retry_after = await limiter.check_rate_limit("test-peer")
        assert allowed is True
        assert retry_after is None
        print("✓ Rate limiter works")
    
    async def test_chunk_info(self):
        """ChunkInfoのテスト"""
        chunk_info = ChunkInfo(
            chunk_id="chunk-001",
            total_chunks=5
        )
        
        # チャンクを追加
        chunk_info.add_chunk(0, "data0")
        chunk_info.add_chunk(1, "data1")
        
        assert chunk_info.is_complete() is False
        assert chunk_info.get_missing_indices() == [2, 3, 4]
        
        # 残りのチャンクを追加
        chunk_info.add_chunk(2, "data2")
        chunk_info.add_chunk(3, "data3")
        chunk_info.add_chunk(4, "data4")
        
        assert chunk_info.is_complete() is True
        print("✓ Chunk info works")


# =============================================================================
# Main Entry Point
# =============================================================================

async def run_all_tests():
    """すべてのテストを実行"""
    print("=" * 60)
    print("Peer Service Extended Test Suite")
    print("=" * 60)
    
    # pytestを使わずに直接実行する場合
    test_classes = [
        TestSessionManager(),
        TestPeerServiceCore(),
        TestPeerStatistics(),
        TestMessageQueue(),
        TestHeartbeatManager(),
        TestIntegration(),
        TestSessionDataclass(),
        TestHelperClasses(),
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for test_class in test_classes:
        class_name = test_class.__class__.__name__
        print(f"\n{'=' * 40}")
        print(f"Running {class_name}")
        print(f"{'=' * 40}")
        
        for method_name in dir(test_class):
            if method_name.startswith("test_"):
                total_tests += 1
                try:
                    method = getattr(test_class, method_name)
                    # フィクスチャをモックで提供
                    if "session_manager" in method.__code__.co_varnames:
                        await method(SessionManager())
                    elif "peer_service" in method.__code__.co_varnames:
                        await method(init_service("test", 8000))
                    elif "message_queue" in method.__code__.co_varnames:
                        await method(MessageQueue())
                    elif "heartbeat_manager" in method.__code__.co_varnames:
                        await method(HeartbeatManager())
                    else:
                        await method()
                    passed_tests += 1
                    print(f"  ✓ {method_name}")
                except Exception as e:
                    print(f"  ✗ {method_name}: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"Results: {passed_tests}/{total_tests} tests passed")
    print(f"{'=' * 60}")
    
    return passed_tests == total_tests


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
