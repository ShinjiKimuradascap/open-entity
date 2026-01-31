#!/usr/bin/env python3
"""
WalletManager 包括的テスト

WalletManager の機能を包括的にテストする unittest ベースのテストスイート。
"""

import unittest
import tempfile
import shutil
import os
import sys
import json
import stat

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# All crypto utilities are now in services.crypto (crypto_utils is deprecated)
from crypto import WalletManager, generate_entity_keypair, CryptoManager


class TestWalletManager(unittest.TestCase):
    """WalletManager のテストクラス"""

    def setUp(self):
        """各テスト前のセットアップ: 一時ディレクトリを作成"""
        self.test_dir = tempfile.mkdtemp(prefix="wallet_test_")
        self.wallet_path = os.path.join(self.test_dir, "test_wallet.json")
        self.wallet = WalletManager(self.wallet_path)
        self.test_password = "test_password_123"

    def tearDown(self):
        """各テスト後のクリーンアップ: 一時ディレクトリを削除"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_create_wallet(self):
        """ウォレット作成、ファイル存在確認"""
        # 事前チェック: ウォレットは存在しない
        self.assertFalse(self.wallet.wallet_exists())

        # ウォレット作成
        priv_key, pub_key = self.wallet.create_wallet(self.test_password)

        # 検証
        self.assertTrue(self.wallet.wallet_exists())
        self.assertIsNotNone(priv_key)
        self.assertIsNotNone(pub_key)
        self.assertEqual(len(priv_key), 64)  # 32 bytes = 64 hex chars
        self.assertEqual(len(pub_key), 64)   # 32 bytes = 64 hex chars
        self.assertTrue(os.path.exists(self.wallet_path))

        # ファイルパーミッションチェック (0o600 = 所有者のみ読み書き)
        file_stat = os.stat(self.wallet_path)
        file_mode = stat.S_IMODE(file_stat.st_mode)
        self.assertEqual(file_mode, 0o600)

        # ウォレットファイルの構造確認
        with open(self.wallet_path, 'r') as f:
            wallet_data = json.load(f)

        self.assertEqual(wallet_data['version'], 1)
        self.assertEqual(wallet_data['public_key'], pub_key)
        self.assertIn('encrypted_private_key', wallet_data)
        self.assertIn('salt', wallet_data)
        self.assertIn('nonce', wallet_data)

        # 値が Base64 エンコードされていることを確認
        import base64
        try:
            base64.b64decode(wallet_data['encrypted_private_key'])
            base64.b64decode(wallet_data['salt'])
            base64.b64decode(wallet_data['nonce'])
        except Exception:
            self.fail("Wallet data should be Base64 encoded")

    def test_load_wallet(self):
        """読み込み、正しい鍵が得られるか"""
        # ウォレット作成
        orig_priv, orig_pub = self.wallet.create_wallet(self.test_password)

        # 新しいインスタンスで読み込み
        wallet2 = WalletManager(self.wallet_path)
        loaded_priv, loaded_pub = wallet2.load_wallet(self.test_password)

        # 検証
        self.assertEqual(loaded_priv, orig_priv)
        self.assertEqual(loaded_pub, orig_pub)

        # get_keys() メソッドでも確認
        mem_priv, mem_pub = wallet2.get_keys()
        self.assertEqual(mem_priv, orig_priv)
        self.assertEqual(mem_pub, orig_pub)

    def test_duplicate_creation_prevention(self):
        """既存ウォレットへの重複作成防止"""
        # ウォレット作成
        self.wallet.create_wallet(self.test_password)

        # 重複作成を試みるとエラー
        with self.assertRaises(FileExistsError):
            self.wallet.create_wallet(self.test_password)

        with self.assertRaises(FileExistsError):
            self.wallet.create_wallet("different_password")

    def test_wrong_password(self):
        """間違いパスワードで復号失敗"""
        # ウォレット作成
        self.wallet.create_wallet(self.test_password)

        # 間違ったパスワードで読み込み
        with self.assertRaises(ValueError) as context:
            self.wallet.load_wallet("wrong_password")

        self.assertIn("Invalid password", str(context.exception))

    def test_empty_password_rejection(self):
        """空パスワードの拒否"""
        with self.assertRaises(ValueError) as context:
            self.wallet.create_wallet("")

        self.assertIn("Password cannot be empty", str(context.exception))

    def test_nonexistent_wallet_load(self):
        """存在しないウォレット読み込みエラー"""
        nonexistent_path = os.path.join(self.test_dir, "nonexistent.json")
        wallet = WalletManager(nonexistent_path)

        with self.assertRaises(FileNotFoundError) as context:
            wallet.load_wallet(self.test_password)

        self.assertIn("Wallet not found", str(context.exception))

    def test_wallet_integrity_tampering(self):
        """ファイル改竄で復号失敗"""
        # ウォレット作成
        self.wallet.create_wallet(self.test_password)

        # ウォレットファイルを読み込み
        with open(self.wallet_path, 'r') as f:
            wallet_data = json.load(f)

        # encrypted_private_key を改竄
        original_encrypted = wallet_data['encrypted_private_key']
        wallet_data['encrypted_private_key'] = original_encrypted[:-10] + "AAAAAAAAAA"

        # 改竄したデータを保存
        with open(self.wallet_path, 'w') as f:
            json.dump(wallet_data, f)

        # 改竄されたファイルで読み込みを試みる
        with self.assertRaises(ValueError) as context:
            self.wallet.load_wallet(self.test_password)

        # salt を改竄
        wallet_data['encrypted_private_key'] = original_encrypted
        wallet_data['salt'] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

        with open(self.wallet_path, 'w') as f:
            json.dump(wallet_data, f)

        with self.assertRaises(ValueError):
            self.wallet.load_wallet(self.test_password)

    def test_wallet_integrity_corrupted_json(self):
        """JSON破損での読み込み失敗"""
        # ウォレット作成
        self.wallet.create_wallet(self.test_password)

        # ファイルを破損させる
        with open(self.wallet_path, 'w') as f:
            f.write("{invalid json")

        # 読み込みを試みる
        with self.assertRaises(json.JSONDecodeError):
            self.wallet.load_wallet(self.test_password)

    def test_wallet_integrity_missing_fields(self):
        """必須フィールド欠如での読み込み失敗"""
        # ウォレット作成
        self.wallet.create_wallet(self.test_password)

        # 必須フィールドを削除
        with open(self.wallet_path, 'r') as f:
            wallet_data = json.load(f)

        del wallet_data['encrypted_private_key']

        with open(self.wallet_path, 'w') as f:
            json.dump(wallet_data, f)

        with self.assertRaises(ValueError) as context:
            self.wallet.load_wallet(self.test_password)

        self.assertIn("Invalid wallet format", str(context.exception))

    def test_wallet_integrity_version_mismatch(self):
        """バージョン不一致での読み込み失敗"""
        # ウォレット作成
        self.wallet.create_wallet(self.test_password)

        # バージョンを変更
        with open(self.wallet_path, 'r') as f:
            wallet_data = json.load(f)

        wallet_data['version'] = 999

        with open(self.wallet_path, 'w') as f:
            json.dump(wallet_data, f)

        with self.assertRaises(ValueError) as context:
            self.wallet.load_wallet(self.test_password)

        self.assertIn("Unsupported wallet version", str(context.exception))

    def test_crypto_manager_integration(self):
        """CryptoManager と連携"""
        # ウォレット作成
        priv_key, pub_key = self.wallet.create_wallet(self.test_password)

        # 読み込み
        loaded_priv, loaded_pub = self.wallet.load_wallet(self.test_password)

        # CryptoManager で使用
        os.environ["ENTITY_PRIVATE_KEY"] = loaded_priv
        crypto = CryptoManager("test-entity")

        # 公開鍵が一致することを確認
        self.assertEqual(
            crypto.get_ed25519_public_key_b64(),
            base64.b64encode(bytes.fromhex(loaded_pub)).decode('ascii')
        )

        # 署名テスト
        test_payload = {"type": "wallet_test", "message": "hello"}
        signature = crypto.sign_message(test_payload)
        self.assertIsNotNone(signature)
        self.assertGreater(len(signature), 0)

        # 自己検証
        is_valid = crypto.verify_signature(
            test_payload,
            signature,
            crypto.get_ed25519_public_key_b64()
        )
        self.assertTrue(is_valid)

        # 改竄されたメッセージは拒否される
        tampered_payload = {"type": "wallet_test", "message": "tampered"}
        is_invalid = crypto.verify_signature(
            tampered_payload,
            signature,
            crypto.get_ed25519_public_key_b64()
        )
        self.assertFalse(is_invalid)

    def test_crypto_manager_with_different_entities(self):
        """異なるエンティティ間の署名・検証"""
        # エンティティAのウォレット
        wallet_a = WalletManager(os.path.join(self.test_dir, "wallet_a.json"))
        priv_a, pub_a = wallet_a.create_wallet("password_a")

        # エンティティBのウォレット
        wallet_b = WalletManager(os.path.join(self.test_dir, "wallet_b.json"))
        priv_b, pub_b = wallet_b.create_wallet("password_b")

        # CryptoManager 作成
        os.environ["ENTITY_PRIVATE_KEY"] = priv_a
        crypto_a = CryptoManager("entity-a")

        os.environ["ENTITY_PRIVATE_KEY"] = priv_b
        crypto_b = CryptoManager("entity-b")

        # エンティティAが署名
        message = {"from": "entity-a", "data": "hello"}
        signature = crypto_a.sign_message(message)

        # エンティティBが検証
        is_valid = crypto_b.verify_signature(
            message,
            signature,
            crypto_a.get_ed25519_public_key_b64()
        )
        self.assertTrue(is_valid)

        # 間違った公開鍵では検証失敗
        is_invalid = crypto_b.verify_signature(
            message,
            signature,
            crypto_b.get_ed25519_public_key_b64()  # Bの公開鍵で検証
        )
        self.assertFalse(is_invalid)

    def test_multiple_wallets(self):
        """複数ウォレット管理"""
        wallets = []
        keys = []

        # 複数のウォレットを作成
        for i in range(3):
            wallet_path = os.path.join(self.test_dir, f"wallet_{i}.json")
            wallet = WalletManager(wallet_path)
            priv, pub = wallet.create_wallet(f"password_{i}")
            wallets.append(wallet)
            keys.append((priv, pub))

        # 各ウォレットが独立していることを確認
        for i, (wallet, (orig_priv, orig_pub)) in enumerate(zip(wallets, keys)):
            # 存在確認
            self.assertTrue(wallet.wallet_exists())

            # 読み込み
            loaded_priv, loaded_pub = wallet.load_wallet(f"password_{i}")
            self.assertEqual(loaded_priv, orig_priv)
            self.assertEqual(loaded_pub, orig_pub)

        # 異なるパスワードでは読み込めない
        for i, wallet in enumerate(wallets):
            wrong_password_index = (i + 1) % 3
            with self.assertRaises(ValueError):
                wallet.load_wallet(f"password_{wrong_password_index}")

    def test_delete_wallet(self):
        """ウォレット削除"""
        # ウォレット作成
        self.wallet.create_wallet(self.test_password)
        self.assertTrue(self.wallet.wallet_exists())

        # 削除
        self.wallet.delete_wallet()
        self.assertFalse(self.wallet.wallet_exists())

        # メモリからもクリアされている
        priv, pub = self.wallet.get_keys()
        self.assertIsNone(priv)
        self.assertIsNone(pub)

        # 削除済みを再度削除するとエラー
        with self.assertRaises(FileNotFoundError):
            self.wallet.delete_wallet()

    def test_get_keys_before_load(self):
        """読み込み前の get_keys()"""
        priv, pub = self.wallet.get_keys()
        self.assertIsNone(priv)
        self.assertIsNone(pub)

    def test_wallet_directory_creation(self):
        """ウォレットディレクトリ自動作成"""
        nested_dir = os.path.join(self.test_dir, "level1", "level2")
        nested_wallet_path = os.path.join(nested_dir, "wallet.json")

        # ディレクトリはまだ存在しない
        self.assertFalse(os.path.exists(nested_dir))

        # ウォレット作成
        wallet = WalletManager(nested_wallet_path)
        wallet.create_wallet(self.test_password)

        # ディレクトリが自動作成されている
        self.assertTrue(os.path.exists(nested_dir))
        self.assertTrue(wallet.wallet_exists())

        # ディレクトリパーミッションを確認 (0o700)
        import stat as stat_module
        dir_stat = os.stat(os.path.dirname(nested_wallet_path))
        dir_mode = stat_module.S_IMODE(dir_stat.st_mode)
        self.assertEqual(dir_mode, 0o700)

    def test_default_wallet_path(self):
        """デフォルトウォレットパス"""
        wallet = WalletManager()
        expected_path = os.path.expanduser("~/.peer_service/wallet.json")
        self.assertEqual(wallet.wallet_path, expected_path)


class TestWalletManagerEdgeCases(unittest.TestCase):
    """WalletManager のエッジケーステスト"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wallet_edge_test_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_unicode_password(self):
        """Unicodeパスワードのテスト"""
        wallet_path = os.path.join(self.test_dir, "unicode_wallet.json")
        wallet = WalletManager(wallet_path)

        # Unicodeパスワード
        unicode_password = "パスワード🔐日本語"
        priv, pub = wallet.create_wallet(unicode_password)

        # 読み込み
        loaded_priv, loaded_pub = wallet.load_wallet(unicode_password)
        self.assertEqual(loaded_priv, priv)
        self.assertEqual(loaded_pub, pub)

    def test_long_password(self):
        """長いパスワードのテスト"""
        wallet_path = os.path.join(self.test_dir, "long_pass_wallet.json")
        wallet = WalletManager(wallet_path)

        # 非常に長いパスワード
        long_password = "A" * 1000
        priv, pub = wallet.create_wallet(long_password)

        # 読み込み
        loaded_priv, loaded_pub = wallet.load_wallet(long_password)
        self.assertEqual(loaded_priv, priv)
        self.assertEqual(loaded_pub, pub)

    def test_special_characters_password(self):
        """特殊文字を含むパスワードのテスト"""
        wallet_path = os.path.join(self.test_dir, "special_wallet.json")
        wallet = WalletManager(wallet_path)

        # 特殊文字を含むパスワード
        special_password = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        priv, pub = wallet.create_wallet(special_password)

        # 読み込み
        loaded_priv, loaded_pub = wallet.load_wallet(special_password)
        self.assertEqual(loaded_priv, priv)
        self.assertEqual(loaded_pub, pub)


def run_tests():
    """テストを実行して結果を表示"""
    print("=" * 60)
    print("WalletManager Comprehensive Tests")
    print("=" * 60)

    # テストスイートを作成
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # テストクラスを追加
    suite.addTests(loader.loadTestsFromTestCase(TestWalletManager))
    suite.addTests(loader.loadTestsFromTestCase(TestWalletManagerEdgeCases))

    # テスト実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 結果サマリー
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ All tests passed!")
        print(f"   Tests run: {result.testsRun}")
    else:
        print("❌ Some tests failed!")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == "__main__":
    import base64
    success = run_tests()
    sys.exit(0 if success else 1)
