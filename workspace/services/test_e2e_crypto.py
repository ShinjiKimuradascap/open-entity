#!/usr/bin/env python3
"""
Tests for E2E Encryption Layer

Test coverage:
- X25519 key exchange
- AES-256-GCM encryption/decryption
- Session management (UUID, sequence numbers)
- Three-way handshake
- Replay protection
- Session expiration
- Protocol compliance
"""

import pytest
import time
import secrets
import base64
from datetime import datetime, timezone, timedelta

# Skip all tests if PyNaCl not available
try:
    from nacl.public import PrivateKey, PublicKey, Box
    from nacl.secret import SecretBox
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False

from crypto import (
    KeyPair, MessageSigner, SignatureVerifier,
    SecureMessage, MessageType, ProtocolError,
    DECRYPTION_FAILED, SESSION_EXPIRED, SEQUENCE_ERROR
)
from e2e_crypto import (
    SessionState, SessionKeys, E2ESession,
    E2ECryptoManager, E2EHandshakeHandler,
    generate_keypair, create_e2e_manager
)

# Test marker for CI categorization
pytestmark = pytest.mark.integration


pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not installed")


class TestSessionKeys:
    """Tests for SessionKeys key derivation"""
    
    def test_key_derivation(self):
        """Test HKDF-like key derivation from shared secret"""
        shared_secret = secrets.token_bytes(32)
        
        keys = SessionKeys.derive_from_shared_secret(shared_secret)
        
        assert len(keys.encryption_key) == 32
        assert len(keys.auth_key) == 32
        assert keys.encryption_key != keys.auth_key
        assert keys.encryption_key != shared_secret
    
    def test_deterministic_derivation(self):
        """Same secret should derive same keys"""
        shared_secret = secrets.token_bytes(32)
        
        keys1 = SessionKeys.derive_from_shared_secret(shared_secret)
        keys2 = SessionKeys.derive_from_shared_secret(shared_secret)
        
        assert keys1.encryption_key == keys2.encryption_key
        assert keys1.auth_key == keys2.auth_key
    
    def test_different_secrets_different_keys(self):
        """Different secrets should derive different keys"""
        secret1 = secrets.token_bytes(32)
        secret2 = secrets.token_bytes(32)
        
        keys1 = SessionKeys.derive_from_shared_secret(secret1)
        keys2 = SessionKeys.derive_from_shared_secret(secret2)
        
        assert keys1.encryption_key != keys2.encryption_key


