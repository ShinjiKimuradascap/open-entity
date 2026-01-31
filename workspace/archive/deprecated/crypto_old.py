#!/usr/bin/env python3
"""
Cryptographic utilities for peer communication
Ed25519 signatures, X25519 key exchange, AES-256-GCM encryption, JWT authentication

This module provides:
- CryptoManager: Main cryptographic operations
- SecureMessage: Secure message structure
- WalletManager: Wallet persistence management
- generate_entity_keypair: Key pair generation

Note: crypto_utils.py is deprecated. Use this module (services.crypto) instead.
"""

import os
import json
import base64
import hashlib
import secrets
import time
import uuid
import warnings
from typing import Optional, Tuple, Dict, Any, Set, List
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta

# Import MessageChunk from chunked_transfer
try:
    from chunked_transfer import MessageChunk
except ImportError:
    MessageChunk = None  # Will be defined locally if needed

# Import from crypto_utils (the actual implementation)
try:
    from crypto_utils import (
        CryptoManager as _CryptoManager,
        SecureMessage as _SecureMessage,
        generate_entity_keypair,
        WalletManager as _WalletManager,
        TIMESTAMP_TOLERANCE_SECONDS,
        JWT_EXPIRY_MINUTES,
        NONCE_SIZE_BYTES,
        AES_KEY_SIZE_BYTES,
        REPLAY_WINDOW_SECONDS,
    )
except ImportError:
    from services.crypto_utils import (
        CryptoManager as _CryptoManager,
        SecureMessage as _SecureMessage,
        generate_entity_keypair,
        WalletManager as _WalletManager,
        TIMESTAMP_TOLERANCE_SECONDS,
        JWT_EXPIRY_MINUTES,
        NONCE_SIZE_BYTES,
        AES_KEY_SIZE_BYTES,
        REPLAY_WINDOW_SECONDS,
    )

# For backward compatibility - re-export with alias
generate_keypair = generate_entity_keypair

# Re-export everything for backward compatibility
__all__ = [
    "CryptoManager",
    "SecureMessage",
    "WalletManager",
    "generate_entity_keypair",
    "generate_keypair",
    "TIMESTAMP_TOLERANCE_SECONDS",
    "JWT_EXPIRY_MINUTES",
    "NONCE_SIZE_BYTES",
    "AES_KEY_SIZE_BYTES",
    "REPLAY_WINDOW_SECONDS",
    "ProtocolError",
    "DECRYPTION_FAILED",
    "SESSION_EXPIRED",
    "SEQUENCE_ERROR",
    "REPLAY_DETECTED",
]

# Error codes for protocol v1.0
DECRYPTION_FAILED = "DECRYPTION_FAILED"
SESSION_EXPIRED = "SESSION_EXPIRED"
SEQUENCE_ERROR = "SEQUENCE_ERROR"
REPLAY_DETECTED = "REPLAY_DETECTED"


class ProtocolError(Exception):
    """Protocol-level error with error code"""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class MessageValidator:
    """Message validation for protocol v1.0"""
    
    PROTOCOL_VERSION = "1.0"
    
    @classmethod
    def validate_version(cls, version: str) -> bool:
        """Validate protocol version"""
        return version == cls.PROTOCOL_VERSION
    
    @classmethod
    def validate_session_id(cls, session_id: Optional[str]) -> bool:
        """Validate session ID (UUID v4 format)"""
        if session_id is None:
            return True  # Optional field
        if not session_id:
            return False
        try:
            parsed = uuid.UUID(session_id)
            return parsed.version == 4
        except (ValueError, AttributeError):
            return False
    
    @staticmethod
    def validate_sequence(current: int, expected: int) -> bool:
        """Validate sequence number ordering"""
        return current == expected


