#!/usr/bin/env python3
"""
Peer Communication Service
AI間の相互通信を実現するサービス

Protocol v1.0対応:
- Ed25519署名によるメッセージ認証（必須）
- リプレイ攻撃防止（タイムスタンプ+ノンス）
- 公開鍵レジストリによるピア管理
- Capability exchange（機能交換）
- Task delegation（タスク委譲）
- Heartbeat（死活監視）
- Peer statistics（統計情報）

TODO v1.1:
- X25519/AES-256-GCM payload encryption ✅ (implemented in crypto.py:1220-1330)
- Session management with UUID ✅ (implemented: session_manager.py)
- Sequence numbers for ordering ✅ (implemented: line 1450-1480)
- Chunked message transfer ✅ (implemented: ChunkInfo class, line 180-220)
- Rate limiting ✅ (implemented: line 2000-2100)
- Ed25519→X25519 key conversion ✅ (implemented in crypto.py:1236-1279)
"""

import asyncio
import base64
import json
import logging
import os
import random
import secrets
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Callable, Awaitable, Dict, List, Any, Tuple
import hashlib
import uuid

import aiohttp
from aiohttp import ClientTimeout, ClientError

# 暗号モジュールのインポート（複数パターン対応）
CRYPTO_AVAILABLE = False
try:
    # パターン1: パッケージとして実行される場合
    from services.crypto import (
        HandshakeChallenge,  # ハンドシェイク用
        E2EEncryption,  # X25519 + AES-256-GCM 暗号化
        WalletManager,  # ウォレット管理（統合済み）
    )
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        # パターン2: スクリプトとして直接実行される場合
        from crypto import (
            HandshakeChallenge,
            E2EEncryption,
            WalletManager,
        )
        CRYPTO_AVAILABLE = True
    except ImportError:
        pass  # CRYPTO_AVAILABLE = False

# E2E暗号化モジュールのインポート（e2e_crypto.py統合）
E2E_CRYPTO_AVAILABLE = False
try:
    from services.e2e_crypto import (
        E2ECryptoManager,
        E2EHandshakeHandler,
        SessionState as E2ESessionState,
    )
    E2E_CRYPTO_AVAILABLE = True
except ImportError:
    try:
        from e2e_crypto import (
            E2ECryptoManager,
            E2EHandshakeHandler,
            SessionState as E2ESessionState,
        )
        E2E_CRYPTO_AVAILABLE = True
    except ImportError:
        pass  # E2E_CRYPTO_AVAILABLE = False

# PeerMonitorのインポート（複数パターン対応）
MONITOR_AVAILABLE = False
try:
    from services.peer_monitor import (
        PeerMonitor, ConnectionEvent, ConnectionMetrics,
        ConnectionEventHandler, PeerDiscoveryHandler
    )
    MONITOR_AVAILABLE = True
except ImportError:
    try:
        from peer_monitor import (
            PeerMonitor, ConnectionEvent, ConnectionMetrics,
            ConnectionEventHandler, PeerDiscoveryHandler
        )
        MONITOR_AVAILABLE = True
    except ImportError:
        pass  # MONITOR_AVAILABLE = False

# Connection Poolのインポート（複数パターン対応）
CONNECTION_POOL_AVAILABLE = False
try:
    from services.connection_pool import (
        PooledConnectionManager,
        get_connection_pool,
        init_connection_pool,
        shutdown_connection_pool
    )
    CONNECTION_POOL_AVAILABLE = True
except ImportError:
    try:
        from connection_pool import (
            PooledConnectionManager,
            get_connection_pool,
            init_connection_pool,
            shutdown_connection_pool
        )
        CONNECTION_POOL_AVAILABLE = True
    except ImportError:
        pass  # CONNECTION_POOL_AVAILABLE = False

# Chunked Transferのインポート（Chunk Management Unification）
CHUNKED_TRANSFER_AVAILABLE = False
try:
    from services.chunked_transfer import ChunkInfo, ChunkManager
    CHUNKED_TRANSFER_AVAILABLE = True
except ImportError:
    try:
        from chunked_transfer import ChunkInfo, ChunkManager
        CHUNKED_TRANSFER_AVAILABLE = True
    except ImportError:
        pass  # CHUNKED_TRANSFER_AVAILABLE = False

# Multi-hop Routerのインポート（v1.2 Store-and-Forward）
MULTI_HOP_AVAILABLE = False
try:
    from services.multi_hop_router import MultiHopRouter, MessageStatus, QueuedMessage
    MULTI_HOP_AVAILABLE = True
except ImportError:
    try:
        from multi_hop_router import MultiHopRouter, MessageStatus, QueuedMessage
        MULTI_HOP_AVAILABLE = True
    except ImportError:
        pass  # MULTI_HOP_AVAILABLE = False

# SessionManagerインポート（新しいUUIDベースのセッション管理）
SESSION_MANAGER_AVAILABLE = False
try:
    from services.session_manager import SessionManager as NewSessionManager
    SESSION_MANAGER_AVAILABLE = True
except ImportError:
    try:
        from session_manager import SessionManager as NewSessionManager
        SESSION_MANAGER_AVAILABLE = True
    except ImportError:
        pass

# Token Systemインポート（トークン経済統合）
TOKEN_SYSTEM_AVAILABLE = False
try:
    from services.token_system import (
        get_wallet, get_task_contract, get_reputation_contract,
        TaskContract, ReputationContract, TaskStatus
    )
    TOKEN_SYSTEM_AVAILABLE = True
except ImportError:
    try:
        from token_system import (
            get_wallet, get_task_contract, get_reputation_contract,
            TaskContract, ReputationContract, TaskStatus
        )
        TOKEN_SYSTEM_AVAILABLE = True
    except ImportError:
        pass  # SESSION_MANAGER_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 型エイリアス
MessageHandler = Callable[[dict], Awaitable[None]]

# Error codes for v1.0 handshake protocol
INVALID_VERSION = "INVALID_VERSION"
INVALID_SIGNATURE = "INVALID_SIGNATURE"
REPLAY_DETECTED = "REPLAY_DETECTED"
UNKNOWN_SENDER = "UNKNOWN_SENDER"
SESSION_EXPIRED = "SESSION_EXPIRED"
SEQUENCE_ERROR = "SEQUENCE_ERROR"
DECRYPTION_FAILED = "DECRYPTION_FAILED"
HANDSHAKE_TIMEOUT = "HANDSHAKE_TIMEOUT"


class PeerStatus(Enum):
    """ピアの生存状態"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class SessionState(Enum):
    """Session state for v1.0 handshake protocol"""
    INITIAL = "initial"
    HANDSHAKE_SENT = "handshake_sent"
    HANDSHAKE_ACKED = "handshake_acked"
    ESTABLISHED = "established"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass
class Session:
    """Session dataclass for v1.0 handshake protocol
    
    Attributes:
        session_id: UUID v4 session identifier
        peer_id: Remote peer entity ID
        state: Current session state
        sequence_num: Last sent sequence number
        expected_sequence: Next expected receive sequence number
        created_at: Session creation timestamp
        last_activity: Last activity timestamp
        peer_public_key: Peer's Ed25519 public key (hex)
        challenge: Handshake challenge for verification
    """
    session_id: str
    peer_id: str
    state: SessionState = SessionState.INITIAL
    sequence_num: int = 0
    expected_sequence: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    peer_public_key: Optional[str] = None
    challenge: Optional[str] = None
    
    def increment_sequence(self) -> int:
        """Increment and return next sequence number"""
        self.sequence_num += 1
        self.last_activity = datetime.now(timezone.utc)
        return self.sequence_num
    
    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = datetime.now(timezone.utc)
    
    def is_expired(self, max_age_seconds: int = 3600) -> bool:
        """Check if session is expired"""
        age = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return age > max_age_seconds
    
    def is_handshake_expired(self, max_handshake_seconds: int = 300) -> bool:
        """Check if handshake is expired (5 minutes default)
        
        Handshake sessions have shorter timeout than established sessions.
        
        Args:
            max_handshake_seconds: Maximum handshake duration (default: 300s = 5min)
            
        Returns:
            True if handshake has timed out
        """
        age = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return age > max_handshake_seconds
    
    def to_dict(self) -> dict:
        """Convert session to dictionary"""
        return {
            "session_id": self.session_id,
            "peer_id": self.peer_id,
            "state": self.state.value,
            "sequence_num": self.sequence_num,
            "expected_sequence": self.expected_sequence,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat()
        }
    
    def validate_state_transition(self, new_state: SessionState) -> Tuple[bool, Optional[str]]:
        """
        Validate session state transition (S9)
        
        Valid transitions:
        - INITIAL -> HANDSHAKE_SENT
        - HANDSHAKE_SENT -> HANDSHAKE_ACKED
        - HANDSHAKE_ACKED -> ESTABLISHED
        - ANY -> ERROR (on error)
        - ANY -> EXPIRED (on expiry)
        
        Args:
            new_state: Target state
            
        Returns:
            (is_valid, error_message)
        """
        valid_transitions = {
            SessionState.INITIAL: [SessionState.HANDSHAKE_SENT, SessionState.ERROR],
            SessionState.HANDSHAKE_SENT: [SessionState.HANDSHAKE_ACKED, SessionState.ERROR],
            SessionState.HANDSHAKE_ACKED: [SessionState.ESTABLISHED, SessionState.ERROR],
            SessionState.ESTABLISHED: [SessionState.ERROR, SessionState.EXPIRED],
            SessionState.ERROR: [SessionState.INITIAL],  # Can retry from error
            SessionState.EXPIRED: []  # Terminal state
        }
        
        allowed = valid_transitions.get(self.state, [])
        
        if new_state in allowed:
            return True, None
        else:
            return False, f"Invalid transition: {self.state.value} -> {new_state.value}"
    
    def transition_to(self, new_state: SessionState) -> Tuple[bool, Optional[str]]:
        """
        Attempt state transition with validation (S9)
        
        Args:
            new_state: Target state
            
        Returns:
            (success, error_message)
        """
        is_valid, error = self.validate_state_transition(new_state)
        if is_valid:
            old_state = self.state
            self.state = new_state
            self.update_activity()
            logger.debug(f"Session {self.session_id}: {old_state.value} -> {new_state.value}")
            return True, None
        else:
            logger.warning(f"Session {self.session_id}: rejected transition {error}")
            return False, error
    
    def can_receive_messages(self) -> bool:
        """Check if session can receive messages (established and not expired)"""
        return self.state == SessionState.ESTABLISHED and not self.is_expired()
    
    def is_handshake_complete(self) -> bool:
        """Check if handshake is complete"""
        return self.state == SessionState.ESTABLISHED


# ========== v1.1 6-Step Handshake Implementation ==========

class V11SessionState(Enum):
    """Session states for v1.1 6-step handshake protocol with PFS
    
    States:
    - INITIAL: No session exists
    - HANDSHAKE_INIT_SENT: Step 1 completed (sent handshake_init)
    - HANDSHAKE_ACK_RECEIVED: Step 2 completed (received handshake_init_ack)
    - CHALLENGE_SENT: Step 3 completed (sent challenge_response)
    - SESSION_ESTABLISHED: Step 4 completed (received session_established)
    - SESSION_CONFIRMED: Step 5 completed (sent session_confirm)
    - READY: Step 6 completed (received ready, encryption active)
    - ERROR: Session error
    - EXPIRED: Session timeout
    """
    INITIAL = "initial"
    HANDSHAKE_INIT_SENT = "handshake_init_sent"
    HANDSHAKE_ACK_RECEIVED = "handshake_ack_received"
    CHALLENGE_SENT = "challenge_sent"
    SESSION_ESTABLISHED = "session_established"
    SESSION_CONFIRMED = "session_confirmed"
    READY = "ready"
    ERROR = "error"
    EXPIRED = "expired"


@dataclass
class V11Session:
    """Session dataclass for v1.1 6-step handshake protocol with PFS
    
    Attributes:
        session_id: UUID v4 session identifier
        peer_id: Remote peer entity ID
        state: Current session state (V11SessionState)
        sequence_num: Last sent sequence number
        expected_sequence: Next expected receive sequence number
        created_at: Session creation timestamp
        last_activity: Last activity timestamp
        peer_public_key: Peer's Ed25519 public key (hex)
        peer_ephemeral_public_key: Peer's X25519 ephemeral public key (hex)
        ephemeral_private_key: Our X25519 ephemeral private key (hex)
        ephemeral_public_key: Our X25519 ephemeral public key (hex)
        challenge: Handshake challenge for verification
        challenge_response: Signed challenge response
        session_key: Derived AES-256-GCM session key
        handshake_hash: Hash of handshake messages for key derivation
    """
    session_id: str
    peer_id: str
    state: V11SessionState = V11SessionState.INITIAL
    sequence_num: int = 0
    expected_sequence: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    peer_public_key: Optional[str] = None
    peer_ephemeral_public_key: Optional[str] = None
    ephemeral_private_key: Optional[str] = None
    ephemeral_public_key: Optional[str] = None
    challenge: Optional[str] = None
    challenge_response: Optional[str] = None
    session_key: Optional[bytes] = None
    handshake_hash: Optional[str] = None
    
    def increment_sequence(self) -> int:
        """Increment and return next sequence number"""
        self.sequence_num += 1
        self.last_activity = datetime.now(timezone.utc)
        return self.sequence_num
    
    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = datetime.now(timezone.utc)
    
    def is_expired(self, max_age_seconds: int = 3600) -> bool:
        """Check if session is expired"""
        age = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return age > max_age_seconds
    
    def is_handshake_expired(self, max_handshake_seconds: int = 300) -> bool:
        """Check if handshake is expired (5 minutes default)"""
        age = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return age > max_handshake_seconds
    
    def to_dict(self) -> dict:
        """Convert session to dictionary (excludes sensitive keys)"""
        return {
            "session_id": self.session_id,
            "peer_id": self.peer_id,
            "state": self.state.value,
            "sequence_num": self.sequence_num,
            "expected_sequence": self.expected_sequence,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "has_session_key": self.session_key is not None,
            "ephemeral_public_key": self.ephemeral_public_key[:32] + "..." if self.ephemeral_public_key else None
        }
    
    def validate_state_transition(self, new_state: V11SessionState) -> Tuple[bool, Optional[str]]:
        """
        Validate v1.1 session state transition
        
        Valid transitions:
        - INITIAL -> HANDSHAKE_INIT_SENT
        - HANDSHAKE_INIT_SENT -> HANDSHAKE_ACK_RECEIVED
        - HANDSHAKE_ACK_RECEIVED -> CHALLENGE_SENT
        - CHALLENGE_SENT -> SESSION_ESTABLISHED
        - SESSION_ESTABLISHED -> SESSION_CONFIRMED
        - SESSION_CONFIRMED -> READY
        - ANY -> ERROR (on error)
        - ANY -> EXPIRED (on expiry)
        """
        valid_transitions = {
            V11SessionState.INITIAL: [V11SessionState.HANDSHAKE_INIT_SENT, V11SessionState.ERROR],
            V11SessionState.HANDSHAKE_INIT_SENT: [V11SessionState.HANDSHAKE_ACK_RECEIVED, V11SessionState.ERROR],
            V11SessionState.HANDSHAKE_ACK_RECEIVED: [V11SessionState.CHALLENGE_SENT, V11SessionState.ERROR],
            V11SessionState.CHALLENGE_SENT: [V11SessionState.SESSION_ESTABLISHED, V11SessionState.ERROR],
            V11SessionState.SESSION_ESTABLISHED: [V11SessionState.SESSION_CONFIRMED, V11SessionState.ERROR],
            V11SessionState.SESSION_CONFIRMED: [V11SessionState.READY, V11SessionState.ERROR],
            V11SessionState.READY: [V11SessionState.ERROR, V11SessionState.EXPIRED],
            V11SessionState.ERROR: [V11SessionState.INITIAL],  # Can retry from error
            V11SessionState.EXPIRED: []  # Terminal state
        }
        
        allowed = valid_transitions.get(self.state, [])
        
        if new_state in allowed:
            return True, None
        else:
            return False, f"Invalid transition: {self.state.value} -> {new_state.value}"
    
    def transition_to(self, new_state: V11SessionState) -> Tuple[bool, Optional[str]]:
        """Attempt state transition with validation"""
        is_valid, error = self.validate_state_transition(new_state)
        if is_valid:
            old_state = self.state
            self.state = new_state
            self.update_activity()
            logger.debug(f"V11Session {self.session_id}: {old_state.value} -> {new_state.value}")
            return True, None
        else:
            logger.warning(f"V11Session {self.session_id}: rejected transition {error}")
            return False, error
    
    def is_encryption_ready(self) -> bool:
        """Check if E2E encryption is ready (READY state and has session key)"""
        return self.state == V11SessionState.READY and self.session_key is not None
    
    def can_send_encrypted(self) -> bool:
        """Check if session can send encrypted messages"""
        return self.is_encryption_ready() and not self.is_expired()


# Error codes for v1.1 protocol
V11_INVALID_VERSION = "INVALID_VERSION"
V11_INVALID_SIGNATURE = "INVALID_SIGNATURE"
V11_REPLAY_DETECTED = "REPLAY_DETECTED"
V11_SESSION_EXPIRED = "SESSION_EXPIRED"
V11_SEQUENCE_ERROR = "SEQUENCE_ERROR"
V11_DECRYPTION_FAILED = "DECRYPTION_FAILED"
V11_CHALLENGE_EXPIRED = "CHALLENGE_EXPIRED"
V11_CHALLENGE_INVALID = "CHALLENGE_INVALID"
V11_HANDSHAKE_IN_PROGRESS = "HANDSHAKE_IN_PROGRESS"
V11_SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
V11_ENCRYPTION_NOT_READY = "ENCRYPTION_NOT_READY"
V11_INVALID_STATE = "INVALID_STATE"


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10  # Token bucket burst size
    block_duration_seconds: int = 300  # Block for 5 minutes on violation


class RateLimiter:
    """Rate limiter for peer communication
    
    Protocol v1.1対応:
    - Per-peer rate limiting
    - Token bucket algorithm
    - Automatic blocking on violation
    - Configurable limits per message type
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._peer_buckets: Dict[str, Dict[str, Any]] = {}  # peer_id -> token bucket
        self._blocked_peers: Dict[str, datetime] = {}  # peer_id -> block expiry
        self._lock = asyncio.Lock()
        
    def is_blocked(self, peer_id: str) -> bool:
        """Check if peer is currently blocked"""
        if peer_id in self._blocked_peers:
            if datetime.now(timezone.utc) < self._blocked_peers[peer_id]:
                return True
            else:
                del self._blocked_peers[peer_id]
        return False
    
    async def check_rate_limit(self, peer_id: str, message_type: str = "default") -> Tuple[bool, Optional[float]]:
        """Check if request is within rate limit
        
        Returns:
            (allowed, retry_after_seconds)
        """
        async with self._lock:
            # Check if peer is blocked
            if self.is_blocked(peer_id):
                retry_after = (self._blocked_peers[peer_id] - datetime.now(timezone.utc)).total_seconds()
                return False, retry_after
            
            now = datetime.now(timezone.utc)
            
            # Initialize or get peer bucket
            if peer_id not in self._peer_buckets:
                self._peer_buckets[peer_id] = {
                    "tokens": self.config.burst_size,
                    "last_update": now,
                    "request_count_minute": 0,
                    "minute_window_start": now,
                    "request_count_hour": 0,
                    "hour_window_start": now,
                }
            
            bucket = self._peer_buckets[peer_id]
            
            # Reset minute window
            minute_elapsed = (now - bucket["minute_window_start"]).total_seconds()
            if minute_elapsed >= 60:
                bucket["request_count_minute"] = 0
                bucket["minute_window_start"] = now
            
            # Reset hour window
            hour_elapsed = (now - bucket["hour_window_start"]).total_seconds()
            if hour_elapsed >= 3600:
                bucket["request_count_hour"] = 0
                bucket["hour_window_start"] = now
            
            # Check minute limit
            if bucket["request_count_minute"] >= self.config.requests_per_minute:
                self._block_peer(peer_id)
                return False, 60.0
            
            # Check hour limit
            if bucket["request_count_hour"] >= self.config.requests_per_hour:
                self._block_peer(peer_id)
                return False, 3600.0
            
            # Token bucket: add tokens based on time elapsed
            time_elapsed = (now - bucket["last_update"]).total_seconds()
            tokens_to_add = time_elapsed * (self.config.requests_per_minute / 60.0)
            bucket["tokens"] = min(self.config.burst_size, bucket["tokens"] + tokens_to_add)
            bucket["last_update"] = now
            
            # Check if we have tokens available
            if bucket["tokens"] < 1.0:
                retry_after = (1.0 - bucket["tokens"]) / (self.config.requests_per_minute / 60.0)
                return False, retry_after
            
            # Consume token
            bucket["tokens"] -= 1.0
            bucket["request_count_minute"] += 1
            bucket["request_count_hour"] += 1
            
            return True, None
    
    def _block_peer(self, peer_id: str) -> None:
        """Block a peer for configured duration"""
        self._blocked_peers[peer_id] = datetime.now(timezone.utc) + timedelta(
            seconds=self.config.block_duration_seconds
        )
        logger.warning(f"Rate limit exceeded for peer {peer_id}, blocked for {self.config.block_duration_seconds}s")
    
    async def get_peer_stats(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """Get rate limit stats for a peer"""
        async with self._lock:
            if peer_id not in self._peer_buckets:
                return None
            
            bucket = self._peer_buckets[peer_id]
            return {
                "tokens_remaining": bucket["tokens"],
                "requests_this_minute": bucket["request_count_minute"],
                "requests_this_hour": bucket["request_count_hour"],
                "is_blocked": self.is_blocked(peer_id),
            }
    
    async def cleanup_old_peers(self, max_inactive_seconds: int = 3600) -> int:
        """Remove inactive peers from tracking"""
        async with self._lock:
            now = datetime.now(timezone.utc)
            to_remove = []
            
            for peer_id, bucket in self._peer_buckets.items():
                if (now - bucket["last_update"]).total_seconds() > max_inactive_seconds:
                    to_remove.append(peer_id)
            
            for peer_id in to_remove:
                del self._peer_buckets[peer_id]
                if peer_id in self._blocked_peers:
                    del self._blocked_peers[peer_id]
            
            return len(to_remove)


class SessionManager:
    """Session管理クラス - UUIDベースのセッション管理
    
    Protocol v1.0対応:
    - UUID v4によるセッションID生成
    - セッション有効期限管理
    - ピアとの1:1セッション対応
    - シーケンス番号管理
    """
    
    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}  # session_id -> SessionInfo
        self._peer_sessions: Dict[str, str] = {}  # peer_id -> session_id (1:1)
        self._lock = asyncio.Lock()
        logger.info("SessionManager initialized")
    
    async def start(self) -> None:
        """セッションマネージャーを開始"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("SessionManager started")
    
    async def stop(self) -> None:
        """セッションマネージャーを停止"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("SessionManager stopped")
    
    async def create_session(
        self,
        peer_id: str,
        peer_public_key: Optional[str] = None,
        ttl_seconds: Optional[int] = None
    ) -> Session:
        """新規セッションを作成
        
        Args:
            peer_id: 対向ピアのエンティティID
            peer_public_key: ピアのEd25519公開鍵（hex）
            ttl_seconds: セッション有効期限（秒）
            
        Returns:
            新規作成されたSessionオブジェクト
        """
        async with self._lock:
            # 既存セッションがあれば削除
            if peer_id in self._peer_sessions:
                old_session_id = self._peer_sessions[peer_id]
                if old_session_id in self._sessions:
                    del self._sessions[old_session_id]
                    logger.debug(f"Replaced old session {old_session_id} for peer {peer_id}")
            
            # 新規セッション作成
            session_id = str(uuid.uuid4())
            session = Session(
                session_id=session_id,
                peer_id=peer_id,
                state=SessionState.INITIAL,
                peer_public_key=peer_public_key
            )
            
            self._sessions[session_id] = session
            self._peer_sessions[peer_id] = session_id
            
            logger.info(f"Created session {session_id} for peer {peer_id}")
            return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """セッションIDからセッションを取得
        
        Args:
            session_id: セッションUUID
            
        Returns:
            Sessionオブジェクト、存在しない場合はNone
        """
        async with self._lock:
            return self._sessions.get(session_id)
    
    async def get_session_by_peer(self, peer_id: str) -> Optional[Session]:
        """ピアIDからセッションを取得（1:1マッピング）
        
        Args:
            peer_id: エンティティID
            
        Returns:
            Sessionオブジェクト、存在しない場合はNone
        """
        async with self._lock:
            session_id = self._peer_sessions.get(peer_id)
            if session_id:
                return self._sessions.get(session_id)
            return None
    
    async def update_session_state(
        self,
        session_id: str,
        new_state: SessionState
    ) -> bool:
        """セッション状態を更新
        
        Args:
            session_id: セッションUUID
            new_state: 新しい状態
            
        Returns:
            更新成功した場合True
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                old_state = session.state
                session.state = new_state
                session.update_activity()
                logger.debug(f"Session {session_id} state: {old_state.value} -> {new_state.value}")
                return True
            return False
    
    async def update_activity(self, session_id: str) -> bool:
        """セッションのアクティビティを更新
        
        Args:
            session_id: セッションUUID
            
        Returns:
            更新成功した場合True
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.update_activity()
                return True
            return False
    
    async def is_session_valid(
        self,
        session_id: str,
        required_state: Optional[SessionState] = None
    ) -> bool:
        """セッションの有効性を検証
        
        Args:
            session_id: セッションUUID
            required_state: 必要な状態（指定時は状態も確認）
            
        Returns:
            有効な場合True
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            if session.state == SessionState.EXPIRED:
                return False
            if session.is_expired(self.default_ttl):
                return False
            if required_state and session.state != required_state:
                return False
            return True
    
    async def terminate_session(self, session_id: str) -> bool:
        """セッションを終了（期限切れに設定）
        
        Args:
            session_id: セッションUUID
            
        Returns:
            成功した場合True
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.state = SessionState.EXPIRED
                # peer_sessionsからも削除
                if session.peer_id in self._peer_sessions:
                    if self._peer_sessions[session.peer_id] == session_id:
                        del self._peer_sessions[session.peer_id]
                logger.info(f"Terminated session {session_id}")
                return True
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """セッションを完全に削除
        
        Args:
            session_id: セッションUUID
            
        Returns:
            成功した場合True
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                if session.peer_id in self._peer_sessions:
                    if self._peer_sessions[session.peer_id] == session_id:
                        del self._peer_sessions[session.peer_id]
                logger.info(f"Deleted session {session_id}")
                return True
            return False
    
    async def get_all_sessions(self) -> List[Session]:
        """全セッションのリストを取得"""
        async with self._lock:
            return list(self._sessions.values())
    
    async def get_active_sessions(self) -> List[Session]:
        """アクティブなセッションのリストを取得"""
        async with self._lock:
            return [
                s for s in self._sessions.values()
                if s.state != SessionState.EXPIRED and not s.is_expired(self.default_ttl)
            ]
    
    async def cleanup_expired(self) -> int:
        """期限切れセッションをクリーンアップ
        
        Returns:
            削除されたセッション数
        """
        async with self._lock:
            expired_ids = []
            for session_id, session in self._sessions.items():
                if session.is_expired(self.default_ttl) or session.state == SessionState.EXPIRED:
                    expired_ids.append(session_id)
            
            for session_id in expired_ids:
                session = self._sessions.pop(session_id, None)
                if session and session.peer_id in self._peer_sessions:
                    if self._peer_sessions[session.peer_id] == session_id:
                        del self._peer_sessions[session.peer_id]
            
            if expired_ids:
                logger.info(f"Cleaned up {len(expired_ids)} expired sessions")
            return len(expired_ids)
    
    async def _cleanup_loop(self) -> None:
        """定期クリーンアップループ"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_expired()
            except Exception as e:
                logger.error(f"Error in session cleanup loop: {e}")
    
    def get_stats(self) -> dict:
        """セッション統計を取得"""
        total = len(self._sessions)
        expired = sum(1 for s in self._sessions.values() if s.state == SessionState.EXPIRED)
        active = total - expired
        return {
            "total_sessions": total,
            "active_sessions": active,
            "expired_sessions": expired,
            "peer_count": len(self._peer_sessions)
        }


    async def get_session(self, session_id: str) -> Optional[Session]:
        """セッションを取得"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_activity = datetime.now(timezone.utc)
            return session
    
    async def get_session_by_peer(self, peer_id: str) -> Optional[Session]:
        """ピアIDからセッションを取得"""
        async with self._lock:
            session_id = self._peer_sessions.get(peer_id)
            if not session_id:
                return None
            session = self._sessions.get(session_id)
            if session:
                session.last_activity = datetime.now(timezone.utc)
            return session
    
    async def establish_session(self, session_id: str) -> bool:
        """セッションを確立状態にする"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            session.established = True
            session.last_activity = datetime.now(timezone.utc)
            logger.info(f"Session {session_id} established")
            return True
    
    async def close_session(self, session_id: str) -> bool:
        """セッションを終了"""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return False
            if session.peer_id in self._peer_sessions:
                del self._peer_sessions[session.peer_id]
            logger.info(f"Closed session {session_id}")
            return True
    
    async def get_next_send_seq(self, session_id: str) -> Optional[int]:
        """送信シーケンス番号を取得・インクリメント"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            seq = session.next_send_seq
            session.next_send_seq += 1
            session.last_activity = datetime.now(timezone.utc)
            return seq
    
    async def validate_received_seq(self, session_id: str, seq_num: int) -> bool:
        """
        受信シーケンス番号を検証
        
        Returns:
            True: 有効なシーケンス番号
            False: 重複または無効
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            
            # 既に受信済みかチェック
            if seq_num in session.received_seq_window:
                logger.debug(f"Duplicate sequence number {seq_num} for session {session_id}")
                return False
            
            # ウィンドウサイズを超える古いシーケンスは無効
            if seq_num <= session.max_received_seq - self._max_seq_window:
                logger.debug(f"Sequence {seq_num} too old for session {session_id}")
                return False
            
            # シーケンスを記録
            session.received_seq_window.add(seq_num)
            session.max_received_seq = max(session.max_received_seq, seq_num)
            
            # ウィンドウサイズを制限
            if len(session.received_seq_window) > self._max_seq_window:
                # 古いエントリを削除
                min_seq = min(session.received_seq_window)
                session.received_seq_window.discard(min_seq)
            
            session.last_activity = datetime.now(timezone.utc)
            return True
    
    async def record_unacknowledged(self, session_id: str, seq_num: int, message: dict) -> bool:
        """未確認メッセージを記録"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            session.unacknowledged[seq_num] = {
                "message": message,
                "timestamp": datetime.now(timezone.utc)
            }
            return True
    
    async def acknowledge_message(self, session_id: str, seq_num: int) -> bool:
        """メッセージを確認済みとして記録"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            if seq_num in session.unacknowledged:
                del session.unacknowledged[seq_num]
                return True
            return False
    
    async def get_unacknowledged_messages(self, session_id: str) -> List[Dict]:
        """
        ACKタイムアウトしたメッセージを取得
        
        Returns:
            再送が必要なメッセージのリスト
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            
            now = datetime.now(timezone.utc)
            expired = []
            for seq_num, info in list(session.unacknowledged.items()):
                elapsed = (now - info["timestamp"]).total_seconds()
                if elapsed > self._ack_timeout_sec:
                    expired.append({
                        "seq_num": seq_num,
                        "message": info["message"],
                        "elapsed_sec": elapsed
                    })
            return expired
    
    async def cleanup_expired_sessions(self) -> int:
        """
        期限切れセッションをクリーンアップ
        
        Returns:
            削除されたセッション数
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            expired_ids = []
            
            for session_id, session in self._sessions.items():
                elapsed = (now - session.last_activity).total_seconds()
                if elapsed > self._session_timeout_sec:
                    expired_ids.append(session_id)
            
            for session_id in expired_ids:
                session = self._sessions.pop(session_id, None)
                if session and session.peer_id in self._peer_sessions:
                    if self._peer_sessions[session.peer_id] == session_id:
                        del self._peer_sessions[session.peer_id]
            
            if expired_ids:
                logger.info(f"Cleaned up {len(expired_ids)} expired sessions")
            return len(expired_ids)
    
    async def get_session_stats(self) -> dict:
        """セッション統計を取得"""
        async with self._lock:
            total = len(self._sessions)
            established = sum(1 for s in self._sessions.values() if s.established)
            total_unacked = sum(len(s.unacknowledged) for s in self._sessions.values())
            
            return {
                "total_sessions": total,
                "established_sessions": established,
                "pending_sessions": total - established,
                "peer_count": len(self._peer_sessions),
                "total_unacknowledged": total_unacked
            }
    
    async def set_encryption_key(self, session_id: str, shared_key: bytes) -> bool:
        """セッションに暗号化鍵を設定"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            session.shared_key = shared_key
            session.encryption_enabled = True
            logger.info(f"Encryption enabled for session {session_id}")
            return True
    
    async def start_cleanup_task(self) -> None:
        """定期クリーンアップタスクを開始"""
        if self._cleanup_task is not None:
            return
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("SessionManager cleanup task started")
    
    async def stop_cleanup_task(self) -> None:
        """定期クリーンアップタスクを停止"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("SessionManager cleanup task stopped")
    
    async def _cleanup_loop(self) -> None:
        """定期クリーンアップループ"""
        while True:
            try:
                await asyncio.sleep(60)  # 1分ごとにクリーンアップ
                await self.cleanup_expired_sessions()
            except Exception as e:
                logger.error(f"Error in session cleanup loop: {e}")


