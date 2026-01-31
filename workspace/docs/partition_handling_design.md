# Network Partition Handling Design

## Overview

分散レジストリシステムにおけるネットワークパーティション（分割）の検出と解決の設計書。

## Architecture

### Core Components

- MerkleTree: 効率的な状態比較 (O(log n))
- VectorClock: 因果関係の追跡
- PartitionManager: パーティション検出と解決

## Partition Detection

### State Machine

HEALTHY -> SUSPECTED -> PARTITIONED -> RECOVERING -> HEALTHY

### Detection Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| PARTITION_TIMEOUT | 60s | Heartbeat missing threshold |
| MERKLE_SYNC_INTERVAL | 30s | State comparison interval |
| MAX_DIVERGENT_ENTRIES | 100 | Batch sync limit |

## State Synchronization

### Merkle Tree Based Sync

1. Root Hash Exchange - O(1) comparison
2. Diff Path Traversal - O(log n) to find differences
3. Incremental Sync - Only divergent entries
4. Conflict Resolution - Vector clock based merge

## Conflict Resolution

### Vector Clock Comparison

Concurrent updates (conflict):
- Node A: {A: 3, B: 2}
- Node B: {A: 2, B: 3}
- Result: CONCURRENT -> requires resolution

Causal ordering (no conflict):
- Node A: {A: 3, B: 2}
- Node B: {A: 4, B: 2}
- Result: B happens-after A -> accept B

### Resolution Strategies

| Strategy | Use Case |
|----------|----------|
| Last-Write-Wins (LWW) | Single-writer scenarios |
| Merge | Multi-writer compatible data |
| Custom | Domain-specific logic |

## Recovery Process

1. Partition End Detected
2. Build Merkle Trees
3. Compare Root Hashes
4. Find Divergent Entries (if different)
5. Resolve Each Conflict
6. Apply Changes Both Sides

## Performance Characteristics

| Operation | Complexity |
|-----------|------------|
| State comparison | O(log n) |
| Diff detection | O(k log n) |
| Conflict resolution | O(m) |
| Full sync | O(n) |

## Fault Tolerance

### Safety Guarantees

- Eventual Consistency
- Conflict-free (deterministic resolution)
- Partition tolerant

## Implementation Status

| Component | Status | File |
|-----------|--------|------|
| MerkleTree | Complete | services/partition_manager.py |
| VectorClock | Complete | services/partition_manager.py |
| PartitionManager | Complete | services/partition_manager.py |
| Integration Tests | Pending | tests/integration/ |

## References

- Implementation: services/partition_manager.py (622 lines)
- Protocol: protocol/peer_protocol_v1.2.md