@dataclass
class KeyPair:
    """Ed25519 key pair - wrapper around crypto_utils"""
    private_key: bytes
    public_key: bytes
    
    @classmethod
    def generate(cls) -> "KeyPair":
        """Generate new key pair using crypto_utils"""
        private_hex, public_hex = generate_entity_keypair()
        return cls(
            private_key=bytes.fromhex(private_hex),
            public_key=bytes.fromhex(public_hex)
        )
    
    @classmethod
    def from_private_key(cls, private_key: bytes) -> "KeyPair":
        """Create key pair from private key (32-byte seed or 64-byte expanded)"""
        # Use first 32 bytes as seed
        seed = private_key[:32] if len(private_key) >= 32 else private_key
        private_hex = seed.hex()
        public_hex = get_public_key_from_private(private_hex)
        return cls(
            private_key=bytes.fromhex(private_hex),
            public_key=bytes.fromhex(public_hex)
        )
    
    @classmethod
    def from_private_key_hex(cls, private_key_hex: str) -> "KeyPair":
        """Create key pair from hex-encoded private key"""
        public_hex = get_public_key_from_private(private_key_hex)
        return cls(
            private_key=bytes.fromhex(private_key_hex),
            public_key=bytes.fromhex(public_hex)
        )
    
    def get_public_key_hex(self) -> str:
        """Get hex-encoded public key"""
        return self.public_key.hex()
    
    def get_private_key_hex(self) -> str:
        """Get hex-encoded private key"""
        return self.private_key[:32].hex() if len(self.private_key) >= 32 else self.private_key.hex()
    
    def save_to_file(
        self, 
        filepath: str, 
        password: Optional[str] = None,
        entity_id: Optional[str] = None
    ) -> bool:
        """
        Save key pair to encrypted file
        """
        try:
            # Build key data
            key_data = {
                "version": 1,
                "algorithm": "Ed25519",
                "public_key": self.get_public_key_hex(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            if entity_id:
                key_data["entity_id"] = entity_id
            
            # Encrypt private key if password provided
            if password:
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                from cryptography.hazmat.primitives import hashes
                
                salt = secrets.token_bytes(32)
                nonce = secrets.token_bytes(12)
                
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=600000,
                )
                encryption_key = kdf.derive(password.encode("utf-8"))
                
                aesgcm = AESGCM(encryption_key)
                # Use first 32 bytes of private key
                private_bytes = self.private_key[:32] if len(self.private_key) >= 32 else self.private_key
                ciphertext = aesgcm.encrypt(nonce, private_bytes, None)
                
                key_data["encrypted"] = True
                key_data["encrypted_private_key"] = base64.b64encode(ciphertext).decode("ascii")
                key_data["salt"] = base64.b64encode(salt).decode("ascii")
                key_data["nonce"] = base64.b64encode(nonce).decode("ascii")
                key_data["kdf"] = "PBKDF2-SHA256"
                key_data["kdf_iterations"] = 600000
            else:
                key_data["encrypted"] = False
                key_data["private_key"] = self.get_private_key_hex()
            
            # Ensure directory exists
            dir_path = os.path.dirname(filepath)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, mode=0o700)
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(key_data, f, indent=2)
            
            os.chmod(filepath, 0o600)
            return True
            
        except Exception as e:
            print(f"Failed to save key pair: {e}")
            return False
    
    @classmethod
    def load_from_file(
        cls, 
        filepath: str, 
        password: Optional[str] = None
    ) -> Optional["KeyPair"]:
        """Load key pair from file"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                key_data = json.load(f)
            
            version = key_data.get("version", 1)
            if version != 1:
                raise ValueError(f"Unsupported key file version: {version}")
            
            if key_data.get("encrypted", False):
                if not password:
                    raise ValueError("Password required for encrypted key file")
                
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                from cryptography.hazmat.primitives import hashes
                
                ciphertext = base64.b64decode(key_data["encrypted_private_key"])
                salt = base64.b64decode(key_data["salt"])
                nonce = base64.b64decode(key_data["nonce"])
                
                iterations = key_data.get("kdf_iterations", 600000)
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=iterations,
                )
                encryption_key = kdf.derive(password.encode("utf-8"))
                
                aesgcm = AESGCM(encryption_key)
                private_key = aesgcm.decrypt(nonce, ciphertext, None)
            else:
                private_key_hex = key_data["private_key"]
                private_key = bytes.fromhex(private_key_hex)
            
            return cls.from_private_key(private_key)
            
        except Exception as e:
            print(f"Failed to load key pair: {e}")
            return None


class MessageSigner:
    """Ed25519 message signer - wrapper around crypto_utils"""
    
    def __init__(self, key_pair: KeyPair):
        self.key_pair = key_pair
        private_hex = key_pair.get_private_key_hex()
        # Create a crypto manager for signing
        self._crypto = _CryptoManager("signer", private_key_hex=private_hex)
    
    def sign_message(self, message: Dict[str, Any]) -> str:
        """Sign a message dictionary"""
        return self._crypto.sign_message(message)
    
    def sign_bytes(self, data: bytes) -> str:
        """Sign raw bytes"""
        # Convert bytes to dict format for compatibility
        message_data = {"data": base64.b64encode(data).decode("ascii")}
        return self._crypto.sign_message(message_data)
    
    @staticmethod
    def _canonical_json(data: Dict[str, Any]) -> bytes:
        """Create canonical JSON representation for signing"""
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


class SignatureVerifier:
    """Ed25519 signature verifier - wrapper around crypto_utils"""
    
    def __init__(self, public_keys: Dict[str, bytes] = None):
        """
        Initialize verifier with known public keys
        """
        self.public_keys = public_keys or {}
        # Create a crypto manager for verification (no private key needed)
        dummy_priv, _ = generate_entity_keypair()
        self._crypto = _CryptoManager("verifier", private_key_hex=dummy_priv)
    
    def add_public_key(self, entity_id: str, public_key: bytes) -> None:
        """Add a public key for an entity"""
        self.public_keys[entity_id] = public_key
    
    def add_public_key_hex(self, entity_id: str, public_key_hex: str) -> None:
        """Add a hex-encoded public key for an entity"""
        self.add_public_key(entity_id, bytes.fromhex(public_key_hex))
    
    def remove_public_key(self, entity_id: str) -> bool:
        """Remove a public key for an entity"""
        if entity_id in self.public_keys:
            del self.public_keys[entity_id]
            return True
        return False
    
    def verify_message(self, message: Dict[str, Any], signature: str, sender_id: str) -> bool:
        """Verify a message signature"""
        if sender_id not in self.public_keys:
            raise ValueError(f"Unknown sender: {sender_id}")
        
        public_key_b64 = base64.b64encode(self.public_keys[sender_id]).decode("ascii")
        return self._crypto.verify_signature(message, signature, public_key_b64)
    
    def verify_bytes(self, data: bytes, signature: str, sender_id: str) -> bool:
        """Verify raw bytes signature"""
        if sender_id not in self.public_keys:
            raise ValueError(f"Unknown sender: {sender_id}")
        
        message_data = {"data": base64.b64encode(data).decode("ascii")}
        public_key_b64 = base64.b64encode(self.public_keys[sender_id]).decode("ascii")
        return self._crypto.verify_signature(message_data, signature, public_key_b64)


class SecureMessage:
    """Secure message with signature (protocol v1.0) - wrapper"""
    
    def __init__(
        self,
        version: str,
        msg_type: str,
        sender_id: str,
        payload: Dict[str, Any],
        timestamp: Optional[str] = None,
        nonce: Optional[str] = None,
        signature: Optional[str] = None,
        session_id: Optional[str] = None,
        sequence_num: Optional[int] = None,
        recipient_id: Optional[str] = None
    ):
        self.version = version
        self.msg_type = msg_type
        self.sender_id = sender_id
        self.payload = payload
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.nonce = nonce or self._generate_nonce()
        self.signature = signature
        self.session_id = session_id
        self.sequence_num = sequence_num
        self.recipient_id = recipient_id
    
    @staticmethod
    def _generate_nonce() -> str:
        """Generate a unique nonce"""
        return base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    
    def sign(self, signer: MessageSigner) -> None:
        """Sign the message using a MessageSigner"""
        signable_data = self.get_signable_data()
        self.signature = signer.sign_message(signable_data)
    
    def get_signable_data(self) -> Dict[str, Any]:
        """Get the data that should be signed"""
        return {
            "version": self.version,
            "msg_type": self.msg_type,
            "sender_id": self.sender_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "version": self.version,
            "msg_type": self.msg_type,
            "sender_id": self.sender_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
        }
        if self.signature:
            result["signature"] = self.signature
        if self.session_id:
            result["session_id"] = self.session_id
        if self.sequence_num is not None:
            result["sequence_num"] = self.sequence_num
        if self.recipient_id:
            result["recipient_id"] = self.recipient_id
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecureMessage":
        """Create from dictionary"""
        return cls(
            version=data.get("version", "1.0"),
            msg_type=data["msg_type"],
            sender_id=data["sender_id"],
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp"),
            nonce=data.get("nonce"),
            signature=data.get("signature"),
            session_id=data.get("session_id"),
            sequence_num=data.get("sequence_num"),
            recipient_id=data.get("recipient_id")
        )


@dataclass
class EncryptedMessage:
    """Encrypted message container"""
    ciphertext: str  # base64 encoded
    nonce: str  # base64 encoded
    sender_public_key: str  # hex encoded
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ciphertext": self.ciphertext,
            "nonce": self.nonce,
            "sender_public_key": self.sender_public_key,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EncryptedMessage":
        return cls(
            ciphertext=data["ciphertext"],
            nonce=data["nonce"],
            sender_public_key=data["sender_public_key"],
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat())
        )


class HandshakeChallenge:
    """Handshake challenge for E2E encryption setup"""
    
    def __init__(self, challenge_data: Optional[Dict[str, Any]] = None):
        self.challenge_data = challenge_data or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def generate(self, entity_id: str) -> Dict[str, Any]:
        """Generate a new handshake challenge"""
        challenge = secrets.token_hex(32)
        self.challenge_data = {
            "entity_id": entity_id,
            "challenge": challenge,
            "timestamp": self.timestamp,
        }
        return self.challenge_data
    
    def verify_response(self, response: Dict[str, Any]) -> bool:
        """Verify a handshake response"""
        expected_challenge = self.challenge_data.get("challenge")
        received_challenge = response.get("challenge_response")
        return expected_challenge == received_challenge


class ReplayProtector:
    """Replay attack protection"""
    
    def __init__(self, max_age_seconds: int = 300):
        self.max_age_seconds = max_age_seconds
        self._seen_nonces: Set[str] = set()
        self._nonce_timestamps: Dict[str, float] = {}
    
    def is_valid(self, nonce: str, timestamp: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a nonce is valid (not replayed and within time window)
        
        Returns:
            (is_valid, error_message)
        """
        try:
            # Parse timestamp
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            ts_seconds = ts.timestamp()
        except (ValueError, AttributeError):
            return False, "Invalid timestamp format"
        
        # Check if nonce already seen
        if nonce in self._seen_nonces:
            return False, REPLAY_DETECTED
        
        # Check timestamp is not too old
        now = datetime.now(timezone.utc).timestamp()
        if now - ts_seconds > self.max_age_seconds:
            return False, "Timestamp too old"
        
        # Check timestamp is not in the future (allow 60s tolerance)
        if ts_seconds > now + 60:
            return False, "Timestamp in future"
        
        # Record nonce
        self._seen_nonces.add(nonce)
        self._nonce_timestamps[nonce] = now
        
        # Cleanup old nonces
        self._cleanup_old_nonces()
        
        return True, None
    
    def _cleanup_old_nonces(self) -> None:
        """Remove nonces older than max_age_seconds"""
        now = datetime.now(timezone.utc).timestamp()
        expired = [
            nonce for nonce, ts in self._nonce_timestamps.items()
            if now - ts > self.max_age_seconds
        ]
        for nonce in expired:
            self._seen_nonces.discard(nonce)
            del self._nonce_timestamps[nonce]


