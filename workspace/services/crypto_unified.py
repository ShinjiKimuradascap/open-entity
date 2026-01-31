"""
Unified Cryptographic Module for AI Collaboration Platform.

This module consolidates cryptographic functionality from:
- crypto.py: Basic cryptographic operations
- e2e_crypto.py: End-to-end encryption
- crypto_utils.py: Protocol v1.1+ cryptographic utilities

Provides a single, cohesive interface for all cryptographic operations including:
- Key pair generation and management (Ed25519, X25519)
- Digital signatures (Ed25519)
- Symmetric encryption (AES-GCM)
- Key conversion and derivation
- Utility functions for encoding/decoding

Protocol Version: 1.1
"""

import os
import json
import base64
import hashlib
import secrets
import time
import uuid
import warnings
from typing import Optional, Tuple, Union, Any, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from threading import Lock

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# =============================================================================
# Constants
# =============================================================================

PROTOCOL_VERSION = "1.1"
TIMESTAMP_TOLERANCE_SECONDS = 60
REPLAY_WINDOW_SECONDS = 300
DEFAULT_SESSION_TIMEOUT = 3600
MAX_SEQUENCE_NUMBER = 2**31 - 1
ED25519_SEED_SIZE = 32
AES_KEY_SIZE = 32
AES_NONCE_SIZE = 16


# =============================================================================
# Exception Classes
# =============================================================================

class CryptoError(Exception):
    """Base exception for cryptographic operations."""
    pass


class SignatureError(CryptoError):
    """Exception raised for signature-related errors."""
    pass


class DecryptionError(CryptoError):
    """Exception raised for decryption-related errors."""
    pass


class SessionError(CryptoError):
    """Exception raised for session-related errors."""
    pass


# =============================================================================
# Core Layer: KeyPair
# =============================================================================

@dataclass
class KeyPair:
    """
    Represents an Ed25519 key pair.
    
    Attributes:
        private_key: The private key bytes (32 bytes)
        public_key: The public key bytes (32 bytes)
    """
    private_key: bytes
    public_key: bytes
    
    def __post_init__(self):
        """Validate key sizes after initialization."""
        if len(self.private_key) != ED25519_SEED_SIZE:
            raise CryptoError(
                f"Invalid private key size: {len(self.private_key)} bytes, "
                f"expected {ED25519_SEED_SIZE}"
            )
        if len(self.public_key) != ED25519_SEED_SIZE:
            raise CryptoError(
                f"Invalid public key size: {len(self.public_key)} bytes, "
                f"expected {ED25519_SEED_SIZE}"
            )
    
    @classmethod
    def generate(cls) -> "KeyPair":
        """
        Generate a new Ed25519 key pair.
        
        Returns:
            A new KeyPair instance with generated keys.
        """
        private_key_obj = Ed25519PrivateKey.generate()
        private_key = private_key_obj.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_key = private_key_obj.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return cls(private_key=private_key, public_key=public_key)
    
    @classmethod
    def from_private_key(cls, private_key: bytes) -> "KeyPair":
        """
        Create a KeyPair from a private key (derives the public key).
        
        Args:
            private_key: The 32-byte private key.
            
        Returns:
            A KeyPair instance with the derived public key.
            
        Raises:
            CryptoError: If the private key is invalid.
        """
        if len(private_key) != ED25519_SEED_SIZE:
            raise CryptoError(
                f"Invalid private key size: {len(private_key)} bytes"
            )
        
        try:
            private_key_obj = Ed25519PrivateKey.from_private_bytes(private_key)
            public_key = private_key_obj.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            return cls(private_key=private_key, public_key=public_key)
        except Exception as e:
            raise CryptoError(f"Failed to derive public key: {e}")
    
    @classmethod
    def from_private_key_hex(cls, private_key_hex: str) -> "KeyPair":
        """
        Create a KeyPair from a hex-encoded private key.
        
        Args:
            private_key_hex: The hex-encoded private key string.
            
        Returns:
            A KeyPair instance with the derived public key.
        """
        try:
            private_key = bytes.fromhex(private_key_hex)
            return cls.from_private_key(private_key)
        except ValueError as e:
            raise CryptoError(f"Invalid hex private key: {e}")
    
    def to_x25519_private(self) -> bytes:
        """
        Convert Ed25519 private key to X25519 private key.
        
        Uses the standard conversion for Ed25519 -> X25519 key exchange.
        
        Returns:
            The 32-byte X25519 private key.
        """
        # Ed25519 private key is used to derive X25519 private key
        # The conversion involves clamping as per RFC 7748
        h = hashlib.sha512(self.private_key).digest()
        # First 32 bytes with clamping
        x25519_private = bytearray(h[:32])
        x25519_private[0] &= 248  # Clear bottom 3 bits
        x25519_private[31] &= 127  # Clear top bit
        x25519_private[31] |= 64   # Set second-to-top bit
        return bytes(x25519_private)
    
    def to_x25519_public(self) -> bytes:
        """
        Convert Ed25519 public key to X25519 public key.
        
        Returns:
            The 32-byte X25519 public key.
        """
        # Montgomery u-coordinate from Edwards point
        # This is a simplified conversion; full conversion requires point arithmetic
        # For now, we derive it from the X25519 private key
        x25519_private = self.to_x25519_private()
        x25519_private_key = X25519PrivateKey.from_private_bytes(x25519_private)
        x25519_public_key = x25519_private_key.public_key()
        return x25519_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    def get_public_key_hex(self) -> str:
        """
        Get the public key as a hex string.
        
        Returns:
            Hex-encoded public key.
        """
        return self.public_key.hex()
    
    def get_private_key_hex(self) -> str:
        """
        Get the private key as a hex string.
        
        Returns:
            Hex-encoded private key.
        """
        return self.private_key.hex()


