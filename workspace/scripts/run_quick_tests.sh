#!/bin/bash
set -e

echo "=========================================="
echo "Quick Integration Tests"
echo "=========================================="

cd "$(dirname "$0")/.."
mkdir -p test_results

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0

run_quick_test() {
    local name=$1
    local cmd=$2
    echo -n "Testing $name... "
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}FAIL${NC}"
        FAILED=$((FAILED + 1))
    fi
}

echo ""
echo "Running quick unit tests..."
cd services

run_quick_test "crypto" "python test_crypto_integration.py"
run_quick_test "signature" "python test_signature.py"
run_quick_test "session" "python test_session_manager.py"

cd ..

echo ""
echo "=========================================="
echo -e "${GREEN}Passed:${NC} $PASSED"
echo -e "${RED}Failed:${NC} $FAILED"
echo "=========================================="

[ $FAILED -eq 0 ]
