# Peer Communication Protocol Implementation Guide v1.0

## Overview
AIエンティティ間の安全な通信プロトコル実装ガイド

## Cryptographic Specifications

### Required (v1.0)

#### Ed25519 Signatures
- Message serialization: JSON with sorted keys, no whitespace
- Signing: Ed25519 private key
- Encoding: Base64
- All messages MUST be signed

#### Replay Protection
- Timestamp: ISO8601 UTC with ±60 seconds tolerance
- Nonce: 128-bit (32 hex chars), uniqueness check required
- Replay detection window: 5 minutes

### Recommended (v1.1+)

#### X25519 + AES-256-GCM Encryption
- Key exchange: X25519 ECDH
- Key derivation: HKDF-SHA256
- Encryption: AES-256-GCM with 128-bit random nonce
- Note: End-to-end encryption planned for v1.1

## Security Requirements
- Timestamp tolerance: ±60 seconds
- Nonce size: 128-bit
- Replay detection window: 5 minutes
- Session management with UUID v4
- Sequence numbers for message ordering

## Required Checks
1. Timestamp validation
2. Nonce uniqueness check
3. Ed25519 signature verification (required for all messages)
4. Version compatibility check
5. Session validation (when session_id provided)

## Reference Implementation
Python: services/crypto_utils.py
- CryptoManager class
- SecureMessage dataclass

## Implementation Checklist

### v1.0 Required ✅
- [x] Ed25519 keypair generation
- [x] Message signing
- [x] Signature verification
- [x] Timestamp validation
- [x] Nonce generation and duplicate detection
- [x] Capability exchange (capability_query/response)
- [x] Task delegation with queue
- [x] Heartbeat with health monitoring
- [x] Peer statistics tracking
- [x] Integration tests

### v1.1 Recommended 📋
- [ ] X25519 keypair generation
- [ ] X25519 key exchange
- [ ] HKDF key derivation
- [ ] AES-256-GCM encryption/decryption
- [ ] Payload encryption for sensitive data
- [ ] Connection pooling optimization
- [ ] Rate limiting per peer

---
Created: 2026-01-31
