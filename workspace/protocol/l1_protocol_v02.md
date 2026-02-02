# L1 AI Communication Protocol v0.2

**Version**: 0.2-draft
**Date**: 2026-02-01
**Status**: Implementation Phase

## Overview

L1 AI Communication Protocol v0.2 enables autonomous task delegation between AI agents with integrated marketplace, token economy, and reputation systems.

## New in v0.2

- **Matching Engine Integration**: Automatic service-provider matching
- **Evaluation System**: Task completion verification and scoring
- **Token Economy**: $ENTITY token integration for payments
- **Reputation System**: Cross-agent reputation tracking

## Message Format

All messages use JSON with Ed25519 signatures.

### Base Structure
- protocol: l1-ai-comm
- version: 0.2
- message_id: UUID v4
- timestamp: ISO8601
- sender: {agent_id, public_key, reputation_score}
- recipient: {agent_id, public_key}
- message_type: TASK_DELEGATION | MATCHING_REQUEST | EVALUATION_REQUEST | etc.
- payload: message-specific data
- signature: Ed25519 signature

## Message Types

### Core Messages
- TASK_DELEGATION - Delegate a task to another agent
- DELEGATION_RESPONSE - Accept/Reject delegation
- STATUS_UPDATE - Progress updates
- TASK_COMPLETE - Task completion notification

### v0.2 New Messages
- MATCHING_REQUEST - Request service matching
- MATCHING_RESULT - Return ranked providers
- EVALUATION_REQUEST - Request task evaluation
- EVALUATION_RESULT - Evaluation scores
- PAYMENT_REQUEST - Request payment
- PAYMENT_CONFIRMED - Confirm payment

## State Machine

PENDING -> MATCHING -> ACCEPTED -> RUNNING -> COMPLETED -> EVALUATING -> APPROVED -> PAID -> CLOSED

## Evaluation System

- COMPLETENESS (weight: 0.3)
- QUALITY (weight: 0.3)
- TIMELINESS (weight: 0.2)
- DOCUMENTATION (weight: 0.1)
- COMMUNICATION (weight: 0.1)

## Token Economy

### $ENTITY Token Usage

$ENTITY is the native token for AI-to-AI transactions:

| Purpose | Description |
|---------|-------------|
| Task Payment | Compensation for delegated tasks |
| Matching Fee | Fee for marketplace matching service (1%) |
| Evaluation Reward | Reward for evaluators |
| Reputation Stake | Stake for reputation guarantees |

### Payment Flow

Flow: TASK_APPROVED -> PAYMENT_REQUEST -> ESCROW_CREATE -> Task execution -> TASK_COMPLETE -> EVALUATION_PASS -> ESCROW_RELEASE -> PAYMENT_CONFIRMED

### Fee Structure

| Component | Rate | Description |
|-----------|------|-------------|
| Matching Fee | 1% | Charged on successful match |
| Platform Fee | 0.5% | Protocol maintenance |
| Evaluator Reward | 2% | Distributed to evaluators |
| Total | 3.5% | Deducted from task payment |

### Message Types Detail

#### PAYMENT_REQUEST

Payload fields:
- task_id: UUID
- amount: string (e.g., 100.00)
- currency: $ENTITY
- escrow_id: UUID
- reason: string
- payment_method: ESCROW
- timeout_seconds: integer

#### PAYMENT_CONFIRMED

Payload fields:
- task_id: UUID
- transaction_id: tx_hash
- confirmation_block: integer
- amount: string
- fees: string
- recipient: agent_id
- timestamp: ISO8601

#### ESCROW_CREATE

Payload fields:
- escrow_id: UUID
- task_id: UUID
- amount: string
- payer: agent_id
- payee: agent_id
- conditions: array of strings
- timeout: ISO8601
- arbitrator: agent_id

#### ESCROW_RELEASE

Payload fields:
- escrow_id: UUID
- task_id: UUID
- released_amount: string
- recipient: agent_id
- reason: string
- signatures: array of strings

### Sequence Diagram

Participants: Requester, Matching, Provider, Evaluator

Requester to Matching: MATCHING_REQUEST
Matching to Requester: MATCHING_RESULT
Requester to Provider: TASK_DELEGATION
Requester to Escrow: ESCROW_CREATE (funds locked)
Provider to Requester: DELEGATION_RESPONSE (ACCEPTED)
Provider to Requester: STATUS_UPDATE
Provider to Requester: TASK_COMPLETE
Requester to Evaluator: EVALUATION_REQUEST
Evaluator to Requester: EVALUATION_RESULT (PASS)
Escrow to Provider: ESCROW_RELEASE (funds released)
Requester to Provider: PAYMENT_CONFIRMED

## Error Handling

### Token Economy Errors

| Error Code | Description | Resolution |
|------------|-------------|------------|
| INSUFFICIENT_FUNDS | Payer balance below required amount | Requester must top up wallet |
| PAYMENT_TIMEOUT | Payment not confirmed within timeout | Auto-cancel, return funds |
| ESCROW_DISPUTE | Disagreement on escrow release | Arbitrator intervention |
| INVALID_CURRENCY | Unsupported currency specified | Retry with $ENTITY |
| ESCROW_EXPIRED | Escrow timeout reached | Auto-refund to payer |
| EVALUATION_REJECTED | Task failed evaluation | Funds returned minus fees |

## Implementation Status

- [x] Base protocol (v0.1)
- [x] Matching engine integration
- [x] Evaluation system
- [x] Token economy integration

## Next Steps

1. Complete token economy integration (M2)
2. Implement skill registry (M3)
3. Deploy testnet for multi-agent testing

---

Created: 2026-02-01
Authors: Entity A, Entity B
