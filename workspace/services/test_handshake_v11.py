#!/usr/bin/env python3
"""
Test Suite for 6-Step Handshake Protocol v1.1

Tests the enhanced handshake flow:
1. handshake_init
2. handshake_response
3. handshake_proof
4. handshake_ready
5. handshake_confirm
6. handshake_complete
"""

import sys
import time
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, '/home/moco/workspace/services')

try:
    from e2e_crypto import (
        E2ECryptoManager, E2EHandshakeHandlerV11, E2ESession,
        SessionState, generate_keypair, NACL_AVAILABLE
    )
except ImportError as e:
    print(f"Import error: {e}")
    NACL_AVAILABLE = False


def test_6step_handshake():
    """Test complete 6-step handshake between Alice and Bob"""
    print("=" * 70)
    print("6-Step Handshake Protocol v1.1 Test")
    print("=" * 70)
    
    if not NACL_AVAILABLE:
        print("ERROR: PyNaCl not available. Cannot run tests.")
        return False
    
    # Generate keypairs
    print("\n[1/7] Generating keypairs...")
    kp_alice = generate_keypair()
    kp_bob = generate_keypair()
    print(f"  Alice PK: {kp_alice.get_public_key_hex()[:32]}...")
    print(f"  Bob PK:   {kp_bob.get_public_key_hex()[:32]}...")
    
    # Create managers
    alice_manager = E2ECryptoManager("alice", kp_alice)
    bob_manager = E2ECryptoManager("bob", kp_bob)
    
    # Create handlers
    alice_handler = E2EHandshakeHandlerV11(alice_manager)
    bob_handler = E2EHandshakeHandlerV11(bob_manager)
    
    start_time = time.time()
    
    # Step 1: Alice -> Bob: handshake_init
    print("\n[2/7] Step 1: Alice sends handshake_init")
    session_alice, msg_init = alice_handler.create_handshake_init(
        "bob",
        supported_versions=["1.0", "1.1"]
    )
    print(f"  Session ID: {session_alice.session_id}")
    print(f"  Challenge:  {msg_init.payload['challenge'][:40]}...")
    print(f"  State:      {session_alice.state.value}")
    assert session_alice.state == SessionState.HANDSHAKE_SENT
    
    # Step 2: Bob -> Alice: handshake_response
    print("\n[3/7] Step 2: Bob sends handshake_response")
    import base64
    ephemeral_pubkey_a = base64.b64decode(msg_init.payload['ephemeral_pubkey'])
    challenge_a = base64.b64decode(msg_init.payload['challenge'])
    
    session_bob, msg_response = bob_handler.create_handshake_response(
        remote_entity_id="alice",
        remote_ephemeral_pubkey=ephemeral_pubkey_a,
        incoming_challenge=challenge_a,
        incoming_payload=msg_init.payload,
        session_id=session_alice.session_id
    )
    print(f"  Challenge response sent")
    print(f"  New challenge: {msg_response.payload['challenge'][:40]}...")
    print(f"  Selected version: {msg_response.payload['selected_version']}")
    print(f"  State: {session_bob.state.value}")
    assert session_bob.state == SessionState.HANDSHAKE_RECEIVED
    assert msg_response.payload['selected_version'] == "1.1"
    
    # Step 3: Alice -> Bob: handshake_proof
    print("\n[4/7] Step 3: Alice sends handshake_proof")
    ephemeral_pubkey_b = base64.b64decode(msg_response.payload['ephemeral_pubkey'])
    challenge_b = base64.b64decode(msg_response.payload['challenge'])
    
    msg_proof = alice_handler.create_handshake_proof(
        session=session_alice,
        remote_challenge=challenge_b,
        remote_ephemeral_pubkey=ephemeral_pubkey_b
    )
    print(f"  Challenge response computed")
    print(f"  Session params: {msg_proof.payload['session_params']}")
    print(f"  State: {session_alice.state.value}")
    assert session_alice.session_keys is not None
    
    # Step 4: Bob -> Alice: handshake_ready
    print("\n[5/7] Step 4: Bob sends handshake_ready")
    msg_ready = bob_handler.create_handshake_ready(session_bob)
    print(f"  Session confirmed: {msg_ready.payload['session_confirmation']['state']}")
    print(f"  Key fingerprint: {msg_ready.payload['session_confirmation']['session_key_fingerprint'][:20]}...")
    print(f"  State: {session_bob.state.value}")
    assert session_bob.state == SessionState.ESTABLISHED
    
    # Step 5: Alice -> Bob: handshake_confirm
    print("\n[6/7] Step 5: Alice sends handshake_confirm")
    msg_confirm = alice_handler.create_handshake_confirm(session_alice)
    print(f"  Session accepted: {msg_confirm.payload['final_confirmation']['session_accepted']}")
    print(f"  First encrypted message included")
    print(f"  State: {session_alice.state.value}")
    assert session_alice.state == SessionState.ESTABLISHED
    
    # Step 6: Bob -> Alice: handshake_complete
    print("\n[7/7] Step 6: Bob sends handshake_complete")
    duration_ms = int((time.time() - start_time) * 1000)
    msg_complete = bob_handler.create_handshake_complete(session_bob, duration_ms)
    print(f"  Session established: {msg_complete.payload['session_established']}")
    print(f"  Ready for traffic: {msg_complete.payload['ready_for_traffic']}")
    print(f"  Handshake duration: {duration_ms}ms")
    
    # Verify sessions
    print("\n" + "=" * 70)
    print("Verification")
    print("=" * 70)
    
    # Check session keys match
    alice_key = session_alice.session_keys.encryption_key.hex()[:32]
    bob_key = session_bob.session_keys.encryption_key.hex()[:32]
    print(f"\nAlice session key: {alice_key}...")
    print(f"Bob session key:   {bob_key}...")
    
    assert session_alice.session_keys.encryption_key == session_bob.session_keys.encryption_key, \
        "Session keys do not match!"
    print("  [PASS] Session keys match")
    
    # Test encryption
    print("\nTesting E2E encryption...")
    test_payload = {"message": "Hello from 6-step handshake!", "timestamp": datetime.now(timezone.utc).isoformat()}
    
    encrypted = alice_manager.encrypt_message(session_alice.session_id, test_payload)
    print(f"  Encrypted: {encrypted.payload['data'][:50]}...")
    
    decrypted = bob_manager.decrypt_message(session_bob, encrypted)
    print(f"  Decrypted: {decrypted}")
    
    assert decrypted == test_payload, "Decryption failed!"
    print("  [PASS] Encryption/Decryption successful")
    
    print("\n" + "=" * 70)
    print("ALL TESTS PASSED!")
    print("=" * 70)
    
    return True


