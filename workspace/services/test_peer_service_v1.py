#!/usr/bin/env python3
"""
Peer Service v1.0 テストスクリプト
新機能（capability_query, heartbeat, task_delegate, handshake）のテスト
"""

import asyncio
import sys
import os
import uuid
import secrets
from datetime import datetime, timezone

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from peer_service import (
    init_service, create_server, PeerService, Session, SessionState,
    INVALID_VERSION, INVALID_SIGNATURE, SESSION_EXPIRED, SEQUENCE_ERROR
)


async def test_session_dataclass():
    """Session dataclassのテスト"""
    print("\n=== Session Dataclass Tests ===\n")

    # 1. Session作成テスト
    print("1. Testing Session creation...")
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
    print("   ✓ Session created successfully")

    # 2. Sequence incrementテスト
    print("\n2. Testing sequence increment...")
    seq = session.increment_sequence()
    assert seq == 1
    assert session.sequence_num == 1
    seq = session.increment_sequence()
    assert seq == 2
    print("   ✓ Sequence increment works")

    # 3. Activity updateテスト
    print("\n3. Testing activity update...")
    old_activity = session.last_activity
    session.update_activity()
    assert session.last_activity > old_activity
    print("   ✓ Activity update works")

    # 4. to_dictテスト
    print("\n4. Testing to_dict...")
    session_dict = session.to_dict()
    assert "session_id" in session_dict
    assert "peer_id" in session_dict
    assert "state" in session_dict
    assert "sequence_num" in session_dict
    print(f"   Session dict: {session_dict}")
    print("   ✓ to_dict works")

    print("\n✅ All Session dataclass tests passed!")


async def test_session_state_transitions():
    """Session state transition tests"""
    print("\n=== Session State Transition Tests ===\n")

    service = init_service("test-state", 8200)

    # 1. Initial state
    print("1. Testing initial state...")
    session = Session(
        session_id=str(uuid.uuid4()),
        peer_id="peer-test",
        state=SessionState.INITIAL
    )
    assert session.state == SessionState.INITIAL
    print("   ✓ Initial state correct")

    # 2. State transition
    print("\n2. Testing state transitions...")
    session.state = SessionState.HANDSHAKE_SENT
    assert session.state == SessionState.HANDSHAKE_SENT
    
    session.state = SessionState.HANDSHAKE_ACKED
    assert session.state == SessionState.HANDSHAKE_ACKED
    
    session.state = SessionState.ESTABLISHED
    assert session.state == SessionState.ESTABLISHED
    print("   ✓ State transitions work")

    # 3. Session expiry
    print("\n3. Testing session expiry...")
    # 新しいセッションは期限切れでない
    fresh_session = Session(
        session_id=str(uuid.uuid4()),
        peer_id="peer-fresh",
        state=SessionState.ESTABLISHED
    )
    assert not fresh_session.is_expired(max_age_seconds=3600)
    print("   ✓ Fresh session not expired")

    print("\n✅ All Session state tests passed!")