def encrypt_payload(plaintext: Dict[str, Any], encryption_key: bytes) -> Dict[str, Any]:
    """Encrypt a payload using AES-256-GCM"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(encryption_key)
    plaintext_bytes = json.dumps(plaintext, sort_keys=True).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)
    
    return {
        "encrypted": True,
        "data": base64.b64encode(ciphertext).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }


def decrypt_payload(payload: Dict[str, Any], encryption_key: bytes) -> Dict[str, Any]:
    """Decrypt a payload using AES-256-GCM"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    
    if not payload.get("encrypted"):
        raise ValueError("Payload is not encrypted")
    
    ciphertext = base64.b64decode(payload["data"])
    nonce = base64.b64decode(payload["nonce"])
    
    aesgcm = AESGCM(encryption_key)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    
    return json.loads(plaintext_bytes.decode("utf-8"))


def create_plain_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create an unencrypted payload"""
    return {
        "encrypted": False,
        "data": base64.b64encode(json.dumps(data, sort_keys=True).encode("utf-8")).decode("ascii")
    }


def load_key_from_env(env_var: str = "ENTITY_PRIVATE_KEY") -> Optional[KeyPair]:
    """Load key pair from environment variable"""
    private_key_hex = os.environ.get(env_var)
    if not private_key_hex:
        return None
    return KeyPair.from_private_key_hex(private_key_hex)


class KeyFingerprint:
    """Key fingerprint utility"""
    
    @staticmethod
    def compute(public_key: bytes) -> str:
        """Compute a fingerprint for a public key"""
        return hashlib.sha256(public_key).hexdigest()[:16]
    
    @staticmethod
    def compute_hex(public_key_hex: str) -> str:
        """Compute a fingerprint from hex-encoded public key"""
        return KeyFingerprint.compute(bytes.fromhex(public_key_hex))


class SessionManager:
    """Session manager for protocol v1.0"""
    
    SESSION_TIMEOUT_SECONDS = 300  # 5 minutes
    
    def __init__(self):
        self._sessions: Dict[str, SecureSession] = {}
    
    def create_session(self, sender_id: str, recipient_id: str) -> SecureSession:
        """Create a new session"""
        session_id = str(uuid.uuid4())
        session = SecureSession(
            session_id=session_id,
            sender_id=sender_id,
            recipient_id=recipient_id
        )
        self._sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[SecureSession]:
        """Get a session by ID"""
        return self._sessions.get(session_id)
    
    def update_activity(self, session_id: str) -> bool:
        """Update last activity timestamp"""
        session = self._sessions.get(session_id)
        if session:
            session.last_activity = datetime.now(timezone.utc).isoformat()
            return True
        return False
    
    def close_session(self, session_id: str) -> bool:
        """Close a session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
    
    def cleanup_expired(self) -> int:
        """Remove expired sessions, returns count removed"""
        now = datetime.now(timezone.utc)
        expired = []
        
        for session_id, session in self._sessions.items():
            last_activity = datetime.fromisoformat(session.last_activity.replace("Z", "+00:00"))
            if (now - last_activity).total_seconds() > self.SESSION_TIMEOUT_SECONDS:
                expired.append(session_id)
        
        for session_id in expired:
            del self._sessions[session_id]
        
        return len(expired)


