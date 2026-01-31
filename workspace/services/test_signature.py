#!/usr/bin/env python3
"""
署名機能テストスクリプト
Ed25519署名・検証の動作確認
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crypto import (
    KeyPair, MessageSigner, SignatureVerifier, 
    SecureMessage, ReplayProtector, generate_keypair
)


def test_key_generation():
    """鍵ペア生成テスト"""
    print("\n=== Key Generation Test ===")
    
    kp = generate_keypair()
    assert kp.public_key is not None, "Public key should be generated"
    assert kp.private_key is not None, "Private key should be generated"
    # Ed25519公開鍵は必ず32バイト
    assert len(kp.public_key) == 32, f"Ed25519 public key must be 32 bytes, got {len(kp.public_key)}"
    # Expanded Ed25519 private key format: 64 bytes (seed + public key scalar)
    assert len(kp.private_key) == 64, f"Ed25519 private key must be 64 bytes (expanded format), got {len(kp.private_key)}"
    
    print(f"✅ Public key: {kp.get_public_key_hex()[:32]}...")
    print(f"✅ Private key: {kp.get_private_key_hex()[:32]}...")
    return kp


def test_signature_sign_verify(kp: KeyPair):
    """署名・検証テスト"""
    print("\n=== Signature Sign/Verify Test ===")
    
    import base64
    
    # 署名者と検証者を作成
    signer = MessageSigner(kp)
    verifier = SignatureVerifier()
    verifier.add_public_key("test-entity", kp.public_key)
    
    # テストメッセージ
    message = {"type": "test", "data": "hello world", "timestamp": "2026-01-31T00:00:00Z"}
    
    # 署名
    signature = signer.sign_message(message)
    assert signature is not None, "Signature should be created"
    assert len(signature) > 0, "Signature should not be empty"
    print(f"✅ Signature created: {signature[:50]}...")
    
    # 検証
    is_valid = verifier.verify_message(message, signature, "test-entity")
    assert is_valid is True, f"Signature should be valid for message: {message}"
    print(f"✅ Signature verified: {is_valid}")
    
    # メッセージ改ざん検出テスト
    tampered_message = {"type": "test", "data": "tampered", "timestamp": "2026-01-31T00:00:00Z"}
    is_invalid = verifier.verify_message(tampered_message, signature, "test-entity")
    assert is_invalid is False, "Tampered message should fail verification"
    print(f"✅ Tampered message detected: {is_invalid}")
    
    # 署名改ざん検出テスト（1ビット変更）
    sig_bytes = base64.b64decode(signature)
    tampered_sig_bytes = sig_bytes[:-1] + bytes([sig_bytes[-1] ^ 0x01])  # 最後のバイトを反転
    tampered_sig = base64.b64encode(tampered_sig_bytes).decode()
    is_sig_invalid = verifier.verify_message(message, tampered_sig, "test-entity")
    assert is_sig_invalid is False, "Tampered signature should fail verification"
    print(f"✅ Tampered signature detected: {is_sig_invalid}")


def test_secure_message(kp: KeyPair):
    """SecureMessageテスト"""
    print("\n=== SecureMessage Test ===")
    
    signer = MessageSigner(kp)
    
    # メッセージ作成
    msg = SecureMessage(
        version="0.3",
        msg_type="status_report",
        sender_id="entity-a",
        payload={"task": "test", "status": "completed"}
    )
    
    # 署名
    msg.sign(signer)
    assert msg.signature is not None, "Message should be signed"
    print(f"✅ Message signed: {msg.signature[:50]}...")
    
    # 検証
    verifier = SignatureVerifier()
    verifier.add_public_key("entity-a", kp.public_key)
    
    is_valid = verifier.verify_message(
        msg.get_signable_data(),
        msg.signature,
        "entity-a"
    )
    assert is_valid is True, "Signed message should be valid"
    print(f"✅ Signed message verified: {is_valid}")
    
    # 辞書変換テスト
    msg_dict = msg.to_dict()
    assert "signature" in msg_dict, "Dictionary should contain signature"
    assert msg_dict["version"] == "0.3", "Version should be preserved"
    print(f"✅ Message to_dict: version={msg_dict['version']}, type={msg_dict['msg_type']}")


def test_replay_protection():
    """リプレイ攻撃防止テスト"""
    print("\n=== Replay Protection Test ===")
    
    protector = ReplayProtector(max_age_seconds=60)
    
    # 有効なメッセージ
    import secrets
    from datetime import datetime, timezone, timedelta
    
    nonce = secrets.token_hex(16)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    valid, error = protector.is_valid(nonce, timestamp)
    assert valid is True, "First check should be valid"
    assert error is None, "No error on first check"
    print(f"✅ First nonce check: valid={valid}")
    
    # リプレイ試行（同じnonce）
    valid2, error2 = protector.is_valid(nonce, timestamp)
    assert valid2 is False, "Replay should be detected"
    assert "replay" in error2.lower(), "Should indicate replay attack"
    print(f"✅ Replay detected: valid={valid2}, error={error2}")
    
    # 古いタイムスタンプ（過去）
    old_nonce = secrets.token_hex(16)
    old_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    valid3, error3 = protector.is_valid(old_nonce, old_timestamp)
    assert valid3 is False, f"Old timestamp should be rejected: {error3}"
    print(f"✅ Old timestamp rejected: valid={valid3}")
    
    # 未来のタイムスタンプ（時計のずれを悪用した攻撃）
    future_nonce = secrets.token_hex(16)
    future_timestamp = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    valid4, error4 = protector.is_valid(future_nonce, future_timestamp)
    assert valid4 is False, f"Future timestamp should be rejected: {error4}"
    print(f"✅ Future timestamp rejected: valid={valid4}")


def test_multiple_entities():
    """複数エンティティ間の署名検証テスト"""
    print("\n=== Multiple Entities Test ===")
    
    # 2つのエンティティ
    kp_a = generate_keypair()
    kp_b = generate_keypair()
    
    signer_a = MessageSigner(kp_a)
    signer_b = MessageSigner(kp_b)
    
    verifier = SignatureVerifier()
    verifier.add_public_key("entity-a", kp_a.public_key)
    verifier.add_public_key("entity-b", kp_b.public_key)
    
    # Entity Aからのメッセージ
    msg_a = SecureMessage(
        version="0.3",
        msg_type="request",
        sender_id="entity-a",
        payload={"action": "do_something"}
    )
    msg_a.sign(signer_a)
    
    # Entity Bからのメッセージ
    msg_b = SecureMessage(
        version="0.3",
        msg_type="response",
        sender_id="entity-b",
        payload={"result": "done"}
    )
    msg_b.sign(signer_b)
    
    # 検証
    valid_a = verifier.verify_message(msg_a.get_signable_data(), msg_a.signature, "entity-a")
    valid_b = verifier.verify_message(msg_b.get_signable_data(), msg_b.signature, "entity-b")
    
    assert valid_a is True, "Entity A's signature should be valid"
    assert valid_b is True, "Entity B's signature should be valid"
    print(f"✅ Entity A signature: {valid_a}")
    print(f"✅ Entity B signature: {valid_b}")
    
    # 間違ったエンティティで検証（失敗すべき）
    try:
        valid_wrong = verifier.verify_message(msg_a.get_signable_data(), msg_a.signature, "entity-b")
        assert valid_wrong is False, "Wrong entity verification should fail"
        print(f"✅ Wrong entity verification failed as expected")
    except Exception as e:
        print(f"✅ Wrong entity verification raised exception: {type(e).__name__}")


def test_key_serialization():
    """鍵のシリアライゼーションテスト"""
    print("\n=== Key Serialization Test ===")
    
    kp = generate_keypair()
    
    # Hexエンコード
    pub_hex = kp.get_public_key_hex()
    priv_hex = kp.get_private_key_hex()
    
    assert len(pub_hex) == 64, "Hex public key should be 64 chars"
    # Expanded Ed25519 private key format: 64 bytes (seed + public key scalar) = 128 hex chars
    assert len(priv_hex) == 128, f"Hex private key should be 128 chars (64 bytes expanded), got {len(priv_hex)}"
    print(f"✅ Private key is in expanded 64-byte format")
    print(f"✅ Public key hex length: {len(pub_hex)}")
    print(f"✅ Private key hex length: {len(priv_hex)}")
    
    # 復元
    kp_restored = KeyPair.from_private_key_hex(priv_hex)
    assert kp_restored.public_key == kp.public_key, "Restored key should match"
    assert kp_restored.private_key == kp.private_key, "Restored key should match"
    print(f"✅ Key restored successfully")


def main():
    """全テスト実行"""
    print("=" * 60)
    print("Signature Function Test Suite")
    print("=" * 60)
    
    try:
        # 鍵生成
        kp = test_key_generation()
        
        # 署名・検証
        test_signature_sign_verify(kp)
        
        # SecureMessage
        test_secure_message(kp)
        
        # リプレイ防止
        test_replay_protection()
        
        # 複数エンティティ
        test_multiple_entities()
        
        # シリアライゼーション
        test_key_serialization()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
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
