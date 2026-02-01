"""GCP Marketplace API tools for AI Collaboration Platform.

This module provides tools to interact with the GCP API Server marketplace,
enabling listing, searching, ordering, and managing marketplace services.
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

# GCP API Server configuration
DEFAULT_GCP_API_URL = "http://34.134.116.148:8080"
GCP_API_URL = os.environ.get("GCP_API_URL", DEFAULT_GCP_API_URL)


def _make_request(
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    GCP API ServerにHTTPリクエストを送信する内部関数
    
    Args:
        endpoint: APIエンドポイント（/で始まる）
        method: HTTPメソッド
        data: リクエストボディ（POST/PUT時）
        headers: 追加ヘッダー
    
    Returns:
        レスポンスJSONまたはエラー情報
    """
    url = f"{GCP_API_URL}{endpoint}"
    
    default_headers = {"Content-Type": "application/json"}
    if headers:
        default_headers.update(headers)
    
    try:
        if data:
            data_bytes = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers=default_headers,
                method=method
            )
        else:
            req = urllib.request.Request(
                url,
                headers=default_headers,
                method=method
            )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return json.loads(response_body)
            return {"success": True, "status_code": response.status}
    
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
        return {
            "success": False,
            "error": f"HTTP {e.code}",
            "details": error_body,
            "status_code": e.code
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status_code": None
        }


def list_marketplace_services() -> Dict[str, Any]:
    """
    マーケットプレイスに登録された全サービス一覧を取得する
    
    Returns:
        サービス一覧を含むレスポンス
        {
            "success": True,
            "services": [
                {
                    "id": "service-uuid",
                    "name": "Service Name",
                    "type": "service_type",
                    "provider": "provider_id",
                    "description": "...",
                    "price": 100.0,
                    "status": "active"
                }
            ]
        }
    """
    print(f"[MARKETPLACE] Fetching service list from {GCP_API_URL}")
    
    result = _make_request("/marketplace/services")
    
    if result.get("success", False):
        services = result.get("services", [])
        print(f"[MARKETPLACE] Found {len(services)} services")
        return {
            "success": True,
            "services": services,
            "count": len(services)
        }
    else:
        print(f"[MARKETPLACE] Failed to fetch services: {result.get('error')}")
        return result


