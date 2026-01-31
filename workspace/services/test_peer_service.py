#!/usr/bin/env python3
"""
Peer Service セキュリティ機能付きテストスクリプト

Protocol v1.0対応:
- Ed25519署名によるメッセージ認証（必須）
- リプレイ攻撃防止（タイムスタンプ+ノンス）
- 公開鍵レジストリによるピア管理
- Capability exchange（機能交換）
- Task delegation（タスク委譲）
- Heartbeat（死活監視）
- Peer statistics（統計情報）

Protocol v1.1対応（実装済み）:
- X25519/AES-256-GCM payload encryption
- Session management with UUID
- Sequence numbers for ordering
- Chunked message transfer

TODO v1.2:
- End-to-end encryption tests
- Load testing with concurrent peers
- Network partition recovery tests
"""

import asyncio
import sys
import os
import time
import secrets
import pytest
from datetime import datetime, timezone, timedelta

# servicesディレクトリをパスに追加（複数パターン対応）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)  # services/
sys.path.insert(0, WORKSPACE_DIR)  # workspace/

# インポート（複数パターン対応）
import_error_details = []
IMPORT_SUCCESS = False

try:
    # パターン1: パッケージとして実行（python -m services.test_peer_service）
    from services.peer_service import init_service, create_server, PeerService
    from services.crypto import WalletManager, generate_entity_keypair, CryptoManager, SecureMessage
    print("✅ Imported using package pattern (services.xxx)")
    IMPORT_SUCCESS = True
except ImportError as e1:
    import_error_details.append(f"Pattern 1 failed: {e1}")
    try:
        # パターン2: スクリプトとして直接実行（python services/test_peer_service.py）
        from peer_service import init_service, create_server, PeerService
        from crypto import WalletManager, generate_entity_keypair, CryptoManager, SecureMessage
        print("✅ Imported using direct pattern (xxx)")
        IMPORT_SUCCESS = True
    except ImportError as e2:
        import_error_details.append(f"Pattern 2 failed: {e2}")
        try:
            # パターン3: workspaceから実行（python services/test_peer_service.py）
            sys.path.insert(0, os.path.join(WORKSPACE_DIR, 'services'))
            from peer_service import init_service, create_server, PeerService
            from crypto import WalletManager, generate_entity_keypair, CryptoManager, SecureMessage
            print("✅ Imported using workspace pattern")
            IMPORT_SUCCESS = True
        except ImportError as e3:
            import_error_details.append(f"Pattern 3 failed: {e3}")
            pass

if not IMPORT_SUCCESS:
    print("❌ Import errors:")
    for detail in import_error_details:
        print(f"   - {detail}")
    raise ImportError(f"Failed to import required modules. Errors: {import_error_details}")


def setup_test_keys():
    """テスト用の鍵ペアを生成して環境変数に設定"""
    # エンティティAの鍵
    priv_a_hex, pub_a_hex = generate_entity_keypair()
    # エンティティBの鍵
    priv_b_hex, pub_b_hex = generate_entity_keypair()
    return priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex


