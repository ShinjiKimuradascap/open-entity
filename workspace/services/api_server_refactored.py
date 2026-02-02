#!/usr/bin/env python3
"""
AI Agent API Server v0.6.0 - Refactored
モジュール化されたAPI Server実装

アーキテクチャ:
- ルーターベースのエンドポイント分割
- 依存性注入パターン
- ミドルウェアによる横断的関心事の分離
- 設定の外部化
"""

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header, Request, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============== 設定管理 ==============

class APIConfig(BaseModel):
    """API設定"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    version: str = "0.6.0"
    
    # セキュリティ設定
    jwt_secret: str = Field(default_factory=lambda: os.urandom(32).hex())
    jwt_algorithm: str = "HS256"
    jwt_expiration: int = 3600
    rate_limit: int = 100
    
    # CORS設定
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True
    
    # 圧縮設定
    gzip_min_length: int = 1000
    gzip_level: int = 6
    
    class Config:
        env_prefix = "API_"


# ============== モデル定義 ==============

class HealthResponse(BaseModel):
    """ヘルスチェックレスポンス"""
    status: str
    version: str
    timestamp: str
    uptime_seconds: float
    components: Dict[str, str]


class ErrorResponse(BaseModel):
    """エラーレスポンス"""
    error: str
    message: str
    timestamp: str
    request_id: Optional[str] = None


class PaginationParams(BaseModel):
    """ページネーションパラメータ"""
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


# ============== 依存性注入 ==============

class ServiceContainer:
    """サービスコンテナ（依存性注入用）"""
    
    def __init__(self):
        self.config: Optional[APIConfig] = None
        self.token_economy: Optional[Any] = None
        self.peer_service: Optional[Any] = None
        self.registry: Optional[Any] = None
        self._initialized = False
    
    async def initialize(self, config: APIConfig) -> None:
        """サービスを初期化"""
        if self._initialized:
            return
        
        self.config = config
        
        # Token Economy初期化（遅延ロード）
        try:
            from services.token_system import TokenEconomy
            self.token_economy = TokenEconomy()
            logger.info("TokenEconomy initialized")
        except Exception as e:
            logger.warning(f"TokenEconomy not available: {e}")
        
        # Peer Service初期化
        try:
            from services.peer_service import PeerService
            self.peer_service = PeerService()
            logger.info("PeerService initialized")
        except Exception as e:
            logger.warning(f"PeerService not available: {e}")
        
        # Registry初期化
        try:
            from services.registry import ServiceRegistry
            self.registry = ServiceRegistry()
            logger.info("ServiceRegistry initialized")
        except Exception as e:
            logger.warning(f"ServiceRegistry not available: {e}")
        
        self._initialized = True
    
    async def shutdown(self) -> None:
        """サービスをシャットダウン"""
        logger.info("Shutting down services...")
        self._initialized = False


# グローバルサービスコンテナ
_container = ServiceContainer()


def get_container() -> ServiceContainer:
    """サービスコンテナを取得"""
    return _container


# ============== 認証・認可 ==============

security = HTTPBearer()


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    JWTトークンを検証
    
    Args:
        credentials: Authorizationヘッダー
    
    Returns:
        デコードされたトークンペイロード
    
    Raises:
        HTTPException: 認証失敗時
    """
    import jwt
    
    token = credentials.credentials
    config = _container.config
    
    try:
        payload = jwt.decode(
            token,
            config.jwt_secret,
            algorithms=[config.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


# ============== ミドルウェア ==============

class RequestLoggingMiddleware:
    """リクエストログミドルウェア"""
    
    async def __call__(self, request: Request, call_next: Callable):
        start_time = time.time()
        
        # リクエストログ
        logger.info(
            f"Request: {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )
        
        response = await call_next(request)
        
        # レスポンスログ
        process_time = time.time() - start_time
        logger.info(
            f"Response: {response.status_code} "
            f"({process_time:.3f}s)"
        )
        
        response.headers["X-Process-Time"] = str(process_time)
        return response


class RateLimitMiddleware:
    """レート制限ミドルウェア（簡易実装）"""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self._requests: Dict[str, List[float]] = {}
    
    async def __call__(self, request: Request, call_next: Callable):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # クライアントのリクエスト履歴を更新
        if client_ip not in self._requests:
            self._requests[client_ip] = []
        
        # 1分前のリクエストを削除
        self._requests[client_ip] = [
            t for t in self._requests[client_ip]
            if now - t < 60
        ]
        
        # レート制限チェック
        if len(self._requests[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "Rate limit exceeded"}
            )
        
        self._requests[client_ip].append(now)
        return await call_next(request)


class ErrorHandlingMiddleware:
    """エラーハンドリングミドルウェア"""
    
    async def __call__(self, request: Request, call_next: Callable):
        try:
            return await call_next(request)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Unhandled exception")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error="Internal server error",
                    message=str(e),
                    timestamp=datetime.now(timezone.utc).isoformat()
                ).dict()
            )


# ============== ルーター ==============

from fastapi import APIRouter

health_router = APIRouter(prefix="/health", tags=["health"])
economy_router = APIRouter(prefix="/economy", tags=["economy"])
peer_router = APIRouter(prefix="/peer", tags=["peer"])
registry_router = APIRouter(prefix="/registry", tags=["registry"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


# Health エンドポイント
@health_router.get("", response_model=HealthResponse)
async def health_check():
    """ヘルスチェック"""
    return HealthResponse(
        status="healthy",
        version=_container.config.version if _container.config else "unknown",
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=time.time() - _start_time,
        components={
            "token_economy": "available" if _container.token_economy else "unavailable",
            "peer_service": "available" if _container.peer_service else "unavailable",
            "registry": "available" if _container.registry else "unavailable"
        }
    )


@health_router.get("/ready")
async def readiness_check():
    """準備状態チェック"""
    if not _container._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )
    return {"ready": True}


# Economy エンドポイント
class BalanceResponse(BaseModel):
    entity_id: str
    balance: float
    currency: str = "AIC"
    timestamp: str


@economy_router.get("/balance/{entity_id}", response_model=BalanceResponse)
async def get_balance(
    entity_id: str,
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """ウォレット残高を取得"""
    if not _container.token_economy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token economy not available"
        )
    
    wallet = _container.token_economy.get_wallet(entity_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet not found for entity: {entity_id}"
        )
    
    return BalanceResponse(
        entity_id=entity_id,
        balance=wallet.get_balance(),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


class TransferRequest(BaseModel):
    from_entity: str
    to_entity: str
    amount: float = Field(..., gt=0)
    description: Optional[str] = None
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        return v


@economy_router.post("/transfer")
async def transfer_tokens(
    request: TransferRequest,
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """トークンを送金"""
    if not _container.token_economy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token economy not available"
        )
    
    # 残高チェック
    from_wallet = _container.token_economy.get_wallet(request.from_entity)
    if not from_wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source wallet not found: {request.from_entity}"
        )
    
    if from_wallet.get_balance() < request.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient balance"
        )
    
    # 送金実行
    success = _container.token_economy.transfer(
        from_entity=request.from_entity,
        to_entity=request.to_entity,
        amount=request.amount,
        description=request.description
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transfer failed"
        )
    
    return {
        "success": True,
        "from_entity": request.from_entity,
        "to_entity": request.to_entity,
        "amount": request.amount,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Peer エンドポイント
@peer_router.get("/peers")
async def list_peers(
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """ピアリストを取得"""
    if not _container.peer_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Peer service not available"
        )
    
    # 実装はpeer_serviceのメソッドに依存
    return {"peers": []}


@peer_router.post("/message")
async def send_message(
    request: Dict[str, Any],
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """ピアにメッセージを送信"""
    if not _container.peer_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Peer service not available"
        )
    
    return {"sent": True, "timestamp": datetime.now(timezone.utc).isoformat()}


# Registry エンドポイント
@registry_router.get("/services")
async def list_services(
    pagination: PaginationParams = Depends(),
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """サービス一覧を取得"""
    if not _container.registry:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registry not available"
        )
    
    return {
        "services": [],
        "page": pagination.page,
        "limit": pagination.limit
    }


# Admin エンドポイント
@admin_router.get("/metrics")
async def get_metrics(
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """システムメトリクスを取得"""
    # Admin権限チェック
    if token_payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime": time.time() - _start_time,
        "memory": {},  # psutil等で実装可能
        "requests_per_minute": 0
    }


@admin_router.post("/reload")
async def reload_config(
    token_payload: Dict[str, Any] = Depends(verify_token)
):
    """設定を再読み込み"""
    if token_payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    logger.info("Configuration reload requested")
    return {"reloaded": True}


# ============== アプリケーション構築 ==============

_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションライフスパン管理"""
    # 起動時
    logger.info("Starting API Server...")
    
    config = APIConfig()
    await _container.initialize(config)
    
    logger.info(f"API Server v{config.version} started on {config.host}:{config.port}")
    
    yield
    
    # シャットダウン時
    logger.info("Shutting down API Server...")
    await _container.shutdown()


def create_app(config: Optional[APIConfig] = None) -> FastAPI:
    """
    FastAPIアプリケーションを作成
    
    Args:
        config: API設定（省略時はデフォルト値）
    
    Returns:
        FastAPIアプリケーション
    """
    if config is None:
        config = APIConfig()
    
    app = FastAPI(
        title="AI Agent API",
        description="AI Collaboration Platform API",
        version=config.version,
        lifespan=lifespan,
        docs_url="/docs" if config.debug else None,
        redoc_url="/redoc" if config.debug else None
    )
    
    # CORSミドルウェア
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=config.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"]
    )
    
    # GZip圧縮
    app.add_middleware(
        GZipMiddleware,
        minimum_size=config.gzip_min_length,
        compresslevel=config.gzip_level
    )
    
    # カスタムミドルウェア
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=config.rate_limit)
    app.add_middleware(ErrorHandlingMiddleware)
    
    # ルーター登録
    app.include_router(health_router)
    app.include_router(economy_router)
    app.include_router(peer_router)
    app.include_router(registry_router)
    app.include_router(admin_router)
    
    return app


# ============== 実行エントリポイント ==============

if __name__ == "__main__":
    import uvicorn
    
    config = APIConfig()
    
    # 環境変数から設定を読み込み
    if os.getenv("API_DEBUG"):
        config.debug = os.getenv("API_DEBUG").lower() == "true"
    if os.getenv("API_PORT"):
        config.port = int(os.getenv("API_PORT"))
    
    app = create_app(config)
    
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info"
    )
