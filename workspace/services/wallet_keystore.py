#!/usr/bin/env python3
"""
Wallet Key Store
マルチエンティティ対応の鍵永続化管理モジュール

機能:
- 複数エンティティの鍵を管理（save_key, load_key, list_entities, delete_key, key_exists）
- AES-256-GCM暗号化によるパスワード保護
- PBKDF2によるキー導出（600,000回イテレーション）
- 安全なファイルパーミッション（0600）とディレクトリパーミッション（0700）
"""

import os
import json
import base64
import secrets
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

# 定数
KEYSTORE_VERSION = 1
PBKDF2_ITERATIONS = 600000  # OWASP推奨値
SALT_SIZE_BYTES = 32  # 256-bit salt
NONCE_SIZE_BYTES = 12  # 96-bit nonce for AES-GCM
AES_KEY_SIZE_BYTES = 32  # 256-bit key
FILE_PERMISSIONS = 0o600  # 所有者のみ読み書き
DIR_PERMISSIONS = 0o700  # 所有者のみアクセス


class WalletKeyStore:
    """
    マルチエンティティ対応の鍵ストア
    
    複数のエンティティの鍵を個別の暗号化ファイルとして管理する。
    各エンティティの秘密鍵はAES-256-GCMで暗号化され、
    パスワードからPBKDF2で導出されたキーで保護される。
    """
    
    def __init__(self, keystore_dir: Optional[str] = None):
        """
        WalletKeyStoreを初期化
        
        Args:
            keystore_dir: 鍵ストアディレクトリのパス
                         （省略時は ~/.peer_service/keystore/）
        """
        if keystore_dir is None:
            keystore_dir = os.path.expanduser("~/.peer_service/keystore")
        
        self.keystore_dir = Path(keystore_dir)
        self._ensure_keystore_directory()
    
    def _ensure_keystore_directory(self) -> None:
        """鍵ストアディレクトリが存在しない場合は作成（安全なパーミッションで）"""
        if not self.keystore_dir.exists():
            self.keystore_dir.mkdir(parents=True, exist_ok=True)
            # ディレクトリパーミッションを0700に設定（所有者のみアクセス）
            os.chmod(self.keystore_dir, DIR_PERMISSIONS)
            logger.info(f"Created keystore directory: {self.keystore_dir}")
    
    def _get_key_path(self, entity_id: str) -> Path:
        """
        エンティティIDに対応する鍵ファイルのパスを取得
        
        Args:
            entity_id: エンティティID
            
        Returns:
            鍵ファイルのパス
        """
        # 安全なファイル名に変換（特殊文字を除去）
        safe_entity_id = "".join(c for c in entity_id if c.isalnum() or c in "_-").rstrip()
        if not safe_entity_id:
            raise ValueError(f"Invalid entity_id: {entity_id}")
        return self.keystore_dir / f"{safe_entity_id}.key"
    
    def _derive_key_from_password(self, password: str, salt: bytes) -> bytes:
        """
        パスワードからPBKDF2で暗号化鍵を導出
        
        Args:
            password: ユーザーのパスワード
            salt: ランダムソルト
            
        Returns:
            32バイトの暗号化鍵
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=AES_KEY_SIZE_BYTES,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return kdf.derive(password.encode("utf-8"))
    
    def save_key(
        self, 
        entity_id: str, 
        private_key_hex: str, 
        password: Optional[str] = None,
        public_key_hex: Optional[str] = None
    ) -> bool:
        """
        エンティティの鍵を保存（パスワード暗号化対応）
        
        Args:
            entity_id: エンティティID
            private_key_hex: 16進数エンコードされた秘密鍵
            password: 暗号化用パスワード（Noneの場合は平文保存）
            public_key_hex: 16進数エンコードされた公開鍵（省略時は秘密鍵から導出）
            
        Returns:
            保存成功時はTrue、失敗時はFalse
            
        Raises:
            ValueError: 鍵の形式が無効な場合
        """
        
        if not private_key_hex or len(private_key_hex) != 64:
            raise ValueError("Invalid private key format: expected 64 hex characters")
        
        try:
            # 公開鍵が指定されていない場合は秘密鍵から導出
            if public_key_hex is None:
                private_key_bytes = bytes.fromhex(private_key_hex)
                private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
                public_key = private_key.public_key()
                public_key_hex = public_key.public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                ).hex()
            
            # 鍵データを構築（共通フィールド）
            key_data = {
                "version": KEYSTORE_VERSION,
                "entity_id": entity_id,
                "public_key": public_key_hex,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # パスワードが指定されている場合は暗号化
            if password:
                # 暗号化用のソルトとnonceを生成
                salt = secrets.token_bytes(SALT_SIZE_BYTES)
                nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
                
                # パスワードから暗号化鍵を導出
                encryption_key = self._derive_key_from_password(password, salt)
                
                # 秘密鍵をAES-256-GCMで暗号化
                private_key_bytes = bytes.fromhex(private_key_hex)
                aesgcm = AESGCM(encryption_key)
                ciphertext = aesgcm.encrypt(nonce, private_key_bytes, None)
                
                # 暗号化情報を追加
                key_data["encrypted"] = True
                key_data["encrypted_private_key"] = base64.b64encode(ciphertext).decode("ascii")
                key_data["salt"] = base64.b64encode(salt).decode("ascii")
                key_data["nonce"] = base64.b64encode(nonce).decode("ascii")
                key_data["algorithm"] = "AES-256-GCM"
                key_data["kdf"] = "PBKDF2-SHA256"
                key_data["kdf_iterations"] = PBKDF2_ITERATIONS
            else:
                # 平文保存
                key_data["encrypted"] = False
                key_data["private_key"] = private_key_hex
            
            # 鍵ファイルを保存
            key_path = self._get_key_path(entity_id)
            with open(key_path, "w", encoding="utf-8") as f:
                json.dump(key_data, f, indent=2)
            
            # ファイルパーミッションを0600に設定（所有者のみ読み書き）
            os.chmod(key_path, FILE_PERMISSIONS)
            
            logger.info(f"Saved key for entity: {entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save key for entity {entity_id}: {e}")
            return False
    
    def load_key(self, entity_id: str, password: Optional[str] = None) -> Tuple[str, str]:
        """
        エンティティの鍵を読み込み（暗号化/平文両対応）
        
        Args:
            entity_id: エンティティID
            password: 復号用パスワード（暗号化ファイルの場合は必須）
            
        Returns:
            (private_key_hex, public_key_hex)のタプル
            
        Raises:
            FileNotFoundError: 鍵ファイルが存在しない場合
            ValueError: パスワードが間違っているか形式が無効な場合
        """
        key_path = self._get_key_path(entity_id)
        
        if not key_path.exists():
            raise FileNotFoundError(f"Key not found for entity: {entity_id}")
        
        try:
            # 鍵ファイルを読み込み
            with open(key_path, "r", encoding="utf-8") as f:
                key_data = json.load(f)
            
            # バージョンチェック
            version = key_data.get("version")
            if version != KEYSTORE_VERSION:
                raise ValueError(f"Unsupported keystore version: {version}")
            
            public_key_hex = key_data["public_key"]
            is_encrypted = key_data.get("encrypted", True)
            
            if is_encrypted:
                # 暗号化ファイルの場合、パスワードが必要
                if not password:
                    raise ValueError("Password required for encrypted key file")
                
                # データをデコード
                try:
                    ciphertext = base64.b64decode(key_data["encrypted_private_key"])
                    salt = base64.b64decode(key_data["salt"])
                    nonce = base64.b64decode(key_data["nonce"])
                except (KeyError, base64.binascii.Error) as e:
                    raise ValueError(f"Invalid key file format: {e}")
                
                # パスワードから暗号化鍵を導出
                encryption_key = self._derive_key_from_password(password, salt)
                
                # 秘密鍵を復号
                try:
                    aesgcm = AESGCM(encryption_key)
                    private_key_bytes = aesgcm.decrypt(nonce, ciphertext, None)
                except Exception as e:
                    raise ValueError("Invalid password or corrupted key data") from e
                
                private_key_hex = private_key_bytes.hex()
            else:
                # 平文ファイル
                private_key_hex = key_data.get("private_key")
                if not private_key_hex:
                    raise ValueError("Invalid key file: missing private_key field")
                private_key_bytes = bytes.fromhex(private_key_hex)
            
            # 整合性チェック：公開鍵が一致するか確認
            try:
                private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
                derived_public_key = private_key.public_key()
                derived_public_bytes = derived_public_key.public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                )
                if derived_public_bytes.hex() != public_key_hex:
                    raise ValueError("Public key mismatch: key file may be corrupted")
            except Exception as e:
                raise ValueError(f"Key validation failed: {e}")
            
            logger.info(f"Loaded key for entity: {entity_id}")
            return private_key_hex, public_key_hex
            
        except (FileNotFoundError, ValueError):
            raise
        except Exception as e:
            logger.error(f"Failed to load key for entity {entity_id}: {e}")
            raise ValueError(f"Failed to load key: {e}") from e
    
    def list_entities(self) -> List[Dict[str, Any]]:
        """
        保存されている全エンティティの詳細情報リストを取得
        
        Returns:
            エンティティ情報の辞書リスト（entity_id, public_key, created_at, encrypted）
        """
        entities = []
        try:
            for key_file in self.keystore_dir.glob("*.key"):
                try:
                    with open(key_file, "r", encoding="utf-8") as f:
                        key_data = json.load(f)
                    
                    entities.append({
                        "entity_id": key_data.get("entity_id", key_file.stem),
                        "public_key": key_data.get("public_key", "unknown"),
                        "created_at": key_data.get("created_at", "unknown"),
                        "encrypted": key_data.get("encrypted", True),
                        "algorithm": key_data.get("algorithm", "Ed25519"),
                    })
                except Exception as e:
                    logger.warning(f"Failed to read key file {key_file}: {e}")
        except Exception as e:
            logger.error(f"Failed to list entities: {e}")
        
        return sorted(entities, key=lambda x: x["entity_id"])
    
    def delete_key(self, entity_id: str) -> bool:
        """
        エンティティの鍵ファイルを削除
        
        Args:
            entity_id: エンティティID
            
        Returns:
            削除成功時はTrue、失敗時はFalse
            
        Raises:
            FileNotFoundError: 鍵ファイルが存在しない場合
        """
        key_path = self._get_key_path(entity_id)
        
        if not key_path.exists():
            raise FileNotFoundError(f"Key not found for entity: {entity_id}")
        
        try:
            key_path.unlink()
            logger.info(f"Deleted key for entity: {entity_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete key for entity {entity_id}: {e}")
            return False
    
    def key_exists(self, entity_id: str) -> bool:
        """
        エンティティの鍵が存在するかチェック
        
        Args:
            entity_id: エンティティID
            
        Returns:
            鍵が存在すればTrue、存在しなければFalse
        """
        key_path = self._get_key_path(entity_id)
        return key_path.exists()
    
    def get_key_info(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        エンティティの鍵情報を取得（秘密鍵は除く）
        
        Args:
            entity_id: エンティティID
            
        Returns:
            鍵情報の辞書、存在しない場合はNone
        """
        key_path = self._get_key_path(entity_id)
        
        if not key_path.exists():
            return None
        
        try:
            with open(key_path, "r", encoding="utf-8") as f:
                key_data = json.load(f)
            
            # 秘密鍵を除いた情報を返す
            return {
                "entity_id": key_data.get("entity_id"),
                "public_key": key_data.get("public_key"),
                "created_at": key_data.get("created_at"),
                "version": key_data.get("version"),
                "algorithm": key_data.get("algorithm"),
                "kdf": key_data.get("kdf"),
                "encrypted": key_data.get("encrypted", True),
            }
        except Exception as e:
            logger.error(f"Failed to get key info for entity {entity_id}: {e}")
            return None
    
    def change_password(
        self, 
        entity_id: str, 
        old_password: str, 
        new_password: str
    ) -> bool:
        """
        エンティティの鍵のパスワードを変更
        
        Args:
            entity_id: エンティティID
            old_password: 現在のパスワード
            new_password: 新しいパスワード
            
        Returns:
            変更成功時はTrue、失敗時はFalse
        """
        if not new_password:
            raise ValueError("New password cannot be empty")
        
        try:
            # 現在の鍵を読み込み
            private_key_hex, public_key_hex = self.load_key(entity_id, old_password)
            
            # 新しいパスワードで保存
            return self.save_key(entity_id, private_key_hex, new_password, public_key_hex)
            
        except Exception as e:
            logger.error(f"Failed to change password for entity {entity_id}: {e}")
            return False


