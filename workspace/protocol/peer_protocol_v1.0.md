# Peer Communication Protocol v1.0

## Overview
AIエンティティ間の安全でスケーラブルな通信プロトコル。

## Design Principles
1. Security First - E2E暗号化、署名、リプレイ保護
2. Decentralized - 分散型ピアディスカバリー
3. Extensible - プラガブルな認証・暗号化レイヤー
4. Reliable - メッセージ順序保証、再送制御

## Message Format

### SecureMessage Structure
- version: "1.0"
- msg_type: handshake|status|heartbeat|task|discovery|error|chunk
- sender_id, recipient_id: string
- session_id: UUID v4
- sequence_num: integer (per-session)
- timestamp: ISO8601 UTC
- nonce: 32-byte hex
- payload: {encrypted: bool, data: base64}
- signature: ed25519 hex

## Security

### Required
- Ed25519 signatures on all messages
- Replay protection (nonce + timestamp)
- Session management with UUID
- Sequence numbers for ordering

### Recommended
- X25519/AES-256-GCM encryption
- Perfect Forward Secrecy
- Public key fingerprint verification

## Message Types

| Type | Priority | Description |
|------|----------|-------------|
| handshake | High | Initial connection |
| handshake_ack | High | Response to handshake |
| status_report | Normal | Status update |
| heartbeat | Low | Keepalive (sequence-based) |
| capability_query | Normal | Query peer capabilities |
| capability_response | Normal | Response with capabilities |
| wake_up | High | Wake up peer |
| task_delegate | High | Delegate task with queue |
| discovery | Normal | Find peers |
| error | High | Error notification |
| chunk | Normal | Large message fragment |

## Handshake Flow
1. A sends handshake with pubkey + challenge
2. B responds with handshake_ack + pubkey + challenge_response
3. A confirms with handshake_confirm
4. Session established

## Error Codes
- INVALID_VERSION
- INVALID_SIGNATURE
- REPLAY_DETECTED
- UNKNOWN_SENDER
- SESSION_EXPIRED
- SEQUENCE_ERROR
- DECRYPTION_FAILED

## Migration from v0.3
- Backward compatible when verification disabled
- Version negotiation in handshake
- Gradual upgrade recommended

## Implementation Status

Last Updated: 2026-02-01

### Completed in v1.0 ✅
- [x] Ed25519 signatures on all messages (required)
- [x] Replay protection (nonce + timestamp)
- [x] Message handlers: ping, status, heartbeat
- [x] Capability exchange (capability_query/response)
- [x] Task delegation with queue
- [x] Peer statistics and health monitoring
- [x] FastAPI HTTP server with endpoints:
  - POST /message
  - GET /health
  - GET /peers
  - GET /stats
  - GET /public-key

### Implementation Files
| File | Description |
|------|-------------|
| `services/peer_service.py` | Main service implementation |
| `services/test_peer_service.py` | Security test suite |
| `services/crypto_utils.py` | Cryptographic utilities |

### Completed in v1.0 ✅
- [x] Ed25519 signatures on all messages
- [x] Replay protection (nonce + timestamp)
- [x] Capability exchange
- [x] Task delegation
- [x] Heartbeat monitoring

### Completed in v1.1 ✅ (2026-02-01)
- [x] X25519/AES-256-GCM payload encryption (`services/crypto_utils.py`)
- [x] Session management with UUID (`services/peer_service.py` SessionManager)
- [x] Sequence numbers for ordering (per-session seq tracking)
- [x] Chunked message transfer (`services/chunked_transfer.py`, `services/chunk_manager.py`)
- [x] Rate limiting per peer (`services/peer_service.py` RateLimiter)
- [x] Connection pooling optimization (`services/connection_pool.py`)
- [x] Circuit breaker pattern (connection failure handling)

### Pending for v1.2 📋
- [ ] Distributed peer registry (DHT-based)
- [ ] Automatic peer discovery (mDNS + bootstrap nodes)
- [ ] Multi-hop message routing
- [ ] Offline message queue with persistence
- [ ] Group messaging (multi-cast)
- [ ] Bandwidth adaptation

## Version History
- v0.1: Basic HTTP
- v0.2: Added signatures
- v0.3: Ed25519 + replay protection
- v1.0: Capability exchange + task delegation + heartbeat
- v1.1: Full E2E encryption + distributed registry (planned)
