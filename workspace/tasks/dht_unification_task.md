# DHT Unification Task

**Assigned to:** @coder
**Priority:** HIGH

## Objective
Implement unified DHT module consolidating 3 existing implementations.

## Source Files
- services/kademlia_dht.py (signatures)
- services/dht.py (clean interfaces)
- services/dht_node.py (HTTP server)

## Target
Create services/dht/ with:
- node.py: DHTNode class
- crypto.py: Ed25519 signatures
- routing.py: KBucket/RoutingTable
- registry.py: High-level API

## Requirements
- PeerInfo with signature support
- DHTNode with crypto integration
- Backward compatibility
- Full test coverage

## Acceptance Criteria
- All tests pass
- Signatures work correctly
- Documentation complete
