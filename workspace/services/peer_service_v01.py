#!/usr/bin/env python3
"""
Peer Communication Service - Protocol v0.1 Implementation
軽量なAI間通信サービス実装

Features:
- Ed25519署名によるメッセージ認証
- リプレイ攻撃防止（nonce + timestamp）
- シンプルなメッセージハンドリング
- HTTPベース通信

Protocol: peer_protocol_v05.md (v0.1)
"""

import asyncio
import base64
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any, Callable, Awaitable
from collections import defaultdict

import aiohttp
from aiohttp import web

# Ed25519暗号ライブラリ
try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.exceptions import BadSignatureError
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False
    print("Warning: PyNaCl not available. Signatures will not work.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
PROTOCOL_VERSION = "0.1"
NONCE_BYTES = 16
TIMESTAMP_TOLERANCE_SEC = 300  # 5 minutes
MAX_STORED_NONCES = 1000
RETRY_DELAYS = [1, 2, 4]  # seconds


@dataclass
class PeerInfo:
    """ピア情報"""
    entity_id: str
    public_key: Optional[str] = None
    endpoint: Optional[str] = None
    last_seen: Optional[datetime] = None
    capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "public_key": self.public_key,
            "endpoint": self.endpoint,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "capabilities": self.capabilities
        }


@dataclass
class Message:
    """v0.1プロトコルメッセージ"""
    version: str
    msg_type: str
    sender_id: str
    recipient_id: str
    timestamp: str
    nonce: str
    payload: Dict[str, Any]
    signature: Optional[str] = None
    
    @classmethod
    def create(
        cls,
        msg_type: str,
        sender_id: str,
        recipient_id: str,
        payload_data: dict,
        signing_key: Optional[SigningKey] = None
    ) -> "Message":
        """新規メッセージ作成"""
        timestamp = datetime.now(timezone.utc).isoformat()
        nonce = secrets.token_hex(NONCE_BYTES)
        
        payload = {
            "data": base64.b64encode(
                json.dumps(payload_data).encode()
            ).decode()
        }
        
        msg = cls(
            version=PROTOCOL_VERSION,
            msg_type=msg_type,
            sender_id=sender_id,
            recipient_id=recipient_id,
            timestamp=timestamp,
            nonce=nonce,
            payload=payload,
            signature=None
        )
        
        if signing_key and NACL_AVAILABLE:
            msg.sign(signing_key)
        
        return msg
    
    def get_signature_data(self) -> str:
        """署名対象データ生成"""
        payload_data = self.payload.get("data", "")
        return (
            f"{self.version}{self.msg_type}"
            f"{self.sender_id}{self.recipient_id}"
            f"{self.timestamp}{self.nonce}{payload_data}"
        )
    
    def sign(self, signing_key: SigningKey) -> None:
        """メッセージ署名"""
        if not NACL_AVAILABLE:
            raise RuntimeError("PyNaCl not available")
        
        sig_data = self.get_signature_data().encode()
        signed = signing_key.sign(sig_data)
        self.signature = signed.signature.hex()
    
    def verify(self, verify_key: VerifyKey) -> bool:
        """署名検証"""
        if not NACL_AVAILABLE or not self.signature:
            return False
        
        try:
            sig_data = self.get_signature_data().encode()
            signature_bytes = bytes.fromhex(self.signature)
            verify_key.verify(sig_data, signature_bytes)
            return True
        except (BadSignatureError, ValueError) as e:
            logger.debug(f"Signature verification failed: {e}")
            return False
    
    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "version": self.version,
            "msg_type": self.msg_type,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "payload": self.payload,
            "signature": self.signature
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """辞書からメッセージ生成"""
        return cls(
            version=data.get("version", PROTOCOL_VERSION),
            msg_type=data.get("msg_type", ""),
            sender_id=data.get("sender_id", ""),
            recipient_id=data.get("recipient_id", ""),
            timestamp=data.get("timestamp", ""),
            nonce=data.get("nonce", ""),
            payload=data.get("payload", {}),
            signature=data.get("signature")
        )
    
    def get_payload_data(self) -> Optional[dict]:
        """ペイロードデータをデコード"""
        try:
            data_b64 = self.payload.get("data", "")
            return json.loads(base64.b64decode(data_b64))
        except Exception as e:
            logger.debug(f"Failed to decode payload: {e}")
            return None