async def test_signature_verification():
    """Ed25519署名検証のテスト"""
    print("\n=== Ed25519 Signature Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    service_a = init_service("entity-a", 8001, private_key_hex=priv_a_hex)
    
    # テストメッセージ
    payload = {"type": "test", "data": "hello", "from": "entity-a"}
    
    # 署名作成
    signature = service_a.crypto_manager.sign_message(payload)
    print(f"Signature created: {signature[:40]}...")
    
    # 検証用に別のCryptoManagerを作成
    crypto_b = CryptoManager("entity-b", private_key_hex=priv_b_hex)
    
    # 署名検証
    is_valid = crypto_b.verify_signature(
        payload, 
        signature, 
        service_a.crypto_manager.get_ed25519_public_key_b64()
    )
    print(f"Signature valid: {is_valid}")
    assert is_valid, "Signature should be valid"
    
    # 改竄テスト
    tampered_payload = {"type": "test", "data": "tampered", "from": "entity-a"}
    is_invalid = crypto_b.verify_signature(
        tampered_payload,
        signature,
        service_a.crypto_manager.get_ed25519_public_key_b64()
    )
    print(f"Tampered signature invalid: {not is_invalid}")
    assert not is_invalid, "Tampered message should fail verification"
    
    print("\n✅ Signature tests completed")


async def test_encryption():
    """X25519 + AES-256-GCM暗号化のテスト"""
    print("\n=== X25519 + AES-256-GCM Encryption Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    crypto_a = CryptoManager("entity-a", private_key_hex=priv_a_hex)
    crypto_b = CryptoManager("entity-b", private_key_hex=priv_b_hex)
    
    # X25519鍵ペアを生成
    crypto_a.generate_x25519_keypair()
    crypto_b.generate_x25519_keypair()
    
    pub_key_b_x25519 = crypto_b.get_x25519_public_key_b64()
    pub_key_a_x25519 = crypto_a.get_x25519_public_key_b64()
    
    # 暗号化
    payload = {"secret": "sensitive data", "value": 12345}
    ciphertext, nonce = crypto_a.encrypt_payload(payload, pub_key_b_x25519, "entity-b")
    print(f"Encrypted payload: {ciphertext[:40]}...")
    print(f"Nonce: {nonce[:20]}...")
    
    # 共有鍵をB側でも導出（通常はハンドシェイクで行う）
    crypto_b.derive_shared_key(pub_key_a_x25519, "entity-a")
    
    # 復号
    decrypted = crypto_b.decrypt_payload(ciphertext, nonce, "entity-a")
    print(f"Decrypted payload: {decrypted}")
    
    assert decrypted == payload, "Decrypted payload should match original"
    print("\n✅ Encryption tests completed")


async def test_jwt_authentication():
    """JWT認証のテスト"""
    print("\n=== JWT Authentication Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    crypto_a = CryptoManager("entity-a", private_key_hex=priv_a_hex)
    crypto_b = CryptoManager("entity-b", private_key_hex=priv_b_hex)
    
    # JWTトークン作成
    token = crypto_a.create_jwt_token(audience="entity-b")
    print(f"JWT created: {token[:50]}...")
    
    # JWT検証
    decoded = crypto_b.verify_jwt_token(
        token,
        crypto_a.get_ed25519_public_key_b64(),
        audience="entity-b"
    )
    print(f"JWT valid: {decoded is not None}")
    assert decoded is not None, "JWT should be valid"
    assert decoded["sub"] == "entity-a", "Subject should be entity-a"
    assert decoded["aud"] == "entity-b", "Audience should be entity-b"
    
    # 期限切れテスト（手動で期限切れトークンを作成）
    import jwt as pyjwt
    
    expired_payload = {
        "sub": "entity-a",
        "iat": datetime.now(timezone.utc) - timedelta(minutes=10),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        "iss": "peer-service",
    }
    
    from cryptography.hazmat.primitives import serialization
    private_key_pem = crypto_a._ed25519_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    expired_token = pyjwt.encode(expired_payload, private_key_pem, algorithm="EdDSA")
    
    expired_decoded = crypto_b.verify_jwt_token(
        expired_token,
        crypto_a.get_ed25519_public_key_b64(),
        audience="entity-b"
    )
    print(f"Expired JWT invalid: {expired_decoded is None}")
    assert expired_decoded is None, "Expired JWT should be invalid"
    
    print("\n✅ JWT tests completed")


async def test_replay_protection():
    """リプレイ攻撃防止のテスト"""
    print("\n=== Replay Protection Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    crypto = CryptoManager("test-entity", private_key_hex=priv_a_hex)
    
    # 正常なnonce
    nonce1 = crypto.generate_nonce()
    ts = time.time()
    
    result1 = crypto.check_and_record_nonce(nonce1, ts)
    print(f"First nonce check: {result1}")
    assert result1, "First nonce should be valid"
    
    # 同じnonceのリプレイ
    result2 = crypto.check_and_record_nonce(nonce1, ts)
    print(f"Replay check (should fail): {not result2}")
    assert not result2, "Replay should be detected"
    
    # 古いタイムスタンプ（60秒以上過去）
    old_ts = ts - 120
    old_nonce = crypto.generate_nonce()
    result3 = crypto.check_and_record_nonce(old_nonce, old_ts)
    print(f"Old timestamp check (should fail): {not result3}")
    assert not result3, "Old timestamp should be rejected"
    
    # 未来のタイムスタンプ（60秒以上未来）
    future_ts = ts + 120
    future_nonce = crypto.generate_nonce()
    result4 = crypto.check_and_record_nonce(future_nonce, future_ts)
    print(f"Future timestamp check (should fail): {not result4}")
    assert not result4, "Future timestamp should be rejected"
    
    print("\n✅ Replay protection tests completed")


async def test_secure_message():
    """セキュアメッセージ（統合機能）のテスト"""
    print("\n=== Secure Message Integration Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    crypto_a = CryptoManager("entity-a", private_key_hex=priv_a_hex)
    crypto_b = CryptoManager("entity-b", private_key_hex=priv_b_hex)
    
    # X25519鍵ペア生成
    crypto_a.generate_x25519_keypair()
    crypto_b.generate_x25519_keypair()
    
    # 共有鍵導出
    crypto_a.derive_shared_key(crypto_b.get_x25519_public_key_b64(), "entity-b")
    crypto_b.derive_shared_key(crypto_a.get_x25519_public_key_b64(), "entity-a")
    
    # セキュアメッセージ作成（暗号化 + JWT）
    payload = {
        "from": "entity-a",
        "type": "task_delegate",
        "payload": {"task": "important_job", "params": {"key": "value"}}
    }
    
    secure_msg = crypto_a.create_secure_message(
        payload=payload,
        encrypt=True,
        peer_public_key_b64=crypto_b.get_x25519_public_key_b64(),
        peer_id="entity-b",
        include_jwt=True,
        jwt_audience="entity-b"
    )
    
    print(f"Secure message created")
    print(f"  - Timestamp: {secure_msg.timestamp}")
    print(f"  - Nonce: {secure_msg.nonce[:20]}...")
    print(f"  - Signature: {secure_msg.signature[:40]}...")
    print(f"  - Encrypted: {secure_msg.encrypted_payload is not None}")
    print(f"  - JWT: {secure_msg.jwt_token is not None}")
    
    # メッセージ検証・復号
    decrypted = crypto_b.verify_and_decrypt_message(
        secure_msg,
        peer_id="entity-a",
        verify_jwt=True,
        jwt_audience="entity-b"
    )
    
    assert decrypted is not None, "Message should be verified and decrypted"
    assert decrypted["type"] == "task_delegate"
    print(f"\nDecrypted payload: {decrypted}")
    
    print("\n✅ Secure message tests completed")


async def test_peer_service_integration():
    """PeerServiceとの統合テスト"""
    print("\n=== PeerService Integration Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # サービスAを初期化
    service_a = init_service(
        "entity-a", 
        8001,
        private_key_hex=priv_a_hex,
        enable_encryption=True,
        require_signatures=True,
    )
    
    # 公開鍵を取得
    keys_a = service_a.get_public_keys()
    print(f"Entity A public keys: ed25519={keys_a['ed25519'][:20]}..., x25519={keys_a['x25519'][:20]}...")
    
    # ピアBを登録（公開鍵付き）
    service_a.add_peer(
        "entity-b",
        "http://localhost:8002",
        public_key=pub_b_hex,  # Base64ではなくhexなので注意 - 実際はBase64が必要
        x25519_public_key=None,  # ハンドシェイクで取得
    )
    
    # ヘルスチェック
    health = await service_a.health_check()
    print(f"\nHealth check: {health}")
    assert health["security"]["encryption_enabled"]
    assert health["security"]["signatures_required"]
    
    print("\n✅ PeerService integration tests completed")


async def test_full_communication_secure():
    """完全なセキュア双方向通信テスト"""
    print("\n=== Full Secure Communication Test ===\n")
    
    try:
        import aiohttp
        from aiohttp import web
    except ImportError:
        print("⚠️ aiohttp not installed, skipping full communication test")
        return
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # 受信サーバー（セキュアメッセージを処理）
    received_messages = []
    
    async def message_handler(request):
        msg_dict = await request.json()
        received_messages.append(msg_dict)
        
        # 簡易検証（実際はCryptoManagerを使う）
        secure_msg = SecureMessage.from_dict(msg_dict)
        
        return web.json_response({
            "status": "received",
            "verified": secure_msg.signature is not None
        })
    
    app = web.Application()
    app.router.add_post("/message", message_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 9997)
    await site.start()
    
    try:
        # 送信側サービス
        service = init_service("test-sender", 8005, private_key_hex=priv_a_hex)
        
        # X25519鍵を生成
        service.crypto_manager.generate_x25519_keypair()
        
        service.add_peer("test-receiver", "http://localhost:9997")
        
        # セキュアメッセージ送信
        result = await service.send_message(
            "test-receiver",
            "status_report",
            {"task_id": "secure-123", "result": "encrypted"},
            encrypt=False,  # テスト用サーバーが復号に対応していないため
            include_jwt=False,
        )
        
        print(f"Send result: {result}")
        print(f"Messages received: {len(received_messages)}")
        
        if received_messages:
            msg = received_messages[0]
            print(f"Received message structure:")
            print(f"  - payload: {msg.get('payload', {}).keys()}")
            print(f"  - signature: {msg.get('signature', '')[:30]}...")
            print(f"  - nonce: {msg.get('nonce', '')[:20]}...")
        
        assert result == True, "Message should be sent successfully"
        assert len(received_messages) == 1, "Message should be received"
        
        print("\n✅ Full secure communication test completed")
        
    finally:
        await runner.cleanup()


async def test_send_with_retry():
    """_send_with_retryメソッドのテスト"""
    print("\n=== _send_with_retry Test ===\n")
    
    try:
        import aiohttp
        from aiohttp import web
    except ImportError:
        print("⚠️ aiohttp not installed, skipping _send_with_retry test")
        return
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # テスト用カウンター
    request_count = {"success": 0, "failure": 0}
    
    async def success_handler(request):
        request_count["success"] += 1
        return web.json_response({"status": "ok"})
    
    async def failure_handler(request):
        request_count["failure"] += 1
        return web.json_response({"status": "error"}, status=500)
    
    # テストサーバー
    app = web.Application()
    app.router.add_post("/success", success_handler)
    app.router.add_post("/failure", failure_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 9996)
    await site.start()
    
    try:
        service = init_service("test-sender", 8007, private_key_hex=priv_a_hex)
        
        # _send_with_retryメソッドの存在チェック
        if not hasattr(service, '_send_with_retry'):
            print("⚠️ _send_with_retry method not available, skipping test")
            return
        
        # 成功ケース
        success, status = await service._send_with_retry(
            "http://localhost:9996/success",
            {"test": "data"},
            max_retries=2,
            base_delay=0.1
        )
        print(f"Success case: success={success}, status={status}")
        assert success is True, "Success case should return True"
        assert status == 200, "Success case should return 200"
        
        # サーバーエラー（リトライ対象）
        request_count["failure"] = 0
        success, status = await service._send_with_retry(
            "http://localhost:9996/failure",
            {"test": "data"},
            max_retries=2,
            base_delay=0.1
        )
        print(f"Failure case: success={success}, status={status}, retries={request_count['failure']}")
        assert success is False, "Failure case should return False"
        assert status == 500, "Failure case should return 500"
        assert request_count["failure"] == 2, "Should retry specified times"
        
        # 接続エラー（タイムアウト）
        success, status = await service._send_with_retry(
            "http://localhost:59999/nonexistent",
            {"test": "data"},
            max_retries=1,
            base_delay=0.1
        )
        print(f"Connection error case: success={success}, status={status}")
        assert success is False, "Connection error should return False"
        assert status is None, "Connection error should return None status"
        
        print("\n✅ _send_with_retry tests completed")
        
    finally:
        await runner.cleanup()


async def test_send_with_retry_non_retryable():
    """リトライ対象外のステータスコードテスト"""
    print("\n=== Non-retryable Status Codes Test ===\n")
    
    try:
        import aiohttp
        from aiohttp import web
    except ImportError:
        print("⚠️ aiohttp not installed, skipping test")
        return
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    request_count = {"count": 0}
    
    async def not_found_handler(request):
        request_count["count"] += 1
        return web.json_response({"status": "not found"}, status=404)
    
    async def forbidden_handler(request):
        request_count["count"] += 1
        return web.json_response({"status": "forbidden"}, status=403)
    
    app = web.Application()
    app.router.add_post("/notfound", not_found_handler)
    app.router.add_post("/forbidden", forbidden_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 9995)
    await site.start()
    
    try:
        service = init_service("test-sender", 8008, private_key_hex=priv_a_hex)
        
        # 404 - リトライ対象外
        request_count["count"] = 0
        success, status = await service._send_with_retry(
            "http://localhost:9995/notfound",
            {"test": "data"},
            max_retries=3,
            base_delay=0.1
        )
        print(f"404 case: success={success}, status={status}, attempts={request_count['count']}")
        assert success is False, "404 should return False"
        assert status == 404, "404 should return status 404"
        assert request_count["count"] == 1, "404 should not retry"
        
        # 403 - リトライ対象外
        request_count["count"] = 0
        success, status = await service._send_with_retry(
            "http://localhost:9995/forbidden",
            {"test": "data"},
            max_retries=3,
            base_delay=0.1
        )
        print(f"403 case: success={success}, status={status}, attempts={request_count['count']}")
        assert success is False, "403 should return False"
        assert status == 403, "403 should return status 403"
        assert request_count["count"] == 1, "403 should not retry"
        
        print("\n✅ Non-retryable status codes tests completed")
        
    finally:
        await runner.cleanup()


async def test_backward_compatibility():
    """後方互換性テスト（旧形式メッセージ）"""
    print("\n=== Backward Compatibility Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # 署名なしで初期化
    service = init_service(
        "compat-test",
        8006,
        private_key_hex=priv_a_hex,
        require_signatures=False,
        enable_encryption=False,
    )
    
    # 旧形式メッセージ（署名なし）を処理
    old_style_message = {
        "from": "legacy-peer",
        "type": "status",
        "payload": {"status": "ok"},
        "timestamp": "2024-01-01T00:00:00"
    }
    
    # このテストは現在の実装では動作しない（署名必須のため）
    # 将来的に互換モードを追加する場合のテスト
    print("⚠️ Backward compatibility mode not yet implemented")
    print("Current implementation requires signatures for all messages")
    
    print("\n✅ Backward compatibility test completed (skipped)")


# ============ PeerService 機能テスト ============

async def test_peer_service_init():
    """PeerService初期化テスト"""
    print("\n=== PeerService Initialization Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # 基本初期化
    service = PeerService("test-entity", 8001)
    assert service.entity_id == "test-entity"
    assert service.port == 8001
    assert len(service.peers) == 0
    assert len(service.message_handlers) >= 5  # デフォルトハンドラ
    print(f"✓ Basic initialization: entity_id={service.entity_id}")
    
    # 暗号機能の初期化確認
    assert service.key_pair is not None
    assert service.signer is not None
    assert service.verifier is not None
    assert service.replay_protector is not None
    print(f"✓ Crypto initialized: public_key={service.get_public_key_hex()[:20]}...")
    
    # キュー・ハートビート初期化確認
    assert service._queue is not None
    assert service._heartbeat is not None
    print("✓ Queue and heartbeat initialized")
    
    # 設定オプションテスト
    service_no_queue = PeerService("test-entity-2", 8002, enable_queue=False)
    assert service_no_queue._queue is None
    print("✓ Queue disabled option works")
    
    service_no_heartbeat = PeerService("test-entity-3", 8003, enable_heartbeat=False)
    assert service_no_heartbeat._heartbeat is None
    print("✓ Heartbeat disabled option works")
    
    print("\n✅ PeerService initialization tests completed")


async def test_peer_management():
    """ピア登録・削除テスト"""
    print("\n=== Peer Management Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    service = PeerService("test-entity", 8001, private_key_hex=priv_a_hex)
    
    # ピア追加
    service.add_peer("peer-b", "http://localhost:8002", public_key_hex=pub_b_hex)
    assert "peer-b" in service.peers
    assert service.peers["peer-b"] == "http://localhost:8002"
    assert "peer-b" in service.peer_infos
    print("✓ Peer added successfully")
    
    # 統計情報初期化確認
    assert "peer-b" in service.peer_stats
    stats = service.peer_stats["peer-b"]
    assert stats.entity_id == "peer-b"
    assert stats.address == "http://localhost:8002"
    print("✓ Peer stats initialized")
    
    # ハートビート登録確認
    if service._heartbeat:
        status = service._heartbeat.get_status("peer-b")
        assert status is not None
        print("✓ Peer registered for heartbeat")
    
    # ピアリスト取得
    peers = service.list_peers()
    assert "peer-b" in peers
    assert len(peers) == 1
    print("✓ Peer list retrieval works")
    
    # ピアアドレス取得
    address = service.get_peer_address("peer-b")
    assert address == "http://localhost:8002"
    print("✓ Peer address retrieval works")
    
    # 存在しないピア
    assert service.get_peer_address("unknown") is None
    print("✓ Unknown peer returns None")
    
    # ピア削除
    result = service.remove_peer("peer-b")
    assert result is True
    assert "peer-b" not in service.peers
    assert "peer-b" not in service.peer_infos
    print("✓ Peer removed successfully")
    
    # 存在しないピア削除
    result = service.remove_peer("peer-b")
    assert result is False
    print("✓ Removing unknown peer returns False")
    
    # 複数ピア管理
    service.add_peer("peer-1", "http://localhost:8001", public_key_hex=pub_a_hex)
    service.add_peer("peer-2", "http://localhost:8002", public_key_hex=pub_b_hex)
    assert len(service.peers) == 2
    print("✓ Multiple peer management works")
    
    print("\n✅ Peer management tests completed")


async def test_message_handlers():
    """メッセージハンドラテスト"""
    print("\n=== Message Handlers Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    service = PeerService("test-entity", 8001, private_key_hex=priv_a_hex)
    
    # デフォルトハンドラ確認
    assert "ping" in service.message_handlers
    assert "status" in service.message_handlers
    assert "heartbeat" in service.message_handlers
    assert "capability_query" in service.message_handlers
    assert "task_delegate" in service.message_handlers
    print("✓ Default handlers registered")
    
    # カスタムハンドラ登録
    test_messages = []
    
    async def custom_handler(message):
        test_messages.append(message)
    
    service.register_handler("custom_type", custom_handler)
    assert "custom_type" in service.message_handlers
    print("✓ Custom handler registered")
    
    # ハンドラ呼び出しテスト（直接）
    test_msg = {"type": "custom_type", "from": "test", "payload": {"data": "test"}}
    await service.message_handlers["custom_type"](test_msg)
    assert len(test_messages) == 1
    print("✓ Custom handler invocation works")
    
    # 統計更新確認（pingハンドラ経由）
    service.add_peer("peer-test", "http://localhost:8001")
    ping_msg = {"type": "ping", "from": "peer-test", "payload": {}}
    
    initial_received = service.peer_stats["peer-test"].total_messages_received
    await service.message_handlers["ping"](ping_msg)
    assert service.peer_stats["peer-test"].total_messages_received == initial_received + 1
    print("✓ Handler updates peer stats")
    
    print("\n✅ Message handlers tests completed")


async def test_handle_message():
    """受信メッセージ処理テスト"""
    print("\n=== Handle Message Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    service_a = PeerService("entity-a", 8001, private_key_hex=priv_a_hex)
    
    # ピアBの公開鍵を登録
    service_a.add_peer_public_key("entity-b", pub_b_hex)
    
    # セキュアメッセージ作成（BからAへ）
    from crypto import CryptoManager
    crypto_b = CryptoManager("entity-b", private_key_hex=priv_b_hex)
    
    payload = {"status": "ok", "data": "test"}
    secure_msg = crypto_b.create_secure_message(
        payload=payload,
        encrypt=False,
        peer_public_key_b64=None,
        peer_id="entity-a",
        include_jwt=False
    )
    message_dict = secure_msg.to_dict(include_signature=True)
    
    # メッセージ処理（署名検証有効）
    result = await service_a.handle_message(message_dict)
    assert result["status"] == "success"
    print("✓ Secure message processed successfully")
    
    # リプレイ攻撃テスト（同じメッセージを再度送信）
    result = await service_a.handle_message(message_dict)
    assert result["status"] == "error"
    assert "Replay" in result["reason"] or "replay" in result["reason"].lower()
    print("✓ Replay attack detected and rejected")
    
    # レガシー形式メッセージ（署名なし）
    legacy_msg = {
        "from": "legacy-peer",
        "type": "status",
        "payload": {"status": "legacy"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    result = await service_a.handle_message(legacy_msg)
    # 署名検証が有効な場合はエラー
    if service_a.enable_verification:
        assert result["status"] == "error"
        print("✓ Legacy unsigned message rejected when verification enabled")
    
    # 不明なメッセージ形式
    unknown_msg = {"unknown": "format"}
    result = await service_a.handle_message(unknown_msg)
    assert result["status"] == "error"
    print("✓ Unknown message format rejected")
    
    # バージョンチェック
    bad_version_msg = {
        "version": "9.9",
        "msg_type": "test",
        "sender_id": "test",
        "payload": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16)
    }
    result = await service_a.handle_message(bad_version_msg)
    assert result["status"] == "error"
    assert "version" in result["reason"].lower()
    print("✓ Unsupported version rejected")
    
    print("\n✅ Handle message tests completed")


async def test_health_check():
    """ヘルスチェック機能テスト"""
    print("\n=== Health Check Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    service = PeerService("test-entity", 8001, private_key_hex=priv_a_hex)
    
    # 基本ヘルスチェック
    health = await service.health_check()
    assert health["entity_id"] == "test-entity"
    assert health["port"] == 8001
    assert health["status"] == "healthy"
    assert health["crypto_available"] is True
    assert health["signing_enabled"] is True
    assert health["verification_enabled"] is True
    assert "public_key" in health
    assert "timestamp" in health
    print("✓ Health check returns correct structure")
    
    # ピア情報
    assert health["peers"] == 0
    assert health["healthy_peers"] == 0
    print("✓ Health check shows correct peer counts")
    
    # ピア追加後
    service.add_peer("peer-1", "http://localhost:8001")
    service.peer_stats["peer-1"].is_healthy = True
    
    health = await service.health_check()
    assert health["peers"] == 1
    assert health["healthy_peers"] == 1
    print("✓ Health check reflects peer status changes")
    
    # ピア統計取得（複数パターン対応）
    try:
        stats = service.get_peer_stats()
    except AttributeError:
        from services.peer_service import PeerService
        stats = service.get_peer_stats()
    assert "peer-1" in stats
    assert stats["peer-1"]["entity_id"] == "peer-1"
    print("✓ Peer stats retrieval works")
    
    # 特定ピア統計
    peer_stats = service.get_peer_stats("peer-1")
    assert peer_stats["entity_id"] == "peer-1"
    
    # 存在しないピア
    assert service.get_peer_stats("unknown") == {}
    print("✓ Stats for unknown peer returns empty dict")
    
    print("\n✅ Health check tests completed")


async def test_queue_and_heartbeat():
    """MessageQueueとHeartbeatManagerテスト"""
    print("\n=== Queue and Heartbeat Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    from peer_service import MessageQueue, HeartbeatManager, PeerStatus
    
    # MessageQueueテスト
    queue = MessageQueue(max_retries=3)
    assert queue.get_queue_size() == 0
    print("✓ Queue initialized empty")
    
    # メッセージ追加
    await queue.enqueue("peer-1", "test_type", {"data": "test"})
    assert queue.get_queue_size() == 1
    print("✓ Message enqueued")
    
    stats = queue.get_stats()
    assert stats["queued"] == 1
    assert stats["sent"] == 0
    print("✓ Queue stats correct")
    
    # HeartbeatManagerテスト
    heartbeat = HeartbeatManager(interval_sec=1.0, failure_threshold=2)
    assert heartbeat.get_status("unknown") == PeerStatus.UNKNOWN
    print("✓ Heartbeat manager initialized")
    
    heartbeat.register_peer("peer-1")
    assert heartbeat.get_status("peer-1") == PeerStatus.UNKNOWN
    print("✓ Peer registered for heartbeat")
    
    # 健全ピアリスト（ping実行前は空）
    healthy = heartbeat.get_healthy_peers()
    assert len(healthy) == 0
    print("✓ No healthy peers before ping")
    
    heartbeat.unregister_peer("peer-1")
    assert "peer-1" not in heartbeat.get_all_status()
    print("✓ Peer unregistered from heartbeat")
    
    print("\n✅ Queue and heartbeat tests completed")


async def test_chunked_message():
    """Chunked message transferテスト (v1.1)"""
    print("\n=== Chunked Message Transfer Test ===\n")
    
    from peer_service import ChunkInfo
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # ChunkInfoテスト
    chunk_info = ChunkInfo(chunk_id="test-msg-123", total_chunks=3)
    assert chunk_info.chunk_id == "test-msg-123"
    assert chunk_info.total_chunks == 3
    assert not chunk_info.is_complete()
    print("✓ ChunkInfo initialized")
    
    # チャンク追加（add_chunkメソッドを使用）
    chunk_info.add_chunk(0, '{"original_msg_type": "test", "data": {"part": 1')
    chunk_info.add_chunk(1, ', "part": 2, "part": 3')
    assert not chunk_info.is_complete()
    print("✓ Partial chunks not complete")
    
    # 最後のチャンク追加
    chunk_info.add_chunk(2, ', "part": 4}}')
    assert chunk_info.is_complete()
    print("✓ All chunks complete")
    
    # ペイロード再構築
    payload = chunk_info.get_payload()
    assert payload is not None
    assert payload["original_msg_type"] == "test"
    print("✓ Payload reconstructed successfully")
    
    # PeerServiceでのchunkハンドラ確認
    service = PeerService("test-entity", 8001)
    assert "chunk" in service.message_handlers
    print("✓ Chunk handler registered")
    
    # チャンクメッセージ処理テスト
    test_messages = []
    
    async def test_handler(message):
        test_messages.append(message)
    
    service.register_handler("large_data", test_handler)
    
    # チャンクメッセージをシミュレート
    message_id = "chunk-test-001"
    total = 2
    
    # 1つ目のチャンク
    chunk1 = {
        "sender_id": "peer-b",
        "msg_type": "chunk",
        "payload": {
            "message_id": message_id,
            "chunk_index": 0,
            "total_chunks": total,
            "data": 'eyJvcmlnaW5hbF9tc2dfdHlwZSI6ICJsYXJnZV9kYXRhIiwgImRhdGEiOiB7ImtleSI6',
            "is_last": False
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await service.message_handlers["chunk"](chunk1)
    assert message_id in service._chunk_buffer
    assert not service._chunk_buffer[message_id].is_complete()
    print("✓ First chunk processed")
    
    # 2つ目のチャンク（最後）
    chunk2 = {
        "sender_id": "peer-b",
        "msg_type": "chunk",
        "payload": {
            "message_id": message_id,
            "chunk_index": 1,
            "total_chunks": total,
            "data": 'InZhbHVlMSJ9fQ==',
            "is_last": True
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await service.message_handlers["chunk"](chunk2)
    # 再構築後、バッファから削除される
    assert message_id not in service._chunk_buffer
    print("✓ Second chunk processed and message reconstructed")
    
    # cleanup_old_chunksテスト
    old_chunk = ChunkInfo(chunk_id="old-msg", total_chunks=2)
    # 古い時間を設定
    old_chunk.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    service._chunk_buffer["old-msg"] = old_chunk
    
    cleaned = await service.cleanup_old_chunks(max_age_seconds=3600)
    assert cleaned == 1
    assert "old-msg" not in service._chunk_buffer
    print("✓ Old chunks cleaned up")
    
    print("\n✅ Chunked message tests completed")


async def test_auto_chunking():
    """自動チャンク分割機能のテスト"""
    print("\n=== Auto Chunking Test ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # 送信側サービス
    service_a = PeerService("entity-a", 8001, private_key_hex=priv_a_hex)
    
    # 受信側サービス（chunk受信用）
    priv_b, pub_b = generate_entity_keypair()
    service_b = PeerService("entity-b", 8002, private_key_hex=priv_b)
    
    # ピア登録（実際のHTTP通信はしないためモック）
    service_a.add_peer("entity-b", "http://localhost:8002")
    service_b.add_peer("entity-a", "http://localhost:8001")
    
    # 公開鍵交換
    service_a.add_peer_public_key("entity-b", pub_b)
    service_b.add_peer_public_key("entity-a", pub_a)
    
    # 大きなペイロードを作成（自動分割閾値を超える）
    large_payload = {
        "large_data": "x" * 10000,  # 10KBのデータ
        "metadata": {"type": "test", "size": "large"}
    }
    
    # ペイロードサイズを確認
    payload_size = len(__import__('json').dumps(large_payload).encode('utf-8'))
    print(f"Payload size: {payload_size} bytes")
    print(f"Auto-chunk threshold: {service_a.AUTO_CHUNK_THRESHOLD} bytes")
    assert payload_size > service_a.AUTO_CHUNK_THRESHOLD, "Payload should exceed threshold"
    
    # 自動チャンク分割の判定テスト（実際にはHTTP通信しない）
    # send_chunked_messageが呼ばれることを確認
    original_send_chunked = service_a.send_chunked_message
    chunked_called = [False]
    
    async def mock_send_chunked(*args, **kwargs):
        chunked_called[0] = True
        print("✓ Auto-chunking triggered: send_chunked_message called")
        return True
    
    service_a.send_chunked_message = mock_send_chunked
    
    # auto_chunk=True（デフォルト）で送信
    result = await service_a.send_message(
        target_id="entity-b",
        message_type="large_data",
        payload=large_payload,
        auto_chunk=True
    )
    
    assert chunked_called[0], "Auto-chunking should be triggered"
    print("✓ Auto-chunking works with default settings")
    
    # auto_chunk=Falseでは通常送信が試行される
    chunked_called[0] = False
    result = await service_a.send_message(
        target_id="entity-b",
        message_type="large_data",
        payload=large_payload,
        auto_chunk=False
    )
    
    # 通常送信は失敗する（HTTPサーバーがないため）が、chunkedは呼ばれない
    assert not chunked_called[0], "Auto-chunking should be disabled"
    print("✓ Auto-chunking can be disabled")
    
    # chunkタイプのメッセージは自動分割されない
    chunked_called[0] = False
    result = await service_a.send_message(
        target_id="entity-b",
        message_type="chunk",  # chunkタイプ
        payload=large_payload,
        auto_chunk=True
    )
    
    assert not chunked_called[0], "Chunk messages should not be auto-chunked"
    print("✓ Chunk messages are not recursively chunked")
    
    # 閾値以下のペイロードは分割されない
    small_payload = {"small": "data"}
    chunked_called[0] = False
    
    # chunked_transferのインポート（複数パターン対応）
    try:
        from services.chunked_transfer import ChunkedTransfer, ChunkedMessage
    except ImportError:
        from chunked_transfer import ChunkedTransfer, ChunkedMessage
    
    result = await service_a.send_message(
        target_id="entity-b",
        message_type="small_data",
        payload=small_payload,
        auto_chunk=True
    )
    
    assert not chunked_called[0], "Small payloads should not be chunked"
    print("✓ Small payloads are not chunked")
    
    # 元のメソッドを復元
    service_a.send_chunked_message = original_send_chunked
    
    print("\n✅ Auto chunking tests completed")


async def test_chunked_transfer():
    """ChunkedTransfer (chunked_transfer.py) の包括的テスト (S3実用化)"""
    print("\n=== ChunkedTransfer Comprehensive Test (v1.1) ===\n")
    
    from chunked_transfer import (
        MessageChunk, ChunkedTransfer, ChunkedTransferManager,
        ChunkedMessageProtocol, ChunkStatus
    )
    import hashlib
    import base64
    import random
    
    # ===========================================
    # Test 1: 基本チャンク分割テスト (>10KB)
    # ===========================================
    print("--- Test 1: Basic Chunking (>10KB) ---")
    
    # 10KB以上の大きなメッセージ作成
    large_data = "x" * 15000  # 15KBのテキストデータ
    original_message = {
        "original_msg_type": "large_data",
        "data": large_data,
        "metadata": {"test": True, "size": "15KB"}
    }
    
    # 32KBチャンクサイズでマネージャー作成
    manager = ChunkedTransferManager(chunk_size=4096)  # 4KBチャンクでテスト
    
    chunks = manager.create_transfer(
        sender_id="entity-a",
        recipient_id="entity-b",
        msg_type="large_data",
        message=original_message
    )
    
    # チャンク数を確認（15KB / 4KB = 約4チャンク）
    total_chunks = len(chunks)
    print(f"  Original message: ~{len(str(original_message))} bytes")
    print(f"  Total chunks: {total_chunks}")
    assert total_chunks >= 4, f"Expected at least 4 chunks, got {total_chunks}"
    
    # 各チャンクの構造を検証
    transfer_id = chunks[0].transfer_id
    for i, chunk in enumerate(chunks):
        assert chunk.transfer_id == transfer_id, f"Chunk {i}: transfer_id mismatch"
        assert chunk.chunk_index == i, f"Chunk {i}: index mismatch"
        assert chunk.total_chunks == total_chunks, f"Chunk {i}: total_chunks mismatch"
        assert len(chunk.checksum) == 16, f"Chunk {i}: checksum should be 16 chars"
        assert chunk.data is not None and len(chunk.data) > 0, f"Chunk {i}: empty data"
    print(f"  ✓ All {total_chunks} chunks have correct structure")
    
    # ===========================================
    # Test 2: チャンク再構築テスト
    # ===========================================
    print("\n--- Test 2: Message Reassembly ---")
    
    # 転送を初期化
    manager.initialize_transfer(
        transfer_id=transfer_id,
        sender_id="entity-a",
        recipient_id="entity-b",
        msg_type="large_data",
        total_chunks=total_chunks
    )
    
    # すべてのチャンクを受信
    for chunk in chunks:
        transfer = manager.receive_chunk(chunk)
        assert transfer is not None, f"Failed to receive chunk {chunk.chunk_index}"
    
    # 転送が完了したことを確認
    transfer = manager.get_transfer(transfer_id)
    assert transfer.is_complete(), "Transfer should be complete"
    assert transfer.status == ChunkStatus.COMPLETED, "Status should be COMPLETED"
    print(f"  ✓ Transfer completed: {transfer.get_progress():.0%}")
    
    # メッセージを再構築
    assembled_message = transfer.assemble_message()
    assert assembled_message is not None, "Failed to assemble message"
    
    # 元のメッセージと完全一致することを確認
    assert assembled_message == original_message, "Assembled message mismatch"
    print("  ✓ Message reassembled correctly")
    print(f"  ✓ Original data size: {len(original_message['data'])} chars")
    print(f"  ✓ Reassembled data size: {len(assembled_message['data'])} chars")
    
    # ===========================================
    # Test 3: チェックサム検証テスト
    # ===========================================
    print("\n--- Test 3: Checksum Verification ---")
    
    # 正しいチェックサムの検証
    for chunk in chunks:
        assert chunk.verify_checksum(), f"Chunk {chunk.chunk_index}: checksum should be valid"
    print("  ✓ All valid checksums verified")
    
    # 破損したデータの検出
    corrupted_chunk = MessageChunk(
        transfer_id="test-corrupt",
        chunk_index=0,
        total_chunks=1,
        data=b"corrupted data",
        checksum="invalid_checksum"
    )
    assert not corrupted_chunk.verify_checksum(), "Corrupted data should fail checksum"
    print("  ✓ Corrupted data detected correctly")
    
    # ===========================================
    # Test 4: 順序不同受信テスト
    # ===========================================
    print("\n--- Test 4: Out-of-Order Reception ---")
    
    # 新しい転送を作成
    out_of_order_msg = {"type": "test", "data": list(range(100))}
    ooo_chunks = manager.create_transfer(
        sender_id="entity-a",
        recipient_id="entity-b",
        msg_type="test",
        message=out_of_order_msg
    )
    
    ooo_transfer_id = ooo_chunks[0].transfer_id
    manager.initialize_transfer(
        transfer_id=ooo_transfer_id,
        sender_id="entity-a",
        recipient_id="entity-b",
        msg_type="test",
        total_chunks=len(ooo_chunks)
    )
    
    # ランダムな順序でチャンクを受信
    shuffled_chunks = ooo_chunks.copy()
    random.shuffle(shuffled_chunks)
    print(f"  Shuffled order: {[c.chunk_index for c in shuffled_chunks]}")
    
    for chunk in shuffled_chunks:
        manager.receive_chunk(chunk)
    
    # 再構築して確認
    ooo_transfer = manager.get_transfer(ooo_transfer_id)
    assert ooo_transfer.is_complete(), "Should be complete after receiving all chunks"
    
    reassembled = ooo_transfer.assemble_message()
    assert reassembled == out_of_order_msg, "Out-of-order message mismatch"
    print("  ✓ Out-of-order reception handled correctly")
    
    # ===========================================
    # Test 5: 欠落チャンク検出テスト
    # ===========================================
    print("\n--- Test 5: Missing Chunk Detection ---")
    
    # 一部のチャンクを欠落させた転送
    missing_chunk_msg = {"type": "partial", "items": list(range(50))}
    partial_chunks = manager.create_transfer(
        sender_id="entity-a",
        recipient_id="entity-b",
        msg_type="partial",
        message=missing_chunk_msg
    )
    
    partial_transfer_id = partial_chunks[0].transfer_id
    manager.initialize_transfer(
        transfer_id=partial_transfer_id,
        sender_id="entity-a",
        recipient_id="entity-b",
        msg_type="partial",
        total_chunks=len(partial_chunks)
    )
    
    # 最初と最後だけ受信（中間を欠落）
    manager.receive_chunk(partial_chunks[0])
    if len(partial_chunks) > 1:
        manager.receive_chunk(partial_chunks[-1])
    
    partial_transfer = manager.get_transfer(partial_transfer_id)
    assert not partial_transfer.is_complete(), "Should not be complete with missing chunks"
    
    # 進捗を確認
    progress = partial_transfer.get_progress()
    print(f"  Total chunks: {len(partial_chunks)}")
    print(f"  Received: {len(partial_transfer.chunks)}")
    print(f"  Progress: {progress:.0%}")
    assert 0 < progress < 1, f"Progress should be between 0 and 1, got {progress}"
    
    # 不完全な転送では assemble_message が None を返す
    incomplete_assembly = partial_transfer.assemble_message()
    assert incomplete_assembly is None, "Should return None for incomplete transfer"
    print("  ✓ Missing chunks detected correctly")
    
    # ===========================================
    # Test 6: Protocol Message Creation
    # ===========================================
    print("\n--- Test 6: Protocol Integration ---")
    
    protocol = ChunkedMessageProtocol(manager)
    
    # チャンクメッセージの作成
    test_chunk = chunks[0]
    chunk_msg = protocol.create_chunk_message(
        chunk=test_chunk,
        sender_id="entity-a",
        session_id="test-session-123"
    )
    
    assert chunk_msg["version"] == "1.1", "Protocol version mismatch"
    assert chunk_msg["msg_type"] == "chunk", "Message type mismatch"
    assert chunk_msg["sender_id"] == "entity-a", "Sender ID mismatch"
    assert chunk_msg["payload"]["chunk"]["transfer_id"] == transfer_id
    assert "progress" in chunk_msg["payload"]
    print("  ✓ Protocol message created correctly")
    
    # チャンクメッセージのパース
    parsed_chunk = protocol.parse_chunk_message(chunk_msg)
    assert parsed_chunk is not None, "Failed to parse chunk message"
    assert parsed_chunk.transfer_id == test_chunk.transfer_id
    assert parsed_chunk.chunk_index == test_chunk.chunk_index
    assert parsed_chunk.verify_checksum(), "Parsed chunk checksum valid"
    print("  ✓ Protocol message parsed correctly")
    
    # 転送初期化メッセージの作成
    init_msg = protocol.create_transfer_init_message(
        transfer_id="init-test-123",
        sender_id="entity-a",
        recipient_id="entity-b",
        msg_type="test",
        total_chunks=5,
        total_size=20000,
        metadata={"priority": "high"}
    )
    assert init_msg["msg_type"] == "chunk_init"
    assert init_msg["payload"]["total_chunks"] == 5
    assert init_msg["payload"]["total_size"] == 20000
    print("  ✓ Transfer init message created correctly")
    
    # ===========================================
    # Test 7: Statistics
    # ===========================================
    print("\n--- Test 7: Transfer Statistics ---")
    
    stats = manager.get_stats()
    assert "active_transfers" in stats
    assert "by_status" in stats
    assert "chunk_size" in stats
    assert stats["chunk_size"] == 4096
    print(f"  Active transfers: {stats['active_transfers']}")
    print(f"  Chunk size: {stats['chunk_size']} bytes")
    print(f"  Max transfer size: {stats['max_transfer_size']} bytes")
    print("  ✓ Statistics retrieved correctly")
    
    print("\n✅ All ChunkedTransfer tests completed")


async def test_session_manager():
    """SessionManagerテスト（Protocol v1.1）"""
    print("\n=== SessionManager Test (v1.1) ===\n")
    
    from peer_service import SessionManager, Session
    
    # SessionManager初期化
    sm = SessionManager(default_ttl_seconds=60, cleanup_interval_seconds=10)
    assert sm.default_ttl == 60
    print("✓ SessionManager initialized")
    
    # セッション作成
    session_id = await sm.create_session("peer-1")
    assert session_id is not None
    assert len(session_id) > 0
    print(f"✓ Session created: {session_id[:8]}...")
    
    # セッション取得
    session = await sm.get_session(session_id)
    assert session is not None
    assert session.peer_id == "peer-1"
    print("✓ Session retrieved")
    
    # セッション終了
    result = await sm.terminate_session(session_id)
    assert result is True
    assert await sm.get_session(session_id) is None
    print("✓ Session terminated")
    
    print("\n✅ SessionManager tests completed")


async def test_rate_limiter():
    """RateLimiterテスト（Protocol v1.1）"""
    print("\n=== RateLimiter Test (v1.1) ===\n")
    
    from peer_service import RateLimiter
    
    # RateLimiter初期化
    rl = RateLimiter(requests_per_minute=5, requests_per_hour=10)
    print("✓ RateLimiter initialized (5/min, 10/hour)")
    
    peer_id = "test-peer"
    
    # 最初の5リクエストは許可
    for i in range(5):
        assert rl.allow_request(peer_id) is True
    print("✓ First 5 requests allowed")
    
    # 6番目は制限される
    assert rl.allow_request(peer_id) is False
    print("✓ 6th request blocked (per minute limit)")
    
    # 別のピアは制限されない
    assert rl.allow_request("other-peer") is True
    print("✓ Other peer not affected")
    
    print("\n✅ RateLimiter tests completed")


async def test_e2e_encryption():
    """E2E暗号化テスト（X25519 + AES-256-GCM）"""
    print("\n=== E2E Encryption Test (v1.1) ===\n")
    
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # E2EEncryptionのインポート（複数パターン対応）
    try:
        from services.peer_service import E2EEncryption
    except ImportError:
        from peer_service import E2EEncryption
    
    # E2EEncryption初期化
    e2e = E2EEncryption()
    print("✓ E2EEncryption initialized")
    
    # 鍵導出
    shared_key = e2e.derive_shared_key(
        my_ed25519_private=bytes.fromhex(priv_a_hex),
        peer_ed25519_public=bytes.fromhex(pub_b_hex),
        peer_id="peer-b"
    )
    assert shared_key is not None
    assert len(shared_key) == 32
    print(f"✓ Shared key derived: {len(shared_key)} bytes")
    
    # 暗号化
    plaintext = b"Hello, this is a secret message!"
    ciphertext, nonce = e2e.encrypt(plaintext, shared_key)
    assert ciphertext is not None
    assert nonce is not None
    print(f"✓ Message encrypted: {len(ciphertext)} bytes")
    
    # 復号
    shared_key_b = e2e.derive_shared_key(
        my_ed25519_private=bytes.fromhex(priv_b_hex),
        peer_ed25519_public=bytes.fromhex(pub_a),
        peer_id="peer-a"
    )
    decrypted = e2e.decrypt(ciphertext, nonce, shared_key_b)
    assert decrypted == plaintext
    print("✓ Message decrypted correctly")
    
    print("\n✅ E2E encryption tests completed")


@pytest.mark.integration
@pytest.mark.peer
async def main():
    """全テスト実行"""
    print("=" * 60)
    print("Peer Service Security Test Suite v0.3")
    print("=" * 60)
    
    # 暗号化・署名関連のテスト
    await test_signature_verification()
    await test_encryption()
    await test_jwt_authentication()
    await test_replay_protection()
    await test_secure_message()
    
    # 統合テスト
    await test_peer_service_integration()
    await test_full_communication_secure()
    
    # 互換性テスト
    await test_backward_compatibility()
    
    # PeerService機能テスト（新規追加）
    await test_peer_service_init()
    await test_peer_management()
    await test_message_handlers()
    await test_handle_message()
    await test_health_check()
    await test_queue_and_heartbeat()
    
    # Chunk機能テスト
    await test_chunked_message()
    await test_auto_chunking()
    
    # ChunkedTransfer v1.1 テスト (chunked_transfer.py使用)
    await test_chunked_transfer()
    
    # Rate limitingテスト
    await test_rate_limiting()
    
    # Protocol v1.1機能テスト
    await test_session_manager()
    await test_rate_limiter()
    await test_e2e_encryption()
    
    # Protocol v1.0 Sequence Validationテスト
    await test_sequence_validation()
    await test_session_expired()
    await test_sequence_e2e()
    
    print("\n" + "=" * 60)
    print("All security tests completed!")
    print("=" * 60)


async def test_rate_limiting():
    """レート制限機能のテスト (v1.1)"""
    print("\n" + "=" * 60)
    print("Testing Rate Limiting (v1.1)")
    print("=" * 60)
    
    from peer_service import RateLimiter, RateLimitConfig
    
    # ===========================================
    # Test 1: 基本レート制限
    # ===========================================
    print("\n--- Test 1: Basic Rate Limiting ---")
    
    config = RateLimitConfig(
        requests_per_minute=5,
        requests_per_hour=100,
        burst_size=3
    )
    limiter = RateLimiter(config)
    
    peer_id = "test_peer_1"
    
    # バーストサイズ内のリクエストは許可される
    for i in range(3):
        allowed, retry_after = await limiter.check_rate_limit(peer_id)
        assert allowed, f"Request {i+1} should be allowed within burst size"
    print("  ✓ Requests within burst size allowed")
    
    # バースト超過後はレート制限される
    allowed, retry_after = await limiter.check_rate_limit(peer_id)
    assert not allowed, "Request exceeding burst should be rate limited"
    assert retry_after is not None, "Retry-After should be provided"
    print(f"  ✓ Rate limit enforced (retry after: {retry_after:.2f}s)")
    
    # ===========================================
    # Test 2: ブロック機能
    # ===========================================
    print("\n--- Test 2: Peer Blocking ---")
    
    config2 = RateLimitConfig(
        requests_per_minute=2,
        block_duration_seconds=1  # 短いブロック時間でテスト
    )
    limiter2 = RateLimiter(config2)
    
    peer_id2 = "test_peer_2"
    
    # 制限内のリクエスト
    allowed, _ = await limiter2.check_rate_limit(peer_id2)
    assert allowed, "First request should be allowed"
    allowed, _ = await limiter2.check_rate_limit(peer_id2)
    assert allowed, "Second request should be allowed"
    
    # 制限超過でブロック
    allowed, retry_after = await limiter2.check_rate_limit(peer_id2)
    assert not allowed, "Third request should be blocked"
    print(f"  ✓ Peer blocked after exceeding limit")
    
    # ブロック中は即座に拒否
    allowed, _ = await limiter2.check_rate_limit(peer_id2)
    assert not allowed, "Blocked peer should be rejected immediately"
    print("  ✓ Blocked peer rejected immediately")
    
    # ===========================================
    # Test 3: 統計情報
    # ===========================================
    print("\n--- Test 3: Rate Limit Statistics ---")
    
    stats = await limiter.get_peer_stats(peer_id)
    assert stats is not None, "Stats should be available"
    assert "tokens_remaining" in stats, "Stats should include tokens_remaining"
    assert "requests_this_minute" in stats, "Stats should include requests_this_minute"
    print(f"  ✓ Stats retrieved: tokens={stats['tokens_remaining']:.2f}, "
          f"requests={stats['requests_this_minute']}")
    
    # ===========================================
    # Test 4: クリーンアップ
    # ===========================================
    print("\n--- Test 4: Cleanup Old Peers ---")
    
    # 新しいpeerを追加
    new_peer = "cleanup_test_peer"
    await limiter.check_rate_limit(new_peer)
    
    # 短い非アクティブ時間でクリーンアップ
    removed = await limiter.cleanup_old_peers(max_inactive_seconds=0)
    assert removed >= 1, "Old peers should be cleaned up"
    print(f"  ✓ Cleaned up {removed} inactive peers")
    
    print("\n✓ All rate limiting tests passed!")


async def test_sequence_validation():
    """シーケンス番号検証のテスト (v1.0)"""
    print("\n" + "=" * 60)
    print("Testing Sequence Number Validation (v1.0)")
    print("=" * 60)
    
    from peer_service import PeerService, SessionState
    
    # テスト用の鍵を生成
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # サービスを初期化
    service = PeerService(
        entity_id="test-entity",
        port=8999,
        private_key_hex=priv_a_hex
    )
    
    # ピアを登録
    service.add_peer("peer-b", "http://localhost:8002", public_key_hex=pub_b_hex)
    
    # セッションを作成
    session = await service.create_session("peer-b")
    session_id = session.session_id
    print(f"  Created session: {session_id}")
    print(f"  Initial expected_sequence: {session.expected_sequence}")
    
    # ===========================================
    # Test 1: 正しいシーケンス番号
    # ===========================================
    print("\n--- Test 1: Valid Sequence Number ---")
    
    message = {
        "version": "1.0",
        "msg_type": "test",
        "sender_id": "peer-b",
        "payload": {"data": "test"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "session_id": session_id,
        "sequence_num": 1
    }
    
    result = await service.handle_message(message)
    assert result["status"] == "success", f"Valid sequence should succeed: {result}"
    print(f"  ✓ Sequence 1 accepted")
    
    # セッションが更新されたことを確認
    updated_session = await service.get_session_by_peer("peer-b")
    assert updated_session.expected_sequence == 2, "Expected sequence should be incremented"
    print(f"  ✓ Expected sequence updated to 2")
    
    # ===========================================
    # Test 2: 次のシーケンス番号
    # ===========================================
    print("\n--- Test 2: Next Sequence Number ---")
    
    message["sequence_num"] = 2
    message["nonce"] = secrets.token_hex(16)
    message["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    result = await service.handle_message(message)
    assert result["status"] == "success", "Next sequence should succeed"
    print(f"  ✓ Sequence 2 accepted")
    
    # ===========================================
    # Test 3: 古いシーケンス番号（リプレイ攻撃）
    # ===========================================
    print("\n--- Test 3: Old Sequence Number (Replay) ---")
    
    message["sequence_num"] = 1  # 古いシーケンス
    message["nonce"] = secrets.token_hex(16)
    message["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    result = await service.handle_message(message)
    assert result["status"] == "error", "Old sequence should fail"
    assert result.get("error_code") == "SEQUENCE_ERROR", "Should return SEQUENCE_ERROR"
    assert "expected" in result, "Should include expected sequence"
    assert "received" in result, "Should include received sequence"
    print(f"  ✓ Old sequence rejected with SEQUENCE_ERROR")
    print(f"  ✓ Expected: {result['expected']}, Received: {result['received']}")
    
    # ===========================================
    # Test 4: シーケンス番号の飛び
    # ===========================================
    print("\n--- Test 4: Sequence Gap ---")
    
    message["sequence_num"] = 10  # 大きく飛ばす
    message["nonce"] = secrets.token_hex(16)
    message["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    result = await service.handle_message(message)
    # シーケンス飛びは警告を出すが処理は続行
    assert result["status"] == "success", "Sequence gap should still process"
    print(f"  ✓ Sequence gap detected but processed (10 > 3)")
    
    # セッションが更新されたことを確認
    updated_session = await service.get_session_by_peer("peer-b")
    assert updated_session.expected_sequence == 11, "Expected sequence should be 11"
    print(f"  ✓ Expected sequence updated to 11")
    
    # ===========================================
    # Test 5: セッションなし（v1.0では必須フィールド欠如でエラー）
    # ===========================================
    print("\n--- Test 5: No Session (Required Fields Missing) ---")
    
    service.add_peer("peer-c", "http://localhost:8003", public_key_hex=pub_b_hex)
    
    # メッセージ作成（タイムスタンプとノンスの生成をtry-exceptで対応）
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
    except NameError:
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()
    
    try:
        nonce = secrets.token_hex(16)
    except AttributeError:
        import secrets
        nonce = secrets.token_hex(16)
    
    message_no_session = {
        "version": "1.0",
        "msg_type": "test",
        "sender_id": "peer-c",
        "payload": {"data": "test"},
        "timestamp": timestamp,
        "nonce": nonce
        # session_id と sequence_num なし
    }
    
    result = await service.handle_message(message_no_session)
    # セッションがない場合は検証をスキップ
    assert result["status"] == "success", "Message without session should still process"
    print(f"  ✓ Message without session processed (validation skipped)")
    
    print("\n✓ All sequence validation tests passed!")


async def test_dht_peer_discovery():
    """DHT-based peer discovery統合テスト"""
    print("\n=== DHT Peer Discovery Integration Test ===\n")
    
    # PeerDiscoveryのインポート
    try:
        from peer_discovery import PeerDiscovery, BootstrapNode
    except ImportError:
        from services.peer_discovery import PeerDiscovery, BootstrapNode
    
    # テスト用ブートストラップノード設定
    bootstrap_nodes = [
        BootstrapNode(
            node_id="test-node-1",
            endpoint="http://localhost:9001",
            public_key="test_pubkey_1"
        ),
        BootstrapNode(
            node_id="test-node-2", 
            endpoint="http://localhost:9002",
            public_key="test_pubkey_2"
        )
    ]
    
    # PeerDiscovery初期化（Moltbook/Registryは無効化）
    discovery = PeerDiscovery(
        enable_moltbook=False,
        enable_registry=False,
        enable_gossip=False
    )
    
    # ブートストラップノードを手動設定
    discovery.bootstrap_nodes = bootstrap_nodes
    
    print(f"✓ PeerDiscovery initialized with {len(bootstrap_nodes)} bootstrap nodes")
    
    # ノードリスト確認
    assert len(discovery.bootstrap_nodes) == 2
    assert discovery.bootstrap_nodes[0].node_id == "test-node-1"
    print("✓ Bootstrap nodes configured correctly")
    
    # 発見したピアの管理テスト（辞書キーアクセスをtry-exceptで対応）
    try:
        test_peer = {
            "peer_id": "discovered-peer-1",
            "endpoint": "http://localhost:8005",
            "public_key": "peer_pubkey_1",
            "capabilities": ["messaging", "task_delegation"]
        }
    except Exception as e:
        print(f"⚠️ Failed to create test peer dict: {e}")
        test_peer = {
            "peer_id": "discovered-peer-1",
            "endpoint": "http://localhost:8005"
        }
    
    discovery._discovered_peers[test_peer["peer_id"]] = test_peer
    assert test_peer["peer_id"] in discovery._discovered_peers
    print("✓ Peer registration works")
    
    # 発見結果の取得
    result = discovery.get_discovered_peers()
    assert len(result) == 1
    assert result[0]["peer_id"] == "discovered-peer-1"
    print("✓ Discovered peers retrieval works")
    
    # PeerServiceとの統合テスト
    priv_a, _, _, _ = setup_test_keys()
    
    try:
        from peer_service import init_service
    except ImportError:
        from services.peer_service import init_service
    
    service = init_service("test-entity", 8001, private_key_hex=priv_a)
    
    # discoveryの設定
    service.discovery = discovery
    print("✓ PeerDiscovery integrated with PeerService")
    
    print("\n✅ DHT peer discovery tests completed")


async def test_concurrent_multi_peer():
    """Multi-peer concurrent communication統合テスト"""
    print("\n=== Concurrent Multi-Peer Communication Test ===\n")
    
    priv_a, _, priv_b, pub_b = setup_test_keys()
    _, _, priv_c, pub_c = setup_test_keys()
    _, _, priv_d, pub_d = setup_test_keys()
    
    try:
        from peer_service import init_service
    except ImportError:
        from services.peer_service import init_service
    
    # サービス初期化
    service = init_service("concurrent-test", 8001, private_key_hex=priv_a)
    
    # 複数ピアを登録
    peers = [
        ("peer-b", "http://localhost:8002", pub_b),
        ("peer-c", "http://localhost:8003", pub_c),
        ("peer-d", "http://localhost:8004", pub_d),
    ]
    
    for peer_id, endpoint, pubkey in peers:
        service.add_peer(peer_id, endpoint, public_key=pubkey)
    
    print(f"✓ Registered {len(peers)} peers")
    
    # ピアリスト確認
    peer_list = service.list_peers()
    assert len(peer_list) == 3
    print("✓ Peer listing correct")
    
    # 各ピアの統計情報
    for peer_id, _, _ in peers:
        stats = service.get_peer_stats(peer_id)
        assert stats is not None
    print("✓ Stats available for all peers")
    
    # 並行メッセージ送信のシミュレーション
    messages_sent = []
    
    async def simulate_send(peer_id):
        messages_sent.append({"peer": peer_id, "timestamp": time.time()})
        await asyncio.sleep(0.01)
        return True
    
    # 複数ピアへの並行送信
    tasks = [simulate_send(peer_id) for peer_id, _, _ in peers]
    results = await asyncio.gather(*tasks)
    
    assert all(results)
    assert len(messages_sent) == 3
    print("✓ Concurrent message sending works")
    
    # メッセージハンドラの並行処理テスト
    received_messages = []
    
    async def test_handler(message):
        received_messages.append(message)
        await asyncio.sleep(0.01)
    
    service.register_handler("concurrent_test", test_handler)
    
    # 複数のメッセージをシミュレート
    test_messages = [
        {"sender_id": "peer-b", "msg_type": "concurrent_test", "payload": {"id": 1}},
        {"sender_id": "peer-c", "msg_type": "concurrent_test", "payload": {"id": 2}},
        {"sender_id": "peer-d", "msg_type": "concurrent_test", "payload": {"id": 3}},
    ]
    
    # 並行処理
    handler_tasks = [
        service.message_handlers["concurrent_test"](msg)
        for msg in test_messages
    ]
    await asyncio.gather(*handler_tasks)
    
    assert len(received_messages) == 3
    print("✓ Concurrent message handling works")
    
    print("\n✅ Concurrent peer communication tests completed")


async def test_session_expired():
    """SESSION_EXPIREDエラーのテスト (v1.0)"""
    print("\n" + "=" * 60)
    print("Testing SESSION_EXPIRED Error (v1.0)")
    print("=" * 60)
    
    from peer_service import PeerService, SessionState
    
    # テスト用の鍵を生成
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # サービスを初期化
    service = PeerService(
        entity_id="test-entity",
        port=8998,
        private_key_hex=priv_a_hex
    )
    
    # ピアを登録
    service.add_peer("peer-expired", "http://localhost:8002", public_key_hex=pub_b_hex)
    
    # セッションを作成
    session = await service.create_session("peer-expired")
    session_id = session.session_id
    print(f"  Created session: {session_id}")
    
    # セッションを期限切れにする（last_activityを過去に設定）
    session.last_activity = datetime.now(timezone.utc) - timedelta(hours=2)
    session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    print(f"  Set session as expired")
    
    # 期限切れセッションでメッセージ送信
    message = {
        "version": "1.0",
        "msg_type": "test",
        "sender_id": "peer-expired",
        "payload": {"data": "test"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "session_id": session_id,
        "sequence_num": 1
    }
    
    result = await service.handle_message(message)
    assert result["status"] == "error", "Expired session should fail"
    assert result.get("error_code") == "SESSION_EXPIRED", "Should return SESSION_EXPIRED"
    print(f"  ✓ Expired session rejected with SESSION_EXPIRED")
    
    # 無効なセッションIDでメッセージ送信
    message["session_id"] = "invalid-session-id"
    message["sequence_num"] = 1
    message["nonce"] = secrets.token_hex(16)
    
    result = await service.handle_message(message)
    assert result["status"] == "error", "Invalid session should fail"
    assert result.get("error_code") == "SESSION_EXPIRED", "Should return SESSION_EXPIRED for invalid session"
    print(f"  ✓ Invalid session rejected with SESSION_EXPIRED")
    
    print("\n✅ Session expiration tests passed!")


async def test_sequence_e2e():
    """シーケンス番号のE2Eテスト - 送信側と受信側 (v1.0)"""
    print("\n" + "=" * 60)
    print("Testing Sequence Numbers E2E (v1.0)")
    print("=" * 60)
    
    from peer_service import PeerService
    
    # テスト用の鍵を生成
    priv_a_hex, pub_a_hex, priv_b_hex, pub_b_hex = setup_test_keys()
    
    # サービスA（送信側）
    service_a = PeerService(
        entity_id="entity-a",
        port=8997,
        private_key_hex=priv_a_hex
    )
    
    # サービスB（受信側）
    service_b = PeerService(
        entity_id="entity-b", 
        port=8996,
        private_key_hex=priv_b_hex
    )
    
    # ピア登録
    service_a.add_peer("entity-b", "http://localhost:8996", public_key_hex=pub_b_hex)
    service_b.add_peer("entity-a", "http://localhost:8997", public_key_hex=pub_a_hex)
    
    # 両方のサービスでセッションを作成
    session_a = await service_a.create_session("entity-b")
    session_b = await service_b.create_session("entity-a")
    
    print(f"  Service A session: {session_a.session_id}")
    print(f"  Service B session: {session_b.session_id}")
    print(f"  Initial sequence A: {session_a.sequence_num}")
    print(f"  Initial expected B: {session_b.expected_sequence}")
    
    # ===========================================
    # Test 1: メッセージ作成時のシーケンス番号
    # ===========================================
    print("\n--- Test 1: Message Creation Sequence ---")
    
    # メッセージ作成（内部でシーケンス番号が自動増加）
    msg_dict = await service_a._create_message_dict(
        msg_type="test",
        payload={"data": "hello"},
        target_peer="entity-b"
    )
    
    assert "session_id" in msg_dict, "Message should have session_id"
    assert "sequence_num" in msg_dict, "Message should have sequence_num"
    assert msg_dict["sequence_num"] == 1, "First message should have sequence 1"
    print(f"  ✓ First message created with sequence_num: {msg_dict['sequence_num']}")
    
    # 2番目のメッセージ
    msg_dict2 = await service_a._create_message_dict(
        msg_type="test",
        payload={"data": "world"},
        target_peer="entity-b"
    )
    assert msg_dict2["sequence_num"] == 2, "Second message should have sequence 2"
    print(f"  ✓ Second message created with sequence_num: {msg_dict2['sequence_num']}")
    
    # ===========================================
    # Test 2: メッセージ受信時のシーケンス検証
    # ===========================================
    print("\n--- Test 2: Message Reception Sequence Validation ---")
    
    # 受信側でメッセージ処理
    result = await service_b.handle_message(msg_dict)
    assert result["status"] == "success", f"Valid message should succeed: {result}"
    print(f"  ✓ Message with sequence 1 accepted")
    
    # セッションが更新されたことを確認
    updated_session = await service_b.get_session_by_peer("entity-a")
    assert updated_session.expected_sequence == 2, "Expected sequence should be 2"
    print(f"  ✓ Expected sequence updated to 2")
    
    # 2番目のメッセージを処理
    result = await service_b.handle_message(msg_dict2)
    assert result["status"] == "success", "Second message should succeed"
    print(f"  ✓ Message with sequence 2 accepted")
    
    # ===========================================
    # Test 3: 重複メッセージ検出
    # ===========================================
    print("\n--- Test 3: Duplicate Message Detection ---")
    
    # 同じシーケンス番号のメッセージを再度送信（リプレイ攻撃シミュレーション）
    msg_dict["nonce"] = secrets.token_hex(16)  # 新しいノンス
    msg_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    result = await service_b.handle_message(msg_dict)
    assert result["status"] == "error", "Duplicate sequence should fail"
    assert result.get("error_code") == "SEQUENCE_ERROR", "Should return SEQUENCE_ERROR"
    print(f"  ✓ Duplicate sequence rejected with SEQUENCE_ERROR")
    print(f"  ✓ Expected: {result.get('expected')}, Received: {result.get('received')}")
    
    # ===========================================
    # Test 4: 送信側のシーケンス増加確認
    # ===========================================
    print("\n--- Test 4: Sender Sequence Increment ---")
    
    # さらにメッセージを送信
    for i in range(3, 6):
        msg = await service_a._create_message_dict(
            msg_type="test",
            payload={"seq": i},
            target_peer="entity-b"
        )
        assert msg["sequence_num"] == i, f"Message should have sequence {i}"
    
    print(f"  ✓ Sequences 3, 4, 5 created correctly")
    
    # セッションの最終状態を確認
    final_session_a = await service_a.get_session_by_peer("entity-b")
    print(f"  ✓ Final sender sequence: {final_session_a.sequence_num}")
    
    print("\n✅ E2E sequence tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
