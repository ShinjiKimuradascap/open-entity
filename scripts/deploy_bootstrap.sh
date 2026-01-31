#!/bin/bash
#
# Deploy A2A Bootstrap Node to Fly.io
# Usage: ./scripts/deploy_bootstrap.sh [environment]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="${FLY_APP_NAME:-open-entity-bootstrap}"
REGION="${FLY_REGION:-nrt}"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check dependencies
check_deps() {
    log_info "Checking dependencies..."
    
    if ! command -v flyctl &> /dev/null; then
        log_error "flyctl is not installed"
        echo "Install from: https://fly.io/docs/hands-on/install-flyctl/"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        log_warning "Docker not found. Local builds will not work."
    fi
    
    log_success "Dependencies OK"
}

# Check authentication
check_auth() {
    log_info "Checking Fly.io authentication..."
    
    if ! flyctl auth whoami &> /dev/null; then
        log_error "Not authenticated with Fly.io"
        echo "Run: flyctl auth login"
        exit 1
    fi
    
    log_success "Authenticated with Fly.io"
}

# Create app if it doesn't exist
create_app() {
    log_info "Checking if app '$APP_NAME' exists..."
    
    if ! flyctl apps list | grep -q "$APP_NAME"; then
        log_info "Creating new app: $APP_NAME"
        flyctl apps create "$APP_NAME" --machines
    else
        log_info "App '$APP_NAME' already exists"
    fi
}

# Set secrets
set_secrets() {
    log_info "Setting secrets..."
    
    # Generate random secret if not set
    if [ -z "$NODE_SECRET" ]; then
        NODE_SECRET=$(openssl rand -hex 32)
        log_info "Generated new NODE_SECRET"
    fi
    
    flyctl secrets set \
        NODE_SECRET="$NODE_SECRET" \
        --app "$APP_NAME"
    
    log_success "Secrets set"
}

# Deploy
deploy() {
    log_info "Deploying to Fly.io..."
    log_info "App: $APP_NAME"
    log_info "Region: $REGION"
    
    # Deploy with remote builder (recommended for CI/CD)
    flyctl deploy \
        --app "$APP_NAME" \
        --region "$REGION" \
        --dockerfile Dockerfile.fly \
        --wait-timeout 300
    
    log_success "Deployment complete!"
}

# Verify deployment
verify() {
    log_info "Verifying deployment..."
    
    # Wait a moment for the app to start
    sleep 5
    
    # Get app URL
    APP_URL=$(flyctl apps info "$APP_NAME" --json 2>/dev/null | grep -o '"Hostname": "[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
    
    if [ -z "$APP_URL" ]; then
        APP_URL="${APP_NAME}.fly.dev"
    fi
    
    log_info "Checking health endpoint..."
    
    MAX_RETRIES=10
    RETRY_COUNT=0
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -sf "https://${APP_URL}/health" > /dev/null 2>&1; then
            log_success "Health check passed!"
            echo ""
            echo "========================================="
            echo "Bootstrap Node is live!"
            echo "URL: https://${APP_URL}"
            echo "Health: https://${APP_URL}/health"
            echo "Stats: https://${APP_URL}/stats"
            echo "========================================="
            return 0
        fi
        
        RETRY_COUNT=$((RETRY_COUNT + 1))
        log_warning "Health check failed, retrying... ($RETRY_COUNT/$MAX_RETRIES)"
        sleep 3
    done
    
    log_error "Health check failed after $MAX_RETRIES attempts"
    echo "Check logs: flyctl logs --app $APP_NAME"
    return 1
}

# Show status
show_status() {
    log_info "App Status:"
    flyctl status --app "$APP_NAME"
    echo ""
    log_info "Recent Logs:"
    flyctl logs --app "$APP_NAME" --limit 20
}

# Show usage
show_usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  deploy    - Deploy or update the bootstrap node (default)"
    echo "  status    - Show app status and logs"
    echo "  logs      - Show recent logs"
    echo "  destroy   - Destroy the app (DANGER!)"
    echo "  help      - Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  FLY_APP_NAME   - App name (default: open-entity-bootstrap)"
    echo "  FLY_REGION     - Deployment region (default: nrt)"
    echo "  NODE_SECRET    - Node secret key (auto-generated if not set)"
}

# Main
main() {
    COMMAND="${1:-deploy}"
    
    case "$COMMAND" in
        deploy)
            check_deps
            check_auth
            create_app
            set_secrets
            deploy
            verify
            ;;
        status)
            check_deps
            check_auth
            show_status
            ;;
        logs)
            check_deps
            check_auth
            flyctl logs --app "$APP_NAME"
            ;;
        destroy)
            check_deps
            check_auth
            log_warning "This will destroy app '$APP_NAME' and all its data!"
            read -p "Are you sure? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                flyctl apps destroy "$APP_NAME"
                log_success "App destroyed"
            else
                log_info "Cancelled"
            fi
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            show_usage
            exit 1
            ;;
    esac
}

# Run main
main "$@"
