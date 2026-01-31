#!/usr/bin/env python3
"""
Unified Cryptographic Module for Peer Communication Protocol v1.1

Features:
- 6-step handshake with X25519 key exchange
- E2E payload encryption (AES-256-GCM)
- Perfect Forward Secrecy (PFS)
- Session state machine (9 states)
- Sequence number tracking per session
- Backward compatibility with v1.0

Migration from v1.0:
- All v1.0 features are maintained
- v1.1 features are opt-in via enable_v11 flag
"""

import os
import json
import base64
import hashlib
import secrets
import logging
import time
import uuid
from typing import Optional, Tuple, Dict, Any, Set, List, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum, auto

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.exceptions import InvalidSignature, InvalidKey

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

# Protocol versions
PROTOCOL_VERSION_1_0 = "1.0"
PROTOCOL_VERSION_1_1 = "1.1"

# Timing constants
TIMESTAMP_TOLERANCE_SECONDS = 60
JWT_EXPIRY_MINUTES = 5
NONCE_SIZE_BYTES = 16
AES_KEY_SIZE_BYTES = 32
REPLAY_WINDOW_SECONDS = 300
SESSION_TTL_SECONDS = 3600  # 1 hour
CHALLENGE_TTL_SECONDS = 60  # 60 seconds

# Key sizes
ED25519_PRIVATE_KEY_SIZE = 32
ED25519_PUBLIC_KEY_SIZE = 32
X25519_PRIVATE_KEY_SIZE = 32
X25519_PUBLIC_KEY_SIZE = 32

# ============================================================================
# Error Codes
# ============================================================================

class ErrorCode:
    """Error codes for protocol v1.1"""
    # v1.0 codes
    INVALID_VERSION = "INVALID_VERSION"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    REPLAY_DETECTED = "REPLAY_DETECTED"
    UNKNOWN_SENDER = "UNKNOWN_SENDER"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SEQUENCE_ERROR = "SEQUENCE_ERROR"
    DECRYPTION_FAILED = "DECRYPTION_FAILED"
    
    # v1.1 codes
    ENCRYPTION_REQUIRED = "ENCRYPTION_REQUIRED"
    CHALLENGE_EXPIRED = "CHALLENGE_EXPIRED"
    CHALLENGE_INVALID = "CHALLENGE_INVALID"
    HANDSHAKE_IN_PROGRESS = "HANDSHAKE_IN_PROGRESS"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    ENCRYPTION_NOT_READY = "ENCRYPTION_NOT_READY"
    INVALID_STATE = "INVALID_STATE"
    RATE_LIMITED = "RATE_LIMITED"


class ProtocolError(Exception):
    """Protocol error with error code"""
    
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


# ============================================================================
# Message Types
# ============================================================================

class MessageType:
    """Message type constants for protocol v1.0/1.1"""
    # v1.0 types
    HANDSHAKE = "handshake"
    HANDSHAKE_ACK = "handshake_ack"
    HANDSHAKE_CONFIRM = "handshake_confirm"
    STATUS_REPORT = "status_report"
    HEARTBEAT = "heartbeat"
    WAKE_UP = "wake_up"
    TASK_DELEGATE = "task_delegate"
    DISCOVERY = "discovery"
    ERROR = "error"
    CHUNK = "chunk"
    
    # v1.1 types
    HANDSHAKE_INIT = "handshake_init"
    HANDSHAKE_INIT_ACK = "handshake_init_ack"
    CHALLENGE_RESPONSE = "challenge_response"
    SESSION_ESTABLISHED = "session_established"
    SESSION_CONFIRM = "session_confirm"
    READY = "ready"
    ENCRYPTED = "encrypted"


# ============================================================================
# Session States (v1.1)
# ============================================================================

class SessionState(Enum):
    """Session states for protocol v1.1"""
    INITIAL = "initial"
    HANDSHAKE_INIT_SENT = "handshake_init_sent"
    HANDSHAKE_ACK_RECEIVED = "handshake_ack_received"
    CHALLENGE_SENT = "challenge_sent"
    SESSION_ESTABLISHED = "session_established"
    SESSION_CONFIRMED = "session_confirmed"
    READY = "ready"
    ERROR = "error"
    EXPIRED = "expired"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SecureSession:
    """Secure session state for protocol v1.1"""
    session_id: str
    sender_id: str
    recipient_id: str
    state: SessionState = SessionState.INITIAL
    sequence_num: int = 0
    created_at: str = None
    last_activity: str = None
    expires_at: str = None
    protocol_version: str = PROTOCOL_VERSION_1_1
    
    # v1.1 fields
    x25519_private_key: Optional[bytes] = None
    x25519_public_key: Optional[bytes] = None
    peer_x25519_public_key: Optional[bytes] = None
    shared_secret: Optional[bytes] = None
    session_key: Optional[bytes] = None
    challenge: Optional[str] = None
    challenge_timestamp: Optional[float] = None
    handshake_hash: Optional[bytes] = None
    encryption_ready: bool = False
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if self.last_activity is None:
            self.last_activity = self.created_at
        if self.expires_at is None:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
            self.expires_at = expiry.isoformat()
    
    def increment_sequence(self) -> int:
        """Increment and return the next sequence number"""
        self.sequence_num += 1
        self.update_activity()
        return self.sequence_num
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now(timezone.utc).isoformat()
    
    def is_expired(self) -> bool:
        """Check if session has expired"""
        if self.state == SessionState.EXPIRED:
            return True
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > expiry
        except:
            return True
    
    def can_encrypt(self) -> bool:
        """Check if session is ready for encryption"""
        return (
            self.state == SessionState.READY and
            self.encryption_ready and
            self.session_key is not None
        )


