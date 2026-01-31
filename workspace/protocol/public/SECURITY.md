# Security Guide

## Cryptographic Requirements

### Ed25519 Signatures
- All messages MUST be signed with Ed25519
- Public keys are 32 bytes, signatures are 64 bytes
- Use deterministic signatures for reproducibility

### X25519 Key Exchange
- ECDH for session key derivation
- Combine with HKDF-SHA256 for key derivation
- Rotate session keys every 24 hours

### AES-256-GCM Encryption
- 256-bit keys derived from X25519 shared secret
- 128-bit random nonce per message
- 128-bit authentication tag

## Replay Protection
- Timestamp tolerance: +/- 60 seconds
- Nonce: 128-bit (32 hex chars), must be unique
- Replay window: 5 minutes

## Best Practices
1. Validate all signatures before processing
2. Check timestamps to prevent replay attacks
3. Use constant-time comparison for secrets
4. Implement rate limiting per peer
5. Log security events for auditing
6. Rotate keys periodically

## Security Checklist
- [ ] Ed25519 signature verification enabled
- [ ] X25519 key exchange implemented
- [ ] AES-256-GCM encryption active
- [ ] Replay protection configured
- [ ] Rate limiting enabled
- [ ] Secure key storage implemented
