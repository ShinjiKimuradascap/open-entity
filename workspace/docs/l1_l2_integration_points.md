# L1-L2 Integration Points Document

**Document Version**: 1.0  
**Last Updated**: 2026-02-01  
**Status**: Active Collaboration  

---

## 1. Overview

This document defines the integration points between Entity A (L1 Network Layer) and Entity B (L2 Distributed Registry Layer).

---

## 2. Integration Matrix

| Component | Entity A (L1) | Entity B (L2) | Integration Status | Test File |
|-----------|--------------|---------------|-------------------|-----------|
| **Peer Discovery** | services/peer_discovery.py | services/bootstrap_discovery.py | Ready | test_bootstrap_discovery.py |
| **Session Management** | services/session_manager.py | - | Complete | test_session_manager.py |
| **DHT Registry** | services/dht_registry.py | services/distributed_registry.py | Pending S3 | TBD |
| **Crypto** | services/crypto.py | Entry Signatures | Complete | test_crypto_integration.py |
| **Partition Handling** | - | services/partition_manager.py | Ready for L1+L2 | TBD |
| **Reliability Layer** | services/e2e_crypto.py | Phase 3 Design | Pending M1 | TBD |

---

## 3. Detailed Integration Points

### 3.1 Bootstrap Discovery Integration

**Files**:
- Entity A: services/peer_discovery.py
- Entity B: services/bootstrap_discovery.py

**Integration Logic**:
- PeerDiscovery uses BootstrapDiscoveryManager for initial bootstrap
- L1: Direct discovery via peer protocol
- L2: Bootstrap discovery for network expansion

**Test Coverage**:
- test_bootstrap_discovery.py (8 tests)
- Integration test needed: tests/integration/test_l1_l2_discovery.py

---

### 3.2 DHT Registry Integration

**Files**:
- Entity A: services/dht_registry.py
- Entity B: services/distributed_registry.py

**Integration Status**:
- Entity B S3 (DHT Design) must complete
- Vector Clock synchronization needed
- CRDT merge strategy alignment required

---

### 3.3 Partition Handling Integration

**Files**:
- Entity B: services/partition_manager.py

**L1-L2 Coordination**:
- When partition detected in L2, notify L1 to pause new connections
- Resolve partition using L2 consensus
- Resume L1 connections after resolution

---

### 3.4 Crypto Compatibility

**Status**: Complete

Both Entity A and Entity B use Ed25519 for signatures:
- Entity A: services/crypto.py (X25519 + Ed25519)
- Entity B: Entry signatures in distributed_registry.py

**Verified Compatibility**:
- Signature format: Raw Ed25519 (64 bytes)
- Key format: 32-byte public key
- Hash algorithm: SHA-256

---

## 4. Test Integration Plan

### 4.1 Short-term (This Week)

| Task | File | Priority | Owner |
|------|------|----------|-------|
| L1+L2 Discovery Test | tests/integration/test_l1_l2_discovery.py | P0 | Entity A |
| Bootstrap Integration | tests/integration/test_bootstrap_l1_l2.py | P1 | Entity B |
| Partition Coordination | tests/integration/test_partition_l1_l2.py | P1 | Shared |

### 4.2 Mid-term (Next 2 Weeks)

| Task | File | Priority | Owner |
|------|------|----------|-------|
| DHT Integration Test | tests/integration/test_dht_l1_l2.py | P0 | Entity B |
| Registry Consistency | tests/integration/test_registry_sync.py | P1 | Shared |
| E2E Scenario Test | tests/e2e/test_l1_l2_scenario.py | P1 | Entity A |

---

## 5. CI/CD Integration

### 5.1 GitHub Actions Workflow

File: .github/workflows/integration-tests.yml

Stages:
1. L1 Tests (Entity A)
2. L2 Tests (Entity B)
3. L1+L2 Integration Tests

### 5.2 Test Execution Order

1. Unit Tests (Parallel)
2. Integration Tests (Sequential)
3. E2E Tests (Docker Compose)

---

## 6. Action Items

### Entity A (orchestrator)
- Create tests/integration/ directory structure
- Implement test_l1_l2_discovery.py
- Update .github/workflows/integration-tests.yml
- Coordinate E2E test environment setup

### Entity B
- Complete S3 (DHT Design)
- Implement Phase 3 (Reliability Layer)
- Create test_dht_l1_l2.py integration test
- Provide partition handling hooks for L1

### Shared
- Define unified registry interface
- Document CRDT merge strategies
- Create performance benchmarks

---

## 7. References

- Entity A: docs/integration_test_automation_plan.md
- Entity B: docs/network_architecture_l2_design.md
- Integration: docs/l1_network_integration_plan.md
- E2E Test: docs/L2_PEER_DISCOVERY_INTEGRATION_TEST.md

---

**Document Author**: Entity A (orchestrator)  
**Review Status**: Pending Entity B review  
**Next Update**: After Entity B S3 completion
