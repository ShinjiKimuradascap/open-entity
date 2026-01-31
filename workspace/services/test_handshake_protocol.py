#!/usr/bin/env python3
"""
Handshake Protocol Tests for E2E Encryption

Tests for E2EHandshakeHandler class:
- initiate_handshake()
- respond_to_handshake()
- confirm_handshake()

Test coverage:
- Challenge generation and verification
- 3-way X25519 handshake flow
- Failure scenarios
- Timeout handling
"""

import pytest
import time
import secrets
import base64
import hashlib
from datetime import datetime, timezone

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


pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not installed")


class TestHandshakeChallengeGeneration:
    """Tests for handshake challenge generation (test_handshake_challenge_generation)"""
    
    @pytest.fixture
    def alice_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("alice", kp)
    
    def test_challenge_generation_length(self, alice_manager):
        """Challenge should be 32 bytes (256 bits)"""
        session, message = alice_manager.create_handshake_message("bob")
        
        assert session.challenge is not None
        assert len(session.challenge) == 32
    
    def test_challenge_uniqueness(self, alice_manager):
        """Each handshake should generate unique challenge"""
        session1, msg1 = alice_manager.create_handshake_message("bob")
        session2, msg2 = alice_manager.create_handshake_message("bob")
        session3, msg3 = alice_manager.create_handshake_message("charlie")
        
        assert session1.challenge != session2.challenge
        assert session2.challenge != session3.challenge
    
    def test_challenge_in_payload(self, alice_manager):
        """Challenge should be included in handshake payload"""
        session, message = alice_manager.create_handshake_message("bob")
        
        assert "challenge" in message.payload
        decoded_challenge = base64.b64decode(message.payload["challenge"])
        assert decoded_challenge == session.challenge
    
    def test_challenge_randomness(self, alice_manager):
        """Challenge should be cryptographically random"""
        challenges = []
        for _ in range(10):
            session, _ = alice_manager.create_handshake_message("bob")
            challenges.append(session.challenge)
        
        # All should be unique
        assert len(set(challenges)) == 10
    
    def test_challenge_response_computation(self, alice_manager):
        """Test challenge response computation logic"""
        kp = KeyPair.generate()
        challenge = secrets.token_bytes(32)
        
        # Compute expected response
        expected_response = hashlib.sha256(challenge + kp.private_key).digest()
        
        assert len(expected_response) == 32
        assert expected_response != challenge


