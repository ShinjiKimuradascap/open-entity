#!/usr/bin/env python3
"""
自動進捗報告スクリプト
30分ごとにreport_to_peer()で進捗を報告
"""

import json
import os
import sys
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_todo_status():
    """タスク状況を読み取る（tasks.dbから）"""
    try:
        import sqlite3
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, status FROM todos")
        todos = cursor.fetchall()
        conn.close()
        
        completed = sum(1 for t in todos if t[2] == 'completed')
        in_progress = sum(1 for t in todos if t[2] == 'in_progress')
        pending = sum(1 for t in todos if t[2] == 'pending')
        
        return {
            'total': len(todos),
            'completed': completed,
            'in_progress': in_progress,
            'pending': pending
        }
    except Exception as e:
        return {'error': str(e)}

def generate_report():
    """進捗レポートを生成"""
    status = get_todo_status()
    now = datetime.now().strftime('%Y-%m-%d %H:%M JST')
    
    if 'error' in status:
        return f"[{now}] タスク状況取得エラー: {status['error']}"
    
    total = status['total']
    completed = status['completed']
    in_progress = status['in_progress']
    pending = status['pending']
    
    if total > 0:
        progress_pct = (completed / total) * 100
    else:
        progress_pct = 0
    
    report = f"""
[{now}] 自動進捗報告
━━━━━━━━━━━━━━━━━━━━━━━━
📊 タスク状況: {completed}/{total} 完了 ({progress_pct:.1f}%)
   - ✅ 完了: {completed}
   - 🔄 実行中: {in_progress}
   - ⏳ 未着手: {pending}

📝 次のアクション:
   - 未完了タスクの継続実行
   - todoread_all()で詳細確認
━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return report

if __name__ == '__main__':
    report = generate_report()
    print(report)
    
    # ログファイルにも記録
    log_file = 'logs/auto_report.log'
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    with open(log_file, 'a') as f:
        f.write(report + '\n')
