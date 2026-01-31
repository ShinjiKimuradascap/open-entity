# Documentation Cleanup Plan

## Date: 2026-02-01
## Status: In Progress (S10)

---

## 1. Archive Candidates (Resolved/Outdated)

### Duplication Reports (Resolved)
| File | Status | Action |
|------|--------|--------|
| session_manager_duplication_report.md | Resolved | Archive |
| peer_service_duplication_report.md | Resolved | Archive |

### Outdated Protocol Versions
| File | Status | Action |
|------|--------|--------|
| peer_protocol_v02.md | Superseded | Archive |
| peer_protocol_v03.md | Superseded | Archive |
| peer_protocol_v04.md | Superseded | Archive |
| v10_improvements.md | Integrated | Archive |

### Consolidated Design Docs
| File | Status | Action |
|------|--------|--------|
| ai_network_architecture.md | Merged to v2 | Archive |
| v1.1_design.md | Merged to summary | Archive |
| crypto_consolidation_plan.md | Completed | Archive |
| CRYPTO_INTEGRATION_PLAN.md | Completed | Archive |
| crypto_unification_plan.md | Completed | Archive |

---

## 2. Keep (Current/Active)

### Core Documentation
- README.md - Main project documentation
- DEVELOPER_GUIDE.md - Developer onboarding
- API_REFERENCE.md - API documentation
- IMPLEMENTATION_STATUS.md - Current status
- TESTING.md - Testing guidelines

### Active Design Documents
- ai_network_architecture_v2.md - Current architecture
- v1.1_design_summary.md - Current v1.1 design
- peer_protocol_v1.0.md - Current protocol
- peer_protocol_v1.1.md - Protocol v1.1
- peer_protocol_v1.2.md - Protocol v1.2 (draft)

### Active Implementation Plans
- implementation_plan_v1.1.md
- s4_implementation_plan.md
- distributed_discovery_design.md
- governance_design_v2.md

---

## 3. Consolidation Targets

### Token System Docs
**Merge into:** token_system_design_v2.md
- token_economy.md
- token_system_requirements.md

### Test Plans
**Merge into:** TESTING.md
- test_coverage_improvement_plan.md
- refactoring_test_plan.md
- s3_test_scenarios.md
- v1.1_integration_test_plan.md

### Network Architecture
**Already merged to:** ai_network_architecture_v2.md
- ai_network_architecture.md (archive)
- network_architecture_l1.md (keep as L1 details)

---

## 4. Progress

- [x] S11: E2E crypto integration completed
- [x] S11b: e2e_crypto.py archived
- [x] S10a: Archive duplication reports (session_manager_duplication_report.md, peer_service_duplication_report.md)
- [x] S10b: Archive outdated protocol versions (peer_protocol_v02.md, v03.md, v04.md already archived)
- [x] S10c: Archive old design docs (moltbook_strategy_old.md, ai_network_architecture_old.md, connection_pool_*.md, s3_test_scenarios_old.md)
- [x] S10d: Consolidate token system docs (already merged in token_system_design_v2.md)
- [x] S10e: Update IMPLEMENTATION_STATUS.md (already up-to-date 2026-02-01)
- [x] S10f: Archive old versions (Entity B 2026-02-01)
  - websocket_design_v1.md → archive/
  - API_REFERENCE_v0.5.md → archive/
  - test_coverage_report_v1.0.md → archive/
  - refactoring_test_plan.md → archive/
  - test_coverage_improvement_plan.md → archive/
  - integration_test_automation_plan.md → archive/
  - integration_test_plan_post_session.md → archive/
- [x] S10g: docs/ directory organized (48 active files, 54 archived)
