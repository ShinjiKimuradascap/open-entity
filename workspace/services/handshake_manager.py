#!/usr/bin/env python3
"""
HandshakeManager - v1.1 Protocol 6-Step Handshake Implementation

6-Step Handshake Flow:
1. handshake_init: A sends Ed25519 pubkey + X25519 ephemeral pubkey
2. handshake_init_ack: B responds Ed25519 pubkey + X25519 ephemeral pubkey + challenge
3. challenge_response: A sends signed challenge
4. session_established: B sends session_id + confirmation
5. session_confirm: A sends ack of session
6. ready: B sends encryption ready
"""

import asyncio
import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable, Awaitable, Tuple

# Crypto imports
try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

# Local imports
try:
    from services.crypto import sign_message, verify_signature
    from services.session_manager import SessionManager, SessionState
except ImportError:
    from crypto import sign_message, verify_signature
    from session_manager import SessionManager, SessionState

logger = logging.getLogger(__name__)


class HandshakeState(Enum):
    """v1.1 Handshake States"""
    INITIAL = "initial"
    HANDSHAKE_INIT_SENT = "handshake_init_sent"
    HANDSHAKE_ACK_RECEIVED = "handshake_ack_received"
    CHALLENGE_SENT = "challenge_sent"
    SESSION_ESTABLISHED = "session_established"
    SESSION_CONFIRMED = "session_confirmed"
    READY = "ready"
    ERROR = "error"
    EXPIRED = "expired"


class HandshakeError(Enum):
    """v1.1 Handshake Error Codes"""
    INVALID_VERSION = "invalid_version"
    INVALID_SIGNATURE = "invalid_signature"
    REPLAY_DETECTED = "replay_detected"
    SESSION_EXPIRED = "session_expired"
    CHALLENGE_EXPIRED = "challenge_expired"
    CHALLENGE_INVALID = "challenge_invalid"
    HANDSHAKE_IN_PROGRESS = "handshake_in_progress"
    SESSION_NOT_FOUND = "session_not_found"
    INVALID_STATE = "invalid_state"
    TIMEOUT = "timeout"


@dataclass
class HandshakeSession:
    """v1.1 Handshake Session Data"""
    session_id: str
    peer_id: str
    state: HandshakeState
    created_at: datetime
    expires_at: datetime
    
    # Keys
    our_ed25519_pubkey: Optional[str] = None
    our_x25519_pubkey: Optional[str] = None
    our_x25519_privkey: Optional[bytes] = None  # ephemeral
    peer_ed25519_pubkey: Optional[str] = None
    peer_x25519_pubkey: Optional[str] = None
    
    # Challenge
    challenge_sent: Optional[str] = None
    challenge_received: Optional[str] = None
    challenge_expires: Optional[datetime] = None
    
    # Session key
    shared_secret: Optional[bytes] = None
    session_key: Optional[bytes] = None
    
    # Handshake hash for key derivation
    handshake_hash: Optional[bytes] = None
    
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_challenge_expired(self) -> bool:
        if not self.challenge_expires:
            return True
        return datetime.now(timezone.utc) > self.challenge_expires


@dataclass
class HandshakeConfig:
    """Handshake Configuration"""
    # Timeouts
    handshake_timeout: int = 60  # seconds
    challenge_timeout: int = 30  # seconds
    
    # Session lifetime
    session_ttl: int = 3600  # 1 hour
    
    # Protocol version
    protocol_version: str = "1.1"
    
    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0


