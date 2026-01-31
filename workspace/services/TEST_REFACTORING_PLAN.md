# Test File Refactoring Plan

## Current State: 35 Test Files

### Peer Service Tests (6 files)
- test_peer_service.py - Main asyncio test - KEEP
- test_peer_service_v1.py - Older version - DEPRECATE
- test_peer_service_e2e.py - MERGE
- test_peer_service_integration.py - MERGE
- test_practical.py - REVIEW
- test_wake_up_protocol.py - MERGE

### Crypto Tests (4 files)
- test_crypto_integration.py - KEEP
- test_e2e_crypto.py - KEEP
- test_security.py - KEEP
- test_signature.py - MERGE

### API Tests (2 files)
- test_api_server.py - KEEP
- test_api_integration.py - MERGE

### Integration Tests (5 files)
- test_integration.py - KEEP
- test_integration_scenarios.py - MERGE
- test_v1.1_integration.py - MERGE
- test_scenario_task_delegation.py - MERGE
- test_endpoints_manual.py - DEPRECATE

### Token/Wallet Tests (6 files)
- test_wallet.py - KEEP
- test_wallet_persistence.py - MERGE
- test_token_integration.py - KEEP
- test_token_system_integration.py - MERGE
- test_token_transfer.py - MERGE
- test_reward_integration.py - MERGE

### Task Tests (3 files)
- test_task_verification.py - KEEP
- test_task_verification_v2.py - MERGE
- test_task_completion_verifier.py - MERGE

### Moltbook Tests (2 files)
- test_moltbook_integration.py - KEEP
- test_moltbook_identity_client.py - KEEP

## Consolidation Target: 15-18 files (from 35)

## Action Plan
1. Archive obsolete tests to tests/archive/
2. Merge duplicate coverage
3. Update imports
4. Verify all tests pass
