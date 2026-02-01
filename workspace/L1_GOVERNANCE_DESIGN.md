# L1: Governance System Design

## Overview
On-chain governance for protocol decisions using $ENTITY stakes.

## Components

### Voting Power
- Based on staked $ENTITY amount
- Tier multipliers apply
- Minimum 1,000 $ENTITY to vote

### Proposal Types
1. Parameter changes
2. Treasury spending
3. Protocol upgrades
4. Dispute resolution

### Process
1. Create proposal (min 10,000 $ENTITY stake)
2. Voting period (7 days)
3. Quorum check (33% participation)
4. Execution (if majority approves)

## Implementation
- Solana program for on-chain voting
- Off-chain UI for proposal creation
- Automatic execution for approved proposals

## Files
- contracts/Governance.sol (existing)
- services/governance_engine.py (extend)
