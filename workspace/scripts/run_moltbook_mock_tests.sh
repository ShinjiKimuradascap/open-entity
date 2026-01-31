#!/bin/bash
#
# Moltbook Integration Mock Tests Runner
# APIキー不要のモックテスト実行スクリプト
#

set -e

echo "==================================="
echo "Moltbook Integration Mock Tests"
echo "==================================="
echo ""

# カラー設定
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 作業ディレクトリに移動
cd "$(dirname "$0")/.."

# Pythonパス設定
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/services"

echo "[1/4] Checking environment..."

# Pythonチェック
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: python3 not found${NC}"
    exit 1
fi

echo "  Python: $(python3 --version)"

# 必要モジュールチェック
echo ""
echo "[2/4] Checking dependencies..."

python3 -c "import pytest" 2>/dev/null || {
    echo -e "${YELLOW}Installing pytest...${NC}"
    pip install pytest pytest-asyncio aiohttp
}

python3 -c "import aiohttp" 2>/dev/null || {
    echo -e "${YELLOW}Installing aiohttp...${NC}"
    pip install aiohttp
}

echo -e "${GREEN}  Dependencies OK${NC}"

# テストファイル存在確認
echo ""
echo "[3/4] Checking test files..."

if [ ! -f "services/test_moltbook_integration.py" ]; then
    echo -e "${RED}ERROR: test_moltbook_integration.py not found${NC}"
    exit 1
fi

if [ ! -f "services/moltbook_integration.py" ]; then
    echo -e "${RED}ERROR: moltbook_integration.py not found${NC}"
    exit 1
fi

echo -e "${GREEN}  Test files found${NC}"

# モックテスト実行
echo ""
echo "[4/4] Running mock tests..."
echo ""

cd services

# モックテスト実行（実APIには接続しない）
python3 -m pytest test_moltbook_integration.py -v \
    --ignore-glob="*integration*" \
    -k "not Integration" \
    --tb=short 2>&1 | tee ../test_results_moltbook_mock.log

TEST_EXIT_CODE=${PIPESTATUS[0]}

cd ..

echo ""
echo "==================================="

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}All mock tests passed!${NC}"
    echo ""
    echo "Test Results: test_results_moltbook_mock.log"
    echo ""
    echo "Next steps:"
    echo "  1. Set MOLTBOOK_API_KEY in .env"
    echo "  2. Run: ./scripts/run_moltbook_integration_tests.sh"
else
    echo -e "${RED}Some tests failed!${NC}"
    echo ""
    echo "Check: test_results_moltbook_mock.log"
fi

echo "==================================="

exit $TEST_EXIT_CODE
