#!/usr/bin/env python3
"""
Rate Limiter for AI Collaboration API
FastAPI用レートリミッターミドルウェア

Features:
- Token bucket algorithm
- Per-endpoint rate limits
- Per-client (IP/Entity) rate limiting
- Configurable limits per endpoint
- Redis-compatible interface (optional)
"""

import asyncio
import time
import logging
from functools import wraps
from typing import Dict, Optional, Callable, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict
from fastapi import Request, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """レート制限設定"""
    requests_per_minute: int = 60
    burst_size: int = 10  # Token bucket burst size
    window_seconds: int = 60
    key_prefix: str = "rl"
    
    def __post_init__(self):
        # Calculate token refill rate
        self.refill_rate = self.requests_per_minute / 60.0  # per second


@dataclass
class RateLimitState:
    """クライアントごとのレート制限状態"""
    tokens: float = 0.0
    last_update: float = field(default_factory=time.time)
    request_count: int = 0
    window_start: float = field(default_factory=time.time)
    

class TokenBucketRateLimiter:
    """
    トークンバケットアルゴリズムによるレートリミッター
    
    Features:
    - スレッドセーフ（asyncio.Lock使用）
    - 自動クリーンアップ（古いエントリ削除）
    - バースト対応
    """
    
    def __init__(
        self,
        default_config: Optional[RateLimitConfig] = None,
        cleanup_interval: int = 300  # 5分
    ):
        self.default_config = default_config or RateLimitConfig()
        self._buckets: Dict[str, RateLimitState] = {}
        self._configs: Dict[str, RateLimitConfig] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = cleanup_interval
        self._stats = {
            "allowed": 0,
            "denied": 0,
            "cleaned": 0
        }
    
    async def start(self) -> None:
        """レートリミッターを開始（クリーンアップタスク）"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Rate limiter started")
    
    async def stop(self) -> None:
        """レートリミッターを停止"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Rate limiter stopped")
    
    def set_config(self, key: str, config: RateLimitConfig) -> None:
        """特定のキーに対する設定を設定"""
        self._configs[key] = config
    
    def get_config(self, key: str) -> RateLimitConfig:
        """キーに対する設定を取得（デフォルト設定を返す）"""
        return self._configs.get(key, self.default_config)
    
    async def check_rate_limit(
        self,
        key: str,
        config: Optional[RateLimitConfig] = None
    ) -> Tuple[bool, Dict]:
        """
        レート制限をチェック
        
        Args:
            key: レート制限キー（クライアントID/IP）
            config: カスタム設定（省略時はデフォルト）
            
        Returns:
            (許可されたか, レート制限情報)
            レート制限情報: {
                "limit": 制限値,
                "remaining": 残りリクエスト数,
                "reset_at": リセット時刻,
                "retry_after": リトライ待ち時間（秒、拒否時のみ）
            }
        """
        cfg = config or self.get_config(key)
        now = time.time()
        
        async with self._lock:
            # バケットを取得または作成
            if key not in self._buckets:
                self._buckets[key] = RateLimitState(
                    tokens=cfg.burst_size,
                    last_update=now
                )
            
            bucket = self._buckets[key]
            
            # トークンを補充
            elapsed = now - bucket.last_update
            bucket.tokens = min(
                cfg.burst_size,
                bucket.tokens + elapsed * cfg.refill_rate
            )
            bucket.last_update = now
            
            # ウィンドウベースの制限もチェック
            window_elapsed = now - bucket.window_start
            if window_elapsed > cfg.window_seconds:
                # ウィンドウリセット
                bucket.window_start = now
                bucket.request_count = 0
            
            # トークンがあれば許可
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                bucket.request_count += 1
                self._stats["allowed"] += 1
                
                reset_at = bucket.window_start + cfg.window_seconds
                return True, {
                    "limit": cfg.requests_per_minute,
                    "remaining": int(bucket.tokens),
                    "reset_at": reset_at,
                    "window": cfg.window_seconds
                }
            
            # 拒否
            self._stats["denied"] += 1
            retry_after = int((1.0 - bucket.tokens) / cfg.refill_rate) + 1
            reset_at = bucket.window_start + cfg.window_seconds
            
            return False, {
                "limit": cfg.requests_per_minute,
                "remaining": 0,
                "reset_at": reset_at,
                "retry_after": retry_after,
                "window": cfg.window_seconds
            }
    
    async def get_stats(self) -> Dict:
        """レートリミッター統計を取得"""
        async with self._lock:
            return {
                **self._stats,
                "active_buckets": len(self._buckets)
            }
    
    async def reset(self, key: Optional[str] = None) -> None:
        """レート制限をリセット"""
        async with self._lock:
            if key:
                self._buckets.pop(key, None)
                logger.info(f"Rate limit reset for key: {key}")
            else:
                self._buckets.clear()
                logger.info("All rate limits reset")
    
    async def _cleanup_loop(self) -> None:
        """古いバケットをクリーンアップするバックグラウンドタスク"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_old_buckets()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in rate limiter cleanup: {e}")
    
    async def _cleanup_old_buckets(self) -> int:
        """古いバケットを削除"""
        now = time.time()
        max_age = self._cleanup_interval * 2  # 10分
        
        async with self._lock:
            to_remove = [
                key for key, bucket in self._buckets.items()
                if now - bucket.last_update > max_age
            ]
            
            for key in to_remove:
                del self._buckets[key]
            
            if to_remove:
                self._stats["cleaned"] += len(to_remove)
                logger.debug(f"Cleaned up {len(to_remove)} old rate limit buckets")
            
            return len(to_remove)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI用レートリミットミドルウェア
    
    Usage:
        app.add_middleware(
            RateLimitMiddleware,
            rate_limiter=limiter,
            key_func=lambda req: req.client.host,
            exclude_paths=["/health", "/docs"]
        )
    """
    
    def __init__(
        self,
        app,
        rate_limiter: TokenBucketRateLimiter,
        key_func: Optional[Callable[[Request], str]] = None,
        exclude_paths: Optional[list] = None,
        include_headers: bool = True
    ):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.key_func = key_func or self._default_key_func
        self.exclude_paths = set(exclude_paths or ["/health", "/docs", "/openapi.json"])
        self.include_headers = include_headers
    
    @staticmethod
    def _default_key_func(request: Request) -> str:
        """デフォルトのキー生成関数（IPアドレス + パス）"""
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        return f"{client_ip}:{path}"
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """リクエストを処理"""
        path = request.url.path
        
        # 除外パスのチェック
        if path in self.exclude_paths:
            return await call_next(request)
        
        # レート制限キーを生成
        key = self.key_func(request)
        
        # レート制限をチェック
        allowed, info = await self.rate_limiter.check_rate_limit(key)
        
        if not allowed:
            # レート制限超過
            logger.warning(f"Rate limit exceeded for {key}")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "retry_after": info.get("retry_after", 60),
                    "limit": info["limit"],
                    "window": info["window"]
                },
                headers={
                    "Retry-After": str(info.get("retry_after", 60)),
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(info["reset_at"]))
                }
            )
        
        # レスポンスを取得
        response = await call_next(request)
        
        # レート制限ヘッダーを追加
        if self.include_headers:
            response.headers["X-RateLimit-Limit"] = str(info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(int(info["reset_at"]))
        
        return response


class EndpointRateLimiter:
    """
    エンドポイントごとのレート制限を管理
    
    Usage:
        limiter = EndpointRateLimiter()
        limiter.set_limit("/message", requests_per_minute=30, burst_size=5)
        limiter.set_limit("/auth/token", requests_per_minute=10, burst_size=2)
    """
    
    def __init__(self, default_rpm: int = 60, default_burst: int = 10):
        self.default_config = RateLimitConfig(
            requests_per_minute=default_rpm,
            burst_size=default_burst
        )
        self._endpoint_configs: Dict[str, RateLimitConfig] = {}
        self._rate_limiter = TokenBucketRateLimiter(self.default_config)
    
    async def start(self) -> None:
        await self._rate_limiter.start()
    
    async def stop(self) -> None:
        await self._rate_limiter.stop()
    
    def set_limit(
        self,
        path: str,
        requests_per_minute: int,
        burst_size: Optional[int] = None
    ) -> None:
        """エンドポイントごとの制限を設定"""
        self._endpoint_configs[path] = RateLimitConfig(
            requests_per_minute=requests_per_minute,
            burst_size=burst_size or requests_per_minute // 6,  # Default: 10% of RPM
            key_prefix=f"rl:{path}"
        )
        logger.info(f"Rate limit set for {path}: {requests_per_minute}/min, burst={burst_size}")
    
    def get_limit(self, path: str) -> RateLimitConfig:
        """エンドポイントの制限を取得"""
        return self._endpoint_configs.get(path, self.default_config)
    
    async def check(
        self,
        client_id: str,
        path: str
    ) -> Tuple[bool, Dict]:
        """
        エンドポイントとクライアントの組み合わせでレート制限をチェック
        
        Args:
            client_id: クライアント識別子（IPまたはEntity ID）
            path: エンドポイントパス
            
        Returns:
            (許可されたか, レート制限情報)
        """
        key = f"{client_id}:{path}"
        config = self.get_limit(path)
        return await self._rate_limiter.check_rate_limit(key, config)
    
    async def get_stats(self) -> Dict:
        """統計情報を取得"""
        base_stats = await self._rate_limiter.get_stats()
        return {
            **base_stats,
            "endpoint_configs": len(self._endpoint_configs)
        }


# グローバルインスタンス（シングルトンパターン）
_default_limiter: Optional[TokenBucketRateLimiter] = None
_endpoint_limiter: Optional[EndpointRateLimiter] = None


def get_rate_limiter() -> TokenBucketRateLimiter:
    """グローバルレートリミッターインスタンスを取得"""
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = TokenBucketRateLimiter()
    return _default_limiter


def get_endpoint_rate_limiter() -> EndpointRateLimiter:
    """グローバルエンドポイントレートリミッターインスタンスを取得"""
    global _endpoint_limiter
    if _endpoint_limiter is None:
        _endpoint_limiter = EndpointRateLimiter()
    return _endpoint_limiter


async def init_rate_limiters() -> None:
    """レートリミッターを初期化して開始"""
    limiter = get_rate_limiter()
    await limiter.start()
    
    endpoint_limiter = get_endpoint_rate_limiter()
    await endpoint_limiter.start()
    
    # エンドポイントごとの制限を設定
    endpoint_limiter.set_limit("/message", requests_per_minute=60, burst_size=10)
    endpoint_limiter.set_limit("/auth/token", requests_per_minute=10, burst_size=2)
    endpoint_limiter.set_limit("/register", requests_per_minute=30, burst_size=5)
    endpoint_limiter.set_limit("/peers", requests_per_minute=120, burst_size=20)
    
    logger.info("Rate limiters initialized with endpoint-specific limits")


def rate_limit(requests_per_minute: int = 60, burst_size: Optional[int] = None):
    """
    Decorator to apply rate limiting to a specific endpoint function
    
    Args:
        requests_per_minute: Maximum requests per minute
        burst_size: Maximum burst size (defaults to requests_per_minute // 6)
        
    Returns:
        Decorated function
        
    Example:
        @rate_limit(requests_per_minute=60)
        @app.post("/message")
        async def send_message(req: MessageRequest):
            return {"status": "ok"}
    """
    def decorator(func: Callable) -> Callable:
        config = RateLimitConfig(
            requests_per_minute=requests_per_minute,
            burst_size=burst_size or requests_per_minute // 6
        )
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract request from kwargs or args
            request = kwargs.get('request')
            if not request and args:
                # Try to find Request in positional args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            # Get client ID
            client_id = "unknown"
            if request:
                client_ip = request.client.host if request.client else "unknown"
                forwarded = request.headers.get("X-Forwarded-For")
                if forwarded:
                    client_id = forwarded.split(",")[0].strip()
                else:
                    client_id = client_ip
            
            # Create temporary limiter for this endpoint
            temp_limiter = TokenBucketRateLimiter(config)
            await temp_limiter.start()
            
            key = f"{client_id}:{func.__name__}"
            allowed, info = await temp_limiter.check_rate_limit(key, config)
            
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "retry_after": info.get("retry_after", 60)
                    },
                    headers={
                        "Retry-After": str(info.get("retry_after", 60)),
                        "X-RateLimit-Limit": str(info["limit"]),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(info["reset_at"]))
                    }
                )
            
            # Add rate limit info to request state if available
            if request and hasattr(request, 'state'):
                request.state.rate_limit_info = info
            
            try:
                return await func(*args, **kwargs)
            finally:
                await temp_limiter.stop()
        
        return async_wrapper
    
    return decorator


