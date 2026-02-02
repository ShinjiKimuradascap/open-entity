#!/bin/bash
# Check Three Entities Health
# 3エンティティ死活確認スクリプト

echo "=========================================="
echo "Three Entities Health Check"
echo "=========================================="
echo ""

ENTITIES=(
    "Entity A:http://localhost:8001"
    "Entity B:http://localhost:8002"
    "Entity C:http://localhost:8003"
)

healthy_count=0
unhealthy_count=0

for entity in "${ENTITIES[@]}"; do
    name="${entity%%:*}"
    url="${entity##*:}"
    
    echo -n "Checking $name... "
    
    if response=$(curl -s "${url}/health" 2>/dev/null); then
        echo "✅ Healthy"
        echo "  Response: $response"
        ((healthy_count++))
    else
        echo "❌ Unreachable"
        ((unhealthy_count++))
    fi
    echo ""
done

echo "=========================================="
echo "Summary: $healthy_count healthy, $unhealthy_count unhealthy"
echo "=========================================="

if [ $unhealthy_count -eq 0 ]; then
    echo "✅ All entities are healthy!"
    exit 0
else
    echo "❌ Some entities are not responding"
    exit 1
fi
