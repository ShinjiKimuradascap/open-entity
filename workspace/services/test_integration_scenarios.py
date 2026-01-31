#!/usr/bin/env python3
"""
Integration Test Scenarios for Peer Communication Protocol
AI間通信プロトコルの実用化統合テスト

Test Scenarios:
1. Handshake Flow (鍵交換)
2. Secure Message Exchange (署名・暗号化メッセージ)
3. Session Management (JWT認証)
4. Error Handling & Attack Prevention (異常系・攻撃防御)
5. Wallet Persistence Integration (ウォレット永続化)
"""

import os
import sys
import time
import json
import base64
import tempfile
import shutil
from typing import Dict, Any, Optional

import pytest

pytestmark = pytest.mark.integration

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.crypto import (
    CryptoManager, WalletManager, SecureMessage,
    generate_entity_keypair, TIMESTAMP_TOLERANCE_SECONDS
)


class TestScenario:
    """テストシナリオベースクラス"""
    
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
    
    def log(self, message: str):
        print(f"  [{self.name}] {message}")
    
    def assert_true(self, condition: bool, message: str) -> bool:
        if condition:
            self.passed += 1
            self.log(f"✅ PASS: {message}")
            return True
        else:
            self.failed += 1
            self.log(f"❌ FAIL: {message}")
            return False
    
    def summary(self) -> str:
        total = self.passed + self.failed
        status = "PASSED" if self.failed == 0 else "FAILED"
        return f"{self.name}: {status} ({self.passed}/{total})"


class HandshakeScenario(TestScenario):
    """
    Scenario 1: セキュアハンドシェイクフロー
    
    2つのエンティティが初めて通信するときの鍵交換プロセス:
    1. Entity A が X25519 エフェメラル鍵ペアを生成
    2. Entity A が公開鍵を Entity B に送信（署名付き）
    3. Entity B が X25519 エフェメラル鍵ペアを生成
    4. Entity B が共有鍵を導出し、応答を送信
    5. Entity A が共有鍵を導出
    6. 以降の通信は AES-256-GCM で暗号化
    """
    
    def __init__(self):
        super().__init__("Handshake")
    
    def run(self) -> bool:
        self.log("=== Starting Handshake Scenario ===")
        
        # 2つのエンティティをセットアップ
        priv_a, pub_a = generate_entity_keypair()
        priv_b, pub_b = generate_entity_keypair()
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_a
        crypto_a = CryptoManager("entity-a")
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_b
        crypto_b = CryptoManager("entity-b")
        
        # Step 1: Entity A がエフェメラル鍵を生成
        self.log("Step 1: Entity A generates ephemeral X25519 keypair")
        crypto_a.generate_x25519_keypair()
        pub_key_a_x25519 = crypto_a.get_x25519_public_key_b64()
        self.assert_true(pub_key_a_x25519 is not None, "Entity A X25519 public key generated")
        
        # Step 2: Entity A が公開鍵を署名付きで送信
        self.log("Step 2: Entity A sends public key with signature")
        handshake_msg = {
            "type": "handshake",
            "from": "entity-a",
            "to": "entity-b",
            "x25519_public_key": pub_key_a_x25519,
            "timestamp": time.time()
        }
        signature = crypto_a.sign_message(handshake_msg)
        self.assert_true(len(signature) > 0, "Handshake message signed")
        
        # Step 3: Entity B がエフェメラル鍵を生成
        self.log("Step 3: Entity B generates ephemeral X25519 keypair")
        crypto_b.generate_x25519_keypair()
        pub_key_b_x25519 = crypto_b.get_x25519_public_key_b64()
        self.assert_true(pub_key_b_x25519 is not None, "Entity B X25519 public key generated")
        
        # Step 4: Entity B が署名を検証し、共有鍵を導出
        self.log("Step 4: Entity B verifies signature and derives shared key")
        is_valid = crypto_b.verify_signature(
            handshake_msg, signature, crypto_a.get_ed25519_public_key_b64()
        )
        self.assert_true(is_valid, "Handshake signature verified by Entity B")
        
        shared_key_b = crypto_b.derive_shared_key(pub_key_a_x25519, "entity-a")
        self.assert_true(len(shared_key_b) == 32, "Shared key derived by Entity B (32 bytes)")
        
        # Step 5: Entity A が共有鍵を導出
        self.log("Step 5: Entity A derives shared key")
        shared_key_a = crypto_a.derive_shared_key(pub_key_b_x25519, "entity-b")
        self.assert_true(len(shared_key_a) == 32, "Shared key derived by Entity A (32 bytes)")
        
        # Step 6: 共有鍵が一致することを確認
        self.log("Step 6: Verify shared keys match")
        keys_match = shared_key_a == shared_key_b
        self.assert_true(keys_match, "Shared keys match between entities")
        
        self.log("=== Handshake Scenario Complete ===")
        return self.failed == 0


