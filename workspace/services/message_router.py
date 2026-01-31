#!/usr/bin/env python3
"""
Message Router Service
AI間メッセージルーティング機能

機能:
- Direct routing: 特定ピアへの送信
- Broadcast: 全ピアへの送信
- Multicast: 特定機能を持つピアへの送信
- Anycast: 最も近い/適切なピアへの送信
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

import aiohttp
from aiohttp import ClientTimeout

from peer_service import PeerService, get_service as get_peer_service
from registry import get_registry

try:
    from crypto import SecureMessage, MessageSigner
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """ルーティング戦略"""
    DIRECT = "direct"       # 特定ピアへ直接送信
    BROADCAST = "broadcast" # 全ピアに送信
    MULTICAST = "multicast" # 特定機能を持つピアに送信
    ANYCAST = "anycast"     # 最も近い/適切なピアに送信


@dataclass
class RoutingResult:
    """ルーティング結果"""
    success: bool
    message_id: str
    recipients: List[str]
    failed_recipients: List[str]
    timestamp: datetime
    errors: List[str]


class MessageRouter:
    """メッセージルーター
    
    メッセージを適切なピアにルーティングする。
    複数のルーティング戦略をサポート。
    """
    
    def __init__(self, peer_service: Optional[PeerService] = None):
        """MessageRouterを初期化
        
        Args:
            peer_service: PeerServiceインスタンス（省略時はグローバルインスタンス）
        """
        self.peer_service = peer_service or get_peer_service()
        self.registry = get_registry()
        self._routing_table: Dict[str, Dict] = {}
        self._message_handlers: Dict[str, Callable] = {}
        self._sent_messages: Dict[str, datetime] = {}  # 重複防止
        
        if not self.peer_service:
            logger.warning("PeerService not initialized")
    
    async def route_message(
        self,
        message: Dict[str, Any],
        strategy: RoutingStrategy = RoutingStrategy.DIRECT,
        target: Optional[str] = None,
        capability: Optional[str] = None
    ) -> RoutingResult:
        """メッセージをルーティング
        
        Args:
            message: 送信するメッセージ
            strategy: ルーティング戦略
            target: 送信先（DIRECT/ANYCAST用）
            capability: 機能フィルタ（MULTICAST用）
            
        Returns:
            ルーティング結果
        """
        message_id = message.get('msg_id') or message.get('nonce') or f"msg_{datetime.now(timezone.utc).timestamp()}"
        
        # 重複チェック
        if message_id in self._sent_messages:
            logger.debug(f"Duplicate message: {message_id}")
            return RoutingResult(
                success=False,
                message_id=message_id,
                recipients=[],
                failed_recipients=[],
                timestamp=datetime.now(timezone.utc),
                errors=["Duplicate message"]
            )
        
        self._sent_messages[message_id] = datetime.now(timezone.utc)
        
        # 戦略に基づいてルーティング
        if strategy == RoutingStrategy.DIRECT:
            return await self._route_direct(message, target)
        elif strategy == RoutingStrategy.BROADCAST:
            return await self._route_broadcast(message)
        elif strategy == RoutingStrategy.MULTICAST:
            return await self._route_multicast(message, capability)
        elif strategy == RoutingStrategy.ANYCAST:
            return await self._route_anycast(message, target, capability)
        else:
            return RoutingResult(
                success=False,
                message_id=message_id,
                recipients=[],
                failed_recipients=[],
                timestamp=datetime.now(timezone.utc),
                errors=[f"Unknown routing strategy: {strategy}"]
            )
    
    async def _route_direct(self, message: Dict, target: Optional[str]) -> RoutingResult:
        """直接ルーティング"""
        if not target:
            return RoutingResult(
                success=False,
                message_id=message.get('msg_id', 'unknown'),
                recipients=[],
                failed_recipients=[],
                timestamp=datetime.now(timezone.utc),
                errors=["Target required for direct routing"]
            )
        
        if not self.peer_service:
            return RoutingResult(
                success=False,
                message_id=message.get('msg_id', 'unknown'),
                recipients=[],
                failed_recipients=[target],
                timestamp=datetime.now(timezone.utc),
                errors=["PeerService not available"]
            )
        
        msg_type = message.get('msg_type', 'message')
        success = await self.peer_service.send_message(target, msg_type, message)
        
        return RoutingResult(
            success=success,
            message_id=message.get('msg_id', 'unknown'),
            recipients=[target] if success else [],
            failed_recipients=[] if success else [target],
            timestamp=datetime.now(timezone.utc),
            errors=[] if success else ["Send failed"]
        )
    
    async def _route_broadcast(self, message: Dict) -> RoutingResult:
        """ブロードキャストルーティング"""
        if not self.peer_service:
            return RoutingResult(
                success=False,
                message_id=message.get('msg_id', 'unknown'),
                recipients=[],
                failed_recipients=[],
                timestamp=datetime.now(timezone.utc),
                errors=["PeerService not available"]
            )
        
        msg_type = message.get('msg_type', 'message')
        results = await self.peer_service.broadcast_message(msg_type, message)
        
        recipients = [peer for peer, success in results.items() if success]
        failed = [peer for peer, success in results.items() if not success]
        
        return RoutingResult(
            success=len(recipients) > 0,
            message_id=message.get('msg_id', 'unknown'),
            recipients=recipients,
            failed_recipients=failed,
            timestamp=datetime.now(timezone.utc),
            errors=[] if len(recipients) > 0 else ["All sends failed"]
        )
    
    async def _route_multicast(self, message: Dict, capability: Optional[str]) -> RoutingResult:
        """マルチキャストルーティング"""
        if not capability:
            return RoutingResult(
                success=False,
                message_id=message.get('msg_id', 'unknown'),
                recipients=[],
                failed_recipients=[],
                timestamp=datetime.now(timezone.utc),
                errors=["Capability required for multicast routing"]
            )
        
        # レジストリから該当するエージェントを検索
        services = self.registry.find_by_capability(capability)
        
        if not services:
            return RoutingResult(
                success=False,
                message_id=message.get('msg_id', 'unknown'),
                recipients=[],
                failed_recipients=[],
                timestamp=datetime.now(timezone.utc),
                errors=[f"No agents found with capability: {capability}"]
            )
        
        recipients = []
        failed = []
        errors = []
        
        for service in services:
            # エンドポイントからピアIDを取得（簡易的）
            peer_id = service.entity_id
            
            if self.peer_service:
                success = await self.peer_service.send_message(
                    peer_id,
                    message.get('msg_type', 'message'),
                    message
                )
                if success:
                    recipients.append(peer_id)
                else:
                    failed.append(peer_id)
                    errors.append(f"Failed to send to {peer_id}")
            else:
                failed.append(peer_id)
        
        return RoutingResult(
            success=len(recipients) > 0,
            message_id=message.get('msg_id', 'unknown'),
            recipients=recipients,
            failed_recipients=failed,
            timestamp=datetime.now(timezone.utc),
            errors=errors
        )
    
    async def _route_anycast(
        self,
        message: Dict,
        target: Optional[str],
        capability: Optional[str]
    ) -> RoutingResult:
        """エニーキャストルーティング"""
        # 最も適切なピアを選択
        candidates = []
        
        if target and self.peer_service and target in self.peer_service.peers:
            # 指定されたターゲットが存在する場合
            candidates = [target]
        elif capability:
            # 機能に基づいて検索
            services = self.registry.find_by_capability(capability)
            candidates = [s.entity_id for s in services]
        
        if not candidates:
            return RoutingResult(
                success=False,
                message_id=message.get('msg_id', 'unknown'),
                recipients=[],
                failed_recipients=[],
                timestamp=datetime.now(timezone.utc),
                errors=["No suitable peer found for anycast"]
            )
        
        # 最初の候補に送信（シンプルな実装）
        # TODO: レイテンシー、負荷などを考慮した選択
        selected = candidates[0]
        
        return await self._route_direct(message, selected)
    
    def add_route(self, destination: str, next_hop: str, metric: int = 1):
        """ルーティングテーブルにエントリを追加"""
        self._routing_table[destination] = {
            'next_hop': next_hop,
            'metric': metric,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
    
    def get_routing_table(self) -> Dict:
        """ルーティングテーブルを取得"""
        return self._routing_table.copy()
    
    def get_stats(self) -> Dict:
        """ルーター統計を取得"""
        return {
            'routing_table_size': len(self._routing_table),
            'sent_messages': len(self._sent_messages),
            'peers': len(self.peer_service.peers) if self.peer_service else 0
        }


# グローバルインスタンス
_router: Optional[MessageRouter] = None


def init_router(peer_service: Optional[PeerService] = None) -> MessageRouter:
    """ルーターを初期化"""
    global _router
    _router = MessageRouter(peer_service)
    return _router


def get_router() -> Optional[MessageRouter]:
    """ルーターインスタンスを取得"""
    return _router


async def main():
    """テスト実行"""
    from peer_service import init_service
    
    # PeerService初期化
    peer_service = init_service("test-router", 8001)
    
    # ルーター初期化
    router = init_router(peer_service)
    
    # テストメッセージ
    message = {
        'msg_id': 'test-001',
        'msg_type': 'test',
        'payload': {'data': 'hello'},
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    
    # ブロードキャストテスト
    result = await router.route_message(message, RoutingStrategy.BROADCAST)
    print(f"Broadcast result: {result}")
    
    # 統計表示
    print(f"Stats: {router.get_stats()}")


if __name__ == "__main__":
    asyncio.run(main())
