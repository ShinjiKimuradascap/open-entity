#!/usr/bin/env python3
"""
API Server統合テスト
署名検証機能のエンドポインドテスト
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone
import secrets

# FastAPI TestClient使用を試行
try:
    from fastapi.testclient import TestClient
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("⚠️ FastAPI not available for integration testing")

from api_server import app, registry
from crypto import KeyPair, MessageSigner, generate_keypair


def test_health_endpoint():
    """ヘルスチェックエンドポイントテスト"""
    print("\n=== Health Endpoint Test ===")
    
    if not FASTAPI_AVAILABLE:
        print("⚠️ Skipped: FastAPI not available")
        return
    
    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    assert data["status"] == "healthy", f"Expected healthy status"
    assert "version" in data, "Response should contain version"
    print(f"✅ Health check: {data['status']}, version={data['version']}")


def test_register_agent():
    """エージェント登録エンドポイントテスト"""
    print("\n=== Register Agent Test ===")
    
    if not FASTAPI_AVAILABLE:
        print("⚠️ Skipped: FastAPI not available")
        return
    
    client = TestClient(app)
    
    # 新規エージェント登録
    response = client.post("/register", json={
        "entity_id": "test-entity-1",
        "name": "Test Entity",
        "endpoint": "http://localhost:8001",
        "capabilities": ["test", "messaging"]
    })
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["status"] == "ok", f"Expected ok status"
    assert data["entity_id"] == "test-entity-1"
    print(f"✅ Agent registered: {data['entity_id']}")


def test_discover_agents():
    """エージェント発見エンドポイントテスト"""
    print("\n=== Discover Agents Test ===")
    
    if not FASTAPI_AVAILABLE:
        print("⚠️ Skipped: FastAPI not available")
        return
    
    client = TestClient(app)
    
    # 事前にエージェントを登録
    client.post("/register", json={
        "entity_id": "discoverable-entity",
        "name": "Discoverable Entity",
        "endpoint": "http://localhost:8002",
        "capabilities": ["discovery", "test"]
    })
    
    # 全エージェント一覧
    response = client.get("/discover")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    print(f"✅ Discovered {len(data['agents'])} agents")
    
    # 機能フィルタリング
    response = client.get("/discover?capability=test")
    assert response.status_code == 200
    data = response.json()
    print(f"✅ Filtered agents with 'test' capability: {len(data['agents'])}")


def test_register_public_key():
    """公開鍵登録エンドポイントテスト"""
    print("\n=== Register Public Key Test ===")
    
    if not FASTAPI_AVAILABLE:
        print("⚠️ Skipped: FastAPI not available")
        return
    
    # 鍵ペア生成
    kp = generate_keypair()
    public_key_hex = kp.get_public_key_hex()
    
    client = TestClient(app)
    
    # 公開鍵登録
    response = client.post("/register-key", json={
        "entity_id": "signed-entity",
        "public_key": public_key_hex
    })
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["status"] == "ok"
    assert data["entity_id"] == "signed-entity"
    print(f"✅ Public key registered: {data['public_key_preview']}")


def test_message_with_signature():
    """署名付きメッセージ受信テスト"""
    print("\n=== Message with Signature Test ===")
    
    if not FASTAPI_AVAILABLE:
        print("⚠️ Skipped: FastAPI not available")
        return
    
    # 鍵ペア生成と公開鍵登録
    kp = generate_keypair()
    signer = MessageSigner(kp)
    
    client = TestClient(app)
    
    # 公開鍵登録
    client.post("/register-key", json={
        "entity_id": "sender-entity",
        "public_key": kp.get_public_key_hex()
    })
    
    # 署名付きメッセージ作成
    from crypto import SecureMessage
    msg = SecureMessage(
        version="0.3",
        msg_type="test_message",
        sender_id="sender-entity",
        payload={"content": "Hello, World!"}
    )
    msg.sign(signer)
    
    # メッセージ送信
    response = client.post("/message", json={
        "version": msg.version,
        "msg_type": msg.msg_type,
        "sender_id": msg.sender_id,
        "payload": msg.payload,
        "timestamp": msg.timestamp,
        "nonce": msg.nonce,
        "signature": msg.signature
    })
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["status"] == "received"
    assert data["verified"] is True, "Message should be verified"
    print(f"✅ Signed message received and verified: {data['verified']}")


def test_message_without_signature():
    """署名なしメッセージ受信テスト（v0.3互換）"""
    print("\n=== Message without Signature Test ===")
    
    if not FASTAPI_AVAILABLE:
        print("⚠️ Skipped: FastAPI not available")
        return
    
    client = TestClient(app)
    
    # 署名なしメッセージ（開発段階では許容される）
    response = client.post("/message", json={
        "version": "0.3",
        "msg_type": "test_message",
        "sender_id": "unsigned-entity",
        "payload": {"content": "No signature"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16)
        # signature フィールドなし
    })
    
    # 署名なしでも受信は可能（検証フラグがFalseになる）
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["status"] == "received"
    assert data["verified"] is False, "Message should not be verified without signature"
    print(f"✅ Unsigned message received (verified={data['verified']})")


def test_replay_protection_on_endpoint():
    """エンドポイントでのリプレイ防止テスト"""
    print("\n=== Replay Protection on Endpoint Test ===")
    
    if not FASTAPI_AVAILABLE:
        print("⚠️ Skipped: FastAPI not available")
        return
    
    client = TestClient(app)
    
    # 鍵ペア生成と公開鍵登録
    kp = generate_keypair()
    signer = MessageSigner(kp)
    
    client.post("/register-key", json={
        "entity_id": "replay-test-entity",
        "public_key": kp.get_public_key_hex()
    })
    
    # メッセージ作成
    from crypto import SecureMessage
    msg = SecureMessage(
        version="0.3",
        msg_type="replay_test",
        sender_id="replay-test-entity",
        payload={"test": "replay"}
    )
    msg.sign(signer)
    
    message_data = {
        "version": msg.version,
        "msg_type": msg.msg_type,
        "sender_id": msg.sender_id,
        "payload": msg.payload,
        "timestamp": msg.timestamp,
        "nonce": msg.nonce,
        "signature": msg.signature
    }
    
    # 最初の送信（成功）
    response1 = client.post("/message", json=message_data)
    assert response1.status_code == 200, "First message should be accepted"
    print(f"✅ First message accepted")
    
    # 同じメッセージの再送信（リプレイ検出）
    response2 = client.post("/message", json=message_data)
    # リプレイは拒否される（400 Bad Request）
    assert response2.status_code == 400, f"Replay should be rejected, got {response2.status_code}"
    assert "replay" in response2.json()["detail"].lower()
    print(f"✅ Replay detected and rejected")


def test_heartbeat():
    """ハートビートエンドポイントテスト"""
    print("\n=== Heartbeat Test ===")
    
    if not FASTAPI_AVAILABLE:
        print("⚠️ Skipped: FastAPI not available")
        return
    
    client = TestClient(app)
    
    # エージェント登録
    client.post("/register", json={
        "entity_id": "heartbeat-entity",
        "name": "Heartbeat Test",
        "endpoint": "http://localhost:8003",
        "capabilities": ["heartbeat"]
    })
    
    # ハートビート送信
    response = client.post("/heartbeat", json={
        "entity_id": "heartbeat-entity",
        "load": 0.5,
        "active_tasks": 3
    })
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["status"] == "ok"
    print(f"✅ Heartbeat accepted")


def main():
    """全統合テスト実行"""
    print("=" * 60)
    print("API Server Integration Test Suite")
    print("=" * 60)
    
    if not FASTAPI_AVAILABLE:
        print("\n⚠️ FastAPI/TestClient not available.")
        print("Install with: pip install fastapi[testclient]")
        return 1
    
    try:
        # 基本エンドポイント
        test_health_endpoint()
        test_register_agent()
        test_discover_agents()
        
        # 署名関連
        test_register_public_key()
        test_message_with_signature()
        test_message_without_signature()
        test_replay_protection_on_endpoint()
        
        # その他
        test_heartbeat()
        
        print("\n" + "=" * 60)
        print("✅ All integration tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
