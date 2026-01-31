#!/usr/bin/env python3
"""
v1.1 Protocol Integration Test Suite

Protocol v1.1機能の統合テスト:
- Chunked message transfer
- X25519/AES-256-GCM E2E encryption
- Rate limiting
- Session management with UUID
- Sequence numbers for ordering

Run: python services/test_v1.1_integration.py
"""

import asyncio
import sys
import os
import time
import json
import secrets
from datetime import datetime, timezone

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from peer_service import (
    PeerService, ChunkInfo, SessionInfo, SessionState,
    RateLimiter, RateLimitConfig
)
from crypto import CryptoManager, generate_entity_keypair


def setup_test_keys():
    """テスト用の鍵ペアを生成"""
    priv_a, pub_a = generate_entity_keypair()
    priv_b, pub_b = generate_entity_keypair()
    return priv_a, pub_a, priv_b, pub_b


async def test_chunked_message_transfer():
    """Chunked message transfer統合テスト"""
    print("\n=== Chunked Message Transfer (v1.1) ===\n")
    
    priv_a, pub_a, priv_b, pub_b = setup_test_keys()
    os.environ["ENTITY_PRIVATE_KEY"] = priv_a
    
    # PeerService初期化（chunk機能はデフォルトで有効）
    service = PeerService(
        "entity-a",
        8001,
        private_key_hex=priv_a
    )
    
    # 大きなペイロードを作成（chunkingが必要なサイズ）
    large_payload = {
        "type": "large_data",
        "data": "x" * 20000,  # 20KBのデータ
        "metadata": {"timestamp": datetime.now(timezone.utc).isoformat()}
    }
    
    # ChunkInfoのテスト
    chunk_info = ChunkInfo(chunk_id="test-chunk-001", total_chunks=3)
    assert chunk_info.chunk_id == "test-chunk-001"
    assert chunk_info.total_chunks == 3
    assert not chunk_info.is_complete()
    print("✓ ChunkInfo created")
    
    # チャンク追加
    chunk_info.add_chunk(0, "eyJrZXkiOiAidmFsdWUxIn0=")
    chunk_info.add_chunk(1, "eyJrZXky")  
    chunk_info.add_chunk(2, "OiAidmFsdWUyIn0=")
    assert chunk_info.is_complete()
    print("✓ All chunks added and complete")
    
    # 再構築
    reconstructed = chunk_info.get_reconstructed_data()
    assert reconstructed is not None
    print("✓ Payload reconstructed")
    
    # cleanup_old_chunksテスト
    service._chunk_buffer["old-chunk"] = chunk_info
    cleaned = await service.cleanup_old_chunks(max_age_seconds=0)  # 即時クリーンアップ
    print(f"✓ Cleanup completed: {cleaned} chunks removed")
    
    print("\n✅ Chunked message transfer tests passed")


async def test_e2e_encryption():
    """X25519/AES-256-GCM E2E暗号化テスト"""
    print("\n=== E2E Encryption (X25519 + AES-256-GCM) ===\n")
    
    priv_a, pub_a, priv_b, pub_b = setup_test_keys()
    
    # CryptoManager初期化
    crypto_a = CryptoManager("entity-a", private_key_hex=priv_a)
    crypto_b = CryptoManager("entity-b", private_key_hex=priv_b)
    
    # X25519鍵ペア生成
    crypto_a.generate_x25519_keypair()
    crypto_b.generate_x25519_keypair()
    print("✓ X25519 keypairs generated")
    
    # 共有鍵導出
    pub_key_b_x25519 = crypto_b.get_x25519_public_key_b64()
    pub_key_a_x25519 = crypto_a.get_x25519_public_key_b64()
    
    crypto_a.derive_shared_key(pub_key_b_x25519, "entity-b")
    crypto_b.derive_shared_key(pub_key_a_x25519, "entity-a")
    print("✓ Shared keys derived")
    
    # 暗号化
    payload = {"secret": "sensitive data", "value": 12345}
    ciphertext, nonce = crypto_a.encrypt_payload(payload, pub_key_b_x25519, "entity-b")
    print(f"✓ Payload encrypted: {ciphertext[:40]}...")
    
    # 復号
    decrypted = crypto_b.decrypt_payload(ciphertext, nonce, "entity-a")
    assert decrypted == payload
    print(f"✓ Payload decrypted successfully")
    
    # SecureMessageテスト
    secure_msg = crypto_a.create_secure_message(
        payload=payload,
        encrypt=True,
        peer_public_key_b64=pub_key_b_x25519,
        peer_id="entity-b",
        include_jwt=True,
        jwt_audience="entity-b"
    )
    assert secure_msg.encrypted_payload is not None
    assert secure_msg.jwt_token is not None
    print("✓ Secure message created with encryption + JWT")
    
    print("\n✅ E2E encryption tests passed")


