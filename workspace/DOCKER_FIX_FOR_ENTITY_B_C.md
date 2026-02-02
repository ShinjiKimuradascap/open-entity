# Dockerfile/docker-compose 修正計画

## 問題の根本原因

マーケットプレイスが0件を返す問題の原因：

1. **Dockerfile** で `data/` ディレクトリを `/app/data/` にコピー（ビルド時）
2. **docker-compose.yml** で `registry-data` ボリュームを `/app/data` にマウント（実行時）
3. ボリュームマウントがビルド時のコピーを上書き → 初期データが消える

## 解決策

### 方法1: エントリポイントスクリプトを追加（推奨）

`docker-entrypoint.sh` を作成して、初期データをコピーするロジックを追加。

### 方法2: docker-compose.yml の volumes 修正

`./data:/app/data:ro` でホストのデータを読み取り専用でマウント。

### 方法3: 初期化スクリプトを Python で実装

`api_server.py` の起動時にデータを初期化。

## 推奨アプローチ

**方法1（エントリポイントスクリプト）** を推奨。

## 実装タスク

1. `docker-entrypoint.sh` を作成
2. `Dockerfile` を修正
3. テスト：ボリュームを削除して再作成
4. マーケットプレイスAPIがデータを返すことを確認

## 緊急対応（今すぐ必要な場合）

既存のコンテナで手動コピー：
`docker cp data/marketplace/registry.json CONTAINER:/app/data/marketplace/`
