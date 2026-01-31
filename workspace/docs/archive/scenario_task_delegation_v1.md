# Scenario: Autonomous Task Delegation v1.0

## Overview
AIエージェント間での自律的タスク委譲シナリオ詳細設計書。
Protocol v1.0準拠、トークン報酬付き。

---

## Participants

| Role | Entity | Responsibilities |
|------|--------|------------------|
| Delegator | Entity A (Orchestrator) | Task作成、委譲、検証、報酬支払い |
| Delegatee | Entity B (Worker) | Task受領、実行、完了報告 |
| Witness | Optional | Task完了の第三者検証 |

---

## Message Flow

1. capability_request - Entity A -> Entity B
2. capability_response - Entity B -> Entity A  
3. task_assign (encrypted) - Entity A -> Entity B
4. task_accept (signed) - Entity B -> Entity A
5. task_progress (optional) - Entity B -> Entity A
6. task_complete (encrypted) - Entity B -> Entity A
7. task_verification_request - Entity A -> Entity B
8. task_verification_response - Entity B -> Entity A
9. reward_transfer - Entity A -> Entity B
10. receipt_ack (signed) - Entity B -> Entity A

---

## State Machine

PENDING -> ASSIGNED -> IN_PROGRESS -> COMPLETED -> VERIFIED -> REWARDED

---

## Implementation Status

| Component | Status | File |
|-----------|--------|------|
| Message format | Done | task_delegation.py |
| State machine | Done | task_delegation.py |
| Escrow integration | WIP | reward_integration.py |
| Verification | TODO | task_verification.py |
| E2E test | TODO | test_scenario_task_delegation.py |

---

Created: 2026-02-01
Version: 1.0
