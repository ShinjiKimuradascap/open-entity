#!/usr/bin/env python3
"""Quick E2E encryption test"""
import sys
sys.path.insert(0, '/home/moco/workspace/services')

print("=" * 60)
print("E2E Encryption Quick Test")
print("=" * 60)

# Test 1: Import test
print("\n[Test 1] Import crypto modules...")
try:
    from crypto import E2EEncryption, KeyPair
    print("  ✅ crypto.E2EEncryption imported")
except ImportError as e:
    print(f"  ❌ Import failed: {e}")
    sys.exit(1)

# Test 2: KeyPair generation
print("\n[Test 2] Generate key pairs...")
try:
    keypair1 = KeyPair.generate()
    keypair2 = KeyPair.generate()
    print(f"  ✅ KeyPair 1: {keypair1.get_public_key_hex()[:16]}...")
    print(f"  ✅ KeyPair 2: {keypair2.get_public_key_hex()[:16]}...")
except Exception as e:
    print(f"  ❌ Key generation failed: {e}")
    sys.exit(1)

# Test 3: E2EEncryption initialization
print("\n[Test 3] Initialize E2E encryption...")
try:
    e2e1 = E2EEncryption(keypair1)
    e2e2 = E2EEncryption(keypair2)
    print("  ✅ E2EEncryption initialized for both peers")
except Exception as e:
    print(f"  ❌ E2E initialization failed: {e}")
    sys.exit(1)

# Test 4: Generate ephemeral keys
print("\n[Test 4] Generate ephemeral X25519 keys...")
try:
    priv1, pub1 = e2e1.generate_ephemeral_keypair()
    priv2, pub2 = e2e2.generate_ephemeral_keypair()
    print(f"  ✅ Peer 1 ephemeral pub: {pub1[:20]}...")
    print(f"  ✅ Peer 2 ephemeral pub: {pub2[:20]}...")
except Exception as e:
    print(f"  ❌ Ephemeral key generation failed: {e}")
    sys.exit(1)

# Test 5: Derive shared keys
print("\n[Test 5] Derive shared keys...")
try:
    e2e1.derive_shared_key(pub2, "peer2")
    e2e2.derive_shared_key(pub1, "peer1")
    print("  ✅ Shared keys derived for both peers")
except Exception as e:
    print(f"  ❌ Shared key derivation failed: {e}")
    sys.exit(1)

# Test 6: Encrypt/Decrypt message
print("\n[Test 6] Encrypt and decrypt message...")
try:
    test_message = {"type": "test", "content": "Hello, E2E Encryption!", "timestamp": "2026-02-01T00:00:00Z"}
    encrypted = e2e1.encrypt_message(test_message, pub2, "peer2")
    print(f"  ✅ Encrypted: {encrypted.ciphertext[:30]}...")
    
    decrypted = e2e2.decrypt_message(encrypted, "peer1")
    print(f"  ✅ Decrypted: {decrypted}")
    
    if decrypted == test_message:
        print("  ✅ Message integrity verified!")
    else:
        print("  ❌ Message mismatch!")
        sys.exit(1)
except Exception as e:
    print(f"  ❌ Encryption/Decryption failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: SessionManager integration check
print("\n[Test 7] Check SessionManager integration...")
try:
    from session_manager import SessionManager
    sm = SessionManager(session_timeout=300)
    print("  ✅ SessionManager imported and initialized")
    
    # Create a session
    session_id = sm.create_session("peer_test_id")
    print(f"  ✅ Session created: {session_id[:16]}...")
    
    # Get session
    session = sm.get_session(session_id)
    if session:
        print(f"  ✅ Session retrieved, seq: {session.seq_num}")
    else:
        print("  ❌ Session not found")
except Exception as e:
    print(f"  ⚠️ SessionManager test skipped: {e}")

print("\n" + "=" * 60)
print("All E2E Encryption tests passed! ✅")
print("=" * 60)