class SecureMessageScenario(TestScenario):
    """
    Scenario 2: セキュアメッセージ交換
    
    ハンドシェイク完了後の暗号化メッセージ交換:
    1. Entity A が暗号化メッセージを作成
    2. Entity B が復号・検証
    3. Entity B が応答を送信
    4. リプレイ攻撃の防止確認
    """
    
    def __init__(self):
        super().__init__("SecureMessage")
    
    def run(self) -> bool:
        self.log("=== Starting Secure Message Scenario ===")
        
        # セットアップ
        priv_a, pub_a = generate_entity_keypair()
        priv_b, pub_b = generate_entity_keypair()
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_a
        crypto_a = CryptoManager("entity-a")
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_b
        crypto_b = CryptoManager("entity-b")
        
        # ハンドシェイクをシミュレート
        crypto_a.generate_x25519_keypair()
        crypto_b.generate_x25519_keypair()
        crypto_a.derive_shared_key(crypto_b.get_x25519_public_key_b64(), "entity-b")
        crypto_b.derive_shared_key(crypto_a.get_x25519_public_key_b64(), "entity-a")
        
        # Step 1: Entity A が暗号化メッセージを作成
        self.log("Step 1: Entity A creates encrypted message")
        payload = {
            "from": "entity-a",
            "type": "task_delegation",
            "task": "分析レポート作成",
            "priority": "high",
            "deadline": "2026-02-01T12:00:00Z"
        }
        
        secure_msg = crypto_a.create_secure_message(
            payload=payload,
            encrypt=True,
            peer_public_key_b64=crypto_b.get_x25519_public_key_b64(),
            peer_id="entity-b"
        )
        self.assert_true(
            secure_msg.encrypted_payload is not None,
            "Message encrypted successfully"
        )
        
        # Step 2: Entity B が復号・検証
        self.log("Step 2: Entity B decrypts and verifies message")
        decrypted = crypto_b.verify_and_decrypt_message(
            secure_msg,
            peer_id="entity-a"
        )
        self.assert_true(decrypted is not None, "Message decrypted and verified")
        self.assert_true(
            decrypted.get("task") == "分析レポート作成",
            "Payload content preserved"
        )
        
        # Step 3: Entity B が応答を送信
        self.log("Step 3: Entity B sends encrypted response")
        response_payload = {
            "from": "entity-b",
            "type": "task_acceptance",
            "task_id": "task-001",
            "estimated_completion": "2026-02-01T10:00:00Z",
            "status": "accepted"
        }
        
        response_msg = crypto_b.create_secure_message(
            payload=response_payload,
            encrypt=True,
            peer_public_key_b64=crypto_a.get_x25519_public_key_b64(),
            peer_id="entity-a"
        )
        
        decrypted_response = crypto_a.verify_and_decrypt_message(
            response_msg,
            peer_id="entity-b"
        )
        self.assert_true(
            decrypted_response is not None,
            "Response decrypted and verified"
        )
        self.assert_true(
            decrypted_response.get("status") == "accepted",
            "Response content correct"
        )
        
        # Step 4: リプレイ攻撃防止の確認
        self.log("Step 4: Replay attack prevention check")
        # 同じメッセージを再度処理しようとすると失敗するはず
        replay_result = crypto_b.verify_and_decrypt_message(
            secure_msg,
            peer_id="entity-a"
        )
        self.assert_true(
            replay_result is None,
            "Replay attack prevented (duplicate nonce rejected)"
        )
        
        self.log("=== Secure Message Scenario Complete ===")
        return self.failed == 0


