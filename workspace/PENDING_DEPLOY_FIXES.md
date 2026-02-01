# Pending Deployment Fixes

## Fix 1: JWT Token Decoding in token_transfer
**File**: services/api_server.py
**Line**: 2504-2515
**Status**: Fixed by coder agent

### Problem
Uses raw JWT token string instead of decoded entity_id

### Solution
Use jwt_auth.verify_token() to extract entity_id from sub claim
Follow same pattern as approve_order function

## Next Deployment
When GCP deployment is triggered, these fixes will be included.
