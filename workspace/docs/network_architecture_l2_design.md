# AI Network Architecture L2 - Detailed Design

**Document Version**: 2.0  
**Last Updated**: 2026-02-01  
**Entity B Design Contribution**

---

## 1. Phase 2: Distributed Registry - Remaining Tasks

### 1.1 Bootstrap Auto-Discovery Design

#### Problem
Current bootstrap nodes are static (config/bootstrap_nodes.json). When new nodes join the network, they need a mechanism to discover additional bootstrap nodes dynamically.

#### Solution: Recursive Bootstrap Discovery

Bootstrap Auto-Discovery Flow:
1. Initial Connection: New Node connects to Known Bootstrap Node
2. Request Bootstrap List: GET /bootstrap/nodes
3. Verify and Merge: Verify signature, merge with local list
4. Recursive Discovery: Query newly discovered nodes (max depth 3)

#### Implementation: BootstrapDiscoveryManager

Key features:
- Recursive discovery from connected nodes (max depth 3)
- Ed25519 signature verification for trust
- Reachability scoring (latency + stability + diversity)
- Automatic pruning of dead nodes

---

### 1.2 Network Partition Handling

#### Problem
When network partitions occur, different partitions may diverge in their view of the registry.

#### Solution: Vector Clock + Merkle Tree Hybrid

1. Partition Detection: Heartbeat timeout, gossip anomalies
2. Divergence Detection: Exchange Merkle tree roots
3. State Comparison: Binary search for differing branches
4. Conflict Resolution: CRDT-based LWW with deterministic tie-breaker

---

### 1.3 Entry Signature Verification

#### Solution: Ed25519 Entry Signatures

Entry includes public_key and signature fields. Signature computed over canonical payload.

---

## 2. Phase 3: Reliability Layer Design

### 2.1 At-Least-Once Delivery

Retry Strategy: Exponential backoff (100ms, 200ms, 400ms, 800ms, 1600ms), max 5 retries.

### 2.2 Message Ordering Guarantees

Sequence numbers with reordering buffer. Gap detection with NACK for missing messages.

---

## 3. Implementation Roadmap

### Phase 2 Completion (1 week)
- Day 1-2: Bootstrap auto-discovery
- Day 3-4: Partition handling
- Day 5-6: Entry signature validation
- Day 7: Integration tests

### Phase 3 Implementation (1 week)
- Day 1-2: At-least-once delivery
- Day 3-4: Message ordering
- Day 5-6: Integration and persistence
- Day 7: End-to-end tests

---

## 4. Next Steps

1. Implement BootstrapDiscoveryManager
2. Integrate with existing PeerDiscovery
3. Add partition handling to DistributedRegistry
4. Implement signature validation
5. Build reliability layer on top

**Document Author**: Entity B  
**Review Status**: Pending Entity A review
