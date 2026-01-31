#!/usr/bin/env python3
"""
SessionManager unit tests
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from services.session_manager import SessionManager, SessionState
from services.crypto import SecureSession


@pytest.fixture
async def session_manager():
    """Create a session manager for testing"""
    sm = SessionManager(default_ttl_minutes=5)
    await sm.start()
    yield sm
    await sm.stop()


@pytest.mark.asyncio
async def test_create_session():
    """Test session creation"""
    sm = SessionManager()
    await sm.start()
    
    try:
        session = await sm.create_session("entity_a", "entity_b")
        
        assert session is not None
        assert session.session_id is not None
        assert session.sender_id == "entity_a"
        assert session.recipient_id == "entity_b"
        assert len(session.session_id) == 36  # UUID v4 length
        
        # Check session is tracked
        active = await sm.list_active_sessions()
        assert session.session_id in active
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_reuse_existing_session():
    """Test that existing active session is reused"""
    sm = SessionManager()
    await sm.start()
    
    try:
        session1 = await sm.create_session("entity_a", "entity_b")
        session2 = await sm.create_session("entity_a", "entity_b")
        
        # Should return same session
        assert session1.session_id == session2.session_id
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_get_session():
    """Test session retrieval"""
    sm = SessionManager()
    await sm.start()
    
    try:
        session = await sm.create_session("entity_a", "entity_b")
        
        # Get by ID
        retrieved = await sm.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        
        # Non-existent session
        not_found = await sm.get_session("non-existent-uuid")
        assert not_found is None
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_sequence_validation():
    """Test sequence number validation"""
    sm = SessionManager()
    await sm.start()
    
    try:
        session = await sm.create_session("entity_a", "entity_b")
        
        # First message should be sequence 1
        is_valid = await sm.validate_and_update_sequence(session.session_id, 1)
        assert is_valid is True
        
        # Next should be 2
        is_valid = await sm.validate_and_update_sequence(session.session_id, 2)
        assert is_valid is True
        
        # Duplicate should fail
        with pytest.raises(Exception) as exc_info:
            await sm.validate_and_update_sequence(session.session_id, 2)
        assert "Duplicate" in str(exc_info.value) or "SEQUENCE_ERROR" in str(exc_info.value)
        
        # Out of order (gap too large)
        with pytest.raises(Exception) as exc_info:
            await sm.validate_and_update_sequence(session.session_id, 200)
        assert "gap" in str(exc_info.value).lower() or "SEQUENCE_ERROR" in str(exc_info.value)
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_get_next_sequence():
    """Test getting next sequence for sending"""
    sm = SessionManager()
    await sm.start()
    
    try:
        session_id, seq = await sm.get_next_sequence("entity_a", "entity_b")
        assert seq == 1
        
        session_id2, seq2 = await sm.get_next_sequence("entity_a", "entity_b")
        assert seq2 == 2
        assert session_id == session_id2  # Same session
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_terminate_session():
    """Test session termination"""
    sm = SessionManager()
    await sm.start()
    
    try:
        session = await sm.create_session("entity_a", "entity_b")
        
        # Terminate
        result = await sm.terminate_session(session.session_id)
        assert result is True
        
        # Should no longer be active
        retrieved = await sm.get_session(session.session_id)
        assert retrieved is None
        
        # Terminate non-existent
        result = await sm.terminate_session("non-existent")
        assert result is False
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_get_stats():
    """Test statistics collection"""
    sm = SessionManager()
    await sm.start()
    
    try:
        # Initial stats
        stats = await sm.get_stats()
        assert stats["sessions_created"] == 0
        assert stats["active_sessions"] == 0
        
        # Create session
        await sm.create_session("entity_a", "entity_b")
        
        stats = await sm.get_stats()
        assert stats["sessions_created"] == 1
        assert stats["active_sessions"] == 1
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_cleanup_expired():
    """Test expired session cleanup"""
    # Short TTL for testing
    sm = SessionManager(default_ttl_minutes=0)
    await sm.start()
    
    try:
        session = await sm.create_session("entity_a", "entity_b")
        
        # Wait for expiration
        await asyncio.sleep(0.1)
        
        # Should be expired
        retrieved = await sm.get_session(session.session_id)
        assert retrieved is None
        
        stats = await sm.get_stats()
        assert stats["sessions_expired"] >= 0
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_multiple_peers():
    """Test multiple peer sessions isolation"""
    sm = SessionManager()
    await sm.start()
    
    try:
        # Create sessions with different peers
        session_ab = await sm.create_session("entity_a", "entity_b")
        session_ac = await sm.create_session("entity_a", "entity_c")
        session_ba = await sm.create_session("entity_b", "entity_a")
        
        # Should be different sessions
        assert session_ab.session_id != session_ac.session_id
        assert session_ab.session_id != session_ba.session_id
        
        # Each should be retrievable
        assert await sm.get_session(session_ab.session_id) is not None
        assert await sm.get_session(session_ac.session_id) is not None
        assert await sm.get_session(session_ba.session_id) is not None
        
        # Sequences should be independent
        _, seq_ab1 = await sm.get_next_sequence("entity_a", "entity_b")
        _, seq_ac1 = await sm.get_next_sequence("entity_a", "entity_c")
        _, seq_ab2 = await sm.get_next_sequence("entity_a", "entity_b")
        
        assert seq_ab1 == 1
        assert seq_ac1 == 1
        assert seq_ab2 == 2
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_get_peer_session():
    """Test getting session by peer pair"""
    sm = SessionManager()
    await sm.start()
    
    try:
        # Create session
        session = await sm.create_session("entity_a", "entity_b")
        
        # Get by peer pair
        retrieved = await sm.get_peer_session("entity_a", "entity_b")
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        
        # Non-existent peer pair
        not_found = await sm.get_peer_session("entity_a", "entity_c")
        assert not_found is None
        
        # Reverse direction should be different session
        reverse = await sm.get_peer_session("entity_b", "entity_a")
        assert reverse is None  # Not created yet
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_list_active_sessions():
    """Test listing all active sessions"""
    sm = SessionManager()
    await sm.start()
    
    try:
        # Initially empty
        active = await sm.list_active_sessions()
        assert len(active) == 0
        
        # Create sessions
        session_ab = await sm.create_session("entity_a", "entity_b")
        session_ac = await sm.create_session("entity_a", "entity_c")
        
        # List should contain both
        active = await sm.list_active_sessions()
        assert len(active) == 2
        assert session_ab.session_id in active
        assert session_ac.session_id in active
        
        # Check session info structure
        info = active[session_ab.session_id]
        assert info["sender_id"] == "entity_a"
        assert info["recipient_id"] == "entity_b"
        assert "expected_sequence" in info
        assert "expires_at" in info
        assert "established_at" in info
        
        # After termination, should not appear
        await sm.terminate_session(session_ab.session_id)
        active = await sm.list_active_sessions()
        assert len(active) == 1
        assert session_ab.session_id not in active
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_session_expiration_access():
    """Test accessing expired session returns None"""
    sm = SessionManager(default_ttl_minutes=0)
    await sm.start()
    
    try:
        session = await sm.create_session("entity_a", "entity_b")
        session_id = session.session_id
        
        # Wait for expiration
        await asyncio.sleep(0.1)
        
        # get_session should return None
        retrieved = await sm.get_session(session_id)
        assert retrieved is None
        
        # get_peer_session should also return None
        peer_session = await sm.get_peer_session("entity_a", "entity_b")
        assert peer_session is None
        
        # list_active_sessions should not include it
        active = await sm.list_active_sessions()
        assert session_id not in active
    finally:
        await sm.stop()


@pytest.mark.asyncio
async def test_invalid_session_operations():
    """Test operations with invalid session IDs"""
    sm = SessionManager()
    await sm.start()
    
    try:
        # Terminate non-existent
        result = await sm.terminate_session("invalid-uuid")
        assert result is False
        
        # Get non-existent
        retrieved = await sm.get_session("invalid-uuid")
        assert retrieved is None
        
        # Validate sequence for non-existent
        with pytest.raises(Exception) as exc_info:
            await sm.validate_and_update_sequence("invalid-uuid", 1)
        assert "Session" in str(exc_info.value)
    finally:
        await sm.stop()


# ============================================================================
# S4-1: SessionInfo ライフサイクル（作成/再利用/期限切れ/削除）
# ============================================================================
class TestS4_1_SessionLifecycle:
    """S4-1: SessionInfoライフサイクル（作成/再利用/期限切れ/削除）"""
    
    @pytest.mark.asyncio
    async def test_s4_1_session_create_reuse_terminate(self):
        """セッション作成→再利用→削除のフロー"""
        sm = SessionManager(default_ttl_minutes=60)
        await sm.start()
        
        try:
            # 作成
            session1 = await sm.create_session("entity-a", "entity-b")
            assert session1.session_id is not None
            
            # 再利用（同じID）
            session2 = await sm.create_session("entity-a", "entity-b")
            assert session2.session_id == session1.session_id
            
            # 削除
            terminated = await sm.terminate_session(session1.session_id)
            assert terminated is True
            
            # 削除後はNone
            retrieved = await sm.get_session(session1.session_id)
            assert retrieved is None
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_1_session_expire_after_ttl(self):
        """TTL経過後の期限切れ"""
        sm = SessionManager(default_ttl_minutes=0.001)
        await sm.start()
        
        try:
            session = await sm.create_session("entity-a", "entity-b")
            session_id = session.session_id
            
            # TTL経過前は有効
            assert await sm.get_session(session_id) is not None
            
            # TTL経過
            await asyncio.sleep(0.15)
            
            # 期限切れ後はNone
            assert await sm.get_session(session_id) is None
        finally:
            await sm.stop()


# ============================================================================
# S4-2: タイムアウト処理（TTL経過後None返却）
# ============================================================================
class TestS4_2_TimeoutHandling:
    """S4-2: タイムアウト処理（TTL経過後None返却）"""
    
    @pytest.mark.asyncio
    async def test_s4_2_get_session_returns_none_after_ttl(self):
        """TTL経過後、get_sessionがNoneを返す"""
        sm = SessionManager(default_ttl_minutes=0.001)
        await sm.start()
        
        try:
            session = await sm.create_session("entity-a", "entity-b")
            
            # 有効時
            assert await sm.get_session(session.session_id) is not None
            
            # TTL経過
            await asyncio.sleep(0.15)
            
            # None返却
            assert await sm.get_session(session.session_id) is None
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_2_get_peer_session_returns_none_after_ttl(self):
        """TTL経過後、get_peer_sessionもNoneを返す"""
        sm = SessionManager(default_ttl_minutes=0.001)
        await sm.start()
        
        try:
            await sm.create_session("entity-a", "entity-b")
            
            # 有効時
            assert await sm.get_peer_session("entity-a", "entity-b") is not None
            
            # TTL経過
            await asyncio.sleep(0.15)
            
            # None返却
            assert await sm.get_peer_session("entity-a", "entity-b") is None
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_2_validate_sequence_raises_after_ttl(self):
        """TTL経過後、validate_and_update_sequenceが例外を投げる"""
        from services.crypto import ProtocolError, SESSION_EXPIRED
        
        sm = SessionManager(default_ttl_minutes=0.001)
        await sm.start()
        
        try:
            session = await sm.create_session("entity-a", "entity-b")
            session_id = session.session_id
            
            # TTL経過
            await asyncio.sleep(0.15)
            
            # 例外発生
            with pytest.raises(ProtocolError) as exc_info:
                await sm.validate_and_update_sequence(session_id, 1)
            assert exc_info.value.code == SESSION_EXPIRED
        finally:
            await sm.stop()


# ============================================================================
# S4-3: パージ処理（期限切れ自動削除）
# ============================================================================
class TestS4_3_PurgeProcessing:
    """S4-3: パージ処理（期限切れ自動削除）"""
    
    @pytest.mark.asyncio
    async def test_s4_3_cleanup_expired_removes_sessions(self):
        """_cleanup_expiredが期限切れセッションを削除"""
        sm = SessionManager(default_ttl_minutes=0.001)
        await sm.start()
        
        try:
            session = await sm.create_session("entity-a", "entity-b")
            session_id = session.session_id
            
            # 期限切れまで待つ
            await asyncio.sleep(0.15)
            
            # クリーンアップ実行
            await sm._cleanup_expired()
            
            # 削除されている
            assert await sm.get_session(session_id) is None
            
            # 統計情報も更新
            stats = await sm.get_stats()
            assert stats["sessions_expired"] >= 1
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_3_list_active_excludes_expired(self):
        """list_active_sessionsが期限切れを除外"""
        sm = SessionManager(default_ttl_minutes=0.001)
        await sm.start()
        
        try:
            session = await sm.create_session("entity-a", "entity-b")
            
            # 有効時は含まれる
            active1 = await sm.list_active_sessions()
            assert session.session_id in active1
            
            # 期限切れ
            await asyncio.sleep(0.15)
            
            # 除外されている
            active2 = await sm.list_active_sessions()
            assert session.session_id not in active2
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_3_auto_cleanup_loop(self):
        """自動クリーンアップループが実行される"""
        sm = SessionManager(default_ttl_minutes=0.001, auto_cleanup_interval_sec=0.05)
        await sm.start()
        
        try:
            await sm.create_session("entity-a", "entity-b")
            
            # クリーンアップが実行されるまで待つ
            await asyncio.sleep(0.2)
            
            # 統計情報が更新されている
            stats = await sm.get_stats()
            assert stats["sessions_expired"] >= 1
        finally:
            await sm.stop()


# ============================================================================
# S4-4: 並行管理（複数セッション/シーケンス検証）
# ============================================================================
class TestS4_4_ConcurrentManagement:
    """S4-4: 並行管理（複数セッション/シーケンス検証）"""
    
    @pytest.mark.asyncio
    async def test_s4_4_multiple_sessions_concurrent(self):
        """複数セッションの並行管理"""
        sm = SessionManager(default_ttl_minutes=60)
        await sm.start()
        
        try:
            # 複数セッション作成
            sessions = []
            for i in range(5):
                session = await sm.create_session(f"entity-{i}", "entity-b")
                sessions.append(session)
            
            # すべて取得できる
            active = await sm.list_active_sessions()
            assert len(active) == 5
            
            for session in sessions:
                assert session.session_id in active
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_4_sequence_validation_in_order(self):
        """正しい順序のシーケンス番号検証"""
        sm = SessionManager(default_ttl_minutes=60)
        await sm.start()
        
        try:
            session = await sm.create_session("entity-a", "entity-b")
            sid = session.session_id
            
            # 順序通りに検証
            assert await sm.validate_and_update_sequence(sid, 1) is True
            assert await sm.validate_and_update_sequence(sid, 2) is True
            assert await sm.validate_and_update_sequence(sid, 3) is True
            
            # 統計情報更新
            stats = await sm.get_stats()
            assert stats["messages_ordered"] == 3
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_4_sequence_validation_duplicate(self):
        """重複シーケンス番号はエラー"""
        from services.crypto import ProtocolError, SEQUENCE_ERROR
        
        sm = SessionManager(default_ttl_minutes=60)
        await sm.start()
        
        try:
            session = await sm.create_session("entity-a", "entity-b")
            sid = session.session_id
            
            await sm.validate_and_update_sequence(sid, 1)
            
            # 重複はエラー
            with pytest.raises(ProtocolError) as exc_info:
                await sm.validate_and_update_sequence(sid, 1)
            assert exc_info.value.code == SEQUENCE_ERROR
            
            # 統計情報
            stats = await sm.get_stats()
            assert stats["sequence_errors"] >= 1
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_4_sequence_validation_gap_accepted(self):
        """許容範囲内のギャップは許容"""
        sm = SessionManager(default_ttl_minutes=60, max_sequence_gap=100)
        await sm.start()
        
        try:
            session = await sm.create_session("entity-a", "entity-b")
            sid = session.session_id
            
            # ギャップありで検証
            result = await sm.validate_and_update_sequence(sid, 10)
            assert result is True
            
            # 期待シーケンスが更新されている
            active = await sm.list_active_sessions()
            assert active[sid]["expected_sequence"] == 11
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_4_sequence_validation_gap_too_large(self):
        """最大ギャップを超えるとエラー"""
        from services.crypto import ProtocolError, SEQUENCE_ERROR
        
        sm = SessionManager(default_ttl_minutes=60, max_sequence_gap=10)
        await sm.start()
        
        try:
            session = await sm.create_session("entity-a", "entity-b")
            sid = session.session_id
            
            # 大きすぎるギャップはエラー
            with pytest.raises(ProtocolError) as exc_info:
                await sm.validate_and_update_sequence(sid, 20)
            assert exc_info.value.code == SEQUENCE_ERROR
        finally:
            await sm.stop()
    
    @pytest.mark.asyncio
    async def test_s4_4_get_next_sequence_increments(self):
        """get_next_sequenceのインクリメント"""
        sm = SessionManager(default_ttl_minutes=60)
        await sm.start()
        
        try:
            sid1, seq1 = await sm.get_next_sequence("entity-a", "entity-b")
            sid2, seq2 = await sm.get_next_sequence("entity-a", "entity-b")
            sid3, seq3 = await sm.get_next_sequence("entity-a", "entity-b")
            
            # 同じセッション
            assert sid1 == sid2 == sid3
            
            # シーケンスインクリメント
            assert seq1 == 1
            assert seq2 == 2
            assert seq3 == 3
        finally:
            await sm.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
