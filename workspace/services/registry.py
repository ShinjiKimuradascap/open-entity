#!/usr/bin/env python3
"""Service Registry - AI service discovery with JSON persistence

AIエージェントのサービス登録・管理を行うレジストリ。
JSONファイルによる永続化とインメモリキャッシュを実装。

Features:
- Service registration and discovery
- Heartbeat tracking
- Capability-based search
- JSON file persistence
- Thread-safe operations (asyncio.Lock)
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ServiceInfo:
    """サービス情報"""
    entity_id: str
    entity_name: str
    endpoint: str
    capabilities: List[str]
    registered_at: datetime
    last_heartbeat: datetime
    
    def is_alive(self, timeout_sec: int = 60) -> bool:
        """サービスが生存しているかチェック"""
        delta = datetime.now(timezone.utc) - self.last_heartbeat
        return delta.seconds < timeout_sec
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換（永続化用）"""
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceInfo":
        """辞書からServiceInfoを復元"""
        return cls(
            entity_id=data["entity_id"],
            entity_name=data["entity_name"],
            endpoint=data["endpoint"],
            capabilities=data.get("capabilities", []),
            registered_at=datetime.fromisoformat(data["registered_at"]),
            last_heartbeat=datetime.fromisoformat(data["last_heartbeat"])
        )


