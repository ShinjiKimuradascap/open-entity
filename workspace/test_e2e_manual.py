#!/usr/bin/env python3
"""
E2E暗号化の動作確認テスト（pytest不要）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

import secrets
import base64
from datetime import datetime, timezone, timedelta

try:
    from nacl.public import PrivateKey, PublicKey, Box
    from nacl.secret import SecretBox
    NACL_AVAILABLE = True
    print("✓ PyNaCl available")
except ImportError as e:
    NACL_AVAILABLE = False
    print(f"✗ PyNaCl not available: {e}")
    sys.exit(1)

try:
    from crypto import KeyPair, MessageSigner, SignatureVerifier, ProtocolError
    from e2e_crypto import (
        SessionState, SessionKeys, E2ESession,
        E2ECryptoManager, E2EHandshakeHandler,
        generate_keypair, create_e2e_manager
    )
    print("✓ crypto and e2e_crypto modules imported")
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)


def test_key_derivation():
    """Test HKDF-like key derivation"""
    print("\n--- Test: Key Derivation ---")
    shared_secret = secrets.token_bytes(32)
    keys = SessionKeys.derive_from_shared_secret(shared_secret)
    
    assert len(keys.encryption_key) == 32, "Encryption key must be 32 bytes"
    assert len(keys.auth_key) == 32, "Auth key must be 32 bytes"
    assert keys.encryption_key != keys.auth_key, "Keys must be different"
    
    # Deterministic
    keys2 = SessionKeys.derive_from_shared_secret(shared_secret)
    assert keys.encryption_key == keys2.encryption_key, "Must be deterministic"
    
    print("✓ Key derivation works correctly")


def test_session_creation():
    """Test session creation"""
    print("\n--- Test: Session Creation ---")
    keypair = KeyPair.generate()
    session = E2ESession.create(
        local_entity_id="alice",
        remote_entity_id="bob",
        local_keypair=keypair,
        timeout_seconds=3600
    )
    
    # UUID v4 format
    assert len(session.session_id) == 36, "Must be UUID format"
    assert session.session_id[14] == '4', "Must be version 4"
    
    assert session.local_entity_id == "alice"
    assert session.remote_entity_id == "bob"
    assert session.state == SessionState.INITIAL
    
    # Ephemeral keys
    assert session.ephemeral_public_key is not None
    assert len(session.ephemeral_public_key) == 32
    
    print(f"✓ Session created: {session.session_id}")


def test_encryption_decryption():
    """Test encrypt/decrypt roundtrip"""
    print("\n--- Test: Encryption/Decryption ---")
    
    # Create two managers
    alice = create_e2e_manager("alice")
    bob = create_e2e_manager("bob")
    
    # Alice creates session
    alice_session = alice.create_session("bob")
    
    # Simulate handshake - manually derive shared secret
    alice_ephemeral = PrivateKey(alice_session.ephemeral_private_key)
    bob_ephemeral = PrivateKey.generate()
    
    # Alice derives shared secret
    bob_public = bob_ephemeral.public_key
    box_alice = Box(alice_ephemeral, bob_public)
    
    # Bob derives shared secret
    alice_public = PublicKey(alice_session.ephemeral_public_key)
    box_bob = Box(bob_ephemeral, alice_public)
    
    # Both should derive same shared secret
    shared_secret_alice = box_alice.shared_key()
    shared_secret_bob = box_bob.shared_key()
    
    assert shared_secret_alice == shared_secret_bob, "Shared secrets must match"
    
    # Encrypt with SecretBox
    secret_box = SecretBox(shared_secret_alice)
    plaintext = b"Hello, E2E Encryption!"
    encrypted = secret_box.encrypt(plaintext)
    
    # Decrypt
    decrypted = secret_box.decrypt(encrypted)
    assert decrypted == plaintext, "Decryption must match original"
    
    print("✓ Encryption/decryption roundtrip successful")


def test_session_expiration():
    """Test session expiration"""
    print("\n--- Test: Session Expiration ---")
    
    keypair = KeyPair.generate()
    session = E2ESession.create(
        local_entity_id="alice",
        remote_entity_id="bob",
        local_keypair=keypair,
        timeout_seconds=1  # 1 second for testing
    )
    
    assert not session.is_expired()
    
    import time
    time.sleep(1.5)
    
    assert session.is_expired(), "Session should be expired"
    print("✓ Session expiration works")


def test_sequence_numbers():
    """Test sequence number tracking"""
    print("\n--- Test: Sequence Numbers ---")
    
    keypair = KeyPair.generate()
    session = E2ESession.create(
        local_entity_id="alice",
        remote_entity_id="bob",
        local_keypair=keypair
    )
    
    # Initial sequence
    seq1 = session.next_sequence_number()
    seq2 = session.next_sequence_number()
    
    assert seq2 == seq1 + 1, "Sequence must increment"
    
    # Record received sequence
    session.record_received_sequence(1)
    session.record_received_sequence(2)
    
    assert session.highest_received_sequence == 2
    assert 1 in session.received_sequences
    assert 2 in session.received_sequences
    
    print("✓ Sequence numbers work correctly")


def test_manager_session_operations():
    """Test E2ECryptoManager session operations"""
    print("\n--- Test: Manager Session Operations ---")
    
    manager = create_e2e_manager("test_entity")
    
    # Create session
    session = manager.create_session("peer")
    assert session.session_id in manager.sessions
    
    # Get session
    retrieved = manager.get_session(session.session_id)
    assert retrieved == session
    
    # Close session
    manager.close_session(session.session_id)
    assert session.session_id not in manager.sessions
    
    print("✓ Manager session operations work")


def run_all_tests():
    """Run all tests"""
    print("=" * 50)
    print("E2E Encryption Manual Tests")
    print("=" * 50)
    
    tests = [
        test_key_derivation,
        test_session_creation,
        test_encryption_decryption,
        test_session_expiration,
        test_sequence_numbers,
        test_manager_session_operations,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
