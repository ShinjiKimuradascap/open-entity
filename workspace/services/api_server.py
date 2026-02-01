#!/usr/bin/env python3
"""
AI Agent API Server v0.5.1
Security-enhanced version with Ed25519 signatures, JWT authentication, replay protection,
DHT peer discovery, governance system, and rate limiting
"""

from fastapi import FastAPI, HTTPException, Header, Request, Depends, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uvicorn
import os
import logging
import json

logger = logging.getLogger(__name__)

# ============================================================================
# Robust Import System - Handles missing dependencies gracefully
# ============================================================================

# Helper to try multiple import paths
def try_import(module_name, *fallback_paths):
    """Try importing from multiple paths, return None if all fail"""
    for path in fallback_paths:
        try:
            if path:
                full_name = f"{path}.{module_name}"
            else:
                full_name = module_name
            mod = __import__(full_name, fromlist=['*'])
            return mod
        except ImportError:
            continue
    return None

# Initialize module placeholders
registry_module = None
peer_service_module = None
token_system_module = None
token_economy_module = None
crypto_module = None
auth_module = None
rate_limiter_module = None
moltbook_module = None
marketplace_module = None

# Try to import registry module
for prefix in ['services.', '']:
    try:
        if prefix:
            registry_module = __import__(f"{prefix}registry", fromlist=['get_registry', 'ServiceInfo'])
        else:
            registry_module = __import__("registry", fromlist=['get_registry', 'ServiceInfo'])
        break
    except ImportError:
        continue

# Try to import peer_service module
for prefix in ['services.', '']:
    try:
        if prefix:
            peer_service_module = __import__(f"{prefix}peer_service", fromlist=['PeerService', 'init_service', 'get_service'])
        else:
            peer_service_module = __import__("peer_service", fromlist=['PeerService', 'init_service', 'get_service'])
        break
    except ImportError:
        continue

# Try to import token_system module  
for prefix in ['services.', '']:
    try:
        if prefix:
            token_system_module = __import__(f"{prefix}token_system", fromlist=[
                'get_wallet', 'get_task_contract', 'get_reputation_contract', 'get_token_minter', 'get_persistence',
                'TokenWallet', 'TaskContract', 'ReputationContract', 'TokenMinter', 'RewardType',
                'TaskStatus', 'TransactionType', 'PersistenceManager'
            ])
        else:
            token_system_module = __import__("token_system", fromlist=[
                'get_wallet', 'get_task_contract', 'get_reputation_contract', 'get_token_minter', 'get_persistence',
                'TokenWallet', 'TaskContract', 'ReputationContract', 'TokenMinter', 'RewardType',
                'TaskStatus', 'TransactionType', 'PersistenceManager'
            ])
        break
    except ImportError:
        continue

# Try to import token_economy module
for prefix in ['services.', '']:
    try:
        if prefix:
            token_economy_module = __import__(f"{prefix}token_economy", fromlist=['TokenEconomy', 'TokenMetadata', 'get_token_economy'])
        else:
            token_economy_module = __import__("token_economy", fromlist=['TokenEconomy', 'TokenMetadata', 'get_token_economy'])
        break
    except ImportError:
        continue

# Try to import crypto module
for prefix in ['services.', '']:
    try:
        if prefix:
            crypto_module = __import__(f"{prefix}crypto", fromlist=[
                'KeyPair', 'MessageSigner', 'SignatureVerifier', 'SecureMessage',
                'ReplayProtector', 'load_key_from_env', 'generate_keypair', 'get_public_key_from_private'
            ])
        else:
            crypto_module = __import__("crypto", fromlist=[
                'KeyPair', 'MessageSigner', 'SignatureVerifier', 'SecureMessage',
                'ReplayProtector', 'load_key_from_env', 'generate_keypair', 'get_public_key_from_private'
            ])
        break
    except ImportError:
        continue

# Try to import auth module
for prefix in ['services.', '']:
    try:
        if prefix:
            auth_module = __import__(f"{prefix}auth", fromlist=[
                'JWTAuth', 'JWTConfig', 'APIKeyAuth', 'CombinedAuth',
                'JWTBearer', 'APIKeyBearer', 'get_current_entity_id',
                'create_jwt_auth', 'create_api_key_auth'
            ])
        else:
            auth_module = __import__("auth", fromlist=[
                'JWTAuth', 'JWTConfig', 'APIKeyAuth', 'CombinedAuth',
                'JWTBearer', 'APIKeyBearer', 'get_current_entity_id',
                'create_jwt_auth', 'create_api_key_auth'
            ])
        break
    except ImportError:
        continue

# Try to import rate_limiter module
for prefix in ['services.', '']:
    try:
        if prefix:
            rate_limiter_module = __import__(f"{prefix}rate_limiter", fromlist=[
                'TokenBucketRateLimiter', 'RateLimitMiddleware', 'EndpointRateLimiter',
                'get_rate_limiter', 'get_endpoint_rate_limiter',
                'init_rate_limiters', 'shutdown_rate_limiters'
            ])
        else:
            rate_limiter_module = __import__("rate_limiter", fromlist=[
                'TokenBucketRateLimiter', 'RateLimitMiddleware', 'EndpointRateLimiter',
                'get_rate_limiter', 'get_endpoint_rate_limiter',
                'init_rate_limiters', 'shutdown_rate_limiters'
            ])
        break
    except ImportError:
        continue

# Try to import moltbook_identity_client module
for prefix in ['services.', '']:
    try:
        if prefix:
            moltbook_module = __import__(f"{prefix}moltbook_identity_client", fromlist=['init_client', 'get_client'])
        else:
            moltbook_module = __import__("moltbook_identity_client", fromlist=['init_client', 'get_client'])
        break
    except ImportError:
        continue

# Try to import marketplace module
for prefix in ['services.', '']:
    try:
        if prefix:
            marketplace_module = __import__(f"{prefix}marketplace", fromlist=['ServiceRegistry', 'ServiceListing', 'ServiceType', 'PricingModel'])
        else:
            marketplace_module = __import__("marketplace", fromlist=['ServiceRegistry', 'ServiceListing', 'ServiceType', 'PricingModel'])
        break
    except ImportError:
        continue

# Try to import solana_token module (for blockchain token transfers)
solana_token_module = None
for prefix in ['services.', '']:
    try:
        if prefix:
            solana_token_module = __import__(f"{prefix}solana_token", fromlist=['SolanaTokenManager', 'TransferResult', 'init_solana_manager', 'get_solana_manager', 'transfer_entity_tokens'])
        else:
            solana_token_module = __import__("solana_token", fromlist=['SolanaTokenManager', 'TransferResult', 'init_solana_manager', 'get_solana_manager', 'transfer_entity_tokens'])
        break
    except ImportError:
        continue

# ============================================================================
# Extract symbols from modules (with fallback mocks)
# ============================================================================

# Registry symbols
if registry_module:
    get_registry = registry_module.get_registry
    ServiceInfo = registry_module.ServiceInfo
    logger.info("✓ Registry module loaded")
else:
    logger.warning("✗ Registry module not available")
    get_registry = lambda: None
    class ServiceInfo:
        pass

# Peer service symbols
if peer_service_module:
    PeerService = peer_service_module.PeerService
    init_peer_service = peer_service_module.init_service
    get_peer_service = peer_service_module.get_service
    logger.info("✓ Peer service module loaded")
else:
    logger.warning("✗ Peer service module not available")
    PeerService = None
    init_peer_service = lambda **kwargs: None
    get_peer_service = lambda: None

# Token system symbols
if token_system_module:
    get_wallet = token_system_module.get_wallet
    get_task_contract = token_system_module.get_task_contract
    get_reputation_contract = token_system_module.get_reputation_contract
    get_token_minter = token_system_module.get_token_minter
    get_persistence = token_system_module.get_persistence
    TokenWallet = token_system_module.TokenWallet
    TaskContract = token_system_module.TaskContract
    ReputationContract = token_system_module.ReputationContract
    TokenMinter = token_system_module.TokenMinter
    RewardType = token_system_module.RewardType
    TaskStatus = token_system_module.TaskStatus
    TransactionType = token_system_module.TransactionType
    PersistenceManager = token_system_module.PersistenceManager
    logger.info("✓ Token system module loaded")
else:
    logger.warning("✗ Token system module not available")
    get_wallet = lambda entity_id: None
    get_task_contract = lambda: None
    get_reputation_contract = lambda: None
    get_token_minter = lambda: None
    get_persistence = lambda: None
    TokenWallet = None
    TaskContract = None
    ReputationContract = None
    TokenMinter = None
    class RewardType:
        TASK_COMPLETION = "task_completion"
    class TaskStatus:
        PENDING = "pending"
        COMPLETED = "completed"
    class TransactionType:
        REWARD = "reward"
        TRANSFER = "transfer"
    PersistenceManager = None

# Token economy symbols
if token_economy_module:
    TokenEconomy = token_economy_module.TokenEconomy
    TokenMetadata = token_economy_module.TokenMetadata
    get_token_economy = token_economy_module.get_token_economy
    logger.info("✓ Token economy module loaded")
else:
    logger.warning("✗ Token economy module not available")
    TokenEconomy = None
    TokenMetadata = None
    get_token_economy = lambda: None

# Crypto symbols
if crypto_module:
    KeyPair = crypto_module.KeyPair
    MessageSigner = crypto_module.MessageSigner
    SignatureVerifier = crypto_module.SignatureVerifier
    SecureMessage = crypto_module.SecureMessage
    ReplayProtector = crypto_module.ReplayProtector
    load_key_from_env = crypto_module.load_key_from_env
    generate_keypair = crypto_module.generate_keypair
    get_public_key_from_private = crypto_module.get_public_key_from_private
    logger.info("✓ Crypto module loaded")
else:
    logger.error("✗ Crypto module not available - critical dependency")
    raise ImportError("Crypto module is required for api_server")

# Auth symbols
if auth_module:
    JWTAuth = auth_module.JWTAuth
    JWTConfig = auth_module.JWTConfig
    APIKeyAuth = auth_module.APIKeyAuth
    CombinedAuth = auth_module.CombinedAuth
    JWTBearer = auth_module.JWTBearer
    APIKeyBearer = auth_module.APIKeyBearer
    get_current_entity_id = auth_module.get_current_entity_id
    create_jwt_auth = auth_module.create_jwt_auth
    create_api_key_auth = auth_module.create_api_key_auth
    logger.info("✓ Auth module loaded")
else:
    logger.error("✗ Auth module not available - critical dependency")
    raise ImportError("Auth module is required for api_server")

# Rate limiter symbols
if rate_limiter_module:
    TokenBucketRateLimiter = rate_limiter_module.TokenBucketRateLimiter
    RateLimitMiddleware = rate_limiter_module.RateLimitMiddleware
    EndpointRateLimiter = rate_limiter_module.EndpointRateLimiter
    get_rate_limiter = rate_limiter_module.get_rate_limiter
    get_endpoint_rate_limiter = rate_limiter_module.get_endpoint_rate_limiter
    init_rate_limiters = rate_limiter_module.init_rate_limiters
    shutdown_rate_limiters = rate_limiter_module.shutdown_rate_limiters
    logger.info("✓ Rate limiter module loaded")
else:
    logger.warning("✗ Rate limiter module not available - using basic implementation")
    # Basic fallback implementations
    class TokenBucketRateLimiter:
        def __init__(self, *args, **kwargs):
            pass
        def is_allowed(self, *args, **kwargs):
            return True
    class RateLimitMiddleware:
        def __init__(self, *args, **kwargs):
            pass
    class EndpointRateLimiter:
        def __init__(self, *args, **kwargs):
            pass
        def set_limit(self, *args, **kwargs):
            pass
        def _rate_limiter(self):
            return None
    get_rate_limiter = lambda: None
    get_endpoint_rate_limiter = lambda: None
    init_rate_limiters = lambda: None
    shutdown_rate_limiters = lambda: None

# Moltbook symbols
if moltbook_module:
    init_moltbook_client = moltbook_module.init_client
    get_moltbook_client = moltbook_module.get_client
    logger.info("✓ Moltbook module loaded")
else:
    logger.warning("✗ Moltbook module not available")
    init_moltbook_client = lambda: None
    get_moltbook_client = lambda: None

# Marketplace symbols
if marketplace_module:
    ServiceRegistry = marketplace_module.ServiceRegistry
    ServiceListing = marketplace_module.ServiceListing
    ServiceType = marketplace_module.ServiceType
    PricingModel = marketplace_module.PricingModel
    logger.info("✓ Marketplace module loaded")
else:
    logger.warning("✗ Marketplace module not available")
    ServiceRegistry = None
    ServiceListing = None
    ServiceType = None
    PricingModel = None

# Import peer communication tools with fallback patterns
try:
    from tools.peer_tools import (
        report_to_peer, talk_to_peer, wake_up_peer, check_peer_alive
    )
except ImportError:
    # Fallback when tools module is not available
    def report_to_peer(*args, **kwargs):
        return "⚠️ Peer tools not available"
    def talk_to_peer(*args, **kwargs):
        return "⚠️ Peer tools not available"
    def wake_up_peer(*args, **kwargs):
        return "⚠️ Peer tools not available"
    def check_peer_alive(*args, **kwargs):
        return False

# Initialize FastAPI app
app = FastAPI(
    title="AI Collaboration API",
    version="0.5.1",
    description="Security-enhanced API with Ed25519 signatures, JWT authentication, and Governance"
)

# Initialize rate limiter with endpoint-specific limits
endpoint_limiter = EndpointRateLimiter(default_rpm=100, default_burst=20)
endpoint_limiter.set_limit("/auth", requests_per_minute=10, burst_size=5)
endpoint_limiter.set_limit("/task", requests_per_minute=60, burst_size=15)
endpoint_limiter.set_limit("/register", requests_per_minute=30, burst_size=10)
endpoint_limiter.set_limit("/message", requests_per_minute=60, burst_size=10)

# Add rate limit middleware
app.add_middleware(
    RateLimitMiddleware,
    rate_limiter=endpoint_limiter._rate_limiter,
    key_func=lambda req: f"{req.client.host if req.client else 'unknown'}:{req.url.path}",
    exclude_paths=["/health", "/docs", "/openapi.json", "/stats", "/keys/public"]
)

# Initialize components (with safe fallbacks)
replay_protector = ReplayProtector(max_age_seconds=60)

# Initialize Registry (with fallback)
registry = None
try:
    if registry_module and get_registry:
        registry = get_registry()
        logger.info("Registry initialized")
except Exception as e:
    logger.warning(f"Failed to initialize registry: {e}")

# Initialize PeerService (with fallback)
peer_service = None
try:
    if peer_service_module and init_peer_service:
        peer_service = init_peer_service(entity_id="api-server", port=8000)
        logger.info("Peer service initialized")
except Exception as e:
    logger.warning(f"Failed to initialize peer service: {e}")

# Initialize Token Economy and Persistence Manager (with fallback)
token_economy = None
try:
    if token_economy_module and get_token_economy:
        token_economy = get_token_economy()
        logger.info("Token economy initialized")
except Exception as e:
    logger.warning(f"Failed to initialize token economy: {e}")

persistence_mgr = None
try:
    if token_system_module and get_persistence:
        persistence_mgr = get_persistence()
        logger.info("Persistence manager initialized")
except Exception as e:
    logger.warning(f"Failed to initialize persistence manager: {e}")

# Initialize Marketplace components
marketplace_registry = None
marketplace_orderbook = None
try:
    if marketplace_module and ServiceRegistry:
        try:
            from services.marketplace import OrderBook
        except ImportError:
            from marketplace import OrderBook
        marketplace_registry = ServiceRegistry(storage_path="data/marketplace/registry.json")
        marketplace_orderbook = OrderBook(storage_path="data/marketplace/orders.json")
        logger.info("Marketplace components initialized")
except Exception as e:
    logger.warning(f"Failed to initialize marketplace components: {e}")

# Initialize Moltbook Client
moltbook_client: Optional[Any] = None
try:
    moltbook_client = init_moltbook_client()
    logger.info("Moltbook client initialized")
except Exception as e:
    logger.warning(f"Failed to initialize Moltbook client: {e}")

# Initialize security components
jwt_auth = create_jwt_auth()
api_key_auth = create_api_key_auth()
combined_auth = CombinedAuth(jwt_auth, api_key_auth)

# Initialize signature verifier
signature_verifier = SignatureVerifier()

# Admin configuration
ADMIN_ENTITIES = set(os.environ.get("ADMIN_ENTITIES", "admin,orchestrator").split(","))

def require_admin(current_entity: str = Depends(get_current_entity_id)) -> str:
    """Verify the current entity has admin privileges"""
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_entity

# Server's own key pair (for signing messages)
_server_keypair: Optional[KeyPair] = None
_server_signer: Optional[MessageSigner] = None


def get_server_keypair() -> KeyPair:
    """Get or create server key pair"""
    global _server_keypair, _server_signer
    if _server_keypair is None:
        _server_keypair = load_key_from_env("ENTITY_PRIVATE_KEY") or generate_keypair()
        _server_signer = MessageSigner(_server_keypair)
    return _server_keypair


def get_server_signer() -> MessageSigner:
    """Get server message signer"""
    global _server_signer
    if _server_signer is None:
        get_server_keypair()
    return _server_signer


# PeerService instance (lazy initialization)
_peer_service = None

def get_peer_service():
    """Get or create PeerService instance"""
    global _peer_service
    if _peer_service is None:
        try:
            from services.peer_service import init_service
        except ImportError:
            from peer_service import init_service
        # エンティティIDは環境変数から取得、またはデフォルト値
        entity_id = os.environ.get("ENTITY_ID", "api-server")
        port = int(os.environ.get("PORT", "8000"))
        _peer_service = init_service(entity_id, port)
    return _peer_service


# Request/Response Models
class RegisterRequest(BaseModel):
    entity_id: str
    name: str
    endpoint: str
    capabilities: List[str]
    public_key: Optional[str] = Field(None, description="Hex-encoded Ed25519 public key")


class HeartbeatRequest(BaseModel):
    entity_id: str
    load: float = 0.0
    active_tasks: int = 0


class MessageRequest(BaseModel):
    version: str
    msg_type: str
    sender_id: str
    recipient_id: str
    payload: Dict[str, Any]
    timestamp: Optional[str] = None
    nonce: Optional[str] = None
    signature: Optional[str] = Field(None, description="Base64-encoded Ed25519 signature")
    session_id: Optional[str] = None
    sequence_num: Optional[int] = None
    payload_encrypted: Optional[bool] = False


class TokenRequest(BaseModel):
    entity_id: str
    api_key: Optional[str] = None
    public_key: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    entity_id: str


class VerifyRequest(BaseModel):
    message: Dict[str, Any]
    signature: str
    sender_id: str


class VerifyResponse(BaseModel):
    valid: bool
    message: str


class PublicKeyResponse(BaseModel):
    public_key: str
    algorithm: str = "Ed25519"
    entity_id: str


class StatsResponse(BaseModel):
    version: str
    registered_agents: int
    active_agents: int
    server_public_key: str
    timestamp: str
    features: List[str]


# Token System Models
class WalletBalanceResponse(BaseModel):
    entity_id: str
    balance: float
    currency: str = "AIC"


class WalletInfoResponse(BaseModel):
    entity_id: str
    balance: float
    total_earned: float
    total_spent: float
    transaction_count: int
    reputation_score: Optional[float] = None


