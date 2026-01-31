#!/usr/bin/env python3
"""
Peer Communication Tools
オーケストレーター用ピア通信ツール

提供機能:
- report_to_peer: 進捗報告（非同期・投げっぱなし）
- talk_to_peer: 双方向通信（応答待ち）
- wake_up_peer: ピアを起こす
- check_peer_alive: ピア生存確認
- restart_peer: ピア再起動支援

使用方法:
    from tools.peer_tools import report_to_peer, talk_to_peer
    
    # 進捗報告
    report_to_peer(status="S1完了", next_action="S2開始")
    
    # 双方向通信
    response = talk_to_peer("タスク完了した。次は何をする？")
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# デフォルト設定
DEFAULT_PEER_HOST = os.environ.get("PEER_HOST", "localhost")
DEFAULT_PEER_PORT = int(os.environ.get("PEER_PORT", "8001"))
DEFAULT_ENTITY_ID = os.environ.get("ENTITY_ID", "entity_a")
DEFAULT_PEER_ID = os.environ.get("PEER_ID", "entity_b")
DEFAULT_TIMEOUT = int(os.environ.get("PEER_TIMEOUT", "30"))


class PeerCommunicationError(Exception):
    """ピア通信エラー"""
    pass


def _get_peer_url(host: str = None, port: int = None) -> str:
    """ピアのURLを取得"""
    host = host or DEFAULT_PEER_HOST
    port = port or DEFAULT_PEER_PORT
    return f"http://{host}:{port}"


def _get_entity_id() -> str:
    """自分のエンティティIDを取得"""
    return DEFAULT_ENTITY_ID


def _get_peer_id() -> str:
    """相手のエンティティIDを取得"""
    return DEFAULT_PEER_ID


async def _send_message_async(
    message_type: str,
    payload: Dict[str, Any],
    target_id: Optional[str] = None,
    wait_response: bool = False,
    timeout: int = DEFAULT_TIMEOUT
) -> Optional[Dict[str, Any]]:
    """
    非同期でメッセージを送信
    
    Args:
        message_type: メッセージタイプ
        payload: メッセージペイロード
        target_id: 送信先エンティティID（省略時はデフォルトピア）
        wait_response: 応答を待つかどうか
        timeout: タイムアウト秒数
        
    Returns:
        応答メッセージ（wait_response=Trueの場合）
    """
    target_id = target_id or _get_peer_id()
    peer_url = _get_peer_url()
    
    message = {
        "version": "1.0",
        "msg_type": message_type,
        "sender_id": _get_entity_id(),
        "recipient_id": target_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload
    }
    
    try:
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{peer_url}/message",
                json=message,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    if wait_response:
                        return await response.json()
                    else:
                        logger.info(f"📤 メッセージ送信成功: {message_type} -> {target_id}")
                        return {"status": "sent"}
                else:
                    error_text = await response.text()
                    logger.error(f"❌ メッセージ送信失敗: {response.status} - {error_text}")
                    if wait_response:
                        raise PeerCommunicationError(f"HTTP {response.status}: {error_text}")
                    return None
                    
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ タイムアウト: {target_id} への送信が{timeout}秒で完了しませんでした")
        if wait_response:
            raise PeerCommunicationError(f"Timeout after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"❌ 送信エラー: {e}")
        if wait_response:
            raise PeerCommunicationError(str(e))
        return None


def report_to_peer(
    status: str,
    next_action: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    相手エンティティに進捗報告する（非同期・投げっぱなし）
    
    応答を待たずにすぐ戻るので、自分のタスクを継続できる。
    
    Args:
        status: 現在の状態（例: "S1完了", "エラー発生"）
        next_action: 次にやること（例: "S2開始"）
        session_id: セッションID（省略時は新規作成）
        metadata: 追加メタデータ
        
    Returns:
        送信結果メッセージ
        
    Example:
        report_to_peer(status="S1完了", next_action="S2開始")
        report_to_peer(status="エラー発生", next_action="再試行")
    """
    payload = {
        "status": status,
        "next_action": next_action,
        "session_id": session_id,
        "metadata": metadata or {},
        "report_type": "progress"
    }
    
    try:
        # 非同期実行を同期的に呼び出し（fire-and-forget）
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 既にイベントループが実行中の場合は新しいタスクとしてスケジュール
            asyncio.create_task(_send_message_async("status_report", payload))
            result = f"📤 報告を送信しました（非同期）: {status}"
        else:
            # イベントループがない場合は直接実行
            loop.run_until_complete(_send_message_async("status_report", payload))
            result = f"📤 報告を送信しました: {status}"
            
        logger.info(result)
        return result
        
    except Exception as e:
        error_msg = f"⚠️ 報告送信エラー: {e}"
        logger.error(error_msg)
        return error_msg


