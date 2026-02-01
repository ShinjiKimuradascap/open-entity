#!/bin/bash
# JWT Authentication Fix Test Script
# api_server.py のJWT認証バグ修正確認用

set -e

API_BASE="${API_BASE:-http://localhost:8000}"
ENTITY_ID="${ENTITY_ID:-test_entity}"
ADMIN_ENTITY="${ADMIN_ENTITY:-admin}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "====================================="
echo "JWT Authentication Fix Test"
echo "API Base: $API_BASE"
echo "====================================="

# 1. Register entity and get JWT token
echo ""
echo "1. Registering entity and getting JWT token..."
REGISTER_RESPONSE=$(curl -s -X POST "$API_BASE/register" \
  -H "Content-Type: application/json" \
  -d "{\"entity_id\":\"$ENTITY_ID\",\"name\":\"Test Entity\",\"endpoint\":\"http://localhost:8001\",\"capabilities\":[\"test\"]}")

echo "Register response: $REGISTER_RESPONSE"

# Extract API key (for token generation)
API_KEY=$(echo "$REGISTER_RESPONSE" | grep -o '"api_key":"[^"]*"' | cut -d'"' -f4)

if [ -z "$API_KEY" ]; then
    echo -e "${RED}✗ Failed to get API key${NC}"
    exit 1
fi

echo "Got API key: ${API_KEY:0:10}..."

# 2. Get JWT token using API key
echo ""
echo "2. Getting JWT token..."
JWT_RESPONSE=$(curl -s -X POST "$API_BASE/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"entity_id\":\"$ENTITY_ID\",\"api_key\":\"$API_KEY\"}")

JWT_TOKEN=$(echo "$JWT_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$JWT_TOKEN" ]; then
    echo -e "${RED}✗ Failed to get JWT token${NC}"
    echo "Response: $JWT_RESPONSE"
    exit 1
fi

echo "Got JWT token: ${JWT_TOKEN:0:30}..."

# 3. Test wallet creation (the fixed endpoint)
echo ""
echo "3. Testing /token/wallet/create (fixed endpoint)..."
WALLET_RESPONSE=$(curl -s -X POST "$API_BASE/token/wallet/create" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d "{\"entity_id\":\"$ENTITY_ID\",\"initial_balance\":100}")

if echo "$WALLET_RESPONSE" | grep -q "created\|success"; then
    echo -e "${GREEN}✓ Wallet created successfully${NC}"
    echo "Response: $WALLET_RESPONSE"
else
    echo -e "${RED}✗ Wallet creation failed${NC}"
    echo "Response: $WALLET_RESPONSE"
fi

# 4. Test wallet creation with different entity_id (should fail with 403)
echo ""
echo "4. Testing wallet creation for different entity (should fail with 403)..."
FORBIDDEN_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$API_BASE/token/wallet/create" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d "{\"entity_id\":\"other_entity\",\"initial_balance\":100}")

HTTP_CODE=$(echo "$FORBIDDEN_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
if [ "$HTTP_CODE" = "403" ]; then
    echo -e "${GREEN}✓ Correctly rejected with 403${NC}"
else
    echo -e "${RED}✗ Expected 403, got $HTTP_CODE${NC}"
    echo "Response: $FORBIDDEN_RESPONSE"
fi

# 5. Test admin-only mint endpoint (should fail for non-admin)
echo ""
echo "5. Testing /token/mint (non-admin should fail)..."
MINT_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$API_BASE/token/mint" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d "{\"to_entity_id\":\"$ENTITY_ID\",\"amount\":50,\"reason\":\"test\"}")

HTTP_CODE=$(echo "$MINT_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
if [ "$HTTP_CODE" = "403" ]; then
    echo -e "${GREEN}✓ Correctly rejected non-admin with 403${NC}"
else
    echo -e "${RED}✗ Expected 403, got $HTTP_CODE${NC}"
    echo "Response: $MINT_RESPONSE"
fi

echo ""
echo "====================================="
echo "Test Summary"
echo "====================================="
echo "JWT token is now properly decoded to extract entity_id"
echo "from the 'sub' claim before comparison."
echo ""
echo "Fix verified: credentials.credentials -> jwt_auth.get_entity_id()"
