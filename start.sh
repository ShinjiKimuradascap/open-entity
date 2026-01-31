#!/bin/bash
# Open Entity 起動スクリプト
# サンドボックス化されたコンテナで自律AIを起動

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Open Entity を起動します..."

# 1. workspace フォルダを作成
mkdir -p workspace

# 2. .env ファイルの存在確認
if [ ! -f .env ]; then
    if [ -f ../.env ]; then
        echo "📋 .env をコピーしています..."
        cp ../.env .env
    else
        echo "⚠️  .env ファイルが見つかりません"
        echo "   .env.example をコピーして設定してください"
        exit 1
    fi
fi

# 3. Docker の起動確認
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker が起動していません"
    echo "   Docker Desktop を起動してから再実行してください"
    exit 1
fi

# 4. ビルド＆起動
echo "🔨 コンテナをビルドしています..."
docker compose build

echo "🐳 コンテナを起動しています..."
docker compose up -d

# 5. 状態確認
echo ""
echo "✅ Open Entity が起動しました！"
echo ""
echo "📊 状態:"
docker compose ps

echo ""
echo "🌐 Web UI: http://localhost:8001"
echo "📝 ログ確認: docker compose logs -f moco"
echo "🛑 停止: docker compose down"