class TestE2ESession:
    """Tests for E2ESession"""
    
    @pytest.fixture
    def keypair(self):
        return KeyPair.generate()
    
    def test_session_creation(self, keypair):
        """Test basic session creation"""
        session = E2ESession.create(
            local_entity_id="alice",
            remote_entity_id="bob",
            local_keypair=keypair,
            timeout_seconds=3600
        )
        
        # UUID v4 format validation
        assert len(session.session_id) == 36  # UUID format
        assert session.session_id[14] == '4'  # Version 4
        
        assert session.local_entity_id == "alice"
        assert session.remote_entity_id == "bob"
        assert session.state == SessionState.INITIAL
        assert session.local_sequence == 0
        assert session.remote_sequence == 0
        assert session.session_keys is None
    
    def test_session_ephemeral_keys(self, keypair):
        """Test ephemeral key generation"""
        session = E2ESession.create("alice", "bob", keypair)
        
        assert session.ephemeral_private_key is not None
        assert session.ephemeral_public_key is not None
        assert len(session.ephemeral_private_key) == 32
        assert len(session.ephemeral_public_key) == 32
    
    def test_sequence_generation(self, keypair):
        """Test sequence number generation"""
        session = E2ESession.create("alice", "bob", keypair)
        
        seq1 = session.next_sequence()
        seq2 = session.next_sequence()
        seq3 = session.next_sequence()
        
        assert seq1 == 0
        assert seq2 == 1
        assert seq3 == 2
        assert session.local_sequence == 3
    
    def test_sequence_wrapping(self, keypair):
        """Test sequence number wrapping"""
        session = E2ESession.create("alice", "bob", keypair)
        session.local_sequence = session.max_sequence - 1
        
        seq1 = session.next_sequence()
        seq2 = session.next_sequence()
        
        assert seq1 == session.max_sequence - 1
        assert seq2 == 0  # Wrapped
    
    def test_remote_sequence_validation(self, keypair):
        """Test incoming sequence validation"""
        session = E2ESession.create("alice", "bob", keypair)
        
        assert session.validate_remote_sequence(1) is True
        assert session.validate_remote_sequence(2) is True
        assert session.validate_remote_sequence(5) is True
        assert session.validate_remote_sequence(3) is False  # Old sequence
        assert session.validate_remote_sequence(5) is False  # Duplicate
    
    def test_session_expiration(self, keypair):
        """Test session expiration"""
        session = E2ESession.create("alice", "bob", keypair, timeout_seconds=0)
        time.sleep(0.1)
        
        assert session.is_expired() is True
    
    def test_session_not_expired(self, keypair):
        """Test active session"""
        session = E2ESession.create("alice", "bob", keypair, timeout_seconds=3600)
        
        assert session.is_expired() is False
    
    def test_session_touch(self, keypair):
        """Test activity timestamp update"""
        session = E2ESession.create("alice", "bob", keypair)
        old_time = session.last_activity
        
        time.sleep(0.01)
        session.touch()
        
        assert session.last_activity > old_time
    
    def test_session_serialization(self, keypair):
        """Test session to_dict serialization"""
        session = E2ESession.create("alice", "bob", keypair)
        data = session.to_dict()
        
        assert data["session_id"] == session.session_id
        assert data["local_entity_id"] == "alice"
        assert data["remote_entity_id"] == "bob"
        assert data["state"] == "initial"
        assert "ephemeral_public_key" in data
        assert "created_at" in data
        assert "last_activity" in data
        # Sensitive keys should NOT be included
        assert "session_keys" not in data
        assert "ephemeral_private_key" not in data


class TestE2ECryptoManager:
    """Tests for E2ECryptoManager"""
    
    @pytest.fixture
    def alice_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("alice", kp)
    
    @pytest.fixture
    def bob_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("bob", kp)
    
    def test_create_session(self, alice_manager):
        """Test session creation via manager"""
        session = alice_manager.create_session("bob")
        
        assert session.session_id in alice_manager._sessions
        assert "bob" in alice_manager._sessions_by_remote
        assert session.session_id in alice_manager._sessions_by_remote["bob"]
    
    def test_get_session(self, alice_manager):
        """Test session retrieval"""
        session = alice_manager.create_session("bob")
        retrieved = alice_manager.get_session(session.session_id)
        
        assert retrieved is session
    
    def test_get_session_expired(self, alice_manager):
        """Test expired session detection"""
        session = alice_manager.create_session("bob")
        session.timeout_seconds = 0
        time.sleep(0.1)
        
        retrieved = alice_manager.get_session(session.session_id)
        assert retrieved.state == SessionState.EXPIRED
    
    def test_get_active_session(self, alice_manager):
        """Test getting active session by remote ID"""
        session = alice_manager.create_session("bob")
        session.state = SessionState.ESTABLISHED
        session.session_keys = SessionKeys(
            encryption_key=secrets.token_bytes(32),
            auth_key=secrets.token_bytes(32)
        )
        
        active = alice_manager.get_active_session("bob")
        assert active is session
    
    def test_close_session(self, alice_manager):
        """Test session closing"""
        session = alice_manager.create_session("bob")
        sid = session.session_id
        
        result = alice_manager.close_session(sid)
        
        assert result is True
        assert sid not in alice_manager._sessions
        assert sid not in alice_manager._sessions_by_remote.get("bob", set())
    
    def test_cleanup_expired_sessions(self, alice_manager):
        """Test expired session cleanup"""
        # Create sessions
        s1 = alice_manager.create_session("bob")
        s2 = alice_manager.create_session("charlie")
        s3 = alice_manager.create_session("dave")
        
        # Mark some as expired
        s1.state = SessionState.EXPIRED
        s2.timeout_seconds = 0
        time.sleep(0.1)
        
        cleaned = alice_manager.cleanup_expired_sessions()
        
        assert cleaned == 2  # s1 and s2
        assert s1.session_id not in alice_manager._sessions
        assert s2.session_id not in alice_manager._sessions
        assert s3.session_id in alice_manager._sessions
    
    def test_list_sessions(self, alice_manager):
        """Test session listing"""
        alice_manager.create_session("bob")
        alice_manager.create_session("bob")
        alice_manager.create_session("charlie")
        
        all_sessions = alice_manager.list_sessions()
        bob_sessions = alice_manager.list_sessions("bob")
        
        assert len(all_sessions) == 3
        assert len(bob_sessions) == 2
    
    def test_get_stats(self, alice_manager):
        """Test manager statistics"""
        s1 = alice_manager.create_session("bob")
        s2 = alice_manager.create_session("charlie")
        s1.state = SessionState.ESTABLISHED
        s2.state = SessionState.HANDSHAKE_SENT
        
        stats = alice_manager.get_stats()
        
        assert stats["total_sessions"] == 2
        assert stats["unique_remotes"] == 2
        assert stats["sessions_by_state"]["established"] == 1
        assert stats["sessions_by_state"]["handshake_sent"] == 1


