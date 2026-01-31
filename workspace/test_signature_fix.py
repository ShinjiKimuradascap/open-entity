#!/usr/bin/env python3
"""
署名検証ロジック修正の検証スクリプト
"""

import os
import sys
import json

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from crypto_utils import CryptoManager, SecureMessage, generate_entity_keypair

# テスト用エンティティID
TEST_ENTITY_A_ID = "entity-a-test"
TEST_ENTITY_B_ID = "entity-b-test"

def test_signature_verification():
    """署名検証テスト"""
    print("\n" + "="*60)
    print("署名検証ロジック修正テスト")
    print("="*60)
    
    try:
        # 鍵ペア生成
        priv_a, pub_a = generate_entity_keypair()
        priv_b, pub_b = generate_entity_keypair()
        print(f"✓ Entity A keys generated: {pub_a[:32]}...")
        print(f"✓ Entity B keys generated: {pub_b[:32]}...")
        
        # CryptoManager初期化
        os.environ["ENTITY_PRIVATE_KEY"] = priv_a
        crypto_a = CryptoManager(TEST_ENTITY_A_ID)
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_b
        crypto_b = CryptoManager(TEST_ENTITY_B_ID)
        
        # X25519鍵ペア生成
        crypto_a.generate_x25519_keypair()
        crypto_b.generate_x25519_keypair()
        
        # 共有鍵派生
        crypto_a.derive_shared_key(
            crypto_b.get_x25519_public_key_b64(), 
            TEST_ENTITY_B_ID
        )
        crypto_b.derive_shared_key(
            crypto_a.get_x25519_public_key_b64(), 
            TEST_ENTITY_A_ID
        )
        print("✓ Shared keys derived")
        
        # テストペイロード
        payload = {
            "type": "test_message",
            "from": TEST_ENTITY_A_ID,
            "to": TEST_ENTITY_B_ID,
            "content": "Hello, this is a test message!"
        }
        
        # === テスト1: 暗号化なしメッセージ ===
        print("\n--- Test 1: Non-encrypted message ---")
        message = crypto_a.create_secure_message(
            payload=payload,
            encrypt=False,
            recipient_id=None,
            include_jwt=False
        )
        print(f"✓ Message created")
        print(f"  - sender_id: {message.sender_id}")
        print(f"  - sender_public_key: {message.sender_public_key[:32]}..." if message.sender_public_key else "  - sender_public_key: None")
        
        # 検証
        result = crypto_b.verify_and_decrypt_message(
            message=message,
            require_encryption=False,
            peer_id=None,
            verify_jwt=False
        )
        
        if result:
            print(f"✓ Signature verification PASSED")
            print(f"  - Verified payload: {json.dumps(result, indent=2)[:100]}...")
        else:
            print("✗ Signature verification FAILED")
            return False
        
        # === テスト2: 暗号化ありメッセージ ===
        print("\n--- Test 2: Encrypted message ---")
        encrypted_message = crypto_a.create_secure_message(
            payload=payload,
            encrypt=True,
            recipient_id=TEST_ENTITY_B_ID,
            include_jwt=False
        )
        print(f"✓ Encrypted message created")
        print(f"  - sender_id: {encrypted_message.sender_id}")
        print(f"  - Has encrypted_payload: {encrypted_message.encrypted_payload is not None}")
        
        # 復号・検証
        decrypted = crypto_b.verify_and_decrypt_message(
            message=encrypted_message,
            require_encryption=True,
            peer_id=TEST_ENTITY_A_ID,
            verify_jwt=False
        )
        
        if decrypted:
            print(f"✓ Decryption and signature verification PASSED")
            print(f"  - Decrypted content: {decrypted.get('content', 'N/A')}")
        else:
            print("✗ Decryption or signature verification FAILED")
            return False
        
        # === テスト3: JWT付きメッセージ ===
        print("\n--- Test 3: Message with JWT ---")
        jwt_message = crypto_a.create_secure_message(
            payload=payload,
            encrypt=False,
            recipient_id=None,
            include_jwt=True,
            jwt_audience=TEST_ENTITY_B_ID
        )
        print(f"✓ JWT message created")
        print(f"  - Has JWT token: {jwt_message.jwt_token is not None}")
        
        # JWT検証
        jwt_result = crypto_b.verify_and_decrypt_message(
            message=jwt_message,
            require_encryption=False,
            peer_id=None,
            verify_jwt=True,
            jwt_audience=TEST_ENTITY_B_ID
        )
        
        if jwt_result:
            print(f"✓ JWT verification PASSED")
        else:
            print("✗ JWT verification FAILED")
            return False
        
        # === テスト4: 改竄検出 ===
        print("\n--- Test 4: Tampered message detection ---")
        tampered_message = crypto_a.create_secure_message(
            payload=payload,
            encrypt=False,
            recipient_id=None,
            include_jwt=False
        )
        # ペイロードを改竄
        tampered_message.payload["content"] = "TAMPERED CONTENT"
        
        tampered_result = crypto_b.verify_and_decrypt_message(
            message=tampered_message,
            require_encryption=False,
            peer_id=None,
            verify_jwt=False
        )
        
        if tampered_result is None:
            print("✓ Tampered message correctly rejected")
        else:
            print("✗ Tampered message was incorrectly accepted")
            return False
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED ✓")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_signature_verification()
    sys.exit(0 if success else 1)
