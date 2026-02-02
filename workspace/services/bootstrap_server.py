#!/usr/bin/env python3
"""
Bootstrap Server for Distributed AI Network
分散型AIネットワーク用ブートストラップサーバー

機能:
- 新規ピアの登録
- 既知のピアリスト提供
- ヘルスチェック
- 古いエントリの自動削除

Protocol: v1.2
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set
from enum import Enum

try:
    from fastapi import FastAPI, HTTPException, Request, Query
    from fastapi.responses import JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PeerStatus(Enum):
    """ピアの状態"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNREACHABLE = "unreachable"


@dataclass
class PeerEntry:
    """ブートストラップに登録されるピア情報"""
    entity_id: str
    address: str  # http://host:port
    public_key: Optional[str] = None  # hex-encoded Ed25519 public key
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: PeerStatus = PeerStatus.ACTIVE
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "entity_id": self.entity_id,
            "address": self.address,
            "public_key": self.public_key,
            "last_seen": self.last_seen.isoformat(),
            "status": self.status.value,
            "capabilities": self.capabilities,
            "metadata": self.metadata
        }


class BootstrapServer:
    """ブートストラップサーバー
    
    AIエージェントがネットワークに参加する際の最初の接続先。
    既知のピアリストを提供し、新規ピアの登録を管理する。
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9000,
        cleanup_interval: int = 300,  # 5分
        peer_timeout: int = 1800,  # 30分
        max_peers: int = 10000
    ):
        self.host = host
        self.port = port
        self.cleanup_interval = cleanup_interval
        self.peer_timeout = peer_timeout
        self.max_peers = max_peers
        
        # ピアレジストリ
        self._peers: Dict[str, PeerEntry] = {}
        self._lock = asyncio.Lock()
        
        # メッセージストア（ストア＆フォワード用）
        self._message_store: Dict[str, List[Dict]] = {}
        self._message_lock = asyncio.Lock()
        self._max_stored_messages = 100  # エンティティあたり最大メッセージ数
        
        # 統計
        self._stats = {
            "total_registered": 0,
            "total_removed": 0,
            "lookup_requests": 0,
            "register_requests": 0
        }
        
        # クリーンアップタスク
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # FastAPIアプリ
        self.app = None
        if FASTAPI_AVAILABLE:
            self._init_app()
    
    def _init_app(self):
        """FastAPIアプリケーションを初期化"""
        self.app = FastAPI(
            title="Bootstrap Server",
            description="Distributed AI Network Bootstrap Server",
            version="1.2.0"
        )
        
        @self.app.post("/register")
        async def register_peer(request: Request):
            """新規ピアを登録"""
            try:
                data = await request.json()
                
                entity_id = data.get("entity_id")
                address = data.get("address")
                public_key = data.get("public_key")
                capabilities = data.get("capabilities", [])
                
                if not entity_id or not address:
                    raise HTTPException(status_code=400, detail="Missing entity_id or address")
                
                success = await self.register_peer(
                    entity_id=entity_id,
                    address=address,
                    public_key=public_key,
                    capabilities=capabilities,
                    metadata=data.get("metadata", {})
                )
                
                if success:
                    return JSONResponse({
                        "status": "success",
                        "message": f"Peer {entity_id} registered"
                    })
                else:
                    return JSONResponse({
                        "status": "error",
                        "message": "Registration failed (max peers reached or other error)"
                    }, status_code=503)
                    
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            except Exception as e:
                logger.error(f"Registration error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/discover")
        async def discover_peers(
            count: int = Query(10, ge=1, le=100),
            exclude: Optional[str] = Query(None)
        ):
            """ピアリストを取得"""
            exclude_set = set(exclude.split(",")) if exclude else set()
            peers = await self.get_peer_list(count, exclude_set)
            
            self._stats["lookup_requests"] += 1
            
            return JSONResponse({
                "peers": [p.to_dict() for p in peers],
                "count": len(peers),
                "total_known": len(self._peers)
            })
        
        @self.app.get("/find/{entity_id}")
        async def find_peer(entity_id: str):
            """特定のピアを検索"""
            peer = await self.find_peer(entity_id)
            
            if peer:
                return JSONResponse(peer.to_dict())
            else:
                raise HTTPException(status_code=404, detail="Peer not found")
        
        @self.app.post("/heartbeat/{entity_id}")
        async def heartbeat(entity_id: str):
            """ハートビートを受信"""
            success = await self.update_last_seen(entity_id)
            
            if success:
                return JSONResponse({
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            else:
                raise HTTPException(status_code=404, detail="Peer not found")
        
        @self.app.get("/stats")
        async def get_stats():
            """サーバー統計を取得"""
            return JSONResponse({
                "total_peers": len(self._peers),
                "stats": self._stats,
                "config": {
                    "cleanup_interval": self.cleanup_interval,
                    "peer_timeout": self.peer_timeout,
                    "max_peers": self.max_peers
                }
            })
        
        @self.app.get("/health")
        async def health_check():
            """ヘルスチェック"""
            return JSONResponse({
                "status": "healthy",
                "peers": len(self._peers),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        
        @self.app.post("/message")
        async def relay_message(request: Request):
            """ピア間メッセージを中継
            
            送信者→Bootstrap Server→受信者のエンドポイントに転送
            """
            try:
                data = await request.json()
                
                sender_id = data.get("sender_id")
                recipient_id = data.get("recipient_id")
                message = data.get("message")
                message_type = data.get("type", "text")
                
                if not sender_id or not recipient_id or not message:
                    raise HTTPException(
                        status_code=400, 
                        detail="Missing sender_id, recipient_id, or message"
                    )
                
                # 受信者を検索
                recipient = await self.find_peer(recipient_id)
                if not recipient:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Recipient {recipient_id} not found"
                    )
                
                # 送信者を検証（オプション）
                sender = await self.find_peer(sender_id)
                
                # メッセージにメタデータを追加
                message_envelope = {
                    "sender_id": sender_id,
                    "recipient_id": recipient_id,
                    "message": message,
                    "type": message_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "relayed_by": "bootstrap-server",
                    "sender_verified": sender is not None
                }
                
                # 受信者のエンドポイントに転送を試行
                import aiohttp
                try:
                    async with aiohttp.ClientSession() as session:
                        recipient_endpoint = f"{recipient.address}/message"
                        async with session.post(
                            recipient_endpoint,
                            json=message_envelope,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 200:
                                return JSONResponse({
                                    "status": "delivered",
                                    "recipient": recipient_id,
                                    "recipient_endpoint": recipient_endpoint,
                                    "timestamp": message_envelope["timestamp"]
                                })
                            else:
                                # 直接配送失敗、ストア＆フォワード
                                stored = await self.store_message(
                                    recipient_id, message_envelope
                                )
                                return JSONResponse({
                                    "status": "stored",
                                    "recipient": recipient_id,
                                    "reason": f"Direct delivery failed (HTTP {response.status})",
                                    "stored": stored,
                                    "timestamp": message_envelope["timestamp"]
                                })
                except Exception as e:
                    # 転送失敗、ストア＆フォワード
                    stored = await self.store_message(
                        recipient_id, message_envelope
                    )
                    return JSONResponse({
                        "status": "stored",
                        "recipient": recipient_id,
                        "reason": f"Direct delivery error: {str(e)}",
                        "stored": stored,
                        "timestamp": message_envelope["timestamp"]
                    })
                    
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Message relay error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/messages/{entity_id}")
        async def get_messages(entity_id: str, limit: int = Query(10, ge=1, le=100)):
            """保存されているメッセージを取得（ストア＆フォワード）"""
            messages = await self.get_stored_messages(entity_id, limit)
            return JSONResponse({
                "entity_id": entity_id,
                "messages": messages,
                "count": len(messages)
            })
        
        @self.app.delete("/messages/{entity_id}")
        async def clear_messages(entity_id: str):
            """メッセージをクリア"""
            cleared = await self.clear_stored_messages(entity_id)
            return JSONResponse({
                "entity_id": entity_id,
                "cleared": cleared
            })
    
    async def register_peer(
        self,
        entity_id: str,
        address: str,
        public_key: Optional[str] = None,
        capabilities: List[str] = None,
        metadata: Dict = None
    ) -> bool:
        """ピアを登録
        
        Args:
            entity_id: エンティティID
            address: アドレス（http://host:port）
            public_key: 公開鍵（hex）
            capabilities: 対応機能リスト
            metadata: 追加メタデータ
            
        Returns:
            登録成功ならTrue
        """
        async with self._lock:
            # 最大数チェック
            if len(self._peers) >= self.max_peers and entity_id not in self._peers:
                logger.warning(f"Max peers reached ({self.max_peers}), rejecting {entity_id}")
                return False
            
            # 登録
            self._peers[entity_id] = PeerEntry(
                entity_id=entity_id,
                address=address,
                public_key=public_key,
                capabilities=capabilities or [],
                metadata=metadata or {}
            )
            
            self._stats["total_registered"] += 1
            self._stats["register_requests"] += 1
            
            logger.info(f"Registered peer: {entity_id} at {address}")
            return True
    
    async def get_peer_list(
        self,
        count: int = 10,
        exclude: Optional[Set[str]] = None
    ) -> List[PeerEntry]:
        """ピアリストを取得
        
        Args:
            count: 取得数
            exclude: 除外するエンティティID
            
        Returns:
            PeerEntryのリスト
        """
        exclude = exclude or set()
        
        async with self._lock:
            # アクティブなピアのみ
            active_peers = [
                p for p in self._peers.values()
                if p.status == PeerStatus.ACTIVE and p.entity_id not in exclude
            ]
            
            # ランダムに選択
            import random
            if len(active_peers) > count:
                return random.sample(active_peers, count)
            return active_peers
    
    async def find_peer(self, entity_id: str) -> Optional[PeerEntry]:
        """特定のピアを検索
        
        Args:
            entity_id: エンティティID
            
        Returns:
            PeerEntryまたはNone
        """
        async with self._lock:
            return self._peers.get(entity_id)
    
    async def update_last_seen(self, entity_id: str) -> bool:
        """最終確認時刻を更新
        
        Args:
            entity_id: エンティティID
            
        Returns:
            更新成功ならTrue
        """
        async with self._lock:
            if entity_id in self._peers:
                self._peers[entity_id].last_seen = datetime.now(timezone.utc)
                self._peers[entity_id].status = PeerStatus.ACTIVE
                return True
            return False
    
    async def store_message(self, entity_id: str, message: Dict) -> bool:
        """メッセージをストア（ストア＆フォワード）
        
        Args:
            entity_id: 受信者エンティティID
            message: メッセージデータ
            
        Returns:
            保存成功ならTrue
        """
        async with self._message_lock:
            if entity_id not in self._message_store:
                self._message_store[entity_id] = []
            
            # 最大数チェック、超えたら古いものから削除
            if len(self._message_store[entity_id]) >= self._max_stored_messages:
                self._message_store[entity_id] = self._message_store[entity_id][-self._max_stored_messages + 1:]
            
            self._message_store[entity_id].append(message)
            logger.info(f"Stored message for {entity_id}")
            return True
    
    async def get_stored_messages(self, entity_id: str, limit: int = 10) -> List[Dict]:
        """保存されているメッセージを取得
        
        Args:
            entity_id: エンティティID
            limit: 取得件数
            
        Returns:
            メッセージリスト
        """
        async with self._message_lock:
            messages = self._message_store.get(entity_id, [])
            return messages[-limit:] if messages else []
    
    async def clear_stored_messages(self, entity_id: str) -> int:
        """保存されているメッセージをクリア
        
        Args:
            entity_id: エンティティID
            
        Returns:
            クリアしたメッセージ数
        """
        async with self._message_lock:
            if entity_id in self._message_store:
                count = len(self._message_store[entity_id])
                del self._message_store[entity_id]
                logger.info(f"Cleared {count} messages for {entity_id}")
                return count
            return 0
    
    async def remove_peer(self, entity_id: str) -> bool:
        """ピアを削除
        
        Args:
            entity_id: エンティティID
            
        Returns:
            削除成功ならTrue
        """
        async with self._lock:
            if entity_id in self._peers:
                del self._peers[entity_id]
                self._stats["total_removed"] += 1
                logger.info(f"Removed peer: {entity_id}")
                return True
            return False
    
    async def start(self):
        """サーバーを開始"""
        # クリーンアップタスク開始
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        if not FASTAPI_AVAILABLE:
            logger.error("FastAPI not available, cannot start HTTP server")
            return
        
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        
        logger.info(f"Bootstrap server starting on {self.host}:{self.port}")
        await server.serve()
    
    async def stop(self):
        """サーバーを停止"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Bootstrap server stopped")
    
    async def _cleanup_loop(self):
        """古いエントリを削除するループ"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_peers()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _cleanup_old_peers(self):
        """古いピアエントリを削除"""
        now = datetime.now(timezone.utc)
        to_remove = []
        
        async with self._lock:
            for entity_id, peer in self._peers.items():
                age = (now - peer.last_seen).total_seconds()
                
                if age > self.peer_timeout:
                    to_remove.append(entity_id)
                    peer.status = PeerStatus.UNREACHABLE
        
        # 削除
        for entity_id in to_remove:
            await self.remove_peer(entity_id)
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old peers")


# グローバルインスタンス
_server: Optional[BootstrapServer] = None


def init_server(
    host: str = "0.0.0.0",
    port: int = 9000,
    **kwargs
) -> BootstrapServer:
    """サーバーを初期化
    
    Args:
        host: ホスト
        port: ポート
        **kwargs: 追加設定
        
    Returns:
        BootstrapServerインスタンス
    """
    global _server
    _server = BootstrapServer(host=host, port=port, **kwargs)
    return _server


def get_server() -> Optional[BootstrapServer]:
    """サーバーインスタンスを取得"""
    return _server


if __name__ == "__main__":
    # テスト実行
    server = init_server(port=9000)
    asyncio.run(server.start())
