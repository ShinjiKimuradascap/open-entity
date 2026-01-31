# Crypto Integration Design

## Duplication Analysis

crypto.py and e2e_crypto.py both implement:
- X25519 key exchange
- AES-256-GCM encryption

## Integration Strategy

Phase 1: Create crypto_core.py with shared primitives
Phase 2: Refactor crypto.py to use crypto_core
Phase 3: Refactor e2e_crypto.py to use crypto_core
Phase 4: Deprecate duplicate code

## Timeline: 4 days

Created: 2026-02-01
