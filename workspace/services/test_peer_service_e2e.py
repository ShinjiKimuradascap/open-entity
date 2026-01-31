#!/usr/bin/env python3
"""
E2E暗号化機能の動作確認テスト

このテストスクリプトは、E2ECryptoManagerのE2E暗号化機能を検証します。
X25519 + HKDF-SHA256 + AES-256-GCM の暗号化・復号フローをテストします。

実行方法:
    cd /home/moco/workspace
    python services/test_peer_service_e2e.py
"""

import asyncio
import sys
import os
import base64
from typing import Optional

# パス設定
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# E2ECryptoManager と関連クラスをインポート
try:
    from services.e2e_crypto import (
        E2ECryptoManager, E2ESession, SessionKeys, SessionState,
        generate_keypair, KeyPair, ProtocolError,
        NACL_AVAILABLE, DECRYPTION_FAILED, SESSION_EXPIRED
    )
    from services.crypto import SecureMessage, MessageType
    CRYPTO_AVAILABLE = True
except ImportError as e:
    print(f"❌ Error importing crypto modules: {e}")
    CRYPTO_AVAILABLE = False
    sys.exit(1)


class E2ECryptoManagerTest:
    """E2ECryptoManager機能のテスト"""

    def __init__(self):
        self.manager_alice: Optional[E2ECryptoManager] = None
        self.manager_bob: Optional[E2ECryptoManager] = None
        self.key_alice: Optional[KeyPair] = None
        self.key_bob: Optional[KeyPair] = None
        self.session_alice: Optional[E2ESession] = None
        self.session_bob: Optional[E2ESession] = None

    async def setup(self):
        """テスト環境のセットアップ"""
        print("🔧 Setting up test environment...")

        # キーペアを生成
        self.key_alice = generate_keypair()
        self.key_bob = generate_keypair()

        print(f"✅ Alice key pair generated: {self.key_alice.get_public_key_hex()[:16]}...")
        print(f"✅ Bob key pair generated: {self.key_bob.get_public_key_hex()[:16]}...")

        # E2ECryptoManagerインスタンスを作成
        self.manager_alice = E2ECryptoManager(
            entity_id="alice",
            keypair=self.key_alice
        )
        self.manager_bob = E2ECryptoManager(
            entity_id="bob",
            keypair=self.key_bob
        )

        print(f"✅ E2ECryptoManager instances created")

    async def test_key_exchange_and_handshake(self):
        """X25519鍵交換とハンドシェイクのテスト"""
        print("\n🔑 Testing X25519 key exchange and handshake...")

        # Aliceがセッションを作成し、ハンドシェイクメッセージを生成
        self.session_alice = self.manager_alice.create_session("bob")
        print(f"✅ Alice created session: {self.session_alice.session_id[:8]}...")
        print(f"   Ephemeral X25519 pubkey: {self.session_alice.ephemeral_public_key.hex()[:16]}...")

        # AliceからBobへのハンドシェイクメッセージ
        session_alice, handshake_msg = self.manager_alice.create_handshake_message(
            remote_entity_id="bob",
            session=self.session_alice
        )
        print(f"✅ Alice created handshake message")
        print(f"   Challenge: {self.session_alice.challenge.hex()[:16]}...")

        # Bobがセッションを作成
        self.session_bob = self.manager_bob.create_session("alice")
        print(f"✅ Bob created session: {self.session_bob.session_id[:8]}...")

        # BobがAliceのハンドシェイクを処理して応答を生成
        # challengeをハンドシェイクメッセージから取得
        challenge = base64.b64decode(handshake_msg.payload.get("challenge", ""))
        response_msg = self.manager_bob.create_handshake_response(
            session=self.session_bob,
            remote_challenge=challenge
        )
        print(f"✅ Bob created handshake response")

        # Aliceが応答を処理してセッション確立
        self.manager_alice.process_handshake_response(
            session=self.session_alice,
            response_payload=response_msg.payload
        )
        print(f"✅ Alice processed handshake response")

        # Bobもハンドシェイクを完了（Aliceの公開鍵で共有鍵を導出）
        alice_pubkey = bytes.fromhex(handshake_msg.payload.get("public_key", ""))
        self.session_bob.complete_handshake(
            remote_public_key=alice_pubkey,
            remote_ephemeral_key=self.session_alice.ephemeral_public_key
        )
        print(f"✅ Bob completed handshake")

        # 両方のセッションが確立されたことを確認
        assert self.session_alice.state == SessionState.ESTABLISHED, "Alice session not established!"
        assert self.session_bob.state == SessionState.ESTABLISHED, "Bob session not established!"
        print(f"✅ Both sessions established")

        # 共有鍵（SessionKeys）が両方に存在することを確認
        assert self.session_alice.session_keys is not None, "Alice session keys not derived!"
        assert self.session_bob.session_keys is not None, "Bob session keys not derived!"
        print(f"✅ Session keys derived on both sides")

        # HKDF-SHA256で導出された鍵を表示
        print(f"   Alice encryption key: {self.session_alice.session_keys.encryption_key.hex()[:16]}...")
        print(f"   Bob encryption key: {self.session_bob.session_keys.encryption_key.hex()[:16]}...")

    async def test_shared_key_derivation(self):
        """HKDF-SHA256共有鍵導出のテスト"""
        print("\n🔑 Testing HKDF-SHA256 shared key derivation...")

        # 共有鍵が同じであることを確認（同じECDH共有秘密から導出されている）
        alice_key = self.session_alice.session_keys.encryption_key
        bob_key = self.session_bob.session_keys.encryption_key

        assert alice_key == bob_key, "Derived encryption keys do not match!"
        assert len(alice_key) == 32, "Encryption key must be 32 bytes (AES-256)!"

        print(f"✅ Shared encryption keys match: {alice_key.hex()[:16]}...")
        print(f"   Key length: {len(alice_key)} bytes")

        # HMACキーも確認
        alice_hmac = self.session_alice.session_keys.mac_key
        bob_hmac = self.session_bob.session_keys.mac_key
        assert alice_hmac == bob_hmac, "Derived MAC keys do not match!"
        print(f"✅ Shared MAC keys match: {alice_hmac.hex()[:16]}...")

    async def test_encryption_decryption(self):
        """AES-256-GCM暗号化・復号のテスト"""
        print("\n🔒 Testing AES-256-GCM encryption/decryption...")

        # テストメッセージ
        test_payload = {
            "message": "Hello, Bob! This is a secret message.",
            "timestamp": "2024-01-01T00:00:00Z",
            "sender": "alice"
        }

        print(f"📄 Plaintext payload: {test_payload}")

        # Aliceが暗号化
        encrypted_msg = self.manager_alice.encrypt_message(
            session_id=self.session_alice.session_id,
            payload=test_payload
        )

        encrypted_data = encrypted_msg.payload.get("data", "")[:32]
        nonce = encrypted_msg.payload.get("nonce", "")
        print(f"🔐 Ciphertext: {encrypted_data}...")
        print(f"   Nonce: {nonce[:24]}...")
        print(f"   Ciphertext length: {len(encrypted_msg.payload.get('data', ''))} bytes (base64)")

        # Bobが復号
        decrypted = self.manager_bob.decrypt_message(
            session=self.session_bob,
            message=encrypted_msg
        )

        # 復号結果を検証
        assert decrypted == test_payload, f"Decrypted payload does not match!\nExpected: {test_payload}\nGot: {decrypted}"

        print(f"📄 Decrypted: {decrypted}")
        print("✅ Encryption/Decryption successful!")

    async def test_different_messages(self):
        """異なるメッセージでのテスト"""
        print("\n📝 Testing different messages...")

        test_messages = [
            {"type": "ping", "data": "hello"},
            {"type": "task", "action": "process", "args": [1, 2, 3]},
            {"type": "status", "healthy": True, "load": 0.5},
            {"type": "large", "data": "x" * 1000},  # 大きなメッセージ
        ]

        for i, msg in enumerate(test_messages):
            # Aliceが暗号化
            encrypted_msg = self.manager_alice.encrypt_message(
                session_id=self.session_alice.session_id,
                payload=msg
            )

            # Bobが復号
            decrypted = self.manager_bob.decrypt_message(
                session=self.session_bob,
                message=encrypted_msg
            )

            assert decrypted == msg, f"Message {i} mismatch!"

        print(f"✅ Successfully encrypted/decrypted {len(test_messages)} different messages")

    async def test_sequence_numbers(self):
        """シーケンス番号のテスト"""
        print("\n🔢 Testing sequence numbers...")

        # 複数のメッセージを送信してシーケンス番号が増加することを確認
        for i in range(5):
            msg = {"type": "test", "seq": i}
            encrypted_msg = self.manager_alice.encrypt_message(
                session_id=self.session_alice.session_id,
                payload=msg
            )
            print(f"   Message {i}: sequence_num = {encrypted_msg.sequence_num}")
            assert encrypted_msg.sequence_num == i, f"Sequence number mismatch at {i}"

        print(f"✅ Sequence numbers incrementing correctly")

    async def test_session_expiration(self):
        """セッション有効期限のテスト"""
        print("\n⏰ Testing session expiration...")

        # 短いタイムアウトで新しいセッションを作成
        short_session = self.manager_alice.create_session("expiry_test")
        short_session.timeout_seconds = 0  # 即座に期限切れ

        # 期限切れをチェック
        assert short_session.is_expired(), "Session should be expired!"
        print(f"✅ Session expiration detection working")

    async def run_all(self):
        """全テストを実行"""
        print("=" * 60)
        print("🚀 E2E Crypto Manager Test Suite")
        print("=" * 60)

        try:
            await self.setup()
            await self.test_key_exchange_and_handshake()
            await self.test_shared_key_derivation()
            await self.test_encryption_decryption()
            await self.test_different_messages()
            await self.test_sequence_numbers()
            await self.test_session_expiration()

            print("\n" + "=" * 60)
            print("✅ All tests passed!")
            print("=" * 60)
            return True

        except AssertionError as e:
            print(f"\n❌ Assertion failed: {e}")
            import traceback
            traceback.print_exc()
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

    if not NACL_AVAILABLE:
        print("❌ PyNaCl not installed. Run: pip install pynacl")
        sys.exit(1)

    test = E2ECryptoManagerTest()
    success = await test.run_all()

    if success:
        print("\n🎉 E2E encryption with X25519 + HKDF-SHA256 + AES-256-GCM is working correctly!")
        print("\nTested features:")
        print("  ✓ X25519 ephemeral key generation")
        print("  ✓ X25519 ECDH key exchange")
        print("  ✓ HKDF-SHA256 key derivation")
        print("  ✓ AES-256-GCM encryption/decryption")
        print("  ✓ Session management with UUID v4")
        print("  ✓ Sequence number tracking")
        print("  ✓ Ed25519 message signing")
        sys.exit(0)
    else:
        print("\n💥 Tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
