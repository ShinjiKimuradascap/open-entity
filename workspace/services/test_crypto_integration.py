#!/usr/bin/env python3
"""
Ed25519署名統合テスト
Protocol v1.0の署名・検証フローをテスト
"""

import asyncio
import json
import sys
import os

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crypto import KeyPair, MessageSigner, SignatureVerifier, SecureMessage, ReplayProtector


def test_key_generation():
    """鍵ペア生成テスト"""
    print("\n=== Test 1: Key Generation ===")
    
    kp = KeyPair.generate()
    print(f"✓ Generated key pair")
    print(f"  Public key: {kp.get_public_key_hex()[:32]}...")
    print(f"  Private key length: {len(kp.private_key)} bytes")
    
    # 秘密鍵から公開鍵を復元
    kp2 = KeyPair.from_private_key(kp.private_key)
    assert kp.public_key == kp2.public_key, "Public key mismatch"
    print("✓ Key recovery from private key works")
    
    return kp


def test_message_signing(key_pair: KeyPair):
    """メッセージ署名テスト"""
    print("\n=== Test 2: Message Signing ===")
    
    signer = MessageSigner(key_pair)
    
    message = {
        "msg_type": "test_message",
        "sender_id": "test-entity",
        "payload": {"data": "hello world", "value": 42}
    }
    
    signature = signer.sign_message(message)
    print(f"✓ Message signed")
    print(f"  Signature: {signature[:40]}...")
    
    return signature, message


def test_signature_verification(key_pair: KeyPair, signature: str, message: dict):
    """署名検証テスト"""
    print("\n=== Test 3: Signature Verification ===")
    
    verifier = SignatureVerifier()
    verifier.add_public_key("test-entity", key_pair.public_key)
    
    # 正常な検証
    is_valid = verifier.verify_message(message, signature, "test-entity")
    assert is_valid, "Valid signature should be accepted"
    print("✓ Valid signature verified")
    
    # 改ざん検出
    tampered_message = message.copy()
    tampered_message["payload"]["data"] = "tampered"
    
    is_invalid = verifier.verify_message(tampered_message, signature, "test-entity")
    assert not is_invalid, "Tampered message should be rejected"
    print("✓ Tampered message correctly rejected")


def test_secure_message():
    """SecureMessageクラステスト"""
    print("\n=== Test 4: SecureMessage ===")
    
    # 鍵生成
    kp = KeyPair.generate()
    signer = MessageSigner(kp)
    
    # メッセージ作成・署名
    msg = SecureMessage(
        version="0.3",
        msg_type="status_report",
        sender_id="entity-a",
        payload={"task": "test", "status": "completed"}
    )
    
    print(f"✓ Created message (v{msg.version})")
    print(f"  Type: {msg.msg_type}")
    print(f"  Nonce: {msg.nonce[:16]}...")
    
    # 署名
    msg.sign(signer)
    print(f"✓ Message signed")
    print(f"  Signature: {msg.signature[:40]}...")
    
    # 辞書変換
    msg_dict = msg.to_dict()
    assert "signature" in msg_dict
    print("✓ Message converted to dict")
    
    # 復元
    msg2 = SecureMessage.from_dict(msg_dict)
    assert msg2.signature == msg.signature
    print("✓ Message restored from dict")
    
    return msg


def test_replay_protection():
    """リプレイ防止テスト"""
    print("\n=== Test 5: Replay Protection ===")
    
    protector = ReplayProtector(max_age_seconds=60)
    
    # 正常なメッセージ
    nonce = "abc123"
    from datetime import timezone
    timestamp = datetime.now(timezone.utc).isoformat()
    
    valid, error = protector.is_valid(nonce, timestamp)
    assert valid, f"First check should pass: {error}"
    print("✓ First message accepted")
    
    # 同じノンス（リプレイ）
    valid2, error2 = protector.is_valid(nonce, timestamp)
    assert not valid2, "Replay should be detected"
    print(f"✓ Replay detected: {error2}")
    
    # 古いタイムスタンプ（現在時刻よりmax_age_seconds以上前）
    from datetime import timezone
    old_datetime = datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year - 1)
    old_time = old_datetime.isoformat()
    valid3, error3 = protector.is_valid("nonce2", old_time)
    assert not valid3, "Old timestamp should be rejected"
    print(f"✓ Old timestamp rejected: {error3}")


