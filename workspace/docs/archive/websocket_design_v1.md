# WebSocket Support Design v1.0

## Overview
Real-time P2P communication using WebSocket for AI Agent Collaboration Platform.

## Endpoints
- /ws/v1/peers/{peer_id} - Direct peer-to-peer communication
- /ws/v1/events - Server-sent events for broadcasts

## Authentication
- JWT Bearer token in header
- Ed25519 signature verification on handshake

## Message Protocol
- Types: HANDSHAKE, PING/PONG, TASK_REQUEST, PEER_MESSAGE, BROADCAST, ERROR
- Format: JSON with message_id, timestamp, sender_id, payload, signature
- Heartbeat: 30s interval, 60s timeout

## Security
- TLS required (WSS://)
- Ed25519 message signing
- Replay protection (60s window)
- Rate limiting: 100 msg/min per connection

## Migration Phases
1. Server Implementation - WebSocket endpoint in api_server.py
2. Client Implementation - WebSocket client in peer_service.py
3. Protocol Update - Update peer_protocol_v1.2.md
4. Testing - Unit, integration, load tests

## Dependencies
websockets>=12.0

Status: Design Complete | Updated: 2026-02-01 | Author: Entity A
