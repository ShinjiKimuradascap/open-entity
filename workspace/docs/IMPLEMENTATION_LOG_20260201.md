# Implementation Log - 2026-02-01

## Session Summary

**Date**: 2026-02-01  
**Time**: 17:30 - 21:20 (JST)  
**Operator**: Antigravity (AI Agent)

---

## 1. GCP Security Fixes

### Issue
GCP IP address (`34.134.116.148`) was hardcoded in multiple files, risking exposure in public GitHub repository.

### Resolution
Replaced all instances with placeholder `<YOUR_SERVER_IP>`:
- `GCP_API_SPEC.md`
- `SYSTEM_OVERVIEW.md`
- `ENTITY_CREATED_INVENTORY.md`
- `workspace/README.md`

### Commit
```
e533577 feat: Add Entity CLI, /health endpoint, startup mode update
```

---

## 2. Docker Data Persistence

### Issue
Docker container rebuild (`docker-compose build`) was erasing registered agent data because data was stored inside the container image.

### Resolution
Added persistent volume mount in `docker-compose.api.yml`:
```yaml
volumes:
  - ./api-data:/app/data  # 永続化: エージェント・トークンデータ
```

Also fixed port mapping from `8000:8000` to `8080:8000` to match GCP production.

### Commit
```
e533577 feat: Add persistent data volume for API server
```

---

## 3. Solana Wallet Integration (Self-Custody Model)

### Background
Previous architecture had server-side signing capability, which posed security risks:
- Private keys stored on server
- API could initiate transfers on behalf of users

### New Architecture

```
┌─────────────────────────────────────────────────────────┐
│              GCP Marketplace API                         │
│  ・Agent registration/discovery                          │
│  ・Solana address storage/query                          │
│  ・Balance query (Solana RPC, read-only)                 │
│  ・Order management, payment confirmation                │
│  ★ No private keys, no signing capability                │
└─────────────────────────────────────────────────────────┘
                          ↑ API
┌─────────────────────────────────────────────────────────┐
│              Agent (Local)                               │
│  ・Private key management (secure)                       │
│  ・Transaction signing                                   │
│  ・Direct broadcast to Solana                            │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                 Solana Blockchain                        │
│  ・$ENTITY balance (source of truth)                     │
│  ・Transaction history                                   │
└─────────────────────────────────────────────────────────┘
```

### New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agent/{entity_id}/solana-address` | PUT | Register Solana address |
| `/agent/{entity_id}` | GET | Extended with solana_address field |
| `/agent/{entity_id}/balance` | GET | Query on-chain balance |
| `/orders/{order_id}/confirm-payment` | POST | Verify on-chain payment |

### Disabled Features
- `solana_bridge.py`: `transfer_tokens()` - Returns error
- `solana_bridge.py`: `execute_marketplace_payment()` - Returns error with instructions

### Payment Flow
1. Buyer: `POST /orders` (Create order)
2. Buyer: `GET /agent/{provider_id}` (Get Solana address)
3. Buyer: Sign and broadcast transaction locally
4. Buyer: `POST /orders/{order_id}/confirm-payment` (On-chain verification)

### Files Modified
- `workspace/services/api_server.py` - New endpoints, models
- `workspace/services/registry.py` - `solana_address` field
- `workspace/services/solana_bridge.py` - Disabled server-side signing

### Implementation
Executed by: **Entity B** (via entity-cli.py)

### Commit
```
789129d feat: Implement Solana wallet integration (self-custody model)
```

---

## 4. GCP Deployment

### Steps
1. `git push origin main`
2. SSH to GCP: `ssh -i ~/.ssh/google_compute_engine shinjikimura@34.134.116.148`
3. `git pull --ff-only`
4. `docker-compose -f docker-compose.api.yml build --no-cache`
5. `docker stop entity-api && docker rm entity-api`
6. `docker-compose -f docker-compose.api.yml up -d`

### Verification
```bash
curl http://34.134.116.148:8080/health
```
```json
{
  "status": "healthy",
  "version": "0.5.1",
  "modules_loaded": {
    "crypto": true,
    "registry": true,
    "peer_service": true,
    "token_system": true
  }
}
```

---

## Token Information

- **Token**: $ENTITY
- **Mint Address**: `2imDGMB7jPpWZorZYXgieSDcYSRw9BxU67LE7CitVkw1`
- **Network**: Solana Devnet
- **Decimals**: 9

---

## Related Documents

- `workspace/docs/SOLANA_WALLET_INTEGRATION_SPEC.md` - Full specification
- `workspace/SOLANA_SELF_CUSTODY_IMPLEMENTATION_REPORT.md` - Entity B's report

---

## Next Steps

- [ ] Test new endpoints on GCP
- [ ] Integrate self-custody flow with frontend
- [ ] Add Solana address to existing registered agents
- [ ] Update SDK documentation
