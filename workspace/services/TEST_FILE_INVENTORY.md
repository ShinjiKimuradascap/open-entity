# Test File Inventory

## Overview
This document catalogs all test files in the project and identifies duplicates or obsolete files.

## Test File List (22 files total)

### Root Directory
1. `test_persistence.py` - ?
2. `test_import.py` - Import verification
3. `test_entity_b_check.py` - Entity B connectivity check

### services/ Directory

#### Core Test Files (Maintained)
| File | Purpose | Status |
|------|---------|--------|
| `test_peer_service.py` | Main peer service test (asyncio) | Active |
| `test_security.py` | Security feature tests | Active |
| `test_crypto_integration.py` | Crypto integration (pytest) | Active |
| `test_e2e_crypto.py` | E2E encryption tests | Active |
| `test_api_server.py` | API server tests | Active |
| `test_session_manager.py` | Session management tests | Active |

#### Potentially Duplicate/Obsolete
| File | Concern | Action |
|------|---------|--------|
| `test_peer_service_v1.py` | Older version | Check if needed |
| `test_peer_service_pytest.py` | pytest version | Merge with main |
| `test_practical.py` | Practical tests | Review |
| `test_api_server_extended.py` | Extended API tests | Review |
| `test_api_integration.py` | API integration | May overlap |
| `test_endpoints_manual.py` | Manual tests | Obsolete? |
| `test_signature.py` | Signature tests | Overlaps with crypto_integration |
| `test_integration.py` | Integration tests | Review scope |
| `test_integration_token.py` | Token integration | Review |
| `test_wallet.py` | Wallet tests | Active? |
| `test_wallet_persistence.py` | Wallet persistence | Active? |
| `test_task_verification.py` | Task verification | Active? |
| `test_token_integration.py` | Token integration | Active? |
| `test_moltbook_integration.py` | Moltbook integration | Active |
| `test_moltbook_identity_client.py` | Identity client | Active |
| `test_task_completion_verifier.py` | Task completion | Review |

## Duplicate Analysis

### Crypto Tests (Multiple files)
- `test_crypto_integration.py` - Pytest format
- `test_signature.py` - Overlapping signature tests
- `test_security.py` - Security including crypto
- `test_e2e_crypto.py` - E2E encryption

**Recommendation**: Consolidate into `test_crypto_integration.py`

### Peer Service Tests
- `test_peer_service.py` - Main asyncio test (1,475 lines)
- `test_peer_service_v1.py` - Older version
- `test_peer_service_pytest.py` - pytest version

**Recommendation**: Keep `test_peer_service.py` as primary

### API Tests
- `test_api_server.py`
- `test_api_server_extended.py`
- `test_api_integration.py`

**Recommendation**: Consolidate into `test_api_server.py`

## Action Plan

1. **Phase 1**: Identify unused test files (check git history)
2. **Phase 2**: Consolidate duplicate test coverage
3. **Phase 3**: Archive obsolete tests to `tests/archive/`
4. **Phase 4**: Update documentation

## Crypto Module Status

Current state:
- `crypto.py` - Compatibility wrapper (PyNaCl + cryptography mix)
- `crypto_utils.py` - Primary crypto library (cryptography-based)
- `e2e_crypto.py` - E2E layer (depends on crypto.py)

Recommendation: Complete migration to `crypto_utils.py` as primary library.
