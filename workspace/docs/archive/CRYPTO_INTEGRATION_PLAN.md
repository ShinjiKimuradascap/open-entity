# Crypto Module Integration Plan

## Current State

### Three Crypto Modules
1. **crypto.py** (2,263 lines)
   - PyNaCl-based implementation
   - Protocol v1.0 compliant
   - Extensive class hierarchy: KeyPair, MessageSigner, SignatureVerifier, etc.
   - Already partially wrapperized - imports from crypto_utils

2. **crypto_utils.py** (1,006 lines)
   - cryptography library-based
   - Modern, well-maintained implementation
   - CryptoManager class with all necessary features
   - JWT support

3. **e2e_crypto.py** (849 lines)
   - E2E encryption layer
   - Depends on crypto.py
   - Session management

## Problem: Library Mismatch

- crypto.py uses PyNaCl (libsodium bindings)
- crypto_utils.py uses cryptography (OpenSSL bindings)
- Key formats are NOT directly compatible

## Integration Strategy

### Phase 1: Maintain Compatibility (Current)
- crypto.py acts as compatibility layer
- Wraps crypto_utils.CryptoManager
- Maintains old API surface

### Phase 2: Gradual Migration
1. Update all imports to use crypto_utils directly
2. Provide conversion utilities for key formats if needed
3. Deprecate crypto.py classes with warnings

### Phase 3: Cleanup
- Remove crypto.py
- Rename crypto_utils.py to crypto.py (optional)
- Update all imports

## Key Format Compatibility

### Ed25519 Private Key
- PyNaCl: 64-byte expanded format
- cryptography: 32-byte seed only

## Recommendation

Keep both libraries during transition:
1. New code uses crypto_utils.py (cryptography)
2. Old code continues using crypto.py (wrapper)
3. Eventually migrate all to cryptography

## Files to Update

Import crypto.py (Legacy):
- auth.py, test_security.py, test_api_server.py
- e2e_crypto.py, api_server.py, peer_service.py

Already Use crypto_utils.py (Modern):
- test_peer_service.py, test_crypto_integration.py