# =============================================================================
# Core Layer: Signature
# =============================================================================

class Signature:
    """
    Ed25519 signature operations.
    
    Provides static methods for signing and verifying data using Ed25519.
    """
    
    @staticmethod
    def sign(data: bytes, private_key: bytes) -> bytes:
        """
        Sign data with an Ed25519 private key.
        
        Args:
            data: The data to sign.
            private_key: The 32-byte Ed25519 private key.
            
        Returns:
            The 64-byte signature.
            
        Raises:
            SignatureError: If signing fails.
        """
        try:
            private_key_obj = Ed25519PrivateKey.from_private_bytes(private_key)
            signature = private_key_obj.sign(data)
            return signature
        except Exception as e:
            raise SignatureError(f"Failed to sign data: {e}")
    
    @staticmethod
    def verify(data: bytes, signature: bytes, public_key: bytes) -> bool:
        """
        Verify an Ed25519 signature.
        
        Args:
            data: The original data that was signed.
            signature: The 64-byte signature.
            public_key: The 32-byte Ed25519 public key.
            
        Returns:
            True if the signature is valid, False otherwise.
        """
        try:
            public_key_obj = Ed25519PublicKey.from_public_bytes(public_key)
            public_key_obj.verify(signature, data)
            return True
        except Exception:
            return False


# =============================================================================
# Core Layer: Encryption
# =============================================================================

class Encryption:
    """
    AES-GCM encryption operations.
    
    Provides authenticated encryption using AES-256-GCM.
    """
    
    @staticmethod
    def encrypt(
        plaintext: bytes,
        key: bytes,
        nonce: Optional[bytes] = None
    ) -> Tuple[bytes, bytes]:
        """
        Encrypt data using AES-256-GCM.
        
        Args:
            plaintext: The data to encrypt.
            key: The 32-byte encryption key.
            nonce: Optional 16-byte nonce. If not provided, a random nonce is generated.
            
        Returns:
            A tuple of (ciphertext, nonce).
            
        Raises:
            DecryptionError: If encryption fails.
        """
        if len(key) != AES_KEY_SIZE:
            raise DecryptionError(
                f"Invalid key size: {len(key)} bytes, expected {AES_KEY_SIZE}"
            )
        
        if nonce is None:
            nonce = generate_nonce(AES_NONCE_SIZE)
        elif len(nonce) != AES_NONCE_SIZE:
            raise DecryptionError(
                f"Invalid nonce size: {len(nonce)} bytes, expected {AES_NONCE_SIZE}"
            )
        
        try:
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            return (ciphertext, nonce)
        except Exception as e:
            raise DecryptionError(f"Encryption failed: {e}")
    
    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
        """
        Decrypt data using AES-256-GCM.
        
        Args:
            ciphertext: The encrypted data (including auth tag).
            key: The 32-byte encryption key.
            nonce: The 16-byte nonce used for encryption.
            
        Returns:
            The decrypted plaintext.
            
        Raises:
            DecryptionError: If decryption fails (e.g., wrong key or tampered data).
        """
        if len(key) != AES_KEY_SIZE:
            raise DecryptionError(
                f"Invalid key size: {len(key)} bytes, expected {AES_KEY_SIZE}"
            )
        
        if len(nonce) != AES_NONCE_SIZE:
            raise DecryptionError(
                f"Invalid nonce size: {len(nonce)} bytes, expected {AES_NONCE_SIZE}"
            )
        
        try:
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext
        except Exception as e:
            raise DecryptionError(f"Decryption failed: {e}")


