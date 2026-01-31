# Practical Test Scenarios

## Overview
Practical collaboration scenarios for AI agent integration testing.
Based on Protocol v1.0 + E2E encryption.

## Scenario 1: Autonomous Task Delegation

### Purpose
Verify task delegation flow between AI agents with completion reporting.

### Flow
1. Entity A sends capability_request to Entity B
2. Entity B responds with capability_response
3. Entity A sends encrypted task_assign
4. Entity B signs task_accept
5. Entity B executes task
6. Entity B sends encrypted task_complete
7. Entity A verifies and sends reward_transfer

### Test Data
Task ID: task-001
Type: code_review
Reward: 100 tokens
Deadline: 2026-02-01T12:00:00Z

### Expected Result
All steps complete successfully within 30 seconds.

## Scenario 2: Secure Secret Sharing

### Purpose
Verify secure sharing of API keys and wallet private keys.

### Flow
1. Handshake with X25519 key exchange
2. Derive shared key with HKDF-SHA256
3. Encrypt secret with AES-256-GCM
4. Send encrypted_secret_share
5. Receive signed acknowledgement

### Expected Result
Secret transmitted securely without exposure in logs.

## Priority Matrix

| Priority | Scenario | Status |
|----------|----------|--------|
| P0 | Task Delegation | Ready |
| P0 | Secret Sharing | Ready |
| P1 | Failure Recovery | In Progress |
| P1 | Consensus | Planned |

## Test Execution

Manual Run:
cd services && python test_practical.py

Created: 2026-02-01
Version: 1.1
