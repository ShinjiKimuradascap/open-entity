#!/usr/bin/env python3
"""
S6: Keystore Security Practical Test Scenario
AES-256-GCM暗号化による鍵ストアのセキュリティテスト

Test Scenarios:
1. Basic Key Operations (save/load/delete)
2. Encryption Security (AES-256-GCM verification)
3. Password Protection (PBKDF2 key derivation)
4. File Permissions (0600/0700 checks)
5. Multi-entity Support (isolated key storage)
6. Error Handling (wrong password, tampering)
"""

import os
import sys
import json
import base64
import tempfile
import shutil
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from services.wallet_keystore import WalletKeyStore, get_keystore, reset_keystore


class TestResult:
    """テスト結果を記録"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.details = []
    
    def log(self, message: str, success: bool = True):
        status = "✅" if success else "❌"
        self.details.append(f"{status} {message}")
        print(f"  {status} {message}")
        if success:
            self.passed += 1
        else:
            self.failed += 1
    
    def summary(self):
        total = self.passed + self.failed
        return f"Passed: {self.passed}/{total}, Failed: {self.failed}"


def generate_test_keypair():
    """テスト用のEd25519鍵ペアを生成"""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    private_key_hex = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    ).hex()
    
    public_key_hex = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    ).hex()
    
    return private_key_hex, public_key_hex


def test_basic_key_operations():
    """
    Scenario 1: 基本的な鍵操作
    - 鍵の保存
    - 鍵の存在確認
    - 鍵の読み込み
    - 鍵の削除
    """
    print("\n=== Scenario 1: Basic Key Operations ===")
    result = TestResult()
    test_dir = tempfile.mkdtemp()
    
    try:
        keystore = WalletKeyStore(test_dir)
        entity_id = "test_entity_basic"
        password = "secure_password_123"
        
        # 鍵ペア生成
        priv_key, pub_key = generate_test_keypair()
        
        # Test 1.1: 鍵が存在しないことを確認
        exists = keystore.key_exists(entity_id)
        result.log(f"Key does not exist initially: {not exists}", not exists)
        
        # Test 1.2: 鍵を保存
        success = keystore.save_key(entity_id, priv_key, password, pub_key)
        result.log(f"Key saved successfully: {success}", success)
        
        # Test 1.3: 鍵が存在することを確認
        exists = keystore.key_exists(entity_id)
        result.log(f"Key exists after save: {exists}", exists)
        
        # Test 1.4: 鍵を読み込み
        loaded_priv, loaded_pub = keystore.load_key(entity_id, password)
        priv_match = loaded_priv == priv_key
        pub_match = loaded_pub == pub_key
        result.log(f"Loaded private key matches: {priv_match}", priv_match)
        result.log(f"Loaded public key matches: {pub_match}", pub_match)
        
        # Test 1.5: エンティティリスト
        entities = keystore.list_entities()
        in_list = entity_id in entities
        result.log(f"Entity in list: {in_list}", in_list)
        
        # Test 1.6: 鍵情報取得（秘密鍵は含まれない）
        info = keystore.get_key_info(entity_id)
        has_pub = info and "public_key" in info
        no_priv = info and "encrypted_private_key" not in info
        result.log(f"Key info has public key: {has_pub}", has_pub)
        result.log(f"Key info excludes private key: {no_priv}", no_priv)
        
        # Test 1.7: 鍵を削除
        deleted = keystore.delete_key(entity_id)
        result.log(f"Key deleted successfully: {deleted}", deleted)
        
        # Test 1.8: 削除後に存在しないことを確認
        exists_after = keystore.key_exists(entity_id)
        result.log(f"Key does not exist after delete: {not exists_after}", not exists_after)
        
    except Exception as e:
        result.log(f"Exception: {e}", False)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    
    return result


def test_encryption_security():
    """
    Scenario 2: 暗号化セキュリティ
    - AES-256-GCM暗号化の確認
    - 暗号化データの構造検証
    - 復号の正確性
    """
    print("\n=== Scenario 2: Encryption Security ===")
    result = TestResult()
    test_dir = tempfile.mkdtemp()
    
    try:
        keystore = WalletKeyStore(test_dir)
        entity_id = "test_entity_crypto"
        password = "crypto_test_pass_456"
        
        priv_key, pub_key = generate_test_keypair()
        
        # Test 2.1: 鍵を保存
        success = keystore.save_key(entity_id, priv_key, password, pub_key)
        result.log(f"Key saved with encryption: {success}", success)
        
        # Test 2.2: 鍵ファイルの構造を検証
        key_path = keystore._get_key_path(entity_id)
        with open(key_path, 'r') as f:
            key_data = json.load(f)
        
        required_fields = ["version", "entity_id", "public_key", 
                          "encrypted_private_key", "salt", "nonce", 
                          "created_at", "algorithm", "kdf", "kdf_iterations"]
        all_fields = all(field in key_data for field in required_fields)
        result.log(f"All required fields present: {all_fields}", all_fields)
        
        # Test 2.3: アルゴリズム確認
        algo_correct = key_data.get("algorithm") == "AES-256-GCM"
        kdf_correct = key_data.get("kdf") == "PBKDF2-SHA256"
        iter_correct = key_data.get("kdf_iterations") == 600000
        result.log(f"Algorithm is AES-256-GCM: {algo_correct}", algo_correct)
        result.log(f"KDF is PBKDF2-SHA256: {kdf_correct}", kdf_correct)
        result.log(f"PBKDF2 iterations is 600000: {iter_correct}", iter_correct)
        
        # Test 2.4: 暗号化データがBase64エンコードされている
        try:
            ciphertext = base64.b64decode(key_data["encrypted_private_key"])
            salt = base64.b64decode(key_data["salt"])
            nonce = base64.b64decode(key_data["nonce"])
            valid_b64 = True
        except Exception:
            valid_b64 = False
        result.log(f"Encrypted data is valid Base64: {valid_b64}", valid_b64)
        
        # Test 2.5: 復号が正確
        loaded_priv, loaded_pub = keystore.load_key(entity_id, password)
        decrypt_correct = loaded_priv == priv_key and loaded_pub == pub_key
        result.log(f"Decryption is accurate: {decrypt_correct}", decrypt_correct)
        
    except Exception as e:
        result.log(f"Exception: {e}", False)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    
    return result


def test_password_protection():
    """
    Scenario 3: パスワード保護
    - 間違ったパスワードでの復号失敗
    - パスワード変更
    - 異なるパスワードでの保存/読み込み
    """
    print("\n=== Scenario 3: Password Protection ===")
    result = TestResult()
    test_dir = tempfile.mkdtemp()
    
    try:
        keystore = WalletKeyStore(test_dir)
        entity_id = "test_entity_passwd"
        password1 = "first_password_123"
        password2 = "second_password_456"
        
        priv_key, pub_key = generate_test_keypair()
        
        # Test 3.1: 最初のパスワードで保存
        success = keystore.save_key(entity_id, priv_key, password1, pub_key)
        result.log(f"Key saved with password1: {success}", success)
        
        # Test 3.2: 正しいパスワードで読み込み成功
        loaded_priv, loaded_pub = keystore.load_key(entity_id, password1)
        load_success = loaded_priv == priv_key
        result.log(f"Load with correct password succeeds: {load_success}", load_success)
        
        # Test 3.3: 間違ったパスワードで読み込み失敗
        try:
            keystore.load_key(entity_id, "wrong_password")
            wrong_pass_rejected = False
        except ValueError:
            wrong_pass_rejected = True
        result.log(f"Wrong password rejected: {wrong_pass_rejected}", wrong_pass_rejected)
        
        # Test 3.4: パスワード変更
        changed = keystore.change_password(entity_id, password1, password2)
        result.log(f"Password change successful: {changed}", changed)
        
        # Test 3.5: 新しいパスワードで読み込み成功
        loaded_priv2, loaded_pub2 = keystore.load_key(entity_id, password2)
        load_with_new = loaded_priv2 == priv_key
        result.log(f"Load with new password succeeds: {load_with_new}", load_with_new)
        
        # Test 3.6: 古いパスワードで読み込み失敗
        try:
            keystore.load_key(entity_id, password1)
            old_pass_rejected = False
        except ValueError:
            old_pass_rejected = True
        result.log(f"Old password rejected after change: {old_pass_rejected}", old_pass_rejected)
        
    except Exception as e:
        result.log(f"Exception: {e}", False)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    
    return result


def test_file_permissions():
    """
    Scenario 4: ファイルパーミッション
    - 鍵ファイル: 0600 (所有者のみ読み書き)
    - ディレクトリ: 0700 (所有者のみアクセス)
    """
    print("\n=== Scenario 4: File Permissions ===")
    result = TestResult()
    test_dir = tempfile.mkdtemp()
    
    try:
        keystore = WalletKeyStore(test_dir)
        entity_id = "test_entity_perms"
        password = "perm_test_pass_789"
        
        priv_key, pub_key = generate_test_keypair()
        
        # Test 4.1: ディレクトリパーミッション確認
        dir_stat = os.stat(test_dir)
        dir_perms = oct(dir_stat.st_mode & 0o777)
        dir_correct = (dir_stat.st_mode & 0o777) == 0o700
        result.log(f"Directory permissions: {dir_perms} (expected: 0o700)", dir_correct)
        
        # Test 4.2: 鍵を保存
        keystore.save_key(entity_id, priv_key, password, pub_key)
        
        # Test 4.3: ファイルパーミッション確認
        key_path = keystore._get_key_path(entity_id)
        file_stat = os.stat(key_path)
        file_perms = oct(file_stat.st_mode & 0o777)
        file_correct = (file_stat.st_mode & 0o777) == 0o600
        result.log(f"Key file permissions: {file_perms} (expected: 0o600)", file_correct)
        
    except Exception as e:
        result.log(f"Exception: {e}", False)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    
    return result


def test_multi_entity_support():
    """
    Scenario 5: マルチエンティティサポート
    - 複数エンティティの鍵を独立して管理
    - エンティティ間の分離
    - 個別のパスワード管理
    """
    print("\n=== Scenario 5: Multi-Entity Support ===")
    result = TestResult()
    test_dir = tempfile.mkdtemp()
    
    try:
        keystore = WalletKeyStore(test_dir)
        
        # 複数エンティティの設定
        entities = [
            ("entity_a", "pass_a_123", generate_test_keypair()),
            ("entity_b", "pass_b_456", generate_test_keypair()),
            ("entity_c", "pass_c_789", generate_test_keypair()),
        ]
        
        # Test 5.1: 全エンティティの鍵を保存
        all_saved = True
        for entity_id, password, (priv_key, pub_key) in entities:
            saved = keystore.save_key(entity_id, priv_key, password, pub_key)
            all_saved = all_saved and saved
        result.log(f"All entities saved: {all_saved}", all_saved)
        
        # Test 5.2: エンティティリスト
        entity_list = keystore.list_entities()
        all_in_list = all(e[0] in entity_list for e in entities)
        result.log(f"All entities in list: {all_in_list}", all_in_list)
        result.log(f"Entity count: {len(entity_list)} (expected: 3)", len(entity_list) == 3)
        
        # Test 5.3: 各エンティティを独立して読み込み
        all_loaded_correctly = True
        for entity_id, password, (expected_priv, expected_pub) in entities:
            loaded_priv, loaded_pub = keystore.load_key(entity_id, password)
            correct = loaded_priv == expected_priv and loaded_pub == expected_pub
            all_loaded_correctly = all_loaded_correctly and correct
        result.log(f"All entities loaded correctly: {all_loaded_correctly}", all_loaded_correctly)
        
        # Test 5.4: エンティティAのパスワードでエンティティBは読み込めない
        try:
            keystore.load_key("entity_b", "pass_a_123")  # AのパスワードでBを読み込み
            cross_load_blocked = False
        except ValueError:
            cross_load_blocked = True
        result.log(f"Cross-entity password protection: {cross_load_blocked}", cross_load_blocked)
        
        # Test 5.5: エンティティを個別に削除
        deleted = keystore.delete_key("entity_b")
        result.log(f"Individual entity deletion: {deleted}", deleted)
        
        remaining = keystore.list_entities()
        b_removed = "entity_b" not in remaining
        others_intact = "entity_a" in remaining and "entity_c" in remaining
        result.log(f"Deleted entity removed: {b_removed}", b_removed)
        result.log(f"Other entities intact: {others_intact}", others_intact)
        
    except Exception as e:
        result.log(f"Exception: {e}", False)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    
    return result


def test_error_handling():
    """
    Scenario 6: エラーハンドリング
    - 存在しないエンティティ
    - 空パスワード
    - 無効な鍵形式
    - 改ざん検出
    """
    print("\n=== Scenario 6: Error Handling ===")
    result = TestResult()
    test_dir = tempfile.mkdtemp()
    
    try:
        keystore = WalletKeyStore(test_dir)
        
        # Test 6.1: 存在しないエンティティの読み込み
        try:
            keystore.load_key("nonexistent_entity", "password")
            not_found_handled = False
        except FileNotFoundError:
            not_found_handled = True
        result.log(f"Non-existent entity raises FileNotFoundError: {not_found_handled}", not_found_handled)
        
        # Test 6.2: 存在しないエンティティの削除
        try:
            keystore.delete_key("nonexistent_entity")
            delete_not_found = False
        except FileNotFoundError:
            delete_not_found = True
        result.log(f"Delete non-existent raises FileNotFoundError: {delete_not_found}", delete_not_found)
        
        # Test 6.3: 空パスワード
        priv_key, pub_key = generate_test_keypair()
        try:
            keystore.save_key("test_entity", priv_key, "", pub_key)
            empty_pass_rejected = False
        except ValueError:
            empty_pass_rejected = True
        result.log(f"Empty password rejected: {empty_pass_rejected}", empty_pass_rejected)
        
        # Test 6.4: 無効な鍵形式（短すぎる）
        try:
            keystore.save_key("test_entity", "short_key", "password", pub_key)
            short_key_rejected = False
        except ValueError:
            short_key_rejected = True
        result.log(f"Short key rejected: {short_key_rejected}", short_key_rejected)
        
        # Test 6.5: 無効な鍵形式（長すぎる）
        try:
            keystore.save_key("test_entity", priv_key + "extra", "password", pub_key)
            long_key_rejected = False
        except ValueError:
            long_key_rejected = True
        result.log(f"Long key rejected: {long_key_rejected}", long_key_rejected)
        
        # Test 6.6: 改ざまれた鍵ファイルの検出
        entity_id = "tamper_test"
        password = "tamper_pass_123"
        keystore.save_key(entity_id, priv_key, password, pub_key)
        
        key_path = keystore._get_key_path(entity_id)
        with open(key_path, 'r') as f:
            key_data = json.load(f)
        
        # nonceを変更して改ざん
        key_data["nonce"] = base64.b64encode(b"tampered123").decode("ascii")
        with open(key_path, 'w') as f:
            json.dump(key_data, f)
        
        try:
            keystore.load_key(entity_id, password)
            tamper_detected = False
        except ValueError:
            tamper_detected = True
        result.log(f"Tampered file detected: {tamper_detected}", tamper_detected)
        
    except Exception as e:
        result.log(f"Exception: {e}", False)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    
    return result


def run_all_tests():
    """全テストシナリオを実行"""
    print("=" * 60)
    print("S6: Keystore Security - Practical Test Scenarios")
    print("=" * 60)
    print("Testing: AES-256-GCM encryption, PBKDF2 key derivation")
    print("         File permissions (0600/0700), Multi-entity support")
    
    results = []
    
    # 各シナリオを実行
    results.append(test_basic_key_operations())
    results.append(test_encryption_security())
    results.append(test_password_protection())
    results.append(test_file_permissions())
    results.append(test_multi_entity_support())
    results.append(test_error_handling())
    
    # サマリー
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total = total_passed + total_failed
    
    for i, result in enumerate(results, 1):
        print(f"  Scenario {i}: {result.summary()}")
    
    print()
    print(f"Total: {total_passed}/{total} passed")
    
    if total_failed == 0:
        print("🎉 All S6 keystore security tests passed!")
        return True
    else:
        print(f"⚠️  {total_failed} tests failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
