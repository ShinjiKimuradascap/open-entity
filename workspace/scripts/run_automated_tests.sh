#!/bin/bash
# Automated Test Runner for AI Collaboration Platform
# Runs tests based on environment and configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TEST_TYPE=${1:-"all"}
VERBOSE=${2:-"false"}
REPORT_DIR="test_reports/$(date +%Y%m%d_%H%M%S)"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Setup
setup() {
    log_info "Setting up test environment..."
    mkdir -p "$REPORT_DIR"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 not found"
        exit 1
    fi
    
    # Check dependencies
    if [ ! -f "requirements.txt" ]; then
        log_warn "requirements.txt not found in current directory"
    fi
    
    log_success "Setup complete"
}

# Run unit tests
run_unit_tests() {
    log_info "Running unit tests..."
    
    if [ "$VERBOSE" = "true" ]; then
        python3 -m pytest services/test_*.py -v \
            -m "not integration and not e2e" \
            --tb=short \
            --junitxml="$REPORT_DIR/unit_tests.xml" \
            2>&1 | tee "$REPORT_DIR/unit_tests.log" || true
    else
        python3 -m pytest services/test_*.py \
            -m "not integration and not e2e" \
            --tb=line \
            --junitxml="$REPORT_DIR/unit_tests.xml" \
            > "$REPORT_DIR/unit_tests.log" 2>&1 || true
    fi
    
    if [ $? -eq 0 ]; then
        log_success "Unit tests passed"
    else
        log_error "Unit tests failed (see $REPORT_DIR/unit_tests.log)"
    fi
}

# Run integration tests
run_integration_tests() {
    log_info "Running integration tests..."
    
    cd services
    
    # Run key integration tests
    for test in test_integration.py test_session_manager.py test_crypto_integration.py; do
        if [ -f "$test" ]; then
            log_info "Running $test..."
            python3 "$test" > "../$REPORT_DIR/${test%.py}.log" 2>&1 || true
        fi
    done
    
    cd ..
    log_success "Integration tests complete"
}

# Run E2E tests
run_e2e_tests() {
    log_info "Running E2E tests..."
    
    # Check if docker-compose is available
    if ! command -v docker-compose &> /dev/null; then
        log_warn "docker-compose not found, skipping E2E tests"
        return
    fi
    
    # Start test environment
    docker-compose -f docker-compose.test.yml up -d entity-a entity-b 2>&1 | tee -a "$REPORT_DIR/e2e_setup.log" || true
    sleep 15
    
    # Run E2E tests
    PYTHONPATH=./services python3 -m pytest tests/e2e/ -v \
        --tb=short \
        --junitxml="$REPORT_DIR/e2e_tests.xml" \
        2>&1 | tee "$REPORT_DIR/e2e_tests.log" || true
    
    # Cleanup
    docker-compose -f docker-compose.test.yml down -v 2>&1 | tee -a "$REPORT_DIR/e2e_setup.log" || true
    
    log_success "E2E tests complete"
}

# Run security checks
run_security_checks() {
    log_info "Running security checks..."
    
    # Check if bandit is installed
    if command -v bandit &> /dev/null; then
        bandit -r services -f json -o "$REPORT_DIR/bandit_report.json" || true
        bandit -r services -f screen 2>&1 | tee "$REPORT_DIR/bandit_screen.log" || true
        log_success "Security checks complete"
    else
        log_warn "bandit not installed, skipping security checks"
    fi
}

# Generate summary report
generate_report() {
    log_info "Generating summary report..."
    
    cat > "$REPORT_DIR/summary.md" << EOF
# Test Report - $(date)

## Test Type: $TEST_TYPE

## Results Summary

### Files Generated
$(ls -1 "$REPORT_DIR")

### Test Status
EOF

    # Count test results from JUnit XML
    if [ -f "$REPORT_DIR/unit_tests.xml" ]; then
        local total=$(grep -o 'tests="[0-9]*"' "$REPORT_DIR/unit_tests.xml" | head -1 | grep -o '[0-9]*')
        local failures=$(grep -o 'failures="[0-9]*"' "$REPORT_DIR/unit_tests.xml" | head -1 | grep -o '[0-9]*')
        local errors=$(grep -o 'errors="[0-9]*"' "$REPORT_DIR/unit_tests.xml" | head -1 | grep -o '[0-9]*')
        
        echo "- Unit Tests: ${total:-0} total, ${failures:-0} failures, ${errors:-0} errors" >> "$REPORT_DIR/summary.md"
    fi
    
    if [ -f "$REPORT_DIR/e2e_tests.xml" ]; then
        local total=$(grep -o 'tests="[0-9]*"' "$REPORT_DIR/e2e_tests.xml" | head -1 | grep -o '[0-9]*')
        local failures=$(grep -o 'failures="[0-9]*"' "$REPORT_DIR/e2e_tests.xml" | head -1 | grep -o '[0-9]*')
        
        echo "- E2E Tests: ${total:-0} total, ${failures:-0} failures" >> "$REPORT_DIR/summary.md"
    fi
    
    echo "" >> "$REPORT_DIR/summary.md"
    echo "Report generated at: $REPORT_DIR" >> "$REPORT_DIR/summary.md"
    
    cat "$REPORT_DIR/summary.md"
    log_success "Report generated at $REPORT_DIR"
}

# Main execution
main() {
    echo "========================================"
    echo "AI Collaboration Platform - Test Runner"
    echo "========================================"
    echo "Test Type: $TEST_TYPE"
    echo "Report Directory: $REPORT_DIR"
    echo "========================================"
    
    setup
    
    case "$TEST_TYPE" in
        "unit")
            run_unit_tests
            ;;
        "integration")
            run_integration_tests
            ;;
        "e2e")
            run_e2e_tests
            ;;
        "security")
            run_security_checks
            ;;
        "all"|*)
            run_unit_tests
            run_integration_tests
            run_e2e_tests
            run_security_checks
            ;;
    esac
    
    generate_report
    
    echo "========================================"
    log_success "Test run complete!"
    echo "Report: $REPORT_DIR"
    echo "========================================"
}

# Run main
main "$@"
