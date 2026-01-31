#!/usr/bin/env python3
"""
Peer Communication Service
AI間の相互通信を実現するサービス
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

import aiohttp
from aiohttp import ClientTimeout, ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PeerService:
    """ピア間通信サービス"""
    
    def __init__(self, entity_id: str, port: int):
        self.entity_id = entity_id
        self.port = port
        self.peers = {}  # {entity_id: address}
        self.message_handlers = {}
        
    def register_handler(self, message_type: str, handler):
        """メッセージハンドラを登録"""
        self.message_handlers[message_type] = handler
        
    async def send_message(self, target_id: str, message_type: str, payload: dict) -> bool:
        """ピアにメッセージを送信（HTTP POST）"""
        if target_id not in self.peers:
            logger.error(f"Unknown peer: {target_id}")
            return False
            
        message = {
            "from": self.entity_id,
            "type": message_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        address = self.peers[target_id]
        url = f"{address}/message"
        
        timeout = ClientTimeout(total=10, connect=5)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json=message,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        logger.info(f"Sent {message_type} to {target_id} successfully")
                        return True
                    else:
                        logger.warning(
                            f"Failed to send {message_type} to {target_id}: "
                            f"HTTP {response.status}"
                        )
                        return False
        except asyncio.TimeoutError:
            logger.error(f"Timeout sending {message_type} to {target_id}")
            return False
        except ClientError as e:
            logger.error(f"Connection error sending {message_type} to {target_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending {message_type} to {target_id}: {e}")
            return False
        
    async def handle_message(self, message: dict):
        """受信メッセージを処理"""
        msg_type = message.get("type")
        handler = self.message_handlers.get(msg_type)
        
        if handler:
            await handler(message)
        else:
            logger.warning(f"No handler for {msg_type}")
            
    def add_peer(self, entity_id: str, address: str):
        """ピアを登録"""
        self.peers[entity_id] = address
        logger.info(f"Added peer: {entity_id} at {address}")
        
    async def health_check(self) -> dict:
        """ヘルスチェック"""
        return {
            "entity_id": self.entity_id,
            "port": self.port,
            "peers": len(self.peers),
            "status": "healthy"
        }


# グローバルインスタンス
_service: Optional[PeerService] = None


def init_service(entity_id: str, port: int) -> PeerService:
    """サービスを初期化"""
    global _service
    _service = PeerService(entity_id, port)
    return _service


def get_service() -> Optional[PeerService]:
    """サービスインスタンスを取得"""
    return _service


# FastAPI サーバー用
class PeerServer:
    """FastAPIベースのピア通信サーバー"""
    
    def __init__(self, service: PeerService):
        self.service = service
        self.app = None
        self._init_app()
        
    def _init_app(self):
        """FastAPIアプリケーションを初期化"""
        try:
            from fastapi import FastAPI, HTTPException, Request
            from fastapi.responses import JSONResponse
            import uvicorn
            
            self.app = FastAPI(title=f"Peer Service - {self.service.entity_id}")
            
            @self.app.post("/message")
            async def handle_message_endpoint(request: Request):
                """メッセージ受信エンドポイント"""
                try:
                    message = await request.json()
                    logger.info(f"Received message: {message.get('type')} from {message.get('from')}")
                    
                    # メッセージ処理
                    await self.service.handle_message(message)
                    
                    return JSONResponse(
                        content={"status": "received", "entity_id": self.service.entity_id}
                    )
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    raise HTTPException(status_code=400, detail="Invalid JSON")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    raise HTTPException(status_code=500, detail=str(e))
            
            @self.app.get("/health")
            async def health_check_endpoint():
                """ヘルスチェックエンドポイント"""
                return await self.service.health_check()
            
            @self.app.get("/")
            async def root():
                """ルートエンドポイント"""
                return {
                    "entity_id": self.service.entity_id,
                    "service": "peer-communication",
                    "version": "0.2"
                }
                
        except ImportError as e:
            logger.error(f"FastAPI/uvicorn not installed: {e}")
            self.app = None
    
    async def start(self, host: str = "0.0.0.0", port: Optional[int] = None):
        """サーバーを起動"""
        import uvicorn
        
        if self.app is None:
            raise RuntimeError("FastAPI app not initialized. Install fastapi and uvicorn.")
        
        port = port or self.service.port
        config = uvicorn.Config(self.app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()


def create_server(service: PeerService) -> PeerServer:
    """PeerServerインスタンスを作成"""
    return PeerServer(service)


if __name__ == "__main__":
    # テスト実行
    service = init_service("test-entity", 8001)
    print(f"Service initialized: {service.entity_id}")
