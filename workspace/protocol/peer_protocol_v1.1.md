# Peer Communication Protocol v1.1

## Overview

Peer Communication Protocol v1.1は、AIエンティティ間の安全でスケーラブルな通信を実現するプロトコルです。v1.0の署名ベース認証に加え、v1.1ではE2E暗号化、Perfect Forward Secrecy (PFS)、および拡張セッション管理を導入しています。

### What's New in v1.1

| Feature | Description | Status |
|---------|-------------|--------|
| 6-Step Handshake | X25519 key exchange for secure session | ✅ Implemented |
| E2E Encryption | AES-256-GCM payload encryption | ✅ Implemented |
| Perfect Forward Secrecy | Ephemeral keys per session | ✅ Implemented |
| Extended Session States | 9-state detailed management | ✅ Implemented |
| Sequence Numbers | Message ordering guarantee | ✅ Implemented |
| Chunked Transfer | Large message split transfer | ✅ Implemented |
| Rate Limiting | Per-peer rate limiting | ✅ Implemented |
| Backward Compatibility | v1.0 peer compatibility | ✅ Maintained |

Main changes from v1.0: 6-step handshake + X25519/AES-256-GCM E2E encryption + PFS

## Design Principles
1. **Security First** - E2E暗号化、署名、リプレイ保護、PFS
2. **Decentralized** - 分散型ピアディスカバリー
3. **Extensible** - プラガブルな認証・暗号化レイヤー
4. **Reliable** - メッセージ順序保証、再送制御
5. **Backward Compatible** - v1.0ピアとの後方互換性維持

## 6-Step Handshake Flow

Step 1: A sends handshake_init (Ed25519 pubkey + X25519 ephemeral pubkey)
Step 2: B responds handshake_init_ack (Ed25519 pubkey + X25519 ephemeral pubkey + challenge)
Step 3: A sends challenge_response (signed challenge)
Step 4: B sends session_established (session_id + confirmation)
Step 5: A sends session_confirm (ack of session)
Step 6: B sends ready (encryption ready)

### Session Key Derivation
shared_secret = X25519(ephemeral_private_key, ephemeral_public_key_peer)
session_key = HKDF-SHA256(input=shared_secret, salt=handshake_hash, info="peer-v1.1-session-key", length=32)

## Session States (v1.1)
- INITIAL: No session exists
- HANDSHAKE_INIT_SENT: Step 1 completed
- HANDSHAKE_ACK_RECEIVED: Step 2 completed
- CHALLENGE_SENT: Step 3 completed
- SESSION_ESTABLISHED: Step 4 completed
- SESSION_CONFIRMED: Step 5 completed
- READY: Step 6 completed (E2E encryption active)
- ERROR: Session error
- EXPIRED: Session timeout

## Error Codes (v1.1)
- INVALID_VERSION: Protocol version not supported
- INVALID_SIGNATURE: Ed25519 verification failed
- REPLAY_DETECTED: Replay attack detected
- SESSION_EXPIRED: Session TTL exceeded
- SEQUENCE_ERROR: Sequence number mismatch
- DECRYPTION_FAILED: AES-GCM decryption failed
- CHALLENGE_EXPIRED: Challenge timeout
- CHALLENGE_INVALID: Challenge signature invalid
- HANDSHAKE_IN_PROGRESS: Another handshake active
- SESSION_NOT_FOUND: Session does not exist
- ENCRYPTION_NOT_READY: Message before READY state
- INVALID_STATE: Invalid state transition

## Implementation Status

### Completed in v1.1
- 6-step handshake with X25519 key exchange
- E2E payload encryption (AES-256-GCM)
- Perfect Forward Secrecy
- Session state machine (9 states)
- Sequence number tracking per session
- Backward compatibility with v1.0

### Pending for v1.2
- Distributed peer registry (DHT-based)
- Rate limiting per peer
- Multi-hop message routing
- Offline message queue with persistence

## Migration from v1.0
- Backward compatible
- Features are opt-in
- Gradual upgrade

## Technical Specifications

### DHT Key Structure
key = SHA256(entity_id + ":" + capability_hash)
value = {entity_id, addresses[], public_key, capabilities[], last_seen, ttl}

### Kademlia Parameters
- k = 20 (bucket size)
- alpha = 3 (parallel lookups)
- tExpire = 86400s
- tRefresh = 3600s

### Encryption Flow
1. Generate ephemeral X25519 keypair
2. ECDH key exchange
3. HKDF-SHA256 key derivation
4. AES-256-GCM encryption

### Rate Limits (Token Bucket)
- handshake: 5/min, burst 10
- heartbeat: 60/min, burst 120
- task: 30/min, burst 60
- discovery: 10/min, burst 20
- chunk: 120/min, burst 240

### Session States
INIT -> HANDSHAKE_SENT -> ACTIVE -> CLOSED

### Error Codes (v1.1 Additions)
- ENCRYPTION_REQUIRED
- SESSION_EXPIRED
- SESSION_NOT_FOUND
- SEQUENCE_ERROR
- RATE_LIMITED
- CHUNK_ERROR
- DHT_ERROR

## Security Considerations
- Eavesdropping: E2E encryption (X25519/AES-256-GCM)
- Tampering: Ed25519 signatures
- Replay: Nonce + timestamp validation
- MITM: Public key fingerprint verification
- DoS: Rate limiting per peer
- Forward secrecy: Ephemeral X25519 keys per session

**Document Version:** 1.1.0-PRODUCTION  
**Last Updated:** 2026-02-01  
**Status:** Production Ready

---

## 統合履歴 (Integration History)

| 日付 | 統合内容 | 備考 |
|------|---------|------|
| 2026-02-01 | `v1.0_improvements.md` から改善案を統合 | v1.1新機能として実装 |
| 2026-02-01 | `v1.0_gap_analysis.md` から要件を統合 | 設計に反映 |

- アーカイブ: `docs/archive/v1.0_improvements.md`, `docs/archive/v1.0_gap_analysis.md`
