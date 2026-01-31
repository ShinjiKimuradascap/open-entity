# E2EEncryption Integration Design
## peer_service.py Encryption Integration

## Current Status

### Existing Components
1. **crypto.py::E2EEncryption** (line 1070+)
   - X25519 + HKDF-SHA256 + AES-256-GCM
   - Ed25519 to X25519 key conversion
   - Shared key derivation & caching

2. **crypto_utils.py::CryptoManager** (line 76+)
   - Ed25519 signatures
   - X25519 key exchange + AES-256-GCM encryption
   - JWT authentication (5min expiry)
   - Replay attack prevention
   - High-level API: create_secure_message() / verify_and_decrypt_message()

3. **peer_service.py** (current)
   - Ed25519 signatures only
   - Handshake: capability exchange
   - Message sending: signatures only

## Integration Strategy: CryptoManager Full Integration

### Benefits
- Production-ready high-level API
- Includes JWT auth & replay protection
- Already tested implementation

### Integration Points
1. PeerService.__init__() - Initialize CryptoManager
2. Handshake - Exchange encryption capabilities
3. send_message() - Add encrypt option
4. Message receive - Auto-decrypt

## Implementation Tasks
- S2.1: CryptoManager integration design - DONE
- S2.2: peer_service.py modifications - NEXT
- S2.3: Handshake encryption negotiation
- S2.4: Integration tests

## Design Decisions
- Use CryptoManager (reuse existing implementation)
- Backward compatible (encryption is optional)
- Automatic key exchange during handshake
- JWT for session authentication
