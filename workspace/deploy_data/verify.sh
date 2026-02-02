#!/bin/bash
# Verify marketplace services are available

echo "🔍 Verifying marketplace services..."

RESPONSE=$(curl -s http://34.134.116.148:8080/marketplace/services)
COUNT=$(echo $RESPONSE | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('services', [])))")

echo "Services found: $COUNT"

if [ "$COUNT" -gt 0 ]; then
    echo "✅ SUCCESS: Marketplace has $COUNT services"
    echo ""
    echo "First 3 services:"
    echo $RESPONSE | python3 -c "import sys, json; [print(f"  - {s['service_id']}: {s['description'][:50]}...") for s in json.load(sys.stdin).get('services', [])[:3]]"
else
    echo "❌ FAILED: No services found"
    echo "Response: $RESPONSE"
fi