class SessionManagementScenario(TestScenario):
    """
    Scenario 3: JWTセッション管理
    
    長期セッションでのJWT認証フロー:
    1. Entity A がJWTトークンを生成（5分有効）
    2. Entity B がJWTを検証
    3. 期限切れJWTの拒否確認
    4. セッション継続中の複数メッセージ交換
    """
    
    def __init__(self):
        super().__init__("SessionManagement")
    
    def run(self) -> bool:
        self.log("=== Starting Session Management Scenario ===")
        
        # セットアップ
        priv_a, pub_a = generate_entity_keypair()
        priv_b, pub_b = generate_entity_keypair()
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_a
        crypto_a = CryptoManager("entity-a")
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_b
        crypto_b = CryptoManager("entity-b")
        
        pub_key_a = crypto_a.get_ed25519_public_key_b64()
        
        # Step 1: Entity A がJWTトークンを生成
        self.log("Step 1: Entity A creates JWT token (5min expiry)")
        jwt_token = crypto_a.create_jwt_token(audience="entity-b")
        self.assert_true(len(jwt_token) > 0, "JWT token created")
        
        # Step 2: Entity B がJWTを検証
        self.log("Step 2: Entity B verifies JWT token")
        decoded = crypto_b.verify_jwt_token(
            jwt_token,
            pub_key_a,
            audience="entity-b"
        )
        self.assert_true(decoded is not None, "JWT token valid")
        self.assert_true(
            decoded.get("sub") == "entity-a",
            "JWT subject correct"
        )
        self.assert_true(
            decoded.get("iss") == "peer-service",
            "JWT issuer correct"
        )
        
        # Step 3: 誤ったaudienceでの検証失敗
        self.log("Step 3: JWT verification with wrong audience (should fail)")
        wrong_aud = crypto_b.verify_jwt_token(
            jwt_token,
            pub_key_a,
            audience="entity-c"
        )
        self.assert_true(wrong_aud is None, "Wrong audience rejected")
        
        # Step 4: JWT付きセキュアメッセージ
        self.log("Step 4: Secure message with JWT authentication")
        secure_msg = crypto_a.create_secure_message(
            payload={"from": "entity-a", "type": "auth_test", "data": "secret"},
            include_jwt=True,
            jwt_audience="entity-b"
        )
        self.assert_true(
            secure_msg.jwt_token is not None,
            "Secure message includes JWT"
        )
        
        # JWTを検証してからペイロードを取得
        jwt_valid = crypto_b.verify_jwt_token(
            secure_msg.jwt_token,
            pub_key_a,
            audience="entity-b"
        )
        self.assert_true(jwt_valid is not None, "JWT in message is valid")
        
        # Step 5: 署名検証
        self.log("Step 5: Signature verification with JWT")
        payload = crypto_b.verify_and_decrypt_message(
            secure_msg,
            verify_jwt=True,
            jwt_audience="entity-b"
        )
        self.assert_true(payload is not None, "Message with JWT verified")
        
        self.log("=== Session Management Scenario Complete ===")
        return self.failed == 0


