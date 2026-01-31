# DHT-Based Peer Registry Design v1.2

## Overview
Distributed peer registry using Kademlia DHT for decentralized peer discovery.

## Research Findings

### Recommended Library: bmuller/kademlia
- Asyncio-based Python implementation
- Production-ready (used in real P2P networks)
- RPC over UDP communication
- Follows reference Kademlia paper

### Alternative Options
- libdht: Work in progress, not production-ready
- kad.py: Simple implementation for key-value store
- pykad: Educational use only

## Design Proposal

### 1. Architecture
- Peer Node contains DHTRegistry (Kademlia Node)
- Node ID is hash of entity_id
- Storage: peer_id maps to peer information

### 2. Key Design
- Key: peer_id (SHA-256 hash)
- Value: PeerInfo with public_key, endpoint, capabilities

### 3. Operations
- Register: Publish own PeerInfo to DHT
- Discover: Query DHT for random peer IDs
- Bootstrap: Connect to known bootstrap nodes
- Refresh: Periodically republish own info

### 4. Security Considerations
- Self-signed PeerInfo with Ed25519
- Signature verification on lookup
- Bootstrap node authentication
- Sybil attack mitigation

### 5. Integration Plan
1. Add kademlia to requirements.txt
2. Create DHTRegistry class
3. Integrate with PeerService bootstrap
4. Add discovery API endpoint

Last Updated: 2026-02-01
