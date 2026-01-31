#!/bin/bash
# ウォッチドッグ - 片方が動いてなかったら起こす
# 使用方法: ./watchdog.sh

INTERVAL=60  # 確認間隔（秒）

echo "🐕 ウォッチドッグ起動"
echo "   Entity A: http://localhost:8001"
echo "   Entity B: http://localhost:8002"
echo "   確認間隔: ${INTERVAL}秒"
echo ""

wake_up() {
    local port=$1
    local name=$2
    local provider=$3
    
    echo "🔔 ${name} を起こしています..."
    
    curl -s -X POST "http://localhost:${port}/api/chat" \
        -H "Content-Type: application/json" \
        -d "{
            \"message\": \"todoread_all() でタスクを確認して、未完了があれば実行。なければ新しいタスクを作成して実行を継続しろ。止まるな。\",
            \"profile\": \"cursor\",
            \"provider\": \"${provider}\"
        }" > /dev/null 2>&1 &
    
    echo "✅ ${name} に起床メッセージ送信"
}

while true; do
    # Entity A 確認
    if curl -s --connect-timeout 5 "http://localhost:8001/api/profiles" > /dev/null 2>&1; then
        echo "$(date '+%H:%M:%S') ✅ Entity A: alive"
    else
        echo "$(date '+%H:%M:%S') ❌ Entity A: dead - restarting..."
        docker restart entity-a
        sleep 10
        wake_up 8001 "Entity A" "moonshot"
    fi
    
    # Entity B 確認
    if curl -s --connect-timeout 5 "http://localhost:8002/api/profiles" > /dev/null 2>&1; then
        echo "$(date '+%H:%M:%S') ✅ Entity B: alive"
    else
        echo "$(date '+%H:%M:%S') ❌ Entity B: dead - restarting..."
        docker restart entity-b
        sleep 10
        wake_up 8002 "Entity B" "openrouter"
    fi
    
    echo ""
    sleep $INTERVAL
done
