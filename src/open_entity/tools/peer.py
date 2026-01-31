"""
Peer Communication Tool - 相手エンティティに話しかけるツール
"""
import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 自分と相手のポート設定
MY_PORT = int(os.getenv("ENTITY_PORT", "8001"))
PEER_PORT = int(os.getenv("PEER_PORT", "8002"))
PEER_HOST = os.getenv("PEER_HOST", "localhost")


def talk_to_peer(message: str, session_id: Optional[str] = None) -> str:
    """
    相手エンティティに話しかける。
    
    Args:
        message: 相手に送るメッセージ
        session_id: セッションID（省略時は新規作成）
    
    Returns:
        相手からの応答
    
    Example:
        talk_to_peer("タスク完了した。そっちの進捗はどう？")
        talk_to_peer("todoread_all() を実行して、未完了タスクを続けろ")
    """
    url = f"http://{PEER_HOST}:{PEER_PORT}/api/chat"
    
    payload = {
        "message": message,
        "profile": "cursor",
        "provider": os.getenv("LLM_PROVIDER", "openrouter"),
    }
    
    if session_id:
        payload["session_id"] = session_id
    
    try:
        with httpx.Client(timeout=300.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "No response from peer")
    except httpx.ConnectError:
        return f"❌ ピアに接続できません ({PEER_HOST}:{PEER_PORT})。相手が起動していない可能性があります。"
    except httpx.TimeoutException:
        return f"⏱️ ピアからの応答がタイムアウトしました。相手が処理中の可能性があります。"
    except Exception as e:
        logger.error(f"Error talking to peer: {e}")
        return f"❌ ピア通信エラー: {e}"


def wake_up_peer() -> str:
    """
    相手エンティティを起こす（タスク継続を促す）。
    
    Returns:
        相手からの応答
    """
    prompt = """todoread_all() を確認して、未完了タスクを実行しろ。
タスクがなければ新しい短期・中期・長期タスクを todowrite() で作成して実行を継続しろ。
完了したら talk_to_peer() で俺に報告しろ。"""
    
    return talk_to_peer(prompt)


def report_to_peer(status: str, next_action: str = "") -> str:
    """
    相手エンティティに進捗報告する（非同期・投げっぱなし）。
    
    応答を待たずにすぐ戻るので、自分のタスクを継続できる。
    
    Args:
        status: 現在の状態（例: "S1完了", "エラー発生"）
        next_action: 次にやること
    
    Returns:
        送信結果のみ（相手の応答は待たない）
    """
    import threading
    
    message = f"""進捗報告:
- 状態: {status}
- 次のアクション: {next_action or "タスク継続"}

お前も独立して todoread_all() でタスク確認して、作業を継続しろ。
定期的に report_to_peer() で俺に報告しろ（応答は待つな）。"""
    
    def send_async():
        try:
            url = f"http://{PEER_HOST}:{PEER_PORT}/api/chat"
            payload = {
                "message": message,
                "profile": "cursor",
                "provider": os.getenv("LLM_PROVIDER", "openrouter"),
            }
            with httpx.Client(timeout=300.0) as client:
                client.post(url, json=payload)
        except Exception as e:
            logger.error(f"Async report failed: {e}")
    
    # バックグラウンドで送信
    thread = threading.Thread(target=send_async, daemon=True)
    thread.start()
    
    return f"📤 報告を送信しました（非同期）: {status}"


def check_peer_alive() -> bool:
    """
    相手エンティティが生きているか確認。
    
    Returns:
        True if peer is responding, False otherwise
    """
    url = f"http://{PEER_HOST}:{PEER_PORT}/api/profiles"
    
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
            return response.status_code == 200
    except Exception:
        return False


def restart_peer() -> str:
    """
    相手エンティティが応答しない場合、起こす（wake_up）を試みる。
    
    まず check_peer_alive() で確認し、応答がなければ複数回 wake_up を試行。
    
    Returns:
        結果メッセージ
    """
    import time
    
    # まず生存確認
    if check_peer_alive():
        return "✅ ピアは応答しています。再起動は不要です。"
    
    # 3回 wake_up を試みる
    for attempt in range(3):
        logger.warning(f"Peer not responding, wake_up attempt {attempt + 1}/3")
        wake_up_peer()
        time.sleep(5)
        
        if check_peer_alive():
            return f"✅ ピアを起こしました（{attempt + 1}回目の試行）"
    
    return "❌ ピアが応答しません。手動で docker restart が必要かもしれません。"


