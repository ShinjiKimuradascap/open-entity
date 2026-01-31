"""Owner notification utility for AI Collaboration Platform.

This module provides functions to notify the owner of various events,
task completions, and errors. Notifications are both printed to console
and persisted to OWNER_MESSAGES.md.
"""

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# 定数
OWNER_MESSAGES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "OWNER_MESSAGES.md"
)

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

LEVEL_EMOJI = {
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "🚨",
    "success": "✅"
}

# Slackカラー設定
SLACK_COLOR = {
    "info": "#36a64f",      # 緑
    "warning": "#ff9900",   # オレンジ
    "error": "#ff0000",     # 赤
    "success": "#36a64f"    # 緑
}


def _send_slack_notification(
    title: str,
    message: str,
    level: str = "info",
    metadata: Optional[dict] = None
) -> bool:
    """
    Slack Webhookに通知を送信する（内部関数）
    
    Args:
        title: 通知タイトル
        message: 通知メッセージ
        level: 重要度
        metadata: 追加メタデータ
    
    Returns:
        bool: 送信成功時True
    """
    if not SLACK_WEBHOOK_URL:
        return False
    
    # メタデータをフィールドに変換
    fields = []
    if metadata:
        for key, value in metadata.items():
            fields.append({
                "title": key,
                "value": str(value),
                "short": True
            })
    
    # Slackメッセージの構築
    payload = {
        "attachments": [{
            "color": SLACK_COLOR.get(level, "#36a64f"),
            "title": title,
            "text": message,
            "fields": fields if fields else None,
            "footer": "Open Entity",
            "ts": int(datetime.now().timestamp())
        }]
    }
    
    # Noneのフィールドを削除
    if not fields:
        del payload["attachments"][0]["fields"]
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200
    except Exception as e:
        print(f"[WARN] Slack notification failed: {e}")
        return False


def notify_owner(
    message: str,
    level: str = "info",
    title: Optional[str] = None,
    metadata: Optional[dict] = None
) -> bool:
    """
    オーナーに通知を送信する
    
    Args:
        message: 通知メッセージ本文
        level: 重要度 (info/warning/error/success)
        title: 通知タイトル（省略時はレベルに応じたデフォルト）
        metadata: 追加メタデータ（オプション）
    
    Returns:
        bool: 書き込み成功時True
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M %Z")
    
    if title is None:
        title = f"Open Entity Notification ({level.upper()})"
    
    emoji = LEVEL_EMOJI.get(level, "📌")
    
    # メタデータ部分の構築
    metadata_section = ""
    if metadata:
        metadata_section = "\n**Metadata:**\n"
        for key, value in metadata.items():
            metadata_section += f"- {key}: {value}\n"
    
    # エントリの構築
    entry = f"""\n## {timestamp} - {emoji} {title}

**Level:** `{level}`

{message}{metadata_section}

---
*自動生成 by Open Entity*
"""
    
    try:
        # ファイルに追記
        with open(OWNER_MESSAGES_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
        
        print(f"[NOTIFY] Owner notification written: {title} ({level})")
        
        # Slack通知（設定されている場合）
        slack_result = _send_slack_notification(title, message, level, metadata)
        if slack_result:
            print(f"[NOTIFY] Slack notification sent: {title}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to write notification: {e}")
        return False


def notify_task_complete(
    task_id: str,
    task_name: str,
    result: str = "success",
    details: Optional[str] = None
) -> bool:
    """タスク完了通知"""
    title = f"Task Completed: {task_name}"
    message = f"**Task ID:** {task_id}\n\n**Result:** {result}"
    if details:
        message += f"\n\n**Details:**\n{details}"
    
    return notify_owner(message, level="success", title=title)


def notify_error(
    error_message: str,
    context: Optional[str] = None,
    task_id: Optional[str] = None
) -> bool:
    """エラー通知"""
    title = "Error Occurred"
    message = error_message
    
    metadata = {}
    if context:
        metadata["context"] = context
    if task_id:
        metadata["task_id"] = task_id
    
    return notify_owner(message, level="error", title=title, metadata=metadata)


def notify_progress(
    task_name: str,
    progress: str,
    next_action: Optional[str] = None
) -> bool:
    """進捗報告"""
    title = f"Progress: {task_name}"
    message = f"**Current Progress:** {progress}"
    if next_action:
        message += f"\n\n**Next Action:** {next_action}"
    
    return notify_owner(message, level="info", title=title)


# 簡単なテスト
if __name__ == "__main__":
    print("Testing notify_owner tool...")
    
    # テスト通知
    notify_owner(
        "This is a test notification from the notify_owner tool.",
        level="info",
        title="Test Notification",
        metadata={"test": "value", "version": "1.0"}
    )
    
    notify_task_complete(
        task_id="TEST-001",
        task_name="Notify Owner Tool Implementation",
        result="success",
        details="Tool created and tested successfully."
    )
    
    print("Test completed. Check OWNER_MESSAGES.md for results.")
