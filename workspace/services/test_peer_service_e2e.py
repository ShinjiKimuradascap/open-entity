#!/usr/bin/env python3
"""
E2E暗号化機能の動作確認テスト

このテストスクリプトは、PeerServiceのE2E暗号化機能を検証します。
X25519 + HKDF-SHA256 + AES-256-GCM の暗号化・復号フローをテストします。

実行方法:
    cd /home/moco/workspace
    python services/test_peer_service_e2e.py
"""

import asyncio
import sys
import os
from typing import Optional

# パス設定
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from crypto import E2EEncryption, KeyPair, generate_keypair
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        from services.crypto import E2EEncryption, KeyPair, generate_keypair
        CRYPTO_AVAILABLE = True
    except ImportError:
        CRYPTO_AVAILABLE = False
        print("❌ Error: crypto module not available")
        sys.exit(1)


class E2EEncryptionTest:
    """E2E暗号化機能のテスト"""

    def __init__(self):
        self.e2e_alice: Optional[E2EEncryption] = None
        self.e2e_bob: Optional[E2EEncryption] = None
        self.key_alice: Optional[KeyPair] = None
        self.key_bob: Optional[KeyPair] = None
        self.shared_key_alice: Optional[bytes] = None
        self.shared_key_bob: Optional[bytes] = None

    async def setup(self):
        """テスト環境のセットアップ"""
        print("🔧 Setting up test environment...")

        # E2E暗号化インスタンスを作成
        self.e2e_alice = E2EEncryption()
        self.e2e_bob = E2EEncryption()

        # キーペアを生成
        self.key_alice = generate_keypair()
        self.key_bob = generate_keypair()

        print(f"✅ Alice key pair generated: {self.key_alice.get_public_key_hex()[:16]}...")
        print(f"✅ Bob key pair generated: {self.key_bob.get_public_key_hex()[:16]}...")

    async def test_key_derivation(self):
        """共有鍵導出のテスト"""
        print("\n🔑 Testing shared key derivation...")

        # Alice側からBobとの共有鍵を導出
        self.shared_key_alice = self.e2e_alice.derive_shared_key(
            my_ed25519_private=self.key_alice.private_key,
            peer_ed25519_public=self.key_bob.public_key,
            peer_id="bob"
        )

        # Bob側からAliceとの共有鍵を導出
        self.shared_key_bob = self.e2e_bob.derive_shared_key(
            my_ed25519_private=self.key_bob.private_key,
            peer_ed25519_public=self.key_alice.public_key,
            peer_id="alice"
        )

        # 両者の共有鍵が同じであることを確認
        assert self.shared_key_alice == self.shared_key_bob, "Shared keys do not match!"
        assert len(self.shared_key_alice) == 32, "Shared key must be 32 bytes!"

        print(f"✅ Shared key derived: {self.shared_key_alice.hex()[:16]}...")
        print(f"   Key length: {len(self.shared_key_alice)} bytes")

    async def test_encryption_decryption(self):
        """暗号化・復号のテスト"""
        print("\n🔒 Testing encryption/decryption...")

        # テストメッセージ
        test_payload = {
            "message": "Hello, Bob! This is a secret message.",
            "timestamp": "2024-01-01T00:00:00Z",
            "sender": "alice"
        }

        # JSON文字列化
        import json
        plaintext = json.dumps(test_payload, sort_keys=True).encode('utf-8')
        print(f"📄 Plaintext: {plaintext.decode()}")

        # Aliceが暗号化
        ciphertext, nonce = self.e2e_alice.encrypt(
            plaintext=plaintext,
            shared_key=self.shared_key_alice
        )

        print(f"🔐 Ciphertext: {ciphertext.hex()[:32]}...")
        print(f"   Nonce: {nonce.hex()}")
        print(f"   Ciphertext length: {len(ciphertext)} bytes")

        # Bobが復号
        decrypted = self.e2e_bob.decrypt(
            ciphertext=ciphertext,
            nonce=nonce,
            shared_key=self.shared_key_bob
        )

        # 復号結果を検証
        decrypted_payload = json.loads(decrypted.decode('utf-8'))
        assert decrypted_payload == test_payload, "Decrypted payload does not match!"

        print(f"📄 Decrypted: {decrypted.decode()}")
        print("✅ Encryption/Decryption successful!")

    async def test_different_messages(self):
        """異なるメッセージでのテスト"""
        print("\n📝 Testing different messages...")

        import json

        test_messages = [
            {"type": "ping", "data": "hello"},
            {"type": "task", "action": "process", "args": [1, 2, 3]},
            {"type": "status", "healthy": True, "load": 0.5},
            {"type": "large", "data": "x" * 1000},  # 大きなメッセージ
        ]

        for i, msg in enumerate(test_messages):
            plaintext = json.dumps(msg, sort_keys=True).encode('utf-8')

            # 暗号化
            ciphertext, nonce = self.e2e_alice.encrypt(
                plaintext=plaintext,
                shared_key=self.shared_key_alice
            )

            # 復号
            decrypted = self.e2e_bob.decrypt(
                ciphertext=ciphertext,
                nonce=nonce,
                shared_key=self.shared_key_bob
            )

            decrypted_msg = json.loads(decrypted.decode('utf-8'))
            assert decrypted_msg == msg, f"Message {i} mismatch!"

        print(f"✅ Successfully encrypted/decrypted {len(test_messages)} different messages")

    async def test_peer_service_integration(self):
        """PeerServiceとの統合テスト"""
        print("\n🔌 Testing PeerService E2E integration...")

        try:
            from peer_service import PeerService
        except ImportError:
            from services.peer_service import PeerService

        # 2つのPeerServiceインスタンスを作成
        alice_service = PeerService(
            entity_id="alice",
            port=8001,
            enable_encryption=True,
            enable_signing=True,
            enable_verification=True
        )

        bob_service = PeerService(
            entity_id="bob",
            port=8002,
            enable_encryption=True,
            enable_signing=True,
            enable_verification=True
        )

        # ピアとして登録
        alice_service.add_peer("bob", "http://localhost:8002")
        bob_service.add_peer("alice", "http://localhost:8001")

        # 公開鍵を交換
        alice_pubkey = alice_service.get_public_key_hex()
        bob_pubkey = bob_service.get_public_key_hex()

        alice_service.add_peer_public_key("bob", bob_pubkey)
        bob_service.add_peer_public_key("alice", alice_pubkey)

        print(f"✅ Alice service initialized with encryption")
        print(f"✅ Bob service initialized with encryption")
        print(f"✅ Peer keys exchanged")

        # E2E暗号化インスタンスの確認
        assert alice_service.e2e_encryption is not None, "Alice E2E encryption not initialized"
        assert bob_service.e2e_encryption is not None, "Bob E2E encryption not initialized"
        print("✅ E2E encryption instances are active")

        # ペイロード暗号化テスト
        test_payload = {"message": "Secret message", "value": 42}

        encrypted = alice_service.encrypt_payload("bob", test_payload)
        assert encrypted is not None, "Encryption failed"
        print(f"✅ Payload encrypted: {encrypted.keys()}")

        # ペイロード復号テスト
        decrypted = bob_service.decrypt_payload("alice", encrypted)
        assert decrypted == test_payload, "Decryption mismatch"
        print(f"✅ Payload decrypted successfully")

        # 共有鍵キャッシュの確認
        assert "bob" in alice_service._e2e_shared_keys, "Shared key not cached for Alice"
        assert "alice" in bob_service._e2e_shared_keys, "Shared key not cached for Bob"
        print("✅ Shared keys are cached")

        print("\n✅ PeerService E2E integration test passed!")

    async def run_all(self):
        """全テストを実行"""
        print("=" * 60)
        print("🚀 E2E Encryption Test Suite")
        print("=" * 60)

        try:
            await self.setup()
            await self.test_key_derivation()
            await self.test_encryption_decryption()
            await self.test_different_messages()
            await self.test_peer_service_integration()

            print("\n" + "=" * 60)
            print("✅ All tests passed!")
            print("=" * 60)
            return True

        except AssertionError as e:
            print(f"\n❌ Assertion failed: {e}")
            return False
        except Exception as e:
            print(f"\n❌ Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """メイン関数"""
    if not CRYPTO_AVAILABLE:
        print("❌ Crypto module not available. Install PyNaCl: pip install pynacl")
        sys.exit(1)

    test = E2EEncryptionTest()
    success = await test.run_all()

    if success:
        print("\n🎉 E2E encryption is working correctly!")
        sys.exit(0)
    else:
        print("\n💥 Tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
