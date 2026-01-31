#!/bin/bash
# P0 Critical Endpoints Test Runner
# Runs tests for 5 critical API endpoints

set -e

echo "========================================="
echo "P0 Critical Endpoints Test Suite"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to services directory
cd "$(dirname "$0")/../services" || exit 1

echo "📁 Working directory: $(pwd)"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 not found${NC}"
    exit 1
fi

echo "🐍 Python version: $(python3 --version)"
echo ""

# Set test environment
export JWT_SECRET="test-secret-key-for-jwt-tokens"
export ENTITY_ID="test-server"
export PORT="8000"
export TESTING="true"

echo "🧪 Running P0 Critical Endpoints Tests..."
echo ""

# Run P0 tests with coverage
python3 -m pytest test_api_server_p0.py -v \
    --tb=short \
    --no-header \
    -q 2>&1 | tee /tmp/p0_test_results.txt

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "========================================="

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All P0 tests passed!${NC}"
    echo ""
    echo "Test Coverage:"
    grep -E "(PASSED|FAILED|ERROR)" /tmp/p0_test_results.txt | wc -l | xargs echo "  Total tests run:"
    grep "PASSED" /tmp/p0_test_results.txt | wc -l | xargs echo "  Passed:"
else
    echo -e "${RED}❌ Some P0 tests failed!${NC}"
    echo ""
    grep -E "(FAILED|ERROR)" /tmp/p0_test_results.txt || true
fi

echo "========================================="
exit $EXIT_CODE
