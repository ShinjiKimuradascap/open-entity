#!/usr/bin/env python3
"""
AI Service Registry

AIエージェントが提供するサービスを登録・管理するレジストリ。
JSONファイルによる永続化とインメモリキャッシュを実装。

Features:
- Service registration and discovery
- Capability-based search
- Tag-based filtering
- Thread-safe operations (asyncio.Lock)
- JSON file persistence
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from uuid import UUID, uuid4

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """サービスの状態"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


@dataclass
class PricingModel:
    """サービス価格モデル"""
    model_type: str  # "free", "per_call", "subscription", "hybrid"
    base_price: float = 0.0
    currency: str = "TOKEN"
    per_call_price: Optional[float] = None
    subscription_tiers: Optional[List[Dict[str, Any]]] = None
    custom_pricing: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_type": self.model_type,
            "base_price": self.base_price,
            "currency": self.currency,
            "per_call_price": self.per_call_price,
            "subscription_tiers": self.subscription_tiers,
            "custom_pricing": self.custom_pricing
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PricingModel":
        return cls(
            model_type=data.get("model_type", "free"),
            base_price=data.get("base_price", 0.0),
            currency=data.get("currency", "TOKEN"),
            per_call_price=data.get("per_call_price"),
            subscription_tiers=data.get("subscription_tiers"),
            custom_pricing=data.get("custom_pricing")
        )


