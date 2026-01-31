#!/usr/bin/env python3
"""
Moltbook Client
Moltbook APIとの連携クライアント

機能:
- Identity Tokenの生成と検証
- Agentプロフィールの取得
- Moltbookへの投稿・コメント
- ハートビートによる定期チェック

APIドキュメント: https://moltbook.com
"""

import asyncio
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional, Dict, Any, Callable, Type, Union

import aiohttp
from aiohttp import ClientTimeout

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Moltbook API エンドポイント
MOLTBOOK_BASE_URL = "https://moltbook.com"
API_VERSION = "v1"


@dataclass
class MoltbookAgent:
    """Moltbook Agentプロフィール"""
    id: str
    name: str
    description: str
    karma: int
    avatar_url: Optional[str]
    verified: bool
    created_at: datetime
    follower_count: int
    post_count: int
    comment_count: int
    owner_x_handle: Optional[str]
    owner_x_name: Optional[str]
    owner_x_verified: bool
    owner_x_follower_count: int


@dataclass
class IdentityToken:
    """Moltbook Identity Token"""
    token: str
    expires_at: datetime
    
    def is_valid(self) -> bool:
        """トークンが有効かチェック（有効期限1時間）"""
        return datetime.now(timezone.utc) < self.expires_at


@dataclass
class RateLimitInfo:
    """レート制限情報"""
    limit: int
    remaining: int
    reset_at: datetime
    retry_after: Optional[int] = None
    
    def is_exceeded(self) -> bool:
        """レート制限を超過したかチェック"""
        return self.remaining <= 0
    
    def wait_time(self) -> float:
        """次のリクエストまでの待機時間（秒）"""
        if self.retry_after:
            return float(self.retry_after)
        now = datetime.now(timezone.utc)
        if now < self.reset_at:
            return (self.reset_at - now).total_seconds()
        return 0.0


class RetryConfig:
    """リトライ設定"""
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        retry_on_status: Optional[set] = None
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retry_on_status = retry_on_status or {429, 500, 502, 503, 504}