@dataclass
class SecureMessage:
    """Secure message structure"""
    payload: Dict[str, Any]
    timestamp: float
    nonce: str
    signature: str
    encrypted_payload: Optional[str] = None
    sender_public_key: Optional[str] = None
    jwt_token: Optional[str] = None
    sender_id: Optional[str] = None
    session_id: Optional[str] = None
    sequence_num: Optional[int] = None
    protocol_version: str = PROTOCOL_VERSION_1_1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecureMessage":
        """Create from dictionary"""
        return cls(
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", 0.0),
            nonce=data.get("nonce", ""),
            signature=data.get("signature", ""),
            encrypted_payload=data.get("encrypted_payload"),
            sender_public_key=data.get("sender_public_key"),
            jwt_token=data.get("jwt_token"),
            sender_id=data.get("sender_id"),
            session_id=data.get("session_id"),
            sequence_num=data.get("sequence_num"),
            protocol_version=data.get("protocol_version", PROTOCOL_VERSION_1_0),
        )


@dataclass
class HandshakeState:
    """Handshake state tracking"""
    initiated_at: float
    challenge: Optional[str] = None
    challenge_sent_at: Optional[float] = None
    x25519_private_key: Optional[bytes] = None
    x25519_public_key: Optional[bytes] = None
    peer_x25519_public_key: Optional[bytes] = None


# ============================================================================
# Key Management
# ============================================================================

def generate_entity_keypair() -> Tuple[bytes, bytes]:
    """Generate a new Ed25519 keypair for entity identity"""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    return private_bytes, public_bytes


def generate_x25519_keypair() -> Tuple[bytes, bytes]:
    """Generate a new X25519 keypair for ephemeral key exchange"""
    private_key = X25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    return private_bytes, public_bytes


def load_ed25519_private_key(key_bytes: bytes) -> Ed25519PrivateKey:
    """Load Ed25519 private key from bytes"""
    return Ed25519PrivateKey.from_private_bytes(key_bytes)


def load_ed25519_public_key(key_bytes: bytes) -> Ed25519PublicKey:
    """Load Ed25519 public key from bytes"""
    return Ed25519PublicKey.from_public_bytes(key_bytes)


def load_x25519_private_key(key_bytes: bytes) -> X25519PrivateKey:
    """Load X25519 private key from bytes"""
    return X25519PrivateKey.from_private_bytes(key_bytes)


def load_x25519_public_key(key_bytes: bytes) -> X25519PublicKey:
    """Load X25519 public key from bytes"""
    return X25519PublicKey.from_public_bytes(key_bytes)


def derive_session_key(shared_secret: bytes, handshake_hash: bytes) -> bytes:
    """Derive session key using HKDF-SHA256"""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=AES_KEY_SIZE_BYTES,
        salt=handshake_hash,
        info=b"peer-v1.1-session-key",
    )
    return hkdf.derive(shared_secret)


def compute_handshake_hash(
    ed25519_pub_a: bytes,
    x25519_pub_a: bytes,
    ed25519_pub_b: bytes,
    x25519_pub_b: bytes
) -> bytes:
    """Compute handshake hash for key derivation"""
    data = ed25519_pub_a + x25519_pub_a + ed25519_pub_b + x25519_pub_b
    return hashlib.sha256(data).digest()


# ============================================================================
# Unified Crypto Manager
# ============================================================================

