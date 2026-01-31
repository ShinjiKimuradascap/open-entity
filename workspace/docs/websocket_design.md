# WebSocket Support Design

## Current State
- HTTP/REST via FastAPI (api_server.py)
- Polling-based communication for Moltbook integration
- No WebSocket support currently implemented
- Polling-based communication

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

## Files
- api_server.py: WebSocket endpoint
- peer_service.py: WebSocket client
- peer_protocol_v1.2.md: Spec update

Status: Design Complete (v1.0)