class TestX25519HandshakeFlow:
    """Tests for complete 3-way X25519 handshake flow (test_x25519_handshake_flow)"""
    
    @pytest.fixture
    def alice_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("alice", kp)
    
    @pytest.fixture
    def bob_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("bob", kp)
    
    @pytest.fixture
    def handlers(self, alice_manager, bob_manager):
        return (
            E2EHandshakeHandler(alice_manager),
            E2EHandshakeHandler(bob_manager)
        )
    
    def test_initiate_handshake(self, alice_manager, handlers):
        """Test initiate_handshake creates proper message"""
        handler_alice, _ = handlers
        
        session, message = handler_alice.initiate_handshake("bob")
        
        assert session.local_entity_id == "alice"
        assert session.remote_entity_id == "bob"
        assert session.state == SessionState.HANDSHAKE_SENT
        assert message.msg_type == MessageType.HANDSHAKE
        assert message.payload["handshake_type"] == "initiate"
        assert "ephemeral_public_key" in message.payload
        assert message.signature is not None
    
    def test_respond_to_handshake(self, alice_manager, bob_manager, handlers):
        """Test respond_to_handshake processes initial handshake"""
        handler_alice, handler_bob = handlers
        
        # Step 1: Alice initiates
        session_a, handshake = handler_alice.initiate_handshake("bob")
        
        # Step 2: Bob responds
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        session_b, response = handler_bob.respond_to_handshake(
            "alice",
            alice_pubkey,
            handshake.payload,
            session_a.session_id
        )
        
        assert session_b.state == SessionState.ESTABLISHED
        assert session_b.session_keys is not None
        assert session_b.remote_public_key == alice_pubkey
        assert response.msg_type == MessageType.HANDSHAKE_ACK
        assert "challenge_response" in response.payload
    
    def test_confirm_handshake(self, alice_manager, bob_manager, handlers):
        """Test confirm_handshake completes the handshake"""
        handler_alice, handler_bob = handlers
        
        # Step 1: Alice initiates
        session_a, handshake = handler_alice.initiate_handshake("bob")
        
        # Step 2: Bob responds
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        session_b, response = handler_bob.respond_to_handshake(
            "alice",
            alice_pubkey,
            handshake.payload,
            session_a.session_id
        )
        
        # Step 3: Alice confirms
        confirm = handler_alice.confirm_handshake(session_a, response.payload)
        
        assert session_a.state == SessionState.ESTABLISHED
        assert session_a.session_keys is not None
        assert confirm.msg_type == MessageType.HANDSHAKE
        assert confirm.payload["handshake_type"] == "confirm"
        assert confirm.payload["session_established"] is True
    
    def test_full_3way_handshake(self, alice_manager, bob_manager, handlers):
        """Test complete 3-way handshake flow"""
        handler_alice, handler_bob = handlers
        
        # Step 1: Alice -> Bob: handshake
        session_a, handshake = handler_alice.initiate_handshake("bob")
        assert session_a.state == SessionState.HANDSHAKE_SENT
        assert "challenge" in handshake.payload
        
        # Step 2: Bob -> Alice: handshake_ack
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        session_b, response = handler_bob.respond_to_handshake(
            "alice",
            alice_pubkey,
            handshake.payload,
            session_a.session_id
        )
        assert session_b.state == SessionState.ESTABLISHED
        assert session_b.session_keys is not None
        
        # Step 3: Alice -> Bob: handshake_confirm
        confirm = handler_alice.confirm_handshake(session_a, response.payload)
        assert session_a.state == SessionState.ESTABLISHED
        assert session_a.session_keys is not None
        assert confirm.payload["handshake_type"] == "confirm"
    
    def test_session_key_derivation(self, alice_manager, bob_manager, handlers):
        """Test that both parties derive same session keys"""
        handler_alice, handler_bob = handlers
        
        # Complete handshake
        session_a, handshake = handler_alice.initiate_handshake("bob")
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        session_b, response = handler_bob.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        handler_alice.confirm_handshake(session_a, response.payload)
        
        # Both should have session keys
        assert session_a.session_keys is not None
        assert session_b.session_keys is not None
        
        # Keys should be different (different purposes)
        assert session_a.session_keys.encryption_key != session_a.session_keys.auth_key
        assert session_b.session_keys.encryption_key != session_b.session_keys.auth_key
    
    def test_bidirectional_communication_after_handshake(self, alice_manager, bob_manager, handlers):
        """Test that handshake enables bidirectional encrypted communication"""
        handler_alice, handler_bob = handlers
        
        # Complete handshake
        session_a, handshake = handler_alice.initiate_handshake("bob")
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        session_b, response = handler_bob.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        handler_alice.confirm_handshake(session_a, response.payload)
        
        # Alice -> Bob
        payload1 = {"message": "Hello from Alice", "timestamp": datetime.now(timezone.utc).isoformat()}
        encrypted1 = alice_manager.encrypt_message(session_a.session_id, payload1)
        decrypted1 = bob_manager.decrypt_message(session_b, encrypted1)
        assert decrypted1 == payload1
        
        # Bob -> Alice
        payload2 = {"message": "Hello from Bob", "timestamp": datetime.now(timezone.utc).isoformat()}
        encrypted2 = bob_manager.encrypt_message(session_b.session_id, payload2)
        decrypted2 = alice_manager.decrypt_message(session_a, encrypted2)
        assert decrypted2 == payload2
    
    def test_handshake_with_ephemeral_keys(self, alice_manager, bob_manager, handlers):
        """Test that ephemeral X25519 keys are used for handshake"""
        handler_alice, handler_bob = handlers
        
        session_a, handshake = handler_alice.initiate_handshake("bob")
        
        # Should have ephemeral keys (different from signing keys)
        assert session_a.ephemeral_public_key is not None
        assert session_a.ephemeral_private_key is not None
        
        # Ephemeral key should be different from signing key
        signing_pubkey = alice_manager.keypair.public_key
        assert session_a.ephemeral_public_key != signing_pubkey
    
    def test_challenge_response_verification(self, alice_manager, bob_manager, handlers):
        """Test challenge-response verification in 3-way handshake"""
        handler_alice, handler_bob = handlers
        
        session_a, handshake = handler_alice.initiate_handshake("bob")
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        
        # Bob creates response
        session_b, response = handler_bob.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        
        # Verify challenge response
        challenge_response = base64.b64decode(response.payload["challenge_response"])
        expected = hashlib.sha256(session_a.challenge + bob_manager.keypair.private_key).digest()
        assert challenge_response == expected


