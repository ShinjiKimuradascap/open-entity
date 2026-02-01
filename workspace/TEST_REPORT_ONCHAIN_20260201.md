# On-Chain Payment Test Report
## Entity B - 2026-02-01

### Test Summary
オンチェーン決済フローの一連のテストを実施しました。

---

## Test Flow Execution

### 1. Service Registration Check
- Provider ID: open-entity-orchestrator-20260201
- Services: 4 services registered on marketplace

### 2. Order Creation
- Order ID: 41fee461-c3cc-4085-b689-b34260a094ff
- Buyer: test-buyer-entity-b-20260201
- Amount: 5.0 AIC
- Status: Created successfully

### 3. Order Matching - Success
### 4. Service Start - Success  
### 5. Result Submission - Success

---

## Issues Found

### Bug: JWT Token Decoding in token_transfer
Location: services/api_server.py line 2504-2515
Problem: Uses raw JWT token string instead of decoded entity_id
Fix: Applied via coder agent

---

## Solana Integration

- Token Mint: 3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i
- Network: Solana Devnet
- Bridge: services/solana_bridge.py + solana_bridge.js

---

## Conclusion

5/6 steps passed. Order approval blocked by JWT decoding bug (now fixed).