def talk_to_peer(
    message: str,
    session_id: Optional[str] = None,
    timeout: int = 30
) -> str:
    """
    相手エンティティに話しかける（双方向通信）
    
    Args:
        message: 相手に送るメッセージ
        session_id: セッションID（省略時は新規作成）
        timeout: 応答待ちタイムアウト（秒）
        
    Returns:
        相手からの応答文字列
        
    Example:
        response = talk_to_peer("タスク完了した。そっちの進捗はどう？")
        response = talk_to_peer("todoread_all() を実行して、未完了タスクを続けろ")
    """
    payload = {
        "message": message,
        "session_id": session_id,
        "msg_type": "direct_message"
    }
    
    try:
        loop = asyncio.get_event_loop()
        
        if loop.is_running():
            # 既に実行中の場合は新しいループを作成
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            response = new_loop.run_until_complete(
                _send_message_async("task_delegate", payload, wait_response=True, timeout=timeout)
            )
            new_loop.close()
        else:
            response = loop.run_until_complete(
                _send_message_async("task_delegate", payload, wait_response=True, timeout=timeout)
            )
        
        if response:
            # 応答からメッセージ部分を抽出
            if "payload" in response and "message" in response["payload"]:
                return response["payload"]["message"]
            elif "payload" in response:
                return json.dumps(response["payload"], ensure_ascii=False)
            else:
                return json.dumps(response, ensure_ascii=False)
        else:
            return "⚠️ 応答がありませんでした"
            
    except PeerCommunicationError as e:
        return f"❌ 通信エラー: {e}"
    except Exception as e:
        return f"❌ エラー: {e}"


def wake_up_peer() -> str:
    """
    相手エンティティを起こす（タスク継続を促す）
    
    Returns:
        相手からの応答
        
    Example:
        wake_up_peer()
    """
    payload = {
        "action": "wake_up",
        "request": "continue_tasks"
    }
    
    try:
        loop = asyncio.get_event_loop()
        
        if loop.is_running():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            response = new_loop.run_until_complete(
                _send_message_async("wake_up", payload, wait_response=True, timeout=10)
            )
            new_loop.close()
        else:
            response = loop.run_until_complete(
                _send_message_async("wake_up", payload, wait_response=True, timeout=10)
            )
        
        if response:
            return f"✅ ピアが応答しました: {response.get('payload', {}).get('status', 'awake')}"
        else:
            return "⚠️ ピアが応答しません。再起動が必要かもしれません。"
            
    except Exception as e:
        return f"❌ wake_upエラー: {e}"


def check_peer_alive() -> bool:
    """
    相手エンティティが生きているか確認
    
    Returns:
        True if peer is responding, False otherwise
        
    Example:
        if check_peer_alive():
            print("ピアは生きています")
        else:
            print("ピアに到達できません")
    """
    try:
        import aiohttp
        
        async def _check():
            peer_url = _get_peer_url()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{peer_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        
        loop = asyncio.get_event_loop()
        
        if loop.is_running():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            result = new_loop.run_until_complete(_check())
            new_loop.close()
        else:
            result = loop.run_until_complete(_check())
        
        return result
        
    except Exception as e:
        logger.debug(f"Alive check failed: {e}")
        return False


def restart_peer() -> str:
    """
    相手エンティティが応答しない場合、起こす（wake_up）を試みる
    
    まず check_peer_alive() で確認し、応答がなければ複数回 wake_up を試行。
    
    Returns:
        結果メッセージ
        
    Example:
        restart_peer()
    """
    # まず生存確認
    if check_peer_alive():
        return "✅ ピアは既に生きています"
    
    # 複数回 wake_up を試行
    for attempt in range(3):
        logger.info(f"🔄 wake_up試行 {attempt + 1}/3...")
        result = wake_up_peer()
        
        if "応答しました" in result:
            return f"✅ ピアが応答しました（試行{attempt + 1}回目）"
        
        # 少し待機
        import time
        time.sleep(2)
    
    return "❌ ピアに到達できません。手動での確認が必要です。"


# エイリアス（後方互換性）
send_progress = report_to_peer
ask_peer = talk_to_peer
ping_peer = check_peer_alive


if __name__ == "__main__":
    # テスト実行
    print("=== Peer Tools Test ===")
    
    print("\n1. check_peer_alive():")
    alive = check_peer_alive()
    print(f"   Result: {alive}")
    
    print("\n2. report_to_peer():")
    result = report_to_peer(status="テスト報告", next_action="次のタスク")
    print(f"   Result: {result}")
    
    print("\n3. talk_to_peer():")
    if alive:
        response = talk_to_peer("こんにちは！これはテストです。")
        print(f"   Response: {response}")
    else:
        print("   Skipped (peer not alive)")
    
    print("\n=== Test Complete ===")