class RetryableError(Exception):
    """リトライ可能なエラー"""
    def __init__(self, message: str, status_code: Optional[int] = None, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.status_code = status_code
        self.original_error = original_error


class NonRetryableError(Exception):
    """リトライしないエラー"""
    def __init__(self, message: str, status_code: Optional[int] = None, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.status_code = status_code
        self.original_error = original_error


def retry_with_backoff(config: Optional[RetryConfig] = None):
    """指数バックオフ付きリトライデコレータ
    
    Args:
        config: リトライ設定（省略時はデフォルト値を使用）
    
    使用例:
        @retry_with_backoff(RetryConfig(max_retries=5))
        async def fetch_data(self):
            ...
    """
    cfg = config or RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error = None
            
            for attempt in range(cfg.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except NonRetryableError as e:
                    # リトライしないエラーは即座に再送出
                    logger.warning(f"Non-retryable error in {func.__name__}: {e}")
                    raise
                    
                except RetryableError as e:
                    last_error = e
                    
                    if attempt >= cfg.max_retries:
                        # 最大リトライ回数に達した
                        logger.error(f"Max retries ({cfg.max_retries}) exceeded for {func.__name__}")
                        raise
                    
                    # 待機時間を計算（指数バックオフ + ジッタ）
                    delay = min(
                        cfg.base_delay * (cfg.exponential_base ** attempt),
                        cfg.max_delay
                    )
                    # ジッタを追加（0-20%のランダム性）
                    jitter = delay * 0.2 * random.random()
                    wait_time = delay + jitter
                    
                    logger.warning(
                        f"Retryable error in {func.__name__} "
                        f"(attempt {attempt + 1}/{cfg.max_retries + 1}): {e}. "
                        f"Waiting {wait_time:.2f}s before retry..."
                    )
                    await asyncio.sleep(wait_time)
                    
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    # 接続エラー・タイムアウトはリトライ可能
                    last_error = e
                    
                    if attempt >= cfg.max_retries:
                        logger.error(f"Max retries ({cfg.max_retries}) exceeded for {func.__name__}: {e}")
                        raise
                    
                    delay = min(
                        cfg.base_delay * (cfg.exponential_base ** attempt),
                        cfg.max_delay
                    )
                    jitter = delay * 0.2 * random.random()
                    wait_time = delay + jitter
                    
                    logger.warning(
                        f"Connection error in {func.__name__} "
                        f"(attempt {attempt + 1}/{cfg.max_retries + 1}): {e}. "
                        f"Waiting {wait_time:.2f}s before retry..."
                    )
                    await asyncio.sleep(wait_time)
            
            # すべてのリトライが失敗した場合
            if last_error:
                raise last_error
            return None
            
        return wrapper
    return decorator


def should_retry(status_code: int) -> bool:
    """ステータスコードに基づいてリトライすべきか判定"""
    # 429 (レート制限) と 5xx はリトライ対象
    if status_code == 429:
        return True
    if 500 <= status_code < 600:
        return True
    return False


def classify_error(status_code: int, message: str = "") -> Union[Type[RetryableError], Type[NonRetryableError]]:
    """エラーを分類してリトライ可能か判定"""
    # 認証エラー (401) はリトライしない
    if status_code == 401:
        return NonRetryableError
    
    # クライアントエラー (400-499、429を除く) はリトライしない
    if 400 <= status_code < 500 and status_code != 429:
        return NonRetryableError
    
    # レート制限 (429) とサーバーエラー (5xx) はリトライ可能
    if status_code == 429 or status_code >= 500:
        return RetryableError
    
    # その他のエラーはデフォルトでリトライしない
    return NonRetryableError


class MoltbookClient:
    """Moltbook APIクライアント
    
    AIエージェントがMoltbookに参加・参加するためのクライアント。
    Identity Token認証方式に対応。
    
    レート制限:
    - 投稿: 30分に1回
    - コメント: 1時間に50回
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        encryption_key: Optional[bytes] = None,
        rate_limit_handler: Optional[Callable[[RateLimitInfo], None]] = None,
        retry_config: Optional[RetryConfig] = None
    ):
        """MoltbookClientを初期化
        
        Args:
            api_key: Moltbook API Key（省略時は環境変数から読み込み）
            encryption_key: APIキー暗号化用のキー（省略時は平文保存）
            rate_limit_handler: レート制限時のコールバック関数
            retry_config: リトライ設定（省略時はデフォルト値）
        """
        raw_api_key = api_key or os.getenv("MOLTBOOK_API_KEY")
        self._encryption_key = encryption_key
        self._encrypted_api_key: Optional[bytes] = None
        self._rate_limit_handler = rate_limit_handler
        self._last_rate_limit: Optional[RateLimitInfo] = None
        self._retry_config = retry_config or RetryConfig()
        
        # APIキーを暗号化して保存
        if raw_api_key and encryption_key:
            self._encrypt_api_key(raw_api_key)
        else:
            self.api_key = raw_api_key
            
        self.base_url = f"{MOLTBOOK_BASE_URL}/api/{API_VERSION}"
        self._identity_token: Optional[IdentityToken] = None
        self._session: Optional[aiohttp.ClientSession] = None
        
        # レート制限管理
        self._last_post_time: Optional[datetime] = None
        self._comment_count: int = 0
        self._comment_window_start: Optional[datetime] = None
        
        if not raw_api_key:
            logger.warning("MOLTBOOK_API_KEY not set. Client will operate in read-only mode.")
    
    def _encrypt_api_key(self, api_key: str) -> None:
        """APIキーを暗号化して保存"""
        if not self._encryption_key:
            self.api_key = api_key
            return
        
        try:
            # Fernet暗号化を使用
            from cryptography.fernet import Fernet
            f = Fernet(self._encryption_key)
            self._encrypted_api_key = f.encrypt(api_key.encode())
            self.api_key = None  # 平文は保持しない
            logger.debug("API key encrypted successfully")
        except ImportError:
            logger.warning("cryptography not installed. API key will be stored in plaintext.")
            self.api_key = api_key
        except Exception as e:
            logger.error(f"Failed to encrypt API key: {e}")
            self.api_key = api_key
    
    def _decrypt_api_key(self) -> Optional[str]:
        """APIキーを復号化して取得"""
        if self.api_key:
            return self.api_key
        
        if not self._encrypted_api_key or not self._encryption_key:
            return None
        
        try:
            from cryptography.fernet import Fernet
            f = Fernet(self._encryption_key)
            return f.decrypt(self._encrypted_api_key).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")
            return None
    
    def _get_api_key(self) -> Optional[str]:
        """APIキーを取得（復号化済み）"""
        return self._decrypt_api_key() or self.api_key
    
    def _parse_rate_limit_headers(self, headers: Dict[str, str]) -> RateLimitInfo:
        """レスポンスヘッダーからレート制限情報を抽出"""
        try:
            limit = int(headers.get("X-RateLimit-Limit", "0"))
            remaining = int(headers.get("X-RateLimit-Remaining", "0"))
            reset_timestamp = int(headers.get("X-RateLimit-Reset", "0"))
            retry_after = headers.get("Retry-After")
            
            reset_at = datetime.fromtimestamp(reset_timestamp) if reset_timestamp else datetime.now(timezone.utc)
            
            return RateLimitInfo(
                limit=limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=int(retry_after) if retry_after else None
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse rate limit headers: {e}")
            return RateLimitInfo(limit=0, remaining=0, reset_at=datetime.now(timezone.utc))
    
    async def _handle_rate_limit(self, rate_limit: RateLimitInfo) -> None:
        """レート制限の処理"""
        self._last_rate_limit = rate_limit
        
        if rate_limit.is_exceeded():
            wait_time = rate_limit.wait_time()
            logger.warning(f"Rate limit exceeded. Waiting {wait_time:.1f} seconds...")
            
            if self._rate_limit_handler:
                self._rate_limit_handler(rate_limit)
            else:
                await asyncio.sleep(wait_time)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTPセッションを取得（必要に応じて作成）"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """セッションを閉じる"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        expect_json: bool = True
    ) -> Optional[Union[Dict[str, Any], str]]:
        """リトライ付きHTTPリクエスト
        
        Args:
            method: HTTPメソッド (GET, POST, etc.)
            url: リクエストURL
            headers: リクエストヘッダー
            json_data: JSONボディ
            params: クエリパラメータ
            expect_json: JSONレスポンスを期待するか
            
        Returns:
            レスポンスデータ（JSONまたはテキスト）またはNone（エラー時）
            
        Raises:
            NonRetryableError: リトライしないエラー（4xxクライアントエラー等）
            RetryableError: リトライ可能なエラー（5xxサーバーエラー等）
        """
        last_error = None
        
        for attempt in range(self._retry_config.max_retries + 1):
            try:
                session = await self._get_session()
                
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=params
                ) as response:
                    # レート制限ヘッダーの解析
                    if "X-RateLimit-Limit" in response.headers:
                        rate_limit = self._parse_rate_limit_headers(dict(response.headers))
                        self._last_rate_limit = rate_limit
                    
                    # ステータスコードに基づいてエラー分類
                    if response.status == 429:
                        # レート制限 - リトライ可能だが待機が必要
                        rate_limit = self._parse_rate_limit_headers(dict(response.headers))
                        wait_time = rate_limit.wait_time()
                        
                        if attempt < self._retry_config.max_retries:
                            logger.warning(f"Rate limit hit. Waiting {wait_time:.1f}s before retry...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise RetryableError(
                                "Rate limit exceeded after all retries",
                                status_code=429
                            )
                    
                    elif response.status == 401:
                        # 認証エラー - リトライしない
                        error_text = await response.text()
                        raise NonRetryableError(
                            f"Authentication failed: {error_text}",
                            status_code=401
                        )
                    
                    elif 400 <= response.status < 500:
                        # クライアントエラー - リトライしない
                        error_text = await response.text()
                        raise NonRetryableError(
                            f"Client error {response.status}: {error_text}",
                            status_code=response.status
                        )
                    
                    elif 500 <= response.status < 600:
                        # サーバーエラー - リトライ可能
                        error_text = await response.text()
                        raise RetryableError(
                            f"Server error {response.status}: {error_text}",
                            status_code=response.status
                        )
                    
                    # 成功レスポンス
                    if response.status in (200, 201):
                        if expect_json:
                            return await response.json()
                        else:
                            return await response.text()
                    else:
                        # その他のステータス
                        error_text = await response.text()
                        raise NonRetryableError(
                            f"Unexpected status {response.status}: {error_text}",
                            status_code=response.status
                        )
                        
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # 接続エラー・タイムアウトはリトライ可能
                last_error = e
                
                if attempt >= self._retry_config.max_retries:
                    raise RetryableError(
                        f"Connection error after {self._retry_config.max_retries} retries: {e}",
                        original_error=e
                    )
                
                # 指数バックオフ計算
                delay = min(
                    self._retry_config.base_delay * (self._retry_config.exponential_base ** attempt),
                    self._retry_config.max_delay
                )
                jitter = delay * 0.2 * random.random()
                wait_time = delay + jitter
                
                logger.warning(
                    f"Connection error (attempt {attempt + 1}/{self._retry_config.max_retries + 1}): {e}. "
                    f"Waiting {wait_time:.2f}s before retry..."
                )
                await asyncio.sleep(wait_time)
                
            except (RetryableError, NonRetryableError):
                raise
            except Exception as e:
                # その他の予期しないエラー
                last_error = e
                if attempt >= self._retry_config.max_retries:
                    raise NonRetryableError(
                        f"Unexpected error after {self._retry_config.max_retries} retries: {e}",
                        original_error=e
                    )
                logger.warning(f"Unexpected error (attempt {attempt + 1}): {e}. Retrying...")
                await asyncio.sleep(self._retry_config.base_delay)
        
        # すべてのリトライが失敗
        if last_error:
            raise RetryableError(f"All retries exhausted: {last_error}", original_error=last_error)
        return None
    
    @retry_with_backoff()
    async def generate_identity_token(self) -> Optional[IdentityToken]:
        """Identity Tokenを生成
        
        Returns:
            IdentityTokenまたはNone（APIキーがない場合）
        """
        api_key = self._get_api_key()
        if not api_key:
            logger.error("Cannot generate token: API key not available")
            return None
        
        url = f"{self.base_url}/agents/me/identity-token"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            data = await self._request_with_retry("POST", url, headers=headers)
            if data:
                token = data.get("token")
                # 有効期限は1時間
                expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                self._identity_token = IdentityToken(token=token, expires_at=expires_at)
                logger.info("Generated new identity token")
                return self._identity_token
            return None
                    
        except (RetryableError, NonRetryableError) as e:
            logger.error(f"Error generating identity token: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating identity token: {e}")
            return None
    
    async def get_valid_token(self) -> Optional[str]:
        """有効なトークンを取得（必要に応じて再生成）"""
        if self._identity_token and self._identity_token.is_valid():
            return self._identity_token.token
        
        # 新しいトークンを生成
        new_token = await self.generate_identity_token()
        return new_token.token if new_token else None
    
    @retry_with_backoff()
    async def verify_identity(self, token: str) -> Optional[MoltbookAgent]:
        """Identity Tokenを検証してAgent情報を取得
        
        Args:
            token: 検証するIdentity Token
            
        Returns:
            MoltbookAgentまたはNone（無効なトークンの場合）
        """
        url = f"{self.base_url}/agents/verify-identity"
        headers = {
            "X-Moltbook-Identity": token,
            "Content-Type": "application/json"
        }
        
        try:
            data = await self._request_with_retry("POST", url, headers=headers)
            if data:
                return self._parse_agent_profile(data)
            return None
                    
        except NonRetryableError as e:
            # 認証エラー等はログ出力してNoneを返す
            logger.error(f"Token verification failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Error verifying identity: {e}")
            return None
    
    def _parse_agent_profile(self, data: Dict[str, Any]) -> MoltbookAgent:
        """APIレスポンスからMoltbookAgentを作成"""
        owner = data.get("owner", {})
        stats = data.get("stats", {})
        
        return MoltbookAgent(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            karma=data.get("karma", 0),
            avatar_url=data.get("avatar_url"),
            verified=data.get("verified", False),
            created_at=datetime.fromisoformat(data.get("created_at", "").replace("Z", "+00:00")),
            follower_count=data.get("follower_count", 0),
            post_count=stats.get("posts", 0),
            comment_count=stats.get("comments", 0),
            owner_x_handle=owner.get("x_handle"),
            owner_x_name=owner.get("x_name"),
            owner_x_verified=owner.get("x_verified", False),
            owner_x_follower_count=owner.get("x_follower_count", 0)
        )
    
    def get_auth_documentation_url(self, app_name: str, endpoint: str, header: str = "X-Moltbook-Identity") -> str:
        """認証説明ドキュメントのURLを生成
        
        Args:
            app_name: アプリ名
            endpoint: APIエンドポイントURL
            header: カスタムヘッダー名（デフォルト: X-Moltbook-Identity）
            
        Returns:
            ドキュメントURL
        """
        return f"https://moltbook.com/auth.md?app={app_name}&endpoint={endpoint}&header={header}"
    
    async def heartbeat(self) -> Dict[str, Any]:
        """ハートビートを送信して接続確認
        
        Returns:
            ステータス情報の辞書
        """
        status = {
            "connected": False,
            "token_valid": False,
            "agent": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # トークンを確認
        token = await self.get_valid_token()
        if token:
            status["token_valid"] = True
            # 自分のプロフィールを取得して確認
            agent = await self.verify_identity(token)
            if agent:
                status["connected"] = True
                status["agent"] = {
                    "id": agent.id,
                    "name": agent.name,
                    "karma": agent.karma,
                    "verified": agent.verified
                }
        
        return status
    
    @retry_with_backoff()
    async def create_post(self, content: str, visibility: str = "public") -> Optional[Dict[str, Any]]:
        """Moltbookに投稿を作成
        
        レート制限: 30分に1回
        
        Args:
            content: 投稿内容
            visibility: 公開範囲 ("public" or "private")
            
        Returns:
            作成された投稿情報またはNone（レート制限・認証エラー時）
        """
        # レート制限チェック（クライアント側）
        if self._last_post_time:
            time_since_last = datetime.now(timezone.utc) - self._last_post_time
            if time_since_last < timedelta(minutes=30):
                wait_minutes = 30 - (time_since_last.total_seconds() / 60)
                logger.warning(f"Post rate limit exceeded. Wait {wait_minutes:.1f} minutes.")
                return None
        
        # トークン取得
        token = await self.get_valid_token()
        if not token:
            logger.error("Cannot create post: No valid token")
            return None
        
        url = f"{self.base_url}/posts"
        headers = {
            "X-Moltbook-Identity": token,
            "Content-Type": "application/json"
        }
        body = {
            "content": content,
            "visibility": visibility
        }
        
        try:
            data = await self._request_with_retry("POST", url, headers=headers, json_data=body)
            if data:
                self._last_post_time = datetime.now(timezone.utc)
                logger.info(f"Post created successfully: {data.get('id')}")
                return data
            return None
                    
        except Exception as e:
            logger.error(f"Error creating post: {e}")
            return None
    
    async def create_comment(self, post_id: str, content: str) -> Optional[Dict[str, Any]]:
        """投稿にコメントを追加
        
        レート制限: 1時間に50回
        
        Args:
            post_id: コメントする投稿のID
            content: コメント内容
            
        Returns:
            作成されたコメント情報またはNone（レート制限・認証エラー時）
        """
        now = datetime.now(timezone.utc)
        
        # コメントウィンドウのリセット（1時間経過）
        if self._comment_window_start:
            if now - self._comment_window_start >= timedelta(hours=1):
                self._comment_count = 0
                self._comment_window_start = now
        else:
            self._comment_window_start = now
        
        # レート制限チェック
        if self._comment_count >= 50:
            reset_time = self._comment_window_start + timedelta(hours=1)
            wait_minutes = (reset_time - now).total_seconds() / 60
            logger.warning(f"Comment rate limit exceeded. Wait {wait_minutes:.1f} minutes.")
            return None
        
        # トークン取得
        token = await self.get_valid_token()
        if not token:
            logger.error("Cannot create comment: No valid token")
            return None
        
        url = f"{self.base_url}/posts/{post_id}/comments"
        headers = {
            "X-Moltbook-Identity": token,
            "Content-Type": "application/json"
        }
        body = {"content": content}
        
        try:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=body) as response:
                if response.status == 201:
                    data = await response.json()
                    self._comment_count += 1
                    logger.info(f"Comment created successfully: {data.get('id')}")
                    return data
                elif response.status == 429:
                    logger.error("Comment rate limit exceeded (server side)")
                    return None
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create comment: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error creating comment: {e}")
            return None
    
    async def get_timeline(self, limit: int = 20, cursor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """タイムラインを取得
        
        Args:
            limit: 取得する投稿数（最大50）
            cursor: ページネーション用カーソル
            
        Returns:
            タイムラインデータまたはNone（エラー時）
        """
        # トークン取得
        token = await self.get_valid_token()
        if not token:
            logger.error("Cannot get timeline: No valid token")
            return None
        
        url = f"{self.base_url}/timeline"
        headers = {"X-Moltbook-Identity": token}
        params = {"limit": min(limit, 50)}
        if cursor:
            params["cursor"] = cursor
        
        try:
            session = await self._get_session()
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Timeline retrieved: {len(data.get('posts', []))} posts")
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to get timeline: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting timeline: {e}")
            return None
    
    async def search_agents(self, query: str, limit: int = 10) -> Optional[Dict[str, Any]]:
        """エージェントを検索
        
        Args:
            query: 検索クエリ
            limit: 取得する件数（最大20）
            
        Returns:
            検索結果またはNone（エラー時）
        """
        # トークン取得（認証が必要な場合のみ）
        token = await self.get_valid_token()
        headers = {}
        if token:
            headers["X-Moltbook-Identity"] = token
        
        url = f"{self.base_url}/agents/search"
        params = {
            "q": query,
            "limit": min(limit, 20)
        }
        
        try:
            session = await self._get_session()
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Agent search completed: {len(data.get('agents', []))} results")
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to search agents: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error searching agents: {e}")
            return None


# グローバルインスタンス
_client: Optional[MoltbookClient] = None


def init_client(api_key: Optional[str] = None) -> MoltbookClient:
    """クライアントを初期化
    
    Args:
        api_key: Moltbook API Key
        
    Returns:
        初期化されたMoltbookClientインスタンス
    """
    global _client
    _client = MoltbookClient(api_key)
    return _client


def get_client() -> Optional[MoltbookClient]:
    """クライアントインスタンスを取得
    
    Returns:
        現在のMoltbookClientインスタンス（未初期化の場合はNone）
    """
    return _client


async def main():
    """テスト実行"""
    import os
    
    # 環境変数からAPIキーを取得
    api_key = os.getenv("MOLTBOOK_API_KEY")
    
    if not api_key:
        print("MOLTBOOK_API_KEY environment variable not set")
        print("Set it to test Moltbook integration")
        return
    
    # クライアント初期化
    client = init_client(api_key)
    
    try:
        # ハートビートテスト
        status = await client.heartbeat()
        print(f"Heartbeat status: {status}")
        
        # トークン生成テスト
        token = await client.generate_identity_token()
        if token:
            print(f"Token generated, expires at: {token.expires_at}")
            
            # トークン検証テスト
            agent = await client.verify_identity(token.token)
            if agent:
                print(f"Agent verified: {agent.name} (Karma: {agent.karma})")
            else:
                print("Token verification failed")
        else:
            print("Token generation failed")
            
    finally:
        await client.close()


if __name__ == "__main__":
    import os
    asyncio.run(main())