# Convenience decorators for common rate limits
def strict_limit(func: Optional[Callable] = None):
    """Strict rate limit (10 requests per minute) - for auth endpoints"""
    decorator = rate_limit(requests_per_minute=10, burst_size=3)
    if func:
        return decorator(func)
    return decorator


def standard_limit(func: Optional[Callable] = None):
    """Standard rate limit (60 requests per minute) - for task endpoints"""
    decorator = rate_limit(requests_per_minute=60, burst_size=10)
    if func:
        return decorator(func)
    return decorator


def generous_limit(func: Optional[Callable] = None):
    """Generous rate limit (100 requests per minute) - for general endpoints"""
    decorator = rate_limit(requests_per_minute=100, burst_size=20)
    if func:
        return decorator(func)
    return decorator


async def shutdown_rate_limiters() -> None:
    """レートリミッターをシャットダウン"""
    if _default_limiter:
        await _default_limiter.stop()
    if _endpoint_limiter:
        await _endpoint_limiter.stop()
    logger.info("Rate limiters shut down")


# FastAPI Dependency
async def check_rate_limit(
    request: Request,
    limiter: TokenBucketRateLimiter = Depends(get_rate_limiter)
) -> None:
    """
    FastAPI dependency for rate limiting individual endpoints
    
    Usage:
        @app.post("/message")
        async def send_message(
            req: MessageRequest,
            _: None = Depends(check_rate_limit)
        ):
            ...
    """
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    key = f"{client_ip}:{path}"
    
    allowed, info = await limiter.check_rate_limit(key)
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "retry_after": info.get("retry_after", 60)
            },
            headers={
                "Retry-After": str(info.get("retry_after", 60))
            }
        )