class PeerServiceV01:
    """
    Protocol v0.1対応ピアサービス
    
    シンプルで軽量な実装。主な機能:
    - メッセージ送受信
    - 署名検証
    - リプレイ保護
    - ピア管理
    """
    
    def __init__(
        self,
        entity_id: str,
        signing_key: Optional[SigningKey] = None,
        host: str = "0.0.0.0",
        port: int = 8000
    ):
        self.entity_id = entity_id
        self.signing_key = signing_key
        self.host = host
        self.port = port
        
        # ピア管理
        self.peers: Dict[str, PeerInfo] = {}
        self.used_nonces: Dict[str, set] = defaultdict(set)
        
        # ハンドラ登録
        self.handlers: Dict[str, Callable[[Message], Awaitable[Optional[Message]]]] = {}
        
        # HTTPサーバー
        self.app = web.Application()
        self._setup_routes()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        
        # 統計
        self.stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "messages_verified": 0,
            "messages_rejected": 0,
            "peers_connected": 0
        }
        
        logger.info(f"PeerServiceV01 initialized for {entity_id}")
    
    def _setup_routes(self) -> None:
        """HTTPルート設定"""
        self.app.router.add_post("/v0.1/message", self._handle_message)
        self.app.router.add_get("/v0.1/health", self._handle_health)
        self.app.router.add_get("/v0.1/public-key", self._handle_public_key)
    
    # === 公開API ===
    
    def register_handler(
        self,
        msg_type: str,
        handler: Callable[[Message], Awaitable[Optional[Message]]]
    ) -> None:
        """メッセージハンドラを登録"""
        self.handlers[msg_type] = handler
        logger.debug(f"Registered handler for {msg_type}")
    
    def register_peer(
        self,
        entity_id: str,
        public_key_hex: Optional[str] = None,
        endpoint: Optional[str] = None
    ) -> None:
        """ピアを登録"""
        self.peers[entity_id] = PeerInfo(
            entity_id=entity_id,
            public_key=public_key_hex,
            endpoint=endpoint
        )
        self.stats["peers_connected"] = len(self.peers)
        logger.info(f"Registered peer: {entity_id}")
    
    async def send_message(
        self,
        recipient_id: str,
        msg_type: str,
        payload: dict,
        retry: bool = True
    ) -> bool:
        """
        メッセージ送信
        
        Args:
            recipient_id: 宛先ピアID
            msg_type: メッセージタイプ
            payload: メッセージペイロード
            retry: 失敗時にリトライするか
        
        Returns:
            送信成功したか
        """
        peer = self.peers.get(recipient_id)
        if not peer or not peer.endpoint:
            logger.error(f"Unknown peer or no endpoint: {recipient_id}")
            return False
        
        # メッセージ作成
        msg = Message.create(
            msg_type=msg_type,
            sender_id=self.entity_id,
            recipient_id=recipient_id,
            payload_data=payload,
            signing_key=self.signing_key
        )
        
        # 送信（リトライ付き）
        delays = RETRY_DELAYS if retry else [0]
        
        for delay in delays:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{peer.endpoint}/v0.1/message",
                        json=msg.to_dict(),
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            self.stats["messages_sent"] += 1
                            logger.debug(f"Message sent to {recipient_id}: {msg_type}")
                            return True
                        else:
                            logger.warning(f"Failed to send message: {resp.status}")
            except Exception as e:
                logger.debug(f"Send error (will retry): {e}")
            
            if delay > 0:
                await asyncio.sleep(delay)
        
        return False
    
    async def ping(self, peer_id: str) -> bool:
        """ピアにping送信"""
        return await self.send_message(
            recipient_id=peer_id,
            msg_type="ping",
            payload={}
        )
    
    async def send_status(
        self,
        peer_id: str,
        state: str = "active",
        tasks_pending: int = 0,
        tasks_completed: int = 0,
        capabilities: Optional[List[str]] = None
    ) -> bool:
        """ステータスレポート送信"""
        return await self.send_message(
            recipient_id=peer_id,
            msg_type="status",
            payload={
                "state": state,
                "tasks_pending": tasks_pending,
                "tasks_completed": tasks_completed,
                "capabilities": capabilities or []
            }
        )
    
    async def delegate_task(
        self,
        peer_id: str,
        task_id: str,
        task_type: str,
        description: str,
        priority: str = "normal",
        deadline: Optional[str] = None
    ) -> bool:
        """タスク委譲"""
        return await self.send_message(
            recipient_id=peer_id,
            msg_type="delegate",
            payload={
                "task_id": task_id,
                "type": task_type,
                "description": description,
                "priority": priority,
                "deadline": deadline
            }
        )
    
    async def send_result(
        self,
        peer_id: str,
        task_id: str,
        status: str,
        result: str,
        duration_sec: Optional[int] = None
    ) -> bool:
        """タスク結果送信"""
        payload = {
            "task_id": task_id,
            "status": status,
            "result": result
        }
        if duration_sec is not None:
            payload["duration_sec"] = duration_sec
        
        return await self.send_message(
            recipient_id=peer_id,
            msg_type="result",
            payload=payload
        )
    
    # === HTTPハンドラ ===
    
    async def _handle_message(self, request: web.Request) -> web.Response:
        """メッセージ受信ハンドラ"""
        try:
            data = await request.json()
            msg = Message.from_dict(data)
            
            # 検証
            is_valid, error = await self._verify_message(msg)
            if not is_valid:
                self.stats["messages_rejected"] += 1
                return web.json_response(
                    {"error": error},
                    status=400
                )
            
            self.stats["messages_verified"] += 1
            self.stats["messages_received"] += 1
            
            # ピア更新
            if msg.sender_id in self.peers:
                self.peers[msg.sender_id].last_seen = datetime.now(timezone.utc)
            
            # ハンドラ実行
            handler = self.handlers.get(msg.msg_type)
            if handler:
                try:
                    response = await handler(msg)
                    if response:
                        return web.json_response(response.to_dict())
                except Exception as e:
                    logger.error(f"Handler error: {e}")
                    return web.json_response(
                        {"error": "HANDLER_ERROR"},
                        status=500
                    )
            
            return web.json_response({"status": "received"})
            
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "INVALID_JSON"},
                status=400
            )
        except Exception as e:
            logger.error(f"Message handling error: {e}")
            return web.json_response(
                {"error": "INTERNAL_ERROR"},
                status=500
            )
    
    async def _handle_health(self, request: web.Request) -> web.Response:
        """ヘルスチェックハンドラ"""
        return web.json_response({
            "status": "healthy",
            "version": PROTOCOL_VERSION,
            "entity_id": self.entity_id,
            "stats": self.stats
        })
    
    async def _handle_public_key(self, request: web.Request) -> web.Response:
        """公開鍵配布ハンドラ"""
        if not self.signing_key or not NACL_AVAILABLE:
            return web.json_response(
                {"error": "NO_PUBLIC_KEY"},
                status=503
            )
        
        public_key = self.signing_key.verify_key.encode().hex()
        return web.json_response({
            "entity_id": self.entity_id,
            "public_key": public_key,
            "algorithm": "Ed25519"
        })
    
    # === 検証ロジック ===
    
    async def _verify_message(self, msg: Message) -> tuple[bool, Optional[str]]:
        """
        メッセージ検証
        
        Returns:
            (is_valid, error_code)
        """
        # バージョンチェック
        if msg.version != PROTOCOL_VERSION:
            return False, "INVALID_VERSION"
        
        # 宛先チェック
        if msg.recipient_id != self.entity_id:
            return False, "UNKNOWN_RECIPIENT"
        
        # タイムスタンプチェック
        try:
            msg_time = datetime.fromisoformat(msg.timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = abs((now - msg_time).total_seconds())
            if diff > TIMESTAMP_TOLERANCE_SEC:
                return False, "EXPIRED_TIMESTAMP"
        except ValueError:
            return False, "INVALID_TIMESTAMP"
        
        # リプレイチェック
        if msg.nonce in self.used_nonces[msg.sender_id]:
            return False, "REPLAY_DETECTED"
        
        # 署名検証（ピア登録済みの場合）
        peer = self.peers.get(msg.sender_id)
        if peer and peer.public_key and NACL_AVAILABLE:
            try:
                verify_key = VerifyKey(bytes.fromhex(peer.public_key))
                if not msg.verify(verify_key):
                    return False, "INVALID_SIGNATURE"
            except ValueError as e:
                logger.debug(f"Invalid public key format: {e}")
                return False, "INVALID_SIGNATURE"
        
        # nonce記録（検証成功後）
        self.used_nonces[msg.sender_id].add(msg.nonce)
        
        # 古いnonceのクリーンアップ
        if len(self.used_nonces[msg.sender_id]) > MAX_STORED_NONCES:
            # 単純に半分削除
            nonces = list(self.used_nonces[msg.sender_id])
            self.used_nonces[msg.sender_id] = set(nonces[MAX_STORED_NONCES//2:])
        
        return True, None
    
    # === サーバー管理 ===
    
    async def start(self) -> None:
        """サーバー起動"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        logger.info(f"PeerServiceV01 started on {self.host}:{self.port}")
    
    async def stop(self) -> None:
        """サーバー停止"""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("PeerServiceV01 stopped")
    
    # === ユーティリティ ===
    
    def get_stats(self) -> dict:
        """統計情報取得"""
        return {
            **self.stats,
            "peers": {k: v.to_dict() for k, v in self.peers.items()}
        }


# === サンプル実行 ===

async def main():
    """サンプル実行"""
    if not NACL_AVAILABLE:
        print("PyNaCl is required. Install with: pip install pynacl")
        return
    
    # エンティティAのキー生成
    signing_key_a = SigningKey.generate()
    public_key_a = signing_key_a.verify_key.encode().hex()
    
    # エンティティBのキー生成
    signing_key_b = SigningKey.generate()
    public_key_b = signing_key_b.verify_key.encode().hex()
    
    # サービス初期化
    service_a = PeerServiceV01(
        entity_id="entity_a",
        signing_key=signing_key_a,
        port=8001
    )
    
    service_b = PeerServiceV01(
        entity_id="entity_b",
        signing_key=signing_key_b,
        port=8002
    )
    
    # ピア登録（相互に）
    service_a.register_peer(
        "entity_b",
        public_key_hex=public_key_b,
        endpoint="http://localhost:8002"
    )
    
    service_b.register_peer(
        "entity_a",
        public_key_hex=public_key_a,
        endpoint="http://localhost:8001"
    )
    
    # ハンドラ登録（B側）
    async def handle_delegate(msg: Message) -> Optional[Message]:
        payload = msg.get_payload_data()
        print(f"[B] Received task: {payload}")
        
        # 結果を返信
        await service_b.send_result(
            peer_id="entity_a",
            task_id=payload.get("task_id"),
            status="completed",
            result="Task processed successfully",
            duration_sec=5
        )
        return None
    
    async def handle_result(msg: Message) -> Optional[Message]:
        payload = msg.get_payload_data()
        print(f"[A] Received result: {payload}")
        return None
    
    service_b.register_handler("delegate", handle_delegate)
    service_a.register_handler("result", handle_result)
    
    # サーバー起動
    await service_a.start()
    await service_b.start()
    
    print("\n=== Servers started ===")
    print(f"Entity A: http://localhost:8001")
    print(f"Entity B: http://localhost:8002")
    
    # テスト: ping
    print("\n--- Test: ping ---")
    success = await service_a.ping("entity_b")
    print(f"Ping result: {'OK' if success else 'FAILED'}")
    
    # テスト: task delegation
    print("\n--- Test: task delegation ---")
    success = await service_a.delegate_task(
        peer_id="entity_b",
        task_id="task_001",
        task_type="test_task",
        description="Test task for v0.1 protocol",
        priority="normal"
    )
    print(f"Delegate result: {'OK' if success else 'FAILED'}")
    
    # 統計表示
    await asyncio.sleep(1)
    print("\n--- Stats ---")
    print(f"Entity A: {service_a.get_stats()}")
    print(f"Entity B: {service_b.get_stats()}")
    
    # クリーンアップ
    await asyncio.sleep(2)
    await service_a.stop()
    await service_b.stop()
    print("\n=== Servers stopped ===")


if __name__ == "__main__":
    asyncio.run(main())
