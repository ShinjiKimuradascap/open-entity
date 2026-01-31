#!/usr/bin/env python3
"""
Security Integration Tests for Peer Communication Protocol v1.0
Tests Ed25519 signatures, replay protection, and peer management
"""

import unittest
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta

import pytest

# Test markers for CI categorization
pytestmark = [pytest.mark.unit, pytest.mark.security]

# Import modules to test
from crypto import (
    KeyPair, MessageSigner, SignatureVerifier, SecureMessage,
    ReplayProtector, generate_keypair, get_public_key_from_private
)
from auth import JWTAuth, APIKeyAuth, JWTConfig, CombinedAuth


class TestKeyPair(unittest.TestCase):
    """Test Ed25519 key pair generation and loading"""
    
    def test_generate_keypair(self):
        """Test key pair generation"""
        kp = generate_keypair()
        self.assertIsInstance(kp, KeyPair)
        self.assertEqual(len(kp.private_key), 32)  # PyNaCl returns 32 bytes (seed format)
        self.assertEqual(len(kp.public_key), 32)   # Ed25519 public key is 32 bytes
    
    def test_keypair_from_private(self):
        """Test loading key pair from private key"""
        kp1 = generate_keypair()
        kp2 = KeyPair.from_private_key(kp1.private_key)
        
        self.assertEqual(kp1.private_key, kp2.private_key)
        self.assertEqual(kp1.public_key, kp2.public_key)
    
    def test_hex_encoding(self):
        """Test hex encoding of keys"""
        kp = generate_keypair()
        
        private_hex = kp.get_private_key_hex()
        public_hex = kp.get_public_key_hex()
        
        self.assertEqual(len(private_hex), 64)  # 32 bytes * 2 (PyNaCl seed format)
        self.assertEqual(len(public_hex), 64)   # 32 bytes * 2
        
        # Test loading from hex
        kp2 = KeyPair.from_private_key_hex(private_hex)
        self.assertEqual(kp.public_key, kp2.public_key)


