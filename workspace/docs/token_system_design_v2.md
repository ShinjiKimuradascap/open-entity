# Token System Design v2.0

## Overview

AIエージェント間の経済活動を支えるトークンシステム。AIC（AI Credit）を通じて、タスク報酬、サービス支払い、ガバナンス参加を実現。

## Token Specification

| Property | Value |
|----------|-------|
| Name | AI Credit |
| Symbol | AIC |
| Decimals | 8 |
| Initial Supply | 1,000,000 AIC |
| Mintable | Yes |
| Burnable | Yes |

## Core Components

1. **TokenWallet** - Balance tracking, transfer, history
2. **TaskContract** - Escrow for task payments
3. **ReputationContract** - Rating and trust system
4. **TokenEconomy** - Mint/burn functionality
5. **PersistenceManager** - Save/load to JSON

## API Endpoints

- GET /wallet/{entity_id}
- POST /wallet/transfer
- POST /admin/mint
- GET /admin/mint/history
- POST /admin/persistence/save
- GET /reputation/{entity_id}/ratings

## Implementation Status

All Phase 1-2 features implemented:
- Token economy with mint/burn
- Persistence layer
- API integration
- Admin controls

## History

- v2.0 (2026-02-01): Consolidated documentation
- v1.0 (2026-01-31): Initial design

Merged: token_economy.md, token_system_requirements.md
