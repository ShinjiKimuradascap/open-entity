# P1 High Priority Endpoints Test Plan
Priority: High | Timeline: This Week

## Overview
P1 priority endpoints cover the core economic functionality of the platform:
- **Wallet operations**: Balance queries, transfers, transaction history
- **Task management**: Task creation, completion, status tracking
- **Rating system**: Reputation tracking and rating submission

## Test Implementation Plan

### 1. Wallet Endpoints

#### 1.1 GET /wallet/{entity_id}
Purpose: Get wallet balance for an entity
Test Cases:
- Get balance for existing wallet with tokens
- Get balance for existing wallet with zero tokens
- Get balance for non-existent entity (404)
- Get balance with invalid entity_id format (400)

Dependencies: Mock TokenWallet, Mock token_economy

#### 1.2 POST /wallet/transfer
Purpose: Transfer tokens between entities
Test Cases:
- Valid transfer between two existing wallets
- Transfer with insufficient balance (400)
- Transfer to non-existent recipient (404)
- Transfer with invalid amount (negative/zero) (400)
- Transfer without proper authentication (401)
- Transfer with replay attack protection

Dependencies: Mock TokenWallet, Mock token_economy, Auth middleware

#### 1.3 GET /wallet/{entity_id}/transactions
Purpose: Get transaction history
Test Cases:
- Get transactions for entity with history
- Get transactions for entity with no history
- Pagination with limit/offset parameters
- Get transactions for non-existent entity (404)
- Filter by transaction type (send/receive)

Dependencies: Mock TokenWallet, Mock PersistenceManager

#### 1.4 GET /wallet/{entity_id}/summary
Purpose: Get transaction summary statistics
Test Cases:
- Get summary for entity with transaction history
- Get summary for entity with no transactions
- Verify total sent/received calculations
- Non-existent entity returns empty summary

Dependencies: Mock TokenWallet, Mock PersistenceManager

### 2. Task Endpoints

#### 2.1 POST /task/create
Purpose: Create a new task
Test Cases:
- Create task with valid parameters
- Create task with invalid parameters (missing required fields)
- Create task with zero/negative reward (400)
- Create task with invalid deadline format (400)
- Create task when creator has insufficient balance (400)
- Verify task ID is generated correctly

Dependencies: Mock TaskContract, Mock TokenWallet, Auth middleware

#### 2.2 POST /task/complete
Purpose: Mark task as completed
Test Cases:
- Complete task as assigned agent
- Complete task that doesn't exist (404)
- Complete task that is already completed (400)
- Complete task without proper authorization (403)
- Verify reward distribution on completion

Dependencies: Mock TaskContract, Mock TokenWallet, Auth middleware

#### 2.3 GET /task/{task_id}
Purpose: Get task status and details
Test Cases:
- Get existing task details
- Get non-existent task (404)
- Get task with invalid ID format (400)
- Verify all task fields are returned

Dependencies: Mock TaskContract

### 3. Rating Endpoints

#### 3.1 POST /rating/submit
Purpose: Submit rating for an entity
Test Cases:
- Submit valid rating (1-5 stars)
- Submit rating with invalid score (0 or 6) (400)
- Submit duplicate rating from same entity (idempotent)
- Submit rating without authentication (401)
- Submit rating for non-existent entity (404)

Dependencies: Mock ReputationContract, Auth middleware

#### 3.2 GET /rating/{entity_id}
Purpose: Get entity rating information
Test Cases:
- Get rating for entity with ratings
- Get rating for entity with no ratings
- Get rating for non-existent entity (404)
- Verify average calculation is correct

Dependencies: Mock ReputationContract

## Implementation Order

1. Phase 1: Wallet Tests (Day 1-2)
   - /wallet/{entity_id} (GET)
   - /wallet/transfer (POST)
   - /wallet/{entity_id}/transactions (GET)
   - /wallet/{entity_id}/summary (GET)

2. Phase 2: Task Tests (Day 3-4)
   - /task/{task_id} (GET)
   - /task/create (POST)
   - /task/complete (POST)

3. Phase 3: Rating Tests (Day 5)
   - /rating/{entity_id} (GET)
   - /rating/submit (POST)

## Success Criteria

1. All P1 endpoints have comprehensive test coverage
2. Test coverage increases from 15.7% to 30%+
3. All tests pass in CI/CD pipeline
4. Mock implementations are reusable for future tests

## Dependencies

- pytest-asyncio for async test support
- pytest-mock for mocking utilities
- fastapi.testclient.TestClient for HTTP testing
- P0 test infrastructure (conftest.py fixtures)
