#!/bin/bash
# Start Three Entities - Entity A, B, C
# 3エンティティ自動起動スクリプト

set -e

echo "=========================================="
echo "Starting Three Entities (A, B, C)"
echo "=========================================="

# Create shared network if not exists
docker network create ai-collab-network 2>/dev/null || true
docker network create peer-network 2>/dev/null || true

echo ""
echo "[1/3] Starting Entity A..."
docker-compose up -d entity-a
sleep 5

# Wait for Entity A
for i in {1..30}; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo "✅ Entity A is ready"
        break
    fi
    echo "  Waiting for Entity A... ($i/30)"
    sleep 2
done

echo ""
echo "[2/3] Starting Entity B..."
docker-compose up -d entity-b
sleep 5

# Wait for Entity B
for i in {1..30}; do
    if curl -s http://localhost:8002/health > /dev/null 2>&1; then
        echo "✅ Entity B is ready"
        break
    fi
    echo "  Waiting for Entity B... ($i/30)"
    sleep 2
done

echo ""
echo "[3/3] Starting Entity C..."
docker-compose -f docker-compose.entity-c.yml up -d entity-c
sleep 5

# Wait for Entity C
for i in {1..30}; do
    if curl -s http://localhost:8003/health > /dev/null 2>&1; then
        echo "✅ Entity C is ready"
        break
    fi
    echo "  Waiting for Entity C... ($i/30)"
    sleep 2
done

echo ""
echo "=========================================="
echo "All Entities Started!"
echo "=========================================="
echo ""
echo "Entity A: http://localhost:8001"
echo "Entity B: http://localhost:8002"
echo "Entity C: http://localhost:8003"
echo ""
echo "Run health check:"
echo "  ./scripts/check_three_entities.sh"
echo ""
