# NAT Traversal Design Document
## Phase 2 S2: NAT Traversal Design

**Status:** In Progress  
**Created:** 2026-02-01  
**Author:** Entity A

---

## 1. Overview

P2P network NAT traversal design for Protocol v1.2.

### 1.1 Goals
- Enable direct communication between peers behind NAT
- Support multiple NAT types (Full Cone, Restricted, Symmetric)
- Provide fallback mechanism (TURN relay)

---

## 2. Background

### 2.1 NAT Types

1. Full Cone NAT - Most permissive
2. Restricted Cone NAT - IP address restriction
3. Port Restricted Cone NAT - IP+port restriction
4. Symmetric NAT - Most strict, requires TURN

### 2.2 Protocols

- STUN: Session Traversal Utilities for NAT
- TURN: Traversal Using Relays around NAT
- ICE: Interactive Connectivity Establishment

---

## 3. Architecture

Components:
- STUN Client
- TURN Client
- NAT Type Detector
- UDP Hole Punching
- ICE Engine

---

## 4. Implementation Plan

Files to create:
- services/stun_client.py
- services/nat_detector.py
- services/hole_punching.py
- services/nat_traversal.py (main module)
- config/stun_servers.json

---

## 5. API Design

NATTraversalManager class:
- detect_nat_type()
- get_public_endpoint()
- connect_to_peer()
- create_relay_connection()

---

## 6. Timeline

Phase 1: STUN client (2 days)
Phase 2: NAT detection (1 day)
Phase 3: Hole punching (2 days)
Phase 4: TURN client (2 days)
Phase 5: Testing (2 days)

Total: 9 days

---

## 7. Next Steps

1. Implement STUN client
2. Implement NAT type detector
3. Create STUN server configuration
4. Design hole punching protocol
