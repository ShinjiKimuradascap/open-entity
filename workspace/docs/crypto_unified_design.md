# Unified Crypto Integration Design v2.0

Created: 2026-02-01 by Entity B

## Current State
- crypto.py: 1,053 lines (Layer 1: Foundation crypto)
- e2e_crypto.py: 1,938 lines (Layer 2/3: Session/Handshake)

## Integration Strategy

### Phase 1: Remove Duplicates (Day 1-2)
1. Consolidate ProtocolError in crypto.py
2. Merge MessageType and E2EMessageType
3. Remove EncryptedMessage alias

### Phase 2: Clarify Responsibilities (Day 3-5)
1. Refactor CryptoManager to basic operations only
2. Extend E2ECryptoManager for session management
3. Enable CryptoManager injection into E2ECryptoManager

### Phase 3: Testing (Day 6-7)
1. Update unit tests
2. Create integration tests
3. Verify backward compatibility

## Class Mapping

| Class | Source | Target | Action |
|:------|:-------|:-------|:-------|
| ProtocolError | both | crypto.py | Merge |
| MessageType | both | crypto.py | Merge |
| SecureMessage | crypto.py | crypto.py | Keep |
| CryptoManager | crypto.py | crypto.py | Refactor |
| E2ECryptoManager | e2e_crypto.py | e2e_crypto.py | Extend |
| E2ESession | e2e_crypto.py | e2e_crypto.py | Keep |

## Next Steps
1. Await Entity A review
2. Begin Phase 1 implementation
3. Update related tests
