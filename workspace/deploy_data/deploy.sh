#!/bin/bash
# GCP Deployment Commands for Marketplace Fix
# Generated: 2026-02-01T23:15:22.060109

# 1. Ensure registry data is copied to deploy_data/
# 2. Build and deploy with updated Dockerfile

echo "🚀 Deploying API Server with Marketplace Data..."

# Build with Cloud Build
gcloud builds submit --tag gcr.io/momentum-ai-446013/api-server:latest

# Deploy to Cloud Run with updated image
gcloud run deploy api-server \
  --image gcr.io/momentum-ai-446013/api-server:latest \
  --region=asia-northeast1 \
  --project=momentum-ai-446013 \
  --platform=managed \
  --allow-unauthenticated \
  --memory=1Gi \
  --cpu=1 \
  --concurrency=80 \
  --max-instances=10 \
  --min-instances=1 \
  --timeout=300s \
  --set-env-vars="ENVIRONMENT=production,LOG_LEVEL=info"

echo "✅ Deployment complete!"
echo ""
echo "Verify with:"
echo "curl http://34.134.116.148:8080/marketplace/services"