class TestEncryptionDecryption:
    """Tests for message encryption and decryption"""
    
    @pytest.fixture
    def alice_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("alice", kp)
    
    @pytest.fixture
    def bob_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("bob", kp)
    
    @pytest.fixture
    def established_session(self, alice_manager, bob_manager):
        """Create an established session between Alice and Bob"""
        # Alice creates session and initiates handshake
        session_a, handshake = alice_manager.create_handshake_message("bob")
        
        # Bob responds
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        handler = E2EHandshakeHandler(bob_manager)
        session_b, response = handler.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        
        # Alice completes
        handler_alice = E2EHandshakeHandler(alice_manager)
        handler_alice.confirm_handshake(session_a, response.payload)
        
        return session_a, session_b, alice_manager, bob_manager
    
    def test_encrypt_decrypt(self, established_session):
        """Test basic encryption and decryption"""
        session_a, session_b, alice_manager, bob_manager = established_session
        
        payload = {"message": "Hello, Bob!", "secret": 12345}
        
        # Alice encrypts
        encrypted = alice_manager.encrypt_message(session_a.session_id, payload)
        
        # Bob decrypts
        decrypted = bob_manager.decrypt_message(session_b, encrypted)
        
        assert decrypted == payload
    
    def test_encrypt_complex_payload(self, established_session):
        """Test encryption of complex nested payload"""
        session_a, session_b, alice_manager, bob_manager = established_session
        
        payload = {
            "type": "task_delegate",
            "task": {
                "id": "task-123",
                "priority": "high",
                "data": {"nested": [1, 2, 3], "nested_dict": {"a": "b"}}
            },
            "metadata": None,
            "tags": ["urgent", "crypto"]
        }
        
        encrypted = alice_manager.encrypt_message(session_a.session_id, payload)
        decrypted = bob_manager.decrypt_message(session_b, encrypted)
        
        assert decrypted == payload
    
    def test_encrypt_session_not_found(self, alice_manager):
        """Test encryption with invalid session ID"""
        with pytest.raises(ProtocolError) as exc_info:
            alice_manager.encrypt_message("invalid-id", {"test": "data"})
        
        assert exc_info.value.code == SESSION_EXPIRED
    
    def test_encrypt_session_not_established(self, alice_manager):
        """Test encryption with non-established session"""
        session = alice_manager.create_session("bob")
        # Session is in INITIAL state
        
        with pytest.raises(ProtocolError) as exc_info:
            alice_manager.encrypt_message(session.session_id, {"test": "data"})
        
        assert exc_info.value.code == SESSION_EXPIRED
    
    def test_encrypt_session_expired(self, alice_manager):
        """Test encryption with expired session"""
        session = alice_manager.create_session("bob")
        session.state = SessionState.ESTABLISHED
        session.session_keys = SessionKeys(
            encryption_key=secrets.token_bytes(32),
            auth_key=secrets.token_bytes(32)
        )
        session.timeout_seconds = 0
        time.sleep(0.1)
        
        with pytest.raises(ProtocolError) as exc_info:
            alice_manager.encrypt_message(session.session_id, {"test": "data"})
        
        assert exc_info.value.code == SESSION_EXPIRED
    
    def test_decrypt_invalid_sequence(self, established_session):
        """Test decryption with invalid sequence number"""
        session_a, session_b, alice_manager, bob_manager = established_session
        
        # Send message
        msg = alice_manager.encrypt_message(session_a.session_id, {"seq": 1})
        bob_manager.decrypt_message(session_b, msg)  # seq 0
        
        # Replay same message
        with pytest.raises(ProtocolError) as exc_info:
            bob_manager.decrypt_message(session_b, msg)  # seq 0 again
        
        assert exc_info.value.code == SEQUENCE_ERROR
    
    def test_decrypt_tampered_message(self, established_session):
        """Test decryption with tampered ciphertext"""
        session_a, session_b, alice_manager, bob_manager = established_session
        
        msg = alice_manager.encrypt_message(session_a.session_id, {"test": "data"})
        
        # Tamper with ciphertext
        msg.payload["data"] = base64.b64encode(b"tampered").decode()
        
        with pytest.raises(ProtocolError) as exc_info:
            bob_manager.decrypt_message(session_b, msg)
        
        assert exc_info.value.code == DECRYPTION_FAILED