async def test_rate_limiting():
    """Rate limiting統合テスト"""
    print("\n=== Rate Limiting (Token Bucket) ===\n")
    
    priv_a, pub_a, priv_b, pub_b = setup_test_keys()
    os.environ["ENTITY_PRIVATE_KEY"] = priv_a
    
    # PeerService初期化（rate limiting有効）
    service = PeerService(
        "entity-a",
        8001,
        rate_limit_requests=60,
        rate_limit_window=60,
        private_key_hex=priv_a
    )
    
    # RateLimiter初期化確認
    assert service._rate_limiter is not None
    print("✓ RateLimiter initialized")
    
    # カスタムコンフィグテスト
    config = RateLimitConfig(
        requests_per_minute=10,
        requests_per_hour=100,
        burst_size=5
    )
    limiter = RateLimiter(config)
    
    # リクエスト許可チェック
    allowed_count = 0
    for i in range(15):
        allowed, retry_after = await limiter.check_rate_limit("peer-b", "test_msg")
        if allowed:
            allowed_count += 1
    
    print(f"✓ Rate limiting applied: {allowed_count}/15 requests allowed (burst=5)")
    assert allowed_count <= 5, "Burst size should limit initial requests"
    
    print("\n✅ Rate limiting tests passed")


async def test_session_management():
    """Session management with UUIDテスト"""
    print("\n=== Session Management (UUID) ===\n")
    
    priv_a, pub_a, priv_b, pub_b = setup_test_keys()
    os.environ["ENTITY_PRIVATE_KEY"] = priv_a
    
    # PeerService初期化（session management有効）
    service = PeerService(
        "entity-a",
        8001,
        enable_session_management=True,
        session_ttl_seconds=3600,
        private_key_hex=priv_a
    )
    
    # SessionManager初期化確認
    assert service._session_manager is not None
    print("✓ SessionManager initialized")
    
    # SessionInfoのテスト
    session = SessionInfo(
        session_id="test-session-uuid-123",
        peer_id="peer-b",
        state=SessionState.INITIAL
    )
    assert session.session_id == "test-session-uuid-123"
    assert session.peer_id == "peer-b"
    assert session.state == SessionState.INITIAL
    print("✓ SessionInfo created")
    
    # シーケンス番号テスト
    seq1 = session.increment_sequence()
    seq2 = session.increment_sequence()
    assert seq1 == 1
    assert seq2 == 2
    print("✓ Sequence numbers working")
    
    # セッション有効期限テスト
    assert not session.is_expired(max_age_seconds=3600)
    print("✓ Session expiration check working")
    
    print("\n✅ Session management tests passed")


async def test_sequence_numbers():
    """Sequence numbers for orderingテスト"""
    print("\n=== Sequence Numbers for Ordering ===\n")
    
    priv_a, pub_a, priv_b, pub_b = setup_test_keys()
    os.environ["ENTITY_PRIVATE_KEY"] = priv_a
    
    # PeerService初期化（sequence tracking有効）
    service = PeerService(
        "entity-a",
        8001,
        enable_session_management=True,
        private_key_hex=priv_a
    )
    
    # セッション作成
    service.add_peer("peer-b", "http://localhost:8002", public_key_hex=pub_b)
    
    # メッセージ送信時のシーケンス番号付与をテスト
    # （実際の送信はモック）
    session = SessionInfo(
        session_id="test-seq-session",
        peer_id="peer-b",
        sequence_num=0,
        expected_sequence=1
    )
    
    # シーケンス番号の増加
    for i in range(1, 6):
        seq = session.increment_sequence()
        assert seq == i
    
    assert session.sequence_num == 5
    print("✓ Sequence numbers increment correctly")
    
    # アクティビティ更新
    old_activity = session.last_activity
    session.update_activity()
    assert session.last_activity > old_activity
    print("✓ Activity timestamp updated")
    
    print("\n✅ Sequence number tests passed")


async def test_v1_1_protocol_compliance():
    """v1.1プロトコル準拠チェック"""
    print("\n=== v1.1 Protocol Compliance ===\n")
    
    priv_a, pub_a, priv_b, pub_b = setup_test_keys()
    os.environ["ENTITY_PRIVATE_KEY"] = priv_a
    
    # 完全なv1.1設定で初期化
    service = PeerService(
        "entity-a",
        8001,
        enable_encryption=True,
        enable_chunking=True,
        enable_rate_limiting=True,
        enable_sessions=True,
        require_signatures=True,
        private_key_hex=priv_a
    )
    
    # カパシティ取得
    health = await service.health_check()
    
    # v1.1機能が有効かチェック
    assert health["crypto_available"] is True
    assert health["signing_enabled"] is True
    print("✓ Encryption and signing enabled")
    
    # メッセージハンドラチェック
    required_handlers = [
        "ping", "status", "heartbeat", "capability_query",
        "task_delegate", "chunk"  # v1.1で追加
    ]
    for handler in required_handlers:
        assert handler in service.message_handlers
    print(f"✓ All v1.1 message handlers registered: {required_handlers}")
    
    # 公開鍵取得
    pub_keys = service.get_public_keys()
    assert "ed25519" in pub_keys
    print("✓ Public keys available")
    
    print("\n✅ v1.1 Protocol compliance verified")


async def main():
    """v1.1統合テスト実行"""
    print("=" * 60)
    print("Protocol v1.1 Integration Test Suite")
    print("=" * 60)
    
    try:
        await test_chunked_message_transfer()
        await test_e2e_encryption()
        await test_rate_limiting()
        await test_session_management()
        await test_sequence_numbers()
        await test_v1_1_protocol_compliance()
        
        print("\n" + "=" * 60)
        print("✅ All v1.1 integration tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