@dataclass
class QueuedMessage:
    """キューに格納されるメッセージ"""
    target_id: str
    message_type: str
    payload: dict
    retry_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    next_retry_at: Optional[datetime] = None


# ChunkInfo and ChunkManager are now imported from chunked_transfer.py
# For backward compatibility, they are re-exported here
if not CHUNKED_TRANSFER_AVAILABLE:
    raise ImportError("ChunkInfo and ChunkManager must be imported from chunked_transfer.py")

class ExponentialBackoff:
    """
    チャンクメッセージ管理クラス（Protocol v1.1対応）
    
    - 複数メッセージのチャンクを同時管理
    - タイムアウト処理（5分以上経過したchunk群は破棄）
    - 重複チャンクの無視
    - 不完全メッセージの検出とクリーンアップ
    """
    
    DEFAULT_TIMEOUT_SECONDS = 300  # 5分
    CLEANUP_INTERVAL_SECONDS = 60  # 1分ごとにクリーンアップ
    
    def __init__(self, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        self._chunks: Dict[str, ChunkInfo] = {}
        self._lock = asyncio.Lock()
        self._timeout_seconds = timeout_seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stats = {
            "total_messages": 0,
            "completed_messages": 0,
            "expired_messages": 0,
            "duplicate_chunks": 0,
            "total_chunks_received": 0
        }
        
        # Protocol v1.0 Reliable Transfer - 送信側管理
        self._send_buffers: Dict[str, dict] = {}  # chunk_id -> 送信バッファ
        self._pending_resend: Dict[str, List[int]] = {}  # chunk_id -> 再送待ちインデックス
        self._ack_waiters: Dict[str, asyncio.Event] = {}  # chunk_id -> ACK待ちイベント
    
    async def add_chunk(
        self,
        chunk_id: str,
        chunk_index: int,
        total_chunks: int,
        data: str,
        original_msg_type: str,
        sender_id: str
    ) -> Tuple[bool, Optional[dict]]:
        """
        チャンクを追加し、完全なメッセージが揃った場合は再構築
        
        Args:
            chunk_id: メッセージ識別用UUID
            chunk_index: このチャンクのインデックス（0-based）
            total_chunks: 総チャンク数
            data: base64エンコードされた分割データ
            original_msg_type: 元のメッセージタイプ
            sender_id: 送信者ID
            
        Returns:
            Tuple[bool, Optional[dict]]: 
                - (True, payload): メッセージが完成
                - (False, None): まだ不完全
        """
        async with self._lock:
            # 新規メッセージの場合はChunkInfoを作成
            if chunk_id not in self._chunks:
                self._chunks[chunk_id] = ChunkInfo(
                    chunk_id=chunk_id,
                    total_chunks=total_chunks,
                    original_msg_type=original_msg_type,
                    sender_id=sender_id
                )
                self._stats["total_messages"] += 1
                logger.debug(f"Started receiving chunked message {chunk_id} ({total_chunks} chunks)")
            
            chunk_info = self._chunks[chunk_id]
            
            # 整合性チェック
            if chunk_info.total_chunks != total_chunks:
                logger.warning(
                    f"Chunk count mismatch for {chunk_id}: "
                    f"expected {chunk_info.total_chunks}, got {total_chunks}"
                )
                return False, None
            
            # チャンクを追加（重複チェック）
            is_new = chunk_info.add_chunk(chunk_index, data)
            if not is_new:
                self._stats["duplicate_chunks"] += 1
                logger.debug(f"Duplicate chunk {chunk_index} for message {chunk_id} - ignored")
                return False, None
            
            self._stats["total_chunks_received"] += 1
            
            logger.debug(
                f"Received chunk {chunk_index + 1}/{total_chunks} for message {chunk_id} from {sender_id}"
            )
            
            # メッセージが完成したかチェック
            if chunk_info.is_complete():
                payload = chunk_info.get_payload()
                if payload is not None:
                    self._stats["completed_messages"] += 1
                    logger.info(f"Reconstructed chunked message {chunk_id} ({total_chunks} chunks)")
                    # バッファから削除
                    del self._chunks[chunk_id]
                    return True, payload
                else:
                    logger.error(f"Failed to reconstruct message {chunk_id}")
                    del self._chunks[chunk_id]
                    return False, None
            
            return False, None
    
    async def cleanup_expired(self) -> int:
        """
        期限切れのチャンクをクリーンアップ
        
        Returns:
            削除されたメッセージ数
        """
        expired_ids = []
        async with self._lock:
            for chunk_id, chunk_info in self._chunks.items():
                if chunk_info.is_expired(self._timeout_seconds):
                    expired_ids.append(chunk_id)
                    missing = chunk_info.get_missing_indices()
                    logger.warning(
                        f"Expired chunked message {chunk_id} from {chunk_info.sender_id}: "
                        f"received {len(chunk_info.received_indices)}/{chunk_info.total_chunks} chunks, "
                        f"missing indices: {missing}"
                    )
            
            for chunk_id in expired_ids:
                del self._chunks[chunk_id]
            
            self._stats["expired_messages"] += len(expired_ids)
        
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired chunked messages")
        
        return len(expired_ids)
    
    async def start_cleanup_task(self) -> None:
        """定期クリーンアップタスクを開始"""
        if self._cleanup_task is not None:
            return
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"ChunkManager cleanup task started (interval: {self.CLEANUP_INTERVAL_SECONDS}s)")
    
    async def stop_cleanup_task(self) -> None:
        """定期クリーンアップタスクを停止"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("ChunkManager cleanup task stopped")
    
    async def _cleanup_loop(self) -> None:
        """クリーンアップループ"""
        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL_SECONDS)
                await self.cleanup_expired()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in chunk cleanup loop: {e}")
    
    def get_stats(self) -> dict:
        """統計情報を取得"""
        return self._stats.copy()
    
    def get_pending_count(self) -> int:
        """処理中のメッセージ数を取得"""
        return len(self._chunks)
    
    def get_pending_info(self) -> List[dict]:
        """処理中のメッセージ情報を取得"""
        return [
            {
                "chunk_id": cid,
                "sender_id": info.sender_id,
                "original_msg_type": info.original_msg_type,
                "received": len(info.received_indices),
                "total": info.total_chunks,
                "progress": f"{len(info.received_indices)}/{info.total_chunks}",
                "age_seconds": (datetime.now(timezone.utc) - info.created_at).total_seconds()
            }
            for cid, info in self._chunks.items()
        ]


class ExponentialBackoff:
    """指数バックオフリトライ間隔計算
    
    リトライ間隔: 1s, 2s, 4s, 8s... (最大60秒)
    jitter（±20%）を追加
    """
    
    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter_percent: float = 0.2
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter_percent = jitter_percent
    
    def get_delay(self, retry_count: int) -> float:
        """リトライ回数に基づく遅延時間を計算（jitter含む）"""
        delay = self.initial_delay * (self.multiplier ** retry_count)
        delay = min(delay, self.max_delay)
        jitter = delay * self.jitter_percent * (2 * random.random() - 1)
        delay += jitter
        return max(0.1, delay)


class MessageQueue:
    """メッセージキュー - 送信失敗時のリトライ管理
    
    送信失敗時にメッセージをキューに保存し、バックグラウンドでリトライ処理を行う。
    最大リトライ回数（3回）で破棄。
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        backoff: Optional[ExponentialBackoff] = None
    ):
        self._queue: deque[QueuedMessage] = deque()
        self._lock = asyncio.Lock()
        self.max_retries = max_retries
        self.backoff = backoff or ExponentialBackoff()
        self._retry_task: Optional[asyncio.Task] = None
        self._stats = {"queued": 0, "sent": 0, "failed": 0, "discarded": 0}
    
    async def enqueue(
        self,
        target_id: str,
        message_type: str,
        payload: dict
    ) -> None:
        """メッセージをキューに追加"""
        message = QueuedMessage(
            target_id=target_id,
            message_type=message_type,
            payload=payload
        )
        async with self._lock:
            self._queue.append(message)
            self._stats["queued"] += 1
        logger.info(f"Message queued for {target_id}: {message_type}")
    
    def get_queue_size(self) -> int:
        """キューサイズを取得"""
        return len(self._queue)
    
    def get_stats(self) -> dict:
        """キュー統計を取得"""
        return self._stats.copy()
    
    async def start_retry_processor(
        self,
        send_func: Callable[[str, str, dict], Any]
    ) -> None:
        """バックグラウンドリトライ処理を開始"""
        if self._retry_task is not None:
            return
        self._retry_task = asyncio.create_task(self._retry_loop(send_func))
        logger.info("Message queue retry processor started")
    
    async def stop_retry_processor(self) -> None:
        """リトライ処理を停止"""
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
            self._retry_task = None
            logger.info("Message queue retry processor stopped")
    
    async def _retry_loop(
        self,
        send_func: Callable[[str, str, dict], Any]
    ) -> None:
        """リトライ処理ループ"""
        while True:
            try:
                next_retry = await self._process_queue(send_func)
                sleep_time = max(1.0, next_retry - datetime.now(timezone.utc).timestamp()) if next_retry else 1.0
                await asyncio.sleep(sleep_time)
            except (ConnectionError, TimeoutError) as e:
                logger.warning(f"Network error in retry loop, backing off: {type(e).__name__}: {e}")
                await asyncio.sleep(5.0)
            except Exception as e:
                logger.exception(f"Unexpected error in retry loop: {type(e).__name__}: {e}")
                await asyncio.sleep(5.0)
    
    async def _process_queue(
        self,
        send_func: Callable[[str, str, dict], Any]
    ) -> Optional[float]:
        """キューを処理
        
        Returns:
            次のリトライ時刻のtimestamp、キューが空ならNone
        """
        now = datetime.now(timezone.utc)
        pending = []
        next_retry_time: Optional[float] = None
        
        async with self._lock:
            remaining = deque()
            for msg in self._queue:
                if msg.next_retry_at is None or msg.next_retry_at <= now:
                    pending.append(msg)
                else:
                    remaining.append(msg)
                    retry_ts = msg.next_retry_at.timestamp()
                    if next_retry_time is None or retry_ts < next_retry_time:
                        next_retry_time = retry_ts
            self._queue = remaining
        for msg in pending:
            try:
                success = await send_func(
                    msg.target_id, msg.message_type, msg.payload
                )
                if success:
                    self._stats["sent"] += 1
                    logger.info("Retry success: target=%s type=%s", msg.target_id, msg.message_type)
                else:
                    await self._handle_retry_failure(msg)
            except (ConnectionError, TimeoutError) as e:
                logger.warning("Retry network error: target=%s error=%s", msg.target_id, e)
                await self._handle_retry_failure(msg)
            except Exception as e:
                logger.exception("Retry unexpected error: target=%s type=%s", msg.target_id, type(e).__name__)
                await self._handle_retry_failure(msg)
        
        return next_retry_time
    
    async def _handle_retry_failure(self, msg: QueuedMessage) -> None:
        """リトライ失敗時の処理"""
        msg.retry_count += 1
        if msg.retry_count >= self.max_retries:
            self._stats["discarded"] += 1
            logger.warning(
                f"Message discarded after {msg.retry_count} retries: "
                f"{msg.message_type} to {msg.target_id}"
            )
        else:
            delay = self.backoff.get_delay(msg.retry_count)
            msg.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            async with self._lock:
                self._queue.append(msg)
            logger.info(
                f"Retry {msg.retry_count}/{self.max_retries} scheduled "
                f"for {msg.target_id} in {delay:.1f}s"
            )


