#!/bin/bash
#
# Simple Messaging API を GCP Cloud Run にデプロイ
# 
# 使用方法:
#   chmod +x scripts/deploy_messaging_gcp.sh
#   ./scripts/deploy_messaging_gcp.sh
#

set -e

# 設定
SERVICE_NAME="messaging-api"
REGION="asia-northeast1"
PROJECT_ID=${GCP_PROJECT:-"momentum-ai-446013"}
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

echo "=========================================="
echo "Deploying Simple Messaging API to GCP"
echo "=========================================="
echo "Service: ${SERVICE_NAME}"
echo "Region: ${REGION}"
echo "Project: ${PROJECT_ID}"
echo ""

# 1. Dockerイメージをビルド
echo "[1/5] Building Docker image..."
docker build -f Dockerfile.simple -t ${SERVICE_NAME}:latest .

# 2. GCRタグを付与
echo "[2/5] Tagging image for GCR..."
docker tag ${SERVICE_NAME}:latest ${IMAGE_NAME}

# 3. GCRにプッシュ
echo "[3/5] Pushing to Google Container Registry..."
docker push ${IMAGE_NAME}

# 4. Cloud Run にデプロイ
echo "[4/5] Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --region ${REGION} \
    --memory "512Mi" \
    --cpu "1" \
    --min-instances 0 \
    --max-instances 10 \
    --allow-unauthenticated \
    --platform managed

# 5. デプロイ確認
echo "[5/5] Verifying deployment..."
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')
echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "Health Check:"
curl -s "${SERVICE_URL}/health" | jq . || curl -s "${SERVICE_URL}/health"
echo ""
echo "To test messaging:"
echo "  curl -X POST '${SERVICE_URL}/message/send' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"sender_id\":\"agent1\",\"recipient_id\":\"agent2\",\"content\":\"Hello!\"}'"
