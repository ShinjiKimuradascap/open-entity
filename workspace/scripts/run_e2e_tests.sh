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
docker-compose -f docker-compose.test.yml down --remove-orphans 2>/dev/null || true

echo ""
echo "Step 2: Building test images..."
docker-compose -f docker-compose.test.yml build

echo ""
echo "Step 3: Starting test services..."
docker-compose -f docker-compose.test.yml up -d entity-a entity-b

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
    docker-compose -f docker-compose.test.yml logs
    exit 1
fi

echo ""
echo "Step 5: Running E2E tests..."
# ローカルでテスト実行（Docker内でも可）
if command -v pytest &> /dev/null; then
    echo "Running tests locally..."
    PYTHONPATH=./services python -m pytest tests/e2e/ -v --tb=short
else
    echo "Running tests in Docker..."
    docker-compose -f docker-compose.test.yml -f docker-compose.e2e.yml up e2e-test-runner
fi

echo ""
echo "Step 6: Cleaning up..."
docker-compose -f docker-compose.test.yml down

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}E2E Tests Completed!${NC}"
echo -e "${GREEN}==========================================${NC}"
