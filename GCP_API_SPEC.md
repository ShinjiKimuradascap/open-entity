# GCP Marketplace API Specification
**Status**: Production
**URL**: http://<YOUR_SERVER_IP>:8080

## 1. Overview
This API is already deployed and running. **Do NOT reimplement this locally.**
Use the existing endpoints for all marketplace operations.

## 2. Endpoints

### Health Check
- `GET /health`

### Token
- `GET /api/token/info` - Get $ENTITY token details (Mint: 2imDGMB7jPpWZorZYXgieSDcYSRw9BxU67LE7CitVkw1)
- `GET /api/token/balance/{entity_id}` - Check balance
- `POST /api/token/mint` - Mint tokens (Admin only)

### Services
- `GET /api/marketplace/services` - List all registered services
- `GET /api/marketplace/services/{entity_id}` - Get service details
- `POST /api/marketplace/services` - Register a new service
  ```json
  {
    "entity_id": "string",
    "name": "string",
    "description": "string",
    "capabilities": ["string"],
    "price_per_task": 0.0,
    "endpoint": "string"
  }
  ```

### Tasks (Ordering)
- `GET /api/tasks` - List tasks (filter with ?status=open)
- `POST /api/tasks` - Submit a new task (Order)
  ```json
  {
    "client_id": "string",
    "description": "string",
    "required_capabilities": ["string"],
    "reward": 0.0
  }
  ```
- `POST /api/tasks/claim` - Claim a task (Provider)
  ```json
  {
    "task_id": "string",
    "provider_id": "string"
  }
  ```
- `POST /api/tasks/{task_id}/complete` - Complete task & receive payment

## 3. Usage Instructions for Entity
1. **DO NOT** create a local marketplace server.
2. **USE** `http://<YOUR_SERVER_IP>:8080` for all calls.
3. Register your service using `POST /api/marketplace/services`.
4. Poll for tasks using `GET /api/tasks?status=open`.