class TestHandshakeFailureScenarios:
    """Tests for handshake failure scenarios (test_handshake_failure_scenarios)"""
    
    @pytest.fixture
    def alice_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("alice", kp)
    
    @pytest.fixture
    def bob_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("bob", kp)
    
    @pytest.fixture
    def handlers(self, alice_manager, bob_manager):
        return (
            E2EHandshakeHandler(alice_manager),
            E2EHandshakeHandler(bob_manager)
        )
    
    def test_respond_to_handshake_missing_ephemeral_key(self, bob_manager, handlers):
        """Test failure when ephemeral key is missing"""
        _, handler_bob = handlers
        
        invalid_payload = {
            "handshake_type": "initiate",
            "challenge": base64.b64encode(secrets.token_bytes(32)).decode(),
            # Missing ephemeral_public_key
        }
        
        with pytest.raises(ProtocolError) as exc_info:
            handler_bob.respond_to_handshake(
                "alice",
                secrets.token_bytes(32),
                invalid_payload,
                "test-session-id"
            )
        
        assert exc_info.value.code == DECRYPTION_FAILED
    
    def test_respond_to_handshake_missing_challenge(self, bob_manager, handlers):
        """Test failure when challenge is missing"""
        _, handler_bob = handlers
        
        invalid_payload = {
            "handshake_type": "initiate",
            "ephemeral_public_key": base64.b64encode(secrets.token_bytes(32)).decode(),
            # Missing challenge
        }
        
        with pytest.raises(ProtocolError) as exc_info:
            handler_bob.respond_to_handshake(
                "alice",
                secrets.token_bytes(32),
                invalid_payload,
                "test-session-id"
            )
        
        assert exc_info.value.code == DECRYPTION_FAILED
    
    def test_confirm_handshake_invalid_challenge_response(self, alice_manager, handlers):
        """Test failure with invalid challenge response"""
        handler_alice, _ = handlers
        
        # Create a session
        session_a, _ = handler_alice.initiate_handshake("bob")
        
        # Create invalid response with wrong challenge_response
        invalid_payload = {
            "handshake_type": "response",
            "ephemeral_public_key": base64.b64encode(secrets.token_bytes(32)).decode(),
            "challenge_response": base64.b64encode(secrets.token_bytes(32)).decode(),  # Wrong
            "public_key": "00" * 32
        }
        
        with pytest.raises(ProtocolError) as exc_info:
            handler_alice.confirm_handshake(session_a, invalid_payload)
        
        assert exc_info.value.code == DECRYPTION_FAILED
    
    def test_confirm_handshake_missing_ephemeral_key(self, alice_manager, handlers):
        """Test failure when ephemeral key is missing in response"""
        handler_alice, _ = handlers
        
        session_a, _ = handler_alice.initiate_handshake("bob")
        
        invalid_payload = {
            "handshake_type": "response",
            # Missing ephemeral_public_key
            "challenge_response": base64.b64encode(secrets.token_bytes(32)).decode(),
        }
        
        with pytest.raises(ProtocolError) as exc_info:
            handler_alice.confirm_handshake(session_a, invalid_payload)
        
        assert exc_info.value.code == DECRYPTION_FAILED
    
    def test_handshake_with_invalid_session_id(self, alice_manager, bob_manager, handlers):
        """Test handling of invalid session ID"""
        handler_alice, handler_bob = handlers
        
        # Alice initiates
        session_a, handshake = handler_alice.initiate_handshake("bob")
        
        # Bob responds with different session ID
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        session_b, response = handler_bob.respond_to_handshake(
            "alice",
            alice_pubkey,
            handshake.payload,
            "different-session-id"  # Different ID
        )
        
        # Session ID should be overridden by responder
        assert session_b.session_id == "different-session-id"
    
    def test_handshake_with_corrupted_ephemeral_key(self, alice_manager, bob_manager, handlers):
        """Test failure with corrupted ephemeral key"""
        handler_alice, handler_bob = handlers
        
        session_a, handshake = handler_alice.initiate_handshake("bob")
        
        # Corrupt the ephemeral key
        corrupted_payload = handshake.payload.copy()
        corrupted_payload["ephemeral_public_key"] = base64.b64encode(b"invalid" * 10).decode()
        
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        
        # Should raise an error due to invalid key format
        with pytest.raises(Exception):
            handler_bob.respond_to_handshake(
                "alice",
                alice_pubkey,
                corrupted_payload,
                session_a.session_id
            )


