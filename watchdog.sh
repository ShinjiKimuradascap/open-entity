#!/bin/bash
# Open Entity Watchdog - 自律AIの監視・再起動スクリプト
#
# 使い方:
#   ./watchdog.sh          # フォアグラウンドで実行
#   nohup ./watchdog.sh &  # バックグラウンドで実行

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 設定
PROFILE="cursor"
CHECK_INTERVAL=300  # 5分ごとにチェック
LOG_FILE="$SCRIPT_DIR/watchdog.log"

# 再起動時に送るプロンプト
RESTART_PROMPT="todoread_all() を確認して、未完了タスクを実行しろ。
タスクがなければ新しい短期・中期・長期タスクを todowrite() で作成して実行を継続しろ。
絶対に最終レスポンスを出すな。ツールを呼び続けろ。"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

is_running() {
    pgrep -f "moco chat.*--profile $PROFILE" > /dev/null 2>&1
}

start_agent() {
    log "🚀 エージェントを起動します..."
    
    # パイプでプロンプトを送信
    echo "$RESTART_PROMPT" | moco chat --profile "$PROFILE" >> "$LOG_FILE" 2>&1 &
    
    log "✅ エージェント起動完了 (PID: $!)"
}

log "========================================="
log "🔄 Open Entity Watchdog 開始"
log "   プロファイル: $PROFILE"
log "   チェック間隔: ${CHECK_INTERVAL}秒"
log "========================================="

while true; do
    if is_running; then
        log "✅ エージェント稼働中"
    else
        log "⚠️ エージェント停止を検出"
        start_agent
    fi
    
    sleep "$CHECK_INTERVAL"
done
