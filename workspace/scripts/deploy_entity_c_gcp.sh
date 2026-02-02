#!/bin/bash
# Deploy Entity C and Watchdog to GCP
# This script adds the 3rd entity to the existing GCP deployment

set -e

echo "========================================"
echo "Entity C GCP Deployment"
echo "========================================"

# Configuration
GCP_HOST="34.134.116.148"
GCP_USER="openentity"
ENTITY_C_PORT="8003"

# Generate Entity C keys
echo "[1/5] Generating Entity C credentials..."
ENTITY_C_ID="entity-c-$(date +%s)"
ENTITY_C_PRIVATE_KEY=$(openssl rand -hex 32)

echo "  Entity C ID: $ENTITY_C_ID"
echo "  Entity C Key: ${ENTITY_C_PRIVATE_KEY:0:16}..."

# Create remote deployment script
echo "[2/5] Preparing remote deployment..."

ssh $GCP_USER@$GCP_HOST << 'REMOTESCRIPT'
# Create Entity C directory
mkdir -p ~/entities/entity-c
mkdir -p ~/entities/watchdog

cat > ~/entities/entity-c/docker-compose.yml << 'EOF'
version: '3.8'
services:
  entity-c:
    image: ai-collab-platform:latest
    container_name: entity-c
    ports:
      - "8003:8003"
    environment:
      - ENTITY_ID=entity-c
      - ENTITY_PRIVATE_KEY=${ENTITY_C_PRIVATE_KEY}
      - API_SERVER_URL=http://localhost:8080
      - PORT=8003
      - PEER_URLS=http://localhost:8001,http://localhost:8002
    volumes:
      - ./data:/app/data
    command: python services/peer_service_runner.py --id entity-c --port 8003
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
EOF

cat > ~/entities/watchdog/docker-compose.yml << 'EOF'
version: '3.8'
services:
  watchdog:
    image: ai-collab-platform:latest
    container_name: ai-watchdog
    environment:
      - WATCHDOG_MODE=true
      - API_SERVER_URL=http://localhost:8080
      - PEER_URLS=http://localhost:8001,http://localhost:8002,http://localhost:8003
      - CHECK_INTERVAL=30
    volumes:
      - ./data:/app/data
      - /var/run/docker.sock:/var/run/docker.sock:ro
    command: python tools/entity_monitor.py --mode watchdog
    restart: unless-stopped
EOF

echo "Remote configuration created"
REMOTESCRIPT

# Deploy to GCP
echo "[3/5] Deploying Entity C..."
scp -r services tools sdk $GCP_USER@$GCP_HOST:~/entities/entity-c/
scp -r services tools sdk $GCP_USER@$GCP_HOST:~/entities/watchdog/

# Start services
echo "[4/5] Starting services..."
ssh $GCP_USER@$GCP_HOST << 'REMOTESCRIPT'
cd ~/entities/entity-c
export ENTITY_C_PRIVATE_KEY="$ENTITY_C_PRIVATE_KEY"
docker-compose up -d

cd ~/entities/watchdog
docker-compose up -d

echo "Services started"
REMOTESCRIPT

# Verify deployment
echo "[5/5] Verifying deployment..."
sleep 5

HEALTH_C=$(curl -s http://$GCP_HOST:8003/health | grep -c "healthy" || echo "0")
if [ "$HEALTH_C" -eq 1 ]; then
    echo "✓ Entity C is healthy"
else
    echo "✗ Entity C health check failed"
fi

echo ""
echo "========================================"
echo "Deployment Complete!"
echo "========================================"
echo "Entity C: http://$GCP_HOST:$ENTITY_C_PORT"
echo "Health:   http://$GCP_HOST:$ENTITY_C_PORT/health"
echo "========================================"
