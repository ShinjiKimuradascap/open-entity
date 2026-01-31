#!/usr/bin/env python3
"""
Moltbook参加依頼通知スクリプト
"""
import sys
sys.path.insert(0, 'tools')

from notify_owner import notify_owner

notify_owner(
    message="Moltbookへの参加が必要です。\n\n参加方法:\n1. Moltbook (https://moltbook.com) にアクセス\n2. Create Agentで新規エージェント作成\n3. API Key, Agent ID, X(Twitter)検証コードを取得\n\n.envファイルにMOLTBOOK_API_KEY, MOLTBOOK_AGENT_ID, MOLTBOOK_X_CODEを設定してください。",
    level="info",
    title="Moltbook参加準備完了 - 認証情報が必要です",
    metadata={
        "status": "waiting_for_credentials",
        "action_required": "Moltbook signup"
    }
)

print("Notification sent to OWNER_MESSAGES.md")
