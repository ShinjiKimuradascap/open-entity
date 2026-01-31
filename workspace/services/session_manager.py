#!/usr/bin/env python3
"""
Session Manager for Protocol v1.0

UUID-based session management with sequence numbers for message ordering.
Integrates with PeerService to provide secure, ordered message delivery.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Dict, Optional, Any, Tuple, Set

from services.crypto import (
    SecureSession, MessageValidator, ProtocolError, ChunkBuffer, ChunkUtils,
    INVALID_VERSION, SESSION_EXPIRED, SEQUENCE_ERROR
)


class SessionStatus(Enum):
    """Strict session state machine states per Protocol v1.1"""
    INIT = "init"                    # Session created, handshake not started
    HANDSHAKE_SENT = "handshake_sent"  # Handshake message sent, awaiting response
    HANDSHAKE_RECEIVED = "handshake_received"  # Handshake received, sent response
    ACTIVE = "active"                # Handshake complete, session operational
    CLOSING = "closing"              # Close initiated, awaiting confirmation
    CLOSED = "closed"                # Session terminated
    ERROR = "error"                  # Error state, session unusable
    
    def __str__(self) -> str:
        return self.value

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """Extended session state with peer tracking"""
    session: SecureSession
    expected_sequence: int = 1  # Next expected sequence number from peer
    last_sent_sequence: int = 0  # Last sequence number we sent
    established_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    is_active: bool = True
    
    def __post_init__(self):
        if self.expires_at is None:
            # Default session lifetime: 1 hour
            self.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)


class SessionManager:
    """
    Manages secure sessions between peers
    
    Features:
    - UUID v4 session creation and tracking
    - Sequence number validation for message ordering
    - Session expiration and cleanup
    - Per-peer session isolation
    """
    
    def __init__(
        self,
        default_ttl_minutes: int = 60,
        max_sequence_gap: int = 100,
        auto_cleanup_interval_sec: int = 300
    ):
        """
        Initialize session manager
        
        Args:
            default_ttl_minutes: Default session lifetime in minutes
            max_sequence_gap: Maximum allowed gap between sequence numbers
            auto_cleanup_interval_sec: Auto cleanup interval in seconds
        """
        self.default_ttl = timedelta(minutes=default_ttl_minutes)
        self.max_sequence_gap = max_sequence_gap
        
        # Sessions: {(sender_id, recipient_id): SessionState}
        self._sessions: Dict[Tuple[str, str], SessionState] = {}
        
        # Session lookup by ID: {session_id: (sender_id, recipient_id)}
        self._session_id_map: Dict[str, Tuple[str, str]] = {}
        
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._auto_cleanup_interval = auto_cleanup_interval_sec
        
        # Statistics
        self._stats = {
            "sessions_created": 0,
            "sessions_expired": 0,
            "sequence_errors": 0,
            "messages_ordered": 0
        }
    
    async def start(self) -> None:
        """Start session manager with auto-cleanup"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Session manager started")
    
    async def stop(self) -> None:
        """Stop session manager"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Session manager stopped")
    
    def _create_session_unlocked(
        self,
        sender_id: str,
        recipient_id: str
    ) -> SecureSession:
        """
        Create a new session between sender and recipient (must hold lock)
        
        Args:
            sender_id: Local entity ID
            recipient_id: Remote peer entity ID
            
        Returns:
            New SecureSession instance
        """
        session_key = (sender_id, recipient_id)
        
        # Check for existing active session
        if session_key in self._sessions:
            existing = self._sessions[session_key]
            if existing.is_active and existing.expires_at > datetime.now(timezone.utc):
                logger.debug(f"Reusing existing session: {existing.session.session_id}")
                return existing.session
        
        # Create new session
        session_id = str(uuid.uuid4())
        session = SecureSession(
            session_id=session_id,
            sender_id=sender_id,
            recipient_id=recipient_id
        )
        
        state = SessionState(
            session=session,
            expires_at=datetime.now(timezone.utc) + self.default_ttl
        )
        
        self._sessions[session_key] = state
        self._session_id_map[session_id] = session_key
        self._stats["sessions_created"] += 1
        
        logger.info(f"Created session {session_id[:8]}... for {sender_id} -> {recipient_id}")
        return session

    async def create_session(
        self,
        sender_id: str,
        recipient_id: str
    ) -> SecureSession:
        """
        Create a new session between sender and recipient
        
        Args:
            sender_id: Local entity ID
            recipient_id: Remote peer entity ID
            
        Returns:
            New SecureSession instance
        """
        async with self._lock:
            return self._create_session_unlocked(sender_id, recipient_id)
    
    async def get_session(
        self,
        session_id: str
    ) -> Optional[SecureSession]:
        """
        Get session by ID
        
        Args:
            session_id: Session UUID
            
        Returns:
            SecureSession if found and active, None otherwise
        """
        async with self._lock:
            session_key = self._session_id_map.get(session_id)
            if not session_key:
                return None
            
            state = self._sessions.get(session_key)
            if not state or not state.is_active:
                return None
            
            # Check expiration
            if datetime.now(timezone.utc) > state.expires_at:
                state.is_active = False
                return None
            
            return state.session
    
    async def validate_and_update_sequence(
        self,
        session_id: str,
        received_sequence: int
    ) -> bool:
        """
        Validate received sequence number and update expected sequence
        
        Args:
            session_id: Session UUID
            received_sequence: Received sequence number
            
        Returns:
            True if sequence is valid (in order)
            
        Raises:
            ProtocolError: If sequence is invalid or out of order
        """
        async with self._lock:
            session_key = self._session_id_map.get(session_id)
            if not session_key:
                raise ProtocolError(SESSION_EXPIRED, "Session not found")
            
            state = self._sessions.get(session_key)
            if not state or not state.is_active:
                raise ProtocolError(SESSION_EXPIRED, "Session expired or inactive")
            
            expected = state.expected_sequence
            
            # Check if sequence is exactly what we expect
            if received_sequence == expected:
                state.expected_sequence = expected + 1
                self._stats["messages_ordered"] += 1
                return True
            
            # Check for duplicate
            if received_sequence < expected:
                raise ProtocolError(
                    SEQUENCE_ERROR,
                    f"Duplicate or old sequence: got {received_sequence}, expected {expected}"
                )
            
            # Check for gap too large
            if received_sequence - expected > self.max_sequence_gap:
                raise ProtocolError(
                    SEQUENCE_ERROR,
                    f"Sequence gap too large: got {received_sequence}, expected {expected}"
                )
            
            # Accept the sequence (with gap) and update expected
            logger.warning(
                f"Sequence gap detected: got {received_sequence}, expected {expected}. "
                f"Missing messages: {expected} to {received_sequence - 1}"
            )
            state.expected_sequence = received_sequence + 1
            self._stats["messages_ordered"] += 1
            return True
    
    async def get_next_sequence(
        self,
        sender_id: str,
        recipient_id: str
    ) -> Tuple[str, int]:
        """
        Get next sequence number for sending
        
        Args:
            sender_id: Local entity ID
            recipient_id: Remote peer entity ID
            
        Returns:
            Tuple of (session_id, next_sequence_number)
        """
        session_key = (sender_id, recipient_id)
        
        async with self._lock:
            state = self._sessions.get(session_key)
            
            if not state or not state.is_active:
                # Create new session (within lock)
                self._create_session_unlocked(sender_id, recipient_id)
                state = self._sessions.get(session_key)
            
            state.last_sent_sequence += 1
            return (state.session.session_id, state.last_sent_sequence)
    
    async def terminate_session(self, session_id: str) -> bool:
        """
        Terminate a session
        
        Args:
            session_id: Session UUID
            
        Returns:
            True if session was found and terminated
        """
        async with self._lock:
            session_key = self._session_id_map.get(session_id)
            if not session_key:
                return False
            
            state = self._sessions.get(session_key)
            if state:
                # Remove from both mappings
                del self._sessions[session_key]
                del self._session_id_map[session_id]
                self._stats["sessions_expired"] += 1
                logger.info(f"Terminated session {session_id[:8]}...")
                return True
            return False
    
    async def get_peer_session(
        self,
        sender_id: str,
        recipient_id: str
    ) -> Optional[SecureSession]:
        """
        Get active session for a peer pair
        
        Args:
            sender_id: Local entity ID
            recipient_id: Remote peer entity ID
            
        Returns:
            SecureSession if found and active, None otherwise
        """
        session_key = (sender_id, recipient_id)
        
        async with self._lock:
            state = self._sessions.get(session_key)
            if not state or not state.is_active:
                return None
            
            if datetime.now(timezone.utc) > state.expires_at:
                state.is_active = False
                return None
            
            return state.session
    
    async def list_active_sessions(self) -> Dict[str, Any]:
        """
        List all active sessions
        
        Returns:
            Dictionary of session info
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            active = {}
            
            for session_key, state in self._sessions.items():
                if state.is_active and state.expires_at > now:
                    sender, recipient = session_key
                    active[state.session.session_id] = {
                        "sender_id": sender,
                        "recipient_id": recipient,
                        "sequence_num": state.session.sequence_num,
                        "expected_sequence": state.expected_sequence,
                        "expires_at": state.expires_at.isoformat(),
                        "established_at": state.established_at.isoformat()
                    }
            
            return active
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics"""
        async with self._lock:
            active_count = sum(
                1 for s in self._sessions.values()
                if s.is_active and s.expires_at > datetime.now(timezone.utc)
            )
            return {
                **self._stats,
                "active_sessions": active_count,
                "total_sessions": len(self._sessions)
            }
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup task"""
        while True:
            try:
                await asyncio.sleep(self._auto_cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_expired(self) -> None:
        """Remove expired sessions"""
        now = datetime.now(timezone.utc)
        expired_count = 0
        
        async with self._lock:
            to_remove = []
            
            for session_key, state in self._sessions.items():
                if state.is_active and state.expires_at < now:
                    to_remove.append(session_key)
            
            for session_key in to_remove:
                state = self._sessions[session_key]
                session_id = state.session.session_id
                
                # Remove from both mappings
                del self._sessions[session_key]
                del self._session_id_map[session_id]
                expired_count += 1
            
            # Update stats within lock
            if expired_count > 0:
                self._stats["sessions_expired"] += expired_count
        
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired sessions")
