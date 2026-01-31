# PeerService DHT Integration Design v1.0

## Overview
Integrate PeerService with DHTRegistry for decentralized peer discovery.

## Current Status
- PeerService: 6,508 lines (HTTP-based peer communication)
- DHTRegistry: 311 lines (Kademlia DHT registry)
- Both implemented but not integrated

## Integration Points
1. DHTRegistry initialization in PeerService
2. Peer discovery using DHT first, fallback to bootstrap
3. Direct connection using DHT lookup

## Implementation Plan
- Phase 1: DHT integration foundation
- Phase 2: Peer discovery integration
- Phase 3: API implementation and tests

## Status
- [x] Design document created (2026-02-01)
- [ ] Integration code implementation
- [ ] Integration tests