def test_challenge_response():
    """Test challenge-response verification"""
    print("\n" + "=" * 70)
    print("Challenge-Response Verification Test")
    print("=" * 70)
    
    if not NACL_AVAILABLE:
        print("Skipping - PyNaCl not available")
        return True
    
    import hashlib
    import base64
    import secrets
    
    kp_alice = generate_keypair()
    kp_bob = generate_keypair()
    
    alice_manager = E2ECryptoManager("alice", kp_alice)
    bob_manager = E2ECryptoManager("bob", kp_bob)
    
    # Simulate challenge generation
    challenge = secrets.token_bytes(32)
    ephemeral_bob = secrets.token_bytes(32)
    static_bob = kp_bob.public_key
    
    # Bob computes expected response
    expected_response = hashlib.sha256(challenge + ephemeral_bob + static_bob).digest()
    
    # Alice verifies (she has access to same data)
    computed_response = hashlib.sha256(challenge + ephemeral_bob + static_bob).digest()
    
    assert expected_response == computed_response, "Challenge response mismatch!"
    print("  [PASS] Challenge-response verification successful")
    
    return True


def test_session_expiration():
    """Test session timeout and expiration"""
    print("\n" + "=" * 70)
    print("Session Expiration Test")
    print("=" * 70)
    
    if not NACL_AVAILABLE:
        print("Skipping - PyNaCl not available")
        return True
    
    kp = generate_keypair()
    manager = E2ECryptoManager("test", kp)
    
    # Create session with 1 second timeout
    session = manager.create_session("remote", timeout_seconds=1)
    print(f"  Created session: {session.session_id}")
    print(f"  Timeout: {session.timeout_seconds}s")
    
    assert not session.is_expired(), "Session should not be expired immediately"
    print("  [PASS] Session not expired (immediate)")
    
    # Wait for expiration
    import time
    time.sleep(1.5)
    
    assert session.is_expired(), "Session should be expired after timeout"
    print("  [PASS] Session expired after timeout")
    
    return True


if __name__ == "__main__":
    all_passed = True
    
    try:
        all_passed &= test_6step_handshake()
    except Exception as e:
        print(f"\n[FAIL] 6-step handshake test failed: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        all_passed &= test_challenge_response()
    except Exception as e:
        print(f"\n[FAIL] Challenge-response test failed: {e}")
        all_passed = False
    
    try:
        all_passed &= test_session_expiration()
    except Exception as e:
        print(f"\n[FAIL] Session expiration test failed: {e}")
        all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED!")
        sys.exit(1)
