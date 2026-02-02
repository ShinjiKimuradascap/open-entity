"""
GCP Gateway Client Tools

ローカルのEntity A/BがGCP Gateway Agentを経由して
GCPの操作を行うためのツール群。

使用方法:
    gcp_deploy("ai-roulette", "gcr.io/project/image:latest")
    gcp_status("ai-roulette")
    gcp_logs("ai-roulette", lines=50)
    gcp_scale("ai-roulette", min_instances=1, max_instances=5)
"""

import os
import requests
from typing import Optional, Dict, Any

# Gateway設定（環境変数から取得）
GCP_GATEWAY_URL = os.getenv("GCP_GATEWAY_URL", "http://localhost:8080")
GCP_GATEWAY_TOKEN = os.getenv("GCP_GATEWAY_TOKEN", "")

def _get_headers() -> Dict[str, str]:
    """認証ヘッダーを取得"""
    headers = {"Content-Type": "application/json"}
    if GCP_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {GCP_GATEWAY_TOKEN}"
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
    
    return {
        "success": True,
        **data
    }


def gcp_deploy(
    service_name: str,
    image: str,
    region: str = "asia-northeast1",
    env_vars: Optional[Dict[str, str]] = None,
    memory: str = "512Mi",
    cpu: str = "1",
    min_instances: int = 0,
    max_instances: int = 10
) -> Dict[str, Any]:
    """
    GCP Cloud Runにサービスをデプロイ
    
    Args:
        service_name: サービス名（許可リスト: ai-roulette, api-server, frontend, entity-gateway, marketplace-api）
        image: Dockerイメージ（gcr.io/... など）
        region: リージョン（デフォルト: asia-northeast1）
        env_vars: 環境変数（オプション）
        memory: メモリ（デフォルト: 512Mi）
        cpu: CPU（デフォルト: 1）
        min_instances: 最小インスタンス数
        max_instances: 最大インスタンス数
    
    Returns:
        デプロイ結果
    
    Example:
        >>> gcp_deploy("ai-roulette", "gcr.io/myproject/ai-roulette:v1")
        {"success": True, "status": "deployed", "url": "https://ai-roulette-xxx.run.app"}
    """
    payload = {
        "service_name": service_name,
        "image": image,
        "region": region,
        "memory": memory,
        "cpu": cpu,
        "min_instances": min_instances,
        "max_instances": max_instances
    }
    
    if env_vars:
        payload["env_vars"] = env_vars
    
    try:
        response = requests.post(
            f"{GCP_GATEWAY_URL}/deploy",
            json=payload,
            headers=_get_headers(),
            timeout=300  # デプロイは時間がかかる
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def gcp_status(service_name: str, region: str = "asia-northeast1") -> Dict[str, Any]:
    """
    サービスのステータスを取得
    
    Args:
        service_name: サービス名
        region: リージョン
    
    Returns:
        ステータス情報
    
    Example:
        >>> gcp_status("ai-roulette")
        {"success": True, "status": "running", "url": "https://..."}
    """
    try:
        response = requests.get(
            f"{GCP_GATEWAY_URL}/status/{service_name}",
            params={"region": region},
            headers=_get_headers(),
            timeout=30
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def gcp_logs(
    service_name: str,
    lines: int = 100,
    region: str = "asia-northeast1"
) -> Dict[str, Any]:
    """
    サービスのログを取得
    
    Args:
        service_name: サービス名
        lines: 取得する行数（最大500）
        region: リージョン
    
    Returns:
        ログ情報
    
    Example:
        >>> gcp_logs("ai-roulette", lines=50)
        {"success": True, "logs": [...]}
    """
    try:
        response = requests.get(
            f"{GCP_GATEWAY_URL}/logs/{service_name}",
            params={"lines": min(lines, 500), "region": region},
            headers=_get_headers(),
            timeout=60
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def gcp_scale(
    service_name: str,
    min_instances: int,
    max_instances: int,
    region: str = "asia-northeast1"
) -> Dict[str, Any]:
    """
    サービスのインスタンス数を変更
    
    Args:
        service_name: サービス名
        min_instances: 最小インスタンス数
        max_instances: 最大インスタンス数
        region: リージョン
    
    Returns:
        スケール結果
    
    Example:
        >>> gcp_scale("ai-roulette", min_instances=1, max_instances=5)
        {"success": True, "status": "scaled"}
    """
    try:
        response = requests.post(
            f"{GCP_GATEWAY_URL}/scale",
            json={
                "service_name": service_name,
                "min_instances": min_instances,
                "max_instances": max_instances
            },
            params={"region": region},
            headers=_get_headers(),
            timeout=60
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def gcp_list_services(region: str = "asia-northeast1") -> Dict[str, Any]:
    """
    デプロイ済みサービス一覧を取得
    
    Args:
        region: リージョン
    
    Returns:
        サービス一覧
    
    Example:
        >>> gcp_list_services()
        {"success": True, "services": [...], "count": 3}
    """
    try:
        response = requests.get(
            f"{GCP_GATEWAY_URL}/services",
            params={"region": region},
            headers=_get_headers(),
            timeout=30
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def gcp_delete_service(service_name: str, region: str = "asia-northeast1") -> Dict[str, Any]:
    """
    サービスを削除（注意: 危険操作）
    
    Args:
        service_name: サービス名
        region: リージョン
    
    Returns:
        削除結果
    """
    try:
        response = requests.delete(
            f"{GCP_GATEWAY_URL}/service/{service_name}",
            params={"region": region},
            headers=_get_headers(),
            timeout=60
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def gcp_gateway_health() -> Dict[str, Any]:
    """
    GCP Gatewayのヘルスチェック
    
    Returns:
        Gateway情報
    
    Example:
        >>> gcp_gateway_health()
        {"success": True, "status": "healthy", "allowed_services": [...]}
    """
    try:
        response = requests.get(
            f"{GCP_GATEWAY_URL}/",
            headers=_get_headers(),
            timeout=10
        )
        return _handle_response(response)
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Gateway unreachable: {str(e)}"}