# =============================================================================
# Utility Functions
# =============================================================================

def generate_keypair() -> KeyPair:
    """
    Generate a new Ed25519 key pair.
    
    This is a convenience function equivalent to KeyPair.generate().
    
    Returns:
        A new KeyPair instance.
    """
    return KeyPair.generate()


def generate_nonce(size: int = 16) -> bytes:
    """
    Generate a cryptographically secure random nonce.
    
    Args:
        size: The size of the nonce in bytes (default: 16).
        
    Returns:
        Random bytes of the specified size.
    """
    return secrets.token_bytes(size)


def generate_uuid() -> str:
    """
    Generate a UUID4 string.
    
    Returns:
        A randomly generated UUID4 string.
    """
    return str(uuid.uuid4())


def encode_base64(data: bytes) -> str:
    """
    Encode bytes to a base64 string.
    
    Args:
        data: The bytes to encode.
        
    Returns:
        Base64-encoded string.
    """
    return base64.b64encode(data).decode('ascii')


def decode_base64(encoded: str) -> bytes:
    """
    Decode a base64 string to bytes.
    
    Args:
        encoded: The base64-encoded string.
        
    Returns:
        The decoded bytes.
        
    Raises:
        CryptoError: If decoding fails.
    """
    try:
        return base64.b64decode(encoded)
    except Exception as e:
        raise CryptoError(f"Base64 decode failed: {e}")


def encode_hex(data: bytes) -> str:
    """
    Encode bytes to a hex string.
    
    Args:
        data: The bytes to encode.
        
    Returns:
        Hex-encoded string (lowercase, no 0x prefix).
    """
    return data.hex()


def decode_hex(encoded: str) -> bytes:
    """
    Decode a hex string to bytes.
    
    Args:
        encoded: The hex-encoded string (with or without 0x prefix).
        
    Returns:
        The decoded bytes.
        
    Raises:
        CryptoError: If decoding fails.
    """
    try:
        # Remove 0x prefix if present
        if encoded.startswith('0x') or encoded.startswith('0X'):
            encoded = encoded[2:]
        return bytes.fromhex(encoded)
    except Exception as e:
        raise CryptoError(f"Hex decode failed: {e}")


def hash_data(data: bytes, algorithm: str = "sha256") -> bytes:
    """
    Compute a cryptographic hash of the data.
    
    Args:
        data: The data to hash.
        algorithm: The hash algorithm to use (default: sha256).
                  Supported: sha256, sha384, sha512, sha3_256, sha3_512, blake2b.
        
    Returns:
        The hash digest.
        
    Raises:
        CryptoError: If the algorithm is not supported.
    """
    algorithms = {
        "sha256": hashlib.sha256,
        "sha384": hashlib.sha384,
        "sha512": hashlib.sha512,
        "sha3_256": hashlib.sha3_256,
        "sha3_512": hashlib.sha3_512,
        "blake2b": hashlib.blake2b,
    }
    
    if algorithm not in algorithms:
        raise CryptoError(f"Unsupported hash algorithm: {algorithm}")
    
    hasher = algorithms[algorithm]()
    hasher.update(data)
    return hasher.digest()
