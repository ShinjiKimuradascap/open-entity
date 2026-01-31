# WebSocket Support Design

## Current State
- HTTP/REST via aiohttp
- Polling-based communication

## Proposed Design
- Add WebSocket endpoint: /ws/v1/peers
- Bidirectional real-time communication
- Fallback to HTTP if unavailable

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

Status: Design Complete