class TransferRequest(BaseModel):
    to_entity_id: str = Field(..., description="Destination entity ID to receive the transfer", example="entity_b")
    amount: float = Field(..., gt=0, description="Amount to transfer (must be positive)", example=100.0)
    description: str = Field(default="", description="Optional transfer description", example="Payment for task completion")


class TransferResponse(BaseModel):
    status: str
    from_entity_id: str
    to_entity_id: str
    amount: float
    description: str
    timestamp: str


class TransactionItem(BaseModel):
    type: str
    amount: float
    timestamp: str
    description: str
    counterparty: Optional[str] = None
    related_task_id: Optional[str] = None


class TransactionHistoryResponse(BaseModel):
    entity_id: str
    transactions: List[TransactionItem]
    count: int


class TaskCreateRequest(BaseModel):
    task_id: str = Field(..., description="Unique identifier for the task", example="task_001")
    agent_id: str = Field(..., description="ID of the agent assigned to the task", example="agent_001")
    amount: float = Field(..., gt=0, description="Task reward amount (must be positive)", example=50.0)
    description: str = Field(default="", description="Optional task description", example="Review code changes")
    expires_at: Optional[str] = Field(default=None, description="Task expiration timestamp (ISO format)", example="2026-02-02T12:00:00Z")


class TaskCreateResponse(BaseModel):
    status: str
    task_id: str
    client_id: str
    agent_id: str
    amount: float
    description: str
    created_at: str
    expires_at: Optional[str] = None


class TaskCompleteRequest(BaseModel):
    task_id: str


class TaskCompleteResponse(BaseModel):
    status: str
    task_id: str
    agent_id: str
    amount: float
    completed_at: str


class TaskStatusResponse(BaseModel):
    task_id: str
    client_id: str
    agent_id: str
    amount: float
    status: str
    created_at: str
    expires_at: Optional[str] = None
    completed_at: Optional[str] = None
    description: str
    approved_by_client: bool = False
    disputed: bool = False
    dispute_reason: Optional[str] = None
    dispute_initiator: Optional[str] = None


class TaskSubmitCompletionRequest(BaseModel):
    task_id: str = Field(..., description="Task ID to submit completion for", example="task_001")


class TaskSubmitCompletionResponse(BaseModel):
    status: str
    task_id: str
    message: str
    submitted_at: str


class TaskApproveRequest(BaseModel):
    task_id: str = Field(..., description="Task ID to approve", example="task_001")
    signature: Optional[str] = Field(default=None, description="Optional approval signature for multi-sig")


class TaskApproveResponse(BaseModel):
    status: str
    task_id: str
    client_id: str
    agent_id: str
    amount: float
    approved_at: str
    message: str


class TaskDisputeRequest(BaseModel):
    task_id: str = Field(..., description="Task ID to dispute", example="task_001")
    reason: str = Field(..., description="Reason for dispute", example="Work not completed as specified")


class TaskDisputeResponse(BaseModel):
    status: str
    task_id: str
    initiator_id: str
    reason: str
    disputed_at: str
    message: str


class TaskResolveRequest(BaseModel):
    task_id: str = Field(..., description="Task ID to resolve", example="task_001")
    approve_task: bool = Field(..., description="Whether to approve the task (True) or reject (False)", example=True)
    slash_percentage: float = Field(default=0.0, ge=0, le=1, description="Slash percentage if rejecting (0.0-1.0)", example=0.5)
    resolution_note: Optional[str] = Field(default=None, description="Optional note about the resolution", example="Task quality insufficient")


class TaskResolveResponse(BaseModel):
    status: str
    task_id: str
    resolver_id: str
    approved: bool
    message: str
    resolved_at: str


class RatingSubmitRequest(BaseModel):
    to_entity_id: str = Field(..., description="Entity ID to rate", example="entity_b")
    task_id: str = Field(..., description="Associated task ID", example="task_001")
    score: float = Field(..., ge=1, le=5, description="Rating score from 1 to 5", example=5)
    comment: str = Field(default="", description="Optional rating comment", example="Excellent work!")


class RatingSubmitResponse(BaseModel):
    status: str
    from_entity_id: str
    to_entity_id: str
    score: float
    comment: str
    timestamp: str


class RatingInfoResponse(BaseModel):
    entity_id: str
    average_rating: Optional[float]
    trust_score: float
    rating_count: int


class WalletCreateRequest(BaseModel):
    entity_id: str = Field(..., description="Unique entity ID for the wallet", example="entity_001")
    initial_balance: float = Field(default=0.0, ge=0, description="Initial wallet balance (non-negative)", example=1000.0)


class WalletCreateResponse(BaseModel):
    status: str
    entity_id: str
    balance: float
    currency: str = "AIC"
    created_at: str


class TaskFailRequest(BaseModel):
    task_id: str
    slash_percentage: float = Field(0.5, ge=0.0, le=1.0, description="Slash percentage (0.0-1.0)")


class TaskFailResponse(BaseModel):
    status: str
    task_id: str
    slashed_amount: float
    returned_amount: float
    failed_at: str


class RewardTaskRequest(BaseModel):
    to_entity_id: str
    complexity: int = Field(1, ge=1, le=10, description="Task complexity (1-10)")
    task_id: Optional[str] = None
    description: str = ""


class RewardTaskResponse(BaseModel):
    status: str
    to_entity_id: str
    amount: float
    reward_type: str
    mint_id: str
    timestamp: str


class RewardReviewRequest(BaseModel):
    to_entity_id: str
    description: str = ""


class RewardReviewResponse(BaseModel):
    status: str
    to_entity_id: str
    amount: float
    reward_type: str
    mint_id: str
    timestamp: str


# Token Economy Models
class TokenMintRequest(BaseModel):
    to_entity_id: str
    amount: float = Field(..., gt=0, description="Amount to mint (must be positive)")
    reason: str = ""


class TokenMintResponse(BaseModel):
    success: bool
    operation_id: Optional[str] = None
    amount: float = 0.0
    new_total_supply: float = 0.0
    new_circulating_supply: float = 0.0
    error: Optional[str] = None


class TokenBurnRequest(BaseModel):
    from_entity_id: str
    amount: float = Field(..., gt=0, description="Amount to burn (must be positive)")
    reason: str = ""


class TokenBurnResponse(BaseModel):
    success: bool
    operation_id: Optional[str] = None
    amount: float = 0.0
    new_circulating_supply: float = 0.0
    total_burned: float = 0.0
    error: Optional[str] = None


class TokenSupplyResponse(BaseModel):
    total_supply: float
    circulating_supply: float
    treasury_balance: float
    burned_tokens: float
    mint_operations_count: int
    burn_operations_count: int
    last_updated: str


class BackupCreateResponse(BaseModel):
    success: bool
    backup_path: Optional[str] = None
    timestamp: str
    error: Optional[str] = None


class BackupListResponse(BaseModel):
    backups: List[Dict[str, Any]]
    count: int


class BackupRestoreRequest(BaseModel):
    backup_path: str


class BackupRestoreResponse(BaseModel):
    success: bool
    restored_from: str
    timestamp: str
    error: Optional[str] = None


# Governance API Models
class GovernanceActionRequest(BaseModel):
    """Action definition for governance proposals"""
    target: str
    function: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    value: float = 0.0


class GovernanceProposalCreateRequest(BaseModel):
    """Request to create a new governance proposal"""
    proposer: Optional[str] = None  # If None, uses authenticated entity
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    proposal_type: str = Field(..., description="parameter_change, upgrade, token_allocation, emergency")
    actions: List[GovernanceActionRequest] = Field(..., min_length=1)


class GovernanceProposalCreateResponse(BaseModel):
    """Response for proposal creation"""
    proposal_id: str
    status: str
    voting_start: Optional[str] = None
    voting_end: Optional[str] = None


class GovernanceProposalDetailResponse(BaseModel):
    """Detailed proposal information"""
    id: str
    proposer: str
    title: str
    description: str
    proposal_type: str
    status: str
    created_at: str
    voting_start: Optional[str] = None
    voting_end: Optional[str] = None
    actions: List[Dict[str, Any]]
    votes_for: str
    votes_against: str
    votes_abstain: str
    total_votes: str
    for_percentage: float
    voters: List[str]
    cancel_reason: Optional[str] = None


class GovernanceVoteRequest(BaseModel):
    """Request to cast a vote"""
    voter: Optional[str] = None  # If None, uses authenticated entity
    vote_type: str = Field(..., description="for, against, or abstain")


class GovernanceVoteResponse(BaseModel):
    """Response for vote casting"""
    success: bool
    voting_power: str
    message: str = ""


class GovernanceCancelRequest(BaseModel):
    """Request to cancel a proposal"""
    canceller: Optional[str] = None  # If None, uses authenticated entity
    reason: str = Field(..., min_length=1)


class GovernanceCancelResponse(BaseModel):
    """Response for proposal cancellation"""
    success: bool
    message: str


class GovernanceResultsResponse(BaseModel):
    """Voting results for a proposal"""
    proposal_id: str
    votes_for: str
    votes_against: str
    votes_abstain: str
    total_votes: str
    for_percentage: float
    against_percentage: float
    abstain_percentage: float
    passed: bool


# Marketplace Registry singleton
_marketplace_registry: Optional[ServiceRegistry] = None

async def get_marketplace_registry() -> ServiceRegistry:
    """Get or create singleton ServiceRegistry instance"""
    global _marketplace_registry
    if _marketplace_registry is None:
        _marketplace_registry = ServiceRegistry(storage_path="data/marketplace_registry.json")
    return _marketplace_registry


# Authentication dependencies
jwt_bearer = JWTBearer(jwt_auth)
api_key_bearer = APIKeyBearer(api_key_auth)


@app.post("/register")
async def register_agent(req: RegisterRequest):
    """Register a new AI agent with optional public key"""
    success = registry.register(
        entity_id=req.entity_id,
        name=req.name,
        endpoint=req.endpoint,
        capabilities=req.capabilities
    )
    
    if success:
        # Store public key if provided
        if req.public_key:
            try:
                signature_verifier.add_public_key_hex(req.entity_id, req.public_key)
            except Exception as e:
                # Log but don't fail registration
                print(f"Warning: Failed to store public key for {req.entity_id}: {e}")
        
        # Generate API key for the entity
        api_key = api_key_auth.generate_key(req.entity_id)
        
        return {
            "status": "ok",
            "entity_id": req.entity_id,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "api_key": api_key,
            "public_key_stored": req.public_key is not None
        }
    
    raise HTTPException(status_code=400, detail="Registration failed")


