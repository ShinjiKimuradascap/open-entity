#!/bin/bash
# Auto Restart Service 管理スクリプト
# Usage: ./scripts/manage_auto_restart.sh [start|stop|restart|status|logs|test]

set -e

SERVICE_NAME="auto_restart"
PID_FILE="/home/moco/workspace/data/auto_restart.pid"
LOG_FILE="/home/moco/workspace/logs/auto_restart.log"
SERVICE_FILE="/home/moco/workspace/services/auto_restart_service.py"

colors() {
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
}

check_colors() {
    if [ -t 1 ]; then
        colors
    fi
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_colors

# PIDファイルからPIDを取得
get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

# プロセスが実行中か確認
is_running() {
    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# サービスを起動
start_service() {
    log_info "Auto Restart Service を起動します..."
    
    if is_running; then
        log_warning "サービスは既に実行中です (PID: $(get_pid))"
        return 0
    fi
    
    # ログディレクトリを作成
    mkdir -p /home/moco/workspace/logs
    mkdir -p /home/moco/workspace/data
    
    # バックグラウンドで起動
    nohup python3 "$SERVICE_FILE" >> "$LOG_FILE" 2>&1 &
    
    # PIDを保存
    echo $! > "$PID_FILE"
    
    # 起動を待機
    sleep 2
    
    if is_running; then
        log_success "サービスを起動しました (PID: $(get_pid))"
        log_info "ログファイル: $LOG_FILE"
    else
        log_error "サービスの起動に失敗しました"
        return 1
    fi
}

# サービスを停止
stop_service() {
    log_info "Auto Restart Service を停止します..."
    
    if ! is_running; then
        log_warning "サービスは実行されていません"
        rm -f "$PID_FILE"
        return 0
    fi
    
    local pid=$(get_pid)
    
    # SIGTERMを送信
    kill -TERM "$pid" 2>/dev/null || true
    
    # 停止を待機（最大10秒）
    local count=0
    while is_running && [ $count -lt 10 ]; do
        sleep 1
        count=$((count + 1))
    done
    
    # 強制終了（必要な場合）
    if is_running; then
        log_warning "強制終了します..."
        kill -KILL "$pid" 2>/dev/null || true
        sleep 1
    fi
    
    rm -f "$PID_FILE"
    
    if ! is_running; then
        log_success "サービスを停止しました"
    else
        log_error "サービスの停止に失敗しました"
        return 1
    fi
}

# サービスを再起動
restart_service() {
    log_info "Auto Restart Service を再起動します..."
    stop_service
    sleep 1
    start_service
}

# ステータスを表示
show_status() {
    echo "========================================"
    echo "  Auto Restart Service Status"
    echo "========================================"
    
    if is_running; then
        local pid=$(get_pid)
        log_success "サービスは実行中です (PID: $pid)"
        
        # プロセス情報を表示
        ps -p "$pid" -o pid,ppid,cmd,etime 2>/dev/null || true
        
        # 状態ファイルがあれば表示
        local state_file="/home/moco/workspace/data/auto_restart_state.json"
        if [ -f "$state_file" ]; then
            echo ""
            log_info "最新の状態:"
            python3 -c "import json; data=json.load(open('$state_file')); print(f\"  状態: {data.get('state', 'N/A')}\"); print(f\"  タスク確認: {data.get('stats', {}).get('total_checks', 0)}回\"); print(f\"  進捗報告: {data.get('stats', {}).get('total_reports', 0)}回\"); print(f\"  クラッシュ: {data.get('crash_count', 0)}回\")" 2>/dev/null || true
        fi
    else
        log_warning "サービスは停止しています"
        
        # 前回の状態を確認
        local state_file="/home/moco/workspace/data/auto_restart_state.json"
        if [ -f "$state_file" ]; then
            log_info "前回の実行状態:"
            python3 -c "import json; data=json.load(open('$state_file')); print(f\"  最終状態: {data.get('state', 'N/A')}\"); print(f\"  保存時刻: {data.get('saved_at', 'N/A')}\")" 2>/dev/null || true
        fi
    fi
    
    echo ""
    echo "ログファイル: $LOG_FILE"
    if [ -f "$LOG_FILE" ]; then
        local log_size=$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null || echo "0")
        log_info "ログサイズ: $(numfmt --to=iec $log_size 2>/dev/null || echo "${log_size} bytes")"
    fi
    echo "========================================"
}

# ログを表示
show_logs() {
    local lines=${1:-50}
    
    if [ -f "$LOG_FILE" ]; then
        echo "========================================"
        echo "  最新の $lines 行のログ"
        echo "========================================"
        tail -n "$lines" "$LOG_FILE"
        echo "========================================"
    else
        log_warning "ログファイルが見つかりません: $LOG_FILE"
    fi
}

# テストを実行
run_test() {
    log_info "テストを実行します..."
    python3 "$SERVICE_FILE" --test
}

# Systemdサービスをインストール
install_systemd() {
    log_info "Systemdサービスをインストールします..."
    
    local service_file="/home/moco/workspace/setup/auto_restart.service"
    
    if [ ! -f "$service_file" ]; then
        log_error "サービスファイルが見つかりません: $service_file"
        return 1
    fi
    
    sudo cp "$service_file" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable auto_restart
    
    log_success "Systemdサービスをインストールしました"
    log_info "開始: sudo systemctl start auto_restart"
    log_info "停止: sudo systemctl stop auto_restart"
    log_info "状態: sudo systemctl status auto_restart"
}

# 使用方法を表示
show_usage() {
    echo "使用方法: $0 [コマンド]"
    echo ""
    echo "コマンド:"
    echo "  start       サービスを起動"
    echo "  stop        サービスを停止"
    echo "  restart     サービスを再起動"
    echo "  status      サービスの状態を表示"
    echo "  logs [N]    最新のN行のログを表示（デフォルト: 50）"
    echo "  test        テストモードで実行"
    echo "  install     Systemdサービスとしてインストール"
    echo "  help        このヘルプを表示"
    echo ""
    echo "例:"
    echo "  $0 start"
    echo "  $0 logs 100"
}

# メイン処理
main() {
    case "${1:-help}" in
        start)
            start_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            restart_service
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs "${2:-50}"
            ;;
        test)
            run_test
            ;;
        install)
            install_systemd
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            log_error "不明なコマンド: $1"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
