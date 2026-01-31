#!/usr/bin/env python3
"""
Cryptographic utilities for peer communication
Ed25519 signatures, X25519 key exchange, AES-256-GCM encryption, JWT authentication

This module provides:
- CryptoManager: Main cryptographic operations
- SecureMessage: Secure message structure
- WalletManager: Wallet persistence management
- generate_entity_keypair: Key pair generation
- MessageValidator: Protocol message validation
- KeyPair: Ed25519 key pair management
- MessageSigner/SignatureVerifier: Message signing and verification

Unified module - combines functionality from legacy crypto_utils.py
"""

import os
import json
import base64
import hashlib
import secrets
import time
import uuid
import logging
import warnings
from typing import Optional, Tuple, Dict, Any, Set, List
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta

import jwt
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidSignature

# Import MessageChunk from chunked_transfer
try:
    from chunked_transfer import MessageChunk
except ImportError:
    MessageChunk = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

TIMESTAMP_TOLERANCE_SECONDS = 60  # 60秒の許容範囲
JWT_EXPIRY_MINUTES = 5  # 5分の有効期限
NONCE_SIZE_BYTES = 16  # 128-bit nonce
AES_KEY_SIZE_BYTES = 32  # 256-bit key for AES-256-GCM
REPLAY_WINDOW_SECONDS = 300  # 5-minute duplicate detection window

# ============================================================================
# SecureMessage
# ============================================================================

@dataclass
class SecureMessage:
    """セキュアメッセージ構造体"""
    payload: Dict[str, Any]  # 元のメッセージ内容
    timestamp: float  # UNIX timestamp (seconds)
    nonce: str  # Base64 encoded 128-bit nonce
    signature: str  # Base64 encoded Ed25519 signature
    encrypted_payload: Optional[str] = None  # Optional: encrypted payload (Base64)
    sender_public_key: Optional[str] = None  # Optional: sender's Ed25519 public key (Base64)
    jwt_token: Optional[str] = None  # Optional: JWT token for session auth
    sender_id: Optional[str] = None  # Sender entity ID
    session_id: Optional[str] = None  # Session UUID (v1.0)
    sequence_num: Optional[int] = None  # Sequence number (v1.0)

    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecureMessage":
        """辞書から生成"""
        return cls(
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", 0.0),
            nonce=data.get("nonce", ""),
            signature=data.get("signature", ""),
            encrypted_payload=data.get("encrypted_payload"),
            sender_public_key=data.get("sender_public_key"),
            jwt_token=data.get("jwt_token"),
            sender_id=data.get("sender_id"),
            session_id=data.get("session_id"),
            sequence_num=data.get("sequence_num"),
        )


# ============================================================================
# CryptoManager
# ============================================================================

