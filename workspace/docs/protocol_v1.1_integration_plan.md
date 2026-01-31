# Protocol v1.1 Integration Plan

## Current Status Analysis

### Completed (v1.0)
- Ed25519 signatures on all messages
- Replay protection (nonce + timestamp)
- Message handlers: ping, status, heartbeat
- Capability exchange
- Task delegation with queue
- Peer statistics and health monitoring
- FastAPI HTTP server endpoints

### Implemented in crypto.py but NOT integrated in peer_service.py
- X25519/AES-256-GCM encryption (E2EEncryption class)
- Session management with UUID (SessionManager class)
- Sequence number management
- Ed25519 to X25519 key conversion

### Pending Integration (v1.1)
1. E2E Encryption Integration
2. Session Management Integration
3. Enhanced Handshake with X25519
4. Chunked Message Transfer

## Implementation Priority

### Phase 1: Session Management (High Priority)
- Integrate SessionManager into PeerService
- Add session_id to all messages
- Implement sequence number validation

### Phase 2: E2E Encryption (High Priority)
- Initialize E2EEncryption in PeerService
- Add encrypted payload support
- Implement key exchange in handshake

### Phase 3: Chunked Transfer (Medium Priority)
- Implement message chunking
- Add chunk reassembly logic

## Files to Modify
1. services/peer_service.py - Main integration
2. protocol/peer_protocol_v1.1.md - Document new protocol version
3. services/api_server.py - Update to use v1.1 features

---

## 統合履歴

このドキュメントは以下のファイルを統合して作成されました:

| 統合元ファイル | 統合日 | 備考 |
|--------------|--------|------|
| protocol_v1.1_improvements.md | 2026-02-01 | v1.1改善案を統合 |
| protocol_v1.1_implementation_status.md | 2026-02-01 | 実装状況を統合 |

統合されたファイルは `docs/archive/` にアーカイブされています。
