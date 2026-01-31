# Peer Protocol v1.1 Implementation Plan

## Summary

Protocol v1.0仕様と実装の差分分析に基づく、未実装機能の設計・実装計画。

## Current Status

### Implemented in v1.0
- Ed25519 signatures on all messages
- Replay protection (nonce + timestamp)
- Message handlers: ping, status, heartbeat
- Capability exchange (capability_query/response)
- Task delegation with queue
- Peer statistics and health monitoring
- FastAPI HTTP server with endpoints
- Basic secure handshake (X25519 key exchange)

### Pending for v1.1

#### 1. Full Handshake Protocol (Priority: High)
Current: Basic secure handshake exists but doesn't follow v1.0 spec
Required: 3-way handshake (handshake → handshake_ack → handshake_confirm)

Protocol Flow:
1. A sends handshake with session_id, public_key, challenge, timestamp, signature
2. B responds with handshake_ack with challenge_response, new_challenge
3. A confirms with handshake_confirm
4. Session established

Implementation Tasks:
- Create HandshakeManager class
- Implement send_handshake() method
- Implement handle_handshake() handler
- Implement send_handshake_ack() method
- Implement handle_handshake_ack() handler
- Implement send_handshake_confirm() method
- Implement handle_handshake_confirm() handler
- Add session state machine
- Add session timeout handling

#### 2. Session Management with UUID (Priority: High)
Current: Session class exists but not integrated into message flow
Required: All messages must include session_id after handshake

Implementation Tasks:
- Integrate Session into PeerService message flow
- Add session_id to all outgoing messages after handshake
- Validate session_id on incoming messages
- Implement session expiration
- Add session cleanup for expired sessions

#### 3. Wake Up Protocol (Priority: Medium)
Current: Not implemented
Required: wake_up message type for peer activation

Implementation Tasks:
- Implement send_wake_up(target_id) method
- Implement handle_wake_up() handler
- Implement send_wake_up_ack() method
- Implement handle_wake_up_ack() handler
- Add wake_up retry logic
- Integrate with HeartbeatManager

#### 4. Sequence Numbers for Ordering (Priority: Medium)
Current: Session class has sequence_num but not used
Required: Per-session sequence numbers for message ordering

Implementation Tasks:
- Auto-increment sequence_num for each sent message
- Track expected_sequence for each peer session
- Validate sequence numbers on receive
- Handle out-of-order messages

## Implementation Order

1. Phase 1: Session Management Foundation
2. Phase 2: Full Handshake Protocol
3. Phase 3: Wake Up Protocol
4. Phase 4: Sequence Numbers

## Files to Modify

- services/peer_service.py
- services/api_server.py
- protocol/peer_protocol_v1.0.md
