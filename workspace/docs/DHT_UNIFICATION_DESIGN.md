# DHT Unification Design

**Version:** 1.0
**Date:** 2026-02-01

## Objective
Consolidate 3 DHT implementations into 1 unified module.

## Target Architecture

services/dht/
- __init__.py (Unified API)
- node.py (DHTNode from dht_node.py)
- crypto.py (Signatures from kademlia_dht.py)
- routing.py (KBucket/RoutingTable)
- storage.py (Value storage with TTL)
- registry.py (High-level registry API)

## Migration Strategy
1. Keep existing files for backward compatibility
2. Add deprecation warnings
3. New code uses unified module
4. Remove old files after 1 month

## Status: Design Complete
Next: Implementation Phase
