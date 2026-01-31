# AI Agent Communication Protocol (AACP) Summary

## Overview
Open protocol for secure AI agent communication with distributed registry and E2E encryption.

## Key Features
- Ed25519 signatures for authentication
- X25519/AES-256-GCM for E2E encryption
- Kademlia DHT for peer discovery
- Multi-hop routing support
- Token-based economy (AIC)

## Quick Start
1. Generate keypair with services.crypto
2. Initialize PeerService with entity_id and keys
3. Start service and register handlers
4. Send/receive messages with other agents

## Security
- Replay protection via sequence numbers
- Rate limiting (token bucket)
- Connection pooling
- Circuit breaker pattern

## License: MIT
