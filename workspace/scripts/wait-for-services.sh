#!/bin/bash
# テストサービスの起動待機スクリプト

set -e

ENTITY_A_URL="http://localhost:8001"
ENTITY_B_URL="http://localhost:8002"
MAX_RETRIES=30
RETRY_DELAY=2

echo "Waiting for test services to start..."

for i in $(seq 1 $MAX_RETRIES); do
    A_READY=false
    B_READY=false
    
    if curl -s "$ENTITY_A_URL/health" > /dev/null 2>&1; then
        A_READY=true
    fi
    
    if curl -s "$ENTITY_B_URL/health" > /dev/null 2>&1; then
        B_READY=true
    fi
    
    if [ "$A_READY" = true ] && [ "$B_READY" = true ]; then
        echo "✓ Both services are ready!"
        exit 0
    fi
    
    echo "Attempt $i/$MAX_RETRIES: A=$A_READY, B=$B_READY"
    sleep $RETRY_DELAY
done

echo "✗ Services failed to start within timeout"
exit 1
