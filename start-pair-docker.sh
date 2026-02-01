#!/bin/bash
# Docker ペア起動 + 初期プロンプト送信
# 使用方法: ./start-pair-docker.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 最初のプロンプト（ビジョンと目標）
INITIAL_PROMPT='あなたはもう一人の仲間（Entity B）と一緒に働く。

🌍 **ビジョン**: 世界を素晴らしくすること

🎯 **大目標（長期）**:
- 人間の世界を探索し、理解を深める
- AIの成果の基礎となるシステムを構築する
- 人間とAIが共存できるインフラを作る
- **AI同士がコミュニケーションできるシステムを作り、公開する**
- **世界中のAIが情報交換できるプラットフォームを構築する**

📅 **中期目標**:
- AI間通信プロトコルの確立と公開
- 価値創造・交換メカニズムの設計
- 自律的な学習・改善システム
- オープンなAI通信APIの設計・実装

🔥 **短期目標**:
- このシステム（Open Entity）の基盤整備
- ピア通信の動作確認
- 最初のタスク実行と報告

まず todowrite() で短期・中期・長期タスクを作成し、実行を開始しろ。
完了したら report_to_peer() で Entity B に報告して、協力して進めろ。

二人で世界を素晴らしくしよう。
世界中のAIが繋がれる未来を作ろう。'

echo "🚀 Open Entity ペア (Docker) を起動します..."
echo ""
echo "🌍 ビジョン: 世界を素晴らしくすること"
echo ""

# .envファイルを読み込んで環境変数をエクスポート
if [ -f ../.env ]; then
  export $(grep -v '^#' ../.env | xargs)
fi

# Docker Compose で起動
echo "📦 Docker コンテナを起動中..."
docker compose -f docker-compose.pair.yml up -d

# 起動完了まで待機
echo "⏳ 起動を待機中..."
sleep 10

# 起動確認
echo "🔍 起動確認..."
if curl -s "http://localhost:8001/api/profiles" > /dev/null; then
    echo "   ✅ Entity A: OK (http://localhost:8001)"
else
    echo "   ❌ Entity A: FAILED"
    exit 1
fi

if curl -s "http://localhost:8002/api/profiles" > /dev/null; then
    echo "   ✅ Entity B: OK (http://localhost:8002)"
else
    echo "   ❌ Entity B: FAILED"
    exit 1
fi

echo ""
echo "🎬 最初のメッセージを Entity A に送信..."

# 最初のメッセージを送信（バックグラウンドで）
curl -s -X POST "http://localhost:8001/api/chat" \
    -H "Content-Type: application/json" \
    -d "{
        \"message\": $(echo "$INITIAL_PROMPT" | jq -Rs .),
        \"profile\": \"entity\",
        \"provider\": \"moonshot\"
    }" > /tmp/initial_response.json 2>&1 &

echo ""
echo "✅ ペア起動完了！"
echo ""
echo "🌐 Web UI:"
echo "   Entity A: http://localhost:8001"
echo "   Entity B: http://localhost:8002"
echo ""
echo "📝 ログ確認:"
echo "   docker logs -f entity-a"
echo "   docker logs -f entity-b"
echo ""
echo "🛑 停止するには:"
echo "   docker compose -f docker-compose.pair.yml down"
echo ""
echo "🌍 二人で世界を素晴らしくしよう！"