@dataclass
class Service:
    """
    AIサービスモデル
    
    AIエージェントが提供するサービスのメタデータ。
    """
    # Identification
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    
    # Provider info
    provider_id: str = ""  # AIエージェントID
    
    # Capabilities and tags
    capabilities: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    # Pricing
    pricing: PricingModel = field(default_factory=lambda: PricingModel("free"))
    
    # Version and endpoint
    version: str = "1.0.0"
    endpoint_url: str = ""
    
    # Status
    status: ServiceStatus = ServiceStatus.ACTIVE
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換（永続化用）"""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "provider_id": self.provider_id,
            "capabilities": self.capabilities,
            "tags": self.tags,
            "pricing": self.pricing.to_dict(),
            "version": self.version,
            "endpoint_url": self.endpoint_url,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Service":
        """辞書からServiceを復元"""
        return cls(
            id=UUID(data["id"]) if "id" in data else uuid4(),
            name=data.get("name", ""),
            description=data.get("description", ""),
            provider_id=data.get("provider_id", ""),
            capabilities=data.get("capabilities", []),
            tags=data.get("tags", []),
            pricing=PricingModel.from_dict(data.get("pricing", {"model_type": "free"})),
            version=data.get("version", "1.0.0"),
            endpoint_url=data.get("endpoint_url", ""),
            status=ServiceStatus(data.get("status", "active")),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.utcnow()
        )
    
    def update_timestamp(self) -> None:
        """更新時刻を更新"""
        self.updated_at = datetime.utcnow()


class ServiceRegistry:
    """
    AIサービスレジストリ
    
    スレッドセーフなサービス管理を実装。
    JSONファイル永続化とインメモリキャッシュを提供。
    
    Usage:
        registry = ServiceRegistry()
        service_id = await registry.register_service(service)
        service = await registry.get_service(service_id)
    """
    
    def __init__(
        self,
        data_dir: Optional[str] = None,
        auto_save: bool = True,
        auto_save_interval: int = 30
    ):
        """
        初期化
        
        Args:
            data_dir: 永続化データの保存先（デフォルト: data/services/）
            auto_save: 自動保存を有効にするか
            auto_save_interval: 自動保存間隔（秒）
        """
        self._data_dir = Path(data_dir) if data_dir else Path("data/services")
        self._data_file = self._data_dir / "services.json"
        self._auto_save = auto_save
        self._auto_save_interval = auto_save_interval
        
        # インメモリキャッシュ
        self._services: Dict[str, Service] = {}  # str(UUID) -> Service
        
        # インデックス（高速検索用）
        self._capability_index: Dict[str, set] = {}  # capability -> set(service_ids)
        self._tag_index: Dict[str, set] = {}  # tag -> set(service_ids)
        self._provider_index: Dict[str, set] = {}  # provider_id -> set(service_ids)
        
        # スレッドセーフ用ロック
        self._lock = asyncio.Lock()
        
        # 自動保存タスク
        self._auto_save_task: Optional[asyncio.Task] = None
        self._dirty: bool = False
        
        # 初期化
        self._ensure_data_dir()
        self._load_from_disk()
        
        logger.info(f"ServiceRegistry initialized: {len(self._services)} services loaded")
    
    def _ensure_data_dir(self) -> None:
        """データディレクトリを作成"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_from_disk(self) -> None:
        """JSONファイルからサービスを読み込み"""
        if not self._data_file.exists():
            logger.info("No existing services file found")
            return
        
        try:
            with open(self._data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for service_data in data.get("services", []):
                try:
                    service = Service.from_dict(service_data)
                    self._add_to_cache(service)
                except Exception as e:
                    logger.error(f"Failed to load service: {e}")
            
            logger.info(f"Loaded {len(self._services)} services from disk")
        except Exception as e:
            logger.error(f"Failed to load services from disk: {e}")
    
    async def _save_to_disk(self) -> bool:
        """サービスをJSONファイルに保存"""
        async with self._lock:
            try:
                data = {
                    "services": [s.to_dict() for s in self._services.values()],
                    "saved_at": datetime.utcnow().isoformat(),
                    "count": len(self._services)
                }
                
                # 一時ファイルに書き込み後、リネーム（原子性）
                temp_file = self._data_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                temp_file.replace(self._data_file)
                
                self._dirty = False
                logger.debug(f"Saved {len(self._services)} services to disk")
                return True
            except Exception as e:
                logger.error(f"Failed to save services to disk: {e}")
                return False
    
    def _add_to_cache(self, service: Service) -> None:
        """サービスをキャッシュとインデックスに追加"""
        service_id = str(service.id)
        self._services[service_id] = service
        
        # Capability index
        for cap in service.capabilities:
            if cap not in self._capability_index:
                self._capability_index[cap] = set()
            self._capability_index[cap].add(service_id)
        
        # Tag index
        for tag in service.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(service_id)
        
        # Provider index
        if service.provider_id:
            if service.provider_id not in self._provider_index:
                self._provider_index[service.provider_id] = set()
            self._provider_index[service.provider_id].add(service_id)
    
    def _remove_from_cache(self, service_id: str) -> Optional[Service]:
        """サービスをキャッシュとインデックスから削除"""
        service = self._services.pop(service_id, None)
        if not service:
            return None
        
        # Capability index
        for cap in service.capabilities:
            if cap in self._capability_index:
                self._capability_index[cap].discard(service_id)
                if not self._capability_index[cap]:
                    del self._capability_index[cap]
        
        # Tag index
        for tag in service.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(service_id)
                if not self._tag_index[tag]:
                    del self._tag_index[tag]
        
        # Provider index
        if service.provider_id and service.provider_id in self._provider_index:
            self._provider_index[service.provider_id].discard(service_id)
            if not self._provider_index[service.provider_id]:
                del self._provider_index[service.provider_id]
        
        return service
    
    def _update_indexes(self, old_service: Service, new_service: Service) -> None:
        """サービス更新時にインデックスを更新"""
        old_id = str(old_service.id)
        
        # Remove old indexes
        for cap in old_service.capabilities:
            if cap in self._capability_index:
                self._capability_index[cap].discard(old_id)
        
        for tag in old_service.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(old_id)
        
        # Add new indexes
        for cap in new_service.capabilities:
            if cap not in self._capability_index:
                self._capability_index[cap] = set()
            self._capability_index[cap].add(old_id)
        
        for tag in new_service.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(old_id)
    
    async def start(self) -> None:
        """自動保存を開始"""
        if self._auto_save and not self._auto_save_task:
            self._auto_save_task = asyncio.create_task(self._auto_save_loop())
            logger.info("ServiceRegistry auto-save started")
    
    async def stop(self) -> None:
        """自動保存を停止し、最後に保存"""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            try:
                await self._auto_save_task
            except asyncio.CancelledError:
                pass
            self._auto_save_task = None
        
        # ダーティなら保存
        if self._dirty:
            await self._save_to_disk()
        
        logger.info("ServiceRegistry stopped")
    
    async def _auto_save_loop(self) -> None:
        """自動保存ループ"""
        while True:
            try:
                await asyncio.sleep(self._auto_save_interval)
                if self._dirty:
                    await self._save_to_disk()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-save error: {e}")
    
    async def register_service(self, service: Service) -> UUID:
        """
        サービスを登録
        
        Args:
            service: 登録するサービス（id未指定時は自動生成）
        
        Returns:
            登録されたサービスのUUID
        """
        async with self._lock:
            # IDが未設定なら生成
            if not service.id:
                service.id = uuid4()
            
            service.update_timestamp()
            self._add_to_cache(service)
            self._dirty = True
            
            logger.info(f"Registered service: {service.name} ({service.id})")
            return service.id
    
    async def get_service(self, service_id: Union[UUID, str]) -> Optional[Service]:
        """
        サービスを取得
        
        Args:
            service_id: サービスID（UUIDまたは文字列）
        
        Returns:
            Serviceオブジェクト、またはNone
        """
        service_id_str = str(service_id)
        async with self._lock:
            service = self._services.get(service_id_str)
            if service:
                # コピーを返す（外部からの変更を防ぐ）
                return Service.from_dict(service.to_dict())
            return None
    
    async def update_service(
        self,
        service_id: Union[UUID, str],
        updates: Dict[str, Any]
    ) -> bool:
        """
        サービスを更新
        
        Args:
            service_id: 更新するサービスのID
            updates: 更新内容の辞書
        
        Returns:
            更新成功時True
        """
        service_id_str = str(service_id)
        
        async with self._lock:
            if service_id_str not in self._services:
                logger.warning(f"Service not found: {service_id}")
                return False
            
            old_service = self._services[service_id_str]
            
            # 更新内容を適用
            service_data = old_service.to_dict()
            
            # 更新可能なフィールド
            updatable_fields = [
                "name", "description", "capabilities", "tags",
                "pricing", "version", "endpoint_url", "status"
            ]
            
            for field in updatable_fields:
                if field in updates:
                    if field == "pricing":
                        service_data[field] = updates[field].to_dict() if isinstance(updates[field], PricingModel) else updates[field]
                    elif field == "status":
                        service_data[field] = updates[field].value if isinstance(updates[field], ServiceStatus) else updates[field]
                    else:
                        service_data[field] = updates[field]
            
            # 新しいServiceオブジェクトを作成
            new_service = Service.from_dict(service_data)
            new_service.update_timestamp()
            
            # キャッシュとインデックスを更新
            self._services[service_id_str] = new_service
            self._update_indexes(old_service, new_service)
            self._dirty = True
            
            logger.info(f"Updated service: {new_service.name} ({service_id})")
            return True
    
    async def delete_service(self, service_id: Union[UUID, str]) -> bool:
        """
        サービスを削除
        
        Args:
            service_id: 削除するサービスのID
        
        Returns:
            削除成功時True
        """
        service_id_str = str(service_id)
        
        async with self._lock:
            service = self._remove_from_cache(service_id_str)
            if service:
                self._dirty = True
                logger.info(f"Deleted service: {service.name} ({service_id})")
                return True
            
            logger.warning(f"Service not found for deletion: {service_id}")
            return False
    
    async def list_services(
        self,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Service]:
        """
        サービス一覧を取得（フィルタリング対応）
        
        Args:
            filters: フィルタ条件辞書
                - status: ServiceStatus
                - provider_id: str
                - capabilities: List[str]
                - tags: List[str]
        
        Returns:
            条件に一致するServiceのリスト
        """
        filters = filters or {}
        results = []
        
        async with self._lock:
            for service in self._services.values():
                # Status filter
                if "status" in filters:
                    target_status = filters["status"]
                    if isinstance(target_status, str):
                        target_status = ServiceStatus(target_status)
                    if service.status != target_status:
                        continue
                
                # Provider filter
                if "provider_id" in filters:
                    if service.provider_id != filters["provider_id"]:
                        continue
                
                # Capabilities filter (すべて含む)
                if "capabilities" in filters:
                    required_caps = set(filters["capabilities"])
                    if not required_caps.issubset(set(service.capabilities)):
                        continue
                
                # Tags filter (いずれか含む)
                if "tags" in filters:
                    filter_tags = set(filters["tags"])
                    if not filter_tags.intersection(set(service.tags)):
                        continue
                
                results.append(Service.from_dict(service.to_dict()))
        
        return results
    
    async def search_by_capability(self, capability: str) -> List[Service]:
        """
        機能でサービスを検索
        
        Args:
            capability: 検索する機能名
        
        Returns:
            機能を持つServiceのリスト
        """
        async with self._lock:
            service_ids = self._capability_index.get(capability, set())
            results = []
            for sid in service_ids:
                service = self._services.get(sid)
                if service and service.status == ServiceStatus.ACTIVE:
                    results.append(Service.from_dict(service.to_dict()))
            return results
    
    async def search_by_tags(self, tags: List[str]) -> List[Service]:
        """
        タグでサービスを検索（OR検索）
        
        Args:
            tags: 検索するタグのリスト
        
        Returns:
            いずれかのタグを持つServiceのリスト
        """
        async with self._lock:
            matching_ids: set = set()
            for tag in tags:
                matching_ids.update(self._tag_index.get(tag, set()))
            
            results = []
            for sid in matching_ids:
                service = self._services.get(sid)
                if service and service.status == ServiceStatus.ACTIVE:
                    results.append(Service.from_dict(service.to_dict()))
            return results
    
    async def get_provider_services(self, provider_id: str) -> List[Service]:
        """
        プロバイダのサービス一覧を取得
        
        Args:
            provider_id: プロバイダID
        
        Returns:
            プロバイダのServiceリスト
        """
        async with self._lock:
            service_ids = self._provider_index.get(provider_id, set())
            return [
                Service.from_dict(self._services[sid].to_dict())
                for sid in service_ids
                if sid in self._services
            ]
    
    async def get_all_capabilities(self) -> List[str]:
        """登録されている全機能一覧を取得"""
        async with self._lock:
            return list(self._capability_index.keys())
    
    async def get_all_tags(self) -> List[str]:
        """登録されている全タグ一覧を取得"""
        async with self._lock:
            return list(self._tag_index.keys())
    
    async def get_stats(self) -> Dict[str, Any]:
        """レジストリ統計情報を取得"""
        async with self._lock:
            status_counts = {}
            for service in self._services.values():
                status = service.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_services": len(self._services),
                "by_status": status_counts,
                "unique_capabilities": len(self._capability_index),
                "unique_tags": len(self._tag_index),
                "providers": len(self._provider_index),
                "data_file": str(self._data_file),
                "dirty": self._dirty
            }
    
    async def force_save(self) -> bool:
        """強制的にディスクに保存"""
        return await self._save_to_disk()
    
    async def reload(self) -> bool:
        """ディスクから再読み込み"""
        async with self._lock:
            self._services.clear()
            self._capability_index.clear()
            self._tag_index.clear()
            self._provider_index.clear()
            self._load_from_disk()
            return True


