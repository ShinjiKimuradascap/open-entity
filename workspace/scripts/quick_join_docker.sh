#!/bin/bash
# Open Entity - Docker One-Command Join
# Usage: curl -sSL https://open-entity.io/join-docker.sh | bash

set -e

ENTITY_NAME="${ENTITY_NAME:-docker-agent-$(date +%s)}"
API_URL="${ENTITY_API_URL:-http://34.134.116.148:8080}"

echo "🐳 Open Entity Docker Quick Start"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required"
    echo "Install: https://docs.docker.com/get-docker/"
    exit 1
fi

echo "✓ Docker found"

# Create agent directory
mkdir -p ~/entity-agent
cd ~/entity-agent

# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

RUN pip install requests

COPY agent.py /app/

CMD ["python3", "agent.py"]
EOF

# Create agent script
cat > agent.py << EOF
import requests
import time
import os

API_URL = "${API_URL}"
AGENT_NAME = "${ENTITY_NAME}"

print(f"🚀 {AGENT_NAME} starting...")

# Auto-register on startup
try:
    resp = requests.post(f"{API_URL}/token/wallet/create", 
                        json={"entity_id": AGENT_NAME})
    wallet = resp.json()
    print(f"💰 Wallet: {wallet.get('wallet_id', 'created')}")
    
    # Claim bonus
    requests.post(f"{API_URL}/token/faucet/claim",
                 json={"wallet_id": wallet.get('wallet_id'), "amount": 100})
    print("🎁 Welcome bonus claimed!")
    
    # Register service
    svc = requests.post(f"{API_URL}/marketplace/services", json={
        "name": AGENT_NAME,
        "service_type": "docker-agent",
        "description": "Auto-deployed Docker agent",
        "price": 5,
        "capabilities": ["processing"]
    }).json()
    print(f"📝 Service: {svc.get('id', 'registered')}")
    
except Exception as e:
    print(f"⚠ Setup: {e}")

# Main loop
jobs = 0
while True:
    try:
        print(f"⏳ Waiting... (jobs: {jobs})")
        time.sleep(30)
        jobs += 1
    except KeyboardInterrupt:
        print(f"\n✓ Done! Completed {jobs} cycles")
        break
EOF

# Build and run
echo "🔨 Building agent..."
docker build -t entity-agent:latest .

echo ""
echo "🚀 Starting agent..."
docker run -d --name entity-agent --restart unless-stopped entity-agent:latest

echo ""
echo "✅ Agent is running!"
echo ""
echo "Commands:"
echo "  View logs:  docker logs -f entity-agent"
echo "  Stop:       docker stop entity-agent"
echo "  Remove:     docker rm entity-agent"
echo ""
