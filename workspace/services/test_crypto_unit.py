#!/usr/bin/env python3
"""
Unit tests for crypto.py
Covers: Ed25519 signatures, X25519 key exchange, AES-256-GCM encryption, E2E session management
"""

import os
import sys
import json
import base64
import tempfile
import time
import uuid
from unittest import mock
from datetime import datetime, timezone, timedelta

import pytest

pytestmark = pytest.mark.unit

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

# Add services directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crypto import (
    CryptoManager,
    SecureMessage,
    WalletManager,
    KeyPair,
    MessageSigner,
    SignatureVerifier,
    MessageValidator,
    ReplayProtector,
    generate_entity_keypair,
    get_public_key_from_private,
    TIMESTAMP_TOLERANCE_SECONDS,
    JWT_EXPIRY_MINUTES,
    NONCE_SIZE_BYTES,
    AES_KEY_SIZE_BYTES,
    REPLAY_WINDOW_SECONDS,
)

# Test marker for CI categorization
pytestmark = pytest.mark.unit


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def entity_keypair():
    """Generate a test keypair"""
    return generate_entity_keypair()


@pytest.fixture
def crypto_manager(entity_keypair):
    """Create a CryptoManager instance with test keys"""
    private_key_hex, public_key_hex = entity_keypair
    return CryptoManager("test_entity", private_key_hex=private_key_hex)


@pytest.fixture
def peer_keypair():
    """Generate a peer keypair for testing"""
    return generate_entity_keypair()


@pytest.fixture
def peer_crypto(peer_keypair):
    """Create a peer CryptoManager"""
    private_key_hex, public_key_hex = peer_keypair
    return CryptoManager("peer_entity", private_key_hex=private_key_hex)