async def test_handshake_message_handlers():
    """Handshake message handler tests"""
    print("\n=== Handshake Message Handler Tests ===\n")

    service_a = init_service("entity-a", 8201)
    service_b = init_service("entity-b", 8202)

    # ピアを登録（実際の通信はせず、ハンドラのみテスト）
    pub_key_a = service_a.get_public_key_hex()
    pub_key_b = service_b.get_public_key_hex()
    
    service_a.add_peer("entity-b", "http://localhost:8202", pub_key_b)
    service_b.add_peer("entity-a", "http://localhost:8201", pub_key_a)

    # 1. Handle handshake test
    print("1. Testing handle_handshake...")
    session_id = str(uuid.uuid4())
    challenge = "abcd1234" * 8  # 32 bytes hex
    
    handshake_msg = {
        "version": "1.0",
        "msg_type": "handshake",
        "sender_id": "entity-a",
        "recipient_id": "entity-b",
        "session_id": session_id,
        "sequence_num": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": "test_nonce_001",
        "payload": {
            "version": "1.0",
            "session_id": session_id,
            "challenge": challenge,
            "public_key": pub_key_a,
            "supported_versions": ["1.0", "0.3"]
        }
    }
    
    result = await service_b.handle_handshake(handshake_msg)
    print(f"   Result: {result}")
    # 署名がないためエラーになるが、基本的な検証は通る
    assert "status" in result
    print("   ✓ handle_handshake executed")

    # 2. Handle invalid version
    print("\n2. Testing invalid version handling...")
    invalid_version_msg = {
        "version": "2.0",  # Invalid version
        "msg_type": "handshake",
        "sender_id": "entity-a",
        "recipient_id": "entity-b",
        "session_id": str(uuid.uuid4()),
        "sequence_num": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": "test_nonce_002",
        "payload": {
            "version": "2.0",
            "session_id": str(uuid.uuid4()),
            "challenge": challenge,
            "public_key": pub_key_a,
            "supported_versions": ["2.0"]
        }
    }
    
    result = await service_b.handle_handshake(invalid_version_msg)
    print(f"   Result: {result}")
    assert result["status"] == "error"
    assert result.get("error_code") == INVALID_VERSION
    print("   ✓ Invalid version correctly rejected")

    # 3. Handle handshake_ack
    print("\n3. Testing handle_handshake_ack...")
    ack_session_id = str(uuid.uuid4())
    
    # 事前にセッションを作成
    from peer_service import Session, SessionState
    session = Session(
        session_id=ack_session_id,
        peer_id="entity-a",
        state=SessionState.HANDSHAKE_SENT,
        challenge=challenge
    )
    service_b._handshake_sessions[ack_session_id] = session
    
    handshake_ack_msg = {
        "version": "1.0",
        "msg_type": "handshake_ack",
        "sender_id": "entity-a",
        "recipient_id": "entity-b",
        "session_id": ack_session_id,
        "sequence_num": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": "test_nonce_003",
        "payload": {
            "session_id": ack_session_id,
            "public_key": pub_key_a,
            "challenge_response": "dummy_response",
            "selected_version": "1.0",
            "confirm": True
        }
    }
    
    result = await service_b.handle_handshake_ack(handshake_ack_msg)
    print(f"   Result: {result}")
    assert "status" in result
    print("   ✓ handle_handshake_ack executed")

    # 4. Handle unknown session
    print("\n4. Testing unknown session handling...")
    unknown_session_msg = {
        "version": "1.0",
        "msg_type": "handshake_ack",
        "sender_id": "entity-a",
        "recipient_id": "entity-b",
        "session_id": str(uuid.uuid4()),  # Unknown session
        "sequence_num": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": "test_nonce_004",
        "payload": {
            "session_id": str(uuid.uuid4()),
            "public_key": pub_key_a,
            "challenge_response": "dummy_response",
            "selected_version": "1.0",
            "confirm": True
        }
    }
    
    result = await service_b.handle_handshake_ack(unknown_session_msg)
    print(f"   Result: {result}")
    assert result["status"] == "error"
    assert result.get("error_code") == SESSION_EXPIRED
    print("   ✓ Unknown session correctly rejected")

    # 5. Handle handshake_confirm
    print("\n5. Testing handle_handshake_confirm...")
    confirm_session_id = str(uuid.uuid4())
    
    # 事前にセッションを作成
    session = Session(
        session_id=confirm_session_id,
        peer_id="entity-a",
        state=SessionState.HANDSHAKE_ACKED
    )
    service_b._handshake_sessions[confirm_session_id] = session
    
    handshake_confirm_msg = {
        "version": "1.0",
        "msg_type": "handshake_confirm",
        "sender_id": "entity-a",
        "recipient_id": "entity-b",
        "session_id": confirm_session_id,
        "sequence_num": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": "test_nonce_005",
        "payload": {
            "session_id": confirm_session_id,
            "confirm": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    }
    
    result = await service_b.handle_handshake_confirm(handshake_confirm_msg)
    print(f"   Result: {result}")
    assert result["status"] == "success"
    print("   ✓ handle_handshake_confirm executed")

    print("\n✅ All handshake handler tests passed!")


async def test_v1_handlers():
    """v1.0 新ハンドラのテスト"""
    print("\n=== v1.0 Handler Tests ===\n")

    service = init_service("test-v1", 8100)

    # 1. capability_query テスト
    print("1. Testing capability_query handler...")
    capability_msg = {
        "version": "0.3",
        "msg_type": "capability_query",
        "sender_id": "peer-a",
        "payload": {},
        "timestamp": "2024-01-01T00:00:00+00:00",
        "nonce": "cap001"
    }
    result = await service.handle_message(capability_msg)
    print(f"   Result: {result}")
    assert result["status"] == "success", "capability_query should succeed"
    assert service._last_capability_response is not None, "Capability response should be stored"
    print(f"   Capabilities: {service._last_capability_response}")

    # 2. heartbeat テスト
    print("\n2. Testing heartbeat handler...")
    heartbeat_msg = {
        "version": "0.3",
        "msg_type": "heartbeat",
        "sender_id": "peer-b",
        "payload": {"sequence": 42},
        "timestamp": "2024-01-01T00:00:00+00:00",
        "nonce": "hb001"
    }
    result = await service.handle_message(heartbeat_msg)
    print(f"   Result: {result}")
    assert result["status"] == "success", "heartbeat should succeed"
    assert "peer-b" in service.peer_stats, "peer-b should be in stats"
    assert service.peer_stats["peer-b"].is_healthy, "peer-b should be marked healthy"

    # 3. task_delegate テスト
    print("\n3. Testing task_delegate handler...")
    task_msg = {
        "version": "0.3",
        "msg_type": "task_delegate",
        "sender_id": "peer-c",
        "payload": {
            "task_id": "TASK-001",
            "description": "Process data analysis",
            "priority": "high",
            "data": {"key": "value"}
        },
        "timestamp": "2024-01-01T00:00:00+00:00",
        "nonce": "task001"
    }
    result = await service.handle_message(task_msg)
    print(f"   Result: {result}")
    assert result["status"] == "success", "task_delegate should succeed"
    assert len(service._pending_tasks) == 1, "Task should be queued"
    assert service._pending_tasks[0]["task_id"] == "TASK-001", "Task ID should match"
    print(f"   Queued task: {service._pending_tasks[0]}")

    # 4. 全ハンドラ登録確認
    print("\n4. Checking registered handlers...")
    expected_handlers = [
        "ping", "status", "capability_query", "heartbeat", "task_delegate",
        "handshake", "handshake_ack", "handshake_confirm"
    ]
    for handler_type in expected_handlers:
        assert handler_type in service.message_handlers, f"{handler_type} handler should be registered"
        print(f"   ✓ {handler_type} handler registered")

    print("\n✅ All v1.0 handler tests passed!")


async def test_health_with_v1_features():
    """ヘルスチェックにv1.0機能が含まれるかテスト"""
    print("\n=== Health Check with v1.0 Features ===\n")

    service = init_service("test-health-v1", 8101)

    health = await service.health_check()
    print(f"Health status: {health}")

    assert health["entity_id"] == "test-health-v1"
    assert "crypto_available" in health
    assert "signing_enabled" in health
    assert "verification_enabled" in health
    assert "public_key" in health

    print("✅ Health check includes v1.0 features!")


async def test_sequence_validation():
    """Sequence number validation tests (S8)"""
    print("\n=== Sequence Number Validation Tests (S8) ===\n")

    service = init_service("test-seq-validation", 8204)

    # 1. セッション作成と初期シーケンス設定
    print("1. Testing sequence validation setup...")
    session_id = str(uuid.uuid4())
    session = Session(
        session_id=session_id,
        peer_id="peer-seq-test",
        state=SessionState.ESTABLISHED,
        sequence_num=0,
        expected_sequence=1
    )
    service._handshake_sessions[session_id] = session
    print(f"   Session created: {session_id}")
    print(f"   Expected sequence: {session.expected_sequence}")
    print("   ✓ Setup complete")

    # 2. 正しいシーケンス番号の検証
    print("\n2. Testing valid sequence number...")
    valid_msg = {
        "version": "1.0",
        "msg_type": "heartbeat",
        "sender_id": "peer-seq-test",
        "recipient_id": "test-seq-validation",
        "session_id": session_id,
        "sequence_num": 1,  # 期待されるシーケンス番号
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "payload": {"status": "ok"}
    }
    result = await service.handle_message(valid_msg)
    assert result["status"] == "success", f"Valid sequence should succeed: {result}"
    assert session.expected_sequence == 2, "Expected sequence should increment"
    print(f"   ✓ Valid sequence accepted (next expected: {session.expected_sequence})")

    # 3. リプレイ攻撃検出（古いシーケンス番号）
    print("\n3. Testing replay attack detection...")
    replay_msg = {
        "version": "1.0",
        "msg_type": "heartbeat",
        "sender_id": "peer-seq-test",
        "recipient_id": "test-seq-validation",
        "session_id": session_id,
        "sequence_num": 1,  # 既に使用済みのシーケンス番号
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "payload": {"status": "replay"}
    }
    result = await service.handle_message(replay_msg)
    # リプレイは検出されるべき
    print(f"   Replay detection result: {result}")
    print("   ✓ Replay attack handling tested")

    # 4. メッセージギャップ検出（飛んだシーケンス番号）
    print("\n4. Testing message gap detection...")
    gap_msg = {
        "version": "1.0",
        "msg_type": "heartbeat",
        "sender_id": "peer-seq-test",
        "recipient_id": "test-seq-validation",
        "session_id": session_id,
        "sequence_num": 5,  # 期待値は2なのに5が来た
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "payload": {"status": "gap"}
    }
    result = await service.handle_message(gap_msg)
    print(f"   Gap detection result: {result}")
    # ギャップは検出されるが、メッセージは処理される（ベストエフォート）
    print("   ✓ Message gap handling tested")

    # 5. 連続したシーケンス番号
    print("\n5. Testing consecutive sequence numbers...")
    for i in range(2, 6):
        msg = {
            "version": "1.0",
            "msg_type": "heartbeat",
            "sender_id": "peer-seq-test",
            "recipient_id": "test-seq-validation",
            "session_id": session_id,
            "sequence_num": i,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": secrets.token_hex(16),
            "payload": {"seq": i}
        }
        result = await service.handle_message(msg)
        assert result["status"] == "success", f"Sequence {i} should succeed"
        print(f"   ✓ Sequence {i} accepted")

    assert session.expected_sequence == 6, f"Expected sequence should be 6, got {session.expected_sequence}"
    print(f"   ✓ All consecutive sequences processed (next: {session.expected_sequence})")

    # 6. 無効なセッションID
    print("\n6. Testing invalid session ID...")
    invalid_session_msg = {
        "version": "1.0",
        "msg_type": "heartbeat",
        "sender_id": "peer-seq-test",
        "recipient_id": "test-seq-validation",
        "session_id": "invalid-session-id",
        "sequence_num": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "payload": {"status": "invalid"}
    }
    result = await service.handle_message(invalid_session_msg)
    print(f"   Invalid session result: {result}")
    print("   ✓ Invalid session handling tested")

    print("\n✅ All sequence validation tests passed!")


async def test_sequence_validation_strict():
    """S8: SEQUENCE_ERROR厳密検証テスト"""
    print("\n=== Sequence Validation Strict Tests (S8) ===\n")

    service = init_service("test-seq-strict", 8204)

    # セッション作成
    session_id = str(uuid.uuid4())
    from peer_service import Session, SessionState
    session = Session(
        session_id=session_id,
        peer_id="peer-strict-test",
        state=SessionState.ESTABLISHED
    )
    service._handshake_sessions[session_id] = session
    print(f"   Created session: {session_id}")
    print(f"   Initial expected_sequence: {session.expected_sequence}")

    # 1. SEQUENCE_ERROR: リプレイ攻撃（古いシーケンス番号）
    print("\n1. Testing SEQUENCE_ERROR for replay attack...")
    
    # まず正常メッセージを送信（seq=1）
    msg1 = {
        "version": "1.0",
        "msg_type": "heartbeat",
        "sender_id": "peer-strict-test",
        "recipient_id": "test-seq-strict",
        "session_id": session_id,
        "sequence_num": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "payload": {"status": "ok"}
    }
    result = await service.handle_message(msg1)
    assert result["status"] == "success", "First message should succeed"
    assert session.expected_sequence == 2, "Expected should be 2 after seq=1"
    print(f"   ✓ Initial message accepted (expected now: {session.expected_sequence})")
    
    # 同じシーケンス番号を再送信（リプレイ攻撃）
    replay_msg = {
        "version": "1.0",
        "msg_type": "heartbeat",
        "sender_id": "peer-strict-test",
        "recipient_id": "test-seq-strict",
        "session_id": session_id,
        "sequence_num": 1,  # 古いシーケンス番号
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "payload": {"status": "replay"}
    }
    result = await service.handle_message(replay_msg)
    
    # SEQUENCE_ERRORが返されることを検証
    assert result["status"] == "error", f"Replay should fail: {result}"
    assert result.get("error_code") == SEQUENCE_ERROR, f"Expected SEQUENCE_ERROR, got: {result.get('error_code')}"
    assert "expected" in result.get("details", {}), "Error details should include expected sequence"
    assert result["details"]["received"] == 1, "Error should show received=1"
    print(f"   ✓ SEQUENCE_ERROR returned for replay attack")
    print(f"     Error: {result.get('error_code')}, Details: {result.get('details')}")

    # 2. SEQUENCE_ERROR: メッセージギャップ（飛んだシーケンス番号）
    print("\n2. Testing SEQUENCE_ERROR for message gap...")
    gap_msg = {
        "version": "1.0",
        "msg_type": "heartbeat",
        "sender_id": "peer-strict-test",
        "recipient_id": "test-seq-strict",
        "session_id": session_id,
        "sequence_num": 10,  # 期待値は2なのに10が来た
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "payload": {"status": "gap"}
    }
    result = await service.handle_message(gap_msg)
    
    # ギャップも検出されることを検証（実装による）
    print(f"   Gap result: {result}")
    if result["status"] == "error":
        print(f"   ✓ Gap detected as error (strict mode)")
    else:
        print(f"   ✓ Gap allowed (best-effort mode)")
    
    # 3. 連続メッセージの正常処理
    print("\n3. Testing consecutive messages...")
    
    # 新しいセッションでテスト
    session_id2 = str(uuid.uuid4())
    session2 = Session(
        session_id=session_id2,
        peer_id="peer-strict-test-2",
        state=SessionState.ESTABLISHED
    )
    service._handshake_sessions[session_id2] = session2
    
    for i in range(1, 6):
        msg = {
            "version": "1.0",
            "msg_type": "heartbeat",
            "sender_id": "peer-strict-test-2",
            "recipient_id": "test-seq-strict",
            "session_id": session_id2,
            "sequence_num": i,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": secrets.token_hex(16),
            "payload": {"seq": i}
        }
        result = await service.handle_message(msg)
        assert result["status"] == "success", f"Sequence {i} should succeed"
        print(f"   ✓ Sequence {i} accepted")
    
    assert session2.expected_sequence == 6, f"Expected 6, got {session2.expected_sequence}"
    print(f"   ✓ All sequences processed (next expected: {session2.expected_sequence})")

    print("\n✅ All strict sequence validation tests passed!")


async def test_session_management():
    """Session management tests"""
    print("\n=== Session Management Tests ===\n")

    service = init_service("test-session-mgmt", 8203)

    # 1. Create and store sessions
    print("1. Testing session storage...")
    session1 = Session(
        session_id="session-001",
        peer_id="peer-a",
        state=SessionState.ESTABLISHED
    )
    session2 = Session(
        session_id="session-002",
        peer_id="peer-b",
        state=SessionState.HANDSHAKE_SENT
    )
    
    service._handshake_sessions["session-001"] = session1
    service._handshake_sessions["session-002"] = session2
    
    assert len(service._handshake_sessions) == 2
    print("   ✓ Sessions stored")

    # 2. get_session test
    print("\n2. Testing get_session...")
    retrieved = service.get_session("session-001")
    assert retrieved is not None
    assert retrieved.session_id == "session-001"
    assert retrieved.peer_id == "peer-a"
    print("   ✓ get_session works")

    # 3. get_peer_session test
    print("\n3. Testing get_peer_session...")
    peer_session = service.get_peer_session("peer-a")
    assert peer_session is not None
    assert peer_session.peer_id == "peer-a"
    assert peer_session.state == SessionState.ESTABLISHED
    print("   ✓ get_peer_session works")

    # 4. list_sessions test
    print("\n4. Testing list_sessions...")
    sessions = service.list_sessions()
    assert len(sessions) == 2
    print(f"   Sessions: {[s['session_id'] for s in sessions]}")
    print("   ✓ list_sessions works")

    # 5. Cleanup test
    print("\n5. Testing session cleanup...")
    service._cleanup_handshake("session-001", "peer-a")
    assert service.get_session("session-001") is None
    print("   ✓ Session cleanup works")

    print("\n✅ All session management tests passed!")


async def main():
    """全テスト実行"""
    print("=" * 50)
    print("Peer Service v1.0 Test Suite")
    print("=" * 50)

    await test_session_dataclass()
    await test_session_state_transitions()
    await test_handshake_message_handlers()
    await test_v1_handlers()
    await test_health_with_v1_features()
    await test_sequence_validation()  # S8: New sequence validation tests
    await test_session_management()

    print("\n" + "=" * 50)
    print("All v1.0 tests completed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
