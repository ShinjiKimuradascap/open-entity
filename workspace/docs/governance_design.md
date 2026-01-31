# Governance System Design v2.0

## Overview

Decentralized governance system for AI token economy.
Token holders can propose and vote on protocol changes.

## Architecture

- Proposal Module: Create and manage proposals
- Voting Module: Cast and tally votes
- Execution Module: Execute approved proposals
- Timelock Module: Security delay and emergency controls

## Core Components

### 1. Proposal Module

Data Model:
- id: UUID
- proposer: str
- title: str
- description: str
- proposal_type: ProposalType
- actions: List[Action]
- status: ProposalStatus
- voting_start/end: datetime
- votes_for/against/abstain: Decimal

Proposal Types:
- ParameterChange
- Upgrade
- TokenAllocation
- Emergency

Status Flow: Pending -> Active -> Succeeded -> Queued -> Executed

### 2. Voting Module

Features:
- Token-weighted voting power
- Delegation support
- For/Against/Abstain vote types

### 3. Execution Module

Flow:
1. Proposal Succeeded
2. Queue to timelock
3. Wait delay period
4. Execute actions
5. Verify results

### 4. Timelock Module

Security:
- Standard delay: 2 days
- Emergency delay: 4 hours
- Guardian pause capability
- 14-day grace period

## Configuration

| Parameter | Value |
|-----------|-------|
| MIN_TOKENS_TO_PROPOSE | 1000 AIC |
| MIN_TOKENS_TO_VOTE | 100 AIC |
| VOTING_PERIOD | 3 days |
| TIMELOCK_DELAY | 2 days |
| QUORUM_PERCENTAGE | 10% |
| APPROVAL_THRESHOLD | 51% |

## API Endpoints

Proposals: POST/GET /governance/proposals
Voting: POST /governance/proposals/{id}/vote
Execution: POST /governance/proposals/{id}/execute

## Implementation

Directory: services/governance/
Files: proposal.py, voting.py, execution.py, timelock.py, models.py, config.py

---

## 統合履歴 (Integration History)

| 日付 | 統合内容 | 備考 |
|------|---------|------|
| 2026-02-01 | v1.0版からv2.0へ更新 | 詳細設計を追加 |

- アーカイブ: `docs/archive/governance_design.md` (v1.0)
