# Peer Communication Protocol v1.2

## Overview
Decentralized AI agent communication with distributed registry and multi-hop routing.

## New Features in v1.2

### 1. Distributed Peer Registry (DHT-based)
- Kademlia DHT for peer discovery
- No central registry required
- Bootstrap nodes for initial connection
- Peer ID = SHA256(public_key)

### 2. Multi-hop Message Routing
- Messages can traverse multiple peers
- Onion routing for privacy
- TTL-based loop prevention
- Route caching for efficiency

### 3. Offline Message Queue
- Persistent storage for undelivered messages
- Retry with exponential backoff
- TTL for message expiration
- Delivery confirmation

### 4. Group Messaging (Multi-cast)
- Create/join/leave groups
- Efficient multi-cast routing
- Group encryption (shared key)
- Member management

### 5. Bandwidth Adaptation
- Dynamic quality adjustment
- Message prioritization
- Congestion control
- Bandwidth usage metrics

## Dependencies

- `kademlia` - Asyncio-based Kademlia DHT implementation
- `rpcudp` - UDP RPC for Kademlia (usually included)

Install: `pip install kademlia`

## Implementation Timeline

- Week 1-2: DHT foundation (kademlia integration)
- Week 3-4: Multi-hop routing
- Week 5-6: Offline queue
- Week 7-8: Group messaging
- Week 9-10: Bandwidth adaptation
- Week 11-12: Testing and optimization

## Connection Pooling Specification

### Pool Architecture
Persistent connection management for efficient multi-hop routing.

Configuration:
- max_connections_per_peer: 3
- max_idle_time: 300 seconds
- connection_timeout: 10 seconds
- keep_alive_interval: 30 seconds

Lifecycle:
1. Acquire - get from pool or create new
2. Validate - check with ping/pong
3. Use - send/receive messages
4. Release - return to pool
5. Evict - remove idle/invalid connections

## Implementation Status

### Completed (v1.1 baseline)
- E2E encryption (X25519/AES-256-GCM)
- Session management with UUID
- Rate limiting (token bucket)
- Message chunking

### Completed (v1.2 current)
- Distributed Registry (`services/distributed_registry.py`)
- Message Router (`services/message_router.py`)
- Rate Limiter (`services/rate_limiter.py`)
- Memory-based Message Queue

### In Progress
- Connection pooling design
- Multi-hop routing protocol
- Kademlia DHT integration planning

### Pending
- Persistent offline message queue
- Group messaging (multi-cast)
- Bandwidth adaptation algorithms
- WebSocket transport support
- Binary protocol (CBOR)
- Message compression (zstd)

## Migration from v1.1

1. Backward Compatible: v1.1ピアとの通信維持
2. Feature Detection: capability_queryでv1.2機能を検出
3. Gradual Upgrade: 個別機能の段階的な有効化

## Notes

- Use existing `kademlia` library for DHT implementation
- Maintain backward compatibility with v1.1
- Support both DHT and static registry (hybrid mode)
- Bootstrap nodes can be loaded from config or environment
- Current focus: Connection pooling + Multi-hop routing for v1.2 MVP
