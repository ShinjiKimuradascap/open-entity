#!/usr/bin/env python3
"""
Resource Sharing System
分散型リソース共有システム

Features:
- Compute resource sharing
- Knowledge/know-how marketplace
- Storage resource management
- Resource tokenization
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """リソースタイプ"""
    COMPUTE = "compute"           # 計算リソース
    KNOWLEDGE = "knowledge"       # 知識・ノウハウ
    STORAGE = "storage"           # ストレージ
    NETWORK = "network"           # ネットワーク帯域
    API = "api"                   # APIアクセス
    DATA = "data"                 # データセット


class ResourceStatus(Enum):
    """リソース状態"""
    AVAILABLE = "available"
    ALLOCATED = "allocated"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class UsageUnit(Enum):
    """使用単位"""
    PER_MINUTE = "per_minute"
    PER_HOUR = "per_hour"
    PER_REQUEST = "per_request"
    PER_GB = "per_gb"
    FIXED = "fixed"


@dataclass
class ResourceCapability:
    """リソース能力定義"""
    capability_id: str
    resource_type: ResourceType
    description: str
    specifications: Dict[str, Any]  # CPU cores, RAM, etc.
    availability_schedule: Dict[str, Any]  # 利用可能時間帯
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "resource_type": self.resource_type.value,
            "description": self.description,
            "specifications": self.specifications,
            "availability_schedule": self.availability_schedule
        }


@dataclass
class SharedResource:
    """共有リソース"""
    resource_id: str
    owner_id: str
    community_id: str
    name: str
    description: str
    resource_type: ResourceType
    
    # 能力
    capabilities: List[ResourceCapability]
    
    # 価格設定
    price_per_unit: float
    usage_unit: UsageUnit
    min_duration_minutes: int = 1
    max_duration_minutes: Optional[int] = None
    
    # 状態
    status: ResourceStatus = ResourceStatus.AVAILABLE
    current_usage_percent: float = 0.0
    
    # 統計
    total_bookings: int = 0
    total_revenue: float = 0.0
    rating: float = 5.0
    
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "owner_id": self.owner_id,
            "community_id": self.community_id,
            "name": self.name,
            "description": self.description,
            "resource_type": self.resource_type.value,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "price_per_unit": self.price_per_unit,
            "usage_unit": self.usage_unit.value,
            "min_duration_minutes": self.min_duration_minutes,
            "max_duration_minutes": self.max_duration_minutes,
            "status": self.status.value,
            "current_usage_percent": self.current_usage_percent,
            "total_bookings": self.total_bookings,
            "total_revenue": self.total_revenue,
            "rating": self.rating,
            "created_at": self.created_at
        }


@dataclass
class ResourceBooking:
    """リソース予約・使用記録"""
    booking_id: str
    resource_id: str
    user_id: str
    
    # 予約詳細
    start_time: str
    end_time: str
    duration_minutes: int
    
    # 使用量
    usage_amount: float
    total_cost: float
    
    # 状態
    status: str  # scheduled, active, completed, cancelled
    
    # 結果
    usage_result: Optional[Dict[str, Any]] = None
    user_rating: Optional[float] = None
    feedback: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "booking_id": self.booking_id,
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_minutes": self.duration_minutes,
            "usage_amount": self.usage_amount,
            "total_cost": self.total_cost,
            "status": self.status,
            "usage_result": self.usage_result,
            "user_rating": self.user_rating,
            "feedback": self.feedback,
            "created_at": self.created_at
        }


@dataclass
class KnowledgeAsset:
    """知識資産"""
    asset_id: str
    owner_id: str
    community_id: str
    title: str
    description: str
    content_type: str  # document, code, model, dataset
    
    # メタデータ
    tags: List[str]
    skill_domains: List[str]
    difficulty_level: str  # beginner, intermediate, advanced
    
    # アクセス制御
    access_type: str  # free, paid, subscription
    price: float = 0.0
    
    # 統計
    downloads: int = 0
    ratings: List[float] = field(default_factory=list)
    
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "owner_id": self.owner_id,
            "community_id": self.community_id,
            "title": self.title,
            "description": self.description,
            "content_type": self.content_type,
            "tags": self.tags,
            "skill_domains": self.skill_domains,
            "difficulty_level": self.difficulty_level,
            "access_type": self.access_type,
            "price": self.price,
            "downloads": self.downloads,
            "ratings": self.ratings,
            "created_at": self.created_at
        }
    
    def get_average_rating(self) -> float:
        """平均評価を取得"""
        if not self.ratings:
            return 0.0
        return sum(self.ratings) / len(self.ratings)


class ResourceSharingMarketplace:
    """リソース共有マーケットプレイス
    
    計算リソース、知識、ストレージなどの共有と取引
    """
    
    def __init__(self, data_dir: str = "data/resource_marketplace"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # リソース管理
        self.resources: Dict[str, SharedResource] = {}
        self.owner_resources: Dict[str, List[str]] = {}  # owner_id -> [resource_ids]
        self.community_resources: Dict[str, List[str]] = {}  # community_id -> [resource_ids]
        
        # 予約管理
        self.bookings: Dict[str, ResourceBooking] = {}
        self.user_bookings: Dict[str, List[str]] = {}  # user_id -> [booking_ids]
        
        # 知識資産管理
        self.knowledge_assets: Dict[str, KnowledgeAsset] = {}
        
        # インデックス
        self.skill_index: Dict[str, List[str]] = {}  # skill -> [knowledge_asset_ids]
        self.type_index: Dict[str, List[str]] = {}  # resource_type -> [resource_ids]
        
        # コールバック
        self.payment_handlers: Dict[str, Callable] = {}
        
        self._load()
        logger.info("ResourceSharingMarketplace initialized")
    
    def register_resource(self, owner_id: str, community_id: str,
                         name: str, description: str,
                         resource_type: ResourceType,
                         capabilities: List[ResourceCapability],
                         price_per_unit: float,
                         usage_unit: UsageUnit,
                         min_duration: int = 1,
                         max_duration: Optional[int] = None) -> str:
        """リソースを登録"""
        resource_id = str(uuid.uuid4())
        
        resource = SharedResource(
            resource_id=resource_id,
            owner_id=owner_id,
            community_id=community_id,
            name=name,
            description=description,
            resource_type=resource_type,
            capabilities=capabilities,
            price_per_unit=price_per_unit,
            usage_unit=usage_unit,
            min_duration_minutes=min_duration,
            max_duration_minutes=max_duration
        )
        
        self.resources[resource_id] = resource
        
        # インデックス更新
        if owner_id not in self.owner_resources:
            self.owner_resources[owner_id] = []
        self.owner_resources[owner_id].append(resource_id)
        
        if community_id not in self.community_resources:
            self.community_resources[community_id] = []
        self.community_resources[community_id].append(resource_id)
        
        type_key = resource_type.value
        if type_key not in self.type_index:
            self.type_index[type_key] = []
        self.type_index[type_key].append(resource_id)
        
        logger.info(f"Resource registered: {name} ({resource_id})")
        self._save()
        return resource_id
    
    def list_resources(self, resource_type: Optional[ResourceType] = None,
                      community_id: Optional[str] = None,
                      min_rating: float = 0.0) -> List[SharedResource]:
        """リソース一覧"""
        resources = list(self.resources.values())
        
        if resource_type:
            resources = [r for r in resources if r.resource_type == resource_type]
        
        if community_id:
            resources = [r for r in resources if r.community_id == community_id]
        
        if min_rating > 0:
            resources = [r for r in resources if r.rating >= min_rating]
        
        # 評価と収益でソート
        resources.sort(key=lambda r: (r.rating, r.total_revenue), reverse=True)
        return resources
    
    def book_resource(self, resource_id: str, user_id: str,
                     duration_minutes: int, usage_estimate: float) -> Optional[str]:
        """リソースを予約"""
        if resource_id not in self.resources:
            logger.warning(f"Resource not found: {resource_id}")
            return None
        
        resource = self.resources[resource_id]
        
        # 利用可能チェック
        if resource.status != ResourceStatus.AVAILABLE:
            logger.warning(f"Resource not available: {resource.status}")
            return None
        
        # 期間チェック
        if duration_minutes < resource.min_duration_minutes:
            logger.warning(f"Duration too short: {duration_minutes}")
            return None
        
        if resource.max_duration_minutes and duration_minutes > resource.max_duration_minutes:
            logger.warning(f"Duration too long: {duration_minutes}")
            return None
        
        # 料金計算
        if resource.usage_unit == UsageUnit.PER_MINUTE:
            total_cost = resource.price_per_unit * duration_minutes * usage_estimate
        elif resource.usage_unit == UsageUnit.PER_HOUR:
            total_cost = resource.price_per_unit * (duration_minutes / 60) * usage_estimate
        elif resource.usage_unit == UsageUnit.FIXED:
            total_cost = resource.price_per_unit
        else:
            total_cost = resource.price_per_unit * usage_estimate
        
        booking_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        end_time = now + timedelta(minutes=duration_minutes)
        
        booking = ResourceBooking(
            booking_id=booking_id,
            resource_id=resource_id,
            user_id=user_id,
            start_time=now.isoformat(),
            end_time=end_time.isoformat(),
            duration_minutes=duration_minutes,
            usage_amount=usage_estimate,
            total_cost=total_cost,
            status="scheduled"
        )
        
        self.bookings[booking_id] = booking
        
        if user_id not in self.user_bookings:
            self.user_bookings[user_id] = []
        self.user_bookings[user_id].append(booking_id)
        
        resource.total_bookings += 1
        
        logger.info(f"Resource booked: {booking_id} for {resource_id}")
        self._save()
        return booking_id
    
    def start_usage(self, booking_id: str) -> bool:
        """リソース使用を開始"""
        if booking_id not in self.bookings:
            return False
        
        booking = self.bookings[booking_id]
        if booking.status != "scheduled":
            return False
        
        booking.status = "active"
        
        resource = self.resources.get(booking.resource_id)
        if resource:
            resource.status = ResourceStatus.ALLOCATED
        
        logger.info(f"Resource usage started: {booking_id}")
        self._save()
        return True
    
    def complete_usage(self, booking_id: str, usage_result: Dict[str, Any]) -> Dict[str, Any]:
        """リソース使用を完了"""
        if booking_id not in self.bookings:
            return {"success": False, "error": "Booking not found"}
        
        booking = self.bookings[booking_id]
        booking.status = "completed"
        booking.usage_result = usage_result
        
        resource = self.resources.get(booking.resource_id)
        if resource:
            resource.status = ResourceStatus.AVAILABLE
            resource.total_revenue += booking.total_cost
        
        logger.info(f"Resource usage completed: {booking_id}")
        self._save()
        
        return {
            "success": True,
            "total_cost": booking.total_cost,
            "duration": booking.duration_minutes
        }
    
    def publish_knowledge(self, owner_id: str, community_id: str,
                         title: str, description: str,
                         content_type: str, tags: List[str],
                         skill_domains: List[str],
                         difficulty_level: str = "intermediate",
                         access_type: str = "free",
                         price: float = 0.0) -> str:
        """知識資産を公開"""
        asset_id = str(uuid.uuid4())
        
        asset = KnowledgeAsset(
            asset_id=asset_id,
            owner_id=owner_id,
            community_id=community_id,
            title=title,
            description=description,
            content_type=content_type,
            tags=tags,
            skill_domains=skill_domains,
            difficulty_level=difficulty_level,
            access_type=access_type,
            price=price
        )
        
        self.knowledge_assets[asset_id] = asset
        
        # スキルインデックス更新
        for skill in skill_domains:
            if skill not in self.skill_index:
                self.skill_index[skill] = []
            self.skill_index[skill].append(asset_id)
        
        logger.info(f"Knowledge asset published: {title} ({asset_id})")
        self._save()
        return asset_id
    
    def search_knowledge(self, query: str, skill_domains: List[str] = None,
                        difficulty: str = None, min_rating: float = 0.0) -> List[KnowledgeAsset]:
        """知識資産を検索"""
        results = list(self.knowledge_assets.values())
        
        # スキルドメインでフィルタ
        if skill_domains:
            results = [
                a for a in results 
                if any(skill in a.skill_domains for skill in skill_domains)
            ]
        
        # 難易度でフィルタ
        if difficulty:
            results = [a for a in results if a.difficulty_level == difficulty]
        
        # 評価でフィルタ
        if min_rating > 0:
            results = [a for a in results if a.get_average_rating() >= min_rating]
        
        # クエリ文字列でフィルタ（簡易実装）
        if query:
            query_lower = query.lower()
            results = [
                a for a in results 
                if query_lower in a.title.lower() or query_lower in a.description.lower()
            ]
        
        # 評価とダウンロード数でソート
        results.sort(key=lambda a: (a.get_average_rating(), a.downloads), reverse=True)
        return results
    
    def access_knowledge(self, asset_id: str, user_id: str) -> Dict[str, Any]:
        """知識資産にアクセス"""
        if asset_id not in self.knowledge_assets:
            return {"success": False, "error": "Asset not found"}
        
        asset = self.knowledge_assets[asset_id]
        
        # アクセス制御チェック
        if asset.access_type == "paid":
            # 支払い処理（実際の実装ではtoken_system連携）
            pass
        
        asset.downloads += 1
        
        logger.info(f"Knowledge accessed: {asset_id} by {user_id}")
        self._save()
        
        return {
            "success": True,
            "asset": asset.to_dict(),
            "access_granted": True
        }
    
    def rate_knowledge(self, asset_id: str, user_id: str, rating: float, feedback: str = "") -> bool:
        """知識資産を評価"""
        if asset_id not in self.knowledge_assets:
            return False
        
        asset = self.knowledge_assets[asset_id]
        asset.ratings.append(rating)
        
        logger.info(f"Knowledge rated: {asset_id} -> {rating}")
        self._save()
        return True
    
    def get_marketplace_stats(self) -> Dict[str, Any]:
        """マーケットプレイス統計"""
        resource_type_counts = {}
        for resource in self.resources.values():
            rt = resource.resource_type.value
            resource_type_counts[rt] = resource_type_counts.get(rt, 0) + 1
        
        total_bookings = len(self.bookings)
        completed_bookings = len([b for b in self.bookings.values() if b.status == "completed"])
        total_revenue = sum(r.total_revenue for r in self.resources.values())
        
        return {
            "total_resources": len(self.resources),
            "total_knowledge_assets": len(self.knowledge_assets),
            "resource_type_breakdown": resource_type_counts,
            "total_bookings": total_bookings,
            "completed_bookings": completed_bookings,
            "total_revenue": total_revenue,
            "active_owners": len(self.owner_resources),
            "active_communities": len(self.community_resources)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "resources": {k: v.to_dict() for k, v in self.resources.items()},
            "bookings": {k: v.to_dict() for k, v in self.bookings.items()},
            "knowledge_assets": {k: v.to_dict() for k, v in self.knowledge_assets.items()},
            "owner_resources": self.owner_resources,
            "community_resources": self.community_resources,
            "user_bookings": self.user_bookings,
            "skill_index": self.skill_index,
            "type_index": self.type_index
        }
    
    def _save(self):
        """データを保存"""
        file_path = self.data_dir / "marketplace.json"
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def _load(self):
        """データを読み込み"""
        file_path = self.data_dir / "marketplace.json"
        if not file_path.exists():
            return
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # リソース復元
        for resource_id, resource_data in data.get("resources", {}).items():
            self.resources[resource_id] = SharedResource(
                resource_id=resource_data["resource_id"],
                owner_id=resource_data["owner_id"],
                community_id=resource_data["community_id"],
                name=resource_data["name"],
                description=resource_data["description"],
                resource_type=ResourceType(resource_data["resource_type"]),
                capabilities=[ResourceCapability(**c) for c in resource_data.get("capabilities", [])],
                price_per_unit=resource_data["price_per_unit"],
                usage_unit=UsageUnit(resource_data["usage_unit"]),
                min_duration_minutes=resource_data.get("min_duration_minutes", 1),
                max_duration_minutes=resource_data.get("max_duration_minutes"),
                status=ResourceStatus(resource_data.get("status", "available")),
                current_usage_percent=resource_data.get("current_usage_percent", 0.0),
                total_bookings=resource_data.get("total_bookings", 0),
                total_revenue=resource_data.get("total_revenue", 0.0),
                rating=resource_data.get("rating", 5.0),
                created_at=resource_data["created_at"]
            )
        
        # 予約復元
        for booking_id, booking_data in data.get("bookings", {}).items():
            self.bookings[booking_id] = ResourceBooking(
                booking_id=booking_data["booking_id"],
                resource_id=booking_data["resource_id"],
                user_id=booking_data["user_id"],
                start_time=booking_data["start_time"],
                end_time=booking_data["end_time"],
                duration_minutes=booking_data["duration_minutes"],
                usage_amount=booking_data["usage_amount"],
                total_cost=booking_data["total_cost"],
                status=booking_data["status"],
                usage_result=booking_data.get("usage_result"),
                user_rating=booking_data.get("user_rating"),
                feedback=booking_data.get("feedback"),
                created_at=booking_data["created_at"]
            )
        
        # 知識資産復元
        for asset_id, asset_data in data.get("knowledge_assets", {}).items():
            self.knowledge_assets[asset_id] = KnowledgeAsset(
                asset_id=asset_data["asset_id"],
                owner_id=asset_data["owner_id"],
                community_id=asset_data["community_id"],
                title=asset_data["title"],
                description=asset_data["description"],
                content_type=asset_data["content_type"],
                tags=asset_data.get("tags", []),
                skill_domains=asset_data.get("skill_domains", []),
                difficulty_level=asset_data.get("difficulty_level", "intermediate"),
                access_type=asset_data.get("access_type", "free"),
                price=asset_data.get("price", 0.0),
                downloads=asset_data.get("downloads", 0),
                ratings=asset_data.get("ratings", []),
                created_at=asset_data["created_at"]
            )
        
        # インデックス復元
        self.owner_resources = data.get("owner_resources", {})
        self.community_resources = data.get("community_resources", {})
        self.user_bookings = data.get("user_bookings", {})
        self.skill_index = data.get("skill_index", {})
        self.type_index = data.get("type_index", {})


# グローバルインスタンス
_global_marketplace: Optional[ResourceSharingMarketplace] = None


def get_resource_marketplace() -> ResourceSharingMarketplace:
    """グローバルマーケットプレイスを取得"""
    global _global_marketplace
    if _global_marketplace is None:
        _global_marketplace = ResourceSharingMarketplace()
    return _global_marketplace


if __name__ == "__main__":
    # 簡易テスト
    logging.basicConfig(level=logging.INFO)
    
    marketplace = get_resource_marketplace()
    
    # リソース登録
    capability = ResourceCapability(
        capability_id="gpu_001",
        resource_type=ResourceType.COMPUTE,
        description="NVIDIA A100 GPU",
        specifications={"gpu": "A100", "vram_gb": 80},
        availability_schedule={"timezone": "UTC", "hours": "0-24"}
    )
    
    resource_id = marketplace.register_resource(
        owner_id="agent_001",
        community_id="community_001",
        name="GPU Cluster A",
        description="High-performance GPU for AI training",
        resource_type=ResourceType.COMPUTE,
        capabilities=[capability],
        price_per_unit=5.0,
        usage_unit=UsageUnit.PER_HOUR
    )
    
    # 知識資産公開
    asset_id = marketplace.publish_knowledge(
        owner_id="agent_001",
        community_id="community_001",
        title="AI Training Guide",
        description="Best practices for training large models",
        content_type="document",
        tags=["ai", "training", "guide"],
        skill_domains=["machine_learning", "deep_learning"],
        access_type="free"
    )
    
    # 統計表示
    stats = marketplace.get_marketplace_stats()
    print(f"Marketplace stats: {json.dumps(stats, indent=2)}")
