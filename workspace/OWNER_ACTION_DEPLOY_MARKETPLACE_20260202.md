# GCPマーケットプレイスデプロイ依頼

**発行時刻:** 2026-02-02 08:20 JST
**優先度:** CRITICAL (T-24h PHローンチ前)

## 現在の問題

API: http://34.134.116.148:8080/health → healthy
API: http://34.134.116.148:8080/marketplace/services → 空 (total: 0)

## 準備済みファイル

- deploy_data/services_registry.json (11サービス)
- deploy_data/deploy.sh (デプロイスクリプト)

## 実行手順

cd /home/moco/workspace && bash deploy_data/deploy.sh

## 検証

curl http://34.134.116.148:8080/marketplace/services
total: 11 が表示されれば成功

Entity A (Orchestrator)