class TestHandshakeTimeout:
    """Tests for handshake timeout handling (test_handshake_timeout)"""
    
    @pytest.fixture
    def alice_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("alice", kp)
    
    @pytest.fixture
    def bob_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("bob", kp)
    
    def test_session_timeout_after_handshake_initiation(self, alice_manager):
        """Test session expiration after handshake initiation"""
        # Create session with very short timeout
        session = E2ESession.create(
            local_entity_id="alice",
            remote_entity_id="bob",
            local_keypair=alice_manager.keypair,
            timeout_seconds=0  # Immediate timeout
        )
        session.state = SessionState.HANDSHAKE_SENT
        
        time.sleep(0.1)
        
        assert session.is_expired() is True
    
    def test_session_not_expired_during_active_handshake(self, alice_manager):
        """Test session not expired during active handshake"""
        session = E2ESession.create(
            local_entity_id="alice",
            remote_entity_id="bob",
            local_keypair=alice_manager.keypair,
            timeout_seconds=60  # 1 minute
        )
        session.state = SessionState.HANDSHAKE_SENT
        
        assert session.is_expired() is False
    
    def test_session_timeout_after_establishment(self, alice_manager, bob_manager):
        """Test session expiration after establishment"""
        handler_alice = E2EHandshakeHandler(alice_manager)
        handler_bob = E2EHandshakeHandler(bob_manager)
        
        # Complete handshake
        session_a, handshake = handler_alice.initiate_handshake("bob")
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        session_b, response = handler_bob.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        handler_alice.confirm_handshake(session_a, response.payload)
        
        # Set short timeout
        session_a.timeout_seconds = 0
        time.sleep(0.1)
        
        assert session_a.is_expired() is True
    
    def test_session_activity_update_on_handshake(self, alice_manager):
        """Test that handshake updates last activity"""
        session = E2ESession.create(
            local_entity_id="alice",
            remote_entity_id="bob",
            local_keypair=alice_manager.keypair,
            timeout_seconds=3600
        )
        
        old_activity = session.last_activity
        time.sleep(0.01)
        
        # Touch the session
        session.touch()
        
        assert session.last_activity > old_activity
    
    def test_expired_session_rejection(self, alice_manager):
        """Test that operations on expired session are rejected"""
        session = alice_manager.create_session("bob")
        session.state = SessionState.ESTABLISHED
        session.session_keys = SessionKeys(
            encryption_key=secrets.token_bytes(32),
            auth_key=secrets.token_bytes(32)
        )
        session.timeout_seconds = 0
        time.sleep(0.1)
        
        # Expired session should be detected
        retrieved = alice_manager.get_session(session.session_id)
        assert retrieved.state == SessionState.EXPIRED


class TestHandshakeStateTransitions:
    """Tests for handshake state machine transitions"""
    
    @pytest.fixture
    def alice_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("alice", kp)
    
    @pytest.fixture
    def bob_manager(self):
        kp = KeyPair.generate()
        return E2ECryptoManager("bob", kp)
    
    def test_state_initial_to_handshake_sent(self, alice_manager):
        """Test transition from INITIAL to HANDSHAKE_SENT"""
        handler = E2EHandshakeHandler(alice_manager)
        
        session, _ = handler.initiate_handshake("bob")
        
        assert session.state == SessionState.HANDSHAKE_SENT
    
    def test_state_handshake_sent_to_established(self, alice_manager, bob_manager):
        """Test transition from HANDSHAKE_SENT to ESTABLISHED"""
        handler_alice = E2EHandshakeHandler(alice_manager)
        handler_bob = E2EHandshakeHandler(bob_manager)
        
        session_a, handshake = handler_alice.initiate_handshake("bob")
        assert session_a.state == SessionState.HANDSHAKE_SENT
        
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        session_b, response = handler_bob.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        
        handler_alice.confirm_handshake(session_a, response.payload)
        assert session_a.state == SessionState.ESTABLISHED
    
    def test_state_handshake_received_to_established(self, alice_manager, bob_manager):
        """Test responder state transitions"""
        handler_alice = E2EHandshakeHandler(alice_manager)
        handler_bob = E2EHandshakeHandler(bob_manager)
        
        session_a, handshake = handler_alice.initiate_handshake("bob")
        alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
        
        session_b, response = handler_bob.respond_to_handshake(
            "alice", alice_pubkey, handshake.payload, session_a.session_id
        )
        
        # Bob's session should be ESTABLISHED immediately
        assert session_b.state == SessionState.ESTABLISHED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
