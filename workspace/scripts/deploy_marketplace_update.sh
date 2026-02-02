#!/bin/bash
#
# Marketplace Registry Update Deployment Script
# Syncs local marketplace registry changes to GCP
#
# Usage: ./scripts/deploy_marketplace_update.sh

set -e

echo "=========================================="
echo "Marketplace Registry Update Deployment"
echo "=========================================="
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI not found"
    echo "   Please install: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Configuration
PROJECT_ID="${GCP_PROJECT:-momentum-ai-446013}"
REGION="asia-northeast1"
SERVICE_NAME="ai-roulette"

echo "Configuration:"
echo "  Project: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Service: $SERVICE_NAME"
echo ""

# Verify marketplace registry
if [ ! -f "data/marketplace/registry.json" ]; then
    echo "❌ Error: marketplace registry not found"
    exit 1
fi

SERVICE_COUNT=$(python3 -c "import json; data=json.load(open('data/marketplace/registry.json')); print(len(data['listings']))")
echo "✓ Marketplace registry: $SERVICE_COUNT services"

# Deploy to Cloud Run
echo ""
echo "[1/3] Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --project $PROJECT_ID \
    --memory "1Gi" \
    --cpu "1" \
    --min-instances 1 \
    --max-instances 10 \
    --concurrency 80 \
    --timeout 300 \
    --allow-unauthenticated

# Get service URL
echo ""
echo "[2/3] Getting service URL..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region $REGION \
    --project $PROJECT_ID \
    --format 'value(status.url)')

echo "✓ Service URL: $SERVICE_URL"

# Verify deployment
echo ""
echo "[3/3] Verifying deployment..."
sleep 5

# Health check
echo "  - Health check..."
HEALTH=$(curl -s "$SERVICE_URL/health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','error'))" 2>/dev/null || echo "error")
if [ "$HEALTH" = "healthy" ]; then
    echo "    ✓ Health check passed"
else
    echo "    ⚠ Health check returned: $HEALTH"
fi

# API check
echo "  - API check..."
API_STATUS=$(curl -s "$SERVICE_URL/api/v1/status" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','error'))" 2>/dev/null || echo "error")
if [ "$API_STATUS" = "operational" ]; then
    echo "    ✓ API operational"
else
    echo "    ⚠ API status: $API_STATUS"
fi

# Marketplace check
echo "  - Marketplace check..."
MKP_COUNT=$(curl -s "$SERVICE_URL/api/v1/marketplace/services" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('services',[])))" 2>/dev/null || echo "0")
echo "    ✓ Marketplace services: $MKP_COUNT"

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Service URL: $SERVICE_URL"
echo "Marketplace: $SERVICE_URL/api/v1/marketplace/services"
echo "Health: $SERVICE_URL/health"
echo ""
echo "Next steps:"
echo "  1. Verify marketplace shows $SERVICE_COUNT services"
echo "  2. Check API documentation: $SERVICE_URL/docs"
echo "  3. Monitor logs: gcloud logging tail --service=$SERVICE_NAME"