class TestMessageSigning(unittest.TestCase):
    """Test Ed25519 message signing and verification"""
    
    def setUp(self):
        self.kp = generate_keypair()
        self.signer = MessageSigner(self.kp)
        self.verifier = SignatureVerifier()
        self.verifier.add_public_key("test-entity", self.kp.public_key)
    
    def test_sign_and_verify_message(self):
        """Test signing and verifying a message"""
        message = {
            "type": "test",
            "data": "hello world",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Sign
        signature = self.signer.sign_message(message)
        self.assertIsInstance(signature, str)
        
        # Verify
        is_valid = self.verifier.verify_message(message, signature, "test-entity")
        self.assertTrue(is_valid)
    
    def test_verify_wrong_signature(self):
        """Test that wrong signature fails verification"""
        message = {"type": "test", "data": "hello"}
        
        # Sign with one key
        signature = self.signer.sign_message(message)
        
        # Create different key
        other_kp = generate_keypair()
        other_verifier = SignatureVerifier()
        other_verifier.add_public_key("other-entity", other_kp.public_key)
        
        # Verification with wrong key should return False (not raise ValueError)
        is_valid = other_verifier.verify_message(message, signature, "other-entity")
        self.assertFalse(is_valid)
    
    def test_tampered_message(self):
        """Test that tampered message fails verification"""
        message = {"type": "test", "data": "hello"}
        
        signature = self.signer.sign_message(message)
        
        # Tamper with message
        message["data"] = "tampered"
        
        # Verification should fail
        is_valid = self.verifier.verify_message(message, signature, "test-entity")
        self.assertFalse(is_valid)


class TestSecureMessage(unittest.TestCase):
    """Test SecureMessage class"""
    
    def setUp(self):
        self.kp = generate_keypair()
        self.signer = MessageSigner(self.kp)
    
    def test_secure_message_creation(self):
        """Test creating a secure message"""
        msg = SecureMessage(
            version="0.3",
            msg_type="test",
            sender_id="entity-1",
            payload={"data": "test"}
        )
        
        self.assertEqual(msg.version, "0.3")
        self.assertEqual(msg.msg_type, "test")
        self.assertEqual(msg.sender_id, "entity-1")
        self.assertIsNotNone(msg.timestamp)
        self.assertIsNotNone(msg.nonce)
        self.assertIsNone(msg.signature)
    
    def test_secure_message_signing(self):
        """Test signing a secure message"""
        msg = SecureMessage(
            version="0.3",
            msg_type="test",
            sender_id="entity-1",
            payload={"data": "test"}
        )
        
        msg.sign(self.signer)
        
        self.assertIsNotNone(msg.signature)
        self.assertIsInstance(msg.signature, str)
    
    def test_to_dict(self):
        """Test converting to dictionary"""
        msg = SecureMessage(
            version="0.3",
            msg_type="test",
            sender_id="entity-1",
            payload={"data": "test"}
        )
        msg.sign(self.signer)
        
        data = msg.to_dict()
        
        self.assertIn("version", data)
        self.assertIn("msg_type", data)
        self.assertIn("sender_id", data)
        self.assertIn("payload", data)
        self.assertIn("timestamp", data)
        self.assertIn("nonce", data)
        self.assertIn("signature", data)
    
    def test_from_dict(self):
        """Test creating from dictionary"""
        original = SecureMessage(
            version="0.3",
            msg_type="test",
            sender_id="entity-1",
            payload={"data": "test"}
        )
        original.sign(self.signer)
        
        data = original.to_dict()
        restored = SecureMessage.from_dict(data)
        
        self.assertEqual(restored.version, original.version)
        self.assertEqual(restored.msg_type, original.msg_type)
        self.assertEqual(restored.sender_id, original.sender_id)
        self.assertEqual(restored.signature, original.signature)


class TestReplayProtection(unittest.TestCase):
    """Test replay attack protection"""
    
    def setUp(self):
        self.protector = ReplayProtector(max_age_seconds=60)
    
    def test_valid_message(self):
        """Test that valid message passes"""
        nonce = "abc123"
        timestamp = datetime.now(timezone.utc).isoformat()
        
        is_valid, error = self.protector.is_valid(nonce, timestamp)
        
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_replay_detection(self):
        """Test that replay is detected"""
        nonce = "abc123"
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # First check passes
        is_valid, _ = self.protector.is_valid(nonce, timestamp)
        self.assertTrue(is_valid)
        
        # Second check fails (replay)
        is_valid, error = self.protector.is_valid(nonce, timestamp)
        self.assertFalse(is_valid)
        self.assertIn("replay", error.lower())
    
    def test_old_message_rejection(self):
        """Test that old messages are rejected"""
        nonce = "old123"
        old_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        
        is_valid, error = self.protector.is_valid(nonce, old_timestamp)
        
        self.assertFalse(is_valid)
        self.assertIn("too old", error.lower())
    
    def test_future_message_rejection(self):
        """Test that future messages are rejected"""
        nonce = "future123"
        future_timestamp = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
        
        is_valid, error = self.protector.is_valid(nonce, future_timestamp)
        
        self.assertFalse(is_valid)


class TestJWTAuth(unittest.TestCase):
    """Test JWT authentication"""
    
    def setUp(self):
        self.config = JWTConfig(secret="test-secret", expiry_minutes=5)
        self.auth = JWTAuth(self.config)
    
    def test_create_token(self):
        """Test JWT token creation"""
        token = self.auth.create_token("entity-1", {"role": "admin"})
        
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 0)
    
    def test_verify_token(self):
        """Test JWT token verification"""
        token = self.auth.create_token("entity-1", {"role": "admin"})
        
        payload = self.auth.verify_token(token)
        
        self.assertEqual(payload["sub"], "entity-1")
        self.assertEqual(payload["role"], "admin")
        self.assertIn("exp", payload)
        self.assertIn("iat", payload)
    
    def test_expired_token(self):
        """Test that expired token is rejected"""
        # Create token that expires immediately
        short_config = JWTConfig(secret="test-secret", expiry_minutes=-1)
        short_auth = JWTAuth(short_config)
        
        token = short_auth.create_token("entity-1")
        
        with self.assertRaises(ValueError) as context:
            short_auth.verify_token(token)
        
        self.assertIn("expired", str(context.exception).lower())
    
    def test_invalid_token(self):
        """Test that invalid token is rejected"""
        with self.assertRaises(ValueError):
            self.auth.verify_token("invalid.token.here")


