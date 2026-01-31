#!/bin/bash
# Open Entity ペア起動スクリプト
# 2つのエンティティを起動し、互いに通信させる

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ポート設定
PORT_A=8001
PORT_B=8002

# サンドボックス設定（この外には出られない）
SANDBOX_DIR="$SCRIPT_DIR"
export MOCO_WORKING_DIRECTORY="$SANDBOX_DIR"

echo "🔒 サンドボックス: $SANDBOX_DIR"

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

echo "🚀 Open Entity ペアを起動します..."
echo ""
echo "🌍 ビジョン: 世界を素晴らしくすること"
echo ""
echo "   Entity A: http://localhost:$PORT_A"
echo "   Entity B: http://localhost:$PORT_B"
echo ""

# Entity A を起動
echo "📦 Entity A を起動中..."
ENTITY_PORT=$PORT_A PEER_PORT=$PORT_B PORT=$PORT_A \
    moco ui --host 0.0.0.0 --port $PORT_A --reload > /tmp/entity_a.log 2>&1 &
PID_A=$!
echo "   PID: $PID_A"

# 少し待機
sleep 3

# Entity B を起動
echo "📦 Entity B を起動中..."
ENTITY_PORT=$PORT_B PEER_PORT=$PORT_A PORT=$PORT_B \
    moco ui --host 0.0.0.0 --port $PORT_B --reload > /tmp/entity_b.log 2>&1 &
PID_B=$!
echo "   PID: $PID_B"

# 起動完了まで待機
echo "⏳ 起動を待機中..."
sleep 8

# 起動確認
echo "🔍 起動確認..."
if curl -s "http://localhost:$PORT_A/api/profiles" > /dev/null; then
    echo "   ✅ Entity A: OK"
else
    echo "   ❌ Entity A: FAILED"
fi

if curl -s "http://localhost:$PORT_B/api/profiles" > /dev/null; then
    echo "   ✅ Entity B: OK"
else
    echo "   ❌ Entity B: FAILED"
fi

echo ""
echo "🎬 最初のメッセージを Entity A に送信..."

# 最初のメッセージを送信
curl -s -X POST "http://localhost:$PORT_A/api/chat" \
    -H "Content-Type: application/json" \
    -d "{
        \"message\": $(echo "$INITIAL_PROMPT" | jq -Rs .),
        \"profile\": \"entity\",
        \"provider\": \"${LLM_PROVIDER:-openrouter}\"
    }" > /tmp/initial_response.json &

echo ""
echo "✅ ペア起動完了！"
echo ""
echo "🌐 Web UI:"
echo "   Entity A: http://localhost:$PORT_A"
echo "   Entity B: http://localhost:$PORT_B"
echo ""
echo "📝 ログ確認:"
echo "   tail -f /tmp/entity_a.log"
echo "   tail -f /tmp/entity_b.log"
echo ""
echo "🛑 停止するには:"
echo "   kill $PID_A $PID_B"
echo ""
echo "🌍 二人で世界を素晴らしくしよう！"
echo ""

# プロセスを待機（Ctrl+Cで終了）
wait $PID_A $PID_B
