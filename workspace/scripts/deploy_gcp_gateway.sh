#!/bin/bash
# GCP Gateway Agentをcloud Runにデプロイするスクリプト

set -e

# 設定
PROJECT_ID="${GCP_PROJECT:-your-project-id}"
REGION="${GCP_REGION:-asia-northeast1}"
SERVICE_NAME="gcp-gateway-agent"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# 認証トークンを生成（初回のみ）
if [ -z "$GATEWAY_AUTH_TOKEN" ]; then
    GATEWAY_AUTH_TOKEN=$(openssl rand -hex 32)
    echo "Generated GATEWAY_AUTH_TOKEN: $GATEWAY_AUTH_TOKEN"
    echo "Save this token! You'll need it for Entity A/B to communicate with the gateway."
fi

echo "=== GCP Gateway Agent Deployment ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# ディレクトリ移動
cd "$(dirname "$0")/../services/gcp_gateway"

# gcp_gateway_agent.pyをコピー
cp ../gcp_gateway_agent.py .

# Dockerイメージのビルド
echo "Building Docker image..."
docker build -t $IMAGE_NAME .

# GCRにプッシュ
echo "Pushing to GCR..."
docker push $IMAGE_NAME

# Cloud Runにデプロイ
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --project $PROJECT_ID \
    --platform managed \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 3 \
    --set-env-vars "GATEWAY_AUTH_TOKEN=$GATEWAY_AUTH_TOKEN,GCP_PROJECT=$PROJECT_ID"

# デプロイ結果を取得
URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --project $PROJECT_ID --format 'value(status.url)')

echo ""
echo "=== Deployment Complete ==="
echo "Gateway URL: $URL"
echo "Auth Token: $GATEWAY_AUTH_TOKEN"
echo ""
echo "To configure Entity A/B, add to .env:"
echo "  GCP_GATEWAY_URL=$URL"
echo "  GCP_GATEWAY_TOKEN=$GATEWAY_AUTH_TOKEN"
