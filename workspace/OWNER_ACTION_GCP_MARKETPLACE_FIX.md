# GCP Marketplace 0件問題 - 緊急修正ガイド

## 問題
GCP APIがマーケットプレイスサービスを空で返す

## 原因
Cloud Runはステートレスでレジストリファイルにアクセスできない

## 解決策

### Step 1: Dockerfileに以下を追加
COPY deploy_data/marketplace_registry.json /app/data/marketplace/registry.json
COPY deploy_data/services_registry.json /app/data/services/registry.json

### Step 2: デプロイ
gcloud builds submit --tag gcr.io/momentum-ai-446013/api-server:latest
gcloud run deploy api-server --source=. --region=asia-northeast1

### Step 3: 検証
./deploy_data/verify.sh

## 緊急度
T-6hローンチ前

Generated: 2026-02-02 08:15 JST