@pytest.fixture
def temp_wallet_dir():
    """Create a temporary directory for wallet tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# ============================================================================
# Test KeyPair Generation
# ============================================================================

class TestKeyPairGeneration:
    """Tests for key pair generation utilities"""

    def test_generate_entity_keypair(self):
        """Test generating a new Ed25519 keypair"""
        private_hex, public_hex = generate_entity_keypair()
        
        # Check format
        assert len(private_hex) == 64  # 32 bytes = 64 hex chars
        assert len(public_hex) == 64   # 32 bytes = 64 hex chars
        
        # Check valid hex
        bytes.fromhex(private_hex)
        bytes.fromhex(public_hex)
    
    def test_get_public_key_from_private(self, entity_keypair):
        """Test deriving public key from private key"""
        private_hex, public_hex = entity_keypair
        derived_public = get_public_key_from_private(private_hex)
        assert derived_public == public_hex
    
    def test_keypair_class_generate(self):
        """Test KeyPair.generate()"""
        kp = KeyPair.generate()
        assert len(kp.private_key) == 32
        assert len(kp.public_key) == 32
        assert kp.get_public_key_hex() == kp.public_key.hex()
        assert kp.get_private_key_hex() == kp.private_key.hex()
    
    def test_keypair_from_private_key(self, entity_keypair):
        """Test KeyPair.from_private_key()"""
        private_hex, public_hex = entity_keypair
        private_bytes = bytes.fromhex(private_hex)
        
        kp = KeyPair.from_private_key(private_bytes)
        assert kp.get_private_key_hex() == private_hex
        assert kp.get_public_key_hex() == public_hex
    
    def test_keypair_from_private_key_hex(self, entity_keypair):
        """Test KeyPair.from_private_key_hex()"""
        private_hex, public_hex = entity_keypair
        
        kp = KeyPair.from_private_key_hex(private_hex)
        assert kp.get_private_key_hex() == private_hex
        assert kp.get_public_key_hex() == public_hex


# ============================================================================
# Test CryptoManager Initialization
# ============================================================================

class TestCryptoManagerInit:
    """Tests for CryptoManager initialization"""

    def test_init_with_private_key(self, entity_keypair):
        """Test initialization with explicit private key"""
        private_hex, public_hex = entity_keypair
        cm = CryptoManager("test_entity", private_key_hex=private_hex)
        
        assert cm.entity_id == "test_entity"
        assert cm.get_ed25519_public_key_b64() is not None
    
    def test_init_with_env_var(self, entity_keypair, monkeypatch):
        """Test initialization with environment variable"""
        private_hex, public_hex = entity_keypair
        monkeypatch.setenv("ENTITY_PRIVATE_KEY", private_hex)
        
        cm = CryptoManager("test_entity")
        assert cm.entity_id == "test_entity"
        assert cm.get_ed25519_public_key_b64() is not None
    
    def test_init_without_key_raises(self):
        """Test that initialization fails without a key"""
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="ENTITY_PRIVATE_KEY"):
                CryptoManager("test_entity")


# ============================================================================
# Test Ed25519 Signatures
# ============================================================================

class TestEd25519Signatures:
    """Tests for Ed25519 signature operations"""

    def test_sign_message(self, crypto_manager):
        """Test signing a message"""
        message = {"data": "test message", "timestamp": time.time()}
        signature = crypto_manager.sign_message(message)
        
        # Check format (base64)
        decoded = base64.b64decode(signature)
        assert len(decoded) == 64  # Ed25519 signature is 64 bytes
    
    def test_verify_signature_success(self, crypto_manager):
        """Test successful signature verification"""
        message = {"data": "test message", "timestamp": time.time()}
        signature = crypto_manager.sign_message(message)
        public_key_b64 = crypto_manager.get_ed25519_public_key_b64()
        
        is_valid = crypto_manager.verify_signature(message, signature, public_key_b64)
        assert is_valid is True
    
    def test_verify_signature_failure_wrong_key(self, crypto_manager, peer_crypto):
        """Test signature verification with wrong public key"""
        message = {"data": "test message", "timestamp": time.time()}
        signature = crypto_manager.sign_message(message)
        wrong_public_key = peer_crypto.get_ed25519_public_key_b64()
        
        is_valid = crypto_manager.verify_signature(message, signature, wrong_public_key)
        assert is_valid is False
    
    def test_verify_signature_failure_tampered_message(self, crypto_manager):
        """Test signature verification with tampered message"""
        message = {"data": "test message", "timestamp": time.time()}
        signature = crypto_manager.sign_message(message)
        public_key_b64 = crypto_manager.get_ed25519_public_key_b64()
        
        # Tamper with message
        message["data"] = "tampered"
        
        is_valid = crypto_manager.verify_signature(message, signature, public_key_b64)
        assert is_valid is False
    
    def test_verify_signature_failure_invalid_signature(self, crypto_manager):
        """Test signature verification with invalid signature format"""
        message = {"data": "test message", "timestamp": time.time()}
        public_key_b64 = crypto_manager.get_ed25519_public_key_b64()
        
        is_valid = crypto_manager.verify_signature(message, "invalid_base64!!!", public_key_b64)
        assert is_valid is False


# ============================================================================
# Test X25519 Key Exchange
# ============================================================================

class TestX25519KeyExchange:
    """Tests for X25519 key exchange"""

    def test_generate_x25519_keypair(self, crypto_manager):
        """Test generating X25519 keypair"""
        private_key, public_key = crypto_manager.generate_x25519_keypair()
        
        assert isinstance(private_key, X25519PrivateKey)
        assert isinstance(public_key, X25519PublicKey)
        assert crypto_manager.get_x25519_public_key_b64() is not None
    
    def test_get_x25519_public_key_before_generation(self, crypto_manager):
        """Test getting X25519 key before generation returns None"""
        assert crypto_manager.get_x25519_public_key_b64() is None
    
    def test_derive_shared_key(self, crypto_manager, peer_crypto):
        """Test deriving shared key between two entities"""
        # Generate keypairs for both entities
        crypto_manager.generate_x25519_keypair()
        peer_crypto.generate_x25519_keypair()
        
        # Get peer's public key
        peer_x25519_b64 = peer_crypto.get_x25519_public_key_b64()
        
        # Derive shared key
        shared_key = crypto_manager.derive_shared_key(peer_x25519_b64, "peer_entity")
        
        assert len(shared_key) == AES_KEY_SIZE_BYTES  # 32 bytes
        assert shared_key == crypto_manager._shared_keys["peer_entity"]
    
    def test_derive_shared_key_symmetric(self, crypto_manager, peer_crypto):
        """Test that shared keys are symmetric"""
        # Generate keypairs
        crypto_manager.generate_x25519_keypair()
        peer_crypto.generate_x25519_keypair()
        
        # Both derive shared key
        crypto_shared = crypto_manager.derive_shared_key(
            peer_crypto.get_x25519_public_key_b64(),
            "peer_entity"
        )
        peer_shared = peer_crypto.derive_shared_key(
            crypto_manager.get_x25519_public_key_b64(),
            "crypto_entity"
        )
        
        # Keys should be identical
        assert crypto_shared == peer_shared
    
    def test_shared_key_caching(self, crypto_manager, peer_crypto):
        """Test that shared keys are cached"""
        crypto_manager.generate_x25519_keypair()
        peer_crypto.generate_x25519_keypair()
        
        peer_x25519_b64 = peer_crypto.get_x25519_public_key_b64()
        
        # First derivation
        key1 = crypto_manager.derive_shared_key(peer_x25519_b64, "peer_entity")
        # Second derivation should return cached key
        key2 = crypto_manager.derive_shared_key(peer_x25519_b64, "peer_entity")
        
        assert key1 is key2  # Same object due to caching


# ============================================================================
# Test AES-256-GCM Encryption
# ============================================================================

class TestAES256GCMEncryption:
    """Tests for AES-256-GCM encryption"""

    def test_encrypt_decrypt_payload(self, crypto_manager, peer_crypto):
        """Test encrypting and decrypting a payload"""
        # Setup keys
        crypto_manager.generate_x25519_keypair()
        peer_crypto.generate_x25519_keypair()
        
        # Encrypt from crypto_manager to peer_crypto
        payload = {"message": "secret data", "timestamp": time.time()}
        peer_x25519_b64 = peer_crypto.get_x25519_public_key_b64()
        
        ciphertext, nonce = crypto_manager.encrypt_payload(payload, peer_x25519_b64, "peer_entity")
        
        # Peer derives shared key and decrypts
        peer_crypto.derive_shared_key(crypto_manager.get_x25519_public_key_b64(), "crypto_entity")
        decrypted = peer_crypto.decrypt_payload(ciphertext, nonce, "crypto_entity")
        
        assert decrypted == payload
    
    def test_decrypt_wrong_peer_fails(self, crypto_manager, peer_crypto):
        """Test decryption fails with wrong peer"""
        crypto_manager.generate_x25519_keypair()
        peer_crypto.generate_x25519_keypair()
        
        payload = {"message": "secret data"}
        peer_x25519_b64 = peer_crypto.get_x25519_public_key_b64()
        ciphertext, nonce = crypto_manager.encrypt_payload(payload, peer_x25519_b64, "peer_entity")
        
        # Try to decrypt without proper shared key setup
        result = crypto_manager.decrypt_payload(ciphertext, nonce, "crypto_entity")
        assert result is None
    
    def test_encrypt_payload_generates_different_ciphertexts(self, crypto_manager, peer_crypto):
        """Test that same payload encrypts to different ciphertexts (nonce randomness)"""
        crypto_manager.generate_x25519_keypair()
        peer_crypto.generate_x25519_keypair()
        
        payload = {"message": "secret data"}
        peer_x25519_b64 = peer_crypto.get_x25519_public_key_b64()
        
        ct1, nonce1 = crypto_manager.encrypt_payload(payload, peer_x25519_b64, "peer_entity")
        ct2, nonce2 = crypto_manager.encrypt_payload(payload, peer_x25519_b64, "peer_entity")
        
        assert ct1 != ct2
        assert nonce1 != nonce2


# ============================================================================
# Test JWT Authentication
# ============================================================================

class TestJWTAuthentication:
    """Tests for JWT token creation and verification"""

    def test_create_jwt_token(self, crypto_manager):
        """Test creating a JWT token"""
        token = crypto_manager.create_jwt_token()
        
        # Should be a non-empty string
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Should have 3 parts (header.payload.signature)
        parts = token.split(".")
        assert len(parts) == 3
    
    def test_create_jwt_token_with_audience(self, crypto_manager):
        """Test creating a JWT token with audience"""
        token = crypto_manager.create_jwt_token(audience="test_audience")
        
        # Decode and check audience
        import jwt as pyjwt
        public_key_b64 = crypto_manager.get_ed25519_public_key_b64()
        public_key_bytes = base64.b64decode(public_key_b64)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        decoded = pyjwt.decode(token, public_key_pem, algorithms=["EdDSA"], audience="test_audience")
        assert decoded["aud"] == "test_audience"
    
    def test_verify_jwt_token_success(self, crypto_manager):
        """Test successful JWT verification"""
        token = crypto_manager.create_jwt_token()
        public_key_b64 = crypto_manager.get_ed25519_public_key_b64()
        
        decoded = crypto_manager.verify_jwt_token(token, public_key_b64)
        
        assert decoded is not None
        assert decoded["sub"] == "test_entity"
        assert decoded["iss"] == "peer-service"
    
    def test_verify_jwt_token_expired(self, crypto_manager):
        """Test verification of expired JWT"""
        # Create a token that will expire immediately
        from datetime import datetime, timezone, timedelta
        import jwt as pyjwt
        
        now = datetime.now(timezone.utc)
        expiry = now - timedelta(seconds=1)  # Already expired
        
        payload = {
            "sub": crypto_manager.entity_id,
            "iat": now - timedelta(minutes=10),
            "exp": expiry,
            "iss": "peer-service",
        }
        
        private_key_pem = crypto_manager._ed25519_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        expired_token = pyjwt.encode(payload, private_key_pem, algorithm="EdDSA")
        public_key_b64 = crypto_manager.get_ed25519_public_key_b64()
        
        decoded = crypto_manager.verify_jwt_token(expired_token, public_key_b64)
        assert decoded is None
    
    def test_verify_jwt_token_invalid(self, crypto_manager):
        """Test verification of invalid JWT"""
        public_key_b64 = crypto_manager.get_ed25519_public_key_b64()
        
        decoded = crypto_manager.verify_jwt_token("invalid.token.here", public_key_b64)
        assert decoded is None


# ============================================================================
# Test Replay Attack Prevention
# ============================================================================

class TestReplayPrevention:
    """Tests for replay attack prevention"""

    def test_generate_nonce(self, crypto_manager):
        """Test nonce generation"""
        nonce1 = crypto_manager.generate_nonce()
        nonce2 = crypto_manager.generate_nonce()
        
        # Should be base64 strings
        decoded1 = base64.b64decode(nonce1)
        decoded2 = base64.b64decode(nonce2)
        
        # Should be 16 bytes (128 bits)
        assert len(decoded1) == NONCE_SIZE_BYTES
        assert len(decoded2) == NONCE_SIZE_BYTES
        
        # Should be unique
        assert nonce1 != nonce2
    
    def test_check_and_record_nonce_success(self, crypto_manager):
        """Test successful nonce check"""
        nonce = crypto_manager.generate_nonce()
        timestamp = time.time()
        
        result = crypto_manager.check_and_record_nonce(nonce, timestamp)
        assert result is True
        
        # Nonce should be recorded
        assert nonce in crypto_manager._seen_nonces
    
    def test_check_and_record_nonce_replay(self, crypto_manager):
        """Test replay detection"""
        nonce = crypto_manager.generate_nonce()
        timestamp = time.time()
        
        # First check
        result1 = crypto_manager.check_and_record_nonce(nonce, timestamp)
        assert result1 is True
        
        # Second check (replay)
        result2 = crypto_manager.check_and_record_nonce(nonce, timestamp)
        assert result2 is False
    
    def test_check_and_record_nonce_old_timestamp(self, crypto_manager):
        """Test rejection of old timestamps"""
        nonce = crypto_manager.generate_nonce()
        old_timestamp = time.time() - TIMESTAMP_TOLERANCE_SECONDS - 1
        
        result = crypto_manager.check_and_record_nonce(nonce, old_timestamp)
        assert result is False
    
    def test_check_and_record_nonce_future_timestamp(self, crypto_manager):
        """Test rejection of future timestamps"""
        nonce = crypto_manager.generate_nonce()
        future_timestamp = time.time() + TIMESTAMP_TOLERANCE_SECONDS + 1
        
        result = crypto_manager.check_and_record_nonce(nonce, future_timestamp)
        assert result is False


# ============================================================================
# Test SecureMessage
# ============================================================================

class TestSecureMessage:
    """Tests for SecureMessage dataclass"""

    def test_secure_message_creation(self):
        """Test creating a SecureMessage"""
        msg = SecureMessage(
            payload={"data": "test"},
            timestamp=time.time(),
            nonce="nonce123",
            signature="sig456",
            sender_id="sender"
        )
        
        assert msg.payload == {"data": "test"}
        assert msg.nonce == "nonce123"
        assert msg.signature == "sig456"
    
    def test_secure_message_to_dict(self):
        """Test converting SecureMessage to dict"""
        msg = SecureMessage(
            payload={"data": "test"},
            timestamp=123.456,
            nonce="nonce123",
            signature="sig456",
            sender_id="sender"
        )
        
        d = msg.to_dict()
        assert d["payload"] == {"data": "test"}
        assert d["timestamp"] == 123.456
        assert d["nonce"] == "nonce123"
    
    def test_secure_message_from_dict(self):
        """Test creating SecureMessage from dict"""
        data = {
            "payload": {"data": "test"},
            "timestamp": 123.456,
            "nonce": "nonce123",
            "signature": "sig456",
            "sender_id": "sender",
            "session_id": "session-uuid"
        }
        
        msg = SecureMessage.from_dict(data)
        assert msg.payload == {"data": "test"}
        assert msg.session_id == "session-uuid"


# ============================================================================
# Test E2E Session Management
# ============================================================================

class TestE2ESessionManagement:
    """Tests for E2E session management via secure messages"""

    def test_create_secure_message_unencrypted(self, crypto_manager):
        """Test creating an unencrypted secure message"""
        payload = {"action": "test", "data": "value"}
        
        msg = crypto_manager.create_secure_message(payload)
        
        assert isinstance(msg, SecureMessage)
        assert msg.payload["action"] == "test"
        assert msg.sender_id == "test_entity"
        assert msg.sender_public_key == crypto_manager.get_ed25519_public_key_b64()
        assert msg.signature is not None
        assert msg.encrypted_payload is None
    
    def test_create_secure_message_encrypted(self, crypto_manager, peer_crypto):
        """Test creating an encrypted secure message"""
        # Setup keys
        peer_crypto.generate_x25519_keypair()
        peer_x25519_b64 = peer_crypto.get_x25519_public_key_b64()
        
        payload = {"action": "test", "secret": "data"}
        
        msg = crypto_manager.create_secure_message(
            payload,
            encrypt=True,
            peer_public_key_b64=peer_x25519_b64,
            peer_id="peer_entity"
        )
        
        assert isinstance(msg, SecureMessage)
        assert msg.encrypted_payload is not None
        assert ":" in msg.encrypted_payload  # ciphertext:nonce format
    
    def test_create_secure_message_with_jwt(self, crypto_manager):
        """Test creating a secure message with JWT"""
        payload = {"action": "test"}
        
        msg = crypto_manager.create_secure_message(
            payload,
            include_jwt=True
        )
        
        assert msg.jwt_token is not None
        assert len(msg.jwt_token.split(".")) == 3
    
    def test_create_secure_message_return_dict(self, crypto_manager):
        """Test creating a secure message returning dict"""
        payload = {"action": "test"}
        
        result = crypto_manager.create_secure_message(
            payload,
            return_dict=True
        )
        
        assert isinstance(result, dict)
        assert result["payload"]["action"] == "test"
    
    def test_verify_and_decrypt_message_unencrypted(self, crypto_manager):
        """Test verifying an unencrypted message"""
        payload = {"action": "test", "data": "value"}
        msg = crypto_manager.create_secure_message(payload)
        
        verified = crypto_manager.verify_and_decrypt_message(msg)
        
        assert verified is not None
        assert verified["action"] == "test"
    
    def test_verify_and_decrypt_message_encrypted(self, crypto_manager, peer_crypto):
        """Test verifying and decrypting an encrypted message"""
        # Setup
        peer_crypto.generate_x25519_keypair()
        crypto_manager.generate_x25519_keypair()
        
        peer_x25519_b64 = peer_crypto.get_x25519_public_key_b64()
        crypto_x25519_b64 = crypto_manager.get_x25519_public_key_b64()
        
        # Peer creates encrypted message to crypto
        payload = {"secret": "message"}
        msg = peer_crypto.create_secure_message(
            payload,
            encrypt=True,
            peer_public_key_b64=crypto_x25519_b64,
            peer_id="test_entity"
        )
        
        # Crypto derives shared key and verifies/decrypts
        crypto_manager.derive_shared_key(peer_x25519_b64, "peer_entity")
        verified = crypto_manager.verify_and_decrypt_message(msg, peer_id="peer_entity")
        
        assert verified is not None
        assert verified["secret"] == "message"
    
    def test_verify_and_decrypt_message_wrong_signature(self, crypto_manager, peer_crypto):
        """Test verification fails with tampered signature"""
        payload = {"action": "test"}
        msg = crypto_manager.create_secure_message(payload)
        
        # Tamper with signature
        msg.signature = base64.b64encode(b"invalid" * 10).decode("ascii")
        
        verified = crypto_manager.verify_and_decrypt_message(msg)
        assert verified is None
    
    def test_verify_and_decrypt_message_replay(self, crypto_manager):
        """Test replay detection in message verification"""
        payload = {"action": "test"}
        msg = crypto_manager.create_secure_message(payload)
        
        # First verification should succeed
        verified1 = crypto_manager.verify_and_decrypt_message(msg)
        assert verified1 is not None
        
        # Second verification should fail (replay)
        verified2 = crypto_manager.verify_and_decrypt_message(msg)
        assert verified2 is None


# ============================================================================
# Test WalletManager
# ============================================================================

class TestWalletManager:
    """Tests for WalletManager"""

    def test_create_wallet(self, temp_wallet_dir):
        """Test creating a wallet"""
        wallet_path = os.path.join(temp_wallet_dir, "wallet.json")
        wm = WalletManager(wallet_path)
        
        private_key, public_key = wm.create_wallet("test_password")
        
        assert len(private_key) == 64
        assert len(public_key) == 64
        assert wm.wallet_exists()
        assert wm._private_key_hex == private_key
    
    def test_create_wallet_empty_password(self, temp_wallet_dir):
        """Test that empty password raises error"""
        wallet_path = os.path.join(temp_wallet_dir, "wallet.json")
        wm = WalletManager(wallet_path)
        
        with pytest.raises(ValueError, match="Password cannot be empty"):
            wm.create_wallet("")
    
    def test_create_wallet_already_exists(self, temp_wallet_dir):
        """Test that creating wallet when one exists raises error"""
        wallet_path = os.path.join(temp_wallet_dir, "wallet.json")
        wm = WalletManager(wallet_path)
        wm.create_wallet("test_password")
        
        with pytest.raises(FileExistsError):
            wm.create_wallet("another_password")
    
    def test_load_wallet(self, temp_wallet_dir):
        """Test loading a wallet"""
        wallet_path = os.path.join(temp_wallet_dir, "wallet.json")
        wm = WalletManager(wallet_path)
        
        private_key, public_key = wm.create_wallet("test_password")
        
        # Load with new manager instance
        wm2 = WalletManager(wallet_path)
        loaded_private, loaded_public = wm2.load_wallet("test_password")
        
        assert loaded_private == private_key
        assert loaded_public == public_key
    
    def test_load_wallet_wrong_password(self, temp_wallet_dir):
        """Test loading with wrong password"""
        wallet_path = os.path.join(temp_wallet_dir, "wallet.json")
        wm = WalletManager(wallet_path)
        wm.create_wallet("correct_password")
        
        wm2 = WalletManager(wallet_path)
        with pytest.raises(ValueError, match="Invalid password"):
            wm2.load_wallet("wrong_password")
    
    def test_load_wallet_not_found(self, temp_wallet_dir):
        """Test loading non-existent wallet"""
        wallet_path = os.path.join(temp_wallet_dir, "nonexistent.json")
        wm = WalletManager(wallet_path)
        
        with pytest.raises(FileNotFoundError):
            wm.load_wallet("password")
    
    def test_delete_wallet(self, temp_wallet_dir):
        """Test deleting a wallet"""
        wallet_path = os.path.join(temp_wallet_dir, "wallet.json")
        wm = WalletManager(wallet_path)
        wm.create_wallet("test_password")
        
        assert wm.wallet_exists()
        wm.delete_wallet()
        assert not wm.wallet_exists()
    
    def test_wallet_integrity(self, temp_wallet_dir):
        """Test wallet data integrity"""
        wallet_path = os.path.join(temp_wallet_dir, "wallet.json")
        wm = WalletManager(wallet_path)
        
        private_key, public_key = wm.create_wallet("test_password")
        
        # Read raw wallet file
        with open(wallet_path, "r") as f:
            wallet_data = json.load(f)
        
        assert wallet_data["version"] == WalletManager.WALLET_VERSION
        assert wallet_data["public_key"] == public_key
        assert "encrypted_private_key" in wallet_data
        assert "salt" in wallet_data
        assert "nonce" in wallet_data


# ============================================================================
# Test MessageSigner and SignatureVerifier
# ============================================================================

class TestMessageSignerVerifier:
    """Tests for MessageSigner and SignatureVerifier"""

    def test_message_signer(self, entity_keypair):
        """Test MessageSigner"""
        private_hex, public_hex = entity_keypair
        kp = KeyPair.from_private_key_hex(private_hex)
        
        signer = MessageSigner(kp)
        message = {"data": "test"}
        
        signature = signer.sign_message(message)
        assert isinstance(signature, str)
        
        # Verify with SignatureVerifier
        verifier = SignatureVerifier()
        verifier.add_public_key("test_entity", bytes.fromhex(public_hex))
        
        is_valid = verifier.verify("test_entity", message, signature)
        assert is_valid is True
    
    def test_message_signer_sign_bytes(self, entity_keypair):
        """Test MessageSigner.sign_bytes"""
        private_hex, public_hex = entity_keypair
        kp = KeyPair.from_private_key_hex(private_hex)
        
        signer = MessageSigner(kp)
        data = b"binary data"
        
        signature = signer.sign_bytes(data)
        assert isinstance(signature, str)
    
    def test_signature_verifier_unknown_entity(self, entity_keypair):
        """Test verification with unknown entity"""
        verifier = SignatureVerifier()
        
        is_valid = verifier.verify("unknown", {"data": "test"}, "signature")
        assert is_valid is False
    
    def test_signature_verifier_wrong_signature(self, entity_keypair):
        """Test verification with wrong signature"""
        private_hex, public_hex = entity_keypair
        
        verifier = SignatureVerifier()
        verifier.add_public_key("test_entity", bytes.fromhex(public_hex))
        
        is_valid = verifier.verify("test_entity", {"data": "test"}, "wrong_signature")
        assert is_valid is False


# ============================================================================
# Test MessageValidator
# ============================================================================

class TestMessageValidator:
    """Tests for MessageValidator"""

    def test_validate_version(self):
        """Test version validation"""
        assert MessageValidator.validate_version("1.0") is True
        assert MessageValidator.validate_version("2.0") is False
        assert MessageValidator.validate_version("") is False
    
    def test_validate_session_id_none(self):
        """Test session ID validation with None"""
        assert MessageValidator.validate_session_id(None) is True
    
    def test_validate_session_id_valid_uuid(self):
        """Test session ID validation with valid UUID"""
        valid_uuid = str(uuid.uuid4())
        assert MessageValidator.validate_session_id(valid_uuid) is True
    
    def test_validate_session_id_invalid(self):
        """Test session ID validation with invalid values"""
        assert MessageValidator.validate_session_id("") is False
        assert MessageValidator.validate_session_id("not-a-uuid") is False
        assert MessageValidator.validate_session_id("12345") is False
    
    def test_validate_sequence(self):
        """Test sequence number validation"""
        assert MessageValidator.validate_sequence(5, 5) is True
        assert MessageValidator.validate_sequence(5, 6) is False
        assert MessageValidator.validate_sequence(0, 0) is True


# ============================================================================
# Test ReplayProtector (Backward Compatibility)
# ============================================================================

class TestReplayProtector:
    """Tests for ReplayProtector class"""

    def test_replay_protector_init(self):
        """Test ReplayProtector initialization"""
        rp = ReplayProtector(max_age_seconds=600)
        assert rp.max_age_seconds == 600
    
    def test_is_replay_old_timestamp(self):
        """Test detection of old timestamps"""
        rp = ReplayProtector(max_age_seconds=300)
        old_timestamp = time.time() - 400
        
        is_replay = rp.is_replay("nonce", old_timestamp)
        assert is_replay is True
    
    def test_is_replay_duplicate_nonce(self):
        """Test detection of duplicate nonces"""
        rp = ReplayProtector()
        timestamp = time.time()
        
        # First check
        assert rp.is_replay("nonce1", timestamp) is False
        
        # Record and check again
        rp.record_nonce("nonce1", timestamp)
        assert rp.is_replay("nonce1", timestamp) is True
    
    def test_check_and_record(self):
        """Test check_and_record method"""
        rp = ReplayProtector()
        timestamp = time.time()
        
        # First attempt
        result1 = rp.check_and_record("nonce1", timestamp)
        assert result1 is True
        
        # Replay attempt
        result2 = rp.check_and_record("nonce1", timestamp)
        assert result2 is False


# ============================================================================
# Integration Test
# ============================================================================

class TestFullE2EFlow:
    """Full E2E integration test"""

    def test_complete_encrypted_communication(self, temp_wallet_dir):
        """Test complete encrypted communication flow between two entities"""
        # Create two entities
        wallet_a_path = os.path.join(temp_wallet_dir, "wallet_a.json")
        wallet_b_path = os.path.join(temp_wallet_dir, "wallet_b.json")
        
        wm_a = WalletManager(wallet_a_path)
        wm_b = WalletManager(wallet_b_path)
        
        priv_a, pub_a = wm_a.create_wallet("password_a")
        priv_b, pub_b = wm_b.create_wallet("password_b")
        
        # Initialize crypto managers
        crypto_a = CryptoManager("entity_a", private_key_hex=priv_a)
        crypto_b = CryptoManager("entity_b", private_key_hex=priv_b)
        
        # Exchange public keys
        crypto_a.add_peer_public_key("entity_b", pub_b)
        crypto_b.add_peer_public_key("entity_a", pub_a)
        
        # Generate X25519 keypairs
        crypto_a.generate_x25519_keypair()
        crypto_b.generate_x25519_keypair()
        
        # Entity A sends encrypted message to B
        message = {
            "type": "task_delegation",
            "task": {"id": "task-123", "description": "Test task"},
            "priority": "high"
        }
        
        secure_msg = crypto_a.create_secure_message(
            message,
            encrypt=True,
            peer_public_key_b64=crypto_b.get_x25519_public_key_b64(),
            peer_id="entity_b",
            include_jwt=True
        )
        
        # Entity B receives and processes message
        crypto_b.derive_shared_key(crypto_a.get_x25519_public_key_b64(), "entity_a")
        
        decrypted = crypto_b.verify_and_decrypt_message(
            secure_msg,
            peer_id="entity_a",
            verify_jwt=True
        )
        
        assert decrypted is not None
        assert decrypted["type"] == "task_delegation"
        assert decrypted["task"]["id"] == "task-123"
        assert decrypted["priority"] == "high"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
