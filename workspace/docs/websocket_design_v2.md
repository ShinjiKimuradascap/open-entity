# WebSocket Support Design v2.0

## Current State
- HTTP/REST via FastAPI (api_server.py)
- Polling-based communication for Moltbook integration
- Protocol v1.1 with 6-step handshake + E2E encryption implemented
- No WebSocket support currently implemented

## Proposed Design

### Architecture
FastAPI WebSocket endpoint for real-time P2P communication

### Endpoints
- `/ws/v1/peers` - Peer-to-peer real-time communication (JWT + Ed25519 auth)
- `/ws/v1/events` - Server-sent events for broadcasts

### Implementation Phases
1. Phase 1: Server-Side WebSocket in api_server.py
2. Phase 2: Client Integration in peer_service.py
3. Phase 3: Protocol Update v1.2
4. Phase 4: Testing & validation

## Benefits
- Lower latency: 100ms -> 10ms
- Server push capability
- Connection reuse

## Migration
1. Implement alongside HTTP
2. Capability exchange detection
3. Gradual migration
4. HTTP fallback

## Detailed Message Protocol

### Message Types (v1.1 Compatible)

#### v1.1 Protocol Mapping
| v1.1 Message Type | WebSocket Message Type | Description |
|-------------------|------------------------|-------------|
| handshake_init | HANDSHAKE_INIT | Step 1 - X25519 pubkey exchange |
| handshake_init_ack | HANDSHAKE_INIT_ACK | Step 2 - Challenge + pubkey response |
| challenge_response | CHALLENGE_RESPONSE | Step 3 - Signed challenge |
| session_established | SESSION_ESTABLISHED | Step 4 - Session confirmation |
| session_confirm | SESSION_CONFIRM | Step 5 - Session ack |
| ready | READY | Step 6 - E2E encryption active |

#### Connection Management
- PING/PONG: Heartbeat (every 30s, ws_heartbeat rate limit: 2/min)

#### Data Transfer
- PEER_MESSAGE: Direct peer message (encrypted)
- BROADCAST: Broadcast to all peers (encrypted)
- TASK_REQUEST/RESPONSE: Task delegation
- CHUNKED_MESSAGE: Large message chunk (v1.1 chunked transfer)
  - chunk_id: Unique identifier for the message
  - sequence_number: Position in chunk sequence
  - is_last: Boolean flag for final chunk
  - WebSocket uses single connection for all chunks (no HTTP overhead)

#### Control
- ERROR: Error notification
- STATUS: Status update
- CAPABILITY_EXCHANGE: Feature negotiation

### Message Format
JSON with message_id, type, version, timestamp, seq, session_id, sender_id, recipient_id, payload, nonce, signature

## Authentication Flow

### Option A: Pre-authenticated (Recommended)
1. Complete v1.1 6-step handshake over HTTP first
2. Upgrade to WebSocket with session_id in query param
3. Resume session over WebSocket with E2E encryption active

### Option B: In-band Handshake
1. Connection Upgrade via HTTP with Authorization header
2. WebSocket Handshake (in-band) within 5 seconds
3. Perform v1.1 6-step handshake over WebSocket
4. Ed25519 signature + X25519 E2E encryption on all messages

## Session Recovery on Reconnection

### Disconnection Detection
- PONG timeout: 30s + 10s grace period
- TCP connection closed
- Error on send/receive

### Reconnection Flow
1. Client attempts reconnection with exponential backoff (1s, 2s, 4s, 8s, max 60s)
2. Include existing `session_id` in query param: `/ws/v1/peers?session_id=sess_abc123`
3. Server validates session state:
   - READY: Resume encrypted session (no re-handshake)
   - EXPIRED/ERROR: Require new v1.1 handshake
   - NOT_FOUND: Treat as new connection
4. Client re-sends any unacknowledged messages with new seq numbers

## Implementation Details

### Phase 1: Server-Side (api_server.py)
WebSocketManager class:
- active_connections dictionary for peer routing
- connect/disconnect handlers
- send_to_peer method

### Phase 2: Client (peer_service.py)
WebSocketPeerClient class:
- Connection with JWT token
- Automatic reconnection with backoff
- Heartbeat loop (30s interval)

### Security Requirements
- TLS 1.3 required (wss:// only)
- Ed25519 signing on all messages
- Replay protection (timestamp + nonce)
- Rate limiting: 100 msg/min per connection
- Max message size: 1MB

### WebSocket Error Mapping to v1.1 Error Codes
| WebSocket Event | v1.1 Error Code | Description |
|-----------------|-----------------|-------------|
| Connection closed unexpectedly | SESSION_NOT_FOUND | Session state lost |
| Invalid message format | INVALID_MESSAGE | JSON parse error |
| WebSocket upgrade failed | AUTHENTICATION_FAILED | JWT or origin check failed |
| Rate limit exceeded | RATE_LIMIT_EXCEEDED | Too many messages |
| Message too large | MESSAGE_TOO_LARGE | Exceeds 1MB limit |
| Protocol violation | INVALID_STATE | Unexpected message type

## Migration Strategy
1. Deploy WebSocket alongside HTTP (dual-stack)
2. Capability exchange during handshake
3. Prefer WebSocket when both sides support it
4. HTTP fallback for legacy peers

## Performance Targets
- Latency: < 10ms (vs 100ms HTTP polling)
- Throughput: 10,000 msg/sec per server
- Concurrent connections: 10,000 per instance
- Memory: < 1MB per connection

## Files
- api_server.py: WebSocket endpoint (+150 lines)
- peer_service.py: WebSocket client (+200 lines)
- websocket_manager.py: Connection management (+100 lines)
- peer_protocol_v1.2.md: Spec update

## Implementation Phases (Updated)

### Phase 1: Server-Side WebSocket (api_server.py)
- WebSocket endpoint `/ws/v1/peers`
- Connection manager with session routing
- Support for pre-authenticated sessions
- Estimated: +200 lines

### Phase 2: Client Integration (peer_service.py)
- WebSocketPeerClient class
- Auto-reconnection with exponential backoff
- Dual-stack (HTTP + WebSocket) support
- Estimated: +250 lines

### Phase 3: Protocol v1.2 Update
- WebSocket transport specification
- Capability negotiation (HTTP vs WebSocket)
- Fallback mechanism documentation

### Phase 4: Testing
- Unit tests for WebSocketManager
- Integration tests with peer_service
- Performance benchmarks

## Status
- Design: Complete (v2.0 - v1.1 Compatible)
- Implementation: Ready to start
- Next Action: Phase 1 implementation in api_server.py
