#!/usr/bin/env python3
"""
統合テスト - Protocol v1.0
Ed25519署名 + リプレイ保護 + PeerService統合 + Capability交換
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crypto import (
    KeyPair, MessageSigner, SignatureVerifier, 
    SecureMessage, ReplayProtector, generate_keypair
)
from peer_service import PeerService, init_service


def test_crypto_peer_integration():
    """暗号機能とPeerServiceの統合テスト"""
    print("\n=== Integration: Crypto + PeerService ===\n")
    
    # エンティティA（送信者）のセットアップ
    kp_a = generate_keypair()
    service_a = PeerService("entity-a", 8001)
    service_a.key_pair = kp_a
    service_a.signer = MessageSigner(kp_a)
    service_a.verifier = SignatureVerifier()
    service_a.replay_protector = ReplayProtector()
    service_a.enable_signing = True
    service_a.enable_verification = True
    
    # エンティティB（受信者）のセットアップ
    kp_b = generate_keypair()
    service_b = PeerService("entity-b", 8002)
    service_b.key_pair = kp_b
    service_b.signer = MessageSigner(kp_b)
    service_b.verifier = SignatureVerifier()
    service_b.replay_protector = ReplayProtector()
    service_b.enable_signing = True
    service_b.enable_verification = True
    
    # 公開鍵交換
    service_b.verifier.add_public_key("entity-a", kp_a.public_key)
    service_a.verifier.add_public_key("entity-b", kp_b.public_key)
    
    print(f"✓ Entity A public key: {kp_a.get_public_key_hex()[:32]}...")
    print(f"✓ Entity B public key: {kp_b.get_public_key_hex()[:32]}...")
    
    # メッセージ作成（A→B）
    msg = SecureMessage(
        version="0.3",
        msg_type="status_report",
        sender_id="entity-a",
        payload={"task": "test", "status": "completed"}
    )
    msg.sign(service_a.signer)
    
    print(f"✓ Message signed by {msg.sender_id}")
    print(f"  Signature: {msg.signature[:50]}...")
    
    # メッセージを辞書に変換（送受信シミュレート）
    msg_dict = msg.to_dict()
    
    # 受信側で処理（B）
    result = asyncio.run(service_b.handle_message(msg_dict))
    
    assert result["status"] == "success", f"Message handling failed: {result}"
    print(f"✓ Message verified and processed by entity-b")
    
    # リプレイ攻撃テスト（同じメッセージを再度送信）
    result2 = asyncio.run(service_b.handle_message(msg_dict))
    assert result2["status"] == "error", "Replay should be detected"
    assert "replay" in result2.get("reason", "").lower(), f"Expected replay error, got: {result2}"
    print(f"✓ Replay attack detected: {result2['reason']}")
    
    print("\n✅ Crypto + PeerService integration passed!")


def test_key_management():
    """公開鍵管理のテスト"""
    print("\n=== Integration: Key Management ===\n")
    
    service = PeerService("test-entity", 8003)
    kp = generate_keypair()
    service.verifier = SignatureVerifier()
    
    # 公開鍵追加
    service.verifier.add_public_key("peer-1", kp.public_key)
    assert "peer-1" in service.verifier.public_keys
    print("✓ Public key added")
    
    # 公開鍵削除
    result = service.verifier.remove_public_key("peer-1")
    assert result is True
    assert "peer-1" not in service.verifier.public_keys
    print("✓ Public key removed")
    
    # 存在しないキーの削除
    result = service.verifier.remove_public_key("peer-1")
    assert result is False
    print("✓ Removing non-existent key handled correctly")
    
    print("\n✅ Key management integration passed!")


def test_protocol_v10_compliance():
    """Protocol v1.0 準拠テスト"""
    print("\n=== Protocol v1.0 Compliance ===\n")
    
    # 鍵生成
    kp = generate_keypair()
    signer = MessageSigner(kp)
    
    # v1.0形式メッセージ作成
    msg = SecureMessage(
        version="1.0",  # 必須: version = "1.0"
        msg_type="test_message",
        sender_id="test-entity",
        payload={"data": "test"}
    )
    
    # 署名
    msg.sign(signer)
    
    # 必須フィールド確認
    msg_dict = msg.to_dict()
    required_fields = ["version", "msg_type", "sender_id", "payload", "timestamp", "nonce", "signature"]
    for field in required_fields:
        assert field in msg_dict, f"Missing required field: {field}"
    
    print(f"✓ All required fields present: {required_fields}")
    print(f"✓ Version: {msg_dict['version']}")
    print(f"✓ Nonce length: {len(msg_dict['nonce'])} chars (128-bit = 32 hex chars)")
    print(f"✓ Timestamp format: ISO 8601")
    
    # タイムスタンプ検証
    from datetime import datetime, timezone
    ts = datetime.fromisoformat(msg_dict['timestamp'])
    assert ts.tzinfo is not None, "Timestamp must be timezone-aware"
    print("✓ Timestamp is timezone-aware")
    
    print("\n✅ Protocol v1.0 compliance passed!")


def main():
    """全統合テスト実行"""
    print("=" * 60)
    print("Integration Tests - Protocol v1.0")
    print("=" * 60)
    
    try:
        test_crypto_peer_integration()
        test_key_management()
        test_protocol_v03_compliance()
        
        print("\n" + "=" * 60)
        print("✅ All integration tests passed!")
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
    main()
