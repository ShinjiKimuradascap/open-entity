# Relay Service Design

## Purpose
NAT traversal and firewall penetration for P2P communication.

## Architecture
Public Relay Nodes mediate between NATed peers.

## Components

### RelayService (Server)
- Accept registrations from NATed peers
- Forward messages between peers
- Enforce bandwidth limits

### RelayClient (NATed Peer)
- Register with public relays
- Send/receive via relay
- Maintain relay connections

### MessageRouter (Integration)
- Select best relay for target
- Fallback to relay when direct fails

## Protocol
1. NATed peer registers with relay
2. Sender asks relay to forward message
3. Relay forwards to registered peer
4. Target receives via relay connection

## Security
- E2E encryption maintained
- Relay cannot read content
- Relay authentication required

## Files
- services/relay_service.py
- services/relay_client.py

---
Created: 2026-02-01
