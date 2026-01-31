#!/bin/bash
# Moltbook Integration Setup Checker
# Moltbook連携設定の検証スクリプト

echo "=========================================="
echo "Moltbook Integration Setup Checker"
echo "=========================================="
echo ""

# カラー設定
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# チェックカウンター
CHECKS_PASSED=0
CHECKS_FAILED=0

# 関数: チェック結果表示
check_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((CHECKS_PASSED++))
}

check_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((CHECKS_FAILED++))
}

check_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# 1. 環境変数チェック
echo "[1/5] Checking environment variables..."
if [ -n "$MOLTBOOK_API_KEY" ]; then
    check_pass "MOLTBOOK_API_KEY is set"
else
    check_fail "MOLTBOOK_API_KEY is not set"
    echo "        Set it with: export MOLTBOOK_API_KEY='your_key'"
fi

if [ -n "$MOLTBOOK_AGENT_ID" ]; then
    check_pass "MOLTBOOK_AGENT_ID is set"
else
    check_warn "MOLTBOOK_AGENT_ID is not set (optional)"
fi

echo ""

# 2. Pythonモジュールチェック
echo "[2/5] Checking Python modules..."
if python -c "import aiohttp" 2>/dev/null; then
    check_pass "aiohttp is installed"
else
    check_fail "aiohttp is not installed"
    echo "        Install with: pip install aiohttp"
fi

if python -c "import yaml" 2>/dev/null; then
    check_pass "PyYAML is installed"
else
    check_fail "PyYAML is not installed"
    echo "        Install with: pip install pyyaml"
fi

echo ""

# 3. 設定ファイルチェック
echo "[3/5] Checking configuration files..."
if [ -f "config/orchestrator_moltbook.yaml" ]; then
    check_pass "orchestrator_moltbook.yaml exists"
else
    check_fail "orchestrator_moltbook.yaml not found"
fi

if [ -f "services/moltbook_integration.py" ]; then
    check_pass "moltbook_integration.py exists"
else
    check_fail "moltbook_integration.py not found"
fi

if [ -f "services/test_moltbook_integration.py" ]; then
    check_pass "test_moltbook_integration.py exists"
else
    check_fail "test_moltbook_integration.py not found"
fi

echo ""

# 4. テスト実行可能性チェック
echo "[4/5] Checking test executability..."
if [ -f "services/test_moltbook_integration.py" ]; then
    if python -c "import sys; sys.path.insert(0, 'services'); import test_moltbook_integration" 2>/dev/null; then
        check_pass "Test module can be imported"
    else
        check_warn "Test module has import issues (may need dependencies)"
    fi
else
    check_fail "Cannot check test module (file not found)"
fi

echo ""

# 5. .envファイルチェック
echo "[5/5] Checking .env file..."
if [ -f ".env" ]; then
    if grep -q "MOLTBOOK_API_KEY" .env; then
        check_pass ".env contains MOLTBOOK_API_KEY entry"
    else
        check_warn ".env does not contain MOLTBOOK_API_KEY"
    fi
else
    check_warn ".env file not found (copy from .env.example)"
fi

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
echo -e "Passed: ${GREEN}$CHECKS_PASSED${NC}"
echo -e "Failed: ${RED}$CHECKS_FAILED${NC}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All critical checks passed!${NC}"
    echo "You can run integration tests with:"
    echo "  cd services && python -m pytest test_moltbook_integration.py -v"
    exit 0
else
    echo -e "${YELLOW}Some checks failed.${NC}"
    echo "Please fix the issues above before running integration tests."
    echo ""
    echo "To get Moltbook API key:"
    echo "  1. Visit https://moltbook.com"
    echo "  2. Complete AI verification process"
    echo "  3. Request API access"
    exit 1
fi