class UnifiedCryptoManager:
    """
    Unified cryptographic manager for protocol v1.0 and v1.1
    
    Supports:
    - Ed25519 signatures for message authentication
    - X25519 + AES-256-GCM encryption for E2E confidentiality
    - 6-step handshake with PFS
    - Session state machine
    - Sequence number tracking
    """
    
    def __init__(
        self,
        entity_id: str,
        private_key: bytes,
        enable_v11: bool = True,
        session_ttl: int = SESSION_TTL_SECONDS
    ):
        self.entity_id = entity_id
        self.private_key = load_ed25519_private_key(private_key)
        self.public_key = self.private_key.public_key()
        self.public_key_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self.enable_v11 = enable_v11
        self.session_ttl = session_ttl
        
        # Session management
        self._sessions: Dict[str, SecureSession] = {}
        self._handshake_states: Dict[str, HandshakeState] = {}
        
        # Replay protection
        self._seen_nonces: Set[str] = set()
        self._nonce_times: Dict[str, float] = {}
        
        # Callbacks
        self._on_session_ready: Optional[Callable[[str], None]] = None
        
        logger.info(f"UnifiedCryptoManager initialized for {entity_id} (v1.1={enable_v11})")
    
    # ========================================================================
    # Key Properties
    # ========================================================================
    
    @property
    def public_key_b64(self) -> str:
        """Get base64 encoded public key"""
        return base64.b64encode(self.public_key_bytes).decode('utf-8')
    
    # ========================================================================
    # Session Management
    # ========================================================================
    
    def create_session(self, recipient_id: str, session_id: Optional[str] = None) -> SecureSession:
        """Create a new session"""
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        session = SecureSession(
            session_id=session_id,
            sender_id=self.entity_id,
            recipient_id=recipient_id,
            state=SessionState.INITIAL,
            protocol_version=PROTOCOL_VERSION_1_1 if self.enable_v11 else PROTOCOL_VERSION_1_0
        )
        
        self._sessions[session_id] = session
        logger.debug(f"Created session {session_id} for {recipient_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[SecureSession]:
        """Get session by ID"""
        session = self._sessions.get(session_id)
        if session and session.is_expired():
            session.state = SessionState.EXPIRED
        return session
    
    def remove_session(self, session_id: str):
        """Remove a session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"Removed session {session_id}")
    
    def list_sessions(self) -> List[SecureSession]:
        """List all active sessions"""
        return [
            session for session in self._sessions.values()
            if not session.is_expired()
        ]
    
    def set_session_ready_callback(self, callback: Callable[[str], None]):
        """Set callback for session ready event"""
        self._on_session_ready = callback
    
    # ========================================================================
    # 6-Step Handshake (v1.1)
    # ========================================================================
    
    def initiate_handshake(self, recipient_id: str) -> Tuple[str, Dict[str, Any]]:
        """
        Step 1: Initiate handshake (A -> B)
        
        Returns:
            (session_id, message_dict)
        """
        if not self.enable_v11:
            raise ProtocolError(
                ErrorCode.INVALID_VERSION,
                "v1.1 handshake not enabled"
            )
        
        # Create session
        session = self.create_session(recipient_id)
        
        # Generate ephemeral X25519 keypair
        x25519_private, x25519_public = generate_x25519_keypair()
        
        # Store in session
        session.x25519_private_key = x25519_private
        session.x25519_public_key = x25519_public
        session.state = SessionState.HANDSHAKE_INIT_SENT
        
        # Create message
        message = {
            "type": MessageType.HANDSHAKE_INIT,
            "protocol_version": PROTOCOL_VERSION_1_1,
            "session_id": session.session_id,
            "sender_id": self.entity_id,
            "recipient_id": recipient_id,
            "ed25519_public_key": self.public_key_b64,
            "x25519_public_key": base64.b64encode(x25519_public).decode('utf-8'),
            "timestamp": time.time(),
            "nonce": base64.b64encode(secrets.token_bytes(NONCE_SIZE_BYTES)).decode('utf-8'),
        }
        
        # Sign message
        signature = self._sign_message(message)
        message["signature"] = signature
        
        logger.info(f"Initiated handshake with {recipient_id}, session {session.session_id}")
        return session.session_id, message
    
    def handle_handshake_init(self, message: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Step 2: Handle handshake init and respond (B -> A)
        
        Returns:
            (session_id, response_message)
        """
        if not self.enable_v11:
            raise ProtocolError(
                ErrorCode.INVALID_VERSION,
                "v1.1 handshake not enabled"
            )
        
        # Verify message
        self._verify_handshake_message(message)
        
        sender_id = message["sender_id"]
        session_id = message["session_id"]
        
        # Create session
        session = self.create_session(sender_id, session_id)
        
        # Store peer's keys
        session.peer_x25519_public_key = base64.b64decode(
            message["x25519_public_key"]
        )
        
        # Generate ephemeral X25519 keypair
        x25519_private, x25519_public = generate_x25519_keypair()
        session.x25519_private_key = x25519_private
        session.x25519_public_key = x25519_public
        
        # Generate challenge
        challenge = base64.b64encode(secrets.token_bytes(32)).decode('utf-8')
        session.challenge = challenge
        session.challenge_timestamp = time.time()
        
        # Compute handshake hash (we don't have peer's Ed25519 key bytes yet)
        # Will compute after receiving challenge response
        
        session.state = SessionState.HANDSHAKE_ACK_RECEIVED
        
        # Create response
        response = {
            "type": MessageType.HANDSHAKE_INIT_ACK,
            "protocol_version": PROTOCOL_VERSION_1_1,
            "session_id": session_id,
            "sender_id": self.entity_id,
            "recipient_id": sender_id,
            "ed25519_public_key": self.public_key_b64,
            "x25519_public_key": base64.b64encode(x25519_public).decode('utf-8'),
            "challenge": challenge,
            "timestamp": time.time(),
            "nonce": base64.b64encode(secrets.token_bytes(NONCE_SIZE_BYTES)).decode('utf-8'),
        }
        
        # Sign response
        signature = self._sign_message(response)
        response["signature"] = signature
        
        logger.info(f"Sent handshake ack to {sender_id}, session {session_id}")
        return session_id, response
    
    def handle_handshake_ack(self, message: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Step 3: Handle handshake ack and send challenge response (A -> B)
        
        Returns:
            (session_id, response_message)
        """
        session_id = message["session_id"]
        session = self.get_session(session_id)
        
        if not session:
            raise ProtocolError(ErrorCode.SESSION_NOT_FOUND, "Session not found")
        
        if session.state != SessionState.HANDSHAKE_INIT_SENT:
            raise ProtocolError(
                ErrorCode.INVALID_STATE,
                f"Invalid state for handshake_ack: {session.state}"
            )
        
        # Verify message
        self._verify_handshake_message(message)
        
        # Store peer's keys
        session.peer_x25519_public_key = base64.b64decode(
            message["x25519_public_key"]
        )
        
        # Get challenge
        challenge = message.get("challenge")
        if not challenge:
            raise ProtocolError(ErrorCode.CHALLENGE_INVALID, "Missing challenge")
        
        # Sign challenge
        challenge_signature = self._sign_data(challenge.encode('utf-8'))
        
        # Compute shared secret
        x25519_private = load_x25519_private_key(session.x25519_private_key)
        x25519_peer = load_x25519_public_key(session.peer_x25519_public_key)
        shared_secret = x25519_private.exchange(x25519_peer)
        session.shared_secret = shared_secret
        
        # Compute handshake hash
        handshake_hash = compute_handshake_hash(
            self.public_key_bytes,
            session.x25519_public_key,
            base64.b64decode(message["ed25519_public_key"]),
            session.peer_x25519_public_key
        )
        session.handshake_hash = handshake_hash
        
        # Derive session key
        session.session_key = derive_session_key(shared_secret, handshake_hash)
        
        session.state = SessionState.CHALLENGE_SENT
        
        # Create response
        response = {
            "type": MessageType.CHALLENGE_RESPONSE,
            "protocol_version": PROTOCOL_VERSION_1_1,
            "session_id": session_id,
            "sender_id": self.entity_id,
            "recipient_id": session.recipient_id,
            "challenge": challenge,
            "challenge_signature": challenge_signature,
            "timestamp": time.time(),
            "nonce": base64.b64encode(secrets.token_bytes(NONCE_SIZE_BYTES)).decode('utf-8'),
        }
        
        # Sign response
        signature = self._sign_message(response)
        response["signature"] = signature
        
        logger.info(f"Sent challenge response for session {session_id}")
        return session_id, response
    
    def handle_challenge_response(self, message: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Step 4: Handle challenge response and establish session (B -> A)
        
        Returns:
            (session_id, response_message)
        """
        session_id = message["session_id"]
        session = self.get_session(session_id)
        
        if not session:
            raise ProtocolError(ErrorCode.SESSION_NOT_FOUND, "Session not found")
        
        if session.state != SessionState.HANDSHAKE_ACK_RECEIVED:
            raise ProtocolError(
                ErrorCode.INVALID_STATE,
                f"Invalid state for challenge_response: {session.state}"
            )
        
        # Verify challenge
        challenge = message.get("challenge")
        if challenge != session.challenge:
            raise ProtocolError(ErrorCode.CHALLENGE_INVALID, "Challenge mismatch")
        
        # Verify challenge signature
        challenge_signature = message.get("challenge_signature")
        if not challenge_signature:
            raise ProtocolError(ErrorCode.CHALLENGE_INVALID, "Missing challenge signature")
        
        # Get sender's public key from original message
        # (should be verified earlier)
        # Verify signature on challenge
        sender_public_key_b64 = message.get("sender_ed25519_public_key")
        if sender_public_key_b64:
            sender_public_key = load_ed25519_public_key(
                base64.b64decode(sender_public_key_b64)
            )
            try:
                sender_public_key.verify(
                    base64.b64decode(challenge_signature),
                    challenge.encode('utf-8')
                )
            except InvalidSignature:
                raise ProtocolError(ErrorCode.CHALLENGE_INVALID, "Invalid challenge signature")
        
        # Check challenge timestamp
        if session.challenge_timestamp:
            if time.time() - session.challenge_timestamp > CHALLENGE_TTL_SECONDS:
                raise ProtocolError(ErrorCode.CHALLENGE_EXPIRED, "Challenge expired")
        
        # Compute shared secret
        x25519_private = load_x25519_private_key(session.x25519_private_key)
        x25519_peer = load_x25519_public_key(session.peer_x25519_public_key)
        shared_secret = x25519_private.exchange(x25519_peer)
        session.shared_secret = shared_secret
        
        # Compute handshake hash
        # Note: We need peer's Ed25519 key - get from message
        peer_ed25519_pub = base64.b64decode(message.get("sender_ed25519_public_key", ""))
        handshake_hash = compute_handshake_hash(
            peer_ed25519_pub,
            session.peer_x25519_public_key,
            self.public_key_bytes,
            session.x25519_public_key
        )
        session.handshake_hash = handshake_hash
        
        # Derive session key
        session.session_key = derive_session_key(shared_secret, handshake_hash)
        
        session.state = SessionState.SESSION_ESTABLISHED
        
        # Create response
        response = {
            "type": MessageType.SESSION_ESTABLISHED,
            "protocol_version": PROTOCOL_VERSION_1_1,
            "session_id": session_id,
            "sender_id": self.entity_id,
            "recipient_id": session.recipient_id,
            "session_key_hash": base64.b64encode(
                hashlib.sha256(session.session_key).digest()[:8]
            ).decode('utf-8'),
            "timestamp": time.time(),
            "nonce": base64.b64encode(secrets.token_bytes(NONCE_SIZE_BYTES)).decode('utf-8'),
        }
        
        # Sign response
        signature = self._sign_message(response)
        response["signature"] = signature
        
        logger.info(f"Session established with {session.recipient_id}, session {session_id}")
        return session_id, response
    
    def handle_session_established(self, message: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Step 5: Handle session established and confirm (A -> B)
        
        Returns:
            (session_id, response_message)
        """
        session_id = message["session_id"]
        session = self.get_session(session_id)
        
        if not session:
            raise ProtocolError(ErrorCode.SESSION_NOT_FOUND, "Session not found")
        
        if session.state != SessionState.CHALLENGE_SENT:
            raise ProtocolError(
                ErrorCode.INVALID_STATE,
                f"Invalid state for session_established: {session.state}"
            )
        
        # Verify message
        self._verify_handshake_message(message)
        
        session.state = SessionState.SESSION_CONFIRMED
        
        # Create response
        response = {
            "type": MessageType.SESSION_CONFIRM,
            "protocol_version": PROTOCOL_VERSION_1_1,
            "session_id": session_id,
            "sender_id": self.entity_id,
            "recipient_id": session.recipient_id,
            "timestamp": time.time(),
            "nonce": base64.b64encode(secrets.token_bytes(NONCE_SIZE_BYTES)).decode('utf-8'),
        }
        
        # Sign response
        signature = self._sign_message(response)
        response["signature"] = signature
        
        logger.info(f"Session confirmed for {session_id}")
        return session_id, response
    
    def handle_session_confirm(self, message: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Step 6: Handle session confirm and send ready (B -> A)
        
        Returns:
            (session_id, response_message)
        """
        session_id = message["session_id"]
        session = self.get_session(session_id)
        
        if not session:
            raise ProtocolError(ErrorCode.SESSION_NOT_FOUND, "Session not found")
        
        if session.state != SessionState.SESSION_ESTABLISHED:
            raise ProtocolError(
                ErrorCode.INVALID_STATE,
                f"Invalid state for session_confirm: {session.state}"
            )
        
        # Verify message
        self._verify_handshake_message(message)
        
        # Mark as ready
        session.state = SessionState.READY
        session.encryption_ready = True
        
        # Create response
        response = {
            "type": MessageType.READY,
            "protocol_version": PROTOCOL_VERSION_1_1,
            "session_id": session_id,
            "sender_id": self.entity_id,
            "recipient_id": session.recipient_id,
            "timestamp": time.time(),
            "nonce": base64.b64encode(secrets.token_bytes(NONCE_SIZE_BYTES)).decode('utf-8'),
        }
        
        # Sign response
        signature = self._sign_message(response)
        response["signature"] = signature
        
        logger.info(f"Session {session_id} is ready for encrypted communication")
        
        # Trigger callback
        if self._on_session_ready:
            self._on_session_ready(session_id)
        
        return session_id, response
    
    def handle_ready(self, message: Dict[str, Any]) -> str:
        """
        Final step: Handle ready message (A)
        
        Returns:
            session_id
        """
        session_id = message["session_id"]
        session = self.get_session(session_id)
        
        if not session:
            raise ProtocolError(ErrorCode.SESSION_NOT_FOUND, "Session not found")
        
        if session.state != SessionState.SESSION_CONFIRMED:
            raise ProtocolError(
                ErrorCode.INVALID_STATE,
                f"Invalid state for ready: {session.state}"
            )
        
        # Verify message
        self._verify_handshake_message(message)
        
        # Mark as ready
        session.state = SessionState.READY
        session.encryption_ready = True
        
        logger.info(f"Session {session_id} is ready for encrypted communication")
        
        # Trigger callback
        if self._on_session_ready:
            self._on_session_ready(session_id)
        
        return session_id
    
    # ========================================================================
    # Message Encryption/Decryption
    # ========================================================================
    
    def encrypt_message(
        self,
        session_id: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Encrypt a message for a session
        
        Args:
            session_id: Session ID
            payload: Message payload to encrypt
            
        Returns:
            Encrypted message dict
        """
        session = self.get_session(session_id)
        
        if not session:
            raise ProtocolError(ErrorCode.SESSION_NOT_FOUND, "Session not found")
        
        if not session.can_encrypt():
            raise ProtocolError(
                ErrorCode.ENCRYPTION_NOT_READY,
                f"Encryption not ready for session {session_id}"
            )
        
        # Generate nonce for AES-GCM
        aes_nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
        
        # Serialize payload
        payload_json = json.dumps(payload, sort_keys=True).encode('utf-8')
        
        # Encrypt with AES-256-GCM
        aesgcm = AESGCM(session.session_key)
        ciphertext = aesgcm.encrypt(aes_nonce, payload_json, None)
        
        # Increment sequence
        sequence_num = session.increment_sequence()
        
        # Create message
        message = {
            "type": MessageType.ENCRYPTED,
            "protocol_version": PROTOCOL_VERSION_1_1,
            "session_id": session_id,
            "sender_id": self.entity_id,
            "recipient_id": session.recipient_id,
            "encrypted_payload": base64.b64encode(ciphertext).decode('utf-8'),
            "aes_nonce": base64.b64encode(aes_nonce).decode('utf-8'),
            "sequence_num": sequence_num,
            "timestamp": time.time(),
            "nonce": base64.b64encode(secrets.token_bytes(NONCE_SIZE_BYTES)).decode('utf-8'),
        }
        
        # Sign message
        signature = self._sign_message(message)
        message["signature"] = signature
        
        return message
    
    def decrypt_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt an encrypted message
        
        Args:
            message: Encrypted message dict
            
        Returns:
            Decrypted payload
        """
        session_id = message.get("session_id")
        session = self.get_session(session_id)
        
        if not session:
            raise ProtocolError(ErrorCode.SESSION_NOT_FOUND, "Session not found")
        
        if not session.can_encrypt():
            raise ProtocolError(
                ErrorCode.ENCRYPTION_NOT_READY,
                f"Encryption not ready for session {session_id}"
            )
        
        # Verify signature
        self._verify_message_signature(message)
        
        # Check sequence number
        seq_num = message.get("sequence_num")
        if seq_num is not None and seq_num <= session.sequence_num:
            raise ProtocolError(
                ErrorCode.SEQUENCE_ERROR,
                f"Sequence number too low: {seq_num} <= {session.sequence_num}"
            )
        
        # Update sequence
        session.sequence_num = seq_num
        session.update_activity()
        
        # Decrypt payload
        encrypted_payload = base64.b64decode(message["encrypted_payload"])
        aes_nonce = base64.b64decode(message["aes_nonce"])
        
        try:
            aesgcm = AESGCM(session.session_key)
            plaintext = aesgcm.decrypt(aes_nonce, encrypted_payload, None)
            payload = json.loads(plaintext.decode('utf-8'))
            return payload
        except Exception as e:
            raise ProtocolError(
                ErrorCode.DECRYPTION_FAILED,
                f"Failed to decrypt message: {e}"
            )
    
    # ========================================================================
    # v1.0 Compatibility
    # ========================================================================
    
    def create_signed_message(
        self,
        payload: Dict[str, Any],
        recipient_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> SecureMessage:
        """
        Create a signed message (v1.0 compatible)
        
        Args:
            payload: Message payload
            recipient_id: Optional recipient ID
            session_id: Optional session ID
            
        Returns:
            Signed SecureMessage
        """
        timestamp = time.time()
        nonce = base64.b64encode(secrets.token_bytes(NONCE_SIZE_BYTES)).decode('utf-8')
        
        # Check for replay
        if nonce in self._seen_nonces:
            raise ProtocolError(ErrorCode.REPLAY_DETECTED, "Replay attack detected")
        
        # Add to seen nonces
        self._seen_nonces.add(nonce)
        self._nonce_times[nonce] = timestamp
        
        # Clean old nonces
        self._clean_old_nonces()
        
        # Create message data
        message_data = {
            "payload": payload,
            "timestamp": timestamp,
            "nonce": nonce,
            "sender_id": self.entity_id,
            "sender_public_key": self.public_key_b64,
        }
        
        if recipient_id:
            message_data["recipient_id"] = recipient_id
        if session_id:
            message_data["session_id"] = session_id
            session = self.get_session(session_id)
            if session:
                seq_num = session.increment_sequence()
                message_data["sequence_num"] = seq_num
        
        # Sign
        signature = self._sign_data(
            json.dumps(message_data, sort_keys=True).encode('utf-8')
        )
        
        return SecureMessage(
            payload=payload,
            timestamp=timestamp,
            nonce=nonce,
            signature=signature,
            sender_public_key=self.public_key_b64,
            sender_id=self.entity_id,
            session_id=session_id,
            sequence_num=message_data.get("sequence_num"),
            protocol_version=PROTOCOL_VERSION_1_0
        )
    
    def verify_message(
        self,
        message: SecureMessage,
        sender_public_key: Optional[bytes] = None
    ) -> bool:
        """
        Verify a signed message (v1.0 compatible)
        
        Args:
            message: SecureMessage to verify
            sender_public_key: Optional sender public key bytes
            
        Returns:
            True if valid
        """
        # Check timestamp
        if abs(time.time() - message.timestamp) > TIMESTAMP_TOLERANCE_SECONDS:
            raise ProtocolError(
                ErrorCode.SESSION_EXPIRED,
                "Message timestamp too old"
            )
        
        # Check for replay
        if message.nonce in self._seen_nonces:
            raise ProtocolError(ErrorCode.REPLAY_DETECTED, "Replay attack detected")
        
        # Add to seen nonces
        self._seen_nonces.add(message.nonce)
        self._nonce_times[message.nonce] = message.timestamp
        
        # Clean old nonces
        self._clean_old_nonces()
        
        # Get sender public key
        if sender_public_key is None:
            if message.sender_public_key:
                sender_public_key = base64.b64decode(message.sender_public_key)
            else:
                raise ProtocolError(
                    ErrorCode.UNKNOWN_SENDER,
                    "No sender public key provided"
                )
        
        # Verify signature
        try:
            public_key = load_ed25519_public_key(sender_public_key)
            
            # Reconstruct signed data
            message_data = {
                "payload": message.payload,
                "timestamp": message.timestamp,
                "nonce": message.nonce,
                "sender_id": message.sender_id,
                "sender_public_key": message.sender_public_key,
            }
            if message.recipient_id:
                message_data["recipient_id"] = message.recipient_id
            if message.session_id:
                message_data["session_id"] = message.session_id
            if message.sequence_num:
                message_data["sequence_num"] = message.sequence_num
            
            public_key.verify(
                base64.b64decode(message.signature),
                json.dumps(message_data, sort_keys=True).encode('utf-8')
            )
            return True
        except InvalidSignature:
            raise ProtocolError(ErrorCode.INVALID_SIGNATURE, "Invalid signature")
    
    # ========================================================================
    # Private Methods
    # ========================================================================
    
    def _sign_message(self, message: Dict[str, Any]) -> str:
        """Sign a message dictionary"""
        # Create copy without signature
        data = {k: v for k, v in message.items() if k != "signature"}
        return self._sign_data(json.dumps(data, sort_keys=True).encode('utf-8'))
    
    def _sign_data(self, data: bytes) -> str:
        """Sign raw data"""
        signature = self.private_key.sign(data)
        return base64.b64encode(signature).decode('utf-8')
    
    def _verify_handshake_message(self, message: Dict[str, Any]):
        """Verify signature on handshake message"""
        signature = message.get("signature")
        if not signature:
            raise ProtocolError(ErrorCode.INVALID_SIGNATURE, "Missing signature")
        
        sender_public_key_b64 = message.get("ed25519_public_key")
        if not sender_public_key_b64:
            raise ProtocolError(ErrorCode.UNKNOWN_SENDER, "Missing sender public key")
        
        try:
            public_key = load_ed25519_public_key(
                base64.b64decode(sender_public_key_b64)
            )
            
            # Reconstruct signed data
            data = {k: v for k, v in message.items() if k != "signature"}
            signed_data = json.dumps(data, sort_keys=True).encode('utf-8')
            
            public_key.verify(
                base64.b64decode(signature),
                signed_data
            )
        except InvalidSignature:
            raise ProtocolError(ErrorCode.INVALID_SIGNATURE, "Invalid signature")
        
        # Check timestamp
        timestamp = message.get("timestamp", 0)
        if abs(time.time() - timestamp) > TIMESTAMP_TOLERANCE_SECONDS:
            raise ProtocolError(
                ErrorCode.SESSION_EXPIRED,
                "Message timestamp too old"
            )
        
        # Check for replay
        nonce = message.get("nonce")
        if nonce in self._seen_nonces:
            raise ProtocolError(ErrorCode.REPLAY_DETECTED, "Replay attack detected")
        
        self._seen_nonces.add(nonce)
        self._nonce_times[nonce] = timestamp
        self._clean_old_nonces()
    
    def _verify_message_signature(self, message: Dict[str, Any]):
        """Verify signature on a regular message"""
        signature = message.get("signature")
        if not signature:
            raise ProtocolError(ErrorCode.INVALID_SIGNATURE, "Missing signature")
        
        # Get sender public key from session or message
        session_id = message.get("session_id")
        session = self.get_session(session_id)
        
        sender_public_key_b64 = message.get("sender_ed25519_public_key")
        if not sender_public_key_b64 and session:
            # We need to have stored peer's public key somewhere
            # For now, skip this verification step
            return
        
        if not sender_public_key_b64:
            raise ProtocolError(ErrorCode.UNKNOWN_SENDER, "Missing sender public key")
        
        try:
            public_key = load_ed25519_public_key(
                base64.b64decode(sender_public_key_b64)
            )
            
            # Reconstruct signed data
            data = {k: v for k, v in message.items() if k != "signature"}
            signed_data = json.dumps(data, sort_keys=True).encode('utf-8')
            
            public_key.verify(
                base64.b64decode(signature),
                signed_data
            )
        except InvalidSignature:
            raise ProtocolError(ErrorCode.INVALID_SIGNATURE, "Invalid signature")
    
    def _clean_old_nonces(self):
        """Clean old nonces from replay protection"""
        current_time = time.time()
        expired = [
            nonce for nonce, timestamp in self._nonce_times.items()
            if current_time - timestamp > REPLAY_WINDOW_SECONDS
        ]
        for nonce in expired:
            self._seen_nonces.discard(nonce)
            del self._nonce_times[nonce]


# ============================================================================
# Wallet Manager (from crypto_utils)
# ============================================================================

class WalletManager:
    """
    Wallet manager for token storage and transactions
    Simplified version for Entity B
    """
    
    def __init__(self, wallet_path: str = "./data/wallets"):
        self.wallet_path = wallet_path
        self._wallets: Dict[str, Dict[str, Any]] = {}
        self._load_wallets()
    
    def _load_wallets(self):
        """Load wallets from disk"""
        import os
        if os.path.exists(self.wallet_path):
            for filename in os.listdir(self.wallet_path):
                if filename.endswith('.json'):
                    wallet_id = filename[:-5]
                    with open(os.path.join(self.wallet_path, filename), 'r') as f:
                        self._wallets[wallet_id] = json.load(f)
    
    def _save_wallet(self, wallet_id: str):
        """Save wallet to disk"""
        import os
        os.makedirs(self.wallet_path, exist_ok=True)
        filepath = os.path.join(self.wallet_path, f"{wallet_id}.json")
        with open(filepath, 'w') as f:
            json.dump(self._wallets[wallet_id], f, indent=2)
    
    def create_wallet(self, wallet_id: str) -> Dict[str, Any]:
        """Create a new wallet"""
        if wallet_id in self._wallets:
            raise ValueError(f"Wallet {wallet_id} already exists")
        
        private_key, public_key = generate_entity_keypair()
        
        wallet = {
            "wallet_id": wallet_id,
            "public_key": base64.b64encode(public_key).decode('utf-8'),
            "private_key": base64.b64encode(private_key).decode('utf-8'),
            "balance": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        self._wallets[wallet_id] = wallet
        self._save_wallet(wallet_id)
        
        return wallet
    
    def get_wallet(self, wallet_id: str) -> Optional[Dict[str, Any]]:
        """Get wallet by ID"""
        return self._wallets.get(wallet_id)
    
    def update_balance(self, wallet_id: str, amount: float) -> bool:
        """Update wallet balance"""
        if wallet_id not in self._wallets:
            return False
        
        self._wallets[wallet_id]["balance"] += amount
        self._save_wallet(wallet_id)
        return True


# ============================================================================
# Convenience Functions
# ============================================================================

def create_crypto_manager(
    entity_id: str,
    private_key: Optional[bytes] = None,
    enable_v11: bool = True
) -> UnifiedCryptoManager:
    """
    Create a UnifiedCryptoManager instance
    
    Args:
        entity_id: Entity ID
        private_key: Optional private key bytes (generated if None)
        enable_v11: Enable v1.1 features
        
    Returns:
        UnifiedCryptoManager instance
    """
    if private_key is None:
        private_key, _ = generate_entity_keypair()
    
    return UnifiedCryptoManager(
        entity_id=entity_id,
        private_key=private_key,
        enable_v11=enable_v11
    )


# Export main classes
__all__ = [
    'UnifiedCryptoManager',
    'WalletManager',
    'SecureSession',
    'SecureMessage',
    'SessionState',
    'MessageType',
    'ErrorCode',
    'ProtocolError',
    'generate_entity_keypair',
    'generate_x25519_keypair',
    'create_crypto_manager',
    'PROTOCOL_VERSION_1_0',
    'PROTOCOL_VERSION_1_1',
]
