#!/usr/bin/env python3
"""
Moltbook Integration Module
AIエージェント専用ソーシャルネットワーク Moltbook との連携モジュール

Features:
- Moltbook APIクライアント
- PeerServiceとの統合
- メッセージハンドラ提供
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import aiohttp

# ロガー設定
logger = logging.getLogger(__name__)


class MoltbookError(Exception):
    """Moltbook APIエラー基底クラス"""
    pass


class AuthenticationError(MoltbookError):
    """認証エラー"""
    pass


class RateLimitError(MoltbookError):
    """レート制限エラー"""
    pass


class NotFoundError(MoltbookError):
    """リソース未発見エラー"""
    pass


class ServerError(MoltbookError):
    """サーバーエラー"""
    pass


@dataclass
class MoltbookPost:
    """Moltbook投稿データ"""
    id: str
    agent_id: str
    content: str
    submolt: Optional[str]
    created_at: datetime
    reply_to: Optional[str] = None
    likes: int = 0
    replies: int = 0


@dataclass
class MoltbookMessage:
    """Moltbook DMデータ"""
    id: str
    from_agent_id: str
    to_agent_id: str
    content: str
    created_at: datetime
    read: bool = False


@dataclass
class IdentityToken:
    """Moltbook Identity Token"""
    token: str
    expires_at: datetime
    
    def is_valid(self) -> bool:
        """トークンが有効かチェック(有効期限1時間)"""
        return datetime.now(timezone.utc) < self.expires_at


class ExponentialBackoff:
    """指数バックオフによるリトライ制御"""
    
    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        max_retries: int = 5,
        exponent: float = 2.0
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.exponent = exponent
        self._attempt = 0
    
    def next_delay(self) -> float:
        """次の遅延時間を計算"""
        if self._attempt >= self.max_retries:
            raise MoltbookError(f"Max retries ({self.max_retries}) exceeded")
        
        delay = min(
            self.initial_delay * (self.exponent ** self._attempt),
            self.max_delay
        )
        self._attempt += 1
        return delay
    
    def reset(self):
        """リセット"""
        self._attempt = 0
    
    @property
    def exhausted(self) -> bool:
        """リトライ回数を使い果たしたか"""
        return self._attempt >= self.max_retries


class MoltbookAgentClient:
    """Moltbook APIクライアント
    
    AIエージェントがMoltbookと通信するためのクライアント.
    投稿,返信,DM,フィード取得などの機能を提供.
    
    Note: Also available as MoltbookClient for backward compatibility.
    """
    
    Example:
        client = MoltbookAgentClient(api_key="xxx", agent_id="agent_123")
        await client.authenticate(x_verification_code="code")
        post = await client.create_post("Hello Moltbook!", submolt="ai_agents")
    """
    
    def __init__(
        self,
        api_key: str,
        agent_id: str,
        base_url: str = "https://api.moltbook.ai/v1",
        timeout: float = 30.0
    ):
        """Initialize Moltbook client.
        
        Args:
            api_key: Moltbook APIキー
            agent_id: このエージェントの一意ID
            base_url: APIベースURL
            timeout: リクエストタイムアウト(秒)
        """
        self.api_key = api_key
        self.agent_id = agent_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._auth_token: Optional[str] = None
        self._verified = False
        self._backoff = ExponentialBackoff()
        
        # Identity Token 管理
        self._identity_token: Optional[IdentityToken] = None
        self._identity_base_url: str = "https://moltbook.com/api/v1"
        
        # メッセージハンドラコールバック
        self._message_handlers: List[Callable[[Dict[str, Any]], None]] = []
        self._mention_handlers: List[Callable[[MoltbookPost], None]] = []
        self._dm_handlers: List[Callable[[MoltbookMessage], None]] = []
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTPセッションを取得(必要に応じて作成)"""
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Agent-ID": self.agent_id,
                "User-Agent": f"MoltbookAgentClient/1.0 (Agent: {self.agent_id})"
            }
            if self._auth_token:
                headers["X-Auth-Token"] = self._auth_token
            
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session
    
    async def _recreate_session(self):
        """認証トークン変更時にセッションを再作成"""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """APIリクエストを実行(リトライ付き)
        
        Args:
            method: HTTPメソッド
            endpoint: APIエンドポイント(/v1以降)
            **kwargs: aiohttpに渡す追加引数
            
        Returns:
            APIレスポンスのJSON
            
        Raises:
            MoltbookError: APIエラー発生時
        """
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        session = await self._get_session()
        
        last_error: Optional[Exception] = None
        
        while not self._backoff.exhausted:
            try:
                async with session.request(method, url, **kwargs) as response:
                    if response.status == 429:
                        # レート制限 - Retry-Afterヘッダーに従う
                        try:
                            retry_after = int(response.headers.get("Retry-After", 60))
                        except (ValueError, TypeError):
                            retry_after = 60
                        logger.warning(f"Rate limited. Waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        # バックオフはリセットせず,Retry-Afterのみ使用
                        continue
                    
                    if response.status == 401:
                        raise AuthenticationError("Authentication failed")
                    
                    if response.status == 404:
                        raise NotFoundError(f"Resource not found: {endpoint}")
                    
                    if response.status >= 500:
                        raise ServerError(f"Server error: {response.status}")
                    
                    response.raise_for_status()
                    
                    # 成功 - バックオフをリセット
                    self._backoff.reset()
                    
                    if response.status == 204:
                        return {}
                    
                    return await response.json()
                    
            except (ServerError, aiohttp.ClientError) as e:
                last_error = e
                delay = self._backoff.next_delay()
                logger.warning(f"Request failed: {e}. Retrying in {delay}s")
                await asyncio.sleep(delay)
            except (AuthenticationError, NotFoundError):
                raise
        
        # リトライ回数使い果たし
        error_msg = str(last_error) if last_error else "Unknown error"
        raise MoltbookError(f"Request failed after retries: {error_msg}")
    
    async def authenticate(self, x_verification_code: str) -> bool:
        """X(Twitter)認証コードで検証
        
        Args:
            x_verification_code: Xアカウント検証用コード
            
        Returns:
            認証成功時True
            
        Raises:
            AuthenticationError: 認証失敗時
        """
        response = await self._request(
            "POST",
            "/auth/verify",
            json={
                "x_verification_code": x_verification_code,
                "agent_id": self.agent_id
                # api_keyはヘッダーに含まれているためボディから削除
            }
        )
        
        self._auth_token = response.get("auth_token")
        self._verified = response.get("verified", False)
        
        # auth_tokenが変更されたらセッションを再作成
        if self._auth_token:
            await self._recreate_session()
        
        if not self._verified:
            raise AuthenticationError("Verification failed")
        
        logger.info(f"Agent {self.agent_id} authenticated successfully")
        return True
    
    def _parse_datetime(self, iso_string: str) -> datetime:
        """ISO形式の日時文字列をパース(Python 3.7互換)"""
        # Python 3.7ではZサフィックスに対応していないため置換
        if iso_string.endswith('Z'):
            iso_string = iso_string.replace('Z', '+00:00')
        return datetime.fromisoformat(iso_string)
    
    async def create_post(
        self,
        content: str,
        submolt: Optional[str] = None
    ) -> MoltbookPost:
        """投稿を作成
        
        Args:
            content: 投稿内容
            submolt: 投稿先submolt(省略時は一般フィード)
            
        Returns:
            作成された投稿
        """
        if not self._verified:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        
        payload = {
            "content": content,
            "agent_id": self.agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if submolt:
            payload["submolt"] = submolt
        
        response = await self._request("POST", "/posts", json=payload)
        
        return MoltbookPost(
            id=response["id"],
            agent_id=response["agent_id"],
            content=response["content"],
            submolt=response.get("submolt"),
            created_at=self._parse_datetime(response["created_at"]),
            likes=response.get("likes", 0),
            replies=response.get("replies", 0)
        )
    
    async def reply_to(
        self,
        post_id: str,
        content: str
    ) -> MoltbookPost:
        """投稿に返信
        
        Args:
            post_id: 返信先投稿ID
            content: 返信内容
            
        Returns:
            作成された返信投稿
        """
        if not self._verified:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        
        payload = {
            "content": content,
            "agent_id": self.agent_id,
            "reply_to": post_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        response = await self._request("POST", "/posts", json=payload)
        
        return MoltbookPost(
            id=response["id"],
            agent_id=response["agent_id"],
            content=response["content"],
            submolt=response.get("submolt"),
            created_at=self._parse_datetime(response["created_at"]),
            reply_to=post_id,
            likes=response.get("likes", 0),
            replies=response.get("replies", 0)
        )
    
    async def get_feed(
        self,
        submolt: Optional[str] = None,
        limit: int = 20,
        before_id: Optional[str] = None
    ) -> List[MoltbookPost]:
        """フィードを取得
        
        Args:
            submolt: 特定のsubmoltのフィード(Noneで一般フィード)
            limit: 取得件数(最大100)
            before_id: このIDより前の投稿を取得(ページネーション)
            
        Returns:
            投稿リスト
        """
        params = {"limit": min(limit, 100)}
        if submolt:
            params["submolt"] = submolt
        if before_id:
            params["before_id"] = before_id
        
        response = await self._request("GET", "/feed", params=params)
        
        posts = []
        for post_data in response.get("posts", []):
            posts.append(MoltbookPost(
                id=post_data["id"],
                agent_id=post_data["agent_id"],
                content=post_data["content"],
                submolt=post_data.get("submolt"),
                created_at=self._parse_datetime(post_data["created_at"]),
                reply_to=post_data.get("reply_to"),
                likes=post_data.get("likes", 0),
                replies=post_data.get("replies", 0)
            ))
        
        return posts
    
    async def join_submolt(self, name: str) -> bool:
        """submoltコミュニティに参加
        
        Args:
            name: submolt名
            
        Returns:
            参加成功時True
        """
        if not self._verified:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        
        await self._request(
            "POST",
            f"/submolts/{name}/join",
            json={"agent_id": self.agent_id}
        )
        
        logger.info(f"Joined submolt: {name}")
        return True
    
    async def leave_submolt(self, name: str) -> bool:
        """submoltコミュニティから離脱
        
        Args:
            name: submolt名
            
        Returns:
            離脱成功時True
        """
        if not self._verified:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        
        await self._request(
            "POST",
            f"/submolts/{name}/leave",
            json={"agent_id": self.agent_id}
        )
        
        logger.info(f"Left submolt: {name}")
        return True
    
    async def send_direct_message(
        self,
        agent_id: str,
        content: str
    ) -> MoltbookMessage:
        """DMを送信
        
        Args:
            agent_id: 送信先エージェントID
            content: メッセージ内容
            
        Returns:
            送信されたメッセージ
        """
        if not self._verified:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        
        payload = {
            "to_agent_id": agent_id,
            "content": content,
            "from_agent_id": self.agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        response = await self._request("POST", "/messages", json=payload)
        
        # APIレスポンスの値を使用
        return MoltbookMessage(
            id=response["id"],
            from_agent_id=response.get("from_agent_id", self.agent_id),
            to_agent_id=response.get("to_agent_id", agent_id),
            content=response.get("content", content),
            created_at=self._parse_datetime(response["created_at"]),
            read=response.get("read", False)
        )
    
    async def get_direct_messages(
        self,
        limit: int = 20,
        unread_only: bool = False
    ) -> List[MoltbookMessage]:
        """DMを取得
        
        Args:
            limit: 取得件数
            unread_only: 未読のみ取得
            
        Returns:
            メッセージリスト
        """
        params = {"limit": min(limit, 100)}
        if unread_only:
            params["unread_only"] = "true"
        
        response = await self._request("GET", "/messages", params=params)
        
        messages = []
        for msg_data in response.get("messages", []):
            messages.append(MoltbookMessage(
                id=msg_data["id"],
                from_agent_id=msg_data["from_agent_id"],
                to_agent_id=msg_data["to_agent_id"],
                content=msg_data["content"],
                created_at=self._parse_datetime(msg_data["created_at"]),
                read=msg_data.get("read", False)
            ))
        
        return messages
    
    async def mark_message_read(self, message_id: str) -> bool:
        """メッセージを既読にする
        
        Args:
            message_id: メッセージID
            
        Returns:
            成功時True
        """
        await self._request("POST", f"/messages/{message_id}/read")
        return True
    
    # ========== PeerService統合機能 ==========
    
    def on_message(self, handler: Callable[[Dict[str, Any]], None]):
        """メッセージハンドラを登録
        
        Args:
            handler: メッセージを受信した時に呼ばれるコールバック
        """
        self._message_handlers.append(handler)
    
    def on_mention(self, handler: Callable[[MoltbookPost], None]):
        """メンションハンドラを登録
        
        Args:
            handler: メンションを受信した時に呼ばれるコールバック
        """
        self._mention_handlers.append(handler)
    
    def on_direct_message(self, handler: Callable[[MoltbookMessage], None]):
        """DMハンドラを登録
        
        Args:
            handler: DMを受信した時に呼ばれるコールバック
        """
        self._dm_handlers.append(handler)
    
    async def process_incoming_message(self, message: Dict[str, Any]):
        """受信メッセージを処理
        
        登録されたハンドラにメッセージを配信します.
        
        Args:
            message: 受信メッセージ
        """
        msg_type = message.get("type")
        
        if msg_type == "mention":
            post = MoltbookPost(
                id=message["post_id"],
                agent_id=message["from_agent_id"],
                content=message["content"],
                submolt=message.get("submolt"),
                created_at=self._parse_datetime(message["timestamp"])
            )
            for handler in self._mention_handlers:
                try:
                    handler(post)
                except Exception as e:
                    logger.error(f"Mention handler error: {e}")
        
        elif msg_type == "direct_message":
            dm = MoltbookMessage(
                id=message["message_id"],
                from_agent_id=message["from_agent_id"],
                to_agent_id=self.agent_id,
                content=message["content"],
                created_at=self._parse_datetime(message["timestamp"])
            )
            for handler in self._dm_handlers:
                try:
                    handler(dm)
                except Exception as e:
                    logger.error(f"DM handler error: {e}")
        
        # 全メッセージハンドラにも配信
        for handler in self._message_handlers:
            try:
                handler(message)
            except Exception as e:
                logger.error(f"Message handler error: {e}")
    
    # ========== Identity Token 認証機能 ==========
    
    async def generate_identity_token(self) -> Optional[IdentityToken]:
        """Identity Tokenを生成
        
        API KeyからIdentity Tokenを生成します.
        生成されたトークンは1時間有効です.
        
        Returns:
            IdentityTokenまたはNone(APIキーがない場合)
        """
        if not self.api_key:
            logger.error("Cannot generate token: API key not available")
            return None
        
        url = f"{self._identity_base_url}/agents/me/identity-token"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            session = await self._get_session()
            async with session.post(url, headers=headers) as response:
                if response.status == 429:
                    # レート制限エラー
                    try:
                        retry_after = int(response.headers.get("Retry-After", 60))
                    except (ValueError, TypeError):
                        retry_after = 60
                    logger.warning(f"Rate limited. Waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    return None
                
                if response.status == 200:
                    data = await response.json()
                    token = data.get("token")
                    # 有効期限は1時間
                    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                    self._identity_token = IdentityToken(token=token, expires_at=expires_at)
                    logger.info("Generated new identity token")
                    return self._identity_token
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to generate token: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error generating identity token: {e}")
            return None
    
    async def verify_identity_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Identity Tokenを検証
        
        Args:
            token: 検証するIdentity Token
            
        Returns:
            Agent情報の辞書またはNone(無効なトークンの場合)
            辞書には以下のキーが含まれます:
            - id: Agent ID
            - name: Agent名
            - description: 説明
            - karma: Karmaポイント
            - verified: 認証済みか
            - created_at: 作成日時
            - follower_count: フォロワー数
            - post_count: 投稿数
            - comment_count: コメント数
        """
        url = f"{self._identity_base_url}/agents/verify-identity"
        headers = {
            "X-Moltbook-Identity": token,
            "Content-Type": "application/json"
        }
        
        try:
            session = await self._get_session()
            async with session.post(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Identity verified for agent: {data.get('name', 'unknown')}")
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"Token verification failed: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error verifying identity token: {e}")
            return None
    
    async def get_valid_identity_token(self) -> Optional[str]:
        """有効なIdentity Tokenを取得(キャッシュ対応)
        
        キャッシュされたトークンが有効な場合はそれを返し,
        無効または存在しない場合は新しいトークンを生成します.
        
        Returns:
            有効なIdentity Token文字列またはNone
        """
        if self._identity_token and self._identity_token.is_valid():
            logger.debug("Using cached identity token")
            return self._identity_token.token
        
        # 新しいトークンを生成
        logger.debug("Generating new identity token")
        new_token = await self.generate_identity_token()
        return new_token.token if new_token else None
    
    async def close(self):
        """クライアントをクローズ"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        logger.info("MoltbookAgentClient closed")
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


class MoltbookPeerBridge:
    """PeerServiceとMoltbookのブリッジ
    
    PeerServiceからMoltbookへのメッセージ中継を実現.
    
    Example:
        bridge = MoltbookPeerBridge(peer_service, moltbook_client)
        await bridge.start()
    """
    
    def __init__(
        self,
        peer_service: Any,  # PeerService型(循環インポート回避のためAny)
        moltbook_client: MoltbookAgentClient,
        forward_submolt: Optional[str] = None
    ):
        """Initialize bridge.
        
        Args:
            peer_service: PeerServiceインスタンス
            moltbook_client: MoltbookAgentClientインスタンス
            forward_submolt: PeerServiceメッセージを転送するsubmolt
        """
        self.peer_service = peer_service
        self.moltbook = moltbook_client
        self.forward_submolt = forward_submolt
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._poll_interval = 30.0  # ポーリング間隔(秒)
    
    async def start(self):
        """ブリッジを開始"""
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("MoltbookPeerBridge started")
    
    async def stop(self):
        """ブリッジを停止"""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("MoltbookPeerBridge stopped")
    
    async def _poll_loop(self):
        """Moltbookをポーリングして新着をチェック"""
        while self._running:
            try:
                # DMをチェック
                messages = await self.moltbook.get_direct_messages(
                    limit=10,
                    unread_only=True
                )
                for msg in messages:
                    # PeerService形式に変換して転送
                    peer_message = {
                        "type": "moltbook_dm",
                        "from": msg.from_agent_id,
                        "to": self.moltbook.agent_id,
                        "payload": {
                            "content": msg.content,
                            "moltbook_message_id": msg.id
                        },
                        "timestamp": msg.created_at.isoformat()
                    }
                    await self._forward_to_peers(peer_message)
                    await self.moltbook.mark_message_read(msg.id)
                
                await asyncio.sleep(self._poll_interval)
                
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
                await asyncio.sleep(self._poll_interval)
    
    async def _forward_to_peers(self, message: Dict[str, Any]):
        """PeerService経由で他のピアに転送"""
        try:
            if hasattr(self.peer_service, 'send_message'):
                await self.peer_service.send_message(
                    target_peer="broadcast",  # または特定のピア
                    message=message
                )
        except Exception as e:
            logger.error(f"Failed to forward to peers: {e}")
    
    async def post_to_moltbook(
        self,
        peer_message: Dict[str, Any],
        format_template: Optional[str] = None
    ) -> Optional[MoltbookPost]:
        """PeerServiceメッセージをMoltbookに投稿
        
        Args:
            peer_message: PeerServiceからのメッセージ
            format_template: 投稿フォーマット(Noneでデフォルト)
            
        Returns:
            作成された投稿(Noneの場合は投稿されなかった)
        """
        if not self.forward_submolt:
            return None
        
        try:
            if format_template:
                content = format_template.format(**peer_message)
            else:
                content = self._default_format(peer_message)
            
            post = await self.moltbook.create_post(
                content=content,
                submolt=self.forward_submolt
            )
            logger.info(f"Posted to Moltbook: {post.id}")
            return post
            
        except Exception as e:
            logger.error(f"Failed to post to Moltbook: {e}")
            return None
    
    def _default_format(self, message: Dict[str, Any]) -> str:
        """デフォルトの投稿フォーマット"""
        msg_type = message.get("type", "unknown")
        from_peer = message.get("from", "unknown")
        payload = message.get("payload", {})
        
        return f"📡 Peer message from {from_peer}\nType: {msg_type}\n{json.dumps(payload, indent=2)[:200]}"


# 簡易ファクトリ関数
def create_moltbook_agent_client(
    api_key: Optional[str] = None,
    agent_id: Optional[str] = None,
    **kwargs
) -> MoltbookAgentClient:
    """MoltbookAgentClientを作成(環境変数からも読み込み)
    
    Args:
        api_key: APIキー(NoneでMOLTBOOK_API_KEY環境変数)
        agent_id: エージェントID(NoneでMOLTBOOK_AGENT_ID環境変数)
        **kwargs: MoltbookAgentClientに渡す追加引数
        
    Returns:
        MoltbookAgentClientインスタンス
    """
    import os
    
    api_key = api_key or os.getenv("MOLTBOOK_API_KEY")
    agent_id = agent_id or os.getenv("MOLTBOOK_AGENT_ID")
    
    if not api_key:
        raise ValueError("API key required (param or MOLTBOOK_API_KEY env var)")
    if not agent_id:
        raise ValueError("Agent ID required (param or MOLTBOOK_AGENT_ID env var)")
    
    return MoltbookAgentClient(api_key=api_key, agent_id=agent_id, **kwargs)


# Backward compatibility alias
MoltbookClient = MoltbookAgentClient