class E2EEncryption:
    """End-to-end encryption using X25519 + AES-256-GCM - wrapper around crypto_utils"""
    
    def __init__(self, key_pair: KeyPair):
        """
        Initialize E2E encryption with a key pair
        """
        self.key_pair = key_pair
        private_hex = key_pair.get_private_key_hex()
        self._crypto = _CryptoManager("e2e", private_key_hex=private_hex)
        self._shared_keys: Dict[str, bytes] = {}
    
    def generate_ephemeral_keypair(self) -> Tuple[str, str]:
        """Generate ephemeral X25519 key pair, return (private_b64, public_b64)"""
        self._crypto.generate_x25519_keypair()
        pub_b64 = self._crypto.get_x25519_public_key_b64()
        priv_b64 = base64.b64encode(self.key_pair.private_key[:32]).decode("ascii")
        return priv_b64, pub_b64
    
    def derive_shared_key(self, peer_public_key_b64: str, peer_id: str) -> bytes:
        """Derive shared key using X25519"""
        return self._crypto.derive_shared_key(peer_public_key_b64, peer_id)
    
    def encrypt_message(
        self, 
        plaintext: Dict[str, Any], 
        peer_public_key_b64: str, 
        peer_id: str
    ) -> EncryptedMessage:
        """Encrypt a message for a peer"""
        if peer_id not in self._shared_keys:
            self._shared_keys[peer_id] = self.derive_shared_key(peer_public_key_b64, peer_id)
        
        shared_key = self._shared_keys[peer_id]
        
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(shared_key)
        plaintext_bytes = json.dumps(plaintext, sort_keys=True).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)
        
        return EncryptedMessage(
            ciphertext=base64.b64encode(ciphertext).decode("ascii"),
            nonce=base64.b64encode(nonce).decode("ascii"),
            sender_public_key=self.key_pair.get_public_key_hex(),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    
    def decrypt_message(
        self, 
        encrypted_msg: EncryptedMessage, 
        peer_id: str
    ) -> Optional[Dict[str, Any]]:
        """Decrypt a message from a peer"""
        if peer_id not in self._shared_keys:
            raise ValueError(f"No shared key for peer: {peer_id}")
        
        shared_key = self._shared_keys[peer_id]
        
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            nonce = base64.b64decode(encrypted_msg.nonce)
            ciphertext = base64.b64decode(encrypted_msg.ciphertext)
            
            aesgcm = AESGCM(shared_key)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
            
            return json.loads(plaintext_bytes.decode("utf-8"))
        except Exception as e:
            print(f"Decryption failed: {e}")
            return None
    
    def get_public_key(self) -> str:
        """Get the public key (hex encoded)"""
        return self.key_pair.get_public_key_hex()


class SecureMessageV1:
    """SecureMessage for protocol v1.0 (alias for compatibility)"""
    
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Use SecureMessage instead")


def generate_keypair() -> KeyPair:
    """Generate a new Ed25519 key pair"""
    return KeyPair.generate()


def get_public_key_from_private(private_key_hex: str) -> str:
    """Derive public key from private key (hex encoded)"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    
    private_bytes = bytes.fromhex(private_key_hex)
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    return public_bytes.hex()


class CryptoManager:
    """CryptoManager - wrapper around crypto_utils.CryptoManager"""
    
    def __init__(self, entity_id: str, private_key_hex: Optional[str] = None):
        """
        Initialize CryptoManager
        
        Args:
            entity_id: Entity ID
            private_key_hex: Hex-encoded private key (optional, uses ENTITY_PRIVATE_KEY env var if not provided)
        """
        self.entity_id = entity_id
        
        if private_key_hex is None:
            private_key_hex = os.environ.get("ENTITY_PRIVATE_KEY")
        
        if not private_key_hex:
            raise ValueError("Private key not provided and ENTITY_PRIVATE_KEY not set")
        
        self._crypto = _CryptoManager(entity_id, private_key_hex=private_key_hex)
        self._public_key_hex = get_public_key_from_private(private_key_hex)
    
    def sign_message(self, message_data: Dict[str, Any]) -> str:
        """Sign a message"""
        return self._crypto.sign_message(message_data)
    
    def verify_signature(
        self, 
        message_data: Dict[str, Any], 
        signature_b64: str, 
        public_key_hex: str
    ) -> bool:
        """Verify a signature"""
        public_key_b64 = base64.b64encode(bytes.fromhex(public_key_hex)).decode("ascii")
        return self._crypto.verify_signature(message_data, signature_b64, public_key_b64)
    
    def get_public_key(self) -> str:
        """Get public key (hex encoded)"""
        return self._public_key_hex


class WalletManager(_WalletManager):
    """WalletManager - inherits from crypto_utils.WalletManager"""
    pass


# ============================================================================
# E2E Encryption Layer (from e2e_crypto.py)
# ============================================================================

from enum import Enum

# Protocol error codes for E2E
DECRYPTION_FAILED = "DECRYPTION_FAILED"
SESSION_EXPIRED = "SESSION_EXPIRED"
SEQUENCE_ERROR = "SEQUENCE_ERROR"
REPLAY_DETECTED = "REPLAY_DETECTED"


class SessionState(Enum):
    """E2E session lifecycle states (v1.1 compliant - 6-step handshake)"""
    # Initial state
    INITIAL = "initial"
    
    # Step 1: Handshake init sent
    HANDSHAKE_INIT_SENT = "handshake_init_sent"
    
    # Step 2: Handshake ack received
    HANDSHAKE_ACK_RECEIVED = "handshake_ack_received"
    
    # Step 3: Challenge response sent
    CHALLENGE_RESPONSE_SENT = "challenge_response_sent"
    
    # Step 4: Session established received
    SESSION_ESTABLISHED_RECEIVED = "session_established_received"
    
    # Step 5: Session confirmed sent
    SESSION_CONFIRMED_SENT = "session_confirmed_sent"
    
    # Step 6: Ready received - encryption active
    READY = "ready"
    
    # Legacy states (backward compatibility)
    HANDSHAKE_SENT = "handshake_sent"  # v1.0: equivalent to HANDSHAKE_INIT_SENT
    HANDSHAKE_RECEIVED = "handshake_received"  # v1.0: responder state
    ESTABLISHED = "established"  # v1.0: session active
    
    # Error state
    ERROR = "error"
    
    # Terminal states
    EXPIRED = "expired"
    CLOSED = "closed"


@dataclass
class SessionKeys:
    """Derived session keys for encryption and authentication"""
    encryption_key: bytes  # 32-byte AES key
    auth_key: bytes       # 32-byte HMAC/authentication key
    
    @classmethod
    def derive_from_shared_secret(cls, shared_secret: bytes) -> "SessionKeys":
        """Derive session keys from X25519 shared secret using HKDF-like construction"""
        # Simple HKDF-like key derivation
        prk = hashlib.sha256(shared_secret).digest()
        
        # Derive encryption key
        enc_key = hashlib.sha256(prk + b"encryption").digest()
        
        # Derive authentication key
        auth_key = hashlib.sha256(prk + b"authentication").digest()
        
        return cls(encryption_key=enc_key, auth_key=auth_key)


@dataclass
class E2ESession:
    """
    End-to-end encrypted session between two entities
    
    Protocol v1.0 compliant session with:
    - UUID v4 session identifier
    - Sequence numbers for ordering
    - Ephemeral X25519 keys for PFS
    - Session timeout and expiration
    """
    session_id: str
    local_entity_id: str
    remote_entity_id: str
    
    # Session state
    state: SessionState = field(default=SessionState.INITIAL)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Cryptographic keys
    local_keypair: Optional[KeyPair] = None
    remote_public_key: Optional[bytes] = None
    session_keys: Optional[SessionKeys] = None
    
    # Ephemeral X25519 keys for this session (PFS)
    ephemeral_private_key: Optional[bytes] = None
    ephemeral_public_key: Optional[bytes] = None
    
    # Sequence numbers
    local_sequence: int = 0
    remote_sequence: int = 0
    
    # Configuration
    timeout_seconds: int = 3600  # 1 hour default
    max_sequence: int = 2**31 - 1
    
    # Challenge for handshake verification
    challenge: Optional[bytes] = None
    
    def __post_init__(self):
        """Initialize ephemeral keys for this session"""
        if self.ephemeral_private_key is None:
            try:
                from nacl.public import PrivateKey
                # Generate ephemeral X25519 keypair
                priv_key = PrivateKey.generate()
                self.ephemeral_private_key = bytes(priv_key)
                self.ephemeral_public_key = bytes(priv_key.public_key)
            except ImportError:
                pass  # nacl not available
    
    @classmethod
    def create(
        cls,
        local_entity_id: str,
        remote_entity_id: str,
        local_keypair: KeyPair,
        timeout_seconds: int = 3600
    ) -> "E2ESession":
        """Create a new E2E session"""
        session_id = str(uuid.uuid4())  # UUID v4
        
        return cls(
            session_id=session_id,
            local_entity_id=local_entity_id,
            remote_entity_id=remote_entity_id,
            local_keypair=local_keypair,
            state=SessionState.INITIAL,
            timeout_seconds=timeout_seconds
        )
    
    def is_expired(self) -> bool:
        """Check if session has expired"""
        now = datetime.now(timezone.utc)
        return (now - self.last_activity).total_seconds() > self.timeout_seconds
    
    def touch(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = datetime.now(timezone.utc)
    
    def next_sequence(self) -> int:
        """Get next local sequence number"""
        seq = self.local_sequence
        self.local_sequence += 1
        if self.local_sequence > self.max_sequence:
            self.local_sequence = 0  # Wrap around
        return seq
    
    def validate_remote_sequence(self, seq: int) -> bool:
        """Validate incoming sequence number"""
        # Accept if sequence is greater than last seen (allowing gaps)
        if seq > self.remote_sequence or (self.remote_sequence > self.max_sequence - 1000 and seq < 1000):
            self.remote_sequence = seq
            return True
        return False
    
    def complete_handshake(self, remote_public_key: bytes, remote_ephemeral_key: bytes) -> None:
        """
        Complete handshake and derive session keys
        
        Args:
            remote_public_key: Remote entity's Ed25519/X25519 public key
            remote_ephemeral_key: Remote ephemeral X25519 public key
        """
        from nacl.public import PrivateKey, PublicKey, Box
        
        self.remote_public_key = remote_public_key
        
        # Perform ECDH with ephemeral keys
        local_priv = PrivateKey(self.ephemeral_private_key)
        remote_pub = PublicKey(remote_ephemeral_key)
        
        box = Box(local_priv, remote_pub)
        shared_secret = box.shared_key()
        
        # Derive session keys
        self.session_keys = SessionKeys.derive_from_shared_secret(shared_secret)
        
        self.state = SessionState.ESTABLISHED
        self.touch()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary (excluding sensitive keys)"""
        return {
            "session_id": self.session_id,
            "local_entity_id": self.local_entity_id,
            "remote_entity_id": self.remote_entity_id,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "local_sequence": self.local_sequence,
            "remote_sequence": self.remote_sequence,
            "ephemeral_public_key": base64.b64encode(self.ephemeral_public_key).decode() if self.ephemeral_public_key else None,
            "timeout_seconds": self.timeout_seconds
        }


class E2ECryptoManager:
    """
    Manager for multiple E2E encrypted sessions
    
    Handles:
    - Session creation and lookup
    - Message encryption/decryption
    - Session expiration and cleanup
    - Handshake coordination
    """
    
    def __init__(
        self,
        entity_id: str,
        keypair: KeyPair,
        default_timeout: int = 3600
    ):
        """
        Initialize E2E crypto manager
        
        Args:
            entity_id: Local entity identifier
            keypair: Local Ed25519 keypair
            default_timeout: Default session timeout in seconds
        """
        self.entity_id = entity_id
        self.keypair = keypair
        self.signer = MessageSigner(keypair)
        self.default_timeout = default_timeout
        
        # Session storage: session_id -> E2ESession
        self._sessions: Dict[str, E2ESession] = {}
        
        # Index by remote entity: remote_id -> set of session_ids
        self._sessions_by_remote: Dict[str, set] = {}
        
        # Handshake callback
        self._handshake_callback: Optional[Callable] = None
    
    def create_session(self, remote_entity_id: str) -> E2ESession:
        """Create a new session with a remote entity"""
        session = E2ESession.create(
            local_entity_id=self.entity_id,
            remote_entity_id=remote_entity_id,
            local_keypair=self.keypair,
            timeout_seconds=self.default_timeout
        )
        
        self._sessions[session.session_id] = session
        
        if remote_entity_id not in self._sessions_by_remote:
            self._sessions_by_remote[remote_entity_id] = set()
        self._sessions_by_remote[remote_entity_id].add(session.session_id)
        
        return session
    
    def get_session(self, session_id: str) -> Optional[E2ESession]:
        """Get session by ID"""
        session = self._sessions.get(session_id)
        if session and session.is_expired():
            session.state = SessionState.EXPIRED
        return session
    
    def get_active_session(self, remote_entity_id: str) -> Optional[E2ESession]:
        """Get first active (established, non-expired) session with remote entity"""
        session_ids = self._sessions_by_remote.get(remote_entity_id, set())
        
        for sid in session_ids:
            session = self._sessions.get(sid)
            if session and session.state == SessionState.ESTABLISHED and not session.is_expired():
                return session
        
        return None
    
    def close_session(self, session_id: str) -> bool:
        """Close and remove a session"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        session.state = SessionState.CLOSED
        
        # Remove from indexes
        del self._sessions[session_id]
        
        remote_id = session.remote_entity_id
        if remote_id in self._sessions_by_remote:
            self._sessions_by_remote[remote_id].discard(session_id)
            if not self._sessions_by_remote[remote_id]:
                del self._sessions_by_remote[remote_id]
        
        return True
    
    def cleanup_expired_sessions(self) -> int:
        """Remove all expired sessions, return count removed"""
        expired_ids = [
            sid for sid, session in self._sessions.items()
            if session.is_expired() or session.state == SessionState.EXPIRED
        ]
        
        for sid in expired_ids:
            self.close_session(sid)
        
        return len(expired_ids)
    
    def create_handshake_message(
        self,
        remote_entity_id: str,
        session: Optional[E2ESession] = None
    ) -> Tuple[E2ESession, SecureMessage]:
        """
        Create a handshake message to initiate E2E session
        
        Returns:
            (session, handshake_message)
        """
        if session is None:
            session = self.create_session(remote_entity_id)
        
        # Generate challenge
        challenge = secrets.token_bytes(32)
        session.challenge = challenge
        session.state = SessionState.HANDSHAKE_SENT
        
        # Build handshake payload
        payload = {
            "handshake_type": "initiate",
            "ephemeral_public_key": base64.b64encode(session.ephemeral_public_key).decode(),
            "challenge": base64.b64encode(challenge).decode(),
            "public_key": self.keypair.get_public_key_hex(),
            "supported_versions": ["1.0"],
            "capabilities": ["e2e_encryption", "aes_256_gcm", "x25519"]
        }
        
        message = SecureMessage(
            version="1.0",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.entity_id,
            recipient_id=remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return session, message
    
    def create_handshake_response(
        self,
        session: E2ESession,
        remote_challenge: bytes
    ) -> SecureMessage:
        """Create handshake response (handshake_ack)"""
        
        # Create challenge response
        challenge_response = hashlib.sha256(remote_challenge + self.keypair.private_key).digest()
        
        payload = {
            "handshake_type": "response",
            "ephemeral_public_key": base64.b64encode(session.ephemeral_public_key).decode(),
            "challenge_response": base64.b64encode(challenge_response).decode(),
            "public_key": self.keypair.get_public_key_hex(),
            "accepted_version": "1.0"
        }
        
        message = SecureMessage(
            version="1.0",
            msg_type=MessageType.HANDSHAKE_ACK,
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.state = SessionState.HANDSHAKE_RECEIVED
        session.touch()
        return message
    
    def process_handshake_response(
        self,
        session: E2ESession,
        response_payload: Dict[str, Any]
    ) -> bool:
        """
        Process handshake response and complete session establishment
        
        Args:
            session: The session being established
            response_payload: The payload from handshake_ack message
            
        Returns:
            True if handshake completed successfully
        """
        # Extract remote ephemeral key
        remote_ephemeral_b64 = response_payload.get("ephemeral_public_key")
        if not remote_ephemeral_b64:
            raise ValueError("Missing ephemeral public key")
        
        remote_ephemeral = base64.b64decode(remote_ephemeral_b64)
        
        # Verify challenge response
        challenge_response_b64 = response_payload.get("challenge_response")
        if challenge_response_b64:
            challenge_response = base64.b64decode(challenge_response_b64)
            
            expected_response = hashlib.sha256(session.challenge + self.keypair.private_key).digest()
            
            if challenge_response != expected_response:
                raise ValueError("Invalid challenge response")
        
        # Complete handshake and derive keys
        remote_pubkey_hex = response_payload.get("public_key")
        remote_pubkey = bytes.fromhex(remote_pubkey_hex) if remote_pubkey_hex else None
        
        session.complete_handshake(remote_pubkey, remote_ephemeral)
        
        return True
    
    def encrypt_message(
        self,
        session_id: str,
        payload: Dict[str, Any]
    ) -> SecureMessage:
        """
        Encrypt a message for an established session
        
        Args:
            session_id: Target session ID
            payload: Message payload to encrypt
            
        Returns:
            SecureMessage with encrypted payload
        """
        from nacl.secret import SecretBox
        from nacl.utils import random
        
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        
        if session.state != SessionState.ESTABLISHED:
            raise ValueError(f"Session not established (state: {session.state.value})")
        
        if session.is_expired():
            raise ValueError("Session has expired")
        
        if not session.session_keys:
            raise ValueError("Session keys not available")
        
        # Encrypt payload using AES-256-GCM
        plaintext = json.dumps(payload, sort_keys=True).encode('utf-8')
        
        secret_box = SecretBox(session.session_keys.encryption_key)
        nonce = random(SecretBox.NONCE_SIZE)
        ciphertext = secret_box.encrypt(plaintext, nonce).ciphertext
        
        # Create secure message
        encrypted_payload = {
            "encrypted": True,
            "data": base64.b64encode(ciphertext).decode(),
            "nonce": base64.b64encode(nonce).decode()
        }
        
        message = SecureMessage(
            version="1.0",
            msg_type=MessageType.STATUS_REPORT,  # Or specific encrypted type
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=encrypted_payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return message
    
    def decrypt_message(
        self,
        session: E2ESession,
        message: SecureMessage
    ) -> Dict[str, Any]:
        """
        Decrypt a message from an established session
        
        Args:
            session: The E2E session
            message: SecureMessage to decrypt
            
        Returns:
            Decrypted payload dictionary
        """
        from nacl.secret import SecretBox
        
        if session.state != SessionState.ESTABLISHED:
            raise ValueError("Session not established")
        
        if session.is_expired():
            raise ValueError("Session has expired")
        
        # Validate sequence
        if message.sequence_num is not None:
            if not session.validate_remote_sequence(message.sequence_num):
                raise ValueError(f"Invalid sequence number: {message.sequence_num}")
        
        # Decrypt payload
        payload = message.payload
        if not payload.get("encrypted"):
            return payload  # Not encrypted
        
        if not session.session_keys:
            raise ValueError("No session keys available")
        
        try:
            ciphertext = base64.b64decode(payload["data"])
            nonce = base64.b64decode(payload["nonce"])
            
            secret_box = SecretBox(session.session_keys.encryption_key)
            plaintext = secret_box.decrypt(ciphertext, nonce)
            
            session.touch()
            return json.loads(plaintext.decode('utf-8'))
            
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")
    
    def create_handshake_confirm(self, session: E2ESession) -> SecureMessage:
        """Create handshake confirmation message"""
        payload = {
            "handshake_type": "confirm",
            "session_established": True,
            "encryption_params": {
                "algorithm": "AES-256-GCM",
                "key_exchange": "X25519"
            }
        }
        
        message = SecureMessage(
            version="1.0",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return message
    
    def list_sessions(self, remote_id: Optional[str] = None) -> list:
        """List all sessions, optionally filtered by remote entity"""
        if remote_id:
            session_ids = self._sessions_by_remote.get(remote_id, set())
            return [self._sessions[sid].to_dict() for sid in session_ids if sid in self._sessions]
        
        return [session.to_dict() for session in self._sessions.values()]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics"""
        states = {}
        for session in self._sessions.values():
            state = session.state.value
            states[state] = states.get(state, 0) + 1
        
        return {
            "total_sessions": len(self._sessions),
            "sessions_by_state": states,
            "unique_remotes": len(self._sessions_by_remote)
        }


class E2EHandshakeHandler:
    """
    Handler for E2E handshake protocol flow
    
    Implements the 3-way handshake:
    1. A -> B: handshake (with challenge)
    2. B -> A: handshake_ack (with challenge response + B's challenge)
    3. A -> B: handshake_confirm
    """
    
    def __init__(self, crypto_manager: E2ECryptoManager):
        self.manager = crypto_manager
    
    def initiate_handshake(self, remote_entity_id: str) -> Tuple[E2ESession, SecureMessage]:
        """Initiate handshake as Alice (entity A)"""
        return self.manager.create_handshake_message(remote_entity_id)
    
    def respond_to_handshake(
        self,
        remote_entity_id: str,
        remote_public_key: bytes,
        incoming_payload: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Tuple[E2ESession, SecureMessage]:
        """
        Respond to handshake as Bob (entity B)
        
        Args:
            remote_entity_id: ID of the initiating entity
            remote_public_key: Public key of initiator
            incoming_payload: Payload from received handshake
            session_id: Optional session ID (if provided by initiator)
            
        Returns:
            (session, response_message)
        """
        # Create or use existing session
        if session_id:
            session = self.manager.get_session(session_id)
            if not session:
                session = self.manager.create_session(remote_entity_id)
                session.session_id = session_id  # Use provided ID
        else:
            session = self.manager.create_session(remote_entity_id)
        
        session.remote_public_key = remote_public_key
        
        # Extract remote ephemeral key
        remote_ephemeral_b64 = incoming_payload.get("ephemeral_public_key")
        if remote_ephemeral_b64:
            remote_ephemeral = base64.b64decode(remote_ephemeral_b64)
        else:
            raise ValueError("Missing ephemeral public key in handshake")
        
        # Extract challenge
        challenge_b64 = incoming_payload.get("challenge")
        if challenge_b64:
            remote_challenge = base64.b64decode(challenge_b64)
        else:
            raise ValueError("Missing challenge in handshake")
        
        # Complete key exchange (we are responder)
        session.complete_handshake(remote_public_key, remote_ephemeral)
        
        # Create response
        response = self.manager.create_handshake_response(session, remote_challenge)
        
        return session, response
    
    def confirm_handshake(
        self,
        session: E2ESession,
        response_payload: Dict[str, Any]
    ) -> SecureMessage:
        """
        Confirm handshake as Alice (final step)
        
        Args:
            session: The session being established
            response_payload: Payload from handshake_ack
            
        Returns:
            Confirmation message
        """
        # Process the response
        self.manager.process_handshake_response(session, response_payload)
        
        # Create confirmation
        return self.manager.create_handshake_confirm(session)


# Update __all__ to include E2E exports
__all__.extend([
    "SessionState",
    "SessionKeys", 
    "E2ESession",
    "E2ECryptoManager",
    "E2EHandshakeHandler",
    "DECRYPTION_FAILED",
    "SESSION_EXPIRED",
    "SEQUENCE_ERROR",
    "REPLAY_DETECTED",
])