# グローバルレジストリインスタンス
_global_registry: Optional[ServiceRegistry] = None


async def get_global_registry() -> ServiceRegistry:
    """グローバルレジストリインスタンスを取得"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ServiceRegistry()
        await _global_registry.start()
    return _global_registry


def reset_global_registry() -> None:
    """グローバルレジストリをリセット（テスト用）"""
    global _global_registry
    _global_registry = None


if __name__ == "__main__":
    # 簡易テスト
    async def test():
        registry = ServiceRegistry()
        await registry.start()
        
        # サービス登録
        service = Service(
            name="Code Review Service",
            description="AI-powered code review",
            provider_id="agent-code-reviewer-001",
            capabilities=["code_review", "analysis"],
            tags=["development", "quality"],
            pricing=PricingModel("per_call", per_call_price=1.0),
            endpoint_url="http://localhost:8001/review"
        )
        
        service_id = await registry.register_service(service)
        print(f"Registered: {service_id}")
        
        # 取得
        retrieved = await registry.get_service(service_id)
        print(f"Retrieved: {retrieved.name}")
        
        # 検索
        results = await registry.search_by_capability("code_review")
        print(f"Found {len(results)} services with 'code_review' capability")
        
        # 統計
        stats = await registry.get_stats()
        print(f"Stats: {stats}")
        
        await registry.stop()
    
    asyncio.run(test())