class HandshakeManager:
    """
    v1.1 Protocol Handshake Manager
    
    Manages 6-step handshake process:
    1. handshake_init
    2. handshake_init_ack
    3. challenge_response
    4. session_established
    5. session_confirm
    6. ready
    """
    
    def __init__(
        self,
        entity_id: str,
        ed25519_private_key: bytes,
        session_manager: Optional[SessionManager] = None,
        config: Optional[HandshakeConfig] = None
    ):
        self.entity_id = entity_id
        self._ed25519_private_key = ed25519_private_key
        self._session_manager = session_manager
        self._config = config or HandshakeConfig()
        
        # Active handshakes
        self._handshakes: Dict[str, HandshakeSession] = {}  # session_id -> session
        self._peer_handshakes: Dict[str, str] = {}  # peer_id -> session_id
        
        # Callbacks
        self._on_handshake_complete: Optional[Callable[[str, bytes], Awaitable[None]]] = None
        self._on_handshake_error: Optional[Callable[[str, HandshakeError], Awaitable[None]]] = None
        
        # Ed25519 public key (cached)
        self._ed25519_pubkey = self._derive_ed25519_pubkey()
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    def _derive_ed25519_pubkey(self) -> str:
        """Derive Ed25519 public key from private key"""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            private_key = Ed25519PrivateKey.from_private_bytes(self._ed25519_private_key)
            public_key = private_key.public_key()
            return public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            ).hex()
        except Exception as e:
            logger.error(f"Failed to derive Ed25519 public key: {e}")
            return ""
    
    def set_callbacks(
        self,
        on_complete: Optional[Callable[[str, bytes], Awaitable[None]]] = None,
        on_error: Optional[Callable[[str, HandshakeError], Awaitable[None]]] = None
    ):
        """Set handshake event callbacks"""
        self._on_handshake_complete = on_complete
        self._on_handshake_error = on_error
    
    # ========================================================================
    # Step 1: Initiate Handshake (handshake_init)
    # ========================================================================
    
    async def initiate_handshake(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """
        Step 1: Initiate handshake with peer
        
        Returns handshake_init message to send
        """
        async with self._lock:
            # Check if handshake already in progress
            if peer_id in self._peer_handshakes:
                existing_id = self._peer_handshakes[peer_id]
                existing = self._handshakes.get(existing_id)
                if existing and not existing.is_expired():
                    logger.warning(f"Handshake already in progress with {peer_id}")
                    return None
            
            # Generate session ID
            session_id = secrets.token_hex(16)
            
            # Generate ephemeral X25519 keypair
            x25519_private = X25519PrivateKey.generate()
            x25519_public = x25519_private.public_key()
            x25519_pubkey_bytes = x25519_public.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            
            # Create handshake session
            now = datetime.now(timezone.utc)
            session = HandshakeSession(
                session_id=session_id,
                peer_id=peer_id,
                state=HandshakeState.HANDSHAKE_INIT_SENT,
                created_at=now,
                expires_at=now + timedelta(seconds=self._config.handshake_timeout),
                our_ed25519_pubkey=self._ed25519_pubkey,
                our_x25519_pubkey=x25519_pubkey_bytes.hex(),
                our_x25519_privkey=x25519_private.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption()
                )
            )
            
            self._handshakes[session_id] = session
            self._peer_handshakes[peer_id] = session_id
            
            logger.info(f"Initiated handshake with {peer_id}, session={session_id}")
            
            # Build handshake_init message
            message = {
                "type": "handshake_init",
                "version": self._config.protocol_version,
                "session_id": session_id,
                "entity_id": self.entity_id,
                "ed25519_pubkey": self._ed25519_pubkey,
                "x25519_pubkey": x25519_pubkey_bytes.hex(),
                "timestamp": now.isoformat()
            }
            
            # Sign message
            message["signature"] = self._sign_message(message)
            
            return message
    
    # ========================================================================
    # Step 2: Handle handshake_init and send handshake_init_ack
    # ========================================================================
    
    async def handle_handshake_init(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Step 2: Handle incoming handshake_init and respond with handshake_init_ack
        
        Returns handshake_init_ack message to send
        """
        try:
            # Validate message
            required = ["session_id", "entity_id", "ed25519_pubkey", "x25519_pubkey", "timestamp", "signature"]
            for field in required:
                if field not in message:
                    logger.error(f"Missing required field: {field}")
                    return None
            
            peer_id = message["entity_id"]
            session_id = message["session_id"]
            
            # Verify signature
            msg_copy = {k: v for k, v in message.items() if k != "signature"}
            if not self._verify_signature(msg_copy, message["signature"], message["ed25519_pubkey"]):
                logger.error(f"Invalid signature from {peer_id}")
                return None
            
            async with self._lock:
                # Generate ephemeral X25519 keypair
                x25519_private = X25519PrivateKey.generate()
                x25519_public = x25519_private.public_key()
                x25519_pubkey_bytes = x25519_public.public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                )
                
                # Generate challenge
                challenge = secrets.token_hex(32)
                
                # Create handshake session
                now = datetime.now(timezone.utc)
                session = HandshakeSession(
                    session_id=session_id,
                    peer_id=peer_id,
                    state=HandshakeState.HANDSHAKE_ACK_RECEIVED,
                    created_at=now,
                    expires_at=now + timedelta(seconds=self._config.handshake_timeout),
                    our_ed25519_pubkey=self._ed25519_pubkey,
                    our_x25519_pubkey=x25519_pubkey_bytes.hex(),
                    our_x25519_privkey=x25519_private.private_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PrivateFormat.Raw,
                        encryption_algorithm=serialization.NoEncryption()
                    ),
                    peer_ed25519_pubkey=message["ed25519_pubkey"],
                    peer_x25519_pubkey=message["x25519_pubkey"],
                    challenge_sent=challenge,
                    challenge_expires=now + timedelta(seconds=self._config.challenge_timeout)
                )
                
                self._handshakes[session_id] = session
                self._peer_handshakes[peer_id] = session_id
                
                logger.info(f"Received handshake_init from {peer_id}, session={session_id}")
                
                # Build handshake_init_ack message
                response = {
                    "type": "handshake_init_ack",
                    "version": self._config.protocol_version,
                    "session_id": session_id,
                    "entity_id": self.entity_id,
                    "ed25519_pubkey": self._ed25519_pubkey,
                    "x25519_pubkey": x25519_pubkey_bytes.hex(),
                    "challenge": challenge,
                    "timestamp": now.isoformat()
                }
                
                # Sign message
                response["signature"] = self._sign_message(response)
                
                return response
                
        except Exception as e:
            logger.exception(f"Error handling handshake_init: {e}")
            return None
    
    # ========================================================================
    # Step 3: Handle handshake_init_ack and send challenge_response
    # ========================================================================
    
    async def handle_handshake_init_ack(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Step 3: Handle handshake_init_ack and send challenge_response
        
        Returns challenge_response message to send
        """
        try:
            session_id = message.get("session_id")
            if not session_id:
                logger.error("Missing session_id in handshake_init_ack")
                return None
            
            async with self._lock:
                session = self._handshakes.get(session_id)
                if not session:
                    logger.error(f"Session not found: {session_id}")
                    return None
                
                if session.state != HandshakeState.HANDSHAKE_INIT_SENT:
                    logger.error(f"Invalid state for handshake_init_ack: {session.state}")
                    return None
                
                # Verify signature
                msg_copy = {k: v for k, v in message.items() if k != "signature"}
                if not self._verify_signature(msg_copy, message["signature"], message["ed25519_pubkey"]):
                    logger.error(f"Invalid signature in handshake_init_ack")
                    await self._set_error(session, HandshakeError.INVALID_SIGNATURE)
                    return None
                
                # Update session
                session.peer_ed25519_pubkey = message["ed25519_pubkey"]
                session.peer_x25519_pubkey = message["x25519_pubkey"]
                session.challenge_received = message["challenge"]
                session.state = HandshakeState.CHALLENGE_SENT
                
                # Derive shared secret
                if session.our_x25519_privkey and session.peer_x25519_pubkey:
                    session.shared_secret = self._derive_shared_secret(
                        session.our_x25519_privkey,
                        session.peer_x25519_pubkey
                    )
                
                logger.info(f"Received handshake_init_ack from {session.peer_id}")
                
                # Sign challenge
                challenge_signature = self._sign_bytes(bytes.fromhex(message["challenge"]))
                
                # Build challenge_response message
                response = {
                    "type": "challenge_response",
                    "version": self._config.protocol_version,
                    "session_id": session_id,
                    "entity_id": self.entity_id,
                    "challenge_signature": challenge_signature,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Sign message
                response["signature"] = self._sign_message(response)
                
                return response
                
        except Exception as e:
            logger.exception(f"Error handling handshake_init_ack: {e}")
            return None
    
    # ========================================================================
    # Step 4: Handle challenge_response and send session_established
    # ========================================================================
    
    async def handle_challenge_response(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Step 4: Handle challenge_response and send session_established
        
        Returns session_established message to send
        """
        try:
            session_id = message.get("session_id")
            if not session_id:
                logger.error("Missing session_id in challenge_response")
                return None
            
            async with self._lock:
                session = self._handshakes.get(session_id)
                if not session:
                    logger.error(f"Session not found: {session_id}")
                    return None
                
                if session.state != HandshakeState.HANDSHAKE_ACK_RECEIVED:
                    logger.error(f"Invalid state for challenge_response: {session.state}")
                    return None
                
                if session.is_challenge_expired():
                    logger.error("Challenge expired")
                    await self._set_error(session, HandshakeError.CHALLENGE_EXPIRED)
                    return None
                
                # Verify challenge signature
                challenge = bytes.fromhex(session.challenge_sent)
                challenge_sig = message.get("challenge_signature", "")
                
                if not self._verify_signature_bytes(challenge, challenge_sig, session.peer_ed25519_pubkey):
                    logger.error("Invalid challenge signature")
                    await self._set_error(session, HandshakeError.CHALLENGE_INVALID)
                    return None
                
                # Update session
                session.state = HandshakeState.SESSION_ESTABLISHED
                
                # Derive shared secret and session key
                if session.our_x25519_privkey and session.peer_x25519_pubkey:
                    session.shared_secret = self._derive_shared_secret(
                        session.our_x25519_privkey,
                        session.peer_x25519_pubkey
                    )
                    session.handshake_hash = self._compute_handshake_hash(session)
                    session.session_key = self._derive_session_key(session)
                
                logger.info(f"Challenge verified for {session.peer_id}, session established")
                
                # Create session in SessionManager if available
                if self._session_manager:
                    await self._session_manager.create_session(
                        session_id=session_id,
                        peer_id=session.peer_id,
                        session_key=session.session_key
                    )
                
                # Build session_established message
                response = {
                    "type": "session_established",
                    "version": self._config.protocol_version,
                    "session_id": session_id,
                    "entity_id": self.entity_id,
                    "confirmation": secrets.token_hex(16),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Sign message
                response["signature"] = self._sign_message(response)
                
                return response
                
        except Exception as e:
            logger.exception(f"Error handling challenge_response: {e}")
            return None
    
    # ========================================================================
    # Step 5: Handle session_established and send session_confirm
    # ========================================================================
    
    async def handle_session_established(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Step 5: Handle session_established and send session_confirm
        
        Returns session_confirm message to send
        """
        try:
            session_id = message.get("session_id")
            if not session_id:
                logger.error("Missing session_id in session_established")
                return None
            
            async with self._lock:
                session = self._handshakes.get(session_id)
                if not session:
                    logger.error(f"Session not found: {session_id}")
                    return None
                
                if session.state != HandshakeState.CHALLENGE_SENT:
                    logger.error(f"Invalid state for session_established: {session.state}")
                    return None
                
                # Update session
                session.state = HandshakeState.SESSION_CONFIRMED
                
                # Derive session key
                session.handshake_hash = self._compute_handshake_hash(session)
                session.session_key = self._derive_session_key(session)
                
                # Create session in SessionManager if available
                if self._session_manager:
                    await self._session_manager.create_session(
                        session_id=session_id,
                        peer_id=session.peer_id,
                        session_key=session.session_key
                    )
                
                logger.info(f"Session established with {session.peer_id}")
                
                # Build session_confirm message
                response = {
                    "type": "session_confirm",
                    "version": self._config.protocol_version,
                    "session_id": session_id,
                    "entity_id": self.entity_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Sign message
                response["signature"] = self._sign_message(response)
                
                return response
                
        except Exception as e:
            logger.exception(f"Error handling session_established: {e}")
            return None
    
    # ========================================================================
    # Step 6: Handle session_confirm and send ready
    # ========================================================================
    
    async def handle_session_confirm(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Step 6: Handle session_confirm and send ready
        
        Returns ready message to send
        """
        try:
            session_id = message.get("session_id")
            if not session_id:
                logger.error("Missing session_id in session_confirm")
                return None
            
            async with self._lock:
                session = self._handshakes.get(session_id)
                if not session:
                    logger.error(f"Session not found: {session_id}")
                    return None
                
                if session.state != HandshakeState.SESSION_ESTABLISHED:
                    logger.error(f"Invalid state for session_confirm: {session.state}")
                    return None
                
                # Update session
                session.state = HandshakeState.READY
                
                logger.info(f"Session confirmed with {session.peer_id}, ready for encrypted communication")
                
                # Notify callback
                if self._on_handshake_complete:
                    await self._on_handshake_complete(session.peer_id, session.session_key)
                
                # Build ready message
                response = {
                    "type": "ready",
                    "version": self._config.protocol_version,
                    "session_id": session_id,
                    "entity_id": self.entity_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Sign message
                response["signature"] = self._sign_message(response)
                
                return response
                
        except Exception as e:
            logger.exception(f"Error handling session_confirm: {e}")
            return None
    
    async def handle_ready(self, message: Dict[str, Any]) -> bool:
        """Handle ready message (final step)"""
        try:
            session_id = message.get("session_id")
            if not session_id:
                logger.error("Missing session_id in ready")
                return False
            
            async with self._lock:
                session = self._handshakes.get(session_id)
                if not session:
                    logger.error(f"Session not found: {session_id}")
                    return False
                
                if session.state != HandshakeState.SESSION_CONFIRMED:
                    logger.error(f"Invalid state for ready: {session.state}")
                    return False
                
                # Update session
                session.state = HandshakeState.READY
                
                logger.info(f"Session ready with {session.peer_id}")
                
                # Notify callback
                if self._on_handshake_complete:
                    await self._on_handshake_complete(session.peer_id, session.session_key)
                
                return True
                
        except Exception as e:
            logger.exception(f"Error handling ready: {e}")
            return False
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def _sign_message(self, message: Dict[str, Any]) -> str:
        """Sign message dictionary"""
        msg_str = json.dumps(message, sort_keys=True, separators=(',', ':'))
        return self._sign_bytes(msg_str.encode())
    
    def _sign_bytes(self, data: bytes) -> str:
        """Sign bytes"""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            private_key = Ed25519PrivateKey.from_private_bytes(self._ed25519_private_key)
            signature = private_key.sign(data)
            return signature.hex()
        except Exception as e:
            logger.error(f"Signing failed: {e}")
            return ""
    
    def _verify_signature(self, message: Dict[str, Any], signature: str, pubkey: str) -> bool:
        """Verify message signature"""
        msg_str = json.dumps(message, sort_keys=True, separators=(',', ':'))
        return self._verify_signature_bytes(msg_str.encode(), signature, pubkey)
    
    def _verify_signature_bytes(self, data: bytes, signature: str, pubkey: str) -> bool:
        """Verify bytes signature"""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey))
            public_key.verify(bytes.fromhex(signature), data)
            return True
        except Exception as e:
            logger.debug(f"Signature verification failed: {e}")
            return False
    
    def _derive_shared_secret(self, our_privkey: bytes, peer_pubkey: str) -> bytes:
        """Derive X25519 shared secret"""
        try:
            private_key = X25519PrivateKey.from_private_bytes(our_privkey)
            public_key = X25519PublicKey.from_public_bytes(bytes.fromhex(peer_pubkey))
            shared = private_key.exchange(public_key)
            return shared
        except Exception as e:
            logger.error(f"Failed to derive shared secret: {e}")
            return b""
    
    def _compute_handshake_hash(self, session: HandshakeSession) -> bytes:
        """Compute handshake hash for key derivation"""
        data = (
            session.session_id +
            session.our_x25519_pubkey +
            session.peer_x25519_pubkey +
            session.our_ed25519_pubkey +
            session.peer_ed25519_pubkey
        )
        return hashlib.sha256(data.encode()).digest()
    
    def _derive_session_key(self, session: HandshakeSession) -> bytes:
        """Derive session key using HKDF"""
        if not session.shared_secret or not session.handshake_hash:
            return b""
        
        try:
            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=session.handshake_hash,
                info=b"peer-v1.1-session-key"
            )
            return hkdf.derive(session.shared_secret)
        except Exception as e:
            logger.error(f"Failed to derive session key: {e}")
            return b""
    
    async def _set_error(self, session: HandshakeSession, error: HandshakeError):
        """Set session to error state and notify"""
        session.state = HandshakeState.ERROR
        if self._on_handshake_error:
            await self._on_handshake_error(session.peer_id, error)
    
    # ========================================================================
    # Public API
    # ========================================================================
    
    def get_session(self, session_id: str) -> Optional[HandshakeSession]:
        """Get handshake session by ID"""
        return self._handshakes.get(session_id)
    
    def get_session_for_peer(self, peer_id: str) -> Optional[HandshakeSession]:
        """Get handshake session for peer"""
        session_id = self._peer_handshakes.get(peer_id)
        if session_id:
            return self._handshakes.get(session_id)
        return None
    
    def is_ready(self, peer_id: str) -> bool:
        """Check if handshake is complete and ready for encrypted communication"""
        session = self.get_session_for_peer(peer_id)
        return session is not None and session.state == HandshakeState.READY
    
    def get_session_key(self, peer_id: str) -> Optional[bytes]:
        """Get derived session key for peer"""
        session = self.get_session_for_peer(peer_id)
        if session and session.state == HandshakeState.READY:
            return session.session_key
        return None
    
    async def cleanup_expired(self):
        """Remove expired handshakes"""
        async with self._lock:
            expired = [
                sid for sid, s in self._handshakes.items()
                if s.is_expired() or s.state == HandshakeState.ERROR
            ]
            for sid in expired:
                session = self._handshakes.pop(sid, None)
                if session:
                    self._peer_handshakes.pop(session.peer_id, None)
                    logger.debug(f"Cleaned up handshake session {sid}")
    
    async def close_session(self, session_id: str):
        """Close handshake session"""
        async with self._lock:
            session = self._handshakes.pop(session_id, None)
            if session:
                self._peer_handshakes.pop(session.peer_id, None)
                logger.info(f"Closed handshake session {session_id}")


# ==============================================================================
# Factory function
# ==============================================================================

def create_handshake_manager(
    entity_id: str,
    private_key: bytes,
    session_manager: Optional[SessionManager] = None,
    **kwargs
) -> HandshakeManager:
    """Factory function to create HandshakeManager"""
    config = HandshakeConfig(**kwargs)
    return HandshakeManager(
        entity_id=entity_id,
        ed25519_private_key=private_key,
        session_manager=session_manager,
        config=config
    )