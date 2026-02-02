"""
Sandbox Gateway Client Tools

リモートのSandbox Gatewayコンテナ内でコマンド実行・ファイル操作・サービス管理を行うためのツール。

使用方法:
    sandbox_exec("python app.py")
    sandbox_write_file("services/app.py", "print('hello')")
    sandbox_read_file("services/app.py")
    sandbox_start_service("api", "python app.py")
    sandbox_list_services()
"""

import os
import requests
from typing import Optional, Dict, Any

# Gateway設定（環境変数から取得）
SANDBOX_GATEWAY_URL = os.getenv("SANDBOX_GATEWAY_URL", "https://sandbox-gateway-501073007991.asia-northeast1.run.app")
SANDBOX_GATEWAY_TOKEN = os.getenv("SANDBOX_GATEWAY_TOKEN", "8209b21881b1e6b79d386217b6c568ec")

def _get_headers() -> Dict[str, str]:
    """認証ヘッダーを取得"""
    headers = {"Content-Type": "application/json"}
    if SANDBOX_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {SANDBOX_GATEWAY_TOKEN}"
    return headers

def _handle_response(response: requests.Response) -> Dict[str, Any]:
    """レスポンスを処理"""
    try:
        data = response.json()
    except:
        data = {"raw": response.text}
    
    if response.status_code >= 400:
        return {
            "success": False,
            "error": data.get("detail", response.text),
            "status_code": response.status_code
        }
    
    return {"success": True, **data}


def sandbox_exec(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 60,
    background: bool = False
) -> Dict[str, Any]:
    """
    Sandboxコンテナ内でコマンドを実行
    
    Args:
        command: 実行するコマンド
        cwd: 作業ディレクトリ（sandbox内の相対パス）
        timeout: タイムアウト秒数
        background: バックグラウンド実行するか
    
    Returns:
        実行結果
    
    Example:
        >>> sandbox_exec("python --version")
        {"success": True, "stdout": "Python 3.11.0", "exit_code": 0}
        
        >>> sandbox_exec("python app.py", background=True)
        {"success": True, "process_id": "proc_123"}
    """
    try:
        response = requests.post(
            f"{SANDBOX_GATEWAY_URL}/exec",
            json={
                "command": command,
                "cwd": cwd,
                "timeout": timeout,
                "background": background
            },
            headers=_get_headers(),
            timeout=timeout + 10
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def sandbox_read_file(path: str) -> Dict[str, Any]:
    """
    Sandboxコンテナ内のファイルを読み取る
    
    Args:
        path: ファイルパス（sandbox root からの相対パス）
    
    Returns:
        ファイル内容
    
    Example:
        >>> sandbox_read_file("services/app.py")
        {"success": True, "content": "print('hello')", "size": 14}
    """
    try:
        response = requests.get(
            f"{SANDBOX_GATEWAY_URL}/files/{path}",
            headers=_get_headers(),
            timeout=30
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def sandbox_write_file(path: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
    """
    Sandboxコンテナ内にファイルを書き込む
    
    Args:
        path: ファイルパス（sandbox root からの相対パス）
        content: ファイル内容
        overwrite: 既存ファイルを上書きするか
    
    Returns:
        書き込み結果
    
    Example:
        >>> sandbox_write_file("services/app.py", "from fastapi import FastAPI\\napp = FastAPI()")
        {"success": True, "status": "written", "size": 42}
    """
    try:
        response = requests.post(
            f"{SANDBOX_GATEWAY_URL}/files/{path}",
            json={
                "path": path,
                "content": content,
                "overwrite": overwrite
            },
            headers=_get_headers(),
            timeout=30
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def sandbox_delete_file(path: str) -> Dict[str, Any]:
    """
    Sandboxコンテナ内のファイルを削除
    
    Args:
        path: ファイルパス
    
    Returns:
        削除結果
    """
    try:
        response = requests.delete(
            f"{SANDBOX_GATEWAY_URL}/files/{path}",
            headers=_get_headers(),
            timeout=30
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def sandbox_start_service(
    name: str,
    command: str,
    port: Optional[int] = None,
    env: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Sandboxコンテナ内でサービスを起動
    
    Args:
        name: サービス名
        command: 起動コマンド
        port: ポート番号（オプション）
        env: 環境変数（オプション）
    
    Returns:
        起動結果
    
    Example:
        >>> sandbox_start_service("api", "python -m uvicorn app:app --port 8000")
        {"success": True, "status": "started", "pid": 123}
    """
    try:
        response = requests.post(
            f"{SANDBOX_GATEWAY_URL}/services/start",
            json={
                "name": name,
                "command": command,
                "port": port,
                "env": env
            },
            headers=_get_headers(),
            timeout=30
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def sandbox_stop_service(name: str) -> Dict[str, Any]:
    """
    Sandboxコンテナ内のサービスを停止
    
    Args:
        name: サービス名
    
    Returns:
        停止結果
    """
    try:
        response = requests.post(
            f"{SANDBOX_GATEWAY_URL}/services/stop/{name}",
            headers=_get_headers(),
            timeout=30
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def sandbox_list_services() -> Dict[str, Any]:
    """
    Sandboxコンテナ内の実行中サービス一覧
    
    Returns:
        サービス一覧
    
    Example:
        >>> sandbox_list_services()
        {"success": True, "services": [{"name": "api", "pid": 123, "status": "running"}]}
    """
    try:
        response = requests.get(
            f"{SANDBOX_GATEWAY_URL}/services",
            headers=_get_headers(),
            timeout=30
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def sandbox_service_logs(name: str, lines: int = 100) -> Dict[str, Any]:
    """
    サービスのログを取得
    
    Args:
        name: サービス名
        lines: 取得する行数
    
    Returns:
        ログ内容
    """
    try:
        response = requests.get(
            f"{SANDBOX_GATEWAY_URL}/services/logs/{name}",
            params={"lines": lines},
            headers=_get_headers(),
            timeout=30
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def sandbox_health() -> Dict[str, Any]:
    """
    Sandbox Gatewayのヘルスチェック
    
    Returns:
        Gateway情報
    """
    try:
        response = requests.get(
            f"{SANDBOX_GATEWAY_URL}/",
            headers=_get_headers(),
            timeout=10
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Gateway unreachable: {str(e)}"}