class TestHandshake:
    """Tests for three-way handshake protocol"""
    
    @pytest.fixture
    def alice_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("alice", kp)
    
    @pytest.fixture
    def bob_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("bob", kp)
    
    def test_handshake_initiate(self, alice_manager):
        """Test handshake initiation"""
        session, message = alice_manager.create_handshake_message("bob")
        
        assert session.state == SessionState.HANDSHAKE_SENT
        assert message.msg_type == MessageType.HANDSHAKE
        assert message.payload["handshake_type"] == "initiate"
        assert "ephemeral_public_key" in message.payload
        assert "challenge" in message.payload
        assert "public_key" in message.payload
        assert "supported_versions" in message.payload
        assert message.session_id == session.session_id
        assert message.signature is not None
    
    def test_handshake_response(self, alice_manager, bob_manager):
        """Test handshake response"""
        # Alice initiates
        session_a, handshake = alice_manager.create_handshake_message("bob")
        
        # Bob responds
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        handler = E2EHandshakeHandler(bob_manager)
        session_b, response = handler.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        
        assert session_b.state == SessionState.ESTABLISHED
        assert session_b.session_keys is not None
        assert response.msg_type == MessageType.HANDSHAKE_ACK
        assert response.payload["handshake_type"] == "response"
        assert "challenge_response" in response.payload
    
    def test_handshake_confirm(self, alice_manager, bob_manager):
        """Test handshake confirmation"""
        # Alice initiates
        session_a, handshake = alice_manager.create_handshake_message("bob")
        
        # Bob responds
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        handler_bob = E2EHandshakeHandler(bob_manager)
        session_b, response = handler_bob.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        
        # Alice confirms
        handler_alice = E2EHandshakeHandler(alice_manager)
        confirm = handler_alice.confirm_handshake(session_a, response.payload)
        
        assert session_a.state == SessionState.ESTABLISHED
        assert session_a.session_keys is not None
        assert confirm.msg_type == MessageType.HANDSHAKE
        assert confirm.payload["handshake_type"] == "confirm"
        assert confirm.payload["session_established"] is True
    
    def test_full_handshake_communication(self, alice_manager, bob_manager):
        """Test complete handshake enables bidirectional communication"""
        # Setup handshake
        session_a, handshake = alice_manager.create_handshake_message("bob")
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        handler_bob = E2EHandshakeHandler(bob_manager)
        session_b, response = handler_bob.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        handler_alice = E2EHandshakeHandler(alice_manager)
        handler_alice.confirm_handshake(session_a, response.payload)
        
        # Test Alice -> Bob
        msg1 = alice_manager.encrypt_message(session_a.session_id, {"from": "alice"})
        decrypted1 = bob_manager.decrypt_message(session_b, msg1)
        assert decrypted1["from"] == "alice"
        
        # Test Bob -> Alice
        msg2 = bob_manager.encrypt_message(session_b.session_id, {"from": "bob"})
        decrypted2 = alice_manager.decrypt_message(session_a, msg2)
        assert decrypted2["from"] == "bob"
    
    def test_challenge_response_verification(self, alice_manager, bob_manager):
        """Test challenge-response verification in handshake"""
        session_a, handshake = alice_manager.create_handshake_message("bob")
        
        # Verify challenge was stored
        assert session_a.challenge is not None
        assert len(session_a.challenge) == 32
        
        # Bob responds
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        handler = E2EHandshakeHandler(bob_manager)
        session_b, response = handler.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        
        # Verify challenge response
        challenge_response = base64.b64decode(response.payload["challenge_response"])
        import hashlib
        expected = hashlib.sha256(session_a.challenge + bob_manager.keypair.private_key).digest()
        assert challenge_response == expected


