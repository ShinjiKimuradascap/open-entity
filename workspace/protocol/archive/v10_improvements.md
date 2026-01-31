# v1.0 Protocol Improvements

## Critical Issues Found

1. **Dual Crypto Implementation**
   - crypto.py uses PyNaCl
   - crypto_utils.py uses cryptography library
   - Need to unify to single implementation

## Proposed Improvements

### 1. Message Format Enhancement
- Add message_id (UUID)
- Add recipient field
- Add content_type
- Add TTL for message expiration

### 2. Enhanced Handshake
- 6-step handshake process
- Challenge-response authentication
- Session key exchange

### 3. Session Management
- Session tokens with expiration
- Automatic rekeying
- Session resumption

### 4. Transport Abstraction
- Support HTTP/WebSocket/QUIC/TCP
- Pluggable transport layer

### 5. DPKI (Decentralized PKI)
- Blockchain-based identity registry
- No central authority required

### 6. Token Economy Foundation
- Payment channels
- Micropayments
- Resource tracking

### 7. Mesh Routing
- Multi-hop message routing
- Store-and-forward

## Implementation Phases

Phase 1: Foundation (unify crypto, new format)
Phase 2: Core Features (sessions, encryption)
Phase 3: Advanced (DPKI, tokens, routing)
Phase 4: Testing & Deployment

---
Draft: 2026-02-01
