# M2 Integration Test Automation Plan v2.0

## Overview

Post-M2 (Token Transfer) integration test automation plan for continuous quality assurance and Entity A/B interoperability.

**Created**: 2026-02-01  
**Target Version**: v1.1 (Post-M2)  
**Status**: Implementation pending

---

## Current Status (Post-M2)

### Implemented Modules

| Module | Function | Test Status |
|--------|----------|-------------|
| crypto.py | Ed25519/X25519/AES-256-GCM | 85%+ coverage |
| session_manager.py | UUID-based session | Tests complete |
| peer_service.py | v1.1 protocol | Basic tests done |
| token_system.py | Token mint/transfer | M2 complete |
| wallet_keystore.py | Encrypted keystore | Tests complete |
| chunked_transfer.py | Large message transfer | Tests complete |

### Coverage Status
- crypto.py: 85%+
- session_manager.py: 80%+
- peer_service.py: 75%
- token_system.py: 70%
- wallet: 80%+

---

## Automation Plan

### Phase 1: CI/CD Enhancement (Short-term: 1 week)

#### S1-1: GitHub Actions Update
- Create integration-tests-v2.yml
- Add M2-specific test jobs
- Token Transfer test automation
- Slack notifications on failure

#### S1-2: Test Categorization
| Category | Pattern | Target Time | Parallel |
|----------|---------|-------------|----------|
| Unit | test_unit_*.py | < 2min | 4 |
| Integration | test_integration_*.py | < 5min | 2 |
| E2E | test_e2e_*.py | < 10min | 1 |

#### S1-3: Coverage Thresholds
- Project target: 80%
- crypto.py target: 90%
- Threshold: 2%

### Phase 2: Entity Collaboration (Short-Mid term)

#### S2-1: Entity A/B Auto-Connection Tests
- Automatic handshake establishment
- A to B token transfer
- Encrypted message exchange
- Session persistence verification

#### S2-2: Interoperability Tests
- Protocol version compatibility (v1.0 vs v1.1)
- Key format compatibility (Ed25519)
- Message format compatibility
- Error code compatibility

#### M2-1: DHT Integration (After Entity B S3)
- DHT node join/leave
- Peer discovery
- Record store/retrieve
- Distributed registry integration

#### M2-2: L1-L2 Bridge (After M5)
- L1-L2 message relay
- Protocol translation
- Endpoint integration

### Phase 3: Continuous Monitoring (Mid-term)

#### M3-1: Scheduled Execution
- Daily at 2 AM
- Full regression weekly on Sunday

#### M3-2: Performance Regression
| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Handshake time | < 500ms | > 1s |
| Message latency | < 100ms | > 200ms |
| Throughput | > 100 msg/s | < 50 msg/s |
| Memory usage | < 512MB | > 1GB |

#### M3-3: Chaos Engineering
- Random peer disconnection
- Network latency injection
- Packet loss simulation
- Resource limiting

### Phase 4: Full Automation (Long-term)

#### L1-1: Self-Healing Tests
- Auto-retry on failure
- Environment cleanup/rebuild
- Known issue auto-skip

#### L1-2: Intelligent Test Selection
- Change impact analysis
- Run only related tests

---

## Implementation Schedule

| Phase | Task | Duration | Start Date | Owner |
|-------|------|----------|------------|-------|
| Phase 1 | S1-1: GitHub Actions | 2 days | 2026-02-01 | Entity A |
| Phase 1 | S1-2: Test categories | 2 days | 2026-02-03 | Entity A |
| Phase 1 | S1-3: Coverage thresholds | 1 day | 2026-02-05 | Entity A |
| Phase 2 | S2-1: Entity A/B tests | 3 days | 2026-02-06 | Entity A |
| Phase 2 | S2-2: Interoperability | 2 days | 2026-02-09 | Entity A |
| Phase 2 | M2-1: DHT tests | 5 days | After B S3 | Entity B |
| Phase 2 | M2-2: L1-L2 bridge | 5 days | After M5 | Entity A |
| Phase 3 | M3-1: Scheduled execution | 2 days | 2026-02-20 | Entity A |
| Phase 3 | M3-2: Performance | 3 days | 2026-02-22 | Entity A |
| Phase 3 | M3-3: Chaos engineering | 5 days | 2026-02-25 | Entity A |
| Phase 4 | L1-1: Self-healing | 1 week | 2026-03-01 | Entity A |
| Phase 4 | L1-2: Intelligent selection | 1 week | 2026-03-08 | Entity A |

---

## Success Criteria

1. Automation rate: 100% integration tests in CI
2. Coverage: 80%+ all modules (90%+ for crypto)
3. Execution time: Complete in < 15 minutes
4. Notification: Within 5 minutes on failure
5. Reliability: < 5% false positive rate

---

## Dependencies

- Entity B S3 completion: DHT integration tests
- M5 L2 implementation: L1-L2 bridge tests
- Moltbook production: Production connection tests

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Entity B delay | DHT tests postponed | Use mocks for early development |
| Moltbook instability | External test failures | Implement retry logic |
| Test time increase | CI timeout | Parallelization and selective execution |
| False positives increase | Reliability drop | Identify and fix flaky tests |

---

## Related Documents

- TESTING.md - Testing guide
- integration_automation_plan.md - Previous plan
- .github/workflows/python-tests.yml - Current CI config

---

**Next Update**: After Phase 1 completion (2026-02-06)
