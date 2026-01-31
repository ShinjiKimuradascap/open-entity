#!/usr/bin/env python3
"""Encryption test debug script - S12 verification"""
import sys
sys.path.insert(0, '/home/moco/workspace')

from services.crypto import CryptoManager, generate_entity_keypair

print("=" * 60)
print("S12: X25519 Auto-Key Generation Test")
print("=" * 60)

# Generate keypairs for Entity A and B
priv_a, pub_a = generate_entity_keypair()
priv_b, pub_b = generate_entity_keypair()

# Create CryptoManagers
crypto_a = CryptoManager('entity-a', priv_a)
crypto_b = CryptoManager('entity-b', priv_b)

# Get X25519 public keys (should auto-generate now)
x25519_a = crypto_a.get_x25519_public_key_b64()
x25519_b = crypto_b.get_x25519_public_key_b64()

print(f"Entity A X25519: {x25519_a[:30]}...")
print(f"Entity B X25519: {x25519_b[:30]}...")

if x25519_a and x25519_b:
    print("✅ X25519 keys auto-generated successfully!")
else:
    print("❌ X25519 key generation failed!")
    sys.exit(1)

# Test encrypted message
payload = {'api_key': 'sk-1234567890abcdef', 'action': 'test'}
try:
    msg = crypto_a.create_secure_message(
        payload,
        encrypt=True,
        peer_public_key_b64=x25519_b,
        peer_id='entity-b'
    )
    print(f"✅ Encrypted message created")
    
    # Decrypt test
    result = crypto_b.verify_and_decrypt_message(msg, peer_id='entity-a')
    
    if result and result.get('data', {}).get('api_key') == 'sk-1234567890abcdef':
        print(f"✅ Decryption successful: {result['data']}")
        print("\n" + "=" * 60)
        print("S12: ALL TESTS PASSED!")
        print("=" * 60)
    else:
        print(f"❌ Decryption failed or data mismatch: {result}")
        sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
