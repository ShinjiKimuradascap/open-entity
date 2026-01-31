# L1-L2 Bridge Design

## Overview

Bridge between L1 (PeerService/HTTP) and L2 (WebSocket/Relay) layers.

## Architecture

### Layer 1: Base Communication (Entity A)
- TCP/HTTP transport
- FastAPI endpoints
- Session management
- Ed25519 signatures

### Layer 2: Advanced Network (Entity B)
- WebSocket transport
- Relay service for NAT traversal
- DHT/Kademlia discovery

### Bridge Component
- Protocol translation
- Message routing
- Fallback handling

## Data Flow

Peer A (L1) -> Bridge -> Peer B (L2)

## Implementation

### BridgeService
- Receives L1 messages
- Detects peer capability
- Routes via L2 if available
- Falls back to L1

## Integration Points

| Component | Entity A | Entity B | Bridge Role |
|-----------|----------|----------|-------------|
| Transport | HTTP | WebSocket | Protocol selection |
| Discovery | Static/DHT | Kademlia | Unified API |
| Security | Ed25519 | Ed25519 | Pass-through |

## Testing
- L1 to L2 message routing
- Fallback scenarios
- Capability exchange

---
Created: 2026-02-01