# グローバルキーストアインスタンス
_keystore_instance: Optional[WalletKeyStore] = None


def get_keystore(keystore_dir: Optional[str] = None) -> WalletKeyStore:
    """
    グローバルキーストアインスタンスを取得
    
    Args:
        keystore_dir: 鍵ストアディレクトリ（省略時はデフォルト）
        
    Returns:
        WalletKeyStoreインスタンス
    """
    global _keystore_instance
    if _keystore_instance is None:
        _keystore_instance = WalletKeyStore(keystore_dir)
    return _keystore_instance


def reset_keystore() -> None:
    """グローバルキーストアインスタンスをリセット（テスト用）"""
    global _keystore_instance
    _keystore_instance = None


if __name__ == "__main__":
    # 簡単なテスト
    import tempfile
    import shutil
    
    logging.basicConfig(level=logging.INFO)
    
    print("=== WalletKeyStore Test ===")
    
    # テスト用の一時ディレクトリを作成
    test_dir = tempfile.mkdtemp()
    
    try:
        # キーストアを初期化
        keystore = WalletKeyStore(test_dir)
        password = "test_password_secure_123"
        
        # テスト用の鍵を生成
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
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
        
        entity_id = "test_entity_001"
        
        # テスト1: 存在確認（まだ存在しない）
        print("\n--- Test 1: Key Existence Check ---")
        exists = keystore.key_exists(entity_id)
        print(f"Key exists (should be False): {exists}")
        assert not exists, "Key should not exist initially"
        
        # テスト2: 鍵の保存
        print("\n--- Test 2: Save Key ---")
        result = keystore.save_key(entity_id, private_key_hex, password)
        print(f"Save result (should be True): {result}")
        assert result, "Save should succeed"
        
        exists = keystore.key_exists(entity_id)
        print(f"Key exists after save (should be True): {exists}")
        assert exists, "Key should exist after save"
        
        # ファイルパーミッションチェック
        key_path = keystore._get_key_path(entity_id)
        mode = os.stat(key_path).st_mode
        print(f"File permissions: {oct(mode & 0o777)} (expected: 600)")
        
        # ディレクトリパーミッションチェック
        dir_mode = os.stat(test_dir).st_mode
        print(f"Directory permissions: {oct(dir_mode & 0o777)} (expected: 700)")
        
        # テスト3: エンティティリスト
        print("\n--- Test 3: List Entities ---")
        entities = keystore.list_entities()
        print(f"Entities: {entities}")
        assert entity_id in entities, "Entity should be in list"
        
        # テスト4: 鍵の読み込み
        print("\n--- Test 4: Load Key ---")
        loaded_priv, loaded_pub = keystore.load_key(entity_id, password)
        print(f"Loaded successfully")
        print(f"  Private key matches: {loaded_priv == private_key_hex}")
        print(f"  Public key matches: {loaded_pub == public_key_hex}")
        assert loaded_priv == private_key_hex, "Private keys should match"
        assert loaded_pub == public_key_hex, "Public keys should match"
        
        # テスト5: 間違ったパスワード
        print("\n--- Test 5: Wrong Password ---")
        try:
            keystore.load_key(entity_id, "wrong_password")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            print(f"Correctly rejected wrong password: {e}")
        
        # テスト6: 鍵情報取得
        print("\n--- Test 6: Key Info ---")
        info = keystore.get_key_info(entity_id)
        print(f"Key info: {info}")
        assert info is not None, "Key info should exist"
        assert info["entity_id"] == entity_id, "Entity ID should match"
        assert "public_key" in info, "Public key should be in info"
        assert "encrypted_private_key" not in info, "Private key should not be in info"
        
        # テスト7: パスワード変更
        print("\n--- Test 7: Change Password ---")
        new_password = "new_secure_password_456"
        result = keystore.change_password(entity_id, password, new_password)
        print(f"Password change result (should be True): {result}")
        assert result, "Password change should succeed"
        
        # 新しいパスワードで読み込み
        loaded_priv2, loaded_pub2 = keystore.load_key(entity_id, new_password)
        print(f"Load with new password: success")
        assert loaded_priv2 == private_key_hex, "Keys should still match after password change"
        
        # テスト8: 鍵の削除
        print("\n--- Test 8: Delete Key ---")
        result = keystore.delete_key(entity_id)
        print(f"Delete result (should be True): {result}")
        assert result, "Delete should succeed"
        
        exists = keystore.key_exists(entity_id)
        print(f"Key exists after delete (should be False): {exists}")
        assert not exists, "Key should not exist after delete"
        
        print("\n=== All WalletKeyStore tests passed ===")
        
    finally:
        # クリーンアップ
        shutil.rmtree(test_dir)
        print(f"\nCleaned up test directory: {test_dir}")