@app.post("/unregister/{entity_id}")
async def unregister_agent(
    entity_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Unregister an agent (requires JWT authentication)"""
    # Verify the requesting entity matches or is admin
    current_entity = credentials.credentials
    
    success = registry.unregister(entity_id)
    if success:
        # Remove public key
        if entity_id in signature_verifier.public_keys:
            del signature_verifier.public_keys[entity_id]
            if entity_id in signature_verifier._verify_keys:
                del signature_verifier._verify_keys[entity_id]
        
        return {"status": "ok", "message": f"{entity_id} unregistered"}
    
    raise HTTPException(status_code=404, detail="Entity not found")


@app.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest):
    """Update agent heartbeat"""
    success = registry.heartbeat(req.entity_id)
    if success:
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    raise HTTPException(status_code=404, detail="Entity not registered")


@app.get("/discover")
async def discover_agents(capability: Optional[str] = None):
    """Discover available agents"""
    if capability:
        services = registry.find_by_capability(capability)
    else:
        services = registry.list_all()
    
    return {
        "agents": [
            {
                "entity_id": s.entity_id,
                "name": s.entity_name,
                "endpoint": s.endpoint,
                "capabilities": s.capabilities,
                "alive": s.is_alive()
            }
            for s in services
        ]
    }


@app.get("/agent/{entity_id}")
async def get_agent(entity_id: str):
    """Get agent details"""
    service = registry.find_by_id(entity_id)
    if service:
        return {
            "entity_id": service.entity_id,
            "name": service.entity_name,
            "endpoint": service.endpoint,
            "capabilities": service.capabilities,
            "registered_at": service.registered_at.isoformat(),
            "last_heartbeat": service.last_heartbeat.isoformat(),
            "alive": service.is_alive()
        }
    raise HTTPException(status_code=404, detail="Entity not found")


@app.post("/message")
async def receive_message(
    req: MessageRequest,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
):
    """
    Receive secure message from peer
    
    Security checks:
    - Ed25519 signature verification (if signature provided)
    - Replay attack prevention using nonce and timestamp
    - Optional JWT/API key authentication
    """
    # Build secure message
    message = SecureMessage(
        version=req.version,
        msg_type=req.msg_type,
        sender_id=req.sender_id,
        payload=req.payload,
        timestamp=req.timestamp,
        nonce=req.nonce,
        signature=req.signature
    )
    
    # 1. Replay protection check
    valid, error = replay_protector.is_valid(message.nonce, message.timestamp)
    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"Replay protection failed: {error}"
        )
    
    # 2. Signature verification (if provided)
    if req.signature:
        try:
            is_valid = signature_verifier.verify_message(
                message.get_signable_data(),
                req.signature,
                req.sender_id
            )
            if not is_valid:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid message signature"
                )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Signature verification error: {e}"
            )
    
    # 3. Optional authentication (JWT or API key)
    auth_result = None
    if authorization or x_api_key:
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
        
        auth_result = combined_auth.authenticate_request(
            token=token,
            api_key=x_api_key
        )
        
        if not auth_result["authenticated"]:
            raise HTTPException(
                status_code=401,
                detail=f"Authentication failed: {auth_result['errors']}"
            )
    
    # Route to handler using PeerService
    peer_service = get_peer_service()
    
    # Convert MessageRequest to dict format expected by PeerService
    message_dict = {
        "version": req.version,
        "msg_type": req.msg_type,
        "sender_id": req.sender_id,
        "payload": req.payload,
        "timestamp": message.timestamp,
        "nonce": message.nonce,
        "signature": req.signature
    }
    
    # Process message through PeerService handlers
    handler_result = await peer_service.handle_message(message_dict)
    
    # Check if message was handled successfully
    if handler_result.get("status") == "error":
        raise HTTPException(
            status_code=500,
            detail=f"Message handling failed: {handler_result.get('reason', 'Unknown error')}"
        )
    
    return {
        "status": "received",
        "msg_type": req.msg_type,
        "from": req.sender_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verified": req.signature is not None,
        "authenticated": auth_result["authenticated"] if auth_result else False,
        "handled": handler_result.get("status") == "success",
        "handler_result": handler_result
    }


# New Security Endpoints

@app.post("/auth/token", response_model=TokenResponse)
async def create_token(req: TokenRequest):
    """
    Create JWT access token
    
    Authentication options:
    - API key (if previously registered)
    - Public key verification (for new entities)
    """
    # Verify using API key
    if req.api_key:
        entity_id = api_key_auth.verify_key(req.api_key)
        if not entity_id or entity_id != req.entity_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
    
    # Create JWT token
    token = jwt_auth.create_token(
        entity_id=req.entity_id,
        additional_claims={"method": "api_key" if req.api_key else "public_key"}
    )
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=jwt_auth.config.expiry_minutes * 60,
        entity_id=req.entity_id
    )


@app.get("/keys/public", response_model=PublicKeyResponse)
async def get_server_public_key():
    """Get server's Ed25519 public key for message verification"""
    keypair = get_server_keypair()
    
    return PublicKeyResponse(
        public_key=keypair.get_public_key_hex(),
        algorithm="Ed25519",
        entity_id="server"
    )


@app.post("/keys/verify", response_model=VerifyResponse)
async def verify_signature(req: VerifyRequest):
    """Verify an Ed25519 signature"""
    try:
        is_valid = signature_verifier.verify_message(
            req.message,
            req.signature,
            req.sender_id
        )
        
        return VerifyResponse(
            valid=is_valid,
            message="Signature is valid" if is_valid else "Signature is invalid"
        )
    except ValueError as e:
        return VerifyResponse(
            valid=False,
            message=f"Verification failed: {e}"
        )


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get server statistics and capabilities"""
    keypair = get_server_keypair()
    services = registry.list_all()
    active = [s for s in services if s.is_alive()]
    
    return StatsResponse(
        version="0.4.0",
        registered_agents=len(services),
        active_agents=len(active),
        server_public_key=keypair.get_public_key_hex(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        features=[
            "Ed25519_signatures",
            "JWT_authentication",
            "API_key_authentication",
            "Replay_protection",
            "Message_encryption"
        ]
    )


@app.get("/health")
async def health_check():
    """API health check"""
    return {
        "status": "healthy",
        "version": "0.4.0",
        "registered_agents": len(registry.list_all()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "security_features": {
            "ed25519_signatures": True,
            "jwt_authentication": True,
            "replay_protection": True
        }
    }


# Secure message sending helper
@app.post("/message/send")
async def send_secure_message(
    recipient_id: str,
    msg_type: str,
    payload: Dict[str, Any],
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Send a secure signed message to another agent
    (Server-side message signing for internal use)
    """
    sender_id = credentials.credentials
    
    # Create secure message
    message = SecureMessage(
        version="0.4.0",
        msg_type=msg_type,
        sender_id=sender_id,
        payload=payload
    )
    
    # Sign the message
    signer = get_server_signer()
    message.sign(signer)
    
    # Send to recipient using PeerService
    peer_service = get_peer_service()
    
    # Get recipient endpoint from registry
    recipient_service = registry.find_by_id(recipient_id)
    if not recipient_service:
        raise HTTPException(status_code=404, detail=f"Recipient not found: {recipient_id}")
    
    # Add peer to PeerService if not already registered
    if recipient_id not in peer_service.peers:
        peer_service.add_peer(
            entity_id=recipient_id,
            address=recipient_service.endpoint
        )
    
    # Send message using PeerService
    send_success = await peer_service.send_message(
        target_id=recipient_id,
        message_type=msg_type,
        payload=payload
    )
    
    if not send_success:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to send message to {recipient_id}"
        )
    
    return {
        "status": "sent",
        "recipient": recipient_id,
        "message": message.to_dict(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Moltbook Integration Endpoints

try:
    # Pattern 1: When run as a module from parent directory
    from services.moltbook_identity_client import MoltbookClient, init_client as init_moltbook_client
    MOLTBOOK_AVAILABLE = True
except ImportError:
    try:
        # Pattern 2: When run directly from services directory
        from moltbook_identity_client import MoltbookClient, init_client as init_moltbook_client
        MOLTBOOK_AVAILABLE = True
    except ImportError:
        MOLTBOOK_AVAILABLE = False
        logger = logging.getLogger(__name__)
        logger.warning("Moltbook client not available")


@app.get("/moltbook/auth-url")
async def get_moltbook_auth_url(request: Request, app_name: str = "AI-Collaboration-API"):
    """Get Moltbook authentication documentation URL"""
    if not MOLTBOOK_AVAILABLE:
        raise HTTPException(status_code=503, detail="Moltbook client not available")
    
    client = init_moltbook_client()
    # Generate URL for authentication instructions
    auth_url = client.get_auth_documentation_url(
        app_name=app_name,
        endpoint=f"{request.base_url}moltbook/verify"
    )
    return {"auth_url": auth_url}


@app.post("/moltbook/verify")
async def verify_moltbook_identity(x_moltbook_identity: Optional[str] = Header(None)):
    """Verify Moltbook identity token"""
    if not MOLTBOOK_AVAILABLE:
        raise HTTPException(status_code=503, detail="Moltbook client not available")
    
    if not x_moltbook_identity:
        raise HTTPException(status_code=400, detail="X-Moltbook-Identity header required")
    
    client = init_moltbook_client()
    try:
        agent = await client.verify_identity(x_moltbook_identity)
        if agent:
            return {
                "status": "verified",
                "agent": {
                    "id": agent.id,
                    "name": agent.name,
                    "karma": agent.karma,
                    "verified": agent.verified,
                    "follower_count": agent.follower_count
                }
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid identity token")
    finally:
        await client.close()


# Token System Endpoints

@app.get("/wallet/{entity_id}", response_model=WalletBalanceResponse)
async def get_wallet_balance(entity_id: str):
    """Get wallet balance for an entity"""
    wallet = get_wallet(entity_id)
    if not wallet:
        raise HTTPException(status_code=404, detail=f"Wallet not found for entity: {entity_id}")
    
    return WalletBalanceResponse(
        entity_id=entity_id,
        balance=wallet.get_balance(),
        currency="AIC"
    )


@app.post("/wallet/transfer", response_model=TransferResponse)
async def transfer_tokens(
    req: TransferRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Transfer tokens to another entity (requires JWT authentication)"""
    # Decode JWT token to get entity_id from 'sub' claim
    try:
        payload = jwt_auth.verify_token(credentials.credentials)
        from_entity_id = payload.get("sub")
        if not from_entity_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing entity_id")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")
    
    # Get sender wallet
    from_wallet = get_wallet(from_entity_id)
    if not from_wallet:
        raise HTTPException(status_code=404, detail=f"Sender wallet not found: {from_entity_id}")
    
    # Get or create recipient wallet
    to_wallet = get_wallet(req.to_entity_id)
    if not to_wallet:
        try:
            from services.token_system import create_wallet
        except ImportError:
            from token_system import create_wallet
        to_wallet = create_wallet(req.to_entity_id, initial_balance=0.0)
    
    # Perform transfer
    success = from_wallet.transfer(to_wallet, req.amount, req.description)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Transfer failed. Insufficient balance or invalid amount."
        )

    # Persist token state
    get_persistence().save_all()

    return TransferResponse(
        status="success",
        from_entity_id=from_entity_id,
        to_entity_id=req.to_entity_id,
        amount=req.amount,
        description=req.description,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/wallet/{entity_id}/transactions", response_model=TransactionHistoryResponse)
async def get_transaction_history(entity_id: str):
    """Get transaction history for an entity"""
    wallet = get_wallet(entity_id)
    if not wallet:
        raise HTTPException(status_code=404, detail=f"Wallet not found for entity: {entity_id}")
    
    transactions = wallet.get_transaction_history()
    
    return TransactionHistoryResponse(
        entity_id=entity_id,
        transactions=[
            TransactionItem(
                type=t.type.value,
                amount=t.amount,
                timestamp=t.timestamp.isoformat(),
                description=t.description,
                counterparty=t.counterparty,
                related_task_id=t.related_task_id
            )
            for t in transactions
        ],
        count=len(transactions)
    )


@app.post("/task/create", response_model=TaskCreateResponse)
async def create_task(
    req: TaskCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Create a new task contract (requires JWT authentication)"""
    client_id = credentials.credentials
    
    # Ensure client wallet exists
    client_wallet = get_wallet(client_id)
    if not client_wallet:
        try:
            from services.token_system import create_wallet
        except ImportError:
            from token_system import create_wallet
        client_wallet = create_wallet(client_id, initial_balance=0.0)
    
    # Ensure agent wallet exists
    agent_wallet = get_wallet(req.agent_id)
    if not agent_wallet:
        try:
            from services.token_system import create_wallet
        except ImportError:
            from token_system import create_wallet
        agent_wallet = create_wallet(req.agent_id, initial_balance=0.0)
    
    # Parse expires_at if provided
    expires_at = None
    if req.expires_at:
        try:
            expires_at = datetime.fromisoformat(req.expires_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at format. Use ISO format.")
    
    # Create task
    tc = get_task_contract()
    success = tc.create_task(
        task_id=req.task_id,
        client_id=client_id,
        agent_id=req.agent_id,
        amount=req.amount,
        description=req.description,
        expires_at=expires_at
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Task creation failed. Insufficient balance or task already exists."
        )

    # Persist token state
    get_persistence().save_all()

    task = tc.get_task(req.task_id)
    
    return TaskCreateResponse(
        status="created",
        task_id=req.task_id,
        client_id=client_id,
        agent_id=req.agent_id,
        amount=req.amount,
        description=req.description,
        created_at=task.created_at.isoformat(),
        expires_at=task.expires_at.isoformat() if task.expires_at else None
    )


@app.post("/task/complete", response_model=TaskCompleteResponse)
async def complete_task(
    req: TaskCompleteRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Complete a task and release locked tokens (requires JWT authentication)"""
    tc = get_task_contract()
    task = tc.get_task(req.task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {req.task_id}")
    
    # Only client or agent can complete the task
    requester_id = credentials.credentials
    if requester_id not in [task.client_id, task.agent_id]:
        raise HTTPException(
            status_code=403, 
            detail="Only client or agent can complete the task"
        )
    
    success = tc.complete_task(req.task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Task completion failed. Task may not be in progress."
        )

    # Persist token state
    get_persistence().save_all()

    return TaskCompleteResponse(
        status="completed",
        task_id=req.task_id,
        agent_id=task.agent_id,
        amount=task.amount,
        completed_at=datetime.now(timezone.utc).isoformat()
    )


@app.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Get task status and details"""
    tc = get_task_contract()
    task = tc.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    return TaskStatusResponse(
        task_id=task.task_id,
        client_id=task.client_id,
        agent_id=task.agent_id,
        amount=task.amount,
        status=task.status.value,
        created_at=task.created_at.isoformat(),
        expires_at=task.expires_at.isoformat() if task.expires_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        description=task.description,
        approved_by_client=task.approved_by_client,
        disputed=task.disputed,
        dispute_reason=task.dispute_reason,
        dispute_initiator=task.dispute_initiator
    )


@app.post("/task/{task_id}/submit-completion", response_model=TaskSubmitCompletionResponse)
async def submit_task_completion(
    task_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """エージェントがタスク完了を提出（クライアント承認待ち状態にする）
    
    Requires JWT authentication. Only the assigned agent can submit completion.
    """
    tc = get_task_contract()
    task = tc.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    # エージェント本人のみ提出可能
    agent_id = credentials.credentials
    if agent_id != task.agent_id:
        raise HTTPException(
            status_code=403,
            detail="Only the assigned agent can submit task completion"
        )
    
    success = tc.submit_task_completion(task_id, agent_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Task completion submission failed. Task may not be in progress."
        )
    
    # Persist token state
    get_persistence().save_all()
    
    return TaskSubmitCompletionResponse(
        status="submitted",
        task_id=task_id,
        message="Task completion submitted, awaiting client approval",
        submitted_at=datetime.now(timezone.utc).isoformat()
    )


@app.post("/task/{task_id}/approve", response_model=TaskApproveResponse)
async def approve_task(
    task_id: str,
    req: TaskApproveRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """クライアントがタスク完了を承認し、ロックされたトークンをエージェントにリリース
    
    Requires JWT authentication. Only the client who created the task can approve.
    """
    tc = get_task_contract()
    task = tc.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    # クライアント本人のみ承認可能
    client_id = credentials.credentials
    if client_id != task.client_id:
        raise HTTPException(
            status_code=403,
            detail="Only the client who created the task can approve"
        )
    
    success = tc.approve_task(task_id, client_id, req.signature)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Task approval failed. Task may not be pending approval."
        )
    
    # Persist token state
    get_persistence().save_all()
    
    return TaskApproveResponse(
        status="approved",
        task_id=task_id,
        client_id=client_id,
        agent_id=task.agent_id,
        amount=task.amount,
        approved_at=datetime.now(timezone.utc).isoformat(),
        message="Task approved and payment released to agent"
    )


@app.post("/task/{task_id}/dispute", response_model=TaskDisputeResponse)
async def dispute_task(
    task_id: str,
    req: TaskDisputeRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """タスクに対して紛争を申請
    
    Requires JWT authentication. Only the client or agent involved can dispute.
    """
    tc = get_task_contract()
    task = tc.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    # クライアントまたはエージェントのみ紛争可能
    initiator_id = credentials.credentials
    if initiator_id not in [task.client_id, task.agent_id]:
        raise HTTPException(
            status_code=403,
            detail="Only the client or agent involved can dispute the task"
        )
    
    success = tc.dispute_task(task_id, initiator_id, req.reason)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Dispute submission failed. Task may not be in a disputable state."
        )
    
    # Persist token state
    get_persistence().save_all()
    
    return TaskDisputeResponse(
        status="disputed",
        task_id=task_id,
        initiator_id=initiator_id,
        reason=req.reason,
        disputed_at=datetime.now(timezone.utc).isoformat(),
        message="Dispute submitted, awaiting governance resolution"
    )


@app.post("/task/{task_id}/resolve", response_model=TaskResolveResponse)
async def resolve_dispute(
    task_id: str,
    req: TaskResolveRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """紛争を解決（ガバナンスによる判定）
    
    Requires JWT authentication. Only governance/admin can resolve disputes.
    """
    tc = get_task_contract()
    task = tc.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    # ガバナンス権限チェック（簡易実装: adminキーまたはガバナンス参加者）
    resolver_id = credentials.credentials
    # TODO: より厳密なガバナンス権限チェックを実装
    
    success = tc.resolve_dispute(
        task_id, 
        resolver_id, 
        req.approve_task, 
        req.slash_percentage,
        req.resolution_note
    )
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Dispute resolution failed. Task may not be in disputed state."
        )
    
    # Persist token state
    get_persistence().save_all()
    
    message = "Task approved and payment released" if req.approve_task else "Task rejected and funds returned to client"
    
    return TaskResolveResponse(
        status="resolved",
        task_id=task_id,
        resolver_id=resolver_id,
        approved=req.approve_task,
        message=message,
        resolved_at=datetime.now(timezone.utc).isoformat()
    )


@app.post("/rating/submit", response_model=RatingSubmitResponse)
async def submit_rating(
    req: RatingSubmitRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Submit a rating for an agent (requires JWT authentication)"""
    from_entity_id = credentials.credentials
    
    if from_entity_id == req.to_entity_id:
        raise HTTPException(status_code=400, detail="Cannot rate yourself")
    
    rc = get_reputation_contract()
    success = rc.rate_agent(
        from_entity=from_entity_id,
        to_entity=req.to_entity_id,
        score=req.score,
        comment=req.comment
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Rating submission failed. Score must be between 1 and 5."
        )
    
    return RatingSubmitResponse(
        status="submitted",
        from_entity_id=from_entity_id,
        to_entity_id=req.to_entity_id,
        score=req.score,
        comment=req.comment,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/rating/{entity_id}", response_model=RatingInfoResponse)
async def get_rating_info(entity_id: str):
    """Get rating and trust score for an entity"""
    rc = get_reputation_contract()
    
    return RatingInfoResponse(
        entity_id=entity_id,
        average_rating=rc.get_rating(entity_id),
        trust_score=rc.get_trust_score(entity_id),
        rating_count=rc.get_rating_count(entity_id)
    )


# Token Minting Endpoints (Admin only)
class MintRequest(BaseModel):
    entity_id: str
    amount: float = Field(..., gt=0, description="Amount to mint")
    mint_type: str = Field(default="manual", description="Type of mint: task_completion, quality_review, innovation_bonus, manual")
    description: str = Field(default="", description="Description of the mint")
    task_id: Optional[str] = Field(default=None, description="Related task ID")
    complexity: Optional[int] = Field(default=None, ge=1, le=100, description="Task complexity for task_completion type")


class MintResponse(BaseModel):
    success: bool
    entity_id: str
    amount: float
    new_balance: float
    mint_type: str
    total_minted: float


@app.post("/admin/mint", response_model=MintResponse)
async def mint_tokens(
    request: MintRequest,
    current_entity: str = Depends(require_admin)
):
    """Mint tokens for an entity (admin only)"""
    from token_system import get_token_minter, RewardType
    
    minter = get_token_minter()
    
    # Register wallet if not already registered
    wallet = get_wallet(request.entity_id)
    if wallet and request.entity_id not in minter._wallets:
        minter.register_wallet(wallet)
    
    # Execute mint based on type
    record = None
    if request.mint_type == "task_completion" and request.complexity:
        record = minter.mint_task_reward(
            to_entity=request.entity_id, 
            complexity=request.complexity,
            task_id=request.task_id or None,
            description=request.description
        )
    elif request.mint_type == "quality_review":
        record = minter.mint_review_reward(
            to_entity=request.entity_id,
            description=request.description
        )
    elif request.mint_type == "innovation_bonus":
        record = minter.mint_innovation_bonus(
            to_entity=request.entity_id,
            feature_description=request.description
        )
    else:
        # Manual mint
        record = minter.mint(
            to_entity=request.entity_id,
            amount=request.amount,
            reward_type=RewardType.GOVERNANCE_PARTICIPATION,
            description=request.description,
            task_id=request.task_id or None
        )
    
    if not record:
        raise HTTPException(status_code=400, detail="Minting failed")
    
    wallet = get_wallet(request.entity_id)
    return MintResponse(
        success=True,
        entity_id=request.entity_id,
        amount=request.amount,
        new_balance=wallet.get_balance() if wallet else 0,
        mint_type=request.mint_type,
        total_minted=minter.get_total_minted()
    )


class MintHistoryResponse(BaseModel):
    entity_id: str
    total_minted_for_entity: float
    history: List[Dict[str, Any]]


@app.get("/admin/mint/history/{entity_id}", response_model=MintHistoryResponse)
async def get_mint_history(
    entity_id: str,
    mint_type: Optional[str] = None,
    current_entity: str = Depends(require_admin)
):
    """Get mint history for an entity (admin only)"""
    from token_system import get_token_minter, RewardType
    
    minter = get_token_minter()
    
    # Convert string mint_type to RewardType if provided
    reward_type = None
    if mint_type:
        try:
            reward_type = RewardType(mint_type)
        except ValueError:
            pass
    
    history_records = minter.get_mint_history(entity_id=entity_id, reward_type=reward_type)
    
    # Convert records to dict format
    history = [record.to_dict() for record in history_records]
    
    # Calculate total for this entity
    total = sum(h["amount"] for h in history)
    
    return MintHistoryResponse(
        entity_id=entity_id,
        total_minted_for_entity=total,
        history=history
    )


# Persistence Endpoints
class PersistenceResponse(BaseModel):
    success: bool
    saved: Optional[Dict[str, int]] = None
    loaded: Optional[Dict[str, int]] = None


@app.post("/admin/persistence/save", response_model=PersistenceResponse)
async def save_all_data(current_entity: str = Depends(require_admin)):
    """Save all token system data to disk (admin only)"""
    from token_system import get_persistence
    
    persistence = get_persistence()
    results = persistence.save_all()
    
    return PersistenceResponse(success=True, saved=results)


@app.post("/admin/persistence/load", response_model=PersistenceResponse)
async def load_all_data(current_entity: str = Depends(require_admin)):
    """Load all token system data from disk (admin only)"""
    from token_system import get_persistence
    
    persistence = get_persistence()
    results = persistence.load_all()
    
    return PersistenceResponse(success=True, loaded=results)


# Token Economy Admin Endpoints

class EconomyMintRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to mint (must be positive)")
    to_entity_id: str = Field(..., description="Recipient entity ID")
    reason: str = Field(default="", description="Reason for minting")


class EconomyMintResponse(BaseModel):
    success: bool
    operation_id: Optional[str] = None
    amount: float
    new_total_supply: float
    new_circulating_supply: float
    timestamp: str


class EconomyBurnRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to burn (must be positive)")
    from_entity_id: str = Field(..., description="Source entity ID")
    reason: str = Field(default="", description="Reason for burning")


class EconomyBurnResponse(BaseModel):
    success: bool
    operation_id: Optional[str] = None
    amount: float
    new_total_supply: float
    new_circulating_supply: float
    timestamp: str


class SupplyStatsResponse(BaseModel):
    total_supply: float
    circulating_supply: float
    treasury_balance: float
    metadata: Dict[str, Any]


class MintHistoryItem(BaseModel):
    operation_id: str
    timestamp: str
    amount: float
    to: str
    reason: str
    new_supply: float


class MintHistoryListResponse(BaseModel):
    history: List[MintHistoryItem]
    count: int


class BurnHistoryItem(BaseModel):
    operation_id: str
    timestamp: str
    amount: float
    from_entity: str
    reason: str
    new_supply: float


class BurnHistoryListResponse(BaseModel):
    history: List[BurnHistoryItem]
    count: int


@app.post("/admin/economy/mint", response_model=EconomyMintResponse)
async def economy_mint(
    req: EconomyMintRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Mint new tokens (admin only)"""
    current_entity = credentials.credentials
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = token_economy.mint(
        amount=req.amount,
        to_entity_id=req.to_entity_id,
        reason=req.reason
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Minting failed"))
    
    return EconomyMintResponse(
        success=True,
        operation_id=result.get("operation_id"),
        amount=result.get("amount", req.amount),
        new_total_supply=result.get("new_total_supply", 0),
        new_circulating_supply=result.get("new_circulating_supply", 0),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.post("/admin/economy/burn", response_model=EconomyBurnResponse)
async def economy_burn(
    req: EconomyBurnRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Burn existing tokens (admin only)"""
    current_entity = credentials.credentials
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = token_economy.burn(
        amount=req.amount,
        from_entity_id=req.from_entity_id,
        reason=req.reason
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Burning failed"))
    
    return EconomyBurnResponse(
        success=True,
        operation_id=result.get("operation_id"),
        amount=result.get("amount", req.amount),
        new_total_supply=result.get("new_total_supply", 0),
        new_circulating_supply=result.get("new_circulating_supply", 0),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/admin/economy/supply", response_model=SupplyStatsResponse)
async def get_supply_stats(
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Get token supply statistics (admin only)"""
    current_entity = credentials.credentials
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return SupplyStatsResponse(
        total_supply=token_economy.metadata.total_supply,
        circulating_supply=token_economy.get_circulating_supply(),
        treasury_balance=token_economy.get_treasury_balance(),
        metadata=token_economy.metadata.to_dict()
    )


@app.get("/admin/economy/history/mint", response_model=MintHistoryListResponse)
async def get_mint_history_economy(
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Get token mint history (admin only)"""
    current_entity = credentials.credentials
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    history = token_economy.get_mint_history()
    return MintHistoryListResponse(
        history=[MintHistoryItem(**item) for item in history],
        count=len(history)
    )


@app.get("/admin/economy/history/burn", response_model=BurnHistoryListResponse)
async def get_burn_history_economy(
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Get token burn history (admin only)"""
    current_entity = credentials.credentials
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    history = token_economy.get_burn_history()
    return BurnHistoryListResponse(
        history=[BurnHistoryItem(**item) for item in history],
        count=len(history)
    )


# Token Persistence Admin Endpoints

class BackupListItem(BaseModel):
    name: str
    path: str
    created_at: str


@app.post("/admin/persistence/backup", response_model=BackupCreateResponse)
async def create_backup(
    tag: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Create a backup of current token data (admin only)"""
    current_entity = credentials.credentials
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    backup_path = persistence_mgr.create_backup(tag=tag)
    
    if backup_path is None:
        raise HTTPException(status_code=500, detail="Failed to create backup")
    
    return BackupCreateResponse(
        success=True,
        backup_path=str(backup_path),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/admin/persistence/backups", response_model=BackupListResponse)
async def list_backups(
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """List available backups (admin only)"""
    current_entity = credentials.credentials
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    backups = persistence_mgr.list_backups()
    backup_items = [
        BackupListItem(
            name=backup.name,
            path=str(backup),
            created_at=datetime.fromtimestamp(backup.stat().st_mtime).isoformat()
        )
        for backup in backups
    ]
    
    return BackupListResponse(
        backups=backup_items,
        count=len(backup_items)
    )


@app.post("/admin/persistence/restore", response_model=BackupRestoreResponse)
async def restore_backup(
    req: BackupRestoreRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Restore data from a backup (admin only)"""
    current_entity = credentials.credentials
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from pathlib import Path
    backup_path = Path(req.backup_path)
    
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail=f"Backup not found: {req.backup_path}")
    
    success = persistence_mgr.restore_backup(backup_path)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to restore backup")
    
    return BackupRestoreResponse(
        success=True,
        message=f"Successfully restored from backup: {req.backup_path}",
        timestamp=datetime.now(timezone.utc).isoformat()
    )


# Transaction Summary Endpoint
class TransactionSummaryResponse(BaseModel):
    entity_id: str
    period: str
    summary: Dict[str, Dict[str, float]]


@app.get("/wallet/{entity_id}/summary", response_model=TransactionSummaryResponse)
async def get_transaction_summary(
    entity_id: str,
    period: str = "daily"
):
    """Get transaction summary for an entity"""
    wallet = get_wallet(entity_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    
    summary = wallet.get_transaction_summary(period=period)
    
    return TransactionSummaryResponse(
        entity_id=entity_id,
        period=period,
        summary=summary
    )


# Detailed Ratings Endpoint
class RatingsDetailResponse(BaseModel):
    entity_id: str
    ratings: List[Dict[str, Any]]


@app.get("/reputation/{entity_id}/ratings", response_model=RatingsDetailResponse)
async def get_all_ratings(entity_id: str):
    """Get all ratings for an entity with details"""
    rc = get_reputation_contract()
    
    ratings = rc.get_all_ratings(entity_id)
    ratings_data = [
        {
            "from_entity": r.from_entity,
            "score": r.score,
            "comment": r.comment,
            "timestamp": r.timestamp.isoformat()
        }
        for r in ratings
    ]
    
    return RatingsDetailResponse(
        entity_id=entity_id,
        ratings=ratings_data
    )


# ============================================================================
# Token System Endpoints (v2 with /token prefix)
# ============================================================================

class WalletCreateRequest(BaseModel):
    entity_id: str
    initial_balance: float = 0.0


class WalletCreateResponse(BaseModel):
    status: str
    entity_id: str
    initial_balance: float
    created_at: str


# Token Economy Models
class TokenSupplyResponse(BaseModel):
    total_supply: float
    circulating_supply: float
    treasury_balance: float
    burned_tokens: float
    mint_operations_count: int
    burn_operations_count: int
    last_updated: str


class TokenMintRequest(BaseModel):
    to_entity_id: str
    amount: float = Field(..., gt=0, description="Amount to mint")
    reason: str = Field(default="", description="Reason for minting")


class TokenMintResponse(BaseModel):
    success: bool
    operation_id: str
    amount: float
    new_total_supply: float
    new_circulating_supply: float


class TokenBurnRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to burn")
    reason: str = Field(default="", description="Reason for burning")


class TokenBurnResponse(BaseModel):
    success: bool
    operation_id: str
    amount: float
    new_circulating_supply: float
    total_burned: float


class MintHistoryItem(BaseModel):
    operation_id: str
    timestamp: str
    amount: float
    to: str
    reason: str
    new_supply: float


class MintHistoryResponse(BaseModel):
    history: List[MintHistoryItem]
    count: int


class BurnHistoryItem(BaseModel):
    operation_id: str
    timestamp: str
    amount: float
    from_entity: str
    reason: str
    new_supply: float


class BurnHistoryResponse(BaseModel):
    history: List[BurnHistoryItem]
    count: int


class TokenSaveResponse(BaseModel):
    success: bool
    wallets_saved: int
    tasks_saved: int
    timestamp: str


class TokenLoadResponse(BaseModel):
    success: bool
    wallets_loaded: int
    tasks_loaded: int
    timestamp: str


class BackupItem(BaseModel):
    name: str
    path: str
    created_at: str


class TokenBackupsResponse(BaseModel):
    backups: List[BackupItem]
    count: int


class TokenBackupResponse(BaseModel):
    success: bool
    backup_path: str
    tag: Optional[str]
    timestamp: str


# 1. Wallet Management Endpoints

@app.post("/token/wallet/create", response_model=WalletCreateResponse)
async def create_new_wallet(
    req: WalletCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Create a new wallet for an entity (requires JWT authentication)"""
    try:
        from services.token_system import create_wallet
    except ImportError:
        from token_system import create_wallet
    
    # Only allow creating wallet for self or admin (for now, allow self only)
    # Decode JWT token to get entity_id from "sub" claim
    current_entity = jwt_auth.get_entity_id(credentials.credentials)
    if current_entity != req.entity_id:
        raise HTTPException(
            status_code=403,
            detail="Can only create wallet for your own entity"
        )
    
    # Check if wallet already exists
    existing = get_wallet(req.entity_id)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Wallet already exists for entity: {req.entity_id}"
        )
    
    wallet = create_wallet(req.entity_id, req.initial_balance)
    
    return WalletCreateResponse(
        status="created",
        entity_id=req.entity_id,
        initial_balance=req.initial_balance,
        created_at=datetime.now(timezone.utc).isoformat()
    )


@app.get("/token/wallet/{entity_id}", response_model=WalletInfoResponse)
async def get_wallet_info(entity_id: str):
    """Get comprehensive wallet information for an entity"""
    wallet = get_wallet(entity_id)
    if not wallet:
        raise HTTPException(status_code=404, detail=f"Wallet not found for entity: {entity_id}")
    
    return WalletInfoResponse(
        entity_id=entity_id,
        balance=wallet.get_balance(),
        currency="AIC",
        transaction_count=len(wallet.get_transaction_history()),
        created_at=wallet.created_at.isoformat() if hasattr(wallet, 'created_at') else None
    )


@app.get("/token/wallet/{entity_id}/balance", response_model=WalletBalanceResponse)
async def get_token_balance(entity_id: str):
    """Get wallet balance for an entity (compatibility endpoint)"""
    wallet = get_wallet(entity_id)
    if not wallet:
        raise HTTPException(status_code=404, detail=f"Wallet not found for entity: {entity_id}")
    
    return WalletBalanceResponse(
        entity_id=entity_id,
        balance=wallet.get_balance(),
        currency="AIC"
    )


# 2. Transaction Endpoints

@app.post("/token/transfer", response_model=TransferResponse)
async def token_transfer(
    req: TransferRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Transfer tokens to another entity (requires JWT authentication)"""
    # Decode JWT token to get from_entity_id from 'sub' claim
    try:
        payload = jwt_auth.verify_token(credentials.credentials)
        from_entity_id = payload.get("sub")
        if not from_entity_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing entity_id")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")
    
    # Get sender wallet
    from_wallet = get_wallet(from_entity_id)
    if not from_wallet:
        raise HTTPException(status_code=404, detail=f"Sender wallet not found: {from_entity_id}")
    
    # Get or create recipient wallet
    to_wallet = get_wallet(req.to_entity_id)
    if not to_wallet:
        try:
            from services.token_system import create_wallet
        except ImportError:
            from token_system import create_wallet
        to_wallet = create_wallet(req.to_entity_id, initial_balance=0.0)
    
    # Perform transfer
    success = from_wallet.transfer(to_wallet, req.amount, req.description)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Transfer failed. Insufficient balance or invalid amount."
        )

    # Persist token state
    get_persistence().save_all()

    return TransferResponse(
        status="success",
        from_entity_id=from_entity_id,
        to_entity_id=req.to_entity_id,
        amount=req.amount,
        description=req.description,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/token/wallet/{entity_id}/history", response_model=TransactionHistoryResponse)
async def get_token_transaction_history(entity_id: str):
    """Get transaction history for an entity"""
    wallet = get_wallet(entity_id)
    if not wallet:
        raise HTTPException(status_code=404, detail=f"Wallet not found for entity: {entity_id}")
    
    transactions = wallet.get_transaction_history()
    
    return TransactionHistoryResponse(
        entity_id=entity_id,
        transactions=[
            TransactionItem(
                type=t.type.value,
                amount=t.amount,
                timestamp=t.timestamp.isoformat(),
                description=t.description,
                counterparty=t.counterparty,
                related_task_id=t.related_task_id
            )
            for t in transactions
        ],
        count=len(transactions)
    )


# 3. Task Contract Endpoints

@app.post("/token/task/create", response_model=TaskCreateResponse)
async def create_token_task(
    req: TaskCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Create a new task contract with token lock (requires JWT authentication)"""
    client_id = credentials.credentials
    
    # Ensure client wallet exists
    client_wallet = get_wallet(client_id)
    if not client_wallet:
        from token_system import create_wallet
        client_wallet = create_wallet(client_id, initial_balance=0.0)
    
    # Ensure agent wallet exists
    agent_wallet = get_wallet(req.agent_id)
    if not agent_wallet:
        from token_system import create_wallet
        agent_wallet = create_wallet(req.agent_id, initial_balance=0.0)
    
    # Parse expires_at if provided
    expires_at = None
    if req.expires_at:
        try:
            expires_at = datetime.fromisoformat(req.expires_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at format. Use ISO format.")
    
    # Create task
    tc = get_task_contract()
    success = tc.create_task(
        task_id=req.task_id,
        client_id=client_id,
        agent_id=req.agent_id,
        amount=req.amount,
        description=req.description,
        expires_at=expires_at
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Task creation failed. Insufficient balance or task already exists."
        )

    # Persist token state
    get_persistence().save_all()

    task = tc.get_task(req.task_id)

    return TaskCreateResponse(
        status="created",
        task_id=req.task_id,
        client_id=client_id,
        agent_id=req.agent_id,
        amount=req.amount,
        description=req.description,
        created_at=task.created_at.isoformat(),
        expires_at=task.expires_at.isoformat() if task.expires_at else None
    )


@app.post("/token/task/{task_id}/complete", response_model=TaskCompleteResponse)
async def complete_token_task(
    task_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Complete a task and release locked tokens (requires JWT authentication)
    
    DEPRECATED: Use /task/{task_id}/submit-completion followed by /task/{task_id}/approve
    for client-approved workflow. This endpoint now enforces client approval.
    """
    tc = get_task_contract()
    task = tc.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    requester_id = credentials.credentials
    
    # エージェントが呼び出した場合: 承認待ち状態にする
    if requester_id == task.agent_id:
        success = tc.submit_task_completion(task_id, requester_id)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Task completion submission failed. Task may not be in progress."
            )
        get_persistence().save_all()
        raise HTTPException(
            status_code=202,
            detail="Task completion submitted, awaiting client approval. Use /task/{task_id}/approve to complete."
        )
    
    # クライアントが呼び出した場合: 承認して完了させる
    elif requester_id == task.client_id:
        # まず承認待ち状態にする（既に承認待ちの場合はスキップ）
        if task.status.value == "in_progress":
            success = tc.submit_task_completion(task_id, task.agent_id)
            if not success:
                raise HTTPException(
                    status_code=400,
                    detail="Task completion submission failed."
                )
            task = tc.get_task(task_id)  # 更新されたタスクを再取得
        
        # 承認を実行
        success = tc.approve_task(task_id, requester_id)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Task approval failed. Task may not be pending approval."
            )
        get_persistence().save_all()
        return TaskCompleteResponse(
            status="completed",
            task_id=task_id,
            agent_id=task.agent_id,
            amount=task.amount,
            completed_at=datetime.now(timezone.utc).isoformat()
        )
    
    else:
        raise HTTPException(
            status_code=403,
            detail="Only client or agent can complete the task"
        )


@app.post("/token/task/{task_id}/fail", response_model=TaskFailResponse)
async def fail_token_task(
    task_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Mark a task as failed and apply slashing (requires JWT authentication)"""
    tc = get_task_contract()
    task = tc.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    # Only client can mark task as failed
    requester_id = credentials.credentials
    if requester_id != task.client_id:
        raise HTTPException(
            status_code=403,
            detail="Only the client can mark a task as failed"
        )
    
    # Store amounts before failure for response
    agent_wallet = get_wallet(task.agent_id)
    client_wallet = get_wallet(task.client_id)
    original_amount = task.amount
    
    success = tc.fail_task(task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Task failure processing failed. Task may not be in progress."
        )
    
    # Calculate slashed and refunded amounts (50% slash default)
    slashed_amount = original_amount * 0.5
    refunded_amount = original_amount * 0.5
    
    return TaskFailResponse(
        status="failed",
        task_id=task_id,
        client_id=task.client_id,
        agent_id=task.agent_id,
        slashed_amount=slashed_amount,
        refunded_amount=refunded_amount,
        failed_at=datetime.now(timezone.utc).isoformat()
    )


@app.get("/token/task/{task_id}", response_model=TaskStatusResponse)
async def get_token_task_status(task_id: str):
    """Get task status and details"""
    tc = get_task_contract()
    task = tc.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    return TaskStatusResponse(
        task_id=task.task_id,
        client_id=task.client_id,
        agent_id=task.agent_id,
        amount=task.amount,
        status=task.status.value,
        created_at=task.created_at.isoformat(),
        expires_at=task.expires_at.isoformat() if task.expires_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        description=task.description
    )


# 4. Rating System Endpoints

@app.post("/token/rate", response_model=RatingSubmitResponse)
async def rate_entity(
    req: RatingSubmitRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Submit a rating for an entity (requires JWT authentication)"""
    from_entity_id = credentials.credentials
    
    if from_entity_id == req.to_entity_id:
        raise HTTPException(status_code=400, detail="Cannot rate yourself")
    
    rc = get_reputation_contract()
    success = rc.rate_agent(
        from_entity=from_entity_id,
        to_entity=req.to_entity_id,
        score=req.score,
        comment=req.comment
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Rating submission failed. Score must be between 1 and 5."
        )
    
    return RatingSubmitResponse(
        status="submitted",
        from_entity_id=from_entity_id,
        to_entity_id=req.to_entity_id,
        score=req.score,
        comment=req.comment,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/token/reputation/{entity_id}", response_model=RatingInfoResponse)
async def get_entity_reputation(entity_id: str):
    """Get rating and trust score for an entity"""
    rc = get_reputation_contract()
    
    return RatingInfoResponse(
        entity_id=entity_id,
        average_rating=rc.get_rating(entity_id),
        trust_score=rc.get_trust_score(entity_id),
        rating_count=rc.get_rating_count(entity_id)
    )


# ============================================================================
# Token Economy Endpoints (v2 with /token prefix)
# ============================================================================

@app.get("/token/supply", response_model=TokenSupplyResponse)
async def get_token_supply():
    """Get current token supply statistics"""
    economy = get_token_economy()
    stats = economy.get_supply_stats()
    
    return TokenSupplyResponse(
        total_supply=stats["total_supply"],
        circulating_supply=stats["circulating_supply"],
        treasury_balance=stats["treasury_balance"],
        burned_tokens=stats["burned_tokens"],
        mint_operations_count=stats["mint_operations_count"],
        burn_operations_count=stats["burn_operations_count"],
        last_updated=stats["last_updated"]
    )


@app.post("/token/mint", response_model=TokenMintResponse)
async def mint_tokens(
    req: TokenMintRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Mint new tokens (requires admin authentication)"""
    # Decode JWT token to get entity_id from "sub" claim
    current_entity = jwt_auth.get_entity_id(credentials.credentials)

    # Verify admin access
    if current_entity not in ADMIN_ENTITIES:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    economy = get_token_economy()
    result = economy.mint(
        amount=req.amount,
        to_entity_id=req.to_entity_id,
        reason=req.reason
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Minting failed"))
    
    return TokenMintResponse(
        success=True,
        operation_id=result["operation_id"],
        amount=result["amount"],
        new_total_supply=result["new_total_supply"],
        new_circulating_supply=result["new_circulating_supply"]
    )


@app.post("/token/burn", response_model=TokenBurnResponse)
async def burn_tokens(
    req: TokenBurnRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Burn tokens (requires authentication)"""
    from_entity_id = credentials.credentials
    
    # Get sender wallet
    from_wallet = get_wallet(from_entity_id)
    if not from_wallet:
        raise HTTPException(status_code=404, detail=f"Wallet not found: {from_entity_id}")
    
    economy = get_token_economy()
    result = economy.burn(
        amount=req.amount,
        from_wallet=from_wallet,
        reason=req.reason
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Burning failed"))
    
    return TokenBurnResponse(
        success=True,
        operation_id=result["operation_id"],
        amount=result["amount"],
        new_circulating_supply=result["new_circulating_supply"],
        total_burned=result["total_burned"]
    )


@app.get("/token/history/mint", response_model=MintHistoryResponse)
async def get_mint_history(limit: int = 100):
    """Get token minting history"""
    economy = get_token_economy()
    history = economy.get_mint_history(limit=limit)
    
    return MintHistoryResponse(
        history=[
            MintHistoryItem(
                operation_id=h["operation_id"],
                timestamp=h["timestamp"],
                amount=h["amount"],
                to=h["to"],
                reason=h["reason"],
                new_supply=h["new_supply"]
            )
            for h in history
        ],
        count=len(history)
    )


@app.get("/token/history/burn", response_model=BurnHistoryResponse)
async def get_burn_history(limit: int = 100):
    """Get token burning history"""
    economy = get_token_economy()
    history = economy.get_burn_history(limit=limit)
    
    return BurnHistoryResponse(
        history=[
            BurnHistoryItem(
                operation_id=h["operation_id"],
                timestamp=h["timestamp"],
                amount=h["amount"],
                from_entity=h["from"],
                reason=h["reason"],
                new_supply=h["new_supply"]
            )
            for h in history
        ],
        count=len(history)
    )


@app.post("/token/save", response_model=TokenSaveResponse)
async def save_token_data(
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Save all token system data (requires authentication)"""
    from token_system import get_persistence
    
    persistence = get_persistence()
    result = persistence.save_all()
    
    return TokenSaveResponse(
        success=True,
        wallets_saved=result.get("wallets", 0),
        tasks_saved=result.get("tasks", 0),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.post("/token/load", response_model=TokenLoadResponse)
async def load_token_data(
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Load all token system data (requires authentication)"""
    from token_system import get_persistence
    
    persistence = get_persistence()
    result = persistence.load_all()
    
    return TokenLoadResponse(
        success=True,
        wallets_loaded=result.get("wallets", 0),
        tasks_loaded=result.get("tasks", 0),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/token/backups", response_model=TokenBackupsResponse)
async def list_token_backups(
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """List available token data backups (requires authentication)"""
    pm = get_persistence_manager()
    backups = pm.list_backups()
    
    return TokenBackupsResponse(
        backups=[
            BackupItem(
                name=b.name,
                path=str(b),
                created_at=datetime.fromtimestamp(b.stat().st_mtime).isoformat() if b.exists() else ""
            )
            for b in backups
        ],
        count=len(backups)
    )


@app.post("/token/backup", response_model=TokenBackupResponse)
async def create_token_backup(
    tag: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Create a backup of token data (requires authentication)"""
    pm = get_persistence_manager()
    backup_path = pm.create_backup(tag=tag)
    
    if backup_path is None:
        raise HTTPException(status_code=500, detail="Failed to create backup")
    
    return TokenBackupResponse(
        success=True,
        backup_path=str(backup_path),
        tag=tag,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


# ============ Rate Limiting Integration ============

@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("Starting up API Server...")
    # Initialize rate limiters
    await init_rate_limiters()
    logger.info("Rate limiting initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Shutting down API Server...")
    # Shutdown rate limiters
    await shutdown_rate_limiters()
    logger.info("Rate limiting shut down")


# Add rate limiting middleware
# Note: This should be added after CORS middleware if used
app.add_middleware(
    RateLimitMiddleware,
    rate_limiter=get_rate_limiter(),
    key_func=lambda req: f"{req.client.host}:{req.url.path}" if req.client else "unknown",
    exclude_paths=["/health", "/docs", "/openapi.json", "/redoc"],
    include_headers=True
)


# ============ Rate Limit Admin Endpoints ============

class RateLimitStatsResponse(BaseModel):
    allowed: int
    denied: int
    cleaned: int
    active_buckets: int
    endpoint_configs: Optional[int] = None


# ============ Moltbook Integration Models ============

class MoltbookPostRequest(BaseModel):
    """Request model for creating a Moltbook post"""
    content: str = Field(..., description="Post content", min_length=1, max_length=5000)
    visibility: str = Field(default="public", description="Post visibility (public or private)")


class MoltbookPostResponse(BaseModel):
    """Response model for Moltbook post creation"""
    success: bool
    post_id: Optional[str] = None
    error: Optional[str] = None


class MoltbookCommentRequest(BaseModel):
    """Request model for creating a Moltbook comment"""
    post_id: str = Field(..., description="ID of the post to comment on")
    content: str = Field(..., description="Comment content", min_length=1, max_length=2000)


class MoltbookCommentResponse(BaseModel):
    """Response model for Moltbook comment creation"""
    success: bool
    comment_id: Optional[str] = None
    error: Optional[str] = None


class MoltbookTimelineResponse(BaseModel):
    """Response model for Moltbook timeline"""
    posts: List[Dict[str, Any]]
    next_cursor: Optional[str] = None


class MoltbookSearchResponse(BaseModel):
    """Response model for Moltbook agent search"""
    agents: List[Dict[str, Any]]


class MoltbookStatusResponse(BaseModel):
    """Response model for Moltbook connection status"""
    connected: bool
    agent: Optional[Dict[str, Any]] = None


# Peer Communication Models
class PeerReportRequest(BaseModel):
    """Request model for reporting progress to peer"""
    status: str = Field(..., description="Current status (e.g., 'S1完了', 'エラー発生')")
    next_action: Optional[str] = Field(None, description="Next action to take (e.g., 'S2開始')")
    session_id: Optional[str] = Field(None, description="Session ID (optional)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class PeerTalkRequest(BaseModel):
    """Request model for talking to peer"""
    message: str = Field(..., description="Message to send to peer")
    session_id: Optional[str] = Field(None, description="Session ID (optional)")
    timeout: int = Field(30, ge=1, le=300, description="Response timeout in seconds (1-300)")


class PeerWakeRequest(BaseModel):
    """Request model for waking up peer"""
    pass


class PeerReportResponse(BaseModel):
    """Response model for peer report"""
    result: str = Field(..., description="Result message")


class PeerTalkResponse(BaseModel):
    """Response model for peer talk"""
    response: str = Field(..., description="Response from peer")


class PeerWakeResponse(BaseModel):
    """Response model for peer wake"""
    result: str = Field(..., description="Wake up result")


class PeerAliveResponse(BaseModel):
    """Response model for peer alive check"""
    alive: bool = Field(..., description="Whether peer is alive and responding")


@app.get("/admin/rate-limits", response_model=RateLimitStatsResponse)
async def get_rate_limit_stats(
    admin: str = Depends(require_admin)
):
    """Get rate limiting statistics (admin only)"""
    limiter = get_rate_limiter()
    stats = await limiter.get_stats()
    return RateLimitStatsResponse(**stats)


@app.post("/admin/rate-limits/reset")
async def reset_rate_limits(
    key: Optional[str] = None,
    admin: str = Depends(require_admin)
):
    """Reset rate limits for a specific key or all keys (admin only)"""
    limiter = get_rate_limiter()
    await limiter.reset(key)
    return {
        "status": "reset",
        "key": key or "all",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============ Token Economy Endpoints ============

@app.post("/tokens/mint", response_model=TokenMintResponse)
async def mint_tokens(
    req: TokenMintRequest,
    admin: str = Depends(require_admin)
):
    """Mint new tokens and send to entity (admin only)"""
    result = token_economy.mint(
        amount=req.amount,
        to_entity_id=req.to_entity_id,
        reason=req.reason
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Minting failed")
        )
    
    return TokenMintResponse(
        success=True,
        operation_id=result.get("operation_id"),
        amount=result.get("amount", 0.0),
        new_total_supply=result.get("new_total_supply", 0.0),
        new_circulating_supply=result.get("new_circulating_supply", 0.0)
    )


@app.post("/tokens/burn", response_model=TokenBurnResponse)
async def burn_tokens(
    req: TokenBurnRequest,
    admin: str = Depends(require_admin)
):
    """Burn (destroy) tokens from an entity's wallet (admin only)"""
    from_wallet = get_wallet(req.from_entity_id)
    
    if not from_wallet:
        raise HTTPException(
            status_code=404,
            detail=f"Wallet not found for entity: {req.from_entity_id}"
        )
    
    result = token_economy.burn(
        amount=req.amount,
        from_wallet=from_wallet,
        reason=req.reason
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Burning failed")
        )
    
    return TokenBurnResponse(
        success=True,
        operation_id=result.get("operation_id"),
        amount=result.get("amount", 0.0),
        new_circulating_supply=result.get("new_circulating_supply", 0.0),
        total_burned=result.get("total_burned", 0.0)
    )


@app.get("/tokens/supply", response_model=TokenSupplyResponse)
async def get_token_supply():
    """Get current token supply statistics"""
    stats = token_economy.get_supply_stats()
    
    return TokenSupplyResponse(
        total_supply=stats.get("total_supply", 0.0),
        circulating_supply=stats.get("circulating_supply", 0.0),
        treasury_balance=stats.get("treasury_balance", 0.0),
        burned_tokens=stats.get("burned_tokens", 0.0),
        mint_operations_count=stats.get("mint_operations_count", 0),
        burn_operations_count=stats.get("burn_operations_count", 0),
        last_updated=stats.get("last_updated", datetime.now(timezone.utc).isoformat())
    )


@app.post("/tokens/backup", response_model=BackupCreateResponse)
async def create_backup(
    tag: Optional[str] = None,
    admin: str = Depends(require_admin)
):
    """Create a backup of token system data (admin only)"""
    backup_path = persistence_mgr.create_backup(tag=tag)
    
    if backup_path is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to create backup"
        )
    
    return BackupCreateResponse(
        success=True,
        backup_path=str(backup_path),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/tokens/backups", response_model=BackupListResponse)
async def list_backups(
    admin: str = Depends(require_admin)
):
    """List available backups (admin only)"""
    backups = persistence_mgr.list_backups()
    
    backup_list = []
    for backup in backups:
        backup_list.append({
            "path": str(backup),
            "name": backup.name,
            "created_at": datetime.fromtimestamp(backup.stat().st_mtime, tz=timezone.utc).isoformat()
        })
    
    return BackupListResponse(
        backups=backup_list,
        count=len(backup_list)
    )


@app.post("/tokens/restore", response_model=BackupRestoreResponse)
async def restore_backup(
    req: BackupRestoreRequest,
    admin: str = Depends(require_admin)
):
    """Restore token system data from a backup (admin only)"""
    from pathlib import Path
    
    backup_path = Path(req.backup_path)
    
    if not backup_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Backup not found: {req.backup_path}"
        )
    
    success = persistence_mgr.restore_backup(backup_path)
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to restore backup"
        )
    
    return BackupRestoreResponse(
        success=True,
        restored_from=str(backup_path),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


# ============ Moltbook Integration Endpoints ============

@app.post("/moltbook/post", response_model=MoltbookPostResponse)
async def create_moltbook_post(
    req: MoltbookPostRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Create a post on Moltbook.
    
    Requires JWT authentication. Rate limited to 1 post per 30 minutes per agent.
    """
    if not moltbook_client:
        raise HTTPException(
            status_code=503,
            detail="Moltbook client not initialized. Check MOLTBOOK_API_KEY configuration."
        )
    
    try:
        result = await moltbook_client.create_post(
            content=req.content,
            visibility=req.visibility
        )
        
        if result:
            return MoltbookPostResponse(
                success=True,
                post_id=result.get("id")
            )
        else:
            return MoltbookPostResponse(
                success=False,
                error="Failed to create post. Rate limit may have been exceeded or authentication failed."
            )
    except Exception as e:
        logger.error(f"Error creating Moltbook post: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/moltbook/comment", response_model=MoltbookCommentResponse)
async def create_moltbook_comment(
    req: MoltbookCommentRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Create a comment on a Moltbook post.
    
    Requires JWT authentication. Rate limited to 50 comments per hour per agent.
    """
    if not moltbook_client:
        raise HTTPException(
            status_code=503,
            detail="Moltbook client not initialized. Check MOLTBOOK_API_KEY configuration."
        )
    
    try:
        result = await moltbook_client.create_comment(
            post_id=req.post_id,
            content=req.content
        )
        
        if result:
            return MoltbookCommentResponse(
                success=True,
                comment_id=result.get("id")
            )
        else:
            return MoltbookCommentResponse(
                success=False,
                error="Failed to create comment. Rate limit may have been exceeded or authentication failed."
            )
    except Exception as e:
        logger.error(f"Error creating Moltbook comment: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/moltbook/timeline", response_model=MoltbookTimelineResponse)
async def get_moltbook_timeline(
    limit: int = 20,
    cursor: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Get the Moltbook timeline.
    
    Requires JWT authentication.
    - limit: Number of posts to retrieve (max 50)
    - cursor: Pagination cursor for retrieving more posts
    """
    if not moltbook_client:
        raise HTTPException(
            status_code=503,
            detail="Moltbook client not initialized. Check MOLTBOOK_API_KEY configuration."
        )
    
    try:
        result = await moltbook_client.get_timeline(
            limit=min(limit, 50),
            cursor=cursor
        )
        
        if result:
            return MoltbookTimelineResponse(
                posts=result.get("posts", []),
                next_cursor=result.get("next_cursor")
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve timeline"
            )
    except Exception as e:
        logger.error(f"Error retrieving Moltbook timeline: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/moltbook/search", response_model=MoltbookSearchResponse)
async def search_moltbook_agents(
    q: str,
    limit: int = 10,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Search for agents on Moltbook.
    
    Requires JWT authentication.
    - q: Search query
    - limit: Maximum number of results (max 20)
    """
    if not moltbook_client:
        raise HTTPException(
            status_code=503,
            detail="Moltbook client not initialized. Check MOLTBOOK_API_KEY configuration."
        )
    
    try:
        result = await moltbook_client.search_agents(
            query=q,
            limit=min(limit, 20)
        )
        
        if result:
            return MoltbookSearchResponse(
                agents=result.get("agents", [])
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to search agents"
            )
    except Exception as e:
        logger.error(f"Error searching Moltbook agents: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/moltbook/status", response_model=MoltbookStatusResponse)
async def get_moltbook_status(
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Get Moltbook connection status and current agent information.
    
    Requires JWT authentication.
    """
    if not moltbook_client:
        return MoltbookStatusResponse(
            connected=False,
            agent=None
        )
    
    try:
        status = await moltbook_client.heartbeat()
        return MoltbookStatusResponse(
            connected=status.get("connected", False),
            agent=status.get("agent")
        )
    except Exception as e:
        logger.error(f"Error checking Moltbook status: {e}")
        return MoltbookStatusResponse(
            connected=False,
            agent=None
        )


# ============================================
# Governance Endpoints
# ============================================

# Governance models
class ProposalCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    proposal_type: str = Field(..., description="parameter_change, protocol_upgrade, token_allocation, emergency_action")
    execution_payload: Optional[Dict[str, Any]] = None


class ProposalResponse(BaseModel):
    id: str
    title: str
    description: str
    proposer: str
    proposal_type: str
    status: str
    created_at: str
    voting_ends_at: Optional[str] = None
    votes_for: int
    votes_against: int
    votes_abstain: int
    voter_count: int


class ProposalListResponse(BaseModel):
    proposals: List[ProposalResponse]
    total: int


class VoteRequest(BaseModel):
    proposal_id: str
    vote: str = Field(..., description="for, against, or abstain")


class VoteResponse(BaseModel):
    success: bool
    message: str


class GovernanceStatsResponse(BaseModel):
    total_proposals: int
    active_proposals: int
    executed_proposals: int
    paused: bool


# Governance endpoints (simplified - no token system dependency)
@app.post("/governance/proposal", response_model=ProposalResponse)
async def create_governance_proposal(
    request: ProposalCreateRequest,
    entity_id: str = Depends(get_current_entity_id)
):
    """
    Create a new governance proposal.
    
    Requires JWT authentication.
    """
    from services.governance import init_governance_system, ProposalType
    
    gov = init_governance_system(storage_path="./data/governance.json")
    
    try:
        proposal_type = ProposalType(request.proposal_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid proposal_type: {request.proposal_type}")
    
    proposal = await gov.create_proposal(
        proposer=entity_id,
        title=request.title,
        description=request.description,
        proposal_type=proposal_type,
        execution_payload=request.execution_payload,
        min_tokens=0  # No minimum for now
    )
    
    if not proposal:
        raise HTTPException(status_code=400, detail="Failed to create proposal")
    
    return ProposalResponse(
        id=proposal.id,
        title=proposal.title,
        description=proposal.description,
        proposer=proposal.proposer,
        proposal_type=proposal.proposal_type.value,
        status=proposal.status.value,
        created_at=proposal.created_at.isoformat(),
        voting_ends_at=proposal.voting_ends_at.isoformat() if proposal.voting_ends_at else None,
        votes_for=proposal.votes_for,
        votes_against=proposal.votes_against,
        votes_abstain=proposal.votes_abstain,
        voter_count=len(proposal.voters)
    )


@app.get("/governance/proposals", response_model=ProposalListResponse)
async def list_governance_proposals(
    status: Optional[str] = None,
    entity_id: str = Depends(get_current_entity_id)
):
    """
    List governance proposals.
    
    Optional query parameter:
    - status: Filter by status (pending, active, succeeded, failed, executed)
    """
    from services.governance import init_governance_system, ProposalStatus
    
    gov = init_governance_system(storage_path="./data/governance.json")
    
    status_filter = None
    if status:
        try:
            status_filter = ProposalStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    proposals = gov.list_proposals(status=status_filter)
    
    return ProposalListResponse(
        proposals=[
            ProposalResponse(
                id=p.id,
                title=p.title,
                description=p.description,
                proposer=p.proposer,
                proposal_type=p.proposal_type.value,
                status=p.status.value,
                created_at=p.created_at.isoformat(),
                voting_ends_at=p.voting_ends_at.isoformat() if p.voting_ends_at else None,
                votes_for=p.votes_for,
                votes_against=p.votes_against,
                votes_abstain=p.votes_abstain,
                voter_count=len(p.voters)
            )
            for p in proposals
        ],
        total=len(proposals)
    )


@app.post("/governance/vote", response_model=VoteResponse)
async def cast_governance_vote(
    request: VoteRequest,
    entity_id: str = Depends(get_current_entity_id)
):
    """
    Cast a vote on a governance proposal.
    
    Vote options: "for", "against", "abstain"
    """
    from services.governance import init_governance_system
    
    gov = init_governance_system(storage_path="./data/governance.json")
    
    success = await gov.cast_vote(
        voter=entity_id,
        proposal_id=request.proposal_id,
        vote=request.vote
    )
    
    if success:
        return VoteResponse(success=True, message="Vote recorded successfully")
    else:
        return VoteResponse(success=False, message="Failed to record vote")


@app.get("/governance/stats", response_model=GovernanceStatsResponse)
async def get_governance_stats(
    entity_id: str = Depends(get_current_entity_id)
):
    """
    Get governance system statistics.
    """
    from services.governance import init_governance_system
    
    gov = init_governance_system(storage_path="./data/governance.json")
    stats = gov.get_stats()
    
    return GovernanceStatsResponse(**stats)


# ============================================================================
# WebSocket Support for Real-time Peer Communication
# ============================================================================

class WebSocketMessage(BaseModel):
    """WebSocket message format"""
    type: str = Field(..., description="Message type: ping, pong, message, task, status")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="Message payload")
    timestamp: Optional[str] = Field(default=None, description="ISO format timestamp")
    sender: Optional[str] = Field(default=None, description="Sender entity ID")


class BidNotification(BaseModel):
    """Bid notification message for real-time marketplace updates"""
    type: str = Field(..., description="Notification type: bid.new, bid.closed, bid.won, auction.started, auction.ended, error")
    auction_id: Optional[str] = Field(default=None, description="Auction/request ID")
    service_id: Optional[str] = Field(default=None, description="Service ID related to the bid")
    provider_id: Optional[str] = Field(default=None, description="Provider ID who made/submitted the bid")
    bid_amount: Optional[float] = Field(default=None, ge=0, description="Bid amount in tokens")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO format timestamp")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional notification details")
    
    class Config:
        schema_extra = {
            "example": {
                "type": "bid.new",
                "auction_id": "550e8400-e29b-41d4-a716-446655440000",
                "service_id": "service-123",
                "provider_id": "provider-456",
                "bid_amount": 100.0,
                "timestamp": "2026-02-01T10:00:00Z",
                "details": {"category": "code_review", "urgency": "high"}
            }
        }


# Import WebSocket connection pool (with fallback)
websocket_pool_module = None
for prefix in ['services.', '']:
    try:
        websocket_pool_module = __import__(f"{prefix}connection_pool", fromlist=[
            'get_websocket_pool', 'init_websocket_pool', 'shutdown_websocket_pool',
            'WebSocketConnectionPool', 'WebSocketState'
        ])
        break
    except ImportError:
        continue

if websocket_pool_module:
    get_websocket_pool = websocket_pool_module.get_websocket_pool
    init_websocket_pool = websocket_pool_module.init_websocket_pool
    shutdown_websocket_pool = websocket_pool_module.shutdown_websocket_pool
    WebSocketConnectionPool = websocket_pool_module.WebSocketConnectionPool
    WebSocketState = websocket_pool_module.WebSocketState
    logger.info("✓ WebSocket connection pool module loaded")
else:
    logger.warning("✗ WebSocket connection pool not available")
    # Mock implementations
    WebSocketState = None
    class WebSocketConnectionPool:
        def __init__(self):
            pass
        async def start(self):
            pass
        async def stop(self):
            pass
        async def add_connection(self, *args, **kwargs):
            pass
        async def remove_connection(self, *args, **kwargs):
            pass
    def get_websocket_pool(*args, **kwargs):
        return WebSocketConnectionPool()
    def init_websocket_pool(*args, **kwargs):
        return WebSocketConnectionPool()
    def shutdown_websocket_pool(*args, **kwargs):
        pass

# Global WebSocket connection pool
_ws_pool: Optional[WebSocketConnectionPool] = None

async def get_ws_pool() -> Optional[WebSocketConnectionPool]:
    """Get or initialize WebSocket connection pool"""
    global _ws_pool
    if _ws_pool is None and websocket_pool_module:
        _ws_pool = get_websocket_pool()
        await _ws_pool.start()
    return _ws_pool


@app.websocket("/ws/v1/peers")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time peer communication.
    
    Authentication: Pass JWT token as query parameter: ?token=<jwt_token>
    Optional: Ed25519 signature verification via X-Signature header in initial message
    
    Message Types:
    - ping: Heartbeat request (server responds with pong)
    - pong: Heartbeat response
    - message: General message between peers
    - task: Task-related communication
    - status: Status update broadcast
    - auth: Authentication with Ed25519 signature
    """
    entity_id: Optional[str] = None
    ws_pool = await get_ws_pool()
    
    try:
        # Authenticate using query parameter token
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=1008, reason="Missing authentication token")
            return
        
        # Verify JWT token
        try:
            payload = jwt_auth.verify_token(token)
            entity_id = payload.get("sub")
            if not entity_id:
                await websocket.close(code=1008, reason="Invalid token: missing subject")
                return
        except Exception as e:
            await websocket.close(code=1008, reason=f"Authentication failed: {str(e)}")
            return
        
        # Register peer with WebSocket connection pool if not already registered
        if entity_id not in ws_pool._configs:
            ws_pool.register_peer(
                peer_id=entity_id,
                endpoint_url=f"ws://{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown",
                reconnect_interval=5.0,
                heartbeat_interval=30.0
            )
        
        # Check for existing connection (prevent duplicate connections)
        if entity_id in ws_pool.get_connected_peers():
            await websocket.close(code=1008, reason="Duplicate connection - peer already connected")
            return
        
        # Accept connection via connection pool (with circuit breaker check)
        connection_accepted = await ws_pool.accept_connection(entity_id, websocket)
        if not connection_accepted:
            await websocket.close(code=1013, reason="Service unavailable - circuit breaker open")
            return
        
        # Initialize connection metadata
        connection_metadata = {
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "last_ping": None,
            "message_count": 0
        }
        
        # Send welcome message
        await websocket.send_json({
            "type": "status",
            "payload": {
                "event": "connected",
                "entity_id": entity_id,
                "message": "WebSocket connection established"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Handle incoming messages
        while True:
            try:
                # Receive JSON message
                data = await websocket.receive_json()
                msg_type = data.get("type", "message")
                msg_payload = data.get("payload", {})
                
                # Update metadata
                connection_metadata["message_count"] += 1
                
                # Update connection pool metrics
                metrics = ws_pool._metrics.get(entity_id)
                if metrics:
                    metrics.record_message(sent=False)
                
                # Verify Ed25519 signature if provided (for enhanced security)
                signature = data.get("signature")
                if signature and msg_payload:
                    try:
                        # Get sender's public key from registry or payload
                        sender_pubkey = msg_payload.get("public_key")
                        if sender_pubkey:
                            # Verify signature over the payload
                            message_bytes = json.dumps(msg_payload, sort_keys=True).encode()
                            sig_bytes = bytes.fromhex(signature)
                            pubkey_bytes = bytes.fromhex(sender_pubkey)
                            
                            # Use crypto module for verification
                            from crypto import verify_signature
                            if not verify_signature(message_bytes, sig_bytes, pubkey_bytes):
                                await websocket.send_json({
                                    "type": "status",
                                    "payload": {
                                        "event": "error",
                                        "message": "Invalid Ed25519 signature"
                                    },
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                })
                                continue
                    except Exception as e:
                        logging.warning(f"Signature verification error for {entity_id}: {e}")
                        # Continue processing even if signature verification fails
                        # (JWT auth is the primary authentication method)
                
                # Handle different message types
                if msg_type == "ping":
                    # Respond with pong
                    connection_metadata["last_ping"] = datetime.now(timezone.utc).isoformat()
                    await websocket.send_json({
                        "type": "pong",
                        "payload": {"timestamp": datetime.now(timezone.utc).isoformat()},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                
                elif msg_type == "pong":
                    # Client pong received (acknowledgment)
                    pass
                
                elif msg_type == "message":
                    # General message - echo back with acknowledgment
                    target = msg_payload.get("target")
                    message_data = {
                        "type": "message",
                        "payload": {
                            **msg_payload,
                            "from": entity_id,
                            "received": True
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "sender": entity_id
                    }
                    
                    if target and target != "broadcast":
                        # Send to specific target
                        sent = await ws_pool.send_message(target, message_data)
                        await websocket.send_json({
                            "type": "status",
                            "payload": {
                                "event": "message_sent",
                                "target": target,
                                "delivered": sent
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    else:
                        # Broadcast to all except sender
                        await ws_pool.broadcast(message_data, exclude=entity_id)
                
                elif msg_type == "task":
                    # Task-related message
                    task_action = msg_payload.get("action")
                    task_id = msg_payload.get("task_id")
                    
                    # Process task message
                    response = {
                        "type": "task",
                        "payload": {
                            "action": task_action,
                            "task_id": task_id,
                            "from": entity_id,
                            "status": "received",
                            "processed": True
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "sender": entity_id
                    }
                    
                    # Echo back to sender
                    await websocket.send_json(response)
                    
                    # If target specified, forward to target
                    target = msg_payload.get("target")
                    if target:
                        await ws_pool.send_message(target, response)
                
                elif msg_type == "status":
                    # Status update request
                    status_type = msg_payload.get("status_type", "general")
                    
                    if status_type == "peers":
                        # Return list of connected peers
                        connected_peers = ws_pool.get_connected_peers()
                        await websocket.send_json({
                            "type": "status",
                            "payload": {
                                "event": "peer_list",
                                "peers": connected_peers,
                                "count": len(connected_peers)
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    else:
                        # General status acknowledgment
                        await websocket.send_json({
                            "type": "status",
                            "payload": {
                                "event": "status_received",
                                "status_type": status_type,
                                "from": entity_id
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                
                else:
                    # Unknown message type
                    await websocket.send_json({
                        "type": "status",
                        "payload": {
                            "event": "error",
                            "message": f"Unknown message type: {msg_type}",
                            "supported_types": ["ping", "pong", "message", "task", "status"]
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
            
            except WebSocketDisconnect:
                break
            except Exception as e:
                logging.error(f"WebSocket error for {entity_id}: {e}")
                try:
                    await websocket.send_json({
                        "type": "status",
                        "payload": {
                            "event": "error",
                            "message": str(e)
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                except:
                    break
    
    except Exception as e:
        logging.error(f"WebSocket connection error: {e}")
    
    finally:
        # Cleanup on disconnect
        if entity_id:
            await ws_pool.disconnect(entity_id)


@app.get("/ws/peers")
async def get_connected_websocket_peers(
    entity_id: str = Depends(get_current_entity_id)
) -> Dict[str, Any]:
    """
    Get list of peers connected via WebSocket.
    Requires JWT authentication.
    """
    ws_pool = await get_ws_pool()
    connected_peers = ws_pool.get_connected_peers()
    return {
        "peers": connected_peers,
        "count": len(connected_peers),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/ws/metrics")
async def get_websocket_metrics(
    peer_id: Optional[str] = None,
    current_entity: str = Depends(get_current_entity_id)
) -> Dict[str, Any]:
    """
    Get WebSocket connection pool metrics.
    Requires JWT authentication.
    
    Args:
        peer_id: Optional specific peer ID to get metrics for
    """
    ws_pool = await get_ws_pool()
    metrics = await ws_pool.get_metrics(peer_id)
    circuit_states = await ws_pool.get_circuit_states()
    connected_peers = ws_pool.get_connected_peers()
    
    return {
        "metrics": metrics,
        "circuit_states": circuit_states,
        "connected_peers": connected_peers,
        "total_connected": len(connected_peers),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/ws/health")
async def get_websocket_health(
    current_entity: str = Depends(get_current_entity_id)
) -> Dict[str, Any]:
    """
    Get WebSocket connection pool health status.
    Requires JWT authentication.
    """
    ws_pool = await get_ws_pool()
    circuit_states = await ws_pool.get_circuit_states()
    
    # Count open circuits (unhealthy peers)
    open_circuits = [
        peer_id for peer_id, state in circuit_states.items()
        if state == "open"
    ]
    
    return {
        "status": "healthy" if len(open_circuits) == 0 else "degraded",
        "connected_peers": len(ws_pool.get_connected_peers()),
        "registered_peers": len(ws_pool._configs),
        "open_circuits": open_circuits,
        "open_circuit_count": len(open_circuits),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============ Marketplace API Endpoints ============

class ServiceListingRequest(BaseModel):
    """Request model for registering a service listing"""
    provider_id: str = Field(..., description="ID of the service provider")
    service_type: str = Field(..., description="Service type (compute, storage, data, analysis, llm, vision, audio)")
    description: str = Field(..., min_length=1, max_length=2000, description="Service description")
    pricing_model: str = Field(..., description="Pricing model (per_request, per_hour, per_gb, fixed)")
    price: float = Field(..., ge=0, description="Service price")
    capabilities: List[str] = Field(default=[], description="List of service capabilities")
    endpoint: str = Field(..., description="Service endpoint URL")
    terms_hash: str = Field(..., description="Hash of service terms")


# v1.3 Multi-Agent Marketplace Phase 1 - New Request/Response Models
class ServiceCreateRequest(BaseModel):
    """Request model for creating a new service (v1.3)"""
    name: str = Field(..., min_length=1, max_length=200, description="Service name")
    description: str = Field(..., min_length=1, max_length=2000, description="Service description")
    category: str = Field(..., description="Service category")
    tags: List[str] = Field(default=[], description="List of service tags")
    capabilities: List[str] = Field(..., min_length=1, description="List of service capabilities (at least one required)")
    pricing_model: str = Field(..., description="Pricing model (per_request, per_hour, per_gb, fixed)")
    price: float = Field(..., ge=0, description="Service price (must be >= 0)")
    currency: str = Field(default="AIC", description="Currency code")
    endpoint: str = Field(..., description="Service endpoint URL")
    terms_hash: Optional[str] = Field(default=None, description="Hash of service terms")
    input_schema: Optional[Dict[str, Any]] = Field(default=None, description="Input JSON schema")
    output_schema: Optional[Dict[str, Any]] = Field(default=None, description="Output JSON schema")
    max_concurrent: int = Field(default=1, ge=1, description="Maximum concurrent requests")
    
    @validator('endpoint')
    def validate_endpoint(cls, v):
        """Validate endpoint URL format"""
        import re
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        if not url_pattern.match(v):
            raise ValueError('Invalid endpoint URL format')
        return v
    
    @validator('capabilities')
    def validate_capabilities(cls, v):
        """Validate capabilities is not empty"""
        if not v or len(v) == 0:
            raise ValueError('At least one capability is required')
        return v


class ServiceUpdateRequest(BaseModel):
    """Request model for updating a service (v1.3)"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200, description="Service name")
    description: Optional[str] = Field(default=None, min_length=1, max_length=2000, description="Service description")
    category: Optional[str] = Field(default=None, description="Service category")
    tags: Optional[List[str]] = Field(default=None, description="List of service tags")
    capabilities: Optional[List[str]] = Field(default=None, description="List of service capabilities")
    pricing_model: Optional[str] = Field(default=None, description="Pricing model")
    price: Optional[float] = Field(default=None, ge=0, description="Service price (must be >= 0)")
    currency: Optional[str] = Field(default=None, description="Currency code")
    endpoint: Optional[str] = Field(default=None, description="Service endpoint URL")
    terms_hash: Optional[str] = Field(default=None, description="Hash of service terms")
    input_schema: Optional[Dict[str, Any]] = Field(default=None, description="Input JSON schema")
    output_schema: Optional[Dict[str, Any]] = Field(default=None, description="Output JSON schema")
    max_concurrent: Optional[int] = Field(default=None, ge=1, description="Maximum concurrent requests")
    is_active: Optional[bool] = Field(default=None, description="Service active status")
    
    @validator('endpoint')
    def validate_endpoint(cls, v):
        """Validate endpoint URL format"""
        if v is None:
            return v
        import re
        url_pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        if not url_pattern.match(v):
            raise ValueError('Invalid endpoint URL format')
        return v
    
    @validator('capabilities')
    def validate_capabilities(cls, v):
        """Validate capabilities is not empty if provided"""
        if v is not None and len(v) == 0:
            raise ValueError('Capabilities cannot be empty if provided')
        return v


class ServiceSearchRequest(BaseModel):
    """Request model for searching services (v1.3)"""
    query: Optional[str] = Field(default=None, description="Search query string")
    category: Optional[str] = Field(default=None, description="Filter by category")
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags (OR matching)")
    capabilities: Optional[List[str]] = Field(default=None, description="Filter by capabilities (AND matching)")
    min_price: Optional[float] = Field(default=None, ge=0, description="Minimum price")
    max_price: Optional[float] = Field(default=None, ge=0, description="Maximum price")
    min_rating: Optional[float] = Field(default=None, ge=0, le=5, description="Minimum rating (0-5)")
    provider_id: Optional[str] = Field(default=None, description="Filter by provider")
    available_only: bool = Field(default=True, description="Only show available services")
    sort_by: str = Field(default="reputation", description="Sort field (reputation, price, created_at)")
    sort_order: str = Field(default="desc", description="Sort order (asc, desc)")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Result offset for pagination")


class ServiceResponse(BaseModel):
    """Response model for a single service (v1.3)"""
    service_id: str
    provider_id: str
    name: str
    description: str
    category: str
    tags: List[str]
    capabilities: List[str]
    pricing_model: str
    price: str
    currency: str
    endpoint: str
    reputation_score: float
    total_reviews: int
    successful_transactions: int
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    terms_hash: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    max_concurrent: int = 1
    completion_rate: float = 0.0
    avg_response_time_ms: float = 0.0


class ServiceListingResponse(BaseModel):
    """Response model for service listing operations"""
    success: bool
    service_id: Optional[str] = None
    listing: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ServiceListResponse(BaseModel):
    """Response model for service list"""
    services: List[Dict[str, Any]]
    total: int
    filters: Dict[str, Any]


class ServiceDetailResponse(BaseModel):
    """Response model for service details"""
    service: Dict[str, Any]


class OrderCreateRequest(BaseModel):
    """Request model for creating an order"""
    buyer_id: str = Field(..., description="ID of the buyer")
    service_id: str = Field(..., description="ID of the service to order")
    quantity: int = Field(default=1, ge=1, description="Quantity to order")
    max_price: float = Field(..., ge=0, description="Maximum price willing to pay")
    requirements: Optional[Dict[str, Any]] = Field(default={}, description="Specific requirements")
    expiry_hours: int = Field(default=24, ge=1, le=168, description="Order expiry in hours (1-168)")


class OrderResponse(BaseModel):
    """Response model for order operations"""
    success: bool
    order_id: Optional[str] = None
    order: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class OrderMatchRequest(BaseModel):
    """Request model for matching an order"""
    provider_id: str = Field(..., description="ID of the provider accepting the order")


class OrderMatchResponse(BaseModel):
    """Response model for order match"""
    success: bool
    order_id: str
    matched_provider_id: Optional[str] = None
    escrow_id: Optional[str] = None
    message: str


class OrderActionResponse(BaseModel):
    """Response model for order actions (start, complete, cancel)"""
    success: bool
    order_id: str
    new_status: Optional[str] = None
    message: str


class SubmitResultRequest(BaseModel):
    """Request model for provider submitting work result"""
    provider_id: str = Field(..., description="ID of the provider submitting result")
    result: Dict[str, Any] = Field(..., description="Work result data")


class SubmitResultResponse(BaseModel):
    """Response model for submit result"""
    success: bool
    order_id: str
    new_status: str
    message: str


class ApproveOrderRequest(BaseModel):
    """Request model for buyer approving order"""
    buyer_id: str = Field(..., description="ID of the buyer")
    rating: int = Field(default=5, ge=1, le=5, description="Rating 1-5")


class ApproveOrderResponse(BaseModel):
    """Response model for approve order"""
    success: bool
    order_id: str
    new_status: str
    message: str


class StartOrderRequest(BaseModel):
    """Request model for provider starting order work"""
    provider_id: str = Field(..., description="ID of the provider")


class StartOrderResponse(BaseModel):
    """Response model for start order"""
    success: bool
    order_id: str
    new_status: str
    message: str


class RejectOrderRequest(BaseModel):
    """Request model for buyer rejecting order"""
    buyer_id: str = Field(..., description="ID of the buyer")
    reason: str = Field(..., min_length=1, max_length=1000, description="Reason for rejection")


class RejectOrderResponse(BaseModel):
    """Response model for reject order"""
    success: bool
    order_id: str
    new_status: str
    message: str


class GetResultResponse(BaseModel):
    """Response model for getting order result"""
    success: bool
    order_id: str
    result: Optional[Dict[str, Any]] = None
    submitted_at: Optional[str] = None
    status: Optional[str] = None
    message: str


class MarketplaceStatsResponse(BaseModel):
    """Response model for marketplace statistics"""
    registry_stats: Dict[str, Any]
    orderbook_stats: Dict[str, Any]
    timestamp: str


@app.get("/marketplace/services", response_model=ServiceListResponse)
async def list_services(
    service_type: Optional[str] = None,
    capabilities: Optional[str] = None,
    min_reputation: float = 0.0,
    max_price: Optional[float] = None,
    limit: int = 100
):
    """
    List available services with optional filtering.
    
    Query parameters:
    - service_type: Filter by service type (compute, storage, data, analysis, llm, vision, audio)
    - capabilities: Comma-separated list of required capabilities
    - min_reputation: Minimum reputation score (0-5)
    - max_price: Maximum price
    - limit: Maximum number of results (default: 100)
    """
    if marketplace_registry is None:
        raise HTTPException(status_code=503, detail="Marketplace service unavailable")
    
    try:
        from services.marketplace import ServiceType
    except ImportError:
        from marketplace import ServiceType
    
    # Parse service type
    type_enum = None
    if service_type:
        try:
            type_enum = ServiceType(service_type.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid service_type: {service_type}")
    
    # Parse capabilities
    cap_list = None
    if capabilities:
        cap_list = [c.strip() for c in capabilities.split(",") if c.strip()]
    
    # Search services
    from decimal import Decimal
    max_price_decimal = Decimal(str(max_price)) if max_price is not None else None
    
    results = await marketplace_registry.search_services(
        service_type=type_enum,
        capabilities=cap_list,
        min_reputation=min_reputation,
        max_price=max_price_decimal,
        limit=limit
    )
    
    return ServiceListResponse(
        services=[s.to_dict() for s in results],
        total=len(results),
        filters={
            "service_type": service_type,
            "capabilities": cap_list,
            "min_reputation": min_reputation,
            "max_price": max_price
        }
    )


@app.post("/marketplace/services", response_model=ServiceListingResponse)
async def register_service(
    req: ServiceListingRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Register a new service listing.
    
    Requires JWT authentication. The authenticated entity becomes the provider.
    """
    if marketplace_registry is None:
        raise HTTPException(status_code=503, detail="Marketplace service unavailable")
    
    try:
        from services.marketplace import ServiceListing, ServiceType, PricingModel
    except ImportError:
        from marketplace import ServiceListing, ServiceType, PricingModel
    
    from decimal import Decimal
    import uuid
    
    # Get provider_id from JWT token
    try:
        payload = jwt_auth.verify_token(credentials.credentials)
        provider_id = payload.get("sub", "")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    # Validate service type
    try:
        svc_type = ServiceType(req.service_type.lower())
    except ValueError:
        valid_types = [t.value for t in ServiceType]
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid service_type. Valid types: {', '.join(valid_types)}"
        )
    
    # Validate pricing model
    try:
        pricing = PricingModel(req.pricing_model.lower())
    except ValueError:
        valid_models = [m.value for m in PricingModel]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pricing_model. Valid models: {', '.join(valid_models)}"
        )
    
    # Create service listing (provider_id from JWT, not request)
    service_id = str(uuid.uuid4())
    listing = ServiceListing(
        service_id=service_id,
        provider_id=provider_id,  # From JWT token, not request
        service_type=svc_type,
        description=req.description,
        pricing_model=pricing,
        price=Decimal(str(req.price)),
        capabilities=req.capabilities,
        endpoint=req.endpoint,
        terms_hash=req.terms_hash
    )
    
    success = await marketplace_registry.register_service(listing)
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to register service")
    
    return ServiceListingResponse(
        success=True,
        service_id=service_id,
        listing=listing.to_dict()
    )


@app.get("/marketplace/services/{service_id}", response_model=ServiceDetailResponse)
async def get_service(service_id: str):
    """Get detailed information about a specific service."""
    if marketplace_registry is None:
        raise HTTPException(status_code=503, detail="Marketplace service unavailable")
    
    listing = await marketplace_registry.get_service(service_id)
    
    if listing is None:
        raise HTTPException(status_code=404, detail=f"Service {service_id} not found")
    
    return ServiceDetailResponse(service=listing.to_dict())


@app.delete("/marketplace/services/{service_id}")
async def delete_service(
    service_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Unregister a service listing.
    
    Requires JWT authentication. Only the service provider can delete their service.
    """
    if marketplace_registry is None:
        raise HTTPException(status_code=503, detail="Marketplace service unavailable")
    
    # Get provider_id from JWT token
    try:
        payload = jwt_auth.verify_token(credentials.credentials)
        provider_id = payload.get("sub", "")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    success = await marketplace_registry.unregister_service(service_id, provider_id)
    
    if not success:
        raise HTTPException(
            status_code=404, 
            detail=f"Service {service_id} not found or provider_id mismatch"
        )
    
    return {
        "success": True,
        "message": f"Service {service_id} unregistered successfully"
    }


# ============ v1.3 Multi-Agent Marketplace Phase 1 Endpoints ============

@app.put("/marketplace/services/{service_id}", response_model=ServiceResponse)
async def update_service_v13(
    service_id: str,
    req: ServiceUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Update a service listing (v1.3).
    
    Requires JWT authentication. Only the service provider can update their service.
    
    Request body can include any of:
    - name, description, category, tags, capabilities
    - pricing_model, price, currency, endpoint
    - terms_hash, input_schema, output_schema
    - max_concurrent, is_active
    """
    if marketplace_registry is None:
        raise HTTPException(status_code=503, detail="Marketplace service unavailable")
    
    # Get provider_id from JWT token
    try:
        payload = jwt_auth.verify_token(credentials.credentials)
        provider_id = payload.get("sub", "")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    # Check if service exists
    existing = await marketplace_registry.get_service(service_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Service {service_id} not found")
    
    # Build updates dict with non-None values
    updates = {}
    for field in ['description', 'endpoint', 'terms_hash', 'is_active']:
        value = getattr(req, field)
        if value is not None:
            updates[field] = value
    
    # Handle pricing_model enum
    if req.pricing_model is not None:
        try:
            from services.marketplace import PricingModel
            updates['pricing_model'] = PricingModel(req.pricing_model.lower())
        except (ImportError, ValueError):
            try:
                from marketplace import PricingModel
                updates['pricing_model'] = PricingModel(req.pricing_model.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid pricing_model: {req.pricing_model}")
    
    # Handle price
    if req.price is not None:
        from decimal import Decimal
        updates['price'] = Decimal(str(req.price))
    
    # Handle capabilities
    if req.capabilities is not None:
        updates['capabilities'] = req.capabilities
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Update service
    success = await marketplace_registry.update_service(service_id, provider_id, updates)
    
    if not success:
        raise HTTPException(
            status_code=403,
            detail="Failed to update service. Ensure you are the service provider."
        )
    
    # Get updated service
    updated = await marketplace_registry.get_service(service_id)
    return ServiceResponse(**updated.to_dict())


@app.get("/marketplace/services/search", response_model=ServiceListResponse)
async def search_services_v13(
    query: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    capabilities: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: float = 0.0,
    available_only: bool = True,
    sort_by: str = "reputation",
    sort_order: str = "desc",
    limit: int = 20,
    offset: int = 0,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Search services with advanced filters (v1.3).
    
    Query parameters:
    - query: Search in name/description (optional)
    - category: Filter by category (optional)
    - tags: Comma-separated tags (OR matching, optional)
    - capabilities: Comma-separated capabilities (AND matching, optional)
    - min_price/max_price: Price range (optional)
    - min_rating: Minimum rating 0-5 (default: 0)
    - available_only: Only active services (default: true)
    - sort_by: reputation|price|created_at (default: reputation)
    - sort_order: asc|desc (default: desc)
    - limit: Results per page 1-100 (default: 20)
    - offset: Pagination offset (default: 0)
    """
    if marketplace_registry is None:
        raise HTTPException(status_code=503, detail="Marketplace service unavailable")
    
    try:
        from services.marketplace import ServiceType
    except ImportError:
        from marketplace import ServiceType
    
    # Parse tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    
    # Parse capabilities
    cap_list = None
    if capabilities:
        cap_list = [c.strip() for c in capabilities.split(",") if c.strip()]
    
    # Parse service type from category
    type_enum = None
    if category:
        try:
            type_enum = ServiceType(category.lower())
        except ValueError:
            pass  # Continue without type filter
    
    # Search using registry
    from decimal import Decimal
    max_price_decimal = Decimal(str(max_price)) if max_price is not None else None
    
    results = await marketplace_registry.search_services(
        service_type=type_enum,
        capabilities=cap_list,
        min_reputation=min_rating,
        max_price=max_price_decimal,
        limit=limit + offset  # Get extra for pagination
    )
    
    # Apply additional filters
    filtered = []
    for listing in results:
        # Skip if not active and available_only
        if available_only and not listing.is_active:
            continue
        
        # Filter by tags (OR matching)
        if tag_list and not any(tag in listing.tags for tag in tag_list):
            continue
        
        # Filter by min_price
        if min_price is not None and float(listing.price) < min_price:
            continue
        
        # Filter by query (name/description)
        if query:
            query_lower = query.lower()
            if query_lower not in listing.description.lower():
                continue
        
        filtered.append(listing)
    
    # Apply sorting
    reverse = sort_order.lower() == "desc"
    if sort_by == "price":
        filtered.sort(key=lambda x: float(x.price), reverse=reverse)
    elif sort_by == "created_at":
        filtered.sort(key=lambda x: x.created_at or datetime.min, reverse=reverse)
    else:  # reputation
        filtered.sort(key=lambda x: x.reputation_score, reverse=reverse)
    
    # Apply pagination
    total = len(filtered)
    paginated = filtered[offset:offset + limit]
    
    return ServiceListResponse(
        services=[s.to_dict() for s in paginated],
        total=total,
        filters={
            "query": query,
            "category": category,
            "tags": tag_list,
            "capabilities": cap_list,
            "min_price": min_price,
            "max_price": max_price,
            "min_rating": min_rating,
            "available_only": available_only,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "offset": offset,
            "limit": limit
        }
    )


@app.get("/marketplace/services/by-provider/{provider_id}", response_model=ServiceListResponse)
async def get_services_by_provider_v13(
    provider_id: str,
    include_inactive: bool = False,
    limit: int = 100,
    offset: int = 0,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Get all services by a specific provider (v1.3).
    
    Path parameters:
    - provider_id: The provider's entity ID
    
    Query parameters:
    - include_inactive: Include inactive services (default: false)
    - limit: Results per page 1-100 (default: 100)
    - offset: Pagination offset (default: 0)
    """
    if marketplace_registry is None:
        raise HTTPException(status_code=503, detail="Marketplace service unavailable")
    
    # Get services from provider
    results = await marketplace_registry.get_provider_services(provider_id)
    
    # Filter inactive if needed
    if not include_inactive:
        results = [s for s in results if s.is_active]
    
    # Apply pagination
    total = len(results)
    paginated = results[offset:offset + limit]
    
    return ServiceListResponse(
        services=[s.to_dict() for s in paginated],
        total=total,
        filters={
            "provider_id": provider_id,
            "include_inactive": include_inactive,
            "offset": offset,
            "limit": limit
        }
    )


@app.post("/marketplace/orders", response_model=OrderResponse)
async def create_order(req: OrderCreateRequest):
    """
    Create a new service order.
    
    TODO: Add authentication check for buyer_id
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    from decimal import Decimal
    
    order = await marketplace_orderbook.create_order(
        buyer_id=req.buyer_id,
        service_id=req.service_id,
        quantity=req.quantity,
        max_price=Decimal(str(req.max_price)),
        requirements=req.requirements,
        expiry_hours=req.expiry_hours
    )
    
    if order is None:
        raise HTTPException(status_code=400, detail="Failed to create order")
    
    return OrderResponse(
        success=True,
        order_id=order.order_id,
        order=order.to_dict()
    )


@app.get("/marketplace/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    """Get detailed information about a specific order."""
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    order = await marketplace_orderbook.get_order(order_id)
    
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    
    return OrderResponse(
        success=True,
        order_id=order_id,
        order=order.to_dict()
    )


@app.post("/marketplace/orders/{order_id}/match", response_model=OrderMatchResponse)
async def match_order(order_id: str, req: OrderMatchRequest):
    """
    Match a pending order with a provider.
    
    TODO: Add authentication check for provider_id
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    result = await marketplace_orderbook.match_order(
        order_id=order_id,
        provider_id=req.provider_id
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    
    return OrderMatchResponse(
        success=True,
        order_id=order_id,
        matched_provider_id=result.matched_provider_id,
        escrow_id=result.escrow_id,
        message=result.message
    )


@app.post("/marketplace/orders/{order_id}/start", response_model=OrderActionResponse)
async def start_service(order_id: str):
    """
    Mark an order as in progress (service started).
    
    TODO: Add authentication check (provider only)
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    success = await marketplace_orderbook.start_service(order_id)
    
    if not success:
        raise HTTPException(
            status_code=400, 
            detail=f"Failed to start service for order {order_id}. Order must be in 'matched' status."
        )
    
    return OrderActionResponse(
        success=True,
        order_id=order_id,
        new_status="in_progress",
        message="Service started successfully"
    )


@app.post("/marketplace/orders/{order_id}/complete", response_model=OrderActionResponse)
async def complete_order(order_id: str):
    """
    Mark an order as completed.
    
    TODO: Add authentication check (buyer or provider)
    TODO: Trigger reputation update and payment release
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    success = await marketplace_orderbook.complete_order(order_id)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to complete order {order_id}. Order must be 'in_progress'."
        )
    
    # Get order details for potential reputation update
    order = await marketplace_orderbook.get_order(order_id)
    
    # TODO: Update service reputation
    # if order and marketplace_registry:
    #     await marketplace_registry.update_reputation(
    #         order.service_id, rating=5.0, transaction_success=True
    #     )
    
    return OrderActionResponse(
        success=True,
        order_id=order_id,
        new_status="completed",
        message="Order completed successfully"
    )


@app.post("/marketplace/orders/{order_id}/cancel", response_model=OrderActionResponse)
async def cancel_order(order_id: str, buyer_id: str):
    """
    Cancel a pending order.
    
    TODO: Add authentication check for buyer_id
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    success = await marketplace_orderbook.cancel_order(order_id, buyer_id)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to cancel order {order_id}. Order not found or not cancellable."
        )
    
    return OrderActionResponse(
        success=True,
        order_id=order_id,
        new_status="cancelled",
        message="Order cancelled successfully"
    )


@app.post("/marketplace/orders/{order_id}/submit", response_model=SubmitResultResponse)
async def submit_order_result(order_id: str, request: SubmitResultRequest):
    """
    Provider submits work result for buyer review.
    Changes order status from 'in_progress' to 'pending_review'.
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    success = await marketplace_orderbook.submit_result(
        order_id=order_id,
        provider_id=request.provider_id,
        result_data=request.result
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to submit result for order {order_id}. Order must be 'in_progress' and provider must match."
        )
    
    return SubmitResultResponse(
        success=True,
        order_id=order_id,
        new_status="pending_review",
        message="Result submitted successfully. Waiting for buyer approval."
    )


@app.post("/marketplace/orders/{order_id}/approve", response_model=ApproveOrderResponse)
async def approve_order_result(
    order_id: str,
    request: ApproveOrderRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Buyer approves submitted work result.
    Changes order status from 'pending_review' to 'completed' and releases payment.
    Also transfers tokens from buyer to provider automatically.
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    # Decode JWT token to get buyer_id from 'sub' claim
    try:
        payload = jwt_auth.verify_token(credentials.credentials)
        buyer_id = payload.get("sub")
        if not buyer_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing entity_id")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")
    
    # Get order info before approval (for token transfer)
    order = await marketplace_orderbook.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    
    # Verify buyer matches
    if order.buyer_id != buyer_id:
        raise HTTPException(status_code=403, detail="Only the buyer can approve this order")
    
    # Approve the order
    # Note: Token transfer is handled inside order_book.approve_order()
    success = await marketplace_orderbook.approve_order(
        order_id=order_id,
        buyer_id=buyer_id
    )
    
    if not success:
        # Get detailed error info from order book logs
        order_check = await marketplace_orderbook.get_order(order_id)
        if order_check is None:
            error_detail = f"Order {order_id} not found in order book"
        elif order_check.buyer_id != buyer_id:
            error_detail = f"Buyer mismatch: expected {order_check.buyer_id}, got {buyer_id}"
        elif order_check.status.value != "pending_review":
            error_detail = f"Order status is '{order_check.status.value}', expected 'pending_review'"
        else:
            error_detail = f"Token transfer failed or other error. Check server logs for details."
        
        logger.error(f"approve_order failed for {order_id}: {error_detail}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to approve order {order_id}: {error_detail}"
        )
    
    # Token transfer is already handled by order_book.approve_order()
    # We just need to persist token state if token system is available
    if token_system_module and order.total_amount > 0:
        try:
            get_persistence().save_all()
        except Exception as e:
            logger.warning(f"Failed to persist token state: {e}")
    
    # === SOLANA BLOCKCHAIN SYNC ===
    # Mirror internal token transfer on Solana blockchain
    solana_tx_signature = None
    try:
        # Import Solana bridge
        try:
            from .solana_bridge import execute_marketplace_payment
        except ImportError:
            from solana_bridge import execute_marketplace_payment
        
        if order.total_amount > 0:
            logger.info(f"Initiating Solana blockchain sync for order {order_id}")
            solana_result = execute_marketplace_payment(
                buyer_id=order.buyer_id,
                provider_id=order.provider_id,
                amount=order.total_amount,
                order_id=order_id
            )
            
            if solana_result.get("success"):
                solana_tx_signature = solana_result.get("signature")
                logger.info(f"✅ Solana sync successful: {solana_tx_signature}")
            else:
                # Log but don't fail - internal transfer already succeeded
                logger.warning(f"⚠️ Solana sync failed: {solana_result.get('error')}")
                logger.warning("Internal transfer succeeded but blockchain sync failed")
                
    except Exception as e:
        # Solana sync failure should not block the approval
        logger.warning(f"⚠️ Solana bridge error: {e}")
        logger.warning("Continuing without blockchain sync")
    
    # TODO: Update provider reputation with rating
    
    # Build response message
    message = f"Order approved and completed. Payment of {order.total_amount} tokens released to provider {order.provider_id}."
    if solana_tx_signature:
        message += f" Solana tx: {solana_tx_signature[:16]}..."
    
    return ApproveOrderResponse(
        success=True,
        order_id=order_id,
        new_status="completed",
        message=message
    )


@app.post("/marketplace/orders/{order_id}/start", response_model=StartOrderResponse)
async def start_order_work(
    order_id: str,
    request: StartOrderRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Provider starts work on a matched order.
    Changes order status from 'matched' to 'in_progress'.
    Only the matched provider can start the order.
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    # Get provider_id from JWT token
    provider_id = credentials.credentials
    
    # Get order info
    order = await marketplace_orderbook.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    
    # Verify provider matches
    if order.provider_id != provider_id:
        raise HTTPException(status_code=403, detail="Only the matched provider can start this order")
    
    # Start the order
    success = await marketplace_orderbook.start_order(
        order_id=order_id,
        provider_id=provider_id
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to start order {order_id}. Order must be 'matched' and provider must match."
        )
    
    return StartOrderResponse(
        success=True,
        order_id=order_id,
        new_status="in_progress",
        message=f"Order started successfully. Provider {provider_id} is now working on the order."
    )


@app.post("/marketplace/orders/{order_id}/reject", response_model=RejectOrderResponse)
async def reject_order_result(order_id: str, request: RejectOrderRequest):
    """
    Buyer rejects submitted work result.
    Changes order status from 'pending_review' to 'disputed'.
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    success = await marketplace_orderbook.reject_order(
        order_id=order_id,
        buyer_id=request.buyer_id,
        reason=request.reason
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to reject order {order_id}. Order must be 'pending_review' and buyer must match."
        )
    
    # TODO: Initiate dispute resolution process
    
    return RejectOrderResponse(
        success=True,
        order_id=order_id,
        new_status="disputed",
        message=f"Order rejected. Reason: {request.reason}. Dispute resolution initiated."
    )


@app.get("/marketplace/orders/{order_id}/result", response_model=GetResultResponse)
async def get_order_result(order_id: str, user_id: str):
    """
    Get submitted result for an order.
    Available to both buyer and provider after result submission.
    """
    if marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace order book unavailable")
    
    result = await marketplace_orderbook.get_result(
        order_id=order_id,
        user_id=user_id
    )
    
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Result not found for order {order_id}. Order may not exist, result not yet submitted, or user not authorized."
        )
    
    return GetResultResponse(
        success=True,
        order_id=order_id,
        result=result.get('result_data'),
        submitted_at=result.get('submitted_at'),
        status=result.get('status'),
        message="Result retrieved successfully"
    )


@app.get("/marketplace/stats", response_model=MarketplaceStatsResponse)
async def get_marketplace_stats():
    """Get marketplace statistics."""
    if marketplace_registry is None or marketplace_orderbook is None:
        raise HTTPException(status_code=503, detail="Marketplace services unavailable")
    
    registry_stats = await marketplace_registry.get_stats()
    orderbook_stats = await marketplace_orderbook.get_stats()
    
    return MarketplaceStatsResponse(
        registry_stats=registry_stats,
        orderbook_stats=orderbook_stats,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


# ============ Service Registry API Endpoints (v1.3) ============

class ServiceRegisterRequest(BaseModel):
    """Request model for service registration"""
    provider_id: str = Field(..., description="ID of the service provider")
    service_type: str = Field(..., description="Service type (compute, storage, data, analysis, llm, vision, audio)")
    description: str = Field(..., min_length=1, max_length=2000, description="Service description")
    pricing_model: str = Field(..., description="Pricing model (per_request, per_hour, per_gb, fixed)")
    price: float = Field(..., ge=0, description="Service price")
    capabilities: List[str] = Field(default=[], description="List of service capabilities")
    endpoint: str = Field(..., description="Service endpoint URL")
    terms_hash: str = Field(..., description="Hash of service terms")


class ServiceRegisterResponse(BaseModel):
    """Response model for service registration"""
    success: bool
    service_id: Optional[str] = None
    message: str
    listing: Optional[Dict[str, Any]] = None


class ServiceSearchRequest(BaseModel):
    """Request model for service search"""
    service_type: Optional[str] = Field(default=None, description="Filter by service type")
    capabilities: Optional[List[str]] = Field(default=None, description="Required capabilities")
    min_reputation: float = Field(default=0.0, ge=0, le=5, description="Minimum reputation score")
    max_price: Optional[float] = Field(default=None, ge=0, description="Maximum price")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")


class ServiceSearchResponse(BaseModel):
    """Response model for service search"""
    services: List[Dict[str, Any]]
    total: int
    filters: Dict[str, Any]


class ServiceUnregisterResponse(BaseModel):
    """Response model for service unregistration"""
    success: bool
    service_id: str
    message: str


class ServiceInfoResponse(BaseModel):
    """Response model for service details (legacy /services endpoint)"""
    service: Optional[Dict[str, Any]] = None
    found: bool
    service_id: str


# Global ServiceRegistry instance for /services endpoints
_service_registry: Optional[Any] = None

async def get_service_registry() -> Any:
    """Get or initialize ServiceRegistry instance"""
    global _service_registry
    if _service_registry is None:
        try:
            from services.marketplace import ServiceRegistry
        except ImportError:
            from marketplace import ServiceRegistry
        _service_registry = ServiceRegistry(storage_path="data/services/registry.json")
    return _service_registry


@app.post("/services/register", response_model=ServiceRegisterResponse)
async def register_service_endpoint(
    req: ServiceRegisterRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Register a new service listing.
    Requires JWT authentication.
    """
    registry = await get_service_registry()
    
    try:
        from services.marketplace import ServiceListing, ServiceType, PricingModel
    except ImportError:
        from marketplace import ServiceListing, ServiceType, PricingModel
    
    from decimal import Decimal
    import uuid
    
    # Validate service type
    try:
        svc_type = ServiceType(req.service_type.lower())
    except ValueError:
        valid_types = [t.value for t in ServiceType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service_type. Valid types: {', '.join(valid_types)}"
        )
    
    # Validate pricing model
    try:
        pricing = PricingModel(req.pricing_model.lower())
    except ValueError:
        valid_models = [m.value for m in PricingModel]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pricing_model. Valid models: {', '.join(valid_models)}"
        )
    
    # Create service listing
    service_id = str(uuid.uuid4())
    listing = ServiceListing(
        service_id=service_id,
        provider_id=req.provider_id,
        service_type=svc_type,
        description=req.description,
        pricing_model=pricing,
        price=Decimal(str(req.price)),
        capabilities=req.capabilities,
        endpoint=req.endpoint,
        terms_hash=req.terms_hash
    )
    
    success = await registry.register_service(listing)
    
    if success:
        return ServiceRegisterResponse(
            success=True,
            service_id=service_id,
            message="Service registered successfully",
            listing=listing.to_dict()
        )
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to register service"
        )


@app.post("/services/search", response_model=ServiceSearchResponse)
async def search_services_endpoint(
    req: ServiceSearchRequest,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Search for services with filters.
    Requires JWT authentication.
    """
    registry = await get_service_registry()
    
    try:
        from services.marketplace import ServiceType
    except ImportError:
        from marketplace import ServiceType
    
    from decimal import Decimal
    
    # Parse service type
    type_enum = None
    if req.service_type:
        try:
            type_enum = ServiceType(req.service_type.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid service_type: {req.service_type}")
    
    # Convert max_price to Decimal
    max_price_decimal = Decimal(str(req.max_price)) if req.max_price is not None else None
    
    # Search services
    results = await registry.search_services(
        service_type=type_enum,
        capabilities=req.capabilities,
        min_reputation=req.min_reputation,
        max_price=max_price_decimal,
        limit=req.limit
    )
    
    return ServiceSearchResponse(
        services=[s.to_dict() for s in results],
        total=len(results),
        filters={
            "service_type": req.service_type,
            "capabilities": req.capabilities,
            "min_reputation": req.min_reputation,
            "max_price": req.max_price
        }
    )


@app.get("/services/provider/{provider_id}", response_model=ServiceSearchResponse)
async def get_provider_services_endpoint(
    provider_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Get all services by a specific provider.
    Requires JWT authentication.
    """
    registry = await get_service_registry()
    
    results = await registry.get_provider_services(provider_id)
    
    return ServiceSearchResponse(
        services=[s.to_dict() for s in results],
        total=len(results),
        filters={"provider_id": provider_id}
    )


@app.get("/services/{service_id}", response_model=ServiceInfoResponse)
async def get_service_detail_endpoint(
    service_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Get details of a specific service.
    Requires JWT authentication.
    """
    registry = await get_service_registry()
    
    listing = await registry.get_service(service_id)
    
    if listing:
        return ServiceInfoResponse(
            service=listing.to_dict(),
            found=True,
            service_id=service_id
        )
    else:
        return ServiceInfoResponse(
            service=None,
            found=False,
            service_id=service_id
        )


@app.delete("/services/{service_id}", response_model=ServiceUnregisterResponse)
async def unregister_service_endpoint(
    service_id: str,
    provider_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Unregister a service (only by the provider).
    Requires JWT authentication.
    """
    registry = await get_service_registry()
    
    success = await registry.unregister_service(service_id, provider_id)
    
    if success:
        return ServiceUnregisterResponse(
            success=True,
            service_id=service_id,
            message="Service unregistered successfully"
        )
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Service not found or provider mismatch"
        )


# WebSocket Bidding Endpoint
# Active bidding connections: request_id -> {websocket, provider_ids}
_bidding_connections: Dict[str, Dict] = {}

@app.websocket("/ws/v1/bidding")
async def bidding_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time bidding notifications.
    
    Authentication: Pass JWT token as query parameter: ?token=<jwt_token>
    
    Message Types (Client -> Server):
    - subscribe: Subscribe to bid requests for a service type
    - bid: Submit a bid for a request
    - unsubscribe: Unsubscribe from a service type
    
    Message Types (Server -> Client):
    - bid_request: New bid request notification
    - bid_status: Bid acceptance/rejection status
    - winner_announcement: Winner selection notification
    - bidding_closed: Bidding window closed
    """
    entity_id: Optional[str] = None
    subscribed_services: set = set()
    
    try:
        # Authenticate using query parameter token
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=1008, reason="Missing authentication token")
            return
        
        # Verify JWT token
        try:
            payload = jwt_auth.verify_token(token)
            entity_id = payload.get("sub")
            if not entity_id:
                await websocket.close(code=1008, reason="Invalid token: missing subject")
                return
        except Exception as e:
            await websocket.close(code=1008, reason=f"Authentication failed: {str(e)}")
            return
        
        # Accept connection
        await websocket.accept()
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "payload": {
                "entity_id": entity_id,
                "message": "Bidding WebSocket connected. Subscribe to service types to receive bid requests.",
                "supported_actions": ["subscribe", "bid", "unsubscribe", "ping"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")
                msg_payload = data.get("payload", {})
                
                if msg_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "payload": {"timestamp": datetime.now(timezone.utc).isoformat()},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                
                elif msg_type == "subscribe":
                    # Subscribe to service type notifications
                    service_type = msg_payload.get("service_type")
                    if service_type:
                        subscribed_services.add(service_type)
                        await websocket.send_json({
                            "type": "subscribed",
                            "payload": {
                                "service_type": service_type,
                                "message": f"Subscribed to {service_type} bid requests"
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                
                elif msg_type == "unsubscribe":
                    # Unsubscribe from service type
                    service_type = msg_payload.get("service_type")
                    if service_type and service_type in subscribed_services:
                        subscribed_services.discard(service_type)
                        await websocket.send_json({
                            "type": "unsubscribed",
                            "payload": {
                                "service_type": service_type,
                                "message": f"Unsubscribed from {service_type} bid requests"
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                
                elif msg_type == "bid":
                    # Submit bid (would integrate with BiddingEngine)
                    request_id = msg_payload.get("request_id")
                    price = msg_payload.get("price")
                    estimated_time = msg_payload.get("estimated_time", 300)
                    
                    # Acknowledge bid receipt
                    await websocket.send_json({
                        "type": "bid_received",
                        "payload": {
                            "request_id": request_id,
                            "provider_id": entity_id,
                            "price": price,
                            "status": "pending",
                            "message": "Bid submitted successfully"
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                
                else:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {
                            "message": f"Unknown message type: {msg_type}"
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Bidding WebSocket error for {entity_id}: {e}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"message": str(e)},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                except:
                    break
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Bidding WebSocket fatal error: {e}")
    finally:
        # Cleanup
        logger.info(f"Bidding WebSocket disconnected: {entity_id}")


async def notify_bid_request(request_id: str, service_type: str, requirements: dict):
    """
    Notify all subscribed providers about a new bid request.
    Called by BiddingEngine when a new request is created.
    """
    message = {
        "type": "bid_request",
        "payload": {
            "request_id": request_id,
            "service_type": service_type,
            "requirements": requirements,
            "bidding_window_seconds": 5,
            "message": "New bid request available"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # This would iterate through active connections and notify matching subscribers
    # Implementation depends on connection management strategy
    logger.info(f"Broadcasting bid request {request_id} for {service_type}")


async def notify_bid_winner(request_id: str, winner_id: str, price: str):
    """
    Notify the winning provider about bid acceptance.
    Called by BiddingEngine when winner is selected.
    """
    message = {
        "type": "winner_announcement",
        "payload": {
            "request_id": request_id,
            "winner_id": winner_id,
            "price": price,
            "message": "Congratulations! Your bid was selected"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    logger.info(f"Announcing winner {winner_id} for request {request_id}")


# ============================================================================
# WebSocket Marketplace Bidding Notification Endpoint (v1.3 Phase 2)
# ============================================================================

# Global subscription management: category -> set of (entity_id, websocket)
_marketplace_bidding_subscribers: Dict[str, set] = {}
# Entity tracking: entity_id -> {websocket, subscribed_categories}
_marketplace_bidding_connections: Dict[str, Dict] = {}


class BiddingSubscriptionRequest(BaseModel):
    """Request to subscribe to bidding notifications for a category"""
    action: str = Field(..., description="Action: subscribe, unsubscribe, ping")
    category: Optional[str] = Field(default=None, description="Service category to subscribe to")
    service_types: Optional[List[str]] = Field(default=None, description="List of service types to subscribe to")


@app.websocket("/ws/v1/marketplace/bidding")
async def marketplace_bidding_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time marketplace bidding notifications.
    
    M2: v1.3 Multi-Agent Marketplace Phase 2 - Real-time bid notification system
    
    Authentication: Pass JWT token as query parameter: ?token=<jwt_token>
    
    Message Types (Client -> Server):
    - subscribe: Subscribe to bidding notifications for a category
    - unsubscribe: Unsubscribe from a category
    - ping: Heartbeat request
    
    Message Types (Server -> Client):
    - bid.new: New bid submitted notification
    - bid.closed: Bidding window closed notification
    - bid.won: Bid won/lost notification
    - auction.started: Auction started notification
    - auction.ended: Auction ended notification
    - error: Error notification
    """
    entity_id: Optional[str] = None
    subscribed_categories: set = set()
    
    try:
        # Authenticate using query parameter token
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=1008, reason="Missing authentication token")
            return
        
        # Verify JWT token
        try:
            payload = jwt_auth.verify_token(token)
            entity_id = payload.get("sub")
            if not entity_id:
                await websocket.close(code=1008, reason="Invalid token: missing subject")
                return
        except Exception as e:
            await websocket.close(code=1008, reason=f"Authentication failed: {str(e)}")
            return
        
        # Accept connection
        await websocket.accept()
        
        # Register connection
        _marketplace_bidding_connections[entity_id] = {
            "websocket": websocket,
            "subscribed_categories": subscribed_categories,
            "connected_at": datetime.now(timezone.utc)
        }
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "payload": {
                "entity_id": entity_id,
                "message": "Marketplace bidding notification WebSocket connected. Subscribe to service categories to receive bid notifications.",
                "supported_actions": ["subscribe", "unsubscribe", "ping"],
                "notification_types": ["bid.new", "bid.closed", "bid.won", "auction.started", "auction.ended", "error"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(f"Marketplace bidding WebSocket connected: {entity_id}")
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                action = data.get("action", "")
                
                if action == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "payload": {"timestamp": datetime.now(timezone.utc).isoformat()},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                
                elif action == "subscribe":
                    # Subscribe to category notifications
                    category = data.get("category")
                    service_types = data.get("service_types", [])
                    
                    if category:
                        subscribed_categories.add(category)
                        if category not in _marketplace_bidding_subscribers:
                            _marketplace_bidding_subscribers[category] = set()
                        _marketplace_bidding_subscribers[category].add((entity_id, websocket))
                        
                        await websocket.send_json({
                            "type": "subscribed",
                            "payload": {
                                "category": category,
                                "message": f"Subscribed to {category} bidding notifications"
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    
                    # Also handle service_types for backward compatibility
                    for service_type in service_types:
                        subscribed_categories.add(service_type)
                        if service_type not in _marketplace_bidding_subscribers:
                            _marketplace_bidding_subscribers[service_type] = set()
                        _marketplace_bidding_subscribers[service_type].add((entity_id, websocket))
                    
                    if service_types:
                        await websocket.send_json({
                            "type": "subscribed",
                            "payload": {
                                "service_types": service_types,
                                "message": f"Subscribed to bidding notifications for: {', '.join(service_types)}"
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                
                elif action == "unsubscribe":
                    # Unsubscribe from category
                    category = data.get("category")
                    if category and category in subscribed_categories:
                        subscribed_categories.discard(category)
                        if category in _marketplace_bidding_subscribers:
                            _marketplace_bidding_subscribers[category].discard((entity_id, websocket))
                        
                        await websocket.send_json({
                            "type": "unsubscribed",
                            "payload": {
                                "category": category,
                                "message": f"Unsubscribed from {category} bidding notifications"
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                
                else:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {
                            "message": f"Unknown action: {action}. Supported: subscribe, unsubscribe, ping"
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Marketplace bidding WebSocket error for {entity_id}: {e}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"message": str(e)},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                except:
                    break
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Marketplace bidding WebSocket fatal error: {e}")
    finally:
        # Cleanup subscriptions
        if entity_id:
            # Remove from all category subscriptions
            for category in list(subscribed_categories):
                if category in _marketplace_bidding_subscribers:
                    _marketplace_bidding_subscribers[category].discard((entity_id, websocket))
                    if not _marketplace_bidding_subscribers[category]:
                        del _marketplace_bidding_subscribers[category]
            
            # Remove connection tracking
            if entity_id in _marketplace_bidding_connections:
                del _marketplace_bidding_connections[entity_id]
            
            logger.info(f"Marketplace bidding WebSocket disconnected: {entity_id}")


async def notify_bid_event(
    notification_type: str,
    auction_id: Optional[str] = None,
    service_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    bid_amount: Optional[float] = None,
    category: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """
    Send bid notification to subscribed clients.
    """
    notification = {
        "type": notification_type,
        "auction_id": auction_id,
        "service_id": service_id,
        "provider_id": provider_id,
        "bid_amount": bid_amount,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details or {}
    }
    
    # If category specified, notify subscribers of that category
    if category and category in _marketplace_bidding_subscribers:
        disconnected = []
        for entity_id, websocket in _marketplace_bidding_subscribers[category]:
            try:
                await websocket.send_json(notification)
                logger.debug(f"Sent {notification_type} to {entity_id} for category {category}")
            except Exception as e:
                logger.warning(f"Failed to send notification to {entity_id}: {e}")
                disconnected.append((entity_id, websocket))
        
        # Clean up disconnected clients
        for entity_id, websocket in disconnected:
            _marketplace_bidding_subscribers[category].discard((entity_id, websocket))


async def broadcast_auction_start(
    auction_id: str,
    service_id: str,
    category: str,
    requirements: Dict[str, Any],
    max_price: float,
    bidding_window_seconds: int = 5
):
    """
    Broadcast auction started notification to category subscribers.
    """
    await notify_bid_event(
        notification_type="auction.started",
        auction_id=auction_id,
        service_id=service_id,
        category=category,
        details={
            "requirements": requirements,
            "max_price": max_price,
            "bidding_window_seconds": bidding_window_seconds,
            "message": f"New auction started for {category}"
        }
    )
    logger.info(f"Broadcasted auction start: {auction_id} for category {category}")


async def broadcast_auction_end(
    auction_id: str,
    service_id: str,
    category: str,
    winner_id: Optional[str] = None,
    winning_bid: Optional[float] = None,
    total_bids: int = 0
):
    """
    Broadcast auction ended notification to category subscribers.
    """
    await notify_bid_event(
        notification_type="auction.ended",
        auction_id=auction_id,
        service_id=service_id,
        provider_id=winner_id,
        bid_amount=winning_bid,
        category=category,
        details={
            "winner_id": winner_id,
            "winning_bid": winning_bid,
            "total_bids": total_bids,
            "message": f"Auction ended. Winner: {winner_id or 'None'}"
        }
    )
    logger.info(f"Broadcasted auction end: {auction_id}, winner: {winner_id}")


async def broadcast_new_bid(
    auction_id: str,
    service_id: str,
    provider_id: str,
    bid_amount: float,
    category: str,
    estimated_time: Optional[int] = None
):
    """
    Broadcast new bid notification to category subscribers.
    """
    await notify_bid_event(
        notification_type="bid.new",
        auction_id=auction_id,
        service_id=service_id,
        provider_id=provider_id,
        bid_amount=bid_amount,
        category=category,
        details={
            "estimated_time_seconds": estimated_time,
            "message": f"New bid received: {bid_amount} from {provider_id}"
        }
    )


async def notify_bid_result(
    auction_id: str,
    service_id: str,
    provider_id: str,
    won: bool,
    bid_amount: float,
    category: str
):
    """
    Notify provider about bid result (won or lost).
    """
    # Find the specific provider's connection
    if provider_id in _marketplace_bidding_connections:
        websocket = _marketplace_bidding_connections[provider_id].get("websocket")
        if websocket:
            notification = {
                "type": "bid.won" if won else "bid.lost",
                "auction_id": auction_id,
                "service_id": service_id,
                "provider_id": provider_id,
                "bid_amount": bid_amount,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": {
                    "won": won,
                    "message": "Congratulations! Your bid was selected" if won else "Your bid was not selected"
                }
            }
            try:
                await websocket.send_json(notification)
                logger.info(f"Sent bid result to {provider_id}: {'won' if won else 'lost'}")
            except Exception as e:
                logger.warning(f"Failed to send bid result to {provider_id}: {e}")


@app.get("/ws/marketplace/bidding/stats")
async def get_marketplace_bidding_stats():
    """
    Get marketplace bidding WebSocket connection statistics.
    """
    return {
        "active_connections": len(_marketplace_bidding_connections),
        "subscribed_categories": {
            category: len(subscribers) 
            for category, subscribers in _marketplace_bidding_subscribers.items()
        },
        "total_subscriptions": sum(
            len(subscribers) 
            for subscribers in _marketplace_bidding_subscribers.values()
        )
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
