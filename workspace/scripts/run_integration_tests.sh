#!/bin/bash
#
# Integration Test Runner
# AI Agent Communication Protocol - Integration Test Automation
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICES_DIR="${SERVICES_DIR:-./services}"
TESTS_DIR="${TESTS_DIR:-./tests}"
VENV_DIR="${VENV_DIR:-./.venv}"
REPORT_DIR="${REPORT_DIR:-./test_reports}"

# Test categories
PHASE1_TESTS="test_session_manager.py test_crypto_integration.py test_signature.py test_wallet.py test_crypto.py"
PHASE2_TESTS="test_e2e_crypto.py test_e2e_crypto_integration.py test_security.py test_handshake_protocol.py test_handshake_integration.py"
PHASE3_TESTS="test_peer_service_integration.py test_peer_service_e2e.py test_peer_service_e2e_integration.py"
PHASE4_TESTS="test_integration_scenarios.py test_moltbook_integration.py"

# Test results tracking
TEST_RESULTS_FILE="$REPORT_DIR/test_results_$(date +%Y%m%d_%H%M%S).json"
TESTS_PASSED=0
TESTS_FAILED=0

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

show_help() {
    cat << EOF
Integration Test Runner for AI Agent Communication Protocol

Usage: $0 [OPTIONS] [PHASE]

PHASE:
    phase1    Run Phase 1 - Basic Functionality tests
    phase2    Run Phase 2 - Encryption Integration tests
    phase3    Run Phase 3 - Peer Service Integration tests
    phase4    Run Phase 4 - End-to-End tests
    all       Run all phases (default)
    quick     Run quick sanity tests only

OPTIONS:
    -h, --help       Show this help message
    -v, --verbose    Verbose output
    -c, --coverage   Generate coverage report
    -p, --parallel   Run tests in parallel (requires pytest-xdist)
    -j, --junit      Generate JUnit XML report
    -k, --keep       Keep test environment after tests
    --no-venv        Don't use virtual environment

Examples:
    $0                    # Run all tests
    $0 phase1             # Run only Phase 1 tests
    $0 phase2 -c -j       # Run Phase 2 with coverage and JUnit report
    $0 quick -v           # Run quick tests with verbose output

EOF
}

setup_environment() {
    log_info "Setting up test environment..."
    
    # Create report directory
    mkdir -p "$REPORT_DIR"
    
    # Setup virtual environment if needed
    if [[ "$USE_VENV" == "true" && ! -d "$VENV_DIR" ]]; then
        log_info "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi
    
    # Activate virtual environment
    if [[ "$USE_VENV" == "true" ]]; then
        source "$VENV_DIR/bin/activate"
    fi
    
    # Install dependencies
    log_info "Installing dependencies..."
    pip install -q -r requirements.txt 2>/dev/null || true
    pip install -q pytest pytest-asyncio pytest-cov pytest-xdist 2>/dev/null || true
    
    log_success "Environment setup complete"
}

run_phase1() {
    log_info "Running Phase 1 - Basic Functionality Tests"
    
    cd "$SERVICES_DIR"
    local pytest_args="-v --tb=short"
    
    [[ "$COVERAGE" == "true" ]] && pytest_args="$pytest_args --cov=. --cov-append"
    [[ "$JUNIT" == "true" ]] && pytest_args="$pytest_args --junitxml=../$REPORT_DIR/junit-phase1.xml"
    [[ "$PARALLEL" == "true" ]] && pytest_args="$pytest_args -n auto"
    
    if python -m pytest $PHASE1_TESTS $pytest_args 2>&1 | tee ../$REPORT_DIR/phase1_output.log; then
        log_success "Phase 1 tests passed"
        ((TESTS_PASSED++))
        return 0
    else
        log_error "Phase 1 tests failed"
        ((TESTS_FAILED++))
        return 1
    fi
}

run_phase2() {
    log_info "Running Phase 2 - Encryption Integration Tests"
    
    cd "$SERVICES_DIR"
    local pytest_args="-v --tb=short"
    
    [[ "$COVERAGE" == "true" ]] && pytest_args="$pytest_args --cov=. --cov-append"
    [[ "$JUNIT" == "true" ]] && pytest_args="$pytest_args --junitxml=../$REPORT_DIR/junit-phase2.xml"
    [[ "$PARALLEL" == "true" ]] && pytest_args="$pytest_args -n auto"
    
    if python -m pytest $PHASE2_TESTS $pytest_args 2>&1 | tee ../$REPORT_DIR/phase2_output.log; then
        log_success "Phase 2 tests passed"
        ((TESTS_PASSED++))
        return 0
    else
        log_error "Phase 2 tests failed"
        ((TESTS_FAILED++))
        return 1
    fi
}

