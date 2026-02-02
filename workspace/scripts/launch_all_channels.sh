#!/bin/bash
# 全SNSチャネル同時ローンチスクリプト

echo "🚀 Open Entity マルチチャネルローンチ開始"
echo "============================================"

# Dev.to投稿
echo "📧 Dev.to投稿中..."
python3 scripts/post_devto.py > /tmp/devto_result.json 2>&1 &
DEVTO_PID=$!

# Twitter投稿
echo "🐦 Twitter投稿中..."
python3 scripts/auto_post_twitter.py template > /tmp/twitter_result.json 2>&1 &
TWITTER_PID=$!

# 完了待ち
echo "⏳ 投稿完了待ち..."
wait $DEVTO_PID
wait $TWITTER_PID

# 結果表示
echo ""
echo "============================================"
echo "📊 投稿結果"
echo "============================================"
echo "Dev.to:"
cat /tmp/devto_result.json
echo ""
echo "Twitter:"
cat /tmp/twitter_result.json

echo ""
echo "✅ 全チャネル投稿完了"
echo "📅 $(date '+%Y-%m-%d %H:%M:%S')"