class ErrorHandlingScenario(TestScenario):
    """
    Scenario 4: エラー処理と攻撃防御
    
    異常系と攻撃シナリオのテスト:
    1. 改ざんされたメッセージの検出
    2. 期限切れタイムスタンプの拒否
    3. 無効な署名の拒否
    4. 誤った復号鍵での復号失敗
    5. 高速リプレイ攻撃の防止
    """
    
    def __init__(self):
        super().__init__("ErrorHandling")
    
    def run(self) -> bool:
        self.log("=== Starting Error Handling Scenario ===")
        
        # セットアップ
        priv_a, pub_a = generate_entity_keypair()
        priv_b, pub_b = generate_entity_keypair()
        priv_c, pub_c = generate_entity_keypair()  # 攻撃者
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_a
        crypto_a = CryptoManager("entity-a")
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_b
        crypto_b = CryptoManager("entity-b")
        
        os.environ["ENTITY_PRIVATE_KEY"] = priv_c
        crypto_c = CryptoManager("attacker")
        
        # ハンドシェイク
        crypto_a.generate_x25519_keypair()
        crypto_b.generate_x25519_keypair()
        shared_key_a = crypto_a.derive_shared_key(
            crypto_b.get_x25519_public_key_b64(), "entity-b"
        )
        shared_key_b = crypto_b.derive_shared_key(
            crypto_a.get_x25519_public_key_b64(), "entity-a"
        )
        
        # Test 1: 改ざんされた署名
        self.log("Test 1: Tampered signature detection")
        original_msg = {"type": "test", "data": "original"}
        signature = crypto_a.sign_message(original_msg)
        
        # 改ざんされたメッセージ
        tampered_msg = {"type": "test", "data": "tampered"}
        is_valid = crypto_b.verify_signature(
            tampered_msg, signature, crypto_a.get_ed25519_public_key_b64()
        )
        self.assert_true(not is_valid, "Tampered message signature rejected")
        
        # Test 2: 期限切れタイムスタンプ
        self.log("Test 2: Expired timestamp rejection")
        old_timestamp = time.time() - 120  # 2分前
        old_nonce = crypto_a.generate_nonce()
        
        result = crypto_b.check_and_record_nonce(old_nonce, old_timestamp)
        self.assert_true(not result, "Old timestamp rejected (>60s tolerance)")
        
        # Test 3: 無効な署名（別の鍵で署名）
        self.log("Test 3: Invalid signature from different key")
        forged_signature = crypto_c.sign_message(original_msg)
        is_forged_valid = crypto_b.verify_signature(
            original_msg, forged_signature, crypto_a.get_ed25519_public_key_b64()
        )
        self.assert_true(not is_forged_valid, "Forged signature rejected")
        
        # Test 4: 誤った復号鍵
        self.log("Test 4: Decryption with wrong key")
        ciphertext, nonce = crypto_a.encrypt_payload(
            {"secret": "data"},
            crypto_b.get_x25519_public_key_b64(),
            "entity-b"
        )
        
        # Entity C は正しい共有鍵を持っていない
        wrong_decrypt = crypto_c.decrypt_payload(ciphertext, nonce, "entity-b")
        self.assert_true(wrong_decrypt is None, "Decryption with wrong key failed")
        
        # Test 5: 高速リプレイ攻撃防止
        self.log("Test 5: Rapid replay attack prevention")
        nonce = crypto_a.generate_nonce()
        timestamp = time.time()
        
        # 初回は成功
        result1 = crypto_b.check_and_record_nonce(nonce, timestamp)
        self.assert_true(result1, "First nonce check passed")
        
        # 連続して同じnonceを試行
        results = []
        for i in range(10):
            results.append(crypto_b.check_and_record_nonce(nonce, timestamp))
        
        all_rejected = not any(results[1:])  # 最初以外は全部拒否される
        self.assert_true(all_rejected, "All replay attempts rejected")
        
        # Test 6: 未来のタイムスタンプ
        self.log("Test 6: Future timestamp rejection")
        future_timestamp = time.time() + 120  # 2分後
        future_nonce = crypto_a.generate_nonce()
        
        future_result = crypto_b.check_and_record_nonce(future_nonce, future_timestamp)
        self.assert_true(not future_result, "Future timestamp rejected")
        
        self.log("=== Error Handling Scenario Complete ===")
        return self.failed == 0