def search_services(
    query: Optional[str] = None,
    service_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    マーケットプレイスのサービスを検索する
    
    Args:
        query: 検索キーワード（サービス名・説明の部分一致）
        service_type: サービスタイプで絞り込み
    
    Returns:
        検索結果を含むレスポンス
        {
            "success": True,
            "services": [...],
            "query": "search query",
            "type_filter": "service_type"
        }
    """
    print(f"[MARKETPLACE] Searching services: query='{query}', type='{service_type}'")
    
    # Build query parameters
    params = []
    if query:
        params.append(f"q={urllib.parse.quote(query)}")
    if service_type:
        params.append(f"type={urllib.parse.quote(service_type)}")
    
    endpoint = "/marketplace/services/search"
    if params:
        endpoint += "?" + "&".join(params)
    
    result = _make_request(endpoint)
    
    if result.get("success", False):
        services = result.get("services", [])
        print(f"[MARKETPLACE] Found {len(services)} matching services")
        return {
            "success": True,
            "services": services,
            "count": len(services),
            "query": query,
            "type_filter": service_type
        }
    else:
        print(f"[MARKETPLACE] Search failed: {result.get('error')}")
        return result


def create_order(
    service_id: str,
    requirements: dict,
    max_price: Optional[float] = None,
    buyer_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    新しいオーダーを作成する
    
    Args:
        service_id: 注文するサービスのID
        requirements: 要件・詳細説明（辞書形式）
        max_price: 最大予算（オプション）
        buyer_id: 購入者ID（オプション）
    
    Returns:
        作成されたオーダー情報
        {
            "success": True,
            "order_id": "order-uuid",
            "status": "pending",
            "estimated_price": 100.0
        }
    """
    print(f"[MARKETPLACE] Creating order for service: {service_id}")
    
    # requirementsが文字列の場合は辞書に変換
    if isinstance(requirements, str):
        try:
            requirements = json.loads(requirements)
        except json.JSONDecodeError:
            requirements = {"description": requirements}
    
    data = {
        "service_id": service_id,
        "requirements": requirements
    }
    if max_price is not None:
        data["max_price"] = max_price
    if buyer_id is not None:
        data["buyer_id"] = buyer_id
    
    result = _make_request("/marketplace/orders", method="POST", data=data)
    
    if result.get("success", False):
        order_id = result.get("order_id", "unknown")
        print(f"[MARKETPLACE] Order created: {order_id}")
        return {
            "success": True,
            "order_id": order_id,
            "status": result.get("status", "pending"),
            "estimated_price": result.get("estimated_price"),
            "service_id": service_id
        }
    else:
        print(f"[MARKETPLACE] Failed to create order: {result.get('error')}")
        return result


def match_order(
    order_id: str,
    provider_id: str
) -> Dict[str, Any]:
    """
    オーダーとプロバイダーをマッチングする
    
    Args:
        order_id: マッチングするオーダーID
        provider_id: サービス提供エージェントのID
    
    Returns:
        マッチング結果
        {
            "success": True,
            "order_id": "order-uuid",
            "provider_id": "provider-uuid",
            "status": "matched"
        }
    """
    print(f"[MARKETPLACE] Matching order {order_id} with provider {provider_id}")
    
    data = {
        "order_id": order_id,
        "provider_id": provider_id
    }
    
    result = _make_request(
        f"/marketplace/orders/{order_id}/match",
        method="POST",
        data=data
    )
    
    if result.get("success", False):
        print(f"[MARKETPLACE] Order matched successfully")
        return {
            "success": True,
            "order_id": order_id,
            "provider_id": provider_id,
            "status": result.get("status", "matched")
        }
    else:
        print(f"[MARKETPLACE] Failed to match order: {result.get('error')}")
        return result


def start_order(order_id: str) -> Dict[str, Any]:
    """
    オーダーの作業を開始する
    
    Args:
        order_id: 開始するオーダーID
    
    Returns:
        開始結果
        {
            "success": True,
            "order_id": "order-uuid",
            "status": "in_progress",
            "started_at": "2026-02-01T12:00:00Z"
        }
    """
    print(f"[MARKETPLACE] Starting order: {order_id}")
    
    result = _make_request(
        f"/marketplace/orders/{order_id}/start",
        method="POST"
    )
    
    if result.get("success", False):
        print(f"[MARKETPLACE] Order started successfully")
        return {
            "success": True,
            "order_id": order_id,
            "status": result.get("status", "in_progress"),
            "started_at": result.get("started_at", datetime.utcnow().isoformat())
        }
    else:
        print(f"[MARKETPLACE] Failed to start order: {result.get('error')}")
        return result


def complete_order(
    order_id: str,
    result: str,
    rating: Optional[int] = None
) -> Dict[str, Any]:
    """
    オーダーを完了としてマークする
    
    Args:
        order_id: 完了するオーダーID
        result: 作業結果・成果物の説明
        rating: 評価（1-5、オプション）
    
    Returns:
        完了結果
        {
            "success": True,
            "order_id": "order-uuid",
            "status": "completed",
            "completed_at": "2026-02-01T12:00:00Z"
        }
    """
    print(f"[MARKETPLACE] Completing order: {order_id}")
    
    data = {"result": result}
    if rating is not None:
        if not 1 <= rating <= 5:
            return {
                "success": False,
                "error": "Rating must be between 1 and 5"
            }
        data["rating"] = rating
    
    api_result = _make_request(
        f"/marketplace/orders/{order_id}/complete",
        method="POST",
        data=data
    )
    
    if api_result.get("success", False):
        print(f"[MARKETPLACE] Order completed successfully")
        return {
            "success": True,
            "order_id": order_id,
            "status": api_result.get("status", "completed"),
            "completed_at": api_result.get("completed_at", datetime.utcnow().isoformat()),
            "rating": rating
        }
    else:
        print(f"[MARKETPLACE] Failed to complete order: {api_result.get('error')}")
        return api_result


def get_order_status(order_id: str) -> Dict[str, Any]:
    """
    オーダーの現在の状態を確認する
    
    Args:
        order_id: 確認するオーダーID
    
    Returns:
        オーダー状態情報
        {
            "success": True,
            "order_id": "order-uuid",
            "status": "in_progress",
            "service_id": "service-uuid",
            "provider_id": "provider-uuid",
            "created_at": "2026-02-01T10:00:00Z",
            "updated_at": "2026-02-01T12:00:00Z"
        }
    """
    print(f"[MARKETPLACE] Checking order status: {order_id}")
    
    result = _make_request(f"/marketplace/orders/{order_id}")
    
    if result.get("success", False):
        print(f"[MARKETPLACE] Order status: {result.get('status')}")
        return result
    else:
        print(f"[MARKETPLACE] Failed to get order status: {result.get('error')}")
        return result


def get_marketplace_stats() -> Dict[str, Any]:
    """
    マーケットプレイスの統計情報を取得する
    
    Returns:
        統計情報
        {
            "success": True,
            "stats": {
                "total_services": 100,
                "active_orders": 50,
                "completed_orders": 500,
                "total_providers": 30,
                "avg_rating": 4.5
            }
        }
    """
    print(f"[MARKETPLACE] Fetching marketplace stats from {GCP_API_URL}")
    
    result = _make_request("/marketplace/stats")
    
    if result.get("success", False):
        stats = result.get("stats", {})
        print(f"[MARKETPLACE] Stats: {stats}")
        return {
            "success": True,
            "stats": stats
        }
    else:
        print(f"[MARKETPLACE] Failed to fetch stats: {result.get('error')}")
        return result


# 後方互換性のためのエイリアス
get_service_list = list_marketplace_services
get_order = get_order_status


# 簡単なテスト
if __name__ == "__main__":
    print("=" * 60)
    print("Marketplace Tools Test")
    print(f"GCP API URL: {GCP_API_URL}")
    print("=" * 60)
    
    # 1. マーケットプレイス統計取得
    print("\n[TEST 1] Get Marketplace Stats")
    stats = get_marketplace_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    # 2. サービス一覧取得
    print("\n[TEST 2] List Services")
    services = list_marketplace_services()
    print(json.dumps(services, indent=2, ensure_ascii=False))
    
    # 3. サービス検索
    print("\n[TEST 3] Search Services")
    search_result = search_services(query="code", service_type="development")
    print(json.dumps(search_result, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 60)
    print("Test completed.")
    print("=" * 60)