class HeartbeatManager:
    """ハートビート管理 - ピア生存状態監視
    
    30秒間隔で登録ピアにping送信し、生存状態を追跡する。
    3回連続失敗で unhealthy とマーク。
    """
    
    def __init__(
        self,
        interval_sec: float = 30.0,
        failure_threshold: int = 3,
        ping_timeout: float = 5.0
    ):
        self.interval_sec = interval_sec
        self.failure_threshold = failure_threshold
        self.ping_timeout = ping_timeout
        self._peer_status: Dict[str, PeerStatus] = {}
        self._failure_counts: Dict[str, int] = {}
        self._last_ping: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._ping_func: Optional[Callable[[str], Any]] = None
    
    def register_peer(self, entity_id: str) -> None:
        """ピアを登録"""
        self._peer_status[entity_id] = PeerStatus.UNKNOWN
        self._failure_counts[entity_id] = 0
        logger.info(f"Peer registered for heartbeat: {entity_id}")
    
    def unregister_peer(self, entity_id: str) -> None:
        """ピアを解除"""
        self._peer_status.pop(entity_id, None)
        self._failure_counts.pop(entity_id, None)
        self._last_ping.pop(entity_id, None)
        logger.info(f"Peer unregistered from heartbeat: {entity_id}")
    
    def get_status(self, entity_id: str) -> PeerStatus:
        """ピアの生存状態を取得"""
        return self._peer_status.get(entity_id, PeerStatus.UNKNOWN)
    
    def get_all_status(self) -> Dict[str, str]:
        """全ピアの生存状態を取得"""
        return {
            eid: status.value
            for eid, status in self._peer_status.items()
        }
    
    def get_healthy_peers(self) -> List[str]:
        """健全なピアのリストを取得"""
        return [
            eid for eid, status in self._peer_status.items()
            if status == PeerStatus.HEALTHY
        ]
    
    async def start(
        self,
        get_peers_func: Callable[[], List[str]],
        ping_func: Callable[[str], Any]
    ) -> None:
        """ハートビート監視を開始"""
        if self._heartbeat_task is not None:
            return
        self._ping_func = ping_func
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(get_peers_func)
        )
        logger.info(f"Heartbeat manager started (interval: {self.interval_sec}s)")
    
    async def stop(self) -> None:
        """ハートビート監視を停止"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
            logger.info("Heartbeat manager stopped")
    
    async def _heartbeat_loop(
        self,
        get_peers_func: Callable[[], List[str]]
    ) -> None:
        """ハートビートループ"""
        while True:
            try:
                await asyncio.sleep(self.interval_sec)
                await self._check_peers(get_peers_func())
            except (ConnectionError, TimeoutError) as e:
                logger.warning("Network error in heartbeat loop: %s", e)
            except Exception as e:
                logger.exception("Unexpected error in heartbeat loop: %s", e)
    
    async def _check_peers(self, peer_ids: List[str]) -> None:
        """ピアの生存確認"""
        for peer_id in peer_ids:
            if peer_id not in self._peer_status:
                self.register_peer(peer_id)
        for peer_id in list(self._peer_status.keys()):
            if peer_id not in peer_ids:
                self.unregister_peer(peer_id)
        tasks = [self._ping_peer(peer_id) for peer_id in peer_ids]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _ping_peer(self, entity_id: str) -> None:
        """ピアにping送信"""
        success = False
        try:
            if self._ping_func:
                success = await self._ping_func(entity_id)
        except (ConnectionError, TimeoutError) as e:
            logger.debug("Ping network error for %s: %s", entity_id, e)
        except Exception as e:
            logger.exception("Ping unexpected error for %s: %s", entity_id, e)
        
        # ロックは一度だけ取得
        async with self._lock:
            if success:
                self._failure_counts[entity_id] = 0
                self._peer_status[entity_id] = PeerStatus.HEALTHY
                self._last_ping[entity_id] = datetime.now(timezone.utc)
            else:
                await self._handle_ping_failure(entity_id)
    
    async def _handle_ping_failure(self, entity_id: str) -> None:
        """ping失敗時の処理"""
        self._failure_counts[entity_id] = self._failure_counts.get(entity_id, 0) + 1
        if self._failure_counts[entity_id] >= self.failure_threshold:
            if self._peer_status.get(entity_id) != PeerStatus.UNHEALTHY:
                self._peer_status[entity_id] = PeerStatus.UNHEALTHY
                logger.warning(
                    f"Peer marked as unhealthy: {entity_id} "
                    f"({self._failure_counts[entity_id]} consecutive failures)"
                )
        else:
            logger.info(
                f"Ping failed for {entity_id} "
                f"({self._failure_counts[entity_id]}/{self.failure_threshold})"
            )


@dataclass
class PeerStats:
    """ピア接続統計情報"""
    entity_id: str
    address: str
    total_messages_sent: int = 0
    total_messages_received: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0
    last_seen: Optional[datetime] = None
    last_error: Optional[str] = None
    is_healthy: bool = False


@dataclass
class PeerInfo:
    """ピア情報（アドレス+公開鍵）"""
    entity_id: str
    address: str
    public_key: Optional[str] = None  # hex-encoded Ed25519 public key


@dataclass
class SessionInfo:
    """v1.0 プロトコル用セッション情報"""
    session_id: str
    peer_id: str
    created_at: datetime
    last_activity: datetime
    sequence_num: int = 0
    established: bool = False


class PeerService:
    """ピア間通信サービス
    
    AIエンティティ間でのメッセージ送受信を管理するサービス.
    ピアの登録、メッセージの送受信、ヘルスチェック機能を提供する。
    Protocol v1.0対応: Ed25519署名、リプレイ保護、SecureMessage形式、Capability交換
    
    Attributes:
        entity_id: このサービスのエンティティID
        port: 通信ポート
        peers: 登録されているピアの辞書 {entity_id: address}
        peer_infos: ピアの詳細情報 {entity_id: PeerInfo}
        message_handlers: メッセージタイプごとのハンドラ辞書
        peer_stats: ピアごとの統計情報辞書
        signer: メッセージ署名用のMessageSigner
        verifier: 署名検証用のSignatureVerifier
        replay_protector: リプレイ攻撃防止用のReplayProtector
        enable_verification: 署名検証の有効/無効フラグ
    """
    
    def __init__(
        self,
        entity_id: str,
        port: int,
        enable_signing: bool = True,
        enable_verification: bool = True,
        max_message_age: int = 60,
        enable_queue: bool = True,
        enable_heartbeat: bool = True,
        registry=None,
        private_key_hex: Optional[str] = None,
        enable_encryption: bool = True,
        require_signatures: bool = True,
        enable_monitor: bool = True,
        auto_discover_peers: bool = True,
        health_check_interval: float = 30.0,
        discovery_interval: float = 60.0,
        enable_session_management: bool = True,
        session_ttl_seconds: int = 3600,
        rate_limit_requests: int = 100,
        rate_limit_window: int = 60,
        enable_connection_pool: bool = True,
        connection_pool_max_connections: int = 10,
        connection_pool_max_keepalive: int = 5,
        connection_pool_keepalive_timeout: int = 30,
        dht_registry: Optional[Any] = None,
        use_dht_discovery: bool = False,
        session_manager: Optional['NewSessionManager'] = None,
        multi_hop_router: Optional['MultiHopRouter'] = None,
        use_multi_hop: bool = False
    ) -> None:
        """PeerServiceを初期化
        
        Args:
            entity_id: このサービスのエンティティID
            port: 通信ポート
            enable_signing: メッセージ署名を有効にする（デフォルト: True）
            enable_verification: 署名検証を有効にする（デフォルト: True）
            max_message_age: メッセージの最大有効期間（秒、デフォルト: 60）
            enable_queue: メッセージキューを有効にする（デフォルト: True）
            enable_heartbeat: ハートビートを有効にする（デフォルト: True）
            registry: サービスレジストリ（オプション）
            private_key_hex: 16進数エンコードされた秘密鍵（環境変数より優先）
            enable_encryption: 暗号化を有効にする（デフォルト: True、互換性用）
            require_signatures: 署名を必須とする（デフォルト: True、enable_verificationと同義）
            enable_monitor: PeerMonitorを有効にする（デフォルト: True）
            auto_discover_peers: 自動ピア発見を有効にする（デフォルト: True）
            health_check_interval: ヘルスチェック間隔（秒、デフォルト: 30）
            discovery_interval: ピア発見間隔（秒、デフォルト: 60）
            enable_session_management: セッション管理を有効にする（デフォルト: True）
            session_ttl_seconds: セッション有効期限（秒、デフォルト: 3600）
            rate_limit_requests: 1分間あたりの最大リクエスト数（デフォルト: 100）
            rate_limit_window: レート制限の時間枠（秒、デフォルト: 60）
            enable_connection_pool: コネクションプールを有効にする（デフォルト: True）
            connection_pool_max_connections: ピアあたりの最大接続数（デフォルト: 10）
            connection_pool_max_keepalive: キープアライブ接続数（デフォルト: 5）
            connection_pool_keepalive_timeout: キープアライブタイムアウト（秒、デフォルト: 30）
            dht_registry: DHTレジストリインスタンス（オプション、デフォルト: None）
            use_dht_discovery: DHTを使用したピア発見を有効にする（デフォルト: False）
            multi_hop_router: Multi-hop routerインスタンス（オプション、デフォルト: None）
            use_multi_hop: マルチホップルーティングを有効にする（デフォルト: False）
        """
        self.entity_id: str = entity_id
        self.port: int = port
        self.peers: Dict[str, str] = {}  # {entity_id: address}
        self.peer_infos: Dict[str, PeerInfo] = {}  # {entity_id: PeerInfo}
        self.message_handlers: Dict[str, MessageHandler] = {}
        self.peer_stats: Dict[str, PeerStats] = {}
        self._registry = registry
        self._dht_registry = dht_registry
        self._use_dht_discovery = use_dht_discovery
        self._multi_hop_router = multi_hop_router
        self._use_multi_hop = use_multi_hop and MULTI_HOP_AVAILABLE
        
        # require_signaturesが指定されていればenable_verificationを上書き
        if not require_signatures:
            enable_verification = False
        
        # API Server統合用設定
        self.api_server_url: Optional[str] = os.environ.get("API_SERVER_URL")
        self.api_key: Optional[str] = os.environ.get("API_KEY")
        self.jwt_token: Optional[str] = None
        self.jwt_expires_at: Optional[datetime] = None
        
        # 暗号セッション管理（X25519鍵共有）
        self.encryption_sessions: Dict[str, Dict[str, Any]] = {}
        self._handshake_challenges: Dict[str, HandshakeChallenge] = {}
        
        # v1.0 プロトコル用セッション管理
        self._sessions: Dict[str, SessionInfo] = {}
        
        # v1.0ハンドシェイク管理
        self._handshake_sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> session info
        self._handshake_pending: Dict[str, Dict[str, Any]] = {}   # target_id -> pending handshake
        
        # メッセージキューの初期化
        self._queue: Optional[MessageQueue] = None
        if enable_queue:
            self._queue = MessageQueue()
        
        # ハートビート管理の初期化
        self._heartbeat: Optional[HeartbeatManager] = None
        if enable_heartbeat:
            self._heartbeat = HeartbeatManager()
        
        # PeerMonitorの初期化
        self._monitor: Optional[PeerMonitor] = None
        self._auto_discover = auto_discover_peers
        self._enable_monitor = enable_monitor
        if enable_monitor and MONITOR_AVAILABLE:
            self._monitor = PeerMonitor(
                entity_id=entity_id,
                registry=registry,
                health_check_interval=health_check_interval,
                discovery_interval=discovery_interval if auto_discover_peers else 0
            )
            logger.info(f"PeerMonitor initialized (health_check={health_check_interval}s, discovery={discovery_interval}s)")
        
        # 暗号機能の初期化
        self.enable_signing = enable_signing and CRYPTO_AVAILABLE
        self.enable_verification = enable_verification and CRYPTO_AVAILABLE
        self.enable_encryption = enable_encryption and CRYPTO_AVAILABLE
        self.crypto_manager: Optional[CryptoManager] = None
        self._peer_public_keys: Dict[str, str] = {}  # entity_id -> base64 public key
        self.e2e_encryption: Optional[E2EEncryption] = None  # X25519 E2E暗号化
        self._e2e_shared_keys: Dict[str, bytes] = {}  # peer_id -> shared_key cache
        self.e2e_manager: Optional['E2ECryptoManager'] = None  # E2E暗号化管理
        self._e2e_handler: Optional['E2EHandshakeHandler'] = None  # E2Eハンドシェイクハンドラ
        self.enable_e2e_encryption: bool = enable_encryption  # E2E暗号化フラグ

        if CRYPTO_AVAILABLE:
            self._init_crypto(max_message_age, private_key_hex)
        else:
            logger.warning("Crypto module not available. Running without signing/verification.")
        
        # E2ECryptoManagerの初期化（E2E暗号化が有効な場合）
        if self.enable_e2e_encryption and E2E_CRYPTO_AVAILABLE and self.crypto_manager:
            try:
                from services.e2e_crypto import E2ECryptoManager
                # KeyPairを取得
                keypair = getattr(self.crypto_manager, '_ed25519_keypair', None)
                if keypair:
                    self.e2e_manager = E2ECryptoManager(
                        entity_id=self.entity_id,
                        keypair=keypair,
                        default_timeout=session_ttl_seconds
                    )
                    logger.info(f"E2ECryptoManager initialized for {self.entity_id}")
                else:
                    logger.warning("Cannot initialize E2ECryptoManager: keypair not available")
            except Exception as e:
                logger.error(f"Failed to initialize E2ECryptoManager: {e}")
                self.e2e_manager = None
        
        # SessionManagerの初期化（外部から受け取るか、新規作成）
        self._session_manager: Optional[NewSessionManager] = None
        if enable_session_management and SESSION_MANAGER_AVAILABLE:
            if session_manager is not None:
                # 外部から受け取ったSessionManagerを使用
                self._session_manager = session_manager
                logger.info("Using provided SessionManager instance")
            else:
                # 新規作成
                self._session_manager = NewSessionManager(
                    default_ttl_minutes=session_ttl_seconds // 60
                )
                logger.info(f"SessionManager initialized (TTL: {session_ttl_seconds}s)")

    @property
    def session_manager(self) -> Optional[NewSessionManager]:
        """SessionManagerインスタンスを取得"""
        return self._session_manager
        
        # RateLimiterの初期化 (v1.1)
        self._rate_limiter: Optional[RateLimiter] = None
        self._enable_rate_limiting: bool = True
        if self._enable_rate_limiting:
            self._rate_limiter = RateLimiter()
            logger.info("RateLimiter initialized (60 req/min, 1000 req/hour)")
        
        # DHTRegistryの初期化
        self._dht_registry: Optional[Any] = dht_registry
        if self._dht_registry:
            logger.info("DHTRegistry integration enabled")
        
        # E2ECryptoManagerの初期化 (v1.1 E2E暗号化強化)
        if E2E_CRYPTO_AVAILABLE and self.keypair and not self.e2e_manager:
            try:
                from services.e2e_crypto import E2ECryptoManager, E2EHandshakeHandler
                self.e2e_manager = E2ECryptoManager(
                    entity_id=self.entity_id,
                    keypair=self.keypair,
                    default_timeout=session_ttl_seconds
                )
                self._e2e_handler = E2EHandshakeHandler(self.e2e_manager)
                logger.info(f"E2ECryptoManager initialized (timeout: {session_ttl_seconds}s)")
            except Exception as e:
                logger.error(f"Failed to initialize E2ECryptoManager: {e}")
        elif not E2E_CRYPTO_AVAILABLE:
            logger.debug("E2E crypto module not available")
        
        # デフォルトのメッセージハンドラを登録
        self._register_default_handlers()
    
    def _init_crypto(self, max_message_age: int, private_key_hex: Optional[str] = None) -> None:
        """暗号機能を初期化
        
        Args:
            max_message_age: メッセージの最大有効期間（秒）
            private_key_hex: プライベートキー（hex文字列）、Noneの場合は環境変数から取得
        """
        # 環境変数または引数からキーペアを読み込み
        if private_key_hex is None:
            private_key_hex = os.environ.get("ENTITY_PRIVATE_KEY")
        if not private_key_hex:
            logger.info("No private key found in environment, generating new key pair...")
            private_key_hex, public_key_hex = generate_entity_keypair()
            logger.info(f"Generated new key pair. Public key: {public_key_hex[:16]}...")
        else:
            logger.info("Loaded key pair from environment variable.")
        
        # CryptoManagerの初期化
        self.crypto_manager = CryptoManager(self.entity_id, private_key_hex)
        public_key_b64 = self.crypto_manager.get_ed25519_public_key_b64()
        logger.info(f"CryptoManager initialized. Public key: {public_key_b64[:16]}...")
        
        if self.enable_signing:
            logger.info("Message signing enabled.")
        if self.enable_verification:
            logger.info("Signature verification enabled.")
        logger.info(f"Replay protection enabled (max_age={max_message_age}s).")

        # E2E暗号化の初期化
        if self.enable_encryption:
            self.e2e_encryption = E2EEncryption()
            logger.info("E2E encryption enabled (X25519 + AES-256-GCM).")
        
        # 信頼できる公開鍵レジストリの読み込み
        self._trusted_keys: Dict[str, str] = {}
        self._load_trusted_keys()
    
    def _load_trusted_keys(self) -> None:
        """信頼できる公開鍵レジストリを読み込み
        
        config/trusted_keys.json から信頼できる公開鍵を読み込む。
        このレジストリに含まれる鍵のみ署名検証に使用される。
        """
        try:
            # 複数のパスを試行
            possible_paths = [
                "config/trusted_keys.json",
                os.path.join(os.path.dirname(__file__), "..", "config", "trusted_keys.json"),
                os.path.join(os.path.dirname(__file__), "config", "trusted_keys.json"),
            ]
            
            trusted_keys_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    trusted_keys_path = path
                    break
            
            if trusted_keys_path is None:
                logger.warning("trusted_keys.json not found. No trusted keys loaded.")
                return
            
            with open(trusted_keys_path, 'r') as f:
                data = json.load(f)
                self._trusted_keys = data.get("keys", {})
                
            if self._trusted_keys:
                logger.info(f"Loaded {len(self._trusted_keys)} trusted public key(s)")
            else:
                logger.info("Trusted keys file loaded but no keys configured")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in trusted_keys.json: {e}")
        except Exception as e:
            logger.warning(f"Failed to load trusted keys: {e}")
    
    def _get_trusted_public_key(self, sender_id: str) -> Optional[str]:
        """信頼できる送信者の公開鍵を取得
        
        Args:
            sender_id: 送信者のエンティティID
            
        Returns:
            hexエンコードされた公開鍵、信頼されていない場合はNone
        """
        # 環境変数からの取得を優先（運用時の柔軟性のため）
        env_key = os.environ.get(f"TRUSTED_KEY_{sender_id.upper().replace('-', '_')}")
        if env_key:
            return env_key
        
        # ファイルからの読み込み
        return self._trusted_keys.get(sender_id)
    
    def add_trusted_key(self, entity_id: str, public_key_hex: str) -> bool:
        """信頼できる公開鍵を明示的に追加
        
        このメソッドは管理者による明示的な信頼設定が必要。
        動的な鍵追加はセキュリティリスクとなるため、非推奨。
        
        Args:
            entity_id: エンティティID
            public_key_hex: hexエンコードされたEd25519公開鍵
            
        Returns:
            追加成功ならTrue
        """
        try:
            # 鍵の形式を検証
            key_bytes = bytes.fromhex(public_key_hex)
            if len(key_bytes) != 32:  # Ed25519公開鍵は32バイト
                logger.error(f"Invalid public key length for {entity_id}: {len(key_bytes)} bytes")
                return False
            
            self._trusted_keys[entity_id] = public_key_hex
            logger.info(f"Added trusted key for {entity_id}")
            return True
        except ValueError as e:
            logger.error(f"Invalid public key format for {entity_id}: {e}")
            return False
    
    def get_public_key_hex(self) -> Optional[str]:
        """このエンティティの公開鍵（hex文字列）を取得
        
        Returns:
            hexエンコードされた公開鍵、暗号機能が無効な場合はNone
        """
        if self.crypto_manager:
            # Base64 -> bytes -> hex
            import base64
            public_key_bytes = self.crypto_manager.get_ed25519_public_key_bytes()
            return public_key_bytes.hex()
        return None
    
    def get_public_keys(self) -> Dict[str, Optional[str]]:
        """このエンティティの公開鍵を取得
        
        Returns:
            ed25519とx25519の公開鍵を含む辞書
        """
        if not self.crypto_manager:
            return {"ed25519": None, "x25519": None}
        
        ed25519_b64 = self.crypto_manager.get_ed25519_public_key_b64()
        x25519_b64 = self.crypto_manager.get_x25519_public_key_b64()
        
        return {
            "ed25519": ed25519_b64,
            "x25519": x25519_b64
        }
    
    def add_peer_public_key(self, entity_id: str, public_key_hex: str) -> None:
        """ピアの公開鍵を登録
        
        Args:
            entity_id: ピアのエンティティID
            public_key_hex: hexエンコードされたEd25519公開鍵
        """
        if not CRYPTO_AVAILABLE or self.verifier is None:
            logger.warning("Cannot add peer public key: crypto not available")
            return
        
        try:
            self.verifier.add_public_key_hex(entity_id, public_key_hex)
            
            # PeerInfoも更新
            if entity_id in self.peer_infos:
                self.peer_infos[entity_id].public_key = public_key_hex
            else:
                address = self.peers.get(entity_id, "")
                self.peer_infos[entity_id] = PeerInfo(
                    entity_id=entity_id,
                    address=address,
                    public_key=public_key_hex
                )
            
            logger.info(f"Added public key for peer: {entity_id}")
        except Exception as e:
            logger.error(f"Failed to add public key for {entity_id}: {e}")

    def _derive_shared_key(self, peer_id: str) -> Optional[bytes]:
        """ピアとの共有鍵を導出（キャッシュ付き）

        Args:
            peer_id: ピアのエンティティID

        Returns:
            共有鍵（32バイト）、失敗時はNone
        """
        if not self.enable_encryption or self.e2e_encryption is None:
            return None

        # キャッシュチェック
        if peer_id in self._e2e_shared_keys:
            return self._e2e_shared_keys[peer_id]

        # ピアの公開鍵を取得
        peer_info = self.peer_infos.get(peer_id)
        if not peer_info or not peer_info.public_key:
            logger.warning(f"Cannot derive shared key: no public key for peer {peer_id}")
            return None

        # 自分の秘密鍵を取得
        if not self.crypto_manager:
            logger.warning("Cannot derive shared key: crypto_manager not available")
            return None

        try:
            my_private_key = self.crypto_manager.get_ed25519_private_key_bytes()
            peer_public_key = bytes.fromhex(peer_info.public_key)

            # 共有鍵を導出
            shared_key = self.e2e_encryption.derive_shared_key(
                my_ed25519_private=my_private_key,
                peer_ed25519_public=peer_public_key,
                peer_id=peer_id
            )

            # キャッシュに保存
            self._e2e_shared_keys[peer_id] = shared_key
            logger.debug(f"Derived and cached shared key for peer: {peer_id}")
            return shared_key

        except Exception as e:
            logger.error(f"Failed to derive shared key for {peer_id}: {e}")
            return None

    def encrypt_payload(self, peer_id: str, payload: dict) -> Optional[dict]:
        """ペイロードをE2E暗号化（CryptoManager使用）

        Args:
            peer_id: 送信先ピアのエンティティID
            payload: 暗号化するペイロード

        Returns:
            暗号化されたペイロード辞書、失敗時はNone
        """
        if not self.enable_encryption or self.crypto_manager is None:
            return None

        try:
            # CryptoManagerを使用して暗号化
            return self.crypto_manager.encrypt_payload_simple(peer_id, payload)
        except Exception as e:
            logger.error(f"Failed to encrypt payload for {peer_id}: {e}")
            return None

    def decrypt_payload(self, peer_id: str, encrypted_data: dict) -> Optional[dict]:
        """暗号化されたペイロードを復号

        Args:
            peer_id: 送信元ピアのエンティティID
            encrypted_data: 暗号化されたデータ（ciphertext, nonceを含む）

        Returns:
            復号されたペイロード辞書、失敗時はNone
        """
        if not self.enable_encryption or self.e2e_encryption is None:
            return None

        shared_key = self._derive_shared_key(peer_id)
        if not shared_key:
            return None

        try:
            # Base64デコード
            ciphertext = base64.b64decode(encrypted_data['ciphertext'])
            nonce = base64.b64decode(encrypted_data['nonce'])

            # 復号
            plaintext = self.e2e_encryption.decrypt(ciphertext, nonce, shared_key)

            # JSONパース
            return json.loads(plaintext.decode('utf-8'))

        except Exception as e:
            logger.error(f"Failed to decrypt payload from {peer_id}: {e}")
            return None

    def _register_default_handlers(self) -> None:
        """デフォルトのメッセージハンドラを登録"""

        async def _handle_ping(message: dict) -> None:
            """pingメッセージハンドラ"""
            sender = message.get("sender_id", message.get("from", "unknown"))
            logger.info(f"Received ping from {sender}")
            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)

        async def _handle_status(message: dict) -> None:
            """statusメッセージハンドラ"""
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            logger.info(f"Received status from {sender}: {payload}")
            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)

        async def _handle_capability_query(message: dict) -> None:
            """capability_queryメッセージハンドラ - 対応機能を返信"""
            sender = message.get("sender_id", message.get("from", "unknown"))
            logger.info(f"Received capability_query from {sender}")

            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)

            # 対応機能リスト
            capabilities = {
                "protocol_version": "1.0",
                "supported_msg_types": list(self.message_handlers.keys()) + ["capability_response"],
                "crypto_features": {
                    "ed25519_signing": self.enable_signing,
                    "signature_verification": self.enable_verification,
                    "replay_protection": self.replay_protector is not None,
                    "payload_encryption": True  # v1.0で実装済み
                },
                "endpoints": [
                    "/message",
                    "/health",
                    "/peers",
                    "/stats",
                    "/public-key"
                ],
                "entity_id": self.entity_id
            }

            # 内部で保持（互換性のため）
            self._last_capability_response = capabilities
            logger.info(f"Capability response prepared for {sender}: {capabilities['crypto_features']}")

            # 自動返信: capability_response を送信
            if sender in self.peers:
                try:
                    response_message = {
                        "msg_type": "capability_response",
                        "payload": {"capabilities": capabilities}
                    }
                    await self.send_message(sender, response_message)
                    logger.info(f"Sent capability_response to {sender}")
                except Exception as e:
                    logger.error(f"Failed to send capability_response to {sender}: {e}")

        async def _handle_error(message: dict) -> None:
            """errorメッセージハンドラ - エラー通知を処理
            
            Protocol v1.0対応:
            - error_code: エラーコード
            - error_message: 人間可読なエラーメッセージ
            - original_message_id: エラーとなった元メッセージのID（オプション）
            
            Error Codes:
            - INVALID_VERSION: プロトコルバージョン不一致
            - INVALID_SIGNATURE: 署名検証失敗
            - REPLAY_DETECTED: リプレイ攻撃検出
            - UNKNOWN_SENDER: 不明な送信者
            - SESSION_EXPIRED: セッション期限切れ
            - SEQUENCE_ERROR: シーケンス番号エラー
            - DECRYPTION_FAILED: 復号失敗
            """
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            
            error_code = payload.get("error_code", "UNKNOWN")
            error_message = payload.get("error_message", "No details provided")
            original_msg_id = payload.get("original_message_id")
            
            logger.warning(f"Received error from {sender}: [{error_code}] {error_message}")
            
            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)
                self.peer_stats[sender].failed_requests += 1
            
            # エラーコードに応じた処理
            if error_code == "INVALID_SIGNATURE":
                logger.error(f"Signature verification failed with peer {sender}")
                # ピアの鍵を再取得が必要かもしれない
                if sender in self.peers:
                    logger.info(f"Consider refreshing public key for {sender}")
                    
            elif error_code == "REPLAY_DETECTED":
                logger.error(f"Replay attack detected from {sender}")
                # 重大なセキュリティ問題 - ピアをブロックすることを検討
                if sender in self.peer_stats:
                    self.peer_stats[sender].is_healthy = False
                    
            elif error_code == "UNKNOWN_SENDER":
                logger.error(f"We are unknown to peer {sender}")
                # 自分の公開鍵を再送信する必要があるかもしれない
                
            elif error_code == "SESSION_EXPIRED":
                logger.warning(f"Session expired with peer {sender}")
                # 新しいセッションを確立が必要
                
            elif error_code == "SEQUENCE_ERROR":
                logger.warning(f"Sequence error detected with peer {sender}")
                # シーケンス番号をリセットする必要があるかもしれない
                
            elif error_code == "DECRYPTION_FAILED":
                logger.error(f"Decryption failed for message from {sender}")
                # 暗号化鍵の不一致 - 鍵交換が必要
                
            # エラーログに記録（内部処理用）
            if not hasattr(self, '_error_log'):
                self._error_log = deque(maxlen=100)  # 最大100件保持
            
            self._error_log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from": sender,
                "error_code": error_code,
                "error_message": error_message,
                "original_message_id": original_msg_id
            })

        async def _handle_heartbeat(message: dict) -> None:
            """heartbeatメッセージハンドラ - 接続生存確認"""
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            sequence = payload.get("sequence", 0)

            logger.debug(f"Received heartbeat from {sender} (seq: {sequence})")

            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)
                self.peer_stats[sender].is_healthy = True

        async def _handle_task_delegate(message: dict) -> None:
            """task_delegateメッセージハンドラ - タスク委譲"""
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            task_id = payload.get("task_id", "unknown")
            task_description = payload.get("description", "")

            logger.info(f"Received task delegation from {sender}: task_id={task_id}")

            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)

            # タスクを内部キューに追加（処理は別途行われる）
            if not hasattr(self, '_pending_tasks'):
                self._pending_tasks = []

            self._pending_tasks.append({
                "task_id": task_id,
                "from": sender,
                "description": task_description,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "payload": payload
            })

            logger.info(f"Task {task_id} queued for processing. Queue size: {len(self._pending_tasks)}")

        # ========== Protocol v1.0 Reliable Transfer ハンドラ ==========
        
        async def _handle_chunk_init(message: dict) -> None:
            """chunk_initハンドラ - 分割送信開始通知
            
            Protocol v1.0対応:
            受信側が送信側に転送準備を通知し、送信側はチャンクバッファを初期化する。
            
            Payload:
            - chunk_id: メッセージ識別子
            - total_chunks: 総チャンク数
            - original_msg_type: 元のメッセージタイプ
            - is_reliable: 信頼性モード有効フラグ
            """
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            
            chunk_id = payload.get("chunk_id")
            total_chunks = payload.get("total_chunks")
            original_msg_type = payload.get("original_msg_type", "unknown")
            is_reliable = payload.get("is_reliable", True)
            
            if not chunk_id or not total_chunks:
                logger.warning(f"Invalid chunk_init from {sender}: missing required fields")
                return
            
            try:
                total_chunks = int(total_chunks)
            except (TypeError, ValueError):
                logger.warning(f"Invalid total_chunks from {sender}: {total_chunks}")
                return
            
            # ChunkManagerが初期化されていなければ作成
            if not hasattr(self, '_chunk_manager') or self._chunk_manager is None:
                self._chunk_manager = ChunkManager()
                await self._chunk_manager.start_cleanup_task()
            
            # 受信側のChunkInfoを作成（送信準備完了を待つ）
            async with self._chunk_manager._lock:
                if chunk_id not in self._chunk_manager._chunks:
                    self._chunk_manager._chunks[chunk_id] = ChunkInfo(
                        chunk_id=chunk_id,
                        total_chunks=total_chunks,
                        original_msg_type=original_msg_type,
                        sender_id=sender,
                        is_reliable=is_reliable,
                        sender_ready=True  # 送信側準備完了
                    )
                    self._chunk_manager._stats["total_messages"] += 1
            
            logger.info(f"Chunk transfer initialized from {sender}: {chunk_id} ({total_chunks} chunks, reliable={is_reliable})")
            
            # ACK応答（準備完了）
            try:
                await self.send_message(
                    target_id=sender,
                    message_type="chunk_ack",
                    payload={
                        "chunk_id": chunk_id,
                        "received_indices": [],
                        "status": "ready"
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send chunk_init ack to {sender}: {e}")
        
        async def _handle_chunk_ack(message: dict) -> None:
            """chunk_ackハンドラ - 受信確認と欠落検出
            
            Protocol v1.0対応:
            受信側からのACKを処理し、欠落チャンクがあれば再送要求する。
            
            Payload:
            - chunk_id: メッセージ識別子
            - received_indices: 受信済みチャンクインデックス
            - missing_indices: 欠落チャンクインデックス（任意）
            - status: "ready" | "in_progress" | "complete"
            """
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            
            chunk_id = payload.get("chunk_id")
            received_indices = payload.get("received_indices", [])
            missing_indices = payload.get("missing_indices", [])
            status = payload.get("status", "in_progress")
            
            if not chunk_id:
                logger.warning(f"Invalid chunk_ack from {sender}: missing chunk_id")
                return
            
            if not hasattr(self, '_chunk_manager') or self._chunk_manager is None:
                return
            
            # ACKを記録
            await self._chunk_manager.mark_acknowledged(chunk_id, received_indices)
            
            # 欠落チャンクが明示的に指定された場合、再送キューに追加
            if missing_indices:
                await self._chunk_manager.queue_resend(chunk_id, missing_indices)
                logger.debug(f"Missing chunks queued for resend: {chunk_id} indices {missing_indices}")
            else:
                # 送信バッファから未ACKのチャンクを計算
                missing = await self._chunk_manager.get_missing_chunks(chunk_id)
                if missing:
                    await self._chunk_manager.queue_resend(chunk_id, missing)
                    logger.debug(f"Auto-detected missing chunks for resend: {chunk_id} indices {missing}")
            
            if status == "complete":
                logger.info(f"Chunk transfer complete acknowledged: {chunk_id} from {sender}")
                # 送信バッファをクリーンアップ
                await self._chunk_manager.cleanup_send_buffer(chunk_id)
            else:
                logger.debug(f"Chunk ACK from {sender}: {chunk_id} status={status}")
        
        async def _handle_chunk_resend(message: dict) -> None:
            """chunk_resendハンドラ - 欠落チャンクの再送要求処理
            
            Protocol v1.0対応:
            受信側からの再送要求を処理し、該当チャンクを再送信する。
            
            Payload:
            - chunk_id: メッセージ識別子
            - indices: 再送要求されたチャンクインデックスリスト
            - reason: 再送理由（任意）
            """
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            
            chunk_id = payload.get("chunk_id")
            indices = payload.get("indices", [])
            reason = payload.get("reason", "not_specified")
            
            if not chunk_id or not indices:
                logger.warning(f"Invalid chunk_resend from {sender}: missing required fields")
                return
            
            if not hasattr(self, '_chunk_manager') or self._chunk_manager is None:
                logger.warning(f"Cannot resend chunks for {chunk_id}: ChunkManager not initialized")
                return
            
            # 送信バッファからチャンクを取得
            buffer_info = self._chunk_manager.get_send_buffer_info(chunk_id)
            if not buffer_info:
                logger.warning(f"Cannot resend chunks for {chunk_id}: send buffer not found")
                return
            
            # 要求されたインデックスのチャンクを再送
            async with self._chunk_manager._lock:
                buffer = self._chunk_manager._send_buffers.get(chunk_id)
                if not buffer:
                    return
                
                resent_count = 0
                for idx in indices:
                    if 0 <= idx < len(buffer["chunks"]):
                        chunk_data = buffer["chunks"][idx]
                        try:
                            await self.send_message(
                                target_id=buffer["target_id"],
                                message_type="chunk",
                                payload={
                                    "chunk_id": chunk_id,
                                    "chunk_index": idx,
                                    "total_chunks": buffer["total_chunks"],
                                    "data": chunk_data,
                                    "original_msg_type": buffer["original_msg_type"],
                                    "is_resend": True
                                }
                            )
                            resent_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to resend chunk {idx} for {chunk_id}: {e}")
            
            logger.info(f"Resent {resent_count}/{len(indices)} chunks for {chunk_id} to {sender} (reason: {reason})")
        
        async def _handle_chunk_complete(message: dict) -> None:
            """chunk_completeハンドラ - 完了確認とリソースクリーンアップ
            
            Protocol v1.0対応:
            受信側からの完了通知を処理し、送信バッファをクリーンアップする。
            
            Payload:
            - chunk_id: メッセージ識別子
            - status: "success" | "failed"
            - checksum_verified: チェックサム検証結果（任意）
            - error: エラーメッセージ（失敗時）
            """
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            
            chunk_id = payload.get("chunk_id")
            status = payload.get("status", "success")
            checksum_verified = payload.get("checksum_verified", None)
            error = payload.get("error", None)
            
            if not chunk_id:
                logger.warning(f"Invalid chunk_complete from {sender}: missing chunk_id")
                return
            
            if not hasattr(self, '_chunk_manager') or self._chunk_manager is None:
                return
            
            # 受信側のChunkInfoをクリーンアップ
            async with self._chunk_manager._lock:
                if chunk_id in self._chunk_manager._chunks:
                    del self._chunk_manager._chunks[chunk_id]
            
            # 送信バッファもクリーンアップ（送信側の場合）
            await self._chunk_manager.cleanup_send_buffer(chunk_id)
            
            if status == "success":
                logger.info(f"Chunk transfer completed successfully: {chunk_id} from {sender}")
                if checksum_verified is not None:
                    logger.debug(f"Checksum verified for {chunk_id}: {checksum_verified}")
            else:
                logger.warning(f"Chunk transfer failed: {chunk_id} from {sender}, error: {error}")

        async def _handle_chunk(message: dict) -> None:
            """chunkメッセージハンドラ - 分割メッセージの再構築
            
            Protocol v1.1対応:
            - chunk_id: UUID（同じメッセージのchunkを識別）
            - chunk_index: このチャンクのインデックス（0-based）
            - total_chunks: 総チャンク数
            - data: base64エンコードされた分割データ
            - original_msg_type: 元のメッセージタイプ（再構成後の処理用）
            """
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            
            # 必須フィールドの検証
            chunk_id = payload.get("chunk_id")
            chunk_index = payload.get("chunk_index")
            total_chunks = payload.get("total_chunks")
            chunk_data = payload.get("data", "")
            original_msg_type = payload.get("original_msg_type", "unknown")
            
            if not all([chunk_id, chunk_index is not None, total_chunks]):
                logger.warning(f"Invalid chunk message from {sender}: missing required fields")
                return
            
            # 型チェック
            try:
                chunk_index = int(chunk_index)
                total_chunks = int(total_chunks)
            except (TypeError, ValueError):
                logger.warning(f"Invalid chunk indices from {sender}: index={chunk_index}, total={total_chunks}")
                return
            
            # 範囲チェック
            if chunk_index < 0 or chunk_index >= total_chunks or total_chunks <= 0:
                logger.warning(f"Invalid chunk range from {sender}: index={chunk_index}, total={total_chunks}")
                return
            
            # ChunkManagerが初期化されていなければ作成
            if not hasattr(self, '_chunk_manager') or self._chunk_manager is None:
                self._chunk_manager = ChunkManager()
                await self._chunk_manager.start_cleanup_task()
                logger.info("ChunkManager initialized for chunked message handling")
            
            # チャンクを追加し、メッセージが完成したかチェック
            is_complete, reconstructed_payload = await self._chunk_manager.add_chunk(
                chunk_id=chunk_id,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                data=chunk_data,
                original_msg_type=original_msg_type,
                sender_id=sender
            )
            
            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)
            
            # メッセージが完成したら対応するハンドラーに委譲
            if is_complete and reconstructed_payload:
                inner_handler = self.message_handlers.get(original_msg_type)
                
                if inner_handler:
                    # 再構築したメッセージを対応するハンドラーに渡す
                    reconstructed_message = {
                        "sender_id": sender,
                        "msg_type": original_msg_type,
                        "payload": reconstructed_payload,
                        "timestamp": message.get("timestamp"),
                        "session_id": message.get("session_id"),
                        "chunk_id": chunk_id  # トレーサビリティ用
                    }
                    try:
                        await inner_handler(reconstructed_message)
                        logger.info(f"Reconstructed message {chunk_id} delegated to {original_msg_type} handler")
                    except Exception as e:
                        logger.error(f"Error handling reconstructed message {chunk_id}: {e}")
                else:
                    logger.warning(f"No handler for reconstructed message type: {original_msg_type}")

        async def _handle_gossip(message: dict) -> None:
            """gossipメッセージハンドラ - 分散レジストリ同期"""
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            gossip_type = payload.get("gossip_type")
            logger.debug(f"Received gossip from {sender}: type={gossip_type}")
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)
            if hasattr(self, '_dist_registry') and self._dist_registry:
                self._dist_registry.on_gossip(sender, payload)

        async def _handle_registry_sync(message: dict) -> None:
            """registry_syncメッセージハンドラ"""
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            entries_data = payload.get("entries", [])
            logger.info(f"Received registry sync from {sender}: {len(entries_data)} entries")
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)
            if hasattr(self, '_dist_registry') and self._dist_registry:
                from distributed_registry import RegistryEntry
                merged = 0
                for entry_data in entries_data:
                    try:
                        entry = RegistryEntry.from_dict(entry_data)
                        if self._dist_registry.merge_entry(entry):
                            merged += 1
                    except Exception as e:
                        logger.error(f"Failed to merge registry entry: {e}")
                logger.info(f"Merged {merged} entries from {sender}")

        # v1.0 ハンドシェイクハンドラ
        async def _handle_handshake(message: dict) -> None:
            """handshakeメッセージハンドラ"""
            await self.handle_handshake(message)

        async def _handle_handshake_ack(message: dict) -> None:
            """handshake_ackメッセージハンドラ"""
            await self.handle_handshake_ack(message)

        async def _handle_handshake_confirm(message: dict) -> None:
            """handshake_confirmメッセージハンドラ"""
            await self.handle_handshake_confirm(message)

        async def _handle_capability_response(message: dict) -> None:
            """capability_responseメッセージハンドラ - ピアの機能情報を処理"""
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            capabilities = payload.get("capabilities", {})

            logger.info(f"Received capability_response from {sender}")

            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)

            # ピア情報を更新
            if sender in self.peer_infos:
                self.peer_infos[sender].capabilities = capabilities
                logger.info(f"Updated capabilities for peer {sender}: {capabilities.get('protocol_version', 'unknown')}")
            else:
                logger.debug(f"Received capabilities from unknown peer {sender}")

            # 内部保存（後続処理用）
            if not hasattr(self, '_peer_capabilities'):
                self._peer_capabilities: Dict[str, dict] = {}
            self._peer_capabilities[sender] = capabilities

        async def _handle_wake_up(message: dict) -> None:
            """wake_upメッセージハンドラ - ピアからの起動通知を処理"""
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            wake_reason = payload.get("reason", "unspecified")

            logger.info(f"Received wake_up from {sender}, reason={wake_reason}")

            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)
                self.peer_stats[sender].is_healthy = True

            # ピアの状態を更新
            if sender in self.peers:
                logger.info(f"Peer {sender} is now awake and ready")
                # 必要に応じて capability_query を送信
                try:
                    query_message = {"msg_type": "capability_query", "payload": {}}
                    await self.send_message(sender, query_message)
                    logger.debug(f"Sent capability_query to {sender} after wake_up")
                except Exception as e:
                    logger.error(f"Failed to send capability_query to {sender}: {e}")

        # Wake Up Protocol ハンドラ（内部）
        async def _handle_wake_up(message: dict) -> None:
            """wake_upメッセージハンドラ"""
            await self.handle_wake_up(message)

        async def _handle_wake_up_ack(message: dict) -> None:
            """wake_up_ackメッセージハンドラ"""
            await self.handle_wake_up_ack(message)

        async def _handle_token_transfer(message: dict) -> None:
            """token_transferメッセージハンドラ - トークン転送

            Protocol v1.2対応:
            他のピアからのトークン転送リクエストを処理する。

            Payload:
            - transfer_id: 転送ID
            - sender_address: 送信元アドレス
            - recipient_address: 送信先アドレス
            - amount: 転送量
            - token_type: トークンタイプ（デフォルト: AGT）
            """
            sender = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            transfer_id = payload.get("transfer_id", "unknown")
            sender_address = payload.get("sender_address", "")
            recipient_address = payload.get("recipient_address", "")
            amount = payload.get("amount", 0)
            token_type = payload.get("token_type", "AGT")

            logger.info(f"Received token transfer from {sender}: transfer_id={transfer_id}, amount={amount} {token_type}")

            # 統計を更新
            if sender in self.peer_stats:
                self.peer_stats[sender].total_messages_received += 1
                self.peer_stats[sender].last_seen = datetime.now(timezone.utc)

            # トークン転送を内部キューに追加（処理は別途行われる）
            if not hasattr(self, '_pending_transfers'):
                self._pending_transfers = []

            self._pending_transfers.append({
                "transfer_id": transfer_id,
                "from_peer": sender,
                "sender_address": sender_address,
                "recipient_address": recipient_address,
                "amount": amount,
                "token_type": token_type,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "payload": payload
            })

            logger.info(f"Token transfer {transfer_id} queued for processing. Queue size: {len(self._pending_transfers)}")

        # ハンドラ登録
        self.register_handler("ping", _handle_ping)
        self.register_handler("status", _handle_status)
        self.register_handler("capability_query", _handle_capability_query)
        self.register_handler("heartbeat", _handle_heartbeat)
        self.register_handler("task_delegate", _handle_task_delegate)
        self.register_handler("chunk", _handle_chunk)
        self.register_handler("error", _handle_error)
        self.register_handler("gossip", _handle_gossip)
        self.register_handler("registry_sync", _handle_registry_sync)
        self.register_handler("handshake", _handle_handshake)
        self.register_handler("handshake_ack", _handle_handshake_ack)
        self.register_handler("handshake_confirm", _handle_handshake_confirm)
        self.register_handler("capability_response", _handle_capability_response)
        self.register_handler("wake_up", _handle_wake_up)
        self.register_handler("wake_up_ack", _handle_wake_up_ack)
        self.register_handler("token_transfer", _handle_token_transfer)

        # 内部状態初期化
        self._last_capability_response = None
        self._pending_tasks = []
        self._dist_registry = None
        
    def register_handler(self, message_type: str, handler: MessageHandler) -> None:
        """メッセージハンドラを登録
        
        Args:
            message_type: メッセージタイプ（例: "ping", "status"）
            handler: 非同期ハンドラ関数
        """
        self.message_handlers[message_type] = handler
        logger.debug(f"Registered handler for {message_type}")
    
    async def _send_with_retry(
        self,
        url: str,
        message_dict: dict,
        max_retries: int = 3,
        base_delay: float = 1.0
    ) -> Tuple[bool, Optional[int]]:
        """HTTP POST送信とリトライロジックを分離
        
        Args:
            url: 送信先URL
            message_dict: 送信するメッセージ辞書
            max_retries: 最大リトライ回数
            base_delay: 初回リトライの待機秒数
            
        Returns:
            Tuple[bool, Optional[int]]: (成功フラグ, HTTPステータスコード)
        """
        last_status: Optional[int] = None
        
        for attempt in range(max_retries):
            timeout = ClientTimeout(total=10, connect=5)
            
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        url,
                        json=message_dict,
                        headers={"Content-Type": "application/json"}
                    ) as response:
                        last_status = response.status
                        
                        if response.status == 200:
                            return True, 200
                        
                        # リトライ対象外のステータスコード
                        if response.status in (400, 401, 403, 404):
                            logger.warning(
                                f"HTTP {response.status} - not retryable"
                            )
                            return False, response.status
                        
                        # サーバーエラーはリトライ対象
                        logger.warning(
                            f"HTTP {response.status} - will retry"
                        )
                        
            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout (attempt {attempt + 1}/{max_retries})"
                )
            except ClientError as e:
                logger.warning(
                    f"Connection error: {e} (attempt {attempt + 1}/{max_retries})"
                )
            except Exception as e:
                logger.warning(
                    f"Unexpected error: {e} (attempt {attempt + 1}/{max_retries})"
                )
            
            # 指数バックオフ（最後の試行を除く）
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay:.1f} seconds...")
                await asyncio.sleep(delay)
        
        return False, last_status

    # 自動チャンク分割の閾値（バイト）
    AUTO_CHUNK_THRESHOLD = 8192  # 8KB

    def _should_use_chunking(self, payload: dict, message_type: str) -> bool:
        """ペイロードがチャンク分割が必要かチェック

        Args:
            payload: メッセージの内容
            message_type: メッセージタイプ

        Returns:
            チャンク分割が必要ならTrue
        """
        if message_type == "chunk":  # chunkタイプは分割しない
            return False
        try:
            payload_size = len(json.dumps(payload).encode('utf-8'))
            if payload_size > self.AUTO_CHUNK_THRESHOLD:
                logger.info(
                    f"Payload size ({payload_size} bytes) exceeds threshold "
                    f"({self.AUTO_CHUNK_THRESHOLD} bytes), will use chunked transfer"
                )
                return True
        except Exception as e:
            logger.warning(f"Failed to check payload size for auto-chunking: {e}")
        return False

    def _prepare_payload(self, target_id: str, payload: dict, encrypt: bool) -> dict:
        """E2E暗号化を適用したペイロードを準備

        Args:
            target_id: 送信先ピアのエンティティID
            payload: 元のペイロード
            encrypt: E2E暗号化を有効にするか

        Returns:
            準備されたペイロード（暗号化済みまたは元のペイロード）
        """
        if not encrypt:
            return payload

        # 優先: E2ECryptoManagerを使用
        if self.e2e_manager and E2E_CRYPTO_AVAILABLE:
            try:
                # アクティブなE2Eセッションを取得
                e2e_session = self.e2e_manager.get_active_session(target_id)
                if e2e_session:
                    # E2ECryptoManagerで暗号化
                    encrypted_msg = self.e2e_manager.encrypt_message(
                        e2e_session.session_id, payload
                    )
                    encrypted_payload = {
                        "_e2e_encrypted": True,
                        "session_id": e2e_session.session_id,
                        "data": encrypted_msg.payload.get("data"),
                        "nonce": encrypted_msg.payload.get("nonce")
                    }
                    logger.debug(f"Payload E2E encrypted for {target_id} using session {e2e_session.session_id}")
                    return encrypted_payload
            except Exception as e:
                logger.warning(f"E2E encryption failed for {target_id}: {e}")
        
        # フォールバック: 従来の暗号化方式
        encrypted = self.encrypt_payload(target_id, payload)
        if encrypted:
            logger.debug(f"Payload encrypted for {target_id} (legacy method)")
            return {"_encrypted_payload": encrypted}
        else:
            logger.warning(f"Failed to encrypt payload for {target_id}, sending unencrypted")
            return payload

    def _get_session_info(self, target_id: str) -> Tuple[Optional[str], Optional[int]]:
        """セッション情報を取得（シーケンス番号用）

        Args:
            target_id: 送信先ピアのエンティティID

        Returns:
            (session_id, sequence_num)のタプル。セッションがない場合は(None, None)
        """
        if hasattr(self, '_session_manager') and self._session_manager:
            try:
                session = asyncio.run(self._session_manager.get_session_by_peer(target_id))
                if session:
                    session_id = session.session_id
                    sequence_num = session.increment_sequence()
                    logger.debug(f"Using session {session_id} with sequence {sequence_num} for {target_id}")
                    return session_id, sequence_num
            except Exception as e:
                logger.warning(f"Failed to get session info for {target_id}: {e}")
        return None, None

    def _update_send_stats(self, target_id: str, success: bool, max_retries: int = 3, status: int = 0):
        """送信統計を更新

        Args:
            target_id: 送信先ピアのエンティティID
            success: 送信が成功したか
            max_retries: 最大リトライ回数（失敗時のログ用）
            status: HTTPステータスコード（失敗時のログ用）
        """
        if success:
            self.peer_stats[target_id].successful_deliveries += 1
            self.peer_stats[target_id].last_seen = datetime.now(timezone.utc)
            self.peer_stats[target_id].is_healthy = True
        else:
            self.peer_stats[target_id].failed_deliveries += 1
            self.peer_stats[target_id].last_error = f"Failed after {max_retries} attempts (HTTP {status})"
            self.peer_stats[target_id].is_healthy = False

    async def send_message(
        self,
        target_id: str,
        message_type: str,
        payload: dict,
        max_retries: int = 3,
        base_delay: float = 1.0,
        auto_chunk: bool = True,
        encrypt: bool = False
    ) -> bool:
        """ピアにメッセージを送信（HTTP POST、自動リトライ付き）

        Protocol v1.0形式（SecureMessage）でメッセージを送信。
        ピアの公開鍵が登録されていれば署名を付与。

        v1.1追加:
        - 自動チャンク分割: ペイロードサイズが閾値を超える場合、
          自動的にchunked messageとして送信
        - E2E暗号化: encrypt=TrueでペイロードをX25519+AES-256-GCMで暗号化

        Args:
            target_id: 送信先ピアのエンティティID
            message_type: メッセージタイプ
            payload: メッセージの内容
            max_retries: 最大リトライ回数（デフォルト: 3）
            base_delay: 初回リトライの待機秒数（デフォルト: 1.0秒）
            auto_chunk: 大きなメッセージを自動的にチャンク分割（デフォルト: True）
            encrypt: E2E暗号化を有効にする（デフォルト: False、後方互換性のため）

        Returns:
            送信成功ならTrue、失敗ならFalse
        """
        if target_id not in self.peers:
            logger.error(f"Unknown peer: {target_id}")
            return False

        # 自動チャンク分割チェック
        if auto_chunk and self._should_use_chunking(payload, message_type):
            return await self.send_chunked_message(
                target_id=target_id,
                message_type=message_type,
                payload=payload,
                max_retries=max_retries
            )

        # 統計情報を初期化（存在しない場合）
        if target_id not in self.peer_stats:
            self.peer_stats[target_id] = PeerStats(
                entity_id=target_id,
                address=self.peers[target_id]
            )
        self.peer_stats[target_id].total_messages_sent += 1

        # E2E暗号化を適用
        actual_payload = self._prepare_payload(target_id, payload, encrypt)

        # セッション情報取得
        session_id, sequence_num = self._get_session_info(target_id)

        # メッセージ作成
        message = self._create_message_dict(
            target_id, message_type, actual_payload,
            session_id=session_id, sequence_num=sequence_num
        )
        url = f"{self.peers[target_id]}/message"

        # 送信実行
        success, status = await self._send_with_retry(
            url, message, max_retries, base_delay
        )

        # 統計更新
        self._update_send_stats(target_id, success, max_retries, status)

        if success:
            logger.info(f"Sent {message_type} to {target_id} successfully")
            return True
        else:
            logger.error(
                f"Failed to send {message_type} to {target_id} after {max_retries} attempts"
            )
            return False
        
        # キューに追加（キューが有効な場合）
        if self._queue:
            await self._queue.enqueue(target_id, message_type, payload)
        
        return False

    def _create_message_dict(
        self,
        target_id: str,
        message_type: str,
        payload: dict
    ) -> dict:
        """送信メッセージ辞書を作成
        
        Protocol v1.0形式（SecureMessage）でメッセージを作成。
        v1.1追加: session_idとsequence_numを自動付与
        
        Args:
            target_id: 送信先ピアID
            message_type: メッセージタイプ
            payload: メッセージ内容
            
        Returns:
            メッセージ辞書
        """
        # ピアの公開鍵が登録されているかチェック
        has_peer_key = (
            self.verifier is not None and 
            target_id in self.verifier.public_keys
        )
        
        # SessionManagerからsession_idとsequence_numを取得
        session_id = None
        sequence_num = None
        if self._session_manager is not None:
            try:
                # 同期的に実行（async関数だが、内部状態の更新のみ）
                import asyncio
                loop = asyncio.get_event_loop()
                session_id, sequence_num = loop.run_until_complete(
                    self._session_manager.get_next_sequence(self.entity_id, target_id)
                )
                logger.debug(f"Got session_id={session_id}, sequence_num={sequence_num} for {target_id}")
            except Exception as e:
                logger.warning(f"Failed to get session info from SessionManager: {e}")
        
        if self.enable_signing and self.signer is not None:
            # SecureMessage形式でメッセージ作成
            secure_msg = SecureMessage(
                version="1.0",
                msg_type=message_type,
                sender_id=self.entity_id,
                payload=payload
            )
            # v1.1: session_idとsequence_numを追加
            if session_id and sequence_num:
                secure_msg.session_id = session_id
                secure_msg.sequence_num = sequence_num
            secure_msg.sign(self.signer)
            logger.debug(f"Sending signed {message_type} to {target_id}")
            return secure_msg.to_dict(include_signature=True)
        
        # 署名なし形式
        message = {
            "version": "1.0",
            "msg_type": message_type,
            "sender_id": self.entity_id,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": secrets.token_hex(16)
        }
        # v1.1: session_idとsequence_numを追加
        if session_id and sequence_num:
            message["session_id"] = session_id
            message["sequence_num"] = sequence_num
        
        if not has_peer_key:
            # 公開鍵が未登録の場合はレガシー形式（session情報は含めない）
            message = {
                "from": self.entity_id,
                "type": message_type,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            logger.debug(f"Sending legacy {message_type} to {target_id} (no peer key)")
        else:
            logger.debug(f"Sending unsigned {message_type} to {target_id}")
        
        return message
    
    async def broadcast_message(
        self, 
        message_type: str, 
        payload: dict,
        exclude_peers: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """登録されている全ピアにメッセージをブロードキャスト
        
        Args:
            message_type: メッセージタイプ
            payload: メッセージの内容
            exclude_peers: 送信から除外するピアIDのリスト
            
        Returns:
            ピアIDをキー、送信結果を値とする辞書
        """
        exclude_set = set(exclude_peers or [])
        results: Dict[str, bool] = {}
        
        # 全ピアに並列送信
        tasks = []
        for peer_id in self.peers:
            if peer_id not in exclude_set:
                task = self.send_message(peer_id, message_type, payload)
                tasks.append((peer_id, task))
        
        # 並列実行
        for peer_id, task in tasks:
            try:
                results[peer_id] = await task
            except Exception as e:
                logger.error(f"Error broadcasting to {peer_id}: {e}")
                results[peer_id] = False
        
        success_count = sum(1 for v in results.values() if v)
        logger.info(
            f"Broadcast {message_type} completed: "
            f"{success_count}/{len(results)} successful"
        )
        
        return results
    
    async def send_chunked_message(
        self,
        target_id: str,
        message_type: str,
        payload: dict,
        chunk_size: int = 8192,
        max_retries: int = 3
    ) -> bool:
        """大きなメッセージをチャンク分割して送信
        
        Protocol v1.0対応:
        - ペイロードをJSON化して複数チャンクに分割
        - 各チャンクにシーケンス番号を付与
        - すべてのチャンクが送信完了するまで待機
        
        Args:
            target_id: 送信先ピアのエンティティID
            message_type: 元のメッセージタイプ
            payload: メッセージの内容
            chunk_size: 1チャンクの最大サイズ（バイト）
            max_retries: 各チャンクの最大リトライ回数
            
        Returns:
            全チャンク送信成功ならTrue、失敗ならFalse
        """
        if target_id not in self.peers:
            logger.error(f"Unknown peer: {target_id}")
            return False
        
        # メッセージIDを生成
        message_id = secrets.token_hex(16)
        
        # ペイロードをJSON文字列化
        inner_payload = {
            "original_msg_type": message_type,
            "data": payload
        }
        payload_json = json.dumps(inner_payload)
        payload_bytes = payload_json.encode('utf-8')
        
        # チャンクに分割
        chunks = []
        for i in range(0, len(payload_bytes), chunk_size):
            chunk_data = payload_bytes[i:i + chunk_size]
            chunks.append(base64.b64encode(chunk_data).decode('ascii'))
        
        total_chunks = len(chunks)
        logger.info(f"Sending chunked message {message_id} to {target_id}: {total_chunks} chunks")
        
        # 各チャンクを送信
        success = True
        for idx, chunk_data in enumerate(chunks):
            chunk_payload = {
                "message_id": message_id,
                "chunk_index": idx,
                "total_chunks": total_chunks,
                "data": chunk_data,
                "is_last": idx == total_chunks - 1
            }
            
            # 通常のsend_messageを使用（chunkタイプで送信）
            result = await self.send_message(
                target_id=target_id,
                message_type="chunk",
                payload=chunk_payload,
                max_retries=max_retries
            )
            
            if not result:
                logger.error(f"Failed to send chunk {idx + 1}/{total_chunks} of message {message_id}")
                success = False
                break
            
            logger.debug(f"Sent chunk {idx + 1}/{total_chunks} of message {message_id}")
        
        if success:
            logger.info(f"Successfully sent all chunks of message {message_id}")
        else:
            logger.error(f"Failed to send complete message {message_id}")
        
        return success
    
    async def cleanup_old_chunks(self, max_age_seconds: float = 3600) -> int:
        """古いチャンクデータをクリーンアップ
        
        Args:
            max_age_seconds: この秒数以上経過したチャンクを削除
            
        Returns:
            削除されたチャンクの数
        """
        if not hasattr(self, '_chunk_buffer') or not self._chunk_buffer:
            return 0
        
        now = datetime.now(timezone.utc)
        expired_ids = []
        
        for message_id, chunk_info in self._chunk_buffer.items():
            age = (now - chunk_info.created_at).total_seconds()
            if age > max_age_seconds:
                expired_ids.append(message_id)
        
        for message_id in expired_ids:
            del self._chunk_buffer[message_id]
            logger.debug(f"Cleaned up expired chunk buffer: {message_id}")
        
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired chunk buffers")
        
        return len(expired_ids)
    
    async def start(self) -> None:
        """サービスを開始（バックグラウンドタスク起動）"""
        if self._queue:
            await self._queue.start_retry_processor(self._send_message_direct)
        if self._heartbeat:
            await self._heartbeat.start(
                get_peers_func=lambda: list(self.peers.keys()),
                ping_func=self._ping_peer
            )
        if self._monitor:
            # 既存のピアをモニターに登録
            for peer_id, address in self.peers.items():
                self._monitor.add_peer(peer_id, address, is_manual=True)
            # モニターを開始
            await self._monitor.start()
        
        # Chunkクリーンアップループを開始
        self._chunk_cleanup_task = asyncio.create_task(self._chunk_cleanup_loop())
        
        # SessionManagerを開始
        if self._session_manager:
            await self._session_manager.start()
        
        # Connection Poolを開始
        if self._connection_pool:
            await self._connection_pool.start()
            logger.info("Connection Pool started")
        
        # DHTRegistryを開始
        if self._dht_registry:
            dht_started = await self._dht_registry.start()
            if dht_started:
                logger.info(f"DHT Registry started for peer discovery")
            else:
                logger.warning("Failed to start DHT Registry, falling back to traditional discovery")
        
        logger.info(f"PeerService started: {self.entity_id}")
    
    async def _chunk_cleanup_loop(self) -> None:
        """古いチャンクデータを定期的にクリーンアップ"""
        while True:
            try:
                # 5分ごとにクリーンアップ
                await asyncio.sleep(300)
                cleaned = await self.cleanup_old_chunks(max_age_seconds=1800)  # 30分超えを削除
                if cleaned > 0:
                    logger.debug(f"Cleaned up {cleaned} expired chunk buffers")
            except asyncio.CancelledError:
                logger.debug("Chunk cleanup loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in chunk cleanup loop: {e}")
    
    async def stop(self) -> None:
        """サービスを停止"""
        if self._queue:
            await self._queue.stop_retry_processor()
        if self._heartbeat:
            await self._heartbeat.stop()
        if self._monitor:
            await self._monitor.stop()
        
        # Chunkクリーンアップタスクを停止
        if hasattr(self, '_chunk_cleanup_task') and self._chunk_cleanup_task:
            self._chunk_cleanup_task.cancel()
            try:
                await self._chunk_cleanup_task
            except asyncio.CancelledError:
                pass
            logger.debug("Chunk cleanup loop stopped")
        
        # DHTRegistryを停止
        if self._dht_registry:
            await self._dht_registry.stop()
            logger.debug("DHT Registry stopped")
        
        logger.info(f"PeerService stopped: {self.entity_id}")
    
    async def _send_message_direct(
        self,
        target_id: str,
        message_type: str,
        payload: dict
    ) -> bool:
        """メッセージを直接送信（キュー用・内部用）"""
        if target_id not in self.peers:
            logger.error(f"Unknown peer: {target_id}")
            return False
        
        # メッセージ作成
        message = self._create_message_dict(target_id, message_type, payload)
        url = f"{self.peers[target_id]}/message"
        
        # 送信実行
        success, _ = await self._send_with_retry(
            url, message, max_retries=1, base_delay=0
        )
        return success
    
    async def _ping_peer(self, target_id: str) -> bool:
        """ピアにping送信（ハートビート用）"""
        if target_id not in self.peers:
            return False
        address = self.peers[target_id]
        url = f"{address}/health"
        timeout = ClientTimeout(
            total=self._heartbeat.ping_timeout if self._heartbeat else 5
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    is_healthy = response.status == 200
                    # 統計を更新
                    if target_id in self.peer_stats:
                        self.peer_stats[target_id].is_healthy = is_healthy
                    return is_healthy
        except Exception:
            if target_id in self.peer_stats:
                self.peer_stats[target_id].is_healthy = False
            return False
    
    def _resolve_from_registry(self, entity_id: str) -> Optional[str]:
        """レジストリからピアアドレスを解決"""
        if not self._registry:
            return None
        try:
            service = self._registry.find_by_id(entity_id)
            if service and service.is_alive():
                return service.endpoint
        except Exception as e:
            logger.error(f"Registry lookup error: {e}")
        return None
    
    def get_queue_status(self) -> Optional[dict]:
        """キュー状態を取得"""
        if not self._queue:
            return None
        return {
            "size": self._queue.get_queue_size(),
            "stats": self._queue.get_stats()
        }
    
    def get_peer_health_status(self, entity_id: str) -> Optional[str]:
        """ピアの健康状態を取得"""
        if not self._heartbeat:
            return None
        return self._heartbeat.get_status(entity_id).value
    
    def get_all_peer_health_status(self) -> Optional[Dict[str, str]]:
        """全ピアの健康状態を取得"""
        if not self._heartbeat:
            return None
        return self._heartbeat.get_all_status()
    
    def get_healthy_peers(self) -> Optional[List[str]]:
        """健全なピアのリストを取得"""
        if not self._heartbeat:
            return None
        return self._heartbeat.get_healthy_peers()
    
    # ========== Session Management Methods ==========
    
    async def create_session(
        self,
        peer_id: str,
        peer_public_key: Optional[str] = None
    ) -> Optional[dict]:
        """ピアとの新規セッションを作成
        
        Args:
            peer_id: 対向ピアのエンティティID
            peer_public_key: ピアのEd25519公開鍵（hex、オプション）
            
        Returns:
            セッション情報辞書、SessionManager無効時はNone
        """
        if not self._session_manager:
            logger.warning("SessionManager is not enabled")
            return None
        
        session = await self._session_manager.create_session(peer_id, peer_public_key)
        return session.to_dict()
    
    async def get_session(self, session_id: str) -> Optional[dict]:
        """セッションIDからセッション情報を取得
        
        Args:
            session_id: セッションUUID
            
        Returns:
            セッション情報辞書、存在しない場合はNone
        """
        if not self._session_manager:
            return None
        
        session = await self._session_manager.get_session(session_id)
        return session.to_dict() if session else None
    
    async def get_session_by_peer(self, peer_id: str) -> Optional[dict]:
        """ピアIDからセッション情報を取得
        
        Args:
            peer_id: エンティティID
            
        Returns:
            セッション情報辞書、存在しない場合はNone
        """
        if not self._session_manager:
            return None
        
        session = await self._session_manager.get_session_by_peer(peer_id)
        return session.to_dict() if session else None
    
    async def terminate_session(self, session_id: str) -> bool:
        """セッションを終了
        
        Args:
            session_id: セッションUUID
            
        Returns:
            成功した場合True
        """
        if not self._session_manager:
            return False
        
        return await self._session_manager.terminate_session(session_id)
    
    async def is_session_valid(self, session_id: str) -> bool:
        """セッションの有効性を確認
        
        Args:
            session_id: セッションUUID
            
        Returns:
            有効な場合True
        """
        if not self._session_manager:
            return False
        
        return await self._session_manager.is_session_valid(session_id)
    
    async def get_all_sessions(self) -> List[dict]:
        """全セッションのリストを取得
        
        Returns:
            セッション情報辞書のリスト
        """
        if not self._session_manager:
            return []
        
        sessions = await self._session_manager.get_all_sessions()
        return [s.to_dict() for s in sessions]
    
    async def get_session_stats(self) -> dict:
        """セッション統計を取得
        
        Returns:
            セッション統計辞書
        """
        if not self._session_manager:
            return {"enabled": False}
        
        stats = self._session_manager.get_stats()
        stats["enabled"] = True
        return stats
        
    async def handle_message(self, message: dict) -> dict:
        """受信メッセージを処理
        
        Protocol v1.0形式（SecureMessage）を処理。
        署名検証、リプレイ保護、セッション管理、シーケンス番号を実行。
        
        Args:
            message: 受信したメッセージ辞書
            
        Returns:
            処理結果の辞書 {"status": "success"|"error", "reason": str}
        """
        # メッセージ形式を判定
        is_secure_format = "version" in message and "sender_id" in message
        is_legacy_format = "from" in message and "type" in message and not is_secure_format
        
        if is_secure_format:
            # Protocol v1.0 SecureMessage形式
            msg_type = message.get("msg_type")
            sender = message.get("sender_id", "unknown")
            
            # Rate limiting check (v1.1)
            if self._rate_limiter is not None:
                allowed, retry_after = await self._rate_limiter.check_rate_limit(sender, msg_type)
                if not allowed:
                    logger.warning(f"Rate limit exceeded for peer {sender}, retry after {retry_after}s")
                    return {
                        "status": "error", 
                        "reason": "rate_limited",
                        "retry_after": retry_after
                    }
            signature = message.get("signature")
            nonce = message.get("nonce")
            timestamp = message.get("timestamp")
            version = message.get("version")
            
            # バージョンチェック（v0.3とv1.0の両方を許可）
            if version not in ("0.3", "1.0"):
                logger.warning(f"Unsupported message version: {version}")
                return {"status": "error", "reason": f"Unsupported version: {version}"}
            
            # 署名検証（リプレイ保護より先に実行）
            if self.enable_verification and self.verifier is not None and signature:
                try:
                    # 署名対象データを取得（重複を避けるためヘルパー関数を使用）
                    signable_data = SecureMessage._get_signable_data_from_fields(
                        version=message["version"],
                        msg_type=message["msg_type"],
                        sender_id=message["sender_id"],
                        payload=message["payload"],
                        timestamp=message["timestamp"],
                        nonce=message["nonce"]
                    )
                    
                    is_valid_sig = self.verifier.verify_message(
                        signable_data, signature, sender
                    )
                    
                    if not is_valid_sig:
                        logger.warning(f"Invalid signature from {sender}")
                        return {"status": "error", "reason": "Invalid signature"}
                    
                    logger.debug(f"Signature verified for {msg_type} from {sender}")
                    
                except ValueError as e:
                    # 公開鍵が未登録
                    if "Unknown sender" in str(e):
                        logger.warning(f"No public key registered for sender: {sender}")
                        # 公開鍵が未登録の場合は従来通り処理（開発時用）
                        if self.enable_verification:
                            return {"status": "error", "reason": f"Unknown sender: {sender}"}
                    else:
                        raise
                except Exception as e:
                    logger.error(f"Signature verification error: {e}")
                    return {"status": "error", "reason": f"Signature verification error: {e}"}
            elif self.enable_verification and not signature:
                logger.warning(f"Message from {sender} has no signature but verification is enabled")
                return {"status": "error", "reason": "Missing signature"}
            
        elif is_legacy_format:
            # 従来形式（フォールバック）
            msg_type = message.get("type")
            sender = message.get("from", "unknown")
            logger.debug(f"Received legacy format message from {sender}")
        else:
            # 不明な形式
            logger.warning(f"Unknown message format: {list(message.keys())}")
            return {"status": "error", "reason": "Unknown message format"}
        
        # 送信元の統計を更新
        if sender in self.peer_stats:
            self.peer_stats[sender].total_messages_received += 1
        
        # シーケンス番号検証（v1.0プロトコル）
        session_id = message.get("session_id")
        sequence_num = message.get("sequence_num")
        
        # v1.0プロトコルではsession_idとsequence_numが必須
        if version == "1.0":
            if not session_id:
                logger.warning(f"Missing session_id from {sender} in v1.0 message")
                return {
                    "status": "error",
                    "reason": "Missing required field: session_id",
                    "error_code": "INVALID_MESSAGE"
                }
            if sequence_num is None:
                logger.warning(f"Missing sequence_num from {sender} in v1.0 message")
                return {
                    "status": "error",
                    "reason": "Missing required field: sequence_num",
                    "error_code": "INVALID_MESSAGE"
                }
        
        if session_id and sequence_num is not None and version == "1.0":
            # セッションを取得
            session = await self._session_manager.get_session_by_peer(sender)
            
            if session:
                # セッションIDが一致するか確認
                if session.session_id != session_id:
                    logger.warning(
                        f"Session ID mismatch from {sender}: "
                        f"received={session_id}, expected={session.session_id}"
                    )
                    return {
                        "status": "error",
                        "reason": "SESSION_EXPIRED",
                        "error_code": "SESSION_EXPIRED",
                        "message": "Invalid session ID"
                    }
                
                # セッションが有効か確認
                if not session.is_valid():
                    logger.warning(f"Expired session from {sender}: {session_id}")
                    return {
                        "status": "error",
                        "reason": "SESSION_EXPIRED",
                        "error_code": "SESSION_EXPIRED",
                        "message": "Session has expired"
                    }
                
                expected_seq = session.expected_sequence
                received_seq = int(sequence_num)
                
                if received_seq < expected_seq:
                    # 古いシーケンス番号（リプレイの可能性）
                    logger.warning(
                        f"Sequence error from {sender}: "
                        f"received={received_seq}, expected>={expected_seq}"
                    )
                    return {
                        "status": "error",
                        "reason": "SEQUENCE_ERROR",
                        "error_code": "SEQUENCE_ERROR",
                        "expected": expected_seq,
                        "received": received_seq
                    }
                elif received_seq > expected_seq:
                    # シーケンス番号が飛んだ（メッセージ欠落の可能性）
                    logger.warning(
                        f"Sequence gap detected from {sender}: "
                        f"received={received_seq}, expected={expected_seq}"
                    )
                    # 欠落を記録しつつ処理は続行
                
                # 期待シーケンス番号を更新
                session.expected_sequence = received_seq + 1
                session.update_activity()
                logger.debug(f"Sequence validated for {sender}: {received_seq}")

        # 暗号化ペイロードの復号（E2E暗号化対応）
        payload = message.get("payload", {})
        
        # E2E暗号化メッセージの復号（E2ECryptoManager使用）
        if isinstance(payload, dict) and payload.get("_e2e_encrypted"):
            if self.e2e_manager and E2E_CRYPTO_AVAILABLE:
                try:
                    session_id = payload.get("session_id")
                    if session_id:
                        e2e_session = self.e2e_manager.get_session(session_id)
                        if e2e_session:
                            # SecureMessageライクな構造を作成
                            from services.crypto import SecureMessage
                            encrypted_msg = SecureMessage(
                                version="1.0",
                                msg_type=msg_type,
                                sender_id=sender,
                                recipient_id=self.entity_id,
                                payload={"encrypted": True, "data": payload.get("data"), "nonce": payload.get("nonce")},
                                session_id=session_id,
                                sequence_num=message.get("sequence_num")
                            )
                            decrypted = self.e2e_manager.decrypt_message(e2e_session, encrypted_msg)
                            if decrypted:
                                message["payload"] = decrypted
                                message["_decrypted"] = True
                                logger.debug(f"Payload E2E decrypted from {sender} using session {session_id}")
                            else:
                                logger.error(f"Failed to E2E decrypt payload from {sender}")
                                return {"status": "error", "reason": "E2E Decryption failed"}
                except Exception as e:
                    logger.error(f"E2E decryption error from {sender}: {e}")
                    return {"status": "error", "reason": f"E2E decryption error: {e}"}
        
        # 従来の暗号化ペイロードの復号
        elif isinstance(payload, dict) and "_encrypted_payload" in payload:
            encrypted_data = payload["_encrypted_payload"]
            decrypted = self.decrypt_payload(sender, encrypted_data)
            if decrypted:
                message["payload"] = decrypted
                message["_decrypted"] = True  # 復号済みフラグ
                logger.debug(f"Payload decrypted from {sender} (legacy method)")
            else:
                logger.error(f"Failed to decrypt payload from {sender}")
                return {"status": "error", "reason": "Decryption failed"}

        # ハンドラを実行
        handler = self.message_handlers.get(msg_type)
        if handler:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Error handling {msg_type} from {sender}: {e}")
                return {"status": "error", "reason": f"Handler error: {e}"}
        else:
            logger.warning(f"No handler for message type: {msg_type} from {sender}")
        
        return {"status": "success"}
            
    def add_peer(
        self, 
        entity_id: str, 
        address: str, 
        public_key_hex: Optional[str] = None,
        public_key: Optional[str] = None,
        x25519_public_key: Optional[str] = None
    ) -> None:
        """ピアを登録
        
        Args:
            entity_id: ピアのエンティティID
            address: ピアのアドレス（例: http://localhost:8001）
            public_key_hex: ピアの公開鍵（hexエンコード、オプション）
            public_key: public_key_hexのエイリアス（互換性用）
            x25519_public_key: X25519公開鍵（Base64、オプション、将来用）
        """
        # public_keyが指定されていればpublic_key_hexとして使用
        if public_key and not public_key_hex:
            public_key_hex = public_key
            
        self.peers[entity_id] = address
        
        # PeerInfoを作成/更新
        self.peer_infos[entity_id] = PeerInfo(
            entity_id=entity_id,
            address=address,
            public_key=public_key_hex
        )
        
        # X25519公開鍵が提供された場合はセッション情報に保存（将来用）
        if x25519_public_key:
            # 将来の実装のために保存
            if entity_id not in self.encryption_sessions:
                self.encryption_sessions[entity_id] = {}
            self.encryption_sessions[entity_id]["x25519_public_key"] = x25519_public_key
        
        # 公開鍵が提供された場合は登録
        if public_key_hex and CRYPTO_AVAILABLE:
            self.add_peer_public_key(entity_id, public_key_hex)
        
        # 統計情報を初期化
        if entity_id not in self.peer_stats:
            self.peer_stats[entity_id] = PeerStats(
                entity_id=entity_id,
                address=address
            )
        
        # ハートビートに登録
        if self._heartbeat:
            self._heartbeat.register_peer(entity_id)
        
        # モニターに登録
        if self._monitor:
            self._monitor.add_peer(entity_id, address, is_manual=True, public_key_hex=public_key_hex)
        
        logger.info(f"Added peer: {entity_id} at {address}" + 
                   (f" with public key" if public_key_hex else ""))
    
    def remove_peer(self, entity_id: str) -> bool:
        """ピアを削除
        
        Args:
            entity_id: 削除するピアのエンティティID
            
        Returns:
            削除成功ならTrue、存在しなければFalse
        """
        if entity_id not in self.peers:
            logger.warning(f"Cannot remove unknown peer: {entity_id}")
            return False
        
        del self.peers[entity_id]
        
        # PeerInfoも削除
        if entity_id in self.peer_infos:
            del self.peer_infos[entity_id]
        
        # 統計情報は保持（履歴のため）
        if entity_id in self.peer_stats:
            self.peer_stats[entity_id].is_healthy = False
        
        # Verifierからも公開鍵を削除（オプション）
        if self.verifier and entity_id in self.verifier.public_keys:
            del self.verifier.public_keys[entity_id]
            if entity_id in self.verifier._verify_keys:
                del self.verifier._verify_keys[entity_id]
        
        # ハートビートから解除
        if self._heartbeat:
            self._heartbeat.unregister_peer(entity_id)
        
        # モニターから削除
        if self._monitor:
            self._monitor.remove_peer(entity_id)
        
        logger.info(f"Removed peer: {entity_id}")
        return True

    async def check_peer_health(self, peer_id: str, timeout: float = 5.0) -> bool:
        """ピアのヘルスチェックを実行

        Args:
            peer_id: チェック対象のピアID
            timeout: タイムアウト秒数

        Returns:
            ピアが健全ならTrue、そうでなければFalse
        """
        if peer_id not in self.peers:
            logger.error(f"Cannot check health of unknown peer: {peer_id}")
            return False

        address = self.peers[peer_id]
        url = f"{address}/health"
        client_timeout = ClientTimeout(total=timeout, connect=2)

        try:
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.get(url) as response:
                    is_healthy = response.status == 200

                    # 統計を更新
                    if peer_id not in self.peer_stats:
                        self.peer_stats[peer_id] = PeerStats(
                            entity_id=peer_id,
                            address=address
                        )

                    self.peer_stats[peer_id].is_healthy = is_healthy
                    if is_healthy:
                        self.peer_stats[peer_id].last_seen = datetime.now(timezone.utc)

                    logger.info(f"Health check for {peer_id}: {'healthy' if is_healthy else 'unhealthy'}")
                    return is_healthy

        except asyncio.TimeoutError:
            logger.warning(f"Health check timeout for {peer_id}")
            self._update_peer_health_status(peer_id, False, "Timeout")
            return False
        except ClientError as e:
            logger.warning(f"Health check connection error for {peer_id}: {e}")
            self._update_peer_health_status(peer_id, False, str(e))
            return False
        except Exception as e:
            logger.error(f"Health check unexpected error for {peer_id}: {e}")
            self._update_peer_health_status(peer_id, False, str(e))
            return False

    def _update_peer_health_status(self, peer_id: str, is_healthy: bool, error: Optional[str] = None) -> None:
        """ピアのヘルス状態を更新（内部メソッド）

        Args:
            peer_id: ピアID
            is_healthy: 健全状態
            error: エラーメッセージ（存在する場合）
        """
        if peer_id in self.peer_stats:
            self.peer_stats[peer_id].is_healthy = is_healthy
            if error:
                self.peer_stats[peer_id].last_error = error

    async def check_all_peers_health(self, timeout: float = 5.0) -> Dict[str, bool]:
        """全ピアのヘルスチェックを実行

        Args:
            timeout: タイムアウト秒数

        Returns:
            ピアIDをキー、ヘルス状態を値とする辞書
        """
        results: Dict[str, bool] = {}

        for peer_id in self.peers:
            results[peer_id] = await self.check_peer_health(peer_id, timeout)

        healthy_count = sum(1 for v in results.values() if v)
        logger.info(f"Health check all peers: {healthy_count}/{len(results)} healthy")

        return results

    def get_peer_stats(self, peer_id: Optional[str] = None) -> dict:
        """ピア接続統計を返却

        Args:
            peer_id: 特定のピアID（省略時は全ピア）

        Returns:
            ピア統計情報の辞書
        """
        def stats_to_dict(stats: PeerStats) -> dict:
            return {
                "entity_id": stats.entity_id,
                "address": stats.address,
                "total_messages_sent": stats.total_messages_sent,
                "total_messages_received": stats.total_messages_received,
                "successful_deliveries": stats.successful_deliveries,
                "failed_deliveries": stats.failed_deliveries,
                "last_seen": stats.last_seen.isoformat() if stats.last_seen else None,
                "last_error": stats.last_error,
                "is_healthy": stats.is_healthy
            }

        if peer_id:
            if peer_id in self.peer_stats:
                return stats_to_dict(self.peer_stats[peer_id])
            return {}

        return {
            peer_id: stats_to_dict(stats) 
            for peer_id, stats in self.peer_stats.items()
        }

    # ============ API Server 統合機能 ============

    async def authenticate_with_api_server(
        self,
        entity_id: Optional[str] = None,
        api_key: Optional[str] = None,
        api_server_url: Optional[str] = None
    ) -> bool:
        """
        API ServerからJWTトークンを取得
        
        Args:
            entity_id: エンティティID（省略時はself.entity_id）
            api_key: APIキー（省略時は環境変数から）
            api_server_url: API Server URL（省略時は環境変数から）
            
        Returns:
            認証成功ならTrue
        """
        url = api_server_url or self.api_server_url
        key = api_key or self.api_key
        eid = entity_id or self.entity_id
        
        if not url:
            logger.error("API Server URL not configured")
            return False
        
        if not key:
            logger.error("API key not configured")
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/auth/token",
                    json={
                        "entity_id": eid,
                        "api_key": key
                    },
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.jwt_token = data.get("access_token")
                        expires_in = data.get("expires_in", 300)
                        self.jwt_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                        self.api_server_url = url  # 保存
                        logger.info(f"Successfully authenticated with API Server as {eid}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Authentication failed: HTTP {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error authenticating with API Server: {e}")
            return False
    
    async def refresh_token_if_needed(self) -> bool:
        """
        トークンが期限切れに近い場合に更新
        
        Returns:
            更新が必要かつ成功した場合True、不要な場合もTrue
        """
        if not self.jwt_token or not self.jwt_expires_at:
            return await self.authenticate_with_api_server()
        
        # 期限切れ5分前に更新
        time_until_expiry = (self.jwt_expires_at - datetime.now(timezone.utc)).total_seconds()
        if time_until_expiry < 300:
            logger.info("JWT token expiring soon, refreshing...")
            return await self.authenticate_with_api_server()
        
        return True
    
    def is_authenticated_with_api_server(self) -> bool:
        """API Server認証状態を確認"""
        if not self.jwt_token or not self.jwt_expires_at:
            return False
        return datetime.now(timezone.utc) < self.jwt_expires_at
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        認証ヘッダーを取得
        
        Returns:
            Authorizationヘッダーを含む辞書
        """
        headers = {"Content-Type": "application/json"}
        
        if self.jwt_token and self.is_authenticated_with_api_server():
            headers["Authorization"] = f"Bearer {self.jwt_token}"
        elif self.api_key:
            headers["X-API-Key"] = self.api_key
            
        return headers

    # ============ メッセージ暗号化機能 ============

    async def send_encrypted_message(
        self,
        target_id: str,
        message_type: str,
        payload: dict,
        max_retries: int = 3
    ) -> bool:
        """
        X25519鍵共有で暗号化したメッセージを送信
        
        Args:
            target_id: 送信先ピアのエンティティID
            message_type: メッセージタイプ
            payload: メッセージの内容
            max_retries: 最大リトライ回数
            
        Returns:
            送信成功ならTrue
        """
        if not CRYPTO_AVAILABLE or not self.key_pair:
            logger.error("Crypto not available for encrypted messaging")
            return False
        
        if target_id not in self.peers:
            logger.error(f"Unknown peer: {target_id}")
            return False
        
        # ピアの公開鍵を取得
        peer_info = self.peer_infos.get(target_id)
        if not peer_info or not peer_info.public_key:
            logger.error(f"No public key for peer {target_id}")
            return False
        
        try:
            # 暗号化メッセージを作成
            encrypted_msg = EncryptedMessage.encrypt(
                sender_keypair=self.key_pair,
                recipient_public_key=bytes.fromhex(peer_info.public_key),
                sender_id=self.entity_id,
                recipient_id=target_id,
                plaintext={
                    "msg_type": message_type,
                    "payload": payload
                }
            )
            
            # 署名を追加
            if self.signer:
                signature = encrypted_msg.sign(self.signer)
            else:
                signature = None
            
            # 送信データ
            message_data = encrypted_msg.to_dict()
            if signature:
                message_data["signature"] = signature
            
            # 送信
            address = self.peers[target_id]
            url = f"{address}/message"
            
            for attempt in range(max_retries):
                try:
                    timeout = ClientTimeout(total=10, connect=5)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(
                            url,
                            json=message_data,
                            headers=self.get_auth_headers()
                        ) as response:
                            if response.status == 200:
                                logger.info(f"Sent encrypted {message_type} to {target_id}")
                                return True
                            else:
                                logger.warning(f"Failed to send encrypted message: HTTP {response.status}")
                                if response.status in (400, 401, 403, 404):
                                    break
                                    
                except Exception as e:
                    logger.warning(f"Error sending encrypted message (attempt {attempt+1}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1.0 * (2 ** attempt))
            
            return False
            
        except Exception as e:
            logger.error(f"Error creating encrypted message: {e}")
            return False
    
    async def handle_encrypted_message(self, message: dict) -> dict:
        """
        暗号化メッセージを復号して処理
        
        Args:
            message: 受信した暗号化メッセージ辞書
            
        Returns:
            処理結果の辞書
        """
        if not CRYPTO_AVAILABLE or not self.key_pair:
            return {"status": "error", "reason": "Crypto not available"}
        
        try:
            # 暗号化メッセージをパース
            encrypted_msg = EncryptedMessage.from_dict(message)
            
            # 署名検証（もしあれば）
            signature = message.get("signature")
            if signature and self.verifier and self.enable_verification:
                signable_data = {
                    "sender_id": encrypted_msg.sender_id,
                    "recipient_id": encrypted_msg.recipient_id,
                    "ciphertext": message.get("ciphertext"),
                    "timestamp": encrypted_msg.timestamp
                }
                
                # 送信者の公開鍵が登録されていなければ追加
                sender_key = message.get("sender_public_key")
                if sender_key and encrypted_msg.sender_id not in self.verifier.public_keys:
                    self.verifier.add_public_key_hex(encrypted_msg.sender_id, sender_key)
                
                is_valid = self.verifier.verify_message(
                    signable_data, signature, encrypted_msg.sender_id
                )
                if not is_valid:
                    return {"status": "error", "reason": "Invalid signature"}
            
            # 復号
            plaintext = encrypted_msg.decrypt(self.key_pair.private_key)
            
            # 元のメッセージタイプとペイロードを取得
            msg_type = plaintext.get("msg_type", "encrypted")
            payload = plaintext.get("payload", {})
            
            # ハンドラに委譲
            handler = self.message_handlers.get(msg_type)
            if handler:
                await handler({
                    "msg_type": msg_type,
                    "sender_id": encrypted_msg.sender_id,
                    "payload": payload
                })
            
            return {"status": "success", "decrypted_type": msg_type}
            
        except Exception as e:
            logger.error(f"Error handling encrypted message: {e}")
            return {"status": "error", "reason": f"Decryption failed: {e}"}

    # ============ セキュアハンドシェイク ============

    async def initiate_secure_handshake(
        self,
        target_id: str,
        timeout: float = 30.0
    ) -> Tuple[bool, Optional[str]]:
        """
        新規ピアとのセキュアハンドシェイクを開始
        
        Args:
            target_id: 対象ピアのエンティティID
            timeout: タイムアウト秒数
            
        Returns:
            (成功ならTrue, エラーメッセージ)
        """
        if not CRYPTO_AVAILABLE or not self.key_pair or not self.signer:
            return False, "Crypto not available"
        
        if target_id not in self.peers:
            return False, f"Unknown peer: {target_id}"
        
        # チャレンジを生成
        challenge = HandshakeChallenge.generate(self.entity_id)
        self._handshake_challenges[target_id] = challenge
        
        address = self.peers[target_id]
        
        try:
            async with aiohttp.ClientSession() as session:
                # 1. チャレンジを送信
                async with session.post(
                    f"{address}/handshake/challenge",
                    json={
                        "challenger_id": self.entity_id,
                        "challenge": challenge.to_dict(),
                        "public_key": self.key_pair.get_public_key_hex()
                    },
                    timeout=ClientTimeout(total=timeout)
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        return False, f"Challenge rejected: {error}"
                    
                    # 2. レスポンスを受信
                    response_data = await response.json()
                    
                    # 3. レスポンスを検証
                    if not self.verifier:
                        self.verifier = SignatureVerifier()
                    
                    is_valid, error = challenge.verify_response(response_data, self.verifier)
                    if not is_valid:
                        return False, f"Handshake verification failed: {error}"
                    
                    # 4. ピアの公開鍵を登録
                    responder_public_key = response_data.get("responder_public_key")
                    if responder_public_key:
                        self.add_peer_public_key(target_id, responder_public_key)
                    
                    logger.info(f"Secure handshake completed with {target_id}")
                    return True, None
                    
        except asyncio.TimeoutError:
            return False, "Handshake timeout"
        except Exception as e:
            return False, f"Handshake error: {e}"
        finally:
            # チャレンジを削除
            self._handshake_challenges.pop(target_id, None)
    
    async def handle_handshake_challenge(self, challenge_data: dict) -> dict:
        """
        ハンドシェイクチャレンジに応答
        
        Args:
            challenge_data: チャレンジデータ
            
        Returns:
            レスポンス辞書
        """
        if not CRYPTO_AVAILABLE or not self.key_pair:
            return {"status": "error", "reason": "Crypto not available"}
        
        try:
            challenger_id = challenge_data.get("challenger_id")
            challenge_dict = challenge_data.get("challenge", {})
            challenger_public_key = challenge_data.get("public_key")
            
            # チャレンジを復元
            challenge = HandshakeChallenge(
                challenger_id=challenge_dict.get("challenger_id", ""),
                challenge=bytes.fromhex(challenge_dict.get("challenge", "")),
                timestamp=challenge_dict.get("timestamp", "")
            )
            
            # タイムスタンプ検証（古すぎるチャレンジは拒否）
            challenge_time = datetime.fromisoformat(challenge.timestamp)
            age = (datetime.now(timezone.utc) - challenge_time).total_seconds()
            if age > 60:
                return {"status": "error", "reason": "Challenge expired"}
            
            # レスポンスを作成
            response = challenge.create_response(self.entity_id, self.key_pair)
            
            # ピアの公開鍵を登録
            if challenger_public_key and self.verifier:
                self.verifier.add_public_key_hex(challenger_id, challenger_public_key)
            
            logger.info(f"Responded to handshake challenge from {challenger_id}")
            return response
            
        except Exception as e:
            logger.error(f"Error handling handshake challenge: {e}")
            return {"status": "error", "reason": str(e)}

    async def _handle_handshake_ack(self, message: dict) -> None:
        """
        v1.0 プロトコル: handshake_ack メッセージハンドラ
        
        ピアからのhandshake_ackを処理し、セッションを確立する。
        
        Args:
            message: handshake_ack メッセージ
            
        Expected payload:
            - sender_id: 送信者ID
            - public_key: 送信者の公開鍵（hex）
            - challenge_response: チャレンジレスポンス
            - session_id: セッションID（UUID v4）
            - selected_version: 選択されたプロトコルバージョン
        """
        try:
            sender_id = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            
            logger.info(f"Received handshake_ack from {sender_id}")
            
            # 必須フィールドの検証
            public_key_hex = payload.get("public_key")
            challenge_response = payload.get("challenge_response")
            session_id = payload.get("session_id")
            selected_version = payload.get("selected_version")
            
            if not all([public_key_hex, challenge_response, session_id]):
                logger.error(f"Missing required fields in handshake_ack from {sender_id}")
                return
            
            # セッションIDの形式検証（UUID v4）
            try:
                import uuid
                parsed_uuid = uuid.UUID(session_id)
                if parsed_uuid.version != 4:
                    logger.error(f"Invalid session_id version: {parsed_uuid.version}")
                    return
            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid session_id format: {e}")
                return
            
            # challenge_responseの検証（保留中のチャレンジがある場合）
            if sender_id in self._handshake_challenges:
                challenge = self._handshake_challenges[sender_id]
                
                if self.verifier:
                    is_valid, error = challenge.verify_response(challenge_response, self.verifier)
                    if not is_valid:
                        logger.error(f"Challenge verification failed for {sender_id}: {error}")
                        return
                    logger.info(f"Challenge response verified for {sender_id}")
            
            # ピアの公開鍵を登録
            if public_key_hex:
                self.add_peer_public_key(sender_id, public_key_hex)
            
            # セッション情報を作成
            now = datetime.now(timezone.utc)
            session_info = SessionInfo(
                session_id=session_id,
                peer_id=sender_id,
                created_at=now,
                last_activity=now,
                sequence_num=0,
                established=False  # handshake_confirm後にTrueに変更
            )
            self._sessions[session_id] = session_info
            
            # 統計を更新
            if sender_id in self.peer_stats:
                self.peer_stats[sender_id].total_messages_received += 1
                self.peer_stats[sender_id].last_seen = now
            
            logger.info(
                f"Session initialized for {sender_id}: "
                f"session_id={session_id}, version={selected_version}"
            )
            
        except Exception as e:
            logger.error(f"Error handling handshake_ack: {e}")

    async def _handle_handshake_confirm(self, message: dict) -> None:
        """
        v1.0 プロトコル: handshake_confirm メッセージハンドラ
        
        ピアからのhandshake_confirmを処理し、セッションを確立済みとしてマークする。
        
        Args:
            message: handshake_confirm メッセージ
            
        Expected payload:
            - session_id: セッションID（UUID v4）
            - confirm: 確認フラグ（bool）
            - timestamp: ISO8601 UTC タイムスタンプ
        """
        try:
            sender_id = message.get("sender_id", message.get("from", "unknown"))
            payload = message.get("payload", {})
            
            logger.info(f"Received handshake_confirm from {sender_id}")
            
            # 必須フィールドの検証
            session_id = payload.get("session_id")
            confirm = payload.get("confirm", False)
            timestamp_str = payload.get("timestamp")
            
            if not session_id:
                logger.error(f"Missing session_id in handshake_confirm from {sender_id}")
                return
            
            # セッションの存在確認
            if session_id not in self._sessions:
                logger.error(f"Unknown session_id: {session_id}")
                return
            
            session_info = self._sessions[session_id]
            
            # 送信者とセッションのピアIDが一致するか確認
            if session_info.peer_id != sender_id:
                logger.error(
                    f"Peer ID mismatch: session expects {session_info.peer_id}, "
                    f"but received from {sender_id}"
                )
                return
            
            # 確認フラグの検証
            if not confirm:
                logger.warning(f"Handshake not confirmed by {sender_id}")
                # セッションを削除
                del self._sessions[session_id]
                return
            
            # タイムスタンプの検証（オプション）
            if timestamp_str:
                try:
                    confirm_time = datetime.fromisoformat(timestamp_str)
                    age = (datetime.now(timezone.utc) - confirm_time).total_seconds()
                    if abs(age) > 60:  # 60秒以上の差は拒否
                        logger.warning(f"Stale handshake_confirm from {sender_id}: age={age}s")
                        return
                except ValueError:
                    logger.warning(f"Invalid timestamp in handshake_confirm from {sender_id}")
            
            # セッションを確立済みとしてマーク
            session_info.established = True
            session_info.last_activity = datetime.now(timezone.utc)
            session_info.sequence_num = 1  # 最初のシーケンス番号を設定
            
            # 統計を更新
            if sender_id in self.peer_stats:
                self.peer_stats[sender_id].total_messages_received += 1
                self.peer_stats[sender_id].last_seen = datetime.now(timezone.utc)
                self.peer_stats[sender_id].is_healthy = True
            
            logger.info(
                f"Session established with {sender_id}: "
                f"session_id={session_id}, sequence_num={session_info.sequence_num}"
            )
            
        except Exception as e:
            logger.error(f"Error handling handshake_confirm: {e}")

    # ============ Wake Up Protocol Methods ============

    async def send_wake_up(
        self,
        target_id: str,
        reason: str = "task_available",
        timeout: float = 10.0,
        max_retries: int = 3
    ) -> Tuple[bool, Optional[str]]:
        """ピアにwake_upメッセージを送信

        Wake Up Protocolにより、休眠中のピアを起こすためのメッセージを送信する。
        タイムアウトとリトライ（3回）を実装。

        Args:
            target_id: 送信先ピアのエンティティID
            reason: 起動理由（デフォルト: "task_available"）
            timeout: 1回あたりのタイムアウト秒数（デフォルト: 10.0秒）
            max_retries: 最大リトライ回数（デフォルト: 3）

        Returns:
            (成功ならTrue, エラーメッセージ)
        """
        if target_id not in self.peers:
            return False, f"Unknown peer: {target_id}"

        # 内部状態を初期化（必要に応じて）
        if not hasattr(self, '_wake_up_states'):
            self._wake_up_states: Dict[str, Dict[str, Any]] = {}

        # wake_up状態を記録
        self._wake_up_states[target_id] = {
            "reason": reason,
            "sent_at": datetime.now(timezone.utc),
            "ack_received": False,
            "retry_count": 0
        }

        # ペイロード作成
        payload = {
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # メッセージ送信（リトライ付き）
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Sending wake_up to {target_id} (attempt {attempt}/{max_retries}, reason={reason})")

                success = await self.send_message(
                    target_id=target_id,
                    message_type="wake_up",
                    payload=payload,
                    max_retries=1,  # 個別送信のリトライは1回のみ（外側ループで制御）
                    base_delay=timeout
                )

                if success:
                    logger.info(f"wake_up sent successfully to {target_id}")
                    self._wake_up_states[target_id]["retry_count"] = attempt
                    return True, None
                else:
                    logger.warning(f"wake_up send failed to {target_id} (attempt {attempt})")

            except Exception as e:
                logger.error(f"Error sending wake_up to {target_id} (attempt {attempt}): {e}")

            # リトライ間隔を増加（指数バックオフ）
            if attempt < max_retries:
                backoff = min(timeout * (2 ** (attempt - 1)), 30.0)  # 最大30秒
                logger.debug(f"Retrying wake_up to {target_id} after {backoff:.1f}s")
                await asyncio.sleep(backoff)

        # 全リトライ失敗
        self._wake_up_states[target_id]["retry_count"] = max_retries
        error_msg = f"Failed to send wake_up to {target_id} after {max_retries} attempts"
        logger.error(error_msg)
        return False, error_msg

    async def handle_wake_up(self, message: dict) -> None:
        """wake_upメッセージを受信

        ピアからの起動通知を処理し、wake_up_ackを返信する。
        必要に応じてcapability_queryを送信。

        Args:
            message: 受信したメッセージ辞書
        """
        sender = message.get("sender_id", message.get("from", "unknown"))
        payload = message.get("payload", {})
        wake_reason = payload.get("reason", "unspecified")
        timestamp = payload.get("timestamp")

        logger.info(f"Received wake_up from {sender}, reason={wake_reason}")

        # 統計を更新
        if sender in self.peer_stats:
            self.peer_stats[sender].total_messages_received += 1
            self.peer_stats[sender].last_seen = datetime.now(timezone.utc)
            self.peer_stats[sender].is_healthy = True

        # ピアの状態を更新
        if sender in self.peers:
            logger.info(f"Peer {sender} is now awake and ready (reason: {wake_reason})")

            # wake_up_ackを返信
            try:
                ack_payload = {
                    "acknowledged": True,
                    "reason": wake_reason,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await self.send_message(
                    target_id=sender,
                    message_type="wake_up_ack",
                    payload=ack_payload
                )
                logger.debug(f"Sent wake_up_ack to {sender}")
            except Exception as e:
                logger.error(f"Failed to send wake_up_ack to {sender}: {e}")

            # 必要に応じてcapability_queryを送信（既存コードの流れに従う）
            try:
                query_payload = {"timestamp": datetime.now(timezone.utc).isoformat()}
                await self.send_message(
                    target_id=sender,
                    message_type="capability_query",
                    payload=query_payload
                )
                logger.debug(f"Sent capability_query to {sender} after wake_up")
            except Exception as e:
                logger.error(f"Failed to send capability_query to {sender}: {e}")
        else:
            logger.warning(f"Received wake_up from unknown peer: {sender}")

    async def send_wake_up_ack(
        self,
        target_id: str,
        wake_up_id: Optional[str] = None,
        reason: str = "awake"
    ) -> bool:
        """wake_up_ackメッセージを送信

        Wake Up Protocolの応答メッセージを送信する。

        Args:
            target_id: 送信先ピアのエンティティID
            wake_up_id: 対応するwake_upメッセージのID（オプション）
            reason: 応答理由（デフォルト: "awake"）

        Returns:
            送信成功ならTrue
        """
        if target_id not in self.peers:
            logger.warning(f"Cannot send wake_up_ack: unknown peer {target_id}")
            return False

        try:
            ack_payload = {
                "acknowledged": True,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            if wake_up_id:
                ack_payload["wake_up_id"] = wake_up_id

            success = await self.send_message(
                target_id=target_id,
                message_type="wake_up_ack",
                payload=ack_payload
            )

            if success:
                logger.debug(f"Sent wake_up_ack to {target_id}")
            else:
                logger.warning(f"Failed to send wake_up_ack to {target_id}")

            return success

        except Exception as e:
            logger.error(f"Error sending wake_up_ack to {target_id}: {e}")
            return False

    async def send_token_transfer(
        self,
        recipient_id: str,
        amount: float,
        token_type: str = "AGT",
        transfer_id: Optional[str] = None,
        memo: Optional[str] = None,
        timeout: float = 10.0,
        max_retries: int = 3
    ) -> Tuple[bool, Optional[str]]:
        """トークン転送メッセージを送信

        Args:
            recipient_id: 受信者のエンティティID
            amount: 転送量
            token_type: トークンタイプ（デフォルト: AGT）
            transfer_id: 転送ID（オプション、未指定時は自動生成）
            memo: 転送メモ（オプション）
            timeout: タイムアウト秒数（デフォルト: 10.0秒）
            max_retries: 最大リトライ回数（デフォルト: 3）

        Returns:
            (成功ならTrue, エラーメッセージ)
        """
        if recipient_id not in self.peers:
            return False, f"Unknown peer: {recipient_id}"

        # transfer_id が未指定の場合は自動生成
        if transfer_id is None:
            transfer_id = str(uuid.uuid4())

        # ペイロード作成
        payload = {
            "transfer_id": transfer_id,
            "sender_address": self.entity_id,
            "recipient_address": recipient_id,
            "amount": amount,
            "token_type": token_type,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if memo:
            payload["memo"] = memo

        # メッセージ送信（リトライ付き）
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Sending token_transfer to {recipient_id} (attempt {attempt}/{max_retries}, amount={amount} {token_type})")

                success = await self.send_message(
                    target_id=recipient_id,
                    message_type="token_transfer",
                    payload=payload,
                    max_retries=1,  # 個別送信のリトライは1回のみ（外側ループで制御）
                    base_delay=timeout
                )

                if success:
                    logger.info(f"token_transfer sent successfully to {recipient_id} (transfer_id={transfer_id})")
                    return True, None
                else:
                    logger.warning(f"token_transfer send failed to {recipient_id} (attempt {attempt})")

            except Exception as e:
                logger.error(f"Error sending token_transfer to {recipient_id} (attempt {attempt}): {e}")

            # リトライ間隔を増加（指数バックオフ）
            if attempt < max_retries:
                backoff = min(timeout * (2 ** (attempt - 1)), 30.0)  # 最大30秒
                logger.debug(f"Retrying token_transfer to {recipient_id} after {backoff:.1f}s")
                await asyncio.sleep(backoff)

        # 全リトライ失敗
        error_msg = f"Failed to send token_transfer to {recipient_id} after {max_retries} attempts"
        logger.error(error_msg)
        return False, error_msg

    async def handle_wake_up_ack(self, message: dict) -> None:
        """wake_up_ackを受信

        wake_upに対する確認応答を処理し、内部状態を更新する。

        Args:
            message: 受信したメッセージ辞書
        """
        sender = message.get("sender_id", message.get("from", "unknown"))
        payload = message.get("payload", {})
        acknowledged = payload.get("acknowledged", False)
        ack_reason = payload.get("reason", "unspecified")

        logger.info(f"Received wake_up_ack from {sender}, acknowledged={acknowledged}, reason={ack_reason}")

        # 内部状態を更新
        if hasattr(self, '_wake_up_states') and sender in self._wake_up_states:
            self._wake_up_states[sender]["ack_received"] = True
            self._wake_up_states[sender]["ack_at"] = datetime.now(timezone.utc)
            logger.info(f"Wake up acknowledged by {sender}")
        else:
            logger.debug(f"Received wake_up_ack from {sender} but no pending wake_up state found")

        # 統計を更新
        if sender in self.peer_stats:
            self.peer_stats[sender].total_messages_received += 1
            self.peer_stats[sender].last_seen = datetime.now(timezone.utc)

    # ============ v1.0 Handshake Protocol Methods ============

    async def initiate_handshake(
        self,
        target_id: str,
        timeout: float = 30.0,
        enable_e2e: bool = True
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """v1.0 プロトコル: ハンドシェイクを開始
        
        3-way handshakeを開始し、新しいセッションを確立する。
        E2E暗号化が有効な場合、E2ECryptoManager経由でセッションを作成する。
        Flow:
        1. A sends handshake with pubkey + challenge (+ E2E capability if enabled)
        2. B responds with handshake_ack + pubkey + challenge_response
        3. A confirms with handshake_confirm
        4. Session established (with E2E encryption if negotiated)
        
        Args:
            target_id: 対象ピアのエンティティID
            timeout: タイムアウト秒数
            enable_e2e: E2E暗号化を有効にする（デフォルト: True）
            
        Returns:
            (成功ならTrue, セッションID, エラーメッセージ)
        """
        if not CRYPTO_AVAILABLE or not self.key_pair or not self.signer:
            return False, None, "Crypto not available"
        
        if target_id not in self.peers:
            return False, None, f"Unknown peer: {target_id}"
        
        # E2Eセッションを作成（E2E暗号化が有効な場合）
        e2e_session = None
        if enable_e2e and self.e2e_manager and E2E_CRYPTO_AVAILABLE:
            try:
                e2e_session = self.e2e_manager.create_session(target_id)
                logger.debug(f"Created E2E session for handshake: {e2e_session.session_id}")
            except Exception as e:
                logger.warning(f"Failed to create E2E session: {e}")
        
        # セッションIDを生成
        session_id = str(uuid.uuid4())
        
        # チャレンジを生成（32バイトのランダム値）
        challenge = secrets.token_hex(32)
        
        # セッションを作成
        session = Session(
            session_id=session_id,
            peer_id=target_id,
            state=SessionState.HANDSHAKE_SENT,
            challenge=challenge
        )
        self._handshake_sessions[session_id] = session
        self._handshake_pending[target_id] = {
            "session_id": session_id,
            "challenge": challenge,
            "started_at": datetime.now(timezone.utc)
        }
        
        address = self.peers[target_id]
        
        try:
            async with aiohttp.ClientSession() as http_session:
                # Step 1: handshake メッセージを送信
                handshake_payload = {
                    "version": "1.0",
                    "session_id": session_id,
                    "challenge": challenge,
                    "public_key": self.key_pair.get_public_key_hex(),
                    "supported_versions": ["1.0", "0.3"],
                    "capabilities": ["e2e_encryption", "aes_256_gcm", "x25519"] if self.enable_e2e_encryption else [],
                    "e2e_enabled": self.enable_e2e_encryption and e2e_session is not None,
                    "e2e_session_id": e2e_session.session_id if e2e_session else None,
                    "e2e_ephemeral_key": base64.b64encode(e2e_session.ephemeral_public_key).decode() if e2e_session else None
                }
                
                handshake_msg = {
                    "version": "1.0",
                    "msg_type": "handshake",
                    "sender_id": self.entity_id,
                    "recipient_id": target_id,
                    "session_id": session_id,
                    "sequence_num": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "nonce": secrets.token_hex(16),
                    "payload": handshake_payload
                }
                
                # 署名を追加
                if self.signer:
                    signable_data = {
                        "version": handshake_msg["version"],
                        "msg_type": handshake_msg["msg_type"],
                        "sender_id": handshake_msg["sender_id"],
                        "payload": handshake_payload,
                        "timestamp": handshake_msg["timestamp"],
                        "nonce": handshake_msg["nonce"]
                    }
                    signature = self.signer.sign(signable_data)
                    handshake_msg["signature"] = signature
                
                logger.info(f"Sending handshake to {target_id}: session_id={session_id}")
                
                async with http_session.post(
                    f"{address}/message",
                    json=handshake_msg,
                    timeout=ClientTimeout(total=timeout)
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        logger.error(f"Handshake rejected by {target_id}: {error}")
                        self._cleanup_handshake(session_id, target_id)
                        return False, None, f"Handshake rejected: {error}"
                    
                    result = await response.json()
                    logger.info(f"Handshake initiated with {target_id}: {result.get('status')}")
                    
                    # セッションを更新
                    session.state = SessionState.HANDSHAKE_SENT
                    session.update_activity()
                    
                    return True, session_id, None
                    
        except asyncio.TimeoutError:
            self._cleanup_handshake(session_id, target_id)
            return False, None, "Handshake timeout"
        except Exception as e:
            self._cleanup_handshake(session_id, target_id)
            return False, None, f"Handshake error: {e}"
    
    def _cleanup_handshake(self, session_id: str, target_id: str) -> None:
        """ハンドシェイク関連のデータをクリーンアップ"""
        self._handshake_sessions.pop(session_id, None)
        self._handshake_pending.pop(target_id, None)
    
    def _cleanup_expired_handshake_sessions(self, max_age_seconds: int = 300) -> int:
        """期限切れのハンドシェイクセッションをクリーンアップ
        
        Args:
            max_age_seconds: 最大ハンドシェイク時間（デフォルト: 300s = 5min）
            
        Returns:
            クリーンアップされたセッション数
        """
        now = datetime.now(timezone.utc)
        expired_sessions = []
        
        for session_id, session in self._handshake_sessions.items():
            if session.state != SessionState.ESTABLISHED:
                # 確立されていないセッションは5分でタイムアウト
                age = (now - session.created_at).total_seconds()
                if age > max_age_seconds:
                    expired_sessions.append(session_id)
                    logger.debug(f"Handshake session expired: {session_id} (age={age:.1f}s)")
        
        # 期限切れセッションを削除
        for session_id in expired_sessions:
            session = self._handshake_sessions.pop(session_id, None)
            if session:
                # 対応するpendingエントリも削除
                for target_id, pending in list(self._handshake_pending.items()):
                    if pending.get("session_id") == session_id:
                        self._handshake_pending.pop(target_id, None)
                        break
                logger.info(f"Cleaned up expired handshake session: {session_id}")
        
        # E2Eセッションのクリーンアップ
        if self.e2e_manager and E2E_CRYPTO_AVAILABLE:
            try:
                cleaned_e2e = self.e2e_manager.cleanup_expired_sessions()
                if cleaned_e2e > 0:
                    logger.debug(f"Cleaned up {cleaned_e2e} expired E2E sessions")
            except Exception as e:
                logger.warning(f"Failed to cleanup E2E sessions: {e}")
        
        return len(expired_sessions)
    
    async def handle_handshake(self, message: dict) -> dict:
        """v1.0 プロトコル: handshake メッセージハンドラ
        
        ピアからのハンドシェイク要求を処理し、handshake_ackを返す。
        
        Args:
            message: handshake メッセージ
            
        Returns:
            処理結果の辞書 {"status": "success"|"error", "reason": str, ...}
            
        Expected payload:
            - version: プロトコルバージョン
            - session_id: UUID v4
            - challenge: 32-byte hex challenge
            - public_key: 送信者の公開鍵（hex）
            - supported_versions: サポートするバージョンのリスト
        """
        try:
            sender_id = message.get("sender_id", "unknown")
            recipient_id = message.get("recipient_id", "")
            session_id = message.get("session_id", "")
            version = message.get("version", "")
            
            logger.info(f"Received handshake from {sender_id}: session_id={session_id}")
            
            # バージョンチェック
            if version != "1.0":
                logger.error(f"Invalid version from {sender_id}: {version}")
                return {
                    "status": "error",
                    "error_code": INVALID_VERSION,
                    "reason": f"Invalid version: {version}. Expected 1.0"
                }
            
            # 署名検証
            signature = message.get("signature")
            if self.enable_verification and self.verifier and signature:
                try:
                    payload = message.get("payload", {})
                    signable_data = {
                        "version": message["version"],
                        "msg_type": message["msg_type"],
                        "sender_id": message["sender_id"],
                        "payload": payload,
                        "timestamp": message["timestamp"],
                        "nonce": message["nonce"]
                    }
                    
                    # 一時的に公開鍵を登録して検証
                    public_key_hex = payload.get("public_key")
                    if public_key_hex and sender_id not in self.verifier.public_keys:
                        self.verifier.add_public_key_hex(sender_id, public_key_hex)
                    
                    is_valid = self.verifier.verify_message(signable_data, signature, sender_id)
                    if not is_valid:
                        logger.error(f"Invalid signature from {sender_id}")
                        return {
                            "status": "error",
                            "error_code": INVALID_SIGNATURE,
                            "reason": "Invalid signature"
                        }
                    
                    logger.debug(f"Signature verified for handshake from {sender_id}")
                    
                except ValueError as e:
                    logger.error(f"Signature verification error: {e}")
                    return {
                        "status": "error",
                        "error_code": INVALID_SIGNATURE,
                        "reason": f"Signature verification failed: {e}"
                    }
            elif self.enable_verification and not signature:
                logger.error(f"Missing signature in handshake from {sender_id}")
                return {
                    "status": "error",
                    "error_code": INVALID_SIGNATURE,
                    "reason": "Missing signature"
                }
            
            payload = message.get("payload", {})
            
            # 必須フィールドの検証
            required_fields = ["session_id", "challenge", "public_key"]
            for field in required_fields:
                if field not in payload:
                    logger.error(f"Missing required field in handshake: {field}")
                    return {
                        "status": "error",
                        "reason": f"Missing required field: {field}"
                    }
            
            received_session_id = payload["session_id"]
            challenge = payload["challenge"]
            public_key_hex = payload["public_key"]
            
            # セッションIDの形式検証（UUID v4）
            try:
                parsed_uuid = uuid.UUID(received_session_id)
                if parsed_uuid.version != 4:
                    logger.error(f"Invalid session_id version: {parsed_uuid.version}")
                    return {
                        "status": "error",
                        "reason": f"Invalid session_id version: {parsed_uuid.version}"
                    }
            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid session_id format: {e}")
                return {
                    "status": "error",
                    "reason": f"Invalid session_id format: {e}"
                }
            
            # チャレンジレスポンスを作成
            if not CRYPTO_AVAILABLE or not self.key_pair:
                return {
                    "status": "error",
                    "reason": "Crypto not available"
                }
            
            # チャレンジに署名（レスポンス）
            challenge_bytes = bytes.fromhex(challenge)
            challenge_response = self.signer.sign(challenge.hex()) if self.signer else ""
            
            # セッションを作成
            session = Session(
                session_id=received_session_id,
                peer_id=sender_id,
                state=SessionState.HANDSHAKE_ACKED,
                peer_public_key=public_key_hex
            )
            self._handshake_sessions[received_session_id] = session
            
            # ピアの公開鍵を登録
            self.add_peer_public_key(sender_id, public_key_hex)
            
            # E2E暗号化ネゴシエーション
            e2e_session = None
            e2e_accepted = False
            if self.enable_e2e_encryption and self.e2e_manager and E2E_CRYPTO_AVAILABLE:
                e2e_enabled = payload.get("e2e_enabled", False)
                e2e_session_id = payload.get("e2e_session_id")
                e2e_ephemeral_key_b64 = payload.get("e2e_ephemeral_key")
                
                if e2e_enabled and e2e_session_id and e2e_ephemeral_key_b64:
                    try:
                        # E2Eセッションを作成（レスポンダー側）
                        e2e_session = self.e2e_manager.create_session(sender_id)
                        
                        # リモートのエフェメラルキーをデコード
                        remote_ephemeral_key = base64.b64decode(e2e_ephemeral_key_b64)
                        remote_pubkey = bytes.fromhex(public_key_hex)
                        
                        # ハンドシェイクを完了してセッションキーを導出
                        e2e_session.complete_handshake(remote_pubkey, remote_ephemeral_key)
                        e2e_accepted = True
                        
                        logger.info(f"E2E encryption negotiated with {sender_id}: session={e2e_session.session_id}")
                    except Exception as e:
                        logger.warning(f"Failed to establish E2E session with {sender_id}: {e}")
            
            # 統計を更新
            if sender_id in self.peer_stats:
                self.peer_stats[sender_id].total_messages_received += 1
                self.peer_stats[sender_id].last_seen = datetime.now(timezone.utc)
            
            # handshake_ack を送信
            ack_payload = {
                "session_id": received_session_id,
                "public_key": self.key_pair.get_public_key_hex(),
                "challenge_response": challenge_response,
                "selected_version": "1.0",
                "confirm": True,
                "e2e_accepted": e2e_accepted,
                "e2e_session_id": e2e_session.session_id if e2e_session else None,
                "e2e_ephemeral_key": base64.b64encode(e2e_session.ephemeral_public_key).decode() if e2e_session else None
            }
            
            ack_msg = {
                "version": "1.0",
                "msg_type": "handshake_ack",
                "sender_id": self.entity_id,
                "recipient_id": sender_id,
                "session_id": received_session_id,
                "sequence_num": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "nonce": secrets.token_hex(16),
                "payload": ack_payload
            }
            
            # 署名を追加
            if self.signer:
                signable_data = {
                    "version": ack_msg["version"],
                    "msg_type": ack_msg["msg_type"],
                    "sender_id": ack_msg["sender_id"],
                    "payload": ack_payload,
                    "timestamp": ack_msg["timestamp"],
                    "nonce": ack_msg["nonce"]
                }
                ack_msg["signature"] = self.signer.sign(signable_data)
            
            # メッセージを送信（キューを使わず直接送信）
            success = await self.send_message(sender_id, "handshake_ack", ack_payload)
            
            if success:
                logger.info(f"Sent handshake_ack to {sender_id}: session_id={received_session_id}")
                return {
                    "status": "success",
                    "session_id": received_session_id,
                    "message": "Handshake acknowledged"
                }
            else:
                logger.error(f"Failed to send handshake_ack to {sender_id}")
                self._handshake_sessions.pop(received_session_id, None)
                return {
                    "status": "error",
                    "reason": "Failed to send handshake_ack"
                }
                
        except Exception as e:
            logger.error(f"Error handling handshake: {e}")
            return {
                "status": "error",
                "reason": f"Internal error: {e}"
            }

    async def handle_handshake_ack(self, message: dict) -> dict:
        """v1.0 プロトコル: handshake_ack メッセージハンドラ
        
        ピアからのhandshake_ackを処理し、handshake_confirmを送信する。
        
        Args:
            message: handshake_ack メッセージ
            
        Returns:
            処理結果の辞書
        """
        try:
            sender_id = message.get("sender_id", "unknown")
            session_id = message.get("session_id", "")
            payload = message.get("payload", {})
            
            logger.info(f"Received handshake_ack from {sender_id}: session_id={session_id}")
            
            # セッションの存在確認
            if session_id not in self._handshake_sessions:
                logger.error(f"Unknown session_id in handshake_ack: {session_id}")
                return {
                    "status": "error",
                    "error_code": SESSION_EXPIRED,
                    "reason": f"Unknown or expired session: {session_id}"
                }
            
            session = self._handshake_sessions[session_id]
            
            # 送信者とセッションのピアIDが一致するか確認
            if session.peer_id != sender_id:
                logger.error(f"Peer ID mismatch in handshake_ack")
                return {
                    "status": "error",
                    "reason": "Peer ID mismatch"
                }
            
            # チャレンジレスポンスの検証
            challenge_response = payload.get("challenge_response")
            if session.challenge and challenge_response and self.verifier:
                try:
                    # ピアの公開鍵を一時的に登録して検証
                    public_key_hex = payload.get("public_key")
                    if public_key_hex and sender_id not in self.verifier.public_keys:
                        self.verifier.add_public_key_hex(sender_id, public_key_hex)
                    
                    # レスポンスを検証
                    is_valid = self.verifier.verify_message(
                        session.challenge, challenge_response, sender_id
                    )
                    if not is_valid:
                        logger.error(f"Invalid challenge response from {sender_id}")
                        return {
                            "status": "error",
                            "error_code": INVALID_SIGNATURE,
                            "reason": "Invalid challenge response"
                        }
                    
                    logger.debug(f"Challenge response verified for {sender_id}")
                    
                except Exception as e:
                    logger.error(f"Challenge verification error: {e}")
                    return {
                        "status": "error",
                        "error_code": INVALID_SIGNATURE,
                        "reason": f"Challenge verification failed: {e}"
                    }
            
            # ピアの公開鍵を登録
            public_key_hex = payload.get("public_key")
            if public_key_hex:
                self.add_peer_public_key(sender_id, public_key_hex)
                session.peer_public_key = public_key_hex
            
            # E2Eセッションを確立（E2E暗号化がネゴシエートされた場合）
            if self.e2e_manager and E2E_CRYPTO_AVAILABLE:
                e2e_accepted = payload.get("e2e_accepted", False)
                e2e_session_id = payload.get("e2e_session_id")
                e2e_ephemeral_key_b64 = payload.get("e2e_ephemeral_key")
                
                if e2e_accepted and e2e_session_id and e2e_ephemeral_key_b64:
                    try:
                        # 既存のE2Eセッションを探すか新規作成
                        e2e_session = self.e2e_manager.get_session(e2e_session_id)
                        if not e2e_session:
                            e2e_session = self.e2e_manager.create_session(sender_id)
                            e2e_session.session_id = e2e_session_id
                        
                        # リモートのエフェメラルキーをデコード
                        remote_ephemeral_key = base64.b64decode(e2e_ephemeral_key_b64)
                        remote_pubkey = bytes.fromhex(public_key_hex) if public_key_hex else None
                        
                        # ハンドシェイクを完了
                        e2e_session.complete_handshake(remote_pubkey, remote_ephemeral_key)
                        
                        logger.info(f"E2E session established with {sender_id}: session={e2e_session_id}")
                    except Exception as e:
                        logger.warning(f"Failed to complete E2E handshake with {sender_id}: {e}")
            
            # セッションを更新
            session.state = SessionState.HANDSHAKE_ACKED
            session.update_activity()
            
            # 統計を更新
            if sender_id in self.peer_stats:
                self.peer_stats[sender_id].total_messages_received += 1
                self.peer_stats[sender_id].last_seen = datetime.now(timezone.utc)
            
            # handshake_confirm を送信
            confirm_payload = {
                "session_id": session_id,
                "confirm": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            success = await self.send_message(sender_id, "handshake_confirm", confirm_payload)
            
            if success:
                # セッションを確立済みとしてマーク
                session.state = SessionState.ESTABLISHED
                session.increment_sequence()
                
                logger.info(f"Session established with {sender_id}: session_id={session_id}")
                
                # クリーンアップ
                self._handshake_pending.pop(sender_id, None)
                
                return {
                    "status": "success",
                    "session_id": session_id,
                    "message": "Handshake completed, session established"
                }
            else:
                logger.error(f"Failed to send handshake_confirm to {sender_id}")
                return {
                    "status": "error",
                    "reason": "Failed to send handshake_confirm"
                }
                
        except Exception as e:
            logger.error(f"Error handling handshake_ack: {e}")
            return {
                "status": "error",
                "reason": f"Internal error: {e}"
            }

    async def handle_handshake_confirm(self, message: dict) -> dict:
        """v1.0 プロトコル: handshake_confirm メッセージハンドラ
        
        ピアからのhandshake_confirmを処理し、セッションを確立する。
        
        Args:
            message: handshake_confirm メッセージ
            
        Returns:
            処理結果の辞書
        """
        try:
            sender_id = message.get("sender_id", "unknown")
            session_id = message.get("session_id", "")
            payload = message.get("payload", {})
            
            logger.info(f"Received handshake_confirm from {sender_id}: session_id={session_id}")
            
            # 必須フィールドの検証
            if not session_id:
                logger.error(f"Missing session_id in handshake_confirm from {sender_id}")
                return {
                    "status": "error",
                    "reason": "Missing session_id"
                }
            
            # セッションの存在確認
            if session_id not in self._handshake_sessions:
                logger.error(f"Unknown session_id: {session_id}")
                return {
                    "status": "error",
                    "error_code": SESSION_EXPIRED,
                    "reason": f"Unknown or expired session: {session_id}"
                }
            
            session = self._handshake_sessions[session_id]
            
            # 送信者とセッションのピアIDが一致するか確認
            if session.peer_id != sender_id:
                logger.error(
                    f"Peer ID mismatch: session expects {session.peer_id}, "
                    f"but received from {sender_id}"
                )
                return {
                    "status": "error",
                    "reason": "Peer ID mismatch"
                }
            
            # 確認フラグの検証
            if not payload.get("confirm", False):
                logger.warning(f"Handshake not confirmed by {sender_id}")
                self._cleanup_handshake(session_id, sender_id)
                return {
                    "status": "error",
                    "reason": "Handshake not confirmed"
                }
            
            # タイムスタンプの検証
            timestamp_str = payload.get("timestamp")
            if timestamp_str:
                try:
                    confirm_time = datetime.fromisoformat(timestamp_str)
                    age = (datetime.now(timezone.utc) - confirm_time).total_seconds()
                    if abs(age) > 60:  # 60秒以上の差は拒否
                        logger.warning(f"Stale handshake_confirm from {sender_id}: age={age}s")
                        return {
                            "status": "error",
                            "error_code": SESSION_EXPIRED,
                            "reason": f"Stale handshake confirm: age={age}s"
                        }
                except ValueError:
                    logger.warning(f"Invalid timestamp in handshake_confirm from {sender_id}")
            
            # セッションを確立済みとしてマーク
            session.state = SessionState.ESTABLISHED
            session.increment_sequence()
            
            # 統計を更新
            if sender_id in self.peer_stats:
                self.peer_stats[sender_id].total_messages_received += 1
                self.peer_stats[sender_id].last_seen = datetime.now(timezone.utc)
                self.peer_stats[sender_id].is_healthy = True
            
            logger.info(
                f"Session established with {sender_id}: "
                f"session_id={session_id}, sequence_num={session.sequence_num}"
            )
            
            return {
                "status": "success",
                "session_id": session_id,
                "message": "Session established"
            }
            
        except Exception as e:
            logger.error(f"Error handling handshake_confirm: {e}")
            return {
                "status": "error",
                "reason": f"Internal error: {e}"
            }
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """セッションを取得
        
        Args:
            session_id: セッションID
            
        Returns:
            Sessionオブジェクト（存在しない場合はNone）
        """
        return self._handshake_sessions.get(session_id)
    
    def get_peer_session(self, peer_id: str) -> Optional[Session]:
        """ピアIDに紐づく確立済みセッションを取得
        
        Args:
            peer_id: ピアID
            
        Returns:
            Sessionオブジェクト（存在しない場合はNone）
        """
        for session in self._handshake_sessions.values():
            if session.peer_id == peer_id and session.state == SessionState.ESTABLISHED:
                return session
        return None
    
    def list_sessions(self) -> List[dict]:
        """全セッションのリストを取得
        
        Returns:
            セッション情報の辞書リスト
        """
        return [session.to_dict() for session in self._handshake_sessions.values()]

    async def health_check(self) -> dict:
        """サービスのヘルスチェック
        
        Returns:
            ヘルスチェック結果の辞書
        """
        healthy_peers = sum(
            1 for stats in self.peer_stats.values() if stats.is_healthy
        )
        
        result = {
            "entity_id": self.entity_id,
            "port": self.port,
            "peers": len(self.peers),
            "healthy_peers": healthy_peers,
            "total_stats_entries": len(self.peer_stats),
            "crypto_available": CRYPTO_AVAILABLE,
            "signing_enabled": self.enable_signing,
            "verification_enabled": self.enable_verification,
            "public_key": self.get_public_key_hex(),
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # キュー統計を追加
        if self._queue:
            result["queue"] = {
                "size": self._queue.get_queue_size(),
                "stats": self._queue.get_stats()
            }
        
        # ハートビート統計を追加
        if self._heartbeat:
            result["heartbeat"] = {
                "peer_status": self._heartbeat.get_all_status(),
                "healthy_count": len(self._heartbeat.get_healthy_peers())
            }
        
        return result
    
    def list_peers(self) -> List[str]:
        """登録されているピアIDのリストを取得
        
        Returns:
            ピアIDのリスト
        """
        return list(self.peers.keys())
    
    def get_peer_address(self, peer_id: str) -> Optional[str]:
        """ピアのアドレスを取得
        
        Args:
            peer_id: ピアID
            
        Returns:
            アドレス（存在しない場合はNone）
        """
        return self.peers.get(peer_id)
    
    def get_peer_info(self, peer_id: str) -> Optional[PeerInfo]:
        """ピアの詳細情報を取得
        
        Args:
            peer_id: ピアID
            
        Returns:
            PeerInfo（存在しない場合はNone）
        """
        return self.peer_infos.get(peer_id)


# グローバルインスタンス
_service: Optional[PeerService] = None


def init_service(
    entity_id: str,
    port: int,
    enable_signing: bool = True,
    enable_verification: bool = True,
    enable_queue: bool = True,
    enable_heartbeat: bool = True,
    registry=None,
    private_key_hex: Optional[str] = None,
    enable_encryption: bool = True,
    require_signatures: bool = True,
    dht_registry=None,
    use_dht_discovery: bool = False
) -> PeerService:
    """サービスを初期化

    Args:
        entity_id: エンティティID
        port: 通信ポート
        enable_signing: メッセージ署名を有効にする
        enable_verification: 署名検証を有効にする
        enable_queue: メッセージキューを有効にする
        enable_heartbeat: ハートビートを有効にする
        registry: サービスレジストリ（オプション）
        private_key_hex: エンティティの秘密鍵（16進文字列、オプション）
        enable_encryption: ペイロード暗号化を有効にする（互換性用）
        require_signatures: 署名を必須とする（enable_verificationと同義）
        dht_registry: DHTレジストリインスタンス（オプション）
        use_dht_discovery: DHTを使用したピア発見を有効にする

    Returns:
        初期化されたPeerServiceインスタンス
    """
    global _service

    # 注意: 環境変数への秘密鍵設定はセキュリティリスクのため削除
    # private_key_hexは直接PeerServiceに渡される

    _service = PeerService(
        entity_id, port, enable_signing, enable_verification,
        enable_queue=enable_queue, enable_heartbeat=enable_heartbeat,
        registry=registry, private_key_hex=private_key_hex,
        enable_encryption=enable_encryption, require_signatures=require_signatures,
        dht_registry=dht_registry, use_dht_discovery=use_dht_discovery
    )
    return _service


    async def discover_from_bootstrap(
        self,
        bootstrap_url: Optional[str] = None,
        max_peers: int = 10
    ) -> List[Dict[str, Any]]:
        """ブートストラップサーバーからピアを発見する
        
        Args:
            bootstrap_url: ブートストラップサーバーURL (Noneの場合は環境変数から取得)
            max_peers: 取得する最大ピア数
            
        Returns:
            発見されたピアのリスト
        """
        import aiohttp
        
        # ブートストラップURLを決定
        if not bootstrap_url:
            bootstrap_url = os.environ.get("BOOTSTRAP_URL", "http://localhost:9000")
        
        discovered = []
        
        try:
            async with aiohttp.ClientSession() as session:
                # 自分の情報を含めてディスカバリー要求
                request_data = {
                    "node_id": self.entity_id,
                    "max_results": max_peers
                }
                
                headers = {"Content-Type": "application/json"}
                if self.jwt_token:
                    headers["Authorization"] = f"Bearer {self.jwt_token}"
                
                async with session.post(
                    f"{bootstrap_url}/discover",
                    json=request_data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        peers = data.get("peers", [])
                        
                        for peer_data in peers:
                            peer_info = {
                                "entity_id": peer_data.get("node_id"),
                                "endpoint": peer_data.get("endpoint"),
                                "public_key": peer_data.get("public_key"),
                                "region": peer_data.get("region", "unknown"),
                                "capabilities": peer_data.get("capabilities", [])
                            }
                            discovered.append(peer_info)
                            
                            # ピアを自動追加（設定が有効な場合）
                            if self._auto_discover and peer_info["entity_id"]:
                                if peer_info["entity_id"] != self.entity_id:
                                    self.add_peer(
                                        peer_info["entity_id"],
                                        peer_info["endpoint"],
                                        is_manual=False,
                                        public_key_hex=peer_info.get("public_key")
                                    )
                        
                        logger.info(f"Discovered {len(discovered)} peers from bootstrap server")
                    else:
                        logger.warning(f"Bootstrap discovery failed: HTTP {response.status}")
                        
        except Exception as e:
            logger.error(f"Error discovering from bootstrap: {e}")
        
        return discovered
    
    async def discover_peers_dht(
        self,
        count: int = 10,
        capability: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """DHTを使用してピアを発見する
        
        Args:
            count: 発見する最大ピア数
            capability: 特定の機能を持つピアのみを発見（オプション）
            
        Returns:
            発見されたピアのリスト
        """
        if not self._dht_registry:
            logger.warning("DHT registry not available, cannot discover peers via DHT")
            return []
        
        discovered = []
        
        try:
            # DHTからピアを発見
            if capability:
                peer_infos = await self._dht_registry.find_by_capability(capability)
                logger.info(f"Discovered {len(peer_infos)} peers with capability '{capability}' via DHT")
            else:
                peer_infos = await self._dht_registry.discover_peers(count=count)
                logger.info(f"Discovered {len(peer_infos)} peers via DHT")
            
            # PeerInfoを辞書形式に変換し、ローカルのピアリストに追加
            for peer_info in peer_infos:
                peer_data = {
                    "entity_id": peer_info.entity_id,
                    "entity_name": peer_info.entity_name,
                    "endpoint": peer_info.endpoint,
                    "public_key": peer_info.public_key,
                    "capabilities": peer_info.capabilities,
                    "peer_id": peer_info.peer_id
                }
                discovered.append(peer_data)
                
                # ローカルのピアリストに追加（まだ存在しない場合）
                if peer_info.entity_id not in self.peers:
                    await self.add_peer(
                        peer_info.entity_id,
                        peer_info.endpoint,
                        is_manual=False,
                        public_key_hex=peer_info.public_key
                    )
            
            return discovered
            
        except Exception as e:
            logger.error(f"Error discovering peers via DHT: {e}")
            return []
    
    async def lookup_peer_dht(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """DHTを使用して特定のピアを検索する
        
        Args:
            peer_id: 検索するピアのID
            
        Returns:
            ピア情報（見つからない場合はNone）
        """
        if not self._dht_registry:
            logger.warning("DHT registry not available, cannot lookup peer via DHT")
            return None
        
        try:
            peer_info = await self._dht_registry.lookup_peer(peer_id)
            if peer_info:
                return {
                    "entity_id": peer_info.entity_id,
                    "entity_name": peer_info.entity_name,
                    "endpoint": peer_info.endpoint,
                    "public_key": peer_info.public_key,
                    "capabilities": peer_info.capabilities,
                    "peer_id": peer_info.peer_id
                }
            return None
            
        except Exception as e:
            logger.error(f"Error looking up peer via DHT: {e}")
            return None
    
    async def register_with_bootstrap(
        self,
        bootstrap_url: Optional[str] = None
    ) -> bool:
        """ブートストラップサーバーに自分を登録する
        
        Args:
            bootstrap_url: ブートストラップサーバーURL
            
        Returns:
            登録成功したかどうか
        """
        import aiohttp
        
        if not bootstrap_url:
            bootstrap_url = os.environ.get("BOOTSTRAP_URL", "http://localhost:9000")
        
        try:
            # 自分の情報を構築
            registration = {
                "node_id": self.entity_id,
                "endpoint": f"http://localhost:{self.port}",
                "public_key": self.get_public_key_b64() if self.keypair else None,
                "region": os.environ.get("REGION", "unknown"),
                "capabilities": ["discovery", "relay"],
                "version": "1.0"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{bootstrap_url}/register",
                    json=registration,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Successfully registered with bootstrap server: {bootstrap_url}")
                        return True
                    else:
                        logger.warning(f"Bootstrap registration failed: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error registering with bootstrap: {e}")
            return False
    
    def load_bootstrap_nodes(self, filepath: str = "config/bootstrap_nodes.json") -> List[str]:
        """ブートストラップノード設定を読み込む
        
        Args:
            filepath: 設定ファイルのパス
            
        Returns:
            ブートストラップサーバーURLのリスト
        """
        bootstrap_urls = []
        
        try:
            # 複数のパスを試行
            possible_paths = [
                filepath,
                os.path.join(os.path.dirname(__file__), "..", filepath),
                os.path.join(os.path.dirname(__file__), filepath),
            ]
            
            config_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
                    break
            
            if not config_path:
                logger.warning(f"Bootstrap nodes config not found: {filepath}")
                return bootstrap_urls
            
            with open(config_path, 'r') as f:
                data = json.load(f)
            
            # ブートストラップサーバーURLを収集
            for server in data.get("bootstrap_servers", []):
                url = server.get("endpoint")
                if url:
                    bootstrap_urls.append(url)
            
            for server in data.get("local_bootstrap", []):
                url = server.get("endpoint")
                if url:
                    bootstrap_urls.append(url)
            
            logger.info(f"Loaded {len(bootstrap_urls)} bootstrap server URLs from {config_path}")
            
        except Exception as e:
            logger.error(f"Error loading bootstrap nodes: {e}")
        
        return bootstrap_urls
    
    async def auto_discover_with_bootstrap(self) -> int:
        """ブートストラップサーバーを使用して自動ピア発見
        
        Returns:
            発見・追加されたピアの数
        """
        if not self._auto_discover:
            return 0
        
        # ブートストラップURLを取得
        bootstrap_urls = self.load_bootstrap_nodes()
        if not bootstrap_urls:
            # 環境変数から取得を試行
            env_url = os.environ.get("BOOTSTRAP_URL")
            if env_url:
                bootstrap_urls = [env_url]
        
        added_count = 0
        
        for url in bootstrap_urls:
            try:
                # 自分を登録
                await self.register_with_bootstrap(url)
                
                # ピアを発見
                peers = await self.discover_from_bootstrap(url)
                
                for peer in peers:
                    entity_id = peer.get("entity_id")
                    endpoint = peer.get("endpoint")
                    
                    if entity_id and endpoint and entity_id != self.entity_id:
                        if entity_id not in self.peers:
                            self.add_peer(
                                entity_id,
                                endpoint,
                                is_manual=False,
                                public_key_hex=peer.get("public_key")
                            )
                            added_count += 1
                
            except Exception as e:
                logger.error(f"Error with bootstrap server {url}: {e}")
        
        if added_count > 0:
            logger.info(f"Auto-discovered and added {added_count} peers via bootstrap")
        
        return added_count
    
    # ============================================================
    # DHT Registry Integration Methods
    # ============================================================
    
    async def discover_peers_via_dht(
        self,
        count: int = 10,
        capability: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """DHTを使用してピアを発見する
        
        DHTレジストリからランダムなピアを発見し、内部ピアリストに追加する。
        capabilityが指定された場合、その機能を持つピアのみを返す。
        
        Args:
            count: 発見する最大ピア数
            capability: フィルタする機能（オプション）
            
        Returns:
            発見されたピア情報のリスト
        """
        if not self._dht_registry:
            logger.warning("DHT registry not available")
            return []
        
        discovered = []
        
        try:
            # DHTからピアを発見
            if capability:
                peer_infos = await self._dht_registry.find_by_capability(capability)
                logger.info(f"Found {len(peer_infos)} peers with capability '{capability}' via DHT")
            else:
                peer_infos = await self._dht_registry.discover_peers(count=count)
                logger.info(f"Discovered {len(peer_infos)} peers via DHT")
            
            # PeerInfoを辞書形式に変換してピアリストに追加
            for peer_info in peer_infos:
                if peer_info.entity_id == self.entity_id:
                    continue  # 自分自身は除外
                
                peer_data = {
                    "entity_id": peer_info.entity_id,
                    "entity_name": peer_info.entity_name,
                    "endpoint": peer_info.endpoint,
                    "public_key": peer_info.public_key,
                    "capabilities": peer_info.capabilities,
                    "peer_id": peer_info.peer_id,
                    "timestamp": peer_info.timestamp
                }
                discovered.append(peer_data)
                
                # ピアを自動追加（設定が有効な場合）
                if self._auto_discover:
                    if peer_info.entity_id not in self.peers:
                        self.add_peer(
                            peer_info.entity_id,
                            peer_info.endpoint,
                            is_manual=False,
                            public_key_hex=peer_info.public_key
                        )
            
            logger.info(f"Added {len(discovered)} peers from DHT discovery")
            
        except Exception as e:
            logger.error(f"Error discovering peers via DHT: {e}")
        
        return discovered
    
    async def register_to_dht(self) -> bool:
        """DHTに自身のピア情報を登録する
        
        Returns:
            登録成功したかどうか
        """
        if not self._dht_registry:
            logger.warning("DHT registry not available")
            return False
        
        try:
            # DHTRegistryの内部メソッドを使用して自身を登録
            result = await self._dht_registry._register_self()
            if result:
                logger.info(f"Successfully registered to DHT: {self.entity_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error registering to DHT: {e}")
            return False
    
    async def get_peer_from_dht(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """DHTから特定のピア情報を取得する
        
        Args:
            peer_id: 検索するピアID（公開鍵のSHA256ハッシュ）
            
        Returns:
            ピア情報（見つからない場合はNone）
        """
        if not self._dht_registry:
            logger.warning("DHT registry not available")
            return None
        
        try:
            peer_info = await self._dht_registry.lookup_peer(peer_id)
            
            if peer_info:
                return {
                    "entity_id": peer_info.entity_id,
                    "entity_name": peer_info.entity_name,
                    "endpoint": peer_info.endpoint,
                    "public_key": peer_info.public_key,
                    "capabilities": peer_info.capabilities,
                    "peer_id": peer_info.peer_id,
                    "timestamp": peer_info.timestamp,
                    "signature": peer_info.signature
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting peer from DHT: {e}")
            return None
    
    async def auto_discover_with_dht(self) -> int:
        """DHTを使用して自動ピア発見
        
        Returns:
            発見・追加されたピアの数
        """
        if not self._auto_discover or not self._dht_registry:
            return 0
        
        try:
            peers = await self.discover_peers_via_dht(count=20)
            
            added_count = 0
            for peer in peers:
                entity_id = peer.get("entity_id")
                endpoint = peer.get("endpoint")
                
                if entity_id and endpoint and entity_id != self.entity_id:
                    if entity_id not in self.peers:
                        self.add_peer(
                            entity_id,
                            endpoint,
                            is_manual=False,
                            public_key_hex=peer.get("public_key")
                        )
                        added_count += 1
            
            if added_count > 0:
                logger.info(f"Auto-discovered and added {added_count} peers via DHT")
            
            return added_count
            
        except Exception as e:
            logger.error(f"Error in DHT auto-discovery: {e}")
            return 0


def get_service() -> Optional[PeerService]:
    """サービスインスタンスを取得
    
    Returns:
        現在のPeerServiceインスタンス（未初期化の場合はNone）
    """
    return _service


# FastAPI サーバー用
class PeerServer:
    """FastAPIベースのピア通信サーバー"""
    
    def __init__(self, service: PeerService):
        """PeerServerを初期化
        
        Args:
            service: PeerServiceインスタンス
        """
        self.service = service
        self.app = None
        self._init_app()
    
    def _init_app(self) -> None:
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
                    
                    # ログ用に送信元を取得
                    sender = message.get("sender_id", message.get("from", "unknown"))
                    msg_type = message.get("msg_type", message.get("type", "unknown"))
                    logger.info(f"Received message: {msg_type} from {sender}")
                    
                    # メッセージ処理（署名検証・リプレイ保護含む）
                    result = await self.service.handle_message(message)
                    
                    if result["status"] == "error":
                        logger.warning(f"Message processing failed: {result.get('reason')}")
                        raise HTTPException(status_code=400, detail=result.get("reason"))
                    
                    return JSONResponse(
                        content={
                            "status": "received", 
                            "entity_id": self.service.entity_id,
                            "verification": "passed" if self.service.enable_verification else "disabled"
                        }
                    )
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    raise HTTPException(status_code=400, detail="Invalid JSON")
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    raise HTTPException(status_code=500, detail=str(e))
            
            @self.app.get("/health")
            async def health_check_endpoint() -> dict:
                """ヘルスチェックエンドポイント"""
                return await self.service.health_check()
            
            @self.app.get("/peers")
            async def list_peers_endpoint() -> dict:
                """ピアリスト取得エンドポイント"""
                peers_with_keys = []
                for peer_id in self.service.list_peers():
                    info = self.service.get_peer_info(peer_id)
                    peers_with_keys.append({
                        "entity_id": peer_id,
                        "address": self.service.get_peer_address(peer_id),
                        "has_public_key": info.public_key is not None if info else False
                    })
                
                return {
                    "entity_id": self.service.entity_id,
                    "peers": peers_with_keys,
                    "count": len(self.service.peers)
                }
            
            @self.app.get("/stats")
            async def get_stats_endpoint() -> dict:
                """統計情報取得エンドポイント"""
                return {
                    "entity_id": self.service.entity_id,
                    "stats": self.service.get_peer_stats()
                }
            
            @self.app.get("/public-key")
            async def get_public_key_endpoint() -> dict:
                """公開鍵取得エンドポイント"""
                return {
                    "entity_id": self.service.entity_id,
                    "public_key": self.service.get_public_key_hex()
                }
            
            @self.app.get("/")
            async def root() -> dict:
                """ルートエンドポイント"""
                return {
                    "entity_id": self.service.entity_id,
                    "service": "peer-communication",
                    "version": "1.0",
        "peers_count": len(self.service.peers),
                    "crypto_available": CRYPTO_AVAILABLE,
                    "signing_enabled": self.service.enable_signing,
                    "verification_enabled": self.service.enable_verification
                }
                
        except ImportError as e:
            logger.error(f"FastAPI/uvicorn not installed: {e}")
            self.app = None
    
    async def start(self, host: str = "0.0.0.0", port: Optional[int] = None) -> None:
        """サーバーを起動
        
        Args:
            host: ホストアドレス
            port: ポート（省略時はservice.portを使用）
            
        Raises:
            RuntimeError: FastAPIアプリが初期化されていない場合
        """
        import uvicorn
        
        if self.app is None:
            raise RuntimeError(
                "FastAPI app not initialized. Install fastapi and uvicorn."
            )
        
        server_port = port or self.service.port
        config = uvicorn.Config(
            self.app, 
            host=host, 
            port=server_port, 
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()


def create_server(service: PeerService) -> PeerServer:
    """PeerServerインスタンスを作成
    
    Args:
        service: PeerServiceインスタンス
        
    Returns:
        PeerServerインスタンス
    """
    return PeerServer(service)


if __name__ == "__main__":
    # テスト実行
    import asyncio
    
    async def run_tests():
        print("=" * 60)
        print("Peer Service - Security Features Test")
        print("=" * 60)
        
        # 1. サービス初期化テスト
        print("\n1. Service Initialization Test")
        service = init_service("test-entity", 8001)
        print(f"   Service initialized: {service.entity_id}")
        print(f"   Public key: {service.get_public_key_hex()}")
        print(f"   Registered handlers: {list(service.message_handlers.keys())}")
        
        # 2. 暗号化メッセージテスト
        if CRYPTO_AVAILABLE:
            print("\n2. Encrypted Message Test")
            
            # 2つのエンティティを作成
            entity_a = PeerService("entity-a", 8001)
            entity_b = PeerService("entity-b", 8002)
            
            # ピアを登録（相互に公開鍵を交換）
            entity_a.add_peer(
                "entity-b",
                "http://localhost:8002",
                entity_b.get_public_key_hex()
            )
            entity_b.add_peer(
                "entity-a",
                "http://localhost:8001",
                entity_a.get_public_key_hex()
            )
            
            print(f"   Entity A public key: {entity_a.get_public_key_hex()[:32]}...")
            print(f"   Entity B public key: {entity_b.get_public_key_hex()[:32]}...")
            
            # 暗号化メッセージの作成と復号テスト
            test_payload = {"message": "Hello, secure world!", "data": [1, 2, 3]}
            
            encrypted = EncryptedMessage.encrypt(
                sender_keypair=entity_a.key_pair,
                recipient_public_key=bytes.fromhex(entity_b.get_public_key_hex()),
                sender_id="entity-a",
                recipient_id="entity-b",
                plaintext=test_payload
            )
            print(f"   Encrypted message created")
            print(f"   Ciphertext length: {len(encrypted.ciphertext)} bytes")
            
            # 復号
            decrypted = encrypted.decrypt(entity_b.key_pair.private_key)
            print(f"   Decrypted message: {decrypted}")
            assert decrypted == test_payload, "Decryption failed!"
            print("   [PASS] Encryption/Decryption successful")
            
            # 3. ハンドシェイクチャレンジテスト
            print("\n3. Handshake Challenge Test")
            
            challenge = HandshakeChallenge.generate("entity-a")
            print(f"   Challenge generated by: {challenge.challenger_id}")
            
            # レスポンス作成
            response = challenge.create_response("entity-b", entity_b.key_pair)
            print(f"   Response created by: entity-b")
            print(f"   Response signature: {response['signature'][:40]}...")
            
            # 検証（Entity Bの公開鍵を verifier に追加）
            verifier = SignatureVerifier()
            verifier.add_public_key_hex("entity-b", entity_b.get_public_key_hex())
            
            is_valid, error = challenge.verify_response(response, verifier)
            print(f"   Verification result: {is_valid}")
            if error:
                print(f"   Error: {error}")
            assert is_valid, "Handshake verification failed!"
            print("   [PASS] Handshake challenge-response successful")
            
            # 4. API Server 統合テスト（モック）
            print("\n4. API Server Integration Test")
            print(f"   API Server URL from env: {service.api_server_url or 'Not set'}")
            print(f"   API Key configured: {'Yes' if service.api_key else 'No'}")
            print(f"   Auth headers (without token): {service.get_auth_headers()}")
            print("   [INFO] To test authentication, set API_SERVER_URL and API_KEY env vars")
            
        else:
            print("\n[SKIP] Crypto tests (PyNaCl not installed)")
        
        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)
        
        return service
    
    # テスト実行
    service = asyncio.run(run_tests())

async def initiate_e2e_handshake(
    self,
    peer_id: str,
    peer_address: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    E2E暗号化ハンドシェイクを開始する
    
    Args:
        peer_id: 相手ピアのエンティティID
        peer_address: 相手ピアのアドレス（オプション）
        
    Returns:
        ハンドシェイク結果、失敗時はNone
    """
    if not E2E_CRYPTO_AVAILABLE or not self.e2e_manager:
        logger.warning("E2E crypto not available for handshake")
        return None
    
    try:
        # ハンドシェイクメッセージを作成
        session, handshake_msg = self.e2e_manager.create_handshake_message(peer_id)
        
        # ペイロードを構築
        payload = {
            "handshake_type": "initiate",
            "session_id": session.session_id,
            "ephemeral_public_key": handshake_msg.payload.get("ephemeral_public_key"),
            "challenge": handshake_msg.payload.get("challenge"),
            "public_key": handshake_msg.payload.get("public_key"),
            "supported_versions": ["1.0", "1.1"],
            "capabilities": ["e2e_encryption", "aes_256_gcm", "x25519"]
        }
        
        # ピアアドレスを取得
        target_address = peer_address or self.peers.get(peer_id)
        if not target_address:
            logger.error(f"No address found for peer {peer_id}")
            return None
        
        # ハンドシェイクメッセージを送信
        result = await self.send_message(
            target_id=peer_id,
            message_type="e2e_handshake",
            payload=payload,
            target_address=target_address
        )
        
        if result.get("status") == "ok":
            logger.info(f"E2E handshake initiated with {peer_id}, session={session.session_id}")
            return {
                "session_id": session.session_id,
                "status": "initiated",
                "peer_id": peer_id
            }
        else:
            logger.error(f"E2E handshake failed: {result.get('error')}")
            return None
            
    except Exception as e:
        logger.error(f"Error initiating E2E handshake: {e}")
        return None


async def handle_e2e_handshake(
    self,
    message: Dict[str, Any]
) -> Dict[str, Any]:
    """
    E2Eハンドシェイクメッセージを処理する
    
    Args:
        message: 受信したハンドシェイクメッセージ
        
    Returns:
        レスポンスメッセージ
    """
    if not E2E_CRYPTO_AVAILABLE or not self.e2e_manager or not self._e2e_handler:
        return {
            "status": "error",
            "error": "E2E crypto not available"
        }
    
    try:
        sender_id = message.get("sender_id", "unknown")
        payload = message.get("payload", {})
        handshake_type = payload.get("handshake_type")
        
        if handshake_type == "initiate":
            # ハンドシェイク開始を処理（Bob側）
            session_id = payload.get("session_id", str(uuid.uuid4()))
            remote_ephemeral_key = payload.get("ephemeral_public_key")
            remote_challenge = payload.get("challenge")
            remote_public_key = payload.get("public_key")
            
            if not all([remote_ephemeral_key, remote_challenge, remote_public_key]):
                return {
                    "status": "error",
                    "error": "Missing required handshake parameters"
                }
            
            # セッションを作成
            session = self.e2e_manager.create_session(sender_id)
            session.session_id = session_id
            
            # ハンドシェイクレスポンスを作成
            import hashlib
            challenge_bytes = base64.b64decode(remote_challenge)
            challenge_response = hashlib.sha256(
                challenge_bytes + self.keypair.private_key
            ).digest()
            
            return {
                "status": "ok",
                "handshake_type": "response",
                "session_id": session_id,
                "ephemeral_public_key": base64.b64encode(
                    session.ephemeral_public_key
                ).decode() if session.ephemeral_public_key else None,
                "challenge_response": base64.b64encode(challenge_response).decode(),
                "public_key": self.keypair.get_public_key_hex(),
                "accepted_version": "1.0"
            }
            
        elif handshake_type == "response":
            # ハンドシェイクレスポンスを処理（Alice側）
            session_id = payload.get("session_id")
            remote_ephemeral_key = payload.get("ephemeral_public_key")
            challenge_response = payload.get("challenge_response")
            
            if not session_id:
                return {
                    "status": "error",
                    "error": "Missing session_id"
                }
            
            session = self.e2e_manager.get_session(session_id)
            if not session:
                return {
                    "status": "error",
                    "error": "Session not found"
                }
            
            # チャレンジレスポンスを検証
            if session.challenge and challenge_response:
                import hashlib
                expected_response = hashlib.sha256(
                    session.challenge + self.keypair.private_key
                ).digest()
                actual_response = base64.b64decode(challenge_response)
                
                if actual_response != expected_response:
                    return {
                        "status": "error",
                        "error": "Invalid challenge response"
                    }
            
            # ハンドシェイクを完了
            remote_pubkey_bytes = bytes.fromhex(payload.get("public_key", ""))
            remote_ephemeral_bytes = base64.b64decode(remote_ephemeral_key)
            session.complete_handshake(remote_pubkey_bytes, remote_ephemeral_bytes)
            
            logger.info(f"E2E handshake completed with {sender_id}, session={session_id}")
            
            return {
                "status": "ok",
                "handshake_type": "confirm",
                "session_id": session_id,
                "session_established": True
            }
            
        else:
            return {
                "status": "error",
                "error": f"Unknown handshake type: {handshake_type}"
            }
            
    except Exception as e:
        logger.error(f"Error handling E2E handshake: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


def encrypt_e2e_message(
    self,
    peer_id: str,
    payload: Dict[str, Any],
    session_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    メッセージをE2E暗号化する
    
    Args:
        peer_id: 相手ピアのエンティティID
        payload: 暗号化するペイロード
        session_id: 使用するセッションID（Noneの場合はアクティブセッションを使用）
        
    Returns:
        暗号化されたメッセージデータ、失敗時はNone
    """
    if not E2E_CRYPTO_AVAILABLE or not self.e2e_manager:
        logger.debug("E2E crypto not available, skipping encryption")
        return None
    
    try:
        # セッションを取得
        if session_id:
            session = self.e2e_manager.get_session(session_id)
        else:
            session = self.e2e_manager.get_active_session(peer_id)
        
        if not session:
            logger.warning(f"No E2E session found for peer {peer_id}")
            return None
        
        # メッセージを暗号化
        encrypted_msg = self.e2e_manager.encrypt_message(session.session_id, payload)
        
        return {
            "encrypted": True,
            "session_id": session.session_id,
            "data": encrypted_msg.payload.get("data"),
            "nonce": encrypted_msg.payload.get("nonce"),
            "sequence_num": encrypted_msg.sequence_num
        }
        
    except Exception as e:
        logger.error(f"Error encrypting E2E message: {e}")
        return None


def decrypt_e2e_message(
    self,
    peer_id: str,
    encrypted_data: Dict[str, Any],
    session_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    E2E暗号化メッセージを復号する
    
    Args:
        peer_id: 相手ピアのエンティティID
        encrypted_data: 暗号化されたデータ
        session_id: 使用するセッションID（Noneの場合はデータから取得）
        
    Returns:
        復号されたペイロード、失敗時はNone
    """
    if not E2E_CRYPTO_AVAILABLE or not self.e2e_manager:
        logger.debug("E2E crypto not available, skipping decryption")
        return None
    
    try:
        # セッションIDを取得
        sid = session_id or encrypted_data.get("session_id")
        if not sid:
            logger.error("No session_id provided for decryption")
            return None
        
        session = self.e2e_manager.get_session(sid)
        if not session:
            logger.warning(f"E2E session {sid} not found")
            return None
        
        # SecureMessageを構築
        from services.e2e_crypto import SecureMessage, MessageType
        msg = SecureMessage(
            version="1.0",
            msg_type=MessageType.STATUS_REPORT,
            sender_id=peer_id,
            recipient_id=self.entity_id,
            payload={
                "encrypted": True,
                "data": encrypted_data.get("data"),
                "nonce": encrypted_data.get("nonce")
            },
            session_id=sid,
            sequence_num=encrypted_data.get("sequence_num", 0)
        )
        
        # 復号
        decrypted = self.e2e_manager.decrypt_message(session, msg)
        return decrypted
        
    except Exception as e:
        logger.error(f"Error decrypting E2E message: {e}")
        return None


def get_e2e_session_info(self, peer_id: Optional[str] = None) -> Dict[str, Any]:
    """
    E2Eセッション情報を取得する
    
    Args:
        peer_id: 特定のピアID（Noneの場合は全セッション）
        
    Returns:
        セッション情報の辞書
    """
    if not self.e2e_manager:
        return {
            "available": False,
            "sessions": []
        }
    
    try:
        sessions = self.e2e_manager.list_sessions(peer_id)
        stats = self.e2e_manager.get_stats()
        
        return {
            "available": True,
            "sessions": sessions,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting E2E session info: {e}")
        return {
            "available": False,
            "error": str(e)
        }