def test_full_flow():
    """完全な署名・検証フロー"""
    print("\n=== Test 6: Full Sign/Verify Flow ===")
    
    # エンティティA（送信者）
    kp_a = KeyPair.generate()
    signer_a = MessageSigner(kp_a)
    
    # エンティティB（受信者）
    kp_b = KeyPair.generate()
    
    # エンティティBの検証器にAの公開鍵を登録
    verifier_b = SignatureVerifier()
    verifier_b.add_public_key("entity-a", kp_a.public_key)
    
    # メッセージ作成
    msg = SecureMessage(
        version="0.3",
        msg_type="task_delegate",
        sender_id="entity-a",
        payload={"task": "process_data", "params": {"input": "test.csv"}}
    )
    
    # 署名
    msg.sign(signer_a)
    print(f"✓ Message signed by {msg.sender_id}")
    
    # リプレイ防止チェック
    protector = ReplayProtector()
    valid, error = protector.is_valid(msg.nonce, msg.timestamp)
    assert valid, f"Replay check failed: {error}"
    print("✓ Replay check passed")
    
    # 署名検証
    is_valid = verifier_b.verify_message(
        msg.get_signable_data(),
        msg.signature,
        msg.sender_id
    )
    assert is_valid, "Signature should be valid"
    print("✓ Signature verified by recipient")
    
    # 辞書形式でのやり取り（HTTP通信をシミュレート）
    msg_dict = msg.to_dict()
    msg_json = json.dumps(msg_dict)
    print(f"✓ Message serialized to JSON ({len(msg_json)} bytes)")
    
    # 受信側で復元
    received_dict = json.loads(msg_json)
    received_msg = SecureMessage.from_dict(received_dict)
    print("✓ Message restored from JSON")
    
    # 検証
    is_valid2 = verifier_b.verify_message(
        received_msg.get_signable_data(),
        received_msg.signature,
        received_msg.sender_id
    )
    assert is_valid2, "Restored message should have valid signature"
    print("✓ Restored message signature verified")


async def test_api_server_integration():
    """APIサーバー統合テスト（オプション）"""
    print("\n=== Test 7: API Server Integration (Optional) ===")
    
    try:
        import aiohttp
    except ImportError:
        print("⚠️ aiohttp not installed, skipping API test")
        return
    
    # 鍵生成
    kp = KeyPair.generate()
    signer = MessageSigner(kp)
    
    # 署名付きメッセージ作成
    msg = SecureMessage(
        version="0.3",
        msg_type="status_report",
        sender_id="test-entity",
        payload={"status": "ok"}
    )
    msg.sign(signer)
    
    print("✓ Created signed message for API")
    print(f"  Ready to POST to /message endpoint")
    print(f"  Payload preview: {json.dumps(msg.to_dict())[:100]}...")


def main():
    """全テスト実行"""
    from datetime import datetime
    
    print("=" * 60)
    print("Ed25519 Crypto Integration Tests")
    print("Protocol v1.0 - AI Peer Communication")
    print("=" * 60)
    
    try:
        # 基本テスト
        kp = test_key_generation()
        sig, msg = test_message_signing(kp)
        test_signature_verification(kp, sig, msg)
        
        # 高度なテスト
        test_secure_message()
        test_replay_protection()
        test_full_flow()
        
        # 非同期テスト
        asyncio.run(test_api_server_integration())
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    from datetime import datetime, timezone
    main()