class TestAPIKeyAuth(unittest.TestCase):
    """Test API key authentication"""
    
    def setUp(self):
        self.auth = APIKeyAuth()
    
    def test_generate_key(self):
        """Test API key generation"""
        key = self.auth.generate_key("entity-1")
        
        self.assertIsInstance(key, str)
        self.assertTrue(key.startswith("ak_"))
    
    def test_verify_key(self):
        """Test API key verification"""
        key = self.auth.generate_key("entity-1")
        
        entity_id = self.auth.verify_key(key)
        
        self.assertEqual(entity_id, "entity-1")
    
    def test_invalid_key(self):
        """Test that invalid key returns None"""
        result = self.auth.verify_key("invalid-key")
        
        self.assertIsNone(result)
    
    def test_key_not_reversible(self):
        """Test that key hash cannot be reversed"""
        key = self.auth.generate_key("entity-1")
        
        # The stored hash should not reveal the key
        stored_hash = self.auth._hash_key(key)
        self.assertNotEqual(stored_hash, key)


class TestCombinedAuth(unittest.TestCase):
    """Test combined authentication"""
    
    def setUp(self):
        self.jwt_auth = JWTAuth(JWTConfig(secret="test-secret"))
        self.api_auth = APIKeyAuth()
        self.combined = CombinedAuth(self.jwt_auth, self.api_auth)
    
    def test_authenticate_with_jwt(self):
        """Test authentication with JWT only"""
        token = self.jwt_auth.create_token("entity-1")
        
        result = self.combined.authenticate_request(token=token)
        
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["entity_id"], "entity-1")
        self.assertIn("jwt", result["methods"])
    
    def test_authenticate_with_api_key(self):
        """Test authentication with API key only"""
        api_key = self.api_auth.generate_key("entity-1")
        
        result = self.combined.authenticate_request(api_key=api_key)
        
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["entity_id"], "entity-1")
        self.assertIn("api_key", result["methods"])
    
    def test_authenticate_with_both(self):
        """Test authentication with both JWT and API key"""
        token = self.jwt_auth.create_token("entity-1")
        api_key = self.api_auth.generate_key("entity-1")
        
        result = self.combined.authenticate_request(token=token, api_key=api_key)
        
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["entity_id"], "entity-1")
        self.assertIn("jwt", result["methods"])
        self.assertIn("api_key", result["methods"])
    
    def test_authenticate_no_credentials(self):
        """Test authentication with no credentials"""
        result = self.combined.authenticate_request()
        
        self.assertFalse(result["authenticated"])
        self.assertIsNone(result["entity_id"])


class TestIntegration(unittest.TestCase):
    """Integration tests for full security flow"""
    
    def test_full_message_flow(self):
        """Test full message signing and verification flow"""
        # Create sender keys
        sender_kp = generate_keypair()
        sender_signer = MessageSigner(sender_kp)
        
        # Create receiver (verifier)
        receiver_verifier = SignatureVerifier()
        receiver_verifier.add_public_key("sender-1", sender_kp.public_key)
        
        # Create replay protector
        protector = ReplayProtector(max_age_seconds=60)
        
        # Create and sign message
        msg = SecureMessage(
            version="0.3",
            msg_type="test",
            sender_id="sender-1",
            payload={"action": "do_something", "params": {"key": "value"}}
        )
        msg.sign(sender_signer)
        
        # Verify replay protection
        is_valid, error = protector.is_valid(msg.nonce, msg.timestamp)
        self.assertTrue(is_valid)
        
        # Verify signature
        is_valid = receiver_verifier.verify_message(
            msg.get_signable_data(),
            msg.signature,
            "sender-1"
        )
        self.assertTrue(is_valid)
    
    def test_end_to_end_auth(self):
        """Test end-to-end authentication flow"""
        # Server creates JWT for client
        server_jwt = JWTAuth(JWTConfig(secret="server-secret"))
        token = server_jwt.create_token("client-1", {"permissions": ["read", "write"]})
        
        # Client uses token
        client_auth = JWTAuth(JWTConfig(secret="server-secret"))
        payload = client_auth.verify_token(token)
        
        self.assertEqual(payload["sub"], "client-1")
        self.assertEqual(payload["permissions"], ["read", "write"])


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestKeyPair))
    suite.addTests(loader.loadTestsFromTestCase(TestMessageSigning))
    suite.addTests(loader.loadTestsFromTestCase(TestSecureMessage))
    suite.addTests(loader.loadTestsFromTestCase(TestReplayProtection))
    suite.addTests(loader.loadTestsFromTestCase(TestJWTAuth))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIKeyAuth))
    suite.addTests(loader.loadTestsFromTestCase(TestCombinedAuth))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