class CryptoManager:
    """暗号化管理クラス
    
    Ed25519署名、X25519鍵交換、AES-256-GCM暗号化、JWT認証を管理する。
    """

    def __init__(self, entity_id: str, private_key_hex: Optional[str] = None):
        """CryptoManagerを初期化
        
        Args:
            entity_id: このエンティティのID
            private_key_hex: 16進数エンコードされたEd25519秘密鍵（省略時は環境変数から読み込み）
        """
        self.entity_id = entity_id
        self._seen_nonces: Set[str] = set()  # リプレイ防止用nonce記録
        self._nonce_timestamps: Dict[str, float] = {}  # nonceのタイムスタンプ記録
        
        # 秘密鍵の読み込み
        if private_key_hex:
            private_key_bytes = bytes.fromhex(private_key_hex)
        else:
            env_key = os.environ.get("ENTITY_PRIVATE_KEY")
            if not env_key:
                raise ValueError(
                    "ENTITY_PRIVATE_KEY environment variable not set "
                    "and no private_key_hex provided"
                )
            private_key_bytes = bytes.fromhex(env_key)
        
        # Ed25519鍵ペア
        self._ed25519_private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        self._ed25519_public_key = self._ed25519_private_key.public_key()
        
        # X25519鍵ペア（エフェメラル、セッションごとに生成）
        self._x25519_private_key: Optional[X25519PrivateKey] = None
        self._x25519_public_key: Optional[X25519PublicKey] = None
        
        # 共有秘密鍵キャッシュ（peer_id -> shared_key）
        self._shared_keys: Dict[str, bytes] = {}
        
        # ピアのEd25519公開鍵キャッシュ（peer_id -> public_key_b64）
        self._peer_public_keys: Dict[str, str] = {}
        
        # X25519公開鍵キャッシュ（peer_id -> x25519_public_key_b64）
        self._peer_x25519_keys: Dict[str, str] = {}
        
        logger.info(f"CryptoManager initialized for entity: {entity_id}")

    # ==================== Key Management ====================

    def get_ed25519_public_key_bytes(self) -> bytes:
        """Ed25519公開鍵をバイト列で取得"""
        return self._ed25519_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

    def get_ed25519_public_key_b64(self) -> str:
        """Ed25519公開鍵をBase64で取得"""
        return base64.b64encode(self.get_ed25519_public_key_bytes()).decode("ascii")

    def generate_x25519_keypair(self) -> Tuple[X25519PrivateKey, X25519PublicKey]:
        """新しいX25519鍵ペアを生成（エフェメラル）"""
        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()
        self._x25519_private_key = private_key
        self._x25519_public_key = public_key
        return private_key, public_key

    def get_x25519_public_key_b64(self) -> Optional[str]:
        """X25519公開鍵をBase64で取得"""
        if self._x25519_public_key is None:
            return None
        public_bytes = self._x25519_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return base64.b64encode(public_bytes).decode("ascii")

    def add_peer_public_key(self, peer_id: str, public_key_hex: str) -> None:
        """ピアのEd25519公開鍵を登録"""
        public_key_bytes = bytes.fromhex(public_key_hex)
        public_key_b64 = base64.b64encode(public_key_bytes).decode("ascii")
        self._peer_public_keys[peer_id] = public_key_b64
        
        # Ed25519 -> X25519 変換
        try:
            x25519_bytes = self._ed25519_to_x25519_public(public_key_bytes)
            x25519_b64 = base64.b64encode(x25519_bytes).decode("ascii")
            self._peer_x25519_keys[peer_id] = x25519_b64
        except Exception as e:
            logger.warning(f"Could not convert Ed25519 to X25519 for {peer_id}: {e}")
        
        logger.debug(f"Added public key for peer: {peer_id}")
    
    def _ed25519_to_x25519_public(self, ed25519_public_bytes: bytes) -> bytes:
        """Ed25519公開鍵をX25519公開鍵に変換（libsodium互換）"""
        try:
            from nacl.bindings import crypto_sign_ed25519_pk_to_curve25519
            return crypto_sign_ed25519_pk_to_curve25519(ed25519_public_bytes)
        except ImportError:
            raise RuntimeError(
                "PyNaCl required for Ed25519 to X25519 conversion. "
                "Install with: pip install pynacl"
            )

    # ==================== Ed25519 Signatures ====================

    def sign_message(self, message_data: Dict[str, Any]) -> str:
        """メッセージにEd25519署名を付与"""
        message_bytes = json.dumps(message_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = self._ed25519_private_key.sign(message_bytes)
        return base64.b64encode(signature).decode("ascii")

    def verify_signature(
        self, 
        message_data: Dict[str, Any], 
        signature_b64: str, 
        public_key_b64: str
    ) -> bool:
        """署名を検証"""
        try:
            public_key_bytes = base64.b64decode(public_key_b64)
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            signature = base64.b64decode(signature_b64)
            message_bytes = json.dumps(message_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
            
            public_key.verify(signature, message_bytes)
            return True
        except (InvalidSignature, Exception) as e:
            logger.warning(f"Signature verification failed: {e}")
            return False

    # ==================== X25519 + AES-256-GCM Encryption ====================

    def derive_shared_key(self, peer_public_key_b64: str, peer_id: str) -> bytes:
        """X25519鍵交換から共有鍵を導出"""
        if peer_id in self._shared_keys:
            return self._shared_keys[peer_id]
        
        if self._x25519_private_key is None:
            self.generate_x25519_keypair()
        
        peer_public_bytes = base64.b64decode(peer_public_key_b64)
        peer_public_key = X25519PublicKey.from_public_bytes(peer_public_bytes)
        
        shared_secret = self._x25519_private_key.exchange(peer_public_key)
        
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        
        shared_key = HKDF(
            algorithm=hashes.SHA256(),
            length=AES_KEY_SIZE_BYTES,
            salt=None,
            info=b"peer-communication-key",
        ).derive(shared_secret)
        
        self._shared_keys[peer_id] = shared_key
        return shared_key

    def encrypt_payload(
        self, 
        payload: Dict[str, Any], 
        peer_public_key_b64: str, 
        peer_id: str
    ) -> Tuple[str, str]:
        """ペイロードをAES-256-GCMで暗号化"""
        shared_key = self.derive_shared_key(peer_public_key_b64, peer_id)
        
        nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
        
        aesgcm = AESGCM(shared_key)
        plaintext = json.dumps(payload, sort_keys=True).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        return (
            base64.b64encode(ciphertext).decode("ascii"),
            base64.b64encode(nonce).decode("ascii")
        )

    def decrypt_payload(
        self, 
        ciphertext_b64: str, 
        nonce_b64: str, 
        peer_id: str
    ) -> Optional[Dict[str, Any]]:
        """暗号文を復号"""
        try:
            if peer_id not in self._shared_keys:
                logger.error(f"No shared key for peer: {peer_id}")
                return None
            
            shared_key = self._shared_keys[peer_id]
            nonce = base64.b64decode(nonce_b64)
            ciphertext = base64.b64decode(ciphertext_b64)
            
            aesgcm = AESGCM(shared_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            
            return json.loads(plaintext.decode("utf-8"))
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None

    # ==================== JWT Authentication ====================

    def create_jwt_token(self, audience: Optional[str] = None) -> str:
        """JWTトークンを作成（5分間有効）"""
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(minutes=JWT_EXPIRY_MINUTES)
        
        payload = {
            "sub": self.entity_id,
            "iat": now,
            "exp": expiry,
            "iss": "peer-service",
        }
        
        if audience:
            payload["aud"] = audience
        
        private_key_pem = self._ed25519_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        token = jwt.encode(payload, private_key_pem, algorithm="EdDSA")
        return token

    def verify_jwt_token(
        self, 
        token: str, 
        sender_public_key_b64: str,
        audience: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """JWTトークンを検証"""
        try:
            public_key_bytes = base64.b64decode(sender_public_key_b64)
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            public_key_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            decoded = jwt.decode(
                token,
                public_key_pem,
                algorithms=["EdDSA"],
                audience=audience,
                issuer="peer-service"
            )
            return decoded
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None
        except Exception as e:
            logger.error(f"JWT verification failed: {e}")
            return None

    # ==================== Replay Attack Prevention ====================

    def generate_nonce(self) -> str:
        """128-bitランダムnonceを生成"""
        return base64.b64encode(secrets.token_bytes(NONCE_SIZE_BYTES)).decode("ascii")

    def check_and_record_nonce(self, nonce: str, timestamp: float) -> bool:
        """nonceをチェックし、リプレイ攻撃を防止"""
        now = time.time()
        
        if abs(now - timestamp) > TIMESTAMP_TOLERANCE_SECONDS:
            logger.warning(f"Timestamp out of tolerance: {timestamp} (now: {now})")
            return False
        
        if nonce in self._seen_nonces:
            logger.warning(f"Replay attack detected: duplicate nonce {nonce}")
            return False
        
        self._seen_nonces.add(nonce)
        self._nonce_timestamps[nonce] = now
        
        self._cleanup_old_nonces()
        
        return True

    def _cleanup_old_nonces(self) -> None:
        """古いnonceエントリをクリーンアップ"""
        now = time.time()
        expired = [
            nonce for nonce, ts in self._nonce_timestamps.items()
            if now - ts > REPLAY_WINDOW_SECONDS
        ]
        for nonce in expired:
            self._seen_nonces.discard(nonce)
            del self._nonce_timestamps[nonce]


# ============================================================================
# WalletManager
# ============================================================================

class WalletManager:
    """ウォレット永続化管理クラス"""
    
    WALLET_VERSION = 1
    PBKDF2_ITERATIONS = 600000
    SALT_SIZE_BYTES = 32
    NONCE_SIZE_BYTES = 12
    
    def __init__(self, wallet_path: Optional[str] = None):
        if wallet_path is None:
            wallet_path = os.path.expanduser("~/.peer_service/wallet.json")
        
        self.wallet_path = wallet_path
        self._wallet_dir = os.path.dirname(wallet_path)
        self._private_key_hex: Optional[str] = None
        self._public_key_hex: Optional[str] = None
    
    def wallet_exists(self) -> bool:
        return os.path.exists(self.wallet_path)
    
    def _ensure_wallet_directory(self) -> None:
        if self._wallet_dir and not os.path.exists(self._wallet_dir):
            os.makedirs(self._wallet_dir, mode=0o700)
    
    def _derive_key_from_password(self, password: str, salt: bytes) -> bytes:
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=AES_KEY_SIZE_BYTES,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
        )
        return kdf.derive(password.encode("utf-8"))
    
    def create_wallet(self, password: str) -> Tuple[str, str]:
        if not password:
            raise ValueError("Password cannot be empty")
        
        if self.wallet_exists():
            raise FileExistsError(f"Wallet already exists at {self.wallet_path}")
        
        private_key_hex, public_key_hex = generate_entity_keypair()
        
        salt = secrets.token_bytes(self.SALT_SIZE_BYTES)
        nonce = secrets.token_bytes(self.NONCE_SIZE_BYTES)
        
        encryption_key = self._derive_key_from_password(password, salt)
        
        private_key_bytes = bytes.fromhex(private_key_hex)
        aesgcm = AESGCM(encryption_key)
        ciphertext = aesgcm.encrypt(nonce, private_key_bytes, None)
        
        wallet_data = {
            "version": self.WALLET_VERSION,
            "public_key": public_key_hex,
            "encrypted_private_key": base64.b64encode(ciphertext).decode("ascii"),
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
        }
        
        self._ensure_wallet_directory()
        with open(self.wallet_path, "w", encoding="utf-8") as f:
            json.dump(wallet_data, f, indent=2)
        
        os.chmod(self.wallet_path, 0o600)
        
        self._private_key_hex = private_key_hex
        self._public_key_hex = public_key_hex
        
        logger.info(f"Wallet created successfully at {self.wallet_path}")
        return private_key_hex, public_key_hex
    
    def load_wallet(self, password: str) -> Tuple[str, str]:
        if not self.wallet_exists():
            raise FileNotFoundError(f"Wallet not found at {self.wallet_path}")
        
        with open(self.wallet_path, "r", encoding="utf-8") as f:
            wallet_data = json.load(f)
        
        version = wallet_data.get("version")
        if version != self.WALLET_VERSION:
            raise ValueError(f"Unsupported wallet version: {version}")
        
        try:
            ciphertext = base64.b64decode(wallet_data["encrypted_private_key"])
            salt = base64.b64decode(wallet_data["salt"])
            nonce = base64.b64decode(wallet_data["nonce"])
            public_key_hex = wallet_data["public_key"]
        except (KeyError, base64.binascii.Error) as e:
            raise ValueError(f"Invalid wallet format: {e}")
        
        encryption_key = self._derive_key_from_password(password, salt)
        
        try:
            aesgcm = AESGCM(encryption_key)
            private_key_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            raise ValueError("Invalid password or corrupted wallet data") from e
        
        private_key_hex = private_key_bytes.hex()
        
        # 整合性チェック
        try:
            private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
            derived_public_key = private_key.public_key()
            derived_public_bytes = derived_public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            if derived_public_bytes.hex() != public_key_hex:
                raise ValueError("Public key mismatch: wallet may be corrupted")
        except Exception as e:
            raise ValueError(f"Key validation failed: {e}")
        
        self._private_key_hex = private_key_hex
        self._public_key_hex = public_key_hex
        
        logger.info(f"Wallet loaded successfully from {self.wallet_path}")
        return private_key_hex, public_key_hex
    
    def get_keys(self) -> Tuple[Optional[str], Optional[str]]:
        return self._private_key_hex, self._public_key_hex
    
    def delete_wallet(self) -> None:
        if not self.wallet_exists():
            raise FileNotFoundError(f"Wallet not found at {self.wallet_path}")
        
        os.remove(self.wallet_path)
        self._private_key_hex = None
        self._public_key_hex = None
        logger.info(f"Wallet deleted: {self.wallet_path}")


# ============================================================================
# Utility Functions
# ============================================================================

def generate_entity_keypair() -> Tuple[str, str]:
    """新しいEd25519鍵ペアを生成"""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    return private_bytes.hex(), public_bytes.hex()


def get_public_key_from_private(private_key_hex: str) -> str:
    """秘密鍵から公開鍵を導出"""
    private_key_bytes = bytes.fromhex(private_key_hex)
    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    return public_bytes.hex()


# Backward compatibility alias
generate_keypair = generate_entity_keypair


# ============================================================================
# MessageValidator
# ============================================================================

class MessageValidator:
    """Message validation for protocol v1.0"""
    
    PROTOCOL_VERSION = "1.0"
    
    @classmethod
    def validate_version(cls, version: str) -> bool:
        return version == cls.PROTOCOL_VERSION
    
    @classmethod
    def validate_session_id(cls, session_id: Optional[str]) -> bool:
        if session_id is None:
            return True
        if not session_id:
            return False
        try:
            parsed = uuid.UUID(session_id)
            return parsed.version == 4
        except (ValueError, AttributeError):
            return False
    
    @staticmethod
    def validate_sequence(current: int, expected: int) -> bool:
        return current == expected


# ============================================================================
# KeyPair
# ============================================================================

@dataclass
class KeyPair:
    """Ed25519 key pair"""
    private_key: bytes
    public_key: bytes
    
    @classmethod
    def generate(cls) -> "KeyPair":
        private_hex, public_hex = generate_entity_keypair()
        return cls(
            private_key=bytes.fromhex(private_hex),
            public_key=bytes.fromhex(public_hex)
        )
    
    @classmethod
    def from_private_key(cls, private_key: bytes) -> "KeyPair":
        seed = private_key[:32] if len(private_key) >= 32 else private_key
        private_hex = seed.hex()
        public_hex = get_public_key_from_private(private_hex)
        return cls(
            private_key=bytes.fromhex(private_hex),
            public_key=bytes.fromhex(public_hex)
        )
    
    @classmethod
    def from_private_key_hex(cls, private_key_hex: str) -> "KeyPair":
        public_hex = get_public_key_from_private(private_key_hex)
        return cls(
            private_key=bytes.fromhex(private_key_hex),
            public_key=bytes.fromhex(public_hex)
        )
    
    def get_public_key_hex(self) -> str:
        return self.public_key.hex()
    
    def get_private_key_hex(self) -> str:
        return self.private_key[:32].hex() if len(self.private_key) >= 32 else self.private_key.hex()


# ============================================================================
# MessageSigner and SignatureVerifier
# ============================================================================

class MessageSigner:
    """Ed25519 message signer"""
    
    def __init__(self, key_pair: KeyPair):
        self.key_pair = key_pair
        private_hex = key_pair.get_private_key_hex()
        self._crypto = CryptoManager("signer", private_key_hex=private_hex)
    
    def sign_message(self, message: Dict[str, Any]) -> str:
        return self._crypto.sign_message(message)
    
    def sign_bytes(self, data: bytes) -> str:
        message_data = {"data": base64.b64encode(data).decode("ascii")}
        return self._crypto.sign_message(message_data)


class SignatureVerifier:
    """Ed25519 signature verifier"""
    
    def __init__(self, public_keys: Dict[str, bytes] = None):
        self.public_keys = public_keys or {}
        self._crypto = CryptoManager("verifier", private_key_hex="0" * 64)
    
    def add_public_key(self, entity_id: str, public_key: bytes):
        self.public_keys[entity_id] = public_key
    
    def verify(self, entity_id: str, message: Dict[str, Any], signature: str) -> bool:
        if entity_id not in self.public_keys:
            return False
        public_key_b64 = base64.b64encode(self.public_keys[entity_id]).decode("ascii")
        return self._crypto.verify_signature(message, signature, public_key_b64)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "CryptoManager",
    "SecureMessage",
    "WalletManager",
    "generate_entity_keypair",
    "generate_keypair",
    "get_public_key_from_private",
    "KeyPair",
    "MessageSigner",
    "SignatureVerifier",
    "MessageValidator",
    "TIMESTAMP_TOLERANCE_SECONDS",
    "JWT_EXPIRY_MINUTES",
    "NONCE_SIZE_BYTES",
    "AES_KEY_SIZE_BYTES",
    "REPLAY_WINDOW_SECONDS",
]
