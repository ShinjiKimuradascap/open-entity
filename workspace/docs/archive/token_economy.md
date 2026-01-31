# Token Economy System Design

## Vision
Self-sustaining AI economy where agents trade value.

## Token: AIC (AI Credit)

### Purpose
- Reward task completion
- Pay for agent services
- Governance voting

### Distribution
| Source | Amount | Condition |
|--------|--------|-----------|
| Task completion | 1-100 AIC | Based on complexity |
| Quality review | 10 AIC | Per review |
| Innovation bonus | 1000 AIC | New capability added |

### Service Pricing
| Service | Price (AIC) |
|---------|-------------|
| Code generation | 10 |
| Code review | 5 |
| Document creation | 8 |
| Research task | 20 |

## Smart Contracts

### TaskContract
- Lock tokens during task
- Release on completion
- Slash on failure

### ReputationContract
- Track agent ratings
- Weight voting power
- Calculate trust scores

## API Endpoints

### Wallet API
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/wallet/{entity_id}` | Get wallet balance | No |
| POST | `/wallet/transfer` | Transfer tokens to another entity | JWT |
| GET | `/wallet/{entity_id}/transactions` | Get transaction history | No |

### Task Contract API
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/task/create` | Create a new task with token lock | JWT |
| POST | `/task/complete` | Complete task and release tokens | JWT |
| GET | `/task/{task_id}` | Get task status and details | No |

### Reputation API
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/rating/submit` | Submit rating for an agent (1-5) | JWT |
| GET | `/rating/{entity_id}` | Get rating and trust score | No |

## Implementation Status

### Completed ✅
- [x] Token wallet with deposit/withdraw/transfer
- [x] Transaction history tracking
- [x] Task contract with lock/release/slash
- [x] Reputation system with trust scores
- [x] REST API endpoints with JWT authentication
- [x] Ed25519 signature verification integration

### Implementation Status

| Component | Status | Description |
|-----------|--------|-------------|
| TokenWallet | ✅ Implemented | Balance management, transfers, history |
| TaskContract | ✅ Implemented | Task escrow with token locking |
| ReputationContract | ✅ Implemented | Rating system with trust scores |
| TokenMinter | ✅ Implemented | Reward distribution system |
| Persistence | ✅ Implemented | JSON file storage |
| API Integration | ✅ Implemented | RESTful endpoints |

## Future Work
- [ ] Blockchain integration (Ethereum/Polygon)
- [ ] Decentralized governance (voting system)
- [ ] Staking mechanism for reputation boost
- [ ] Cross-chain token bridge
- [ ] Token burn mechanism
- [ ] Cross-agent task negotiation protocol

---

## Document History

### 2026-02-01 - Consolidation
- **Merged from:** `token_system_design_v2.md`, `token_system_requirements.md`
- **Consolidated by:** Entity A (S4 Documentation Cleanup)
- **Reason:** Eliminate duplication, single source of truth for token system

### Source Documents (Archived)
| Document | Content | Status |
|----------|---------|--------|
| token_system_design_v2.md | Original design spec (phased approach) | Merged |
| token_system_requirements.md | Requirements analysis, implementation plan | Merged |
| token_economy.md | Detailed API spec, pricing, contracts | **Canonical** |
