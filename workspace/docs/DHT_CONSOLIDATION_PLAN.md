# DHT Implementation Consolidation Plan

## Date
2026-02-01

## Overview
Consolidate 3 separate Kademlia DHT implementations into a single primary implementation.

## Current State

| File | Lines | Implementation | Status |
|------|-------|----------------|--------|
| services/dht_node.py | 1,031 | Native Kademlia (complete) | **PRIMARY** |
| services/dht.py | 661 | Native Kademlia (partial) | DEPRECATE |
| services/dht_registry.py | 600 | External kademlia lib | DEPRECATE |

## Issues with Current State

1. Code Duplication: 3 separate Kademlia implementations
2. NodeInfo Class Conflicts: Different NodeInfo definitions in each file
3. Maintenance Overhead: Changes need to be synced across 3 files
4. Import Confusion: Unclear which DHT to use

## Consolidation Plan

### Phase 1: Archive Deprecated Files

Move to archive/deprecated/:
- services/dht.py -> archive/deprecated/dht.py
- services/dht_registry.py -> archive/deprecated/dht_registry.py

### Phase 2: Update Imports

Files using deprecated DHT modules need updating.

### Phase 3: Verify Primary Implementation

Confirm dht_node.py has all required features.

### Phase 4: Testing

Test dht_node.py standalone and integration.

## References

- Primary: services/dht_node.py (1,031 lines, most complete)
- Design: docs/kademlia_dht_design.md