class ServiceRegistry:
    """Central service registry for AI entities with JSON persistence
    
    JSONファイル永続化とインメモリキャッシュを提供。
    起動時に自動読み込み、変更時に自動保存。
    
    Usage:
        registry = ServiceRegistry()
        registry.register("agent-1", "Coder Agent", "http://localhost:8001", ["code"])
        services = registry.list_all()
    """
    
    def __init__(
        self,
        data_dir: Optional[str] = None,
        auto_save: bool = True
    ):
        """
        初期化
        
        Args:
            data_dir: 永続化データの保存先（デフォルト: data/agents/）
            auto_save: 自動保存を有効にするか
        """
        self._data_dir = Path(data_dir) if data_dir else Path("data/agents")
        self._data_file = self._data_dir / "registry.json"
        self._auto_save = auto_save
        
        # インメモリキャッシュ
        self._services: Dict[str, ServiceInfo] = {}
        
        # スレッドセーフ用ロック
        self._lock = asyncio.Lock()
        
        # 初期化
        self._ensure_data_dir()
        self._load_from_disk()
        
        logger.info(f"ServiceRegistry initialized: {len(self._services)} agents loaded")
    
    def _ensure_data_dir(self) -> None:
        """データディレクトリを作成"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_from_disk(self) -> None:
        """JSONファイルからサービスを読み込み"""
        if not self._data_file.exists():
            logger.info("No existing registry file found, starting fresh")
            return
        
        try:
            with open(self._data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for service_data in data.get("services", []):
                try:
                    service = ServiceInfo.from_dict(service_data)
                    self._services[service.entity_id] = service
                except Exception as e:
                    logger.error(f"Failed to load service: {e}")
            
            logger.info(f"Loaded {len(self._services)} agents from disk")
        except Exception as e:
            logger.error(f"Failed to load registry from disk: {e}")
    
    async def _save_to_disk(self) -> bool:
        """サービスをJSONファイルに保存"""
        async with self._lock:
            try:
                data = {
                    "services": [s.to_dict() for s in self._services.values()],
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(self._services)
                }
                
                # 一時ファイルに書き込み後、リネーム（原子性）
                temp_file = self._data_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                temp_file.replace(self._data_file)
                
                logger.debug(f"Saved {len(self._services)} agents to disk")
                return True
            except Exception as e:
                logger.error(f"Failed to save registry to disk: {e}")
                return False
    
    def _save_to_disk_sync(self) -> bool:
        """同期的に保存（非同期コンテキスト外から呼び出す用）"""
        try:
            data = {
                "services": [s.to_dict() for s in self._services.values()],
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "count": len(self._services)
            }
            
            # 一時ファイルに書き込み後、リネーム（原子性）
            temp_file = self._data_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self._data_file)
            
            logger.debug(f"Saved {len(self._services)} agents to disk")
            return True
        except Exception as e:
            logger.error(f"Failed to save registry to disk: {e}")
            return False
    
    def register(
        self,
        entity_id: str,
        name: str,
        endpoint: str,
        capabilities: List[str]
    ) -> bool:
        """
        サービスを登録
        
        Args:
            entity_id: エージェントID
            name: エージェント名
            endpoint: エンドポイントURL
            capabilities: 提供できる機能のリスト
        
        Returns:
            登録成功時True
        """
        now = datetime.now(timezone.utc)
        self._services[entity_id] = ServiceInfo(
            entity_id=entity_id,
            entity_name=name,
            endpoint=endpoint,
            capabilities=capabilities,
            registered_at=now,
            last_heartbeat=now
        )
        
        # 自動保存
        if self._auto_save:
            self._save_to_disk_sync()
        
        logger.info(f"Registered agent: {name} ({entity_id})")
        return True
    
    async def register_async(
        self,
        entity_id: str,
        name: str,
        endpoint: str,
        capabilities: List[str]
    ) -> bool:
        """
        サービスを登録（非同期版）
        
        Args:
            entity_id: エージェントID
            name: エージェント名
            endpoint: エンドポイントURL
            capabilities: 提供できる機能のリスト
        
        Returns:
            登録成功時True
        """
        now = datetime.now(timezone.utc)
        async with self._lock:
            self._services[entity_id] = ServiceInfo(
                entity_id=entity_id,
                entity_name=name,
                endpoint=endpoint,
                capabilities=capabilities,
                registered_at=now,
                last_heartbeat=now
            )
        
        # 自動保存
        if self._auto_save:
            await self._save_to_disk()
        
        logger.info(f"Registered agent: {name} ({entity_id})")
        return True
    
    def unregister(self, entity_id: str) -> bool:
        """
        サービスを削除
        
        Args:
            entity_id: 削除するエージェントのID
        
        Returns:
            削除成功時True
        """
        if entity_id in self._services:
            service = self._services.pop(entity_id)
            
            # 自動保存
            if self._auto_save:
                self._save_to_disk_sync()
            
            logger.info(f"Unregistered agent: {service.entity_name} ({entity_id})")
            return True
        
        logger.warning(f"Agent not found for unregistration: {entity_id}")
        return False
    
    async def unregister_async(self, entity_id: str) -> bool:
        """
        サービスを削除（非同期版）
        
        Args:
            entity_id: 削除するエージェントのID
        
        Returns:
            削除成功時True
        """
        async with self._lock:
            if entity_id in self._services:
                service = self._services.pop(entity_id)
                
                # 自動保存
                if self._auto_save:
                    await self._save_to_disk()
                
                logger.info(f"Unregistered agent: {service.entity_name} ({entity_id})")
                return True
        
        logger.warning(f"Agent not found for unregistration: {entity_id}")
        return False
    
    def heartbeat(self, entity_id: str) -> bool:
        """
        ハートビートを更新
        
        Args:
            entity_id: エージェントID
        
        Returns:
            更新成功時True
        """
        if entity_id in self._services:
            self._services[entity_id].last_heartbeat = datetime.now(timezone.utc)
            # ハートビートは頻繁なので保存しない（起動時に再登録される）
            return True
        return False
    
    async def heartbeat_async(self, entity_id: str) -> bool:
        """
        ハートビートを更新（非同期版）
        
        Args:
            entity_id: エージェントID
        
        Returns:
            更新成功時True
        """
        async with self._lock:
            if entity_id in self._services:
                self._services[entity_id].last_heartbeat = datetime.now(timezone.utc)
                return True
        return False
    
    def find_by_capability(self, capability: str) -> List[ServiceInfo]:
        """
        機能でサービスを検索
        
        Args:
            capability: 検索する機能名
        
        Returns:
            機能を持つ生存中のServiceInfoリスト
        """
        return [
            s for s in self._services.values()
            if capability in s.capabilities and s.is_alive()
        ]
    
    def find_by_id(self, entity_id: str) -> Optional[ServiceInfo]:
        """
        IDでサービスを検索
        
        Args:
            entity_id: エージェントID
        
        Returns:
            ServiceInfo、またはNone
        """
        service = self._services.get(entity_id)
        if service:
            # コピーを返す（外部からの変更を防ぐ）
            return ServiceInfo.from_dict(service.to_dict())
        return None
    
    def list_all(self) -> List[ServiceInfo]:
        """
        全登録サービスを取得
        
        Returns:
            全ServiceInfoのリスト
        """
        return list(self._services.values())
    
    def list_alive(self, timeout_sec: int = 60) -> List[ServiceInfo]:
        """
        生存中のサービスのみを取得
        
        Args:
            timeout_sec: 生存判定のタイムアウト秒数
        
        Returns:
            生存中のServiceInfoリスト
        """
        return [s for s in self._services.values() if s.is_alive(timeout_sec)]
    
    def cleanup_stale(self, timeout_sec: int = 120) -> int:
        """
        古いサービスをクリーンアップ
        
        Args:
            timeout_sec: 生存判定のタイムアウト秒数
        
        Returns:
            削除されたサービス数
        """
        stale = [
            eid for eid, s in self._services.items()
            if not s.is_alive(timeout_sec)
        ]
        for eid in stale:
            del self._services[eid]
        
        # 削除があった場合は保存
        if stale and self._auto_save:
            self._save_to_disk_sync()
        
        if stale:
            logger.info(f"Cleaned up {len(stale)} stale agents")
        return len(stale)
    
    async def force_save(self) -> bool:
        """強制的にディスクに保存"""
        return await self._save_to_disk()
    
    def force_save_sync(self) -> bool:
        """強制的にディスクに保存（同期版）"""
        return self._save_to_disk_sync()
    
    async def reload(self) -> bool:
        """ディスクから再読み込み"""
        async with self._lock:
            self._services.clear()
            self._load_from_disk()
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """レジストリ統計情報を取得"""
        alive_count = len(self.list_alive())
        total_count = len(self._services)
        
        return {
            "total_agents": total_count,
            "alive_agents": alive_count,
            "stale_agents": total_count - alive_count,
            "data_file": str(self._data_file),
            "data_file_exists": self._data_file.exists()
        }


# グローバルレジストリインスタンス
_global_registry: Optional[ServiceRegistry] = None


def get_registry() -> ServiceRegistry:
    """グローバルレジストリインスタンスを取得"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ServiceRegistry()
    return _global_registry


def reset_global_registry() -> None:
    """グローバルレジストリをリセット（テスト用）"""
    global _global_registry
    _global_registry = None


if __name__ == "__main__":
    # 簡易テスト
    async def test():
        registry = ServiceRegistry()
        
        # サービス登録
        registry.register(
            entity_id="agent-1",
            name="Coder Agent",
            endpoint="http://localhost:8001",
            capabilities=["code", "review"]
        )
        print(f"Registered: {len(registry.list_all())} agents")
        
        # 取得
        service = registry.find_by_id("agent-1")
        if service:
            print(f"Retrieved: {service.entity_name}")
        
        # 検索
        results = registry.find_by_capability("code")
        print(f"Found {len(results)} agents with 'code' capability")
        
        # 統計
        stats = registry.get_stats()
        print(f"Stats: {stats}")
        
        # ファイル確認
        print(f"Registry file: {registry._data_file}")
        print(f"File exists: {registry._data_file.exists()}")
    
    asyncio.run(test())
