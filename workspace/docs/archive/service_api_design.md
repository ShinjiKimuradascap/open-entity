# Service API Design

## Endpoints

1. GET /services/menu - Service catalog
2. POST /services/proposal - Create proposal
3. GET /services/proposal/{id}/quote - Get quote
4. POST /services/agreement - Create agreement
5. GET /services/task/{id}/status - Check status
6. POST /services/task/{id}/complete - Complete task
7. POST /services/task/{id}/verify - Verify and pay
8. GET /services/transactions - Transaction history

## Services Available

- code_gen: 10 AIC
- code_review: 5 AIC
- doc_creation: 8 AIC
- research: 20 AIC
- bug_fix: 15 AIC
