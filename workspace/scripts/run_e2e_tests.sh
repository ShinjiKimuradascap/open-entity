#!/bin/bash
set -e

echo "=========================================="
echo "S3 Practical Test Suite - E2E Test Runner"
echo "=========================================="

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 作業ディレクトリに移動
cd "$(dirname "$0")/.."

echo ""
echo "Step 1: Stopping any existing containers..."
docker compose -f docker-compose.test.yml down --remove-orphans 2>/dev/null || true

echo ""
echo "Step 2: Building test images..."
docker compose -f docker-compose.test.yml build

echo ""
echo "Step 3: Starting test services..."
docker compose -f docker-compose.test.yml up -d entity-a entity-b

echo ""
echo "Step 4: Waiting for services to be healthy..."
max_attempts=30
attempt=1

while [ $attempt -le $max_attempts ]; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1 && \
       curl -s http://localhost:8002/health > /dev/null 2>&1; then
        echo -e "${GREEN}Services are ready!${NC}"
        break
    fi
    echo "Attempt $attempt/$max_attempts: Waiting for services..."
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -gt $max_attempts ]; then
    echo -e "${RED}Services failed to start${NC}"
    docker compose -f docker-compose.test.yml logs
    exit 1
fi

echo ""
echo "Step 5: Running E2E tests..."
echo ""

# テスト結果ディレクトリ作成
mkdir -p test_results

# ローカルでテスト実行（Docker内でも可）
if command -v pytest &> /dev/null; then
    echo "Running tests locally..."
    
    # 5a: E2E Crypto Integration Tests
    echo ""
    echo "Step 5a: Running E2E Crypto Integration Tests..."
    PYTHONPATH=./services python -m pytest services/test_e2e_crypto_integration.py -v --tb=short 2>&1 | tee test_results/e2e_crypto_integration.log
    CRYPTO_TEST_RESULT=${PIPESTATUS[0]}
    
    if [ $CRYPTO_TEST_RESULT -eq 0 ]; then
        echo -e "${GREEN}✅ E2E Crypto Integration Tests passed${NC}"
    else
        echo -e "${YELLOW}⚠️ E2E Crypto Integration Tests had failures${NC}"
    fi
    
    # 5b: E2E Peer Communication Tests
    echo ""
    echo "Step 5b: Running E2E Peer Communication Tests..."
    PYTHONPATH=./services python -m pytest tests/e2e/ -v --tb=short 2>&1 | tee test_results/e2e_peer_communication.log
    PEER_TEST_RESULT=${PIPESTATUS[0]}
    
    if [ $PEER_TEST_RESULT -eq 0 ]; then
        echo -e "${GREEN}✅ E2E Peer Communication Tests passed${NC}"
    else
        echo -e "${YELLOW}⚠️ E2E Peer Communication Tests had failures${NC}"
    fi
    
    # 5c: E2E Crypto Unit Tests (standalone)
    echo ""
    echo "Step 5c: Running standalone E2E crypto tests..."
    PYTHONPATH=./services python services/test_e2e_crypto_integration.py 2>&1 | tee test_results/e2e_crypto_standalone.log
    STANDALONE_RESULT=${PIPESTATUS[0]}
    
    if [ $STANDALONE_RESULT -eq 0 ]; then
        echo -e "${GREEN}✅ Standalone E2E crypto tests passed${NC}"
    else
        echo -e "${YELLOW}⚠️ Standalone E2E crypto tests had failures${NC}"
    fi
    
else
    echo "Running tests in Docker..."
    docker compose -f docker-compose.test.yml -f docker-compose.e2e.yml up e2e-test-runner
fi

echo ""
echo "Step 6: Cleaning up..."
docker compose -f docker-compose.test.yml down

echo ""
echo "Step 6: Generating test summary..."
echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}E2E Tests Summary${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""

# テスト結果サマリー
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

if [ -f test_results/e2e_crypto_integration.log ]; then
    CRYPTO_PASSED=$(grep -c "PASSED" test_results/e2e_crypto_integration.log 2>/dev/null || echo "0")
    CRYPTO_FAILED=$(grep -c "FAILED" test_results/e2e_crypto_integration.log 2>/dev/null || echo "0")
    echo -e "Crypto Integration: ${GREEN}$CRYPTO_PASSED passed${NC}, ${RED}$CRYPTO_FAILED failed${NC}"
    TOTAL_TESTS=$((TOTAL_TESTS + CRYPTO_PASSED + CRYPTO_FAILED))
    PASSED_TESTS=$((PASSED_TESTS + CRYPTO_PASSED))
    FAILED_TESTS=$((FAILED_TESTS + CRYPTO_FAILED))
fi

if [ -f test_results/e2e_peer_communication.log ]; then
    PEER_PASSED=$(grep -c "PASSED" test_results/e2e_peer_communication.log 2>/dev/null || echo "0")
    PEER_FAILED=$(grep -c "FAILED" test_results/e2e_peer_communication.log 2>/dev/null || echo "0")
    echo -e "Peer Communication: ${GREEN}$PEER_PASSED passed${NC}, ${RED}$PEER_FAILED failed${NC}"
    TOTAL_TESTS=$((TOTAL_TESTS + PEER_PASSED + PEER_FAILED))
    PASSED_TESTS=$((PASSED_TESTS + PEER_PASSED))
    FAILED_TESTS=$((FAILED_TESTS + PEER_FAILED))
fi

echo ""
echo -e "Total: ${GREEN}$PASSED_TESTS passed${NC}, ${RED}$FAILED_TESTS failed${NC}"
echo ""

# 終了コード判定
if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${YELLOW}⚠️ Some tests failed. Check test_results/ for details.${NC}"
    EXIT_CODE=1
else
    echo -e "${GREEN}✅ All tests passed!${NC}"
    EXIT_CODE=0
fi

echo ""
echo "Step 7: Cleaning up..."
docker-compose -f docker-compose.test.yml down --remove-orphans 2>/dev/null || true

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}E2E Tests Completed!${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo "Test results saved to: test_results/"
echo ""

exit $EXIT_CODE