run_phase3() {
    log_info "Running Phase 3 - Peer Service Integration Tests"
    
    cd "$SERVICES_DIR"
    
    if python test_peer_service_integration.py 2>&1 | tee ../$REPORT_DIR/phase3_output.log; then
        log_success "Phase 3 tests passed"
        ((TESTS_PASSED++))
        return 0
    else
        log_error "Phase 3 tests failed"
        ((TESTS_FAILED++))
        return 1
    fi
}

run_phase4() {
    log_info "Running Phase 4 - End-to-End Tests"
    
    cd "$SERVICES_DIR"
    local pytest_args="-v --tb=short"
    
    [[ "$COVERAGE" == "true" ]] && pytest_args="$pytest_args --cov=. --cov-append"
    [[ "$JUNIT" == "true" ]] && pytest_args="$pytest_args --junitxml=../$REPORT_DIR/junit-phase4.xml"
    
    if python -m pytest $PHASE4_TESTS $pytest_args 2>&1 | tee ../$REPORT_DIR/phase4_output.log; then
        log_success "Phase 4 tests passed"
        ((TESTS_PASSED++))
        return 0
    else
        log_error "Phase 4 tests failed"
        ((TESTS_FAILED++))
        return 1
    fi
}

run_quick() {
    log_info "Running Quick Sanity Tests"
    
    cd "$SERVICES_DIR"
    
    # Run only the most critical tests
    python -m pytest test_session_manager.py::TestSessionManager::test_create_session \
                     test_crypto_integration.py::TestCryptoIntegration::test_key_generation \
                     test_signature.py -v --tb=short
}

generate_report() {
    if [[ "$COVERAGE" == "true" ]]; then
        log_info "Generating coverage report..."
        cd "$SERVICES_DIR"
        python -m pytest --cov=. --cov-report=html:../$REPORT_DIR/coverage_html \
                        --cov-report=xml:../$REPORT_DIR/coverage.xml \
                        --cov-report=term-missing
        log_success "Coverage report generated in $REPORT_DIR/"
    fi
    
    if [[ "$JUNIT" == "true" ]]; then
        log_info "JUnit reports saved to $REPORT_DIR/"
    fi
    
    # Generate JSON test results summary
    cat > "$TEST_RESULTS_FILE" << EOF
{
    "timestamp": "$(date -Iseconds)",
    "phase": "$PHASE",
    "tests_passed": $TESTS_PASSED,
    "tests_failed": $TESTS_FAILED,
    "overall_result": "$([ $TESTS_FAILED -eq 0 ] && echo "PASSED" || echo "FAILED")"
}
EOF
    log_info "Test results saved to: $TEST_RESULTS_FILE"
}

cleanup() {
    if [[ "$KEEP_ENV" != "true" ]]; then
        log_info "Cleaning up..."
        # Add cleanup tasks here if needed
    fi
}

# Main
main() {
    local PHASE="all"
    local VERBOSE="false"
    local COVERAGE="false"
    local PARALLEL="false"
    local JUNIT="false"
    local USE_VENV="true"
    local KEEP_ENV="false"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--verbose)
                VERBOSE="true"
                shift
                ;;
            -c|--coverage)
                COVERAGE="true"
                shift
                ;;
            -p|--parallel)
                PARALLEL="true"
                shift
                ;;
            -j|--junit)
                JUNIT="true"
                shift
                ;;
            -k|--keep)
                KEEP_ENV="true"
                shift
                ;;
            --no-venv)
                USE_VENV="false"
                shift
                ;;
            phase1|phase2|phase3|phase4|all|quick)
                PHASE="$1"
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # Setup
    setup_environment
    
    # Track results
    local RESULT=0
    
    # Run tests based on phase
    case $PHASE in
        phase1)
            run_phase1 || RESULT=1
            ;;
        phase2)
            run_phase2 || RESULT=1
            ;;
        phase3)
            run_phase3 || RESULT=1
            ;;
        phase4)
            run_phase4 || RESULT=1
            ;;
        quick)
            run_quick || RESULT=1
            ;;
        all)
            run_phase1 || RESULT=1
            run_phase2 || RESULT=1
            run_phase3 || RESULT=1
            run_phase4 || RESULT=1
            ;;
    esac
    
    # Generate reports
    generate_report
    
    # Cleanup
    cleanup
    
    # Summary
    if [[ $RESULT -eq 0 ]]; then
        log_success "All tests passed!"
    else
        log_error "Some tests failed!"
    fi
    
    exit $RESULT
}

# Run main
trap cleanup EXIT
main "$@"