class WalletPersistenceScenario(TestScenario):
    """
    Scenario 5: ウォレット永続化統合
    
    ウォレットの作成・保存・読み込み・使用フロー:
    1. 新規ウォレット作成
    2. ウォレットからCryptoManager初期化
    3. メッセージ署名・検証
    4. ウォレット削除
    """
    
    def __init__(self):
        super().__init__("WalletPersistence")
        self.test_dir = None
        self.wallet_path = None
    
    def setup(self):
        self.test_dir = tempfile.mkdtemp()
        self.wallet_path = os.path.join(self.test_dir, "test_wallet.json")
    
    def cleanup(self):
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def run(self) -> bool:
        self.setup()
        try:
            self.log("=== Starting Wallet Persistence Scenario ===")
            
            # Step 1: 新規ウォレット作成
            self.log("Step 1: Create new wallet")
            wallet = WalletManager(self.wallet_path)
            password = "secure_password_123"
            
            self.assert_true(not wallet.wallet_exists(), "Wallet does not exist initially")
            
            priv_key, pub_key = wallet.create_wallet(password)
            self.assert_true(wallet.wallet_exists(), "Wallet created successfully")
            self.assert_true(len(priv_key) == 64, "Private key is 32 bytes (64 hex)")
            self.assert_true(len(pub_key) == 64, "Public key is 32 bytes (64 hex)")
            
            # Step 2: ウォレットからCryptoManager初期化
            self.log("Step 2: Initialize CryptoManager from wallet")
            os.environ["ENTITY_PRIVATE_KEY"] = priv_key
            crypto = CryptoManager("wallet-test-entity")
            
            # 公開鍵が一致することを確認
            derived_pub = crypto.get_ed25519_public_key_b64()
            expected_pub = base64.b64encode(bytes.fromhex(pub_key)).decode("ascii")
            self.assert_true(derived_pub == expected_pub, "Public key matches wallet")
            
            # Step 3: メッセージ署名・検証
            self.log("Step 3: Sign and verify message with wallet keys")
            test_payload = {
                "type": "wallet_test",
                "message": "Hello from wallet!",
                "timestamp": time.time()
            }
            
            signature = crypto.sign_message(test_payload)
            self.assert_true(len(signature) > 0, "Message signed with wallet key")
            
            is_valid = crypto.verify_signature(
                test_payload,
                signature,
                derived_pub
            )
            self.assert_true(is_valid, "Self-signature verified")
            
            # Step 4: 別インスタンスで読み込み
            self.log("Step 4: Load wallet in new instance")
            wallet2 = WalletManager(self.wallet_path)
            loaded_priv, loaded_pub = wallet2.load_wallet(password)
            
            self.assert_true(loaded_priv == priv_key, "Private key preserved")
            self.assert_true(loaded_pub == pub_key, "Public key preserved")
            
            # Step 5: 読み込んだ鍵で署名検証
            self.log("Step 5: Verify signature with loaded keys")
            os.environ["ENTITY_PRIVATE_KEY"] = loaded_priv
            crypto2 = CryptoManager("wallet-test-entity-2")
            
            # 以前の署名を検証
            is_valid_loaded = crypto2.verify_signature(
                test_payload,
                signature,
                derived_pub
            )
            self.assert_true(is_valid_loaded, "Signature verified with loaded keys")
            
            # Step 6: 新しい署名を作成
            new_payload = {"type": "new_message", "data": "test"}
            new_signature = crypto2.sign_message(new_payload)
            
            is_new_valid = crypto.verify_signature(
                new_payload,
                new_signature,
                crypto2.get_ed25519_public_key_b64()
            )
            self.assert_true(is_new_valid, "New signature cross-verified")
            
            # Step 7: 誤ったパスワードで読み込み失敗
            self.log("Step 7: Wrong password rejection")
            wallet3 = WalletManager(self.wallet_path)
            try:
                wallet3.load_wallet("wrong_password")
                self.assert_true(False, "Should have raised ValueError")
            except ValueError:
                self.assert_true(True, "Wrong password correctly rejected")
            
            self.log("=== Wallet Persistence Scenario Complete ===")
            return self.failed == 0
            
        finally:
            self.cleanup()


def run_all_scenarios():
    """全てのテストシナリオを実行"""
    print("=" * 60)
    print("Peer Communication Protocol - Integration Test Scenarios")
    print("=" * 60)
    print()
    
    scenarios = [
        HandshakeScenario(),
        SecureMessageScenario(),
        SessionManagementScenario(),
        ErrorHandlingScenario(),
        WalletPersistenceScenario(),
    ]
    
    results = []
    for scenario in scenarios:
        try:
            scenario.run()
        except Exception as e:
            scenario.log(f"❌ EXCEPTION: {e}")
            scenario.failed += 1
        results.append(scenario)
        print()
    
    # サマリー
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    for result in results:
        print(f"  {result.summary()}")
    
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total = total_passed + total_failed
    
    print()
    print(f"Total: {total_passed}/{total} passed")
    
    if total_failed == 0:
        print("🎉 All scenarios passed!")
        return True
    else:
        print(f"⚠️  {total_failed} tests failed")
        return False


if __name__ == "__main__":
    import base64
    success = run_all_scenarios()
    sys.exit(0 if success else 1)