class TestProtocolCompliance:
    """Tests for protocol v1.0 compliance"""
    
    @pytest.fixture
    def manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("test-entity", kp)
    
    def test_message_version(self, manager):
        """Test protocol version in messages"""
        session, message = manager.create_handshake_message("peer")
        
        assert message.version == "1.0"
    
    def test_session_id_uuid_format(self, manager):
        """Test session ID is valid UUID v4"""
        import uuid
        
        session, _ = manager.create_handshake_message("peer")
        
        # Should be valid UUID
        parsed = uuid.UUID(session.session_id)
        assert parsed.version == 4
    
    def test_message_signature(self, manager):
        """Test all messages are signed"""
        session, message = manager.create_handshake_message("peer")
        
        assert message.signature is not None
        assert len(base64.b64decode(message.signature)) > 0
    
    def test_timestamp_iso_format(self, manager):
        """Test timestamp is ISO8601 format"""
        session, message = manager.create_handshake_message("peer")
        
        # Should be parseable as ISO timestamp
        ts = datetime.fromisoformat(message.timestamp.replace('Z', '+00:00'))
        assert ts.tzinfo is not None
    
    def test_nonce_uniqueness(self, manager):
        """Test nonce uniqueness"""
        _, msg1 = manager.create_handshake_message("peer")
        _, msg2 = manager.create_handshake_message("peer")
        _, msg3 = manager.create_handshake_message("peer")
        
        assert msg1.nonce != msg2.nonce
        assert msg2.nonce != msg3.nonce
        assert len(msg1.nonce) >= 32  # At least 128 bits


class TestUtilities:
    """Tests for utility functions"""
    
    def test_generate_keypair(self):
        """Test keypair generation"""
        kp = generate_keypair()
        
        assert len(kp.private_key) == 64  # Ed25519 private key
        assert len(kp.public_key) == 32   # Ed25519 public key
    
    def test_create_e2e_manager(self):
        """Test manager creation helper"""
        manager = create_e2e_manager("test-entity")
        
        assert manager.entity_id == "test-entity"
        assert manager.keypair is not None
    
    def test_create_e2e_manager_with_key(self):
        """Test manager creation with existing key"""
        kp = KeyPair.generate()
        manager = create_e2e_manager("test-entity", kp.get_private_key_hex())
        
        assert manager.keypair.get_public_key_hex() == kp.get_public_key_hex()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