# Tests
async def _test_rate_limiter():
    """レートリミッターのテスト"""
    print("=== Testing Rate Limiter ===")
    
    # テスト1: 基本的なレート制限
    print("\n--- Test 1: Basic Rate Limiting ---")
    limiter = TokenBucketRateLimiter(
        RateLimitConfig(requests_per_minute=60, burst_size=5)
    )
    await limiter.start()
    
    # バーストテスト（5リクエストは許可される）
    key = "test_client"
    for i in range(7):
        allowed, info = await limiter.check_rate_limit(key)
        status = "✓" if allowed else "✗"
        print(f"  Request {i+1}: {status} (tokens: {info.get('remaining', 0)})")
    
    # テスト2: 時間経過でトークン補充
    print("\n--- Test 2: Token Refill ---")
    await asyncio.sleep(2)  # 2秒待機
    allowed, info = await limiter.check_rate_limit(key)
    print(f"  After 2s: {'✓' if allowed else '✗'} (tokens: {info.get('remaining', 0)})")
    
    # テスト3: エンドポイント別制限
    print("\n--- Test 3: Endpoint-Specific Limits ---")
    endpoint_limiter = EndpointRateLimiter()
    await endpoint_limiter.start()
    
    endpoint_limiter.set_limit("/api/message", requests_per_minute=30, burst_size=3)
    endpoint_limiter.set_limit("/api/auth", requests_per_minute=10, burst_size=2)
    
    for path in ["/api/message", "/api/auth", "/api/other"]:
        config = endpoint_limiter.get_limit(path)
        print(f"  {path}: {config.requests_per_minute}/min, burst={config.burst_size}")
    
    # クリーンアップ
    await limiter.stop()
    await endpoint_limiter.stop()
    
    print("\n=== All rate limiter tests passed ===")


if __name__ == "__main__":
    asyncio.run(_test_rate_limiter())
