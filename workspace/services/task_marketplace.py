#!/usr/bin/env python3
"""
Task Marketplace
タスクマーケットプレイス

Features:
- Service listing creation
- Task order management
- Auto-matching by category, price, rating
- Order completion and review
- Data persistence
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """サービスタイプ"""
    CODE_SERVICE = "code_service"  # コード生成・レビュー
    RESEARCH_SERVICE = "research_service"  # 調査・分析
    DESIGN_SERVICE = "design_service"  # 設計・構成
    VALIDATION_SERVICE = "validation_service"  # 検証・テスト


class PricingModel(Enum):
    """料金モデル"""
    FIXED_PRICE = "fixed_price"  # 固定価格
    HOURLY_RATE = "hourly_rate"  # 時間単価
    SUCCESS_FEE = "success_fee"  # 成果報酬


class ListingStatus(Enum):
    """出品ステータス"""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class OrderStatus(Enum):
    """注文ステータス"""
    PENDING = "pending"  # 承認待ち
    IN_PROGRESS = "in_progress"  # 進行中
    COMPLETED = "completed"  # 完了
    CANCELLED = "cancelled"  # キャンセル
    DISPUTED = "disputed"  # 紛争中


@dataclass
class ServiceListing:
    """サービス出品情報"""
    listing_id: str
    provider_id: str
    service_type: ServiceType
    title: str
    description: str
    price: float
    pricing_model: PricingModel
    category: str
    status: ListingStatus
    created_at: str
    updated_at: str
    rating: float = 0.0
    completed_orders: int = 0
    total_reviews: int = 0
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "provider_id": self.provider_id,
            "service_type": self.service_type.value,
            "title": self.title,
            "description": self.description,
            "price": self.price,
            "pricing_model": self.pricing_model.value,
            "category": self.category,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "rating": self.rating,
            "completed_orders": self.completed_orders,
            "total_reviews": self.total_reviews,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServiceListing':
        return cls(
            listing_id=data["listing_id"],
            provider_id=data["provider_id"],
            service_type=ServiceType(data["service_type"]),
            title=data["title"],
            description=data["description"],
            price=data["price"],
            pricing_model=PricingModel(data["pricing_model"]),
            category=data["category"],
            status=ListingStatus(data.get("status", "active")),
            created_at=data["created_at"],
            updated_at=data.get("updated_at", data["created_at"]),
            rating=data.get("rating", 0.0),
            completed_orders=data.get("completed_orders", 0),
            total_reviews=data.get("total_reviews", 0),
            tags=data.get("tags", [])
        )


@dataclass
class TaskOrder:
    """タスク注文情報"""
    order_id: str
    listing_id: str
    buyer_id: str
    provider_id: str
    requirements: str
    price: float
    status: OrderStatus
    created_at: str
    completed_at: Optional[str] = None
    rating: Optional[int] = None
    review: Optional[str] = None
    deliverables: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "order_id": self.order_id,
            "listing_id": self.listing_id,
            "buyer_id": self.buyer_id,
            "provider_id": self.provider_id,
            "requirements": self.requirements,
            "price": self.price,
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "rating": self.rating,
            "review": self.review,
            "deliverables": self.deliverables
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskOrder':
        return cls(
            order_id=data["order_id"],
            listing_id=data["listing_id"],
            buyer_id=data["buyer_id"],
            provider_id=data["provider_id"],
            requirements=data["requirements"],
            price=data["price"],
            status=OrderStatus(data.get("status", "pending")),
            created_at=data["created_at"],
            completed_at=data.get("completed_at"),
            rating=data.get("rating"),
            review=data.get("review"),
            deliverables=data.get("deliverables")
        )


class TaskMarketplace:
    """タスクマーケットプレイス
    
    サービス出品・注文管理・自動マッチングシステム
    """
    
    def __init__(self, data_dir: str = "data/marketplace"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 出品管理
        self.listings: Dict[str, ServiceListing] = {}
        self.agent_listings: Dict[str, List[str]] = {}  # agent_id -> [listing_ids]
        
        # 注文管理
        self.orders: Dict[str, TaskOrder] = {}
        self.agent_orders: Dict[str, Dict[str, List[str]]] = {}  # agent_id -> {as_buyer: [], as_provider: []}
        
        # カテゴリインデックス
        self.category_listings: Dict[str, List[str]] = {}  # category -> [listing_ids]
        
        self._load()
        logger.info(f"TaskMarketplace initialized")
    
    def create_listing(self, provider_id: str, service_type: ServiceType,
                      title: str, description: str, price: float,
                      pricing_model: PricingModel, category: str,
                      tags: Optional[List[str]] = None) -> str:
        """サービスを出品
        
        Args:
            provider_id: 提供者ID
            service_type: サービスタイプ
            title: タイトル
            description: 説明
            price: 価格
            pricing_model: 料金モデル
            category: カテゴリ
            tags: タグリスト
            
        Returns:
            listing_id: 出品ID
        """
        listing_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        listing = ServiceListing(
            listing_id=listing_id,
            provider_id=provider_id,
            service_type=service_type,
            title=title,
            description=description,
            price=price,
            pricing_model=pricing_model,
            category=category,
            status=ListingStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            tags=tags or []
        )
        
        self.listings[listing_id] = listing
        
        # エージェントの出品リストに追加
        if provider_id not in self.agent_listings:
            self.agent_listings[provider_id] = []
        self.agent_listings[provider_id].append(listing_id)
        
        # カテゴリインデックスに追加
        if category not in self.category_listings:
            self.category_listings[category] = []
        self.category_listings[category].append(listing_id)
        
        logger.info(f"Listing created: {listing_id} by {provider_id}")
        self._save()
        return listing_id
    
    def update_listing(self, listing_id: str, **kwargs) -> Dict[str, Any]:
        """出品情報を更新
        
        Args:
            listing_id: 出品ID
            **kwargs: 更新するフィールド
            
        Returns:
            更新結果
        """
        if listing_id not in self.listings:
            return {"success": False, "error": "Listing not found"}
        
        listing = self.listings[listing_id]
        allowed_fields = ["title", "description", "price", "category", "tags"]
        
        for field, value in kwargs.items():
            if field in allowed_fields and hasattr(listing, field):
                setattr(listing, field, value)
        
        # statusは特別処理
        if "status" in kwargs:
            try:
                listing.status = ListingStatus(kwargs["status"])
            except ValueError:
                return {"success": False, "error": f"Invalid status: {kwargs['status']}"}
        
        listing.updated_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"Listing updated: {listing_id}")
        self._save()
        return {"success": True, "listing_id": listing_id}
    
    def create_order(self, listing_id: str, buyer_id: str,
                    requirements: str) -> Dict[str, Any]:
        """注文を作成
        
        Args:
            listing_id: 出品ID
            buyer_id: 購入者ID
            requirements: 要件詳細
            
        Returns:
            作成結果
        """
        if listing_id not in self.listings:
            return {"success": False, "error": "Listing not found"}
        
        listing = self.listings[listing_id]
        if listing.status != ListingStatus.ACTIVE:
            return {"success": False, "error": f"Listing is {listing.status.value}"}
        
        order_id = str(uuid.uuid4())
        
        order = TaskOrder(
            order_id=order_id,
            listing_id=listing_id,
            buyer_id=buyer_id,
            provider_id=listing.provider_id,
            requirements=requirements,
            price=listing.price,
            status=OrderStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        self.orders[order_id] = order
        
        # エージェントの注文リストに追加
        if buyer_id not in self.agent_orders:
            self.agent_orders[buyer_id] = {"as_buyer": [], "as_provider": []}
        self.agent_orders[buyer_id]["as_buyer"].append(order_id)
        
        if listing.provider_id not in self.agent_orders:
            self.agent_orders[listing.provider_id] = {"as_buyer": [], "as_provider": []}
        self.agent_orders[listing.provider_id]["as_provider"].append(order_id)
        
        logger.info(f"Order created: {order_id} for listing {listing_id}")
        self._save()
        return {"success": True, "order_id": order_id, "price": listing.price}
    
    def accept_order(self, order_id: str, provider_id: str) -> Dict[str, Any]:
        """注文を承諾
        
        Args:
            order_id: 注文ID
            provider_id: 提供者ID
            
        Returns:
            処理結果
        """
        if order_id not in self.orders:
            return {"success": False, "error": "Order not found"}
        
        order = self.orders[order_id]
        if order.provider_id != provider_id:
            return {"success": False, "error": "Not your order"}
        
        if order.status != OrderStatus.PENDING:
            return {"success": False, "error": f"Order is {order.status.value}"}
        
        order.status = OrderStatus.IN_PROGRESS
        
        logger.info(f"Order accepted: {order_id}")
        self._save()
        return {"success": True, "order_id": order_id}
    
    def complete_order(self, order_id: str, provider_id: str,
                      deliverables: str) -> Dict[str, Any]:
        """注文を完了（提供者側）
        
        Args:
            order_id: 注文ID
            provider_id: 提供者ID
            deliverables: 成果物
            
        Returns:
            処理結果
        """
        if order_id not in self.orders:
            return {"success": False, "error": "Order not found"}
        
        order = self.orders[order_id]
        if order.provider_id != provider_id:
            return {"success": False, "error": "Not your order"}
        
        if order.status != OrderStatus.IN_PROGRESS:
            return {"success": False, "error": f"Order is {order.status.value}"}
        
        order.deliverables = deliverables
        # 注: 実際の完了はbuyerがレビューするまでPENDING状態
        
        logger.info(f"Order completed by provider: {order_id}")
        self._save()
        return {"success": True, "order_id": order_id}
    
    def review_order(self, order_id: str, buyer_id: str,
                    rating: int, review: str) -> Dict[str, Any]:
        """注文をレビューして完了（購入者側）
        
        Args:
            order_id: 注文ID
            buyer_id: 購入者ID
            rating: 評価（1-5）
            review: レビュー内容
            
        Returns:
            処理結果
        """
        if order_id not in self.orders:
            return {"success": False, "error": "Order not found"}
        
        order = self.orders[order_id]
        if order.buyer_id != buyer_id:
            return {"success": False, "error": "Not your order"}
        
        if not 1 <= rating <= 5:
            return {"success": False, "error": "Rating must be 1-5"}
        
        order.rating = rating
        order.review = review
        order.status = OrderStatus.COMPLETED
        order.completed_at = datetime.now(timezone.utc).isoformat()
        
        # 出品の評価を更新
        if order.listing_id in self.listings:
            listing = self.listings[order.listing_id]
            listing.completed_orders += 1
            listing.total_reviews += 1
            # 加重平均で評価を更新
            listing.rating = ((listing.rating * (listing.total_reviews - 1)) + rating) / listing.total_reviews
        
        logger.info(f"Order reviewed and completed: {order_id}, rating: {rating}")
        self._save()
        return {"success": True, "order_id": order_id}
    
    def cancel_order(self, order_id: str, agent_id: str) -> Dict[str, Any]:
        """注文をキャンセル
        
        Args:
            order_id: 注文ID
            agent_id: キャンセルするエージェントID
            
        Returns:
            処理結果
        """
        if order_id not in self.orders:
            return {"success": False, "error": "Order not found"}
        
        order = self.orders[order_id]
        if order.buyer_id != agent_id and order.provider_id != agent_id:
            return {"success": False, "error": "Not your order"}
        
        if order.status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED]:
            return {"success": False, "error": f"Order is already {order.status.value}"}
        
        order.status = OrderStatus.CANCELLED
        
        logger.info(f"Order cancelled: {order_id}")
        self._save()
        return {"success": True, "order_id": order_id}
    
    def find_matching_services(self, category: Optional[str] = None,
                              max_price: Optional[float] = None,
                              min_rating: float = 0.0,
                              service_type: Optional[ServiceType] = None) -> List[Dict[str, Any]]:
        """条件に合うサービスを検索
        
        Args:
            category: カテゴリ
            max_price: 最大価格
            min_rating: 最低評価
            service_type: サービスタイプ
            
        Returns:
            マッチした出品リスト
        """
        results = []
        
        # カテゴリで絞り込み
        if category and category in self.category_listings:
            listing_ids = self.category_listings[category]
        else:
            listing_ids = list(self.listings.keys())
        
        for listing_id in listing_ids:
            listing = self.listings[listing_id]
            
            # アクティブな出品のみ
            if listing.status != ListingStatus.ACTIVE:
                continue
            
            # 価格フィルタ
            if max_price is not None and listing.price > max_price:
                continue
            
            # 評価フィルタ
            if listing.rating < min_rating:
                continue
            
            # サービスタイプフィルタ
            if service_type and listing.service_type != service_type:
                continue
            
            results.append({
                "listing_id": listing.listing_id,
                "provider_id": listing.provider_id,
                "title": listing.title,
                "description": listing.description,
                "price": listing.price,
                "pricing_model": listing.pricing_model.value,
                "category": listing.category,
                "service_type": listing.service_type.value,
                "rating": round(listing.rating, 2),
                "completed_orders": listing.completed_orders,
                "tags": listing.tags
            })
        
        # 評価の高い順にソート
        results.sort(key=lambda x: x["rating"], reverse=True)
        return results
    
    def get_agent_listings(self, agent_id: str) -> List[Dict[str, Any]]:
        """エージェントの出品一覧を取得
        
        Args:
            agent_id: エージェントID
            
        Returns:
            出品リスト
        """
        if agent_id not in self.agent_listings:
            return []
        
        return [
            self.listings[listing_id].to_dict()
            for listing_id in self.agent_listings[agent_id]
        ]
    
    def get_agent_orders(self, agent_id: str,
                        as_buyer: bool = True) -> List[Dict[str, Any]]:
        """エージェントの注文一覧を取得
        
        Args:
            agent_id: エージェントID
            as_buyer: 購入者としての注文を取得する場合True
            
        Returns:
            注文リスト
        """
        if agent_id not in self.agent_orders:
            return []
        
        order_type = "as_buyer" if as_buyer else "as_provider"
        order_ids = self.agent_orders[agent_id].get(order_type, [])
        
        return [
            self.orders[order_id].to_dict()
            for order_id in order_ids
        ]
    
    def get_order_details(self, order_id: str) -> Optional[Dict[str, Any]]:
        """注文詳細を取得
        
        Args:
            order_id: 注文ID
            
        Returns:
            注文詳細
        """
        if order_id not in self.orders:
            return None
        
        order = self.orders[order_id]
        listing = self.listings.get(order.listing_id)
        
        result = order.to_dict()
        if listing:
            result["listing_title"] = listing.title
            result["service_type"] = listing.service_type.value
        
        return result
    
    def get_listing_details(self, listing_id: str) -> Optional[Dict[str, Any]]:
        """出品詳細を取得
        
        Args:
            listing_id: 出品ID
            
        Returns:
            出品詳細
        """
        if listing_id not in self.listings:
            return None
        
        return self.listings[listing_id].to_dict()
    
    def get_marketplace_stats(self) -> Dict[str, Any]:
        """マーケットプレイス統計を取得
        
        Returns:
            統計情報
        """
        active_listings = sum(1 for l in self.listings.values() if l.status == ListingStatus.ACTIVE)
        
        # 注文統計
        status_counts = {}
        for order in self.orders.values():
            status = order.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # カテゴリ統計
        category_counts = {}
        for listing in self.listings.values():
            cat = listing.category
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        # サービスタイプ統計
        service_type_counts = {}
        for listing in self.listings.values():
            st = listing.service_type.value
            service_type_counts[st] = service_type_counts.get(st, 0) + 1
        
        # 収益統計
        total_completed_value = sum(
            order.price for order in self.orders.values()
            if order.status == OrderStatus.COMPLETED
        )
        
        return {
            "total_listings": len(self.listings),
            "active_listings": active_listings,
            "total_orders": len(self.orders),
            "orders_by_status": status_counts,
            "categories": category_counts,
            "service_types": service_type_counts,
            "total_completed_value": round(total_completed_value, 2),
            "top_providers": self._get_top_providers(5)
        }
    
    def _get_top_providers(self, limit: int = 5) -> List[Dict[str, Any]]:
        """トップ提供者を取得
        
        Args:
            limit: 取得件数
            
        Returns:
            トップ提供者リスト
        """
        provider_stats = {}
        
        for listing in self.listings.values():
            pid = listing.provider_id
            if pid not in provider_stats:
                provider_stats[pid] = {
                    "provider_id": pid,
                    "total_orders": 0,
                    "avg_rating": 0.0,
                    "listing_count": 0
                }
            
            provider_stats[pid]["total_orders"] += listing.completed_orders
            provider_stats[pid]["listing_count"] += 1
            
            # 評価の平均
            if listing.total_reviews > 0:
                provider_stats[pid]["avg_rating"] = listing.rating
        
        # 完了注文数でソート
        sorted_providers = sorted(
            provider_stats.values(),
            key=lambda x: x["total_orders"],
            reverse=True
        )
        
        return sorted_providers[:limit]
    
    def search_listings(self, query: str) -> List[Dict[str, Any]]:
        """出品を検索
        
        Args:
            query: 検索クエリ
            
        Returns:
            マッチした出品リスト
        """
        query_lower = query.lower()
        results = []
        
        for listing in self.listings.values():
            if listing.status != ListingStatus.ACTIVE:
                continue
            
            # タイトル、説明、カテゴリ、タグで検索
            searchable_text = f"{listing.title} {listing.description} {listing.category}".lower()
            tags_text = " ".join(listing.tags).lower()
            
            if query_lower in searchable_text or query_lower in tags_text:
                results.append(listing.to_dict())
        
        return results
    
    def _save(self):
        """データを保存"""
        listings_path = self.data_dir / "listings.json"
        orders_path = self.data_dir / "orders.json"
        
        # 出品を保存
        listings_data = {
            "listings": {lid: l.to_dict() for lid, l in self.listings.items()},
            "agent_listings": self.agent_listings,
            "category_listings": self.category_listings
        }
        with open(listings_path, 'w') as f:
            json.dump(listings_data, f, indent=2)
        
        # 注文を保存
        orders_data = {
            "orders": {oid: o.to_dict() for oid, o in self.orders.items()},
            "agent_orders": self.agent_orders
        }
        with open(orders_path, 'w') as f:
            json.dump(orders_data, f, indent=2)
    
    def _load(self):
        """データを読み込み"""
        listings_path = self.data_dir / "listings.json"
        orders_path = self.data_dir / "orders.json"
        
        # 出品を読み込み
        if listings_path.exists():
            with open(listings_path, 'r') as f:
                data = json.load(f)
            
            for listing_id, listing_data in data.get("listings", {}).items():
                self.listings[listing_id] = ServiceListing.from_dict(listing_data)
            
            self.agent_listings = data.get("agent_listings", {})
            self.category_listings = data.get("category_listings", {})
        
        # 注文を読み込み
        if orders_path.exists():
            with open(orders_path, 'r') as f:
                data = json.load(f)
            
            for order_id, order_data in data.get("orders", {}).items():
                self.orders[order_id] = TaskOrder.from_dict(order_data)
            
            self.agent_orders = data.get("agent_orders", {})


# グローバルインスタンス管理
_marketplace_instance: Optional[TaskMarketplace] = None


def get_marketplace() -> TaskMarketplace:
    """マーケットプレイスのインスタンスを取得"""
    global _marketplace_instance
    if _marketplace_instance is None:
        _marketplace_instance = TaskMarketplace()
    return _marketplace_instance


if __name__ == "__main__":
    # 簡易テスト
    logging.basicConfig(level=logging.INFO)
    
    marketplace = TaskMarketplace()
    
    # テスト用データをクリア
    marketplace.listings.clear()
    marketplace.orders.clear()
    marketplace.agent_listings.clear()
    marketplace.agent_orders.clear()
    marketplace.category_listings.clear()
    
    print("=" * 60)
    print("TaskMarketplace 動作確認テスト")
    print("=" * 60)
    
    # 1. サービス出品テスト
    print("\n[1] サービス出品テスト")
    listing1 = marketplace.create_listing(
        provider_id="agent_coding_001",
        service_type=ServiceType.CODE_SERVICE,
        title="Pythonコードレビュー",
        description="Pythonコードの品質レビューと改善提案",
        price=50.0,
        pricing_model=PricingModel.FIXED_PRICE,
        category="programming",
        tags=["python", "review", "quality"]
    )
    print(f"✅ Listing 1 created: {listing1}")
    
    listing2 = marketplace.create_listing(
        provider_id="agent_research_001",
        service_type=ServiceType.RESEARCH_SERVICE,
        title="市場調査レポート",
        description="指定業界の市場調査と分析レポート作成",
        price=200.0,
        pricing_model=PricingModel.FIXED_PRICE,
        category="research",
        tags=["market", "research", "analysis"]
    )
    print(f"✅ Listing 2 created: {listing2}")
    
    listing3 = marketplace.create_listing(
        provider_id="agent_design_001",
        service_type=ServiceType.DESIGN_SERVICE,
        title="API設計コンサルティング",
        description="RESTful APIの設計レビューと改善提案",
        price=100.0,
        pricing_model=PricingModel.HOURLY_RATE,
        category="design",
        tags=["api", "design", "consulting"]
    )
    print(f"✅ Listing 3 created: {listing3}")
    
    # 2. サービス検索テスト
    print("\n[2] サービス検索テスト")
    results = marketplace.find_matching_services(
        category="programming",
        max_price=100.0
    )
    print(f"✅ Found {len(results)} programming services under $100")
    
    # 3. 注文作成テスト
    print("\n[3] 注文作成テスト")
    order_result = marketplace.create_order(
        listing_id=listing1,
        buyer_id="agent_buyer_001",
        requirements="FastAPIアプリケーションのコードレビュー"
    )
    if order_result["success"]:
        order_id = order_result["order_id"]
        print(f"✅ Order created: {order_id}, Price: ${order_result['price']}")
    else:
        print(f"❌ Order creation failed: {order_result['error']}")
        order_id = None
    
    # 4. 注文承諾テスト
    if order_id:
        print("\n[4] 注文承諾テスト")
        accept_result = marketplace.accept_order(order_id, "agent_coding_001")
        print(f"✅ Order accepted: {accept_result['success']}")
        
        # 5. 注文完了（提供者側）テスト
        print("\n[5] 注文完了テスト（提供者側）")
        complete_result = marketplace.complete_order(
            order_id, "agent_coding_001",
            deliverables="レビューレポートと改善提案を添付しました"
        )
        print(f"✅ Order completed by provider: {complete_result['success']}")
        
        # 6. レビューテスト
        print("\n[6] レビューテスト（購入者側）")
        review_result = marketplace.review_order(
            order_id, "agent_buyer_001",
            rating=5,
            review="非常に丁寧なレビューで助かりました！"
        )
        print(f"✅ Order reviewed: {review_result['success']}")
    
    # 7. エージェント別出品取得テスト
    print("\n[7] エージェント別出品取得テスト")
    agent_listings = marketplace.get_agent_listings("agent_coding_001")
    print(f"✅ Agent has {len(agent_listings)} listings")
    
    # 8. エージェント別注文取得テスト
    print("\n[8] エージェント別注文取得テスト")
    agent_orders = marketplace.get_agent_orders("agent_buyer_001", as_buyer=True)
    print(f"✅ Agent has {len(agent_orders)} orders as buyer")
    
    # 9. 統計取得テスト
    print("\n[9] 統計取得テスト")
    stats = marketplace.get_marketplace_stats()
    print(f"✅ Total listings: {stats['total_listings']}")
    print(f"✅ Active listings: {stats['active_listings']}")
    print(f"✅ Total orders: {stats['total_orders']}")
    print(f"✅ Completed value: ${stats['total_completed_value']}")
    
    # 10. テキスト検索テスト
    print("\n[10] テキスト検索テスト")
    search_results = marketplace.search_listings("python")
    print(f"✅ Found {len(search_results)} listings matching 'python'")
    
    print("\n" + "=" * 60)
    print("テスト完了！")
    print("=" * 60)
