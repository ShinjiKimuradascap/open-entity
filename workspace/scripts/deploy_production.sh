#!/bin/bash
#
# Production Deployment Script for AI Collaboration Platform
# AIコラボレーションプラットフォーム 本番デプロイスクリプト
#
# Usage: ./scripts/deploy_production.sh [environment]
# Environments: staging, production

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENVIRONMENT="${1:-production}"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check .env file
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        log_warn ".env file not found, copying from .env.example"
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        log_warn "Please configure .env file before running again"
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

# Generate secure keys if not exists
generate_keys() {
    log_info "Checking/generating secure keys..."
    
    # Generate API private key if default
    if grep -q "API_PRIVATE_KEY=0000000000000000000000000000000000000000000000000000000000000000" "$PROJECT_DIR/.env"; then
        log_warn "Generating new API_PRIVATE_KEY..."
        NEW_KEY=$(openssl rand -hex 32)
        sed -i "s/API_PRIVATE_KEY=0000000000000000000000000000000000000000000000000000000000000000/API_PRIVATE_KEY=$NEW_KEY/" "$PROJECT_DIR/.env"
        log_info "New API_PRIVATE_KEY generated"
    fi
    
    # Generate Entity A key if default
    if grep -q "ENTITY_A_PRIVATE_KEY=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" "$PROJECT_DIR/.env"; then
        log_warn "Generating new ENTITY_A_PRIVATE_KEY..."
        NEW_KEY=$(openssl rand -hex 32)
        sed -i "s/ENTITY_A_PRIVATE_KEY=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/ENTITY_A_PRIVATE_KEY=$NEW_KEY/" "$PROJECT_DIR/.env"
        log_info "New ENTITY_A_PRIVATE_KEY generated"
    fi
    
    # Generate Entity B key if default
    if grep -q "ENTITY_B_PRIVATE_KEY=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" "$PROJECT_DIR/.env"; then
        log_warn "Generating new ENTITY_B_PRIVATE_KEY..."
        NEW_KEY=$(openssl rand -hex 32)
        sed -i "s/ENTITY_B_PRIVATE_KEY=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/ENTITY_B_PRIVATE_KEY=$NEW_KEY/" "$PROJECT_DIR/.env"
        log_info "New ENTITY_B_PRIVATE_KEY generated"
    fi
    
    # Generate JWT secret if default
    if grep -q "JWT_SECRET=your-super-secret-jwt-key-change-in-production" "$PROJECT_DIR/.env"; then
        log_warn "Generating new JWT_SECRET..."
        NEW_SECRET=$(openssl rand -base64 32)
        sed -i "s/JWT_SECRET=your-super-secret-jwt-key-change-in-production/JWT_SECRET=$NEW_SECRET/" "$PROJECT_DIR/.env"
        log_info "New JWT_SECRET generated"
    fi
}

# Build and start services
build_and_start() {
    log_info "Building Docker images..."
    cd "$PROJECT_DIR"
    docker-compose build --no-cache
    
    log_info "Starting services..."
    docker-compose up -d
    
    log_info "Waiting for services to be healthy..."
    sleep 10
    
    # Check health
    if docker-compose ps | grep -q "unhealthy"; then
        log_error "Some services are unhealthy"
        docker-compose ps
        exit 1
    fi
    
    log_info "All services are healthy"
}

# Setup monitoring
setup_monitoring() {
    log_info "Setting up monitoring..."
    
    # Create monitoring directories if not exist
    mkdir -p "$PROJECT_DIR/monitoring"
    
    # Create prometheus config if not exists
    if [ ! -f "$PROJECT_DIR/monitoring/prometheus.yml" ]; then
        cat > "$PROJECT_DIR/monitoring/prometheus.yml" << 'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'api-server'
    static_configs:
      - targets: ['api-server:8000']
    metrics_path: /metrics
    
  - job_name: 'entity-a'
    static_configs:
      - targets: ['entity-a:8001']
    metrics_path: /metrics
    
  - job_name: 'entity-b'
    static_configs:
      - targets: ['entity-b:8002']
    metrics_path: /metrics
EOF
        log_info "Created prometheus.yml"
    fi
}

# Display deployment info
deployment_info() {
    echo ""
    echo "=========================================="
    echo "  Deployment Complete!"
    echo "=========================================="
    echo ""
    echo "Services:"
    echo "  API Server:    http://localhost:8000"
    echo "  Entity A:      http://localhost:8001"
    echo "  Entity B:      http://localhost:8002"
    echo "  Redis:         localhost:6379"
    echo "  Prometheus:    http://localhost:9090"
    echo "  Grafana:       http://localhost:3000"
    echo ""
    echo "Health Check:"
    echo "  curl http://localhost:8000/health"
    echo ""
    echo "Logs:"
    echo "  docker-compose logs -f"
    echo ""
    echo "Stop:"
    echo "  docker-compose down"
    echo ""
    echo "=========================================="
}

# Main deployment flow
main() {
    log_info "Starting deployment for environment: $ENVIRONMENT"
    
    check_prerequisites
    generate_keys
    setup_monitoring
    build_and_start
    deployment_info
    
    log_info "Deployment completed successfully!"
}

# Run main function
main "$@"
