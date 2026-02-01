# $ENTITY Token Bridge Design
## Internal AIC ↔ On-Chain $ENTITY Bridge

## Overview
Bridge design for swapping between internal AIC tokens and Solana $ENTITY tokens.

## Token Information

| Property | Value |
|----------|-------|
| Token Name | ENTITY Token |
| Symbol | $ENTITY |
| Network | Solana Devnet |
| Mint Address | 2imDGMB7jPpWZorZYXgieSDcYSRw9BxU67LE7CitVkw1 |
| Total Supply | 1,000,000,000 |
| Decimals | 9 |

## Exchange Rate
1 AIC = 1 $ENTITY (1:1 peg)

## Bridge Flows
- AIC to $ENTITY: Lock AIC, Mint $ENTITY
- $ENTITY to AIC: Burn $ENTITY, Release AIC

## Implementation Phases
- Phase 1: Devnet Testing
- Phase 2: Integration  
- Phase 3: Mainnet Launch

Created: 2026-02-01