# AI Network Architecture L2

## Overview
L2 layer provides decentralized AI coordination network built on top of L1 peer-to-peer communication.

## L1 vs L2
| Layer | Scope | Status |
|-------|-------|--------|
| L1 | Direct peer communication | Complete |
| L2 | Global P2P network | Design |

## Core Components

### 1. Peer Discovery Service
- Bootstrap discovery from configured nodes
- Mdns local network discovery
- Gossip-based peer propagation

### 2. Distributed Hash Table (Kademlia)
- k=20, alpha=3
- tExpire=86400s, tRefresh=3600s
- SHA256-based key structure

### 3. Message Router
- Direct routing
- Relay routing for NAT traversal
- Store-and-forward for offline peers

### 4. Relay Service
- NAT traversal
- Firewall penetration
- Public relay nodes

### 5. Network Topology Manager
- Max 50 connections
- Small-world topology maintenance
- Peer selection optimization

### 6. Fault Tolerance
- Phi-accrual failure detection
- Auto-reconnection
- Partition healing

## Implementation Roadmap

### Phase 1: Foundation (2 weeks)
- PeerDiscoveryService
- Bootstrap functionality
- Gossip integration

### Phase 2: DHT Core (2 weeks)
- Kademlia implementation
- Routing table management
- Registry integration

### Phase 3: Routing & Relay (2 weeks)
- MessageRouter
- RelayService
- NAT traversal

### Phase 4: Fault Tolerance (1 week)
- Phi-accrual detector
- Auto-reconnection

### Phase 5: Integration (1 week)
- L1/L2 integration
- End-to-end testing

## Next Actions
1. PeerDiscoveryService detailed design
2. KademliaDHT implementation
3. RelayService implementation

---
Created: 2026-02-01
