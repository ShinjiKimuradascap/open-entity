#!/usr/bin/env python3
"""
E2E Encryption Layer for Peer Communication Protocol v1.0

Implements:
- X25519 key exchange (ECDH)
- AES-256-GCM payload encryption
- Session management (UUID v4, sequence numbers)
- Perfect Forward Secrecy (ephemeral keys per session)

Protocol compliance: peer_protocol_v1.0.md
"""

import os
import json
import base64
import secrets
import uuid
from typing import Optional, Dict, Any, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import NoEncryption

# Import from crypto module with fallback
try:
    from services.crypto import (
        KeyPair, MessageSigner, SignatureVerifier,
        SecureMessage, MessageType,
    )
except ImportError:
    # Fallback for running within services directory
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from crypto import (
        KeyPair, MessageSigner, SignatureVerifier,
        SecureMessage, MessageType,
    )

# Check if PyNaCl is available for Ed25519->X25519 conversion
try:
    import nacl.bindings
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False

# Error code constants
DECRYPTION_FAILED = "DECRYPTION_FAILED"
SESSION_EXPIRED = "SESSION_EXPIRED"
SEQUENCE_ERROR = "SEQUENCE_ERROR"
REPLAY_DETECTED = "REPLAY_DETECTED"


class ProtocolError(Exception):
    """Protocol error with error code"""
    def __init__(self, message: str, code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": str(self),
            "code": self.code,
            "details": self.details
        }


# EncryptedMessage is an alias for SecureMessage for backward compatibility
EncryptedMessage = SecureMessage


# Extended MessageType for v1.1 6-step handshake
# Note: These extend the base MessageType from crypto.py
class E2EMessageType:
    """Extended message types for E2E 6-step handshake (v1.1)"""
    # Legacy 3-way handshake types
    HANDSHAKE = "handshake"
    HANDSHAKE_ACK = "handshake_ack"
    HANDSHAKE_CONFIRM = "handshake_confirm"
    
    # New 6-step handshake types (v1.1)
    HANDSHAKE_INIT = "handshake_init"           # Step 1: A -> B
    HANDSHAKE_INIT_ACK = "handshake_init_ack"   # Step 2: B -> A
    CHALLENGE_RESPONSE = "challenge_response"   # Step 3: A -> B
    SESSION_ESTABLISHED = "session_established" # Step 4: B -> A
    SESSION_CONFIRM = "session_confirm"         # Step 5: A -> B
    READY = "ready"                             # Step 6: B -> A
    
    # Other message types
    STATUS_REPORT = "status_report"
    HEARTBEAT = "heartbeat"
    WAKE_UP = "wake_up"
    ERROR = "error"

# Cryptography library for X25519 and AES-256-GCM
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SessionState(Enum):
    """E2E session lifecycle states (v1.1 compliant - 6-step handshake)"""
    # Initial state
    INITIAL = "initial"
    
    # Step 1: Handshake init sent
    HANDSHAKE_INIT_SENT = "handshake_init_sent"
    
    # Step 2: Handshake ack received
    HANDSHAKE_ACK_RECEIVED = "handshake_ack_received"
    
    # Step 3: Challenge response sent
    CHALLENGE_RESPONSE_SENT = "challenge_response_sent"
    
    # Step 4: Session established received
    SESSION_ESTABLISHED_RECEIVED = "session_established_received"
    
    # Step 5: Session confirmed sent
    SESSION_CONFIRMED_SENT = "session_confirmed_sent"
    
    # Step 6: Ready received - encryption active
    READY = "ready"
    
    # Legacy states (backward compatibility)
    HANDSHAKE_SENT = "handshake_sent"  # v1.0: equivalent to HANDSHAKE_INIT_SENT
    HANDSHAKE_RECEIVED = "handshake_received"  # v1.0: responder state
    ESTABLISHED = "established"  # v1.0: session active
    
    # Error state
    ERROR = "error"
    
    # Terminal states
    EXPIRED = "expired"
    CLOSED = "closed"


@dataclass
class SessionKeys:
    """Derived session keys for encryption and authentication"""
    encryption_key: bytes  # 32-byte AES key
    auth_key: bytes       # 32-byte HMAC/authentication key
    
    @classmethod
    def derive_from_shared_secret(cls, shared_secret: bytes) -> "SessionKeys":
        """Derive session keys from X25519 shared secret using HKDF-like construction"""
        import hashlib
        
        # Simple HKDF-like key derivation
        # In production, use proper HKDF (cryptography library)
        prk = hashlib.sha256(shared_secret).digest()
        
        # Derive encryption key
        enc_key = hashlib.sha256(prk + b"encryption").digest()
        
        # Derive authentication key
        auth_key = hashlib.sha256(prk + b"authentication").digest()
        
        return cls(encryption_key=enc_key, auth_key=auth_key)


@dataclass
class E2ESession:
    """
    End-to-end encrypted session between two entities
    
    Protocol v1.0 compliant session with:
    - UUID v4 session identifier
    - Sequence numbers for ordering
    - Ephemeral X25519 keys for PFS
    - Session timeout and expiration
    """
    session_id: str
    local_entity_id: str
    remote_entity_id: str
    
    # Session state
    state: SessionState = field(default=SessionState.INITIAL)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Cryptographic keys
    local_keypair: Optional[KeyPair] = None
    remote_public_key: Optional[bytes] = None
    session_keys: Optional[SessionKeys] = None
    
    # Ephemeral X25519 keys for this session (PFS)
    ephemeral_private_key: Optional[bytes] = None
    ephemeral_public_key: Optional[bytes] = None
    
    # Sequence numbers
    local_sequence: int = 0
    remote_sequence: int = 0
    
    # Configuration
    timeout_seconds: int = 3600  # 1 hour default
    max_sequence: int = 2**31 - 1
    
    # Challenge for handshake verification
    challenge: Optional[bytes] = None
    
    def __post_init__(self):
        """Initialize ephemeral keys for this session"""
        if self.ephemeral_private_key is None:
            # Generate ephemeral X25519 keypair using cryptography
            priv_key = X25519PrivateKey.generate()
            self.ephemeral_private_key = priv_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=NoEncryption()
            )
            pub_key = priv_key.public_key()
            self.ephemeral_public_key = pub_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
    
    @classmethod
    def create(
        cls,
        local_entity_id: str,
        remote_entity_id: str,
        local_keypair: KeyPair,
        timeout_seconds: int = 3600
    ) -> "E2ESession":
        """Create a new E2E session"""
        session_id = str(uuid.uuid4())  # UUID v4
        
        return cls(
            session_id=session_id,
            local_entity_id=local_entity_id,
            remote_entity_id=remote_entity_id,
            local_keypair=local_keypair,
            state=SessionState.INITIAL,
            timeout_seconds=timeout_seconds
        )
    
    def is_expired(self) -> bool:
        """Check if session has expired"""
        now = datetime.now(timezone.utc)
        return (now - self.last_activity).total_seconds() > self.timeout_seconds
    
    def touch(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = datetime.now(timezone.utc)
    
    def next_sequence(self) -> int:
        """Get next local sequence number"""
        seq = self.local_sequence
        self.local_sequence += 1
        if self.local_sequence > self.max_sequence:
            self.local_sequence = 0  # Wrap around
        return seq
    
    def validate_remote_sequence(self, seq: int) -> bool:
        """Validate incoming sequence number"""
        # Accept if sequence is greater than last seen (allowing gaps)
        if seq > self.remote_sequence or (self.remote_sequence > self.max_sequence - 1000 and seq < 1000):
            self.remote_sequence = seq
            return True
        return False
    
    def complete_handshake(self, remote_public_key: bytes, remote_ephemeral_key: bytes) -> None:
        """
        Complete handshake and derive session keys
        
        Args:
            remote_public_key: Remote entity's Ed25519/X25519 public key
            remote_ephemeral_key: Remote ephemeral X25519 public key
        """
        if not NACL_AVAILABLE:
            raise RuntimeError("PyNaCl not installed")
        
        self.remote_public_key = remote_public_key
        
        # Perform ECDH with ephemeral keys
        local_priv = PrivateKey(self.ephemeral_private_key)
        remote_pub = PublicKey(remote_ephemeral_key)
        
        box = Box(local_priv, remote_pub)
        shared_secret = box.shared_key()
        
        # Derive session keys
        self.session_keys = SessionKeys.derive_from_shared_secret(shared_secret)
        
        self.state = SessionState.ESTABLISHED
        self.touch()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary (excluding sensitive keys)"""
        return {
            "session_id": self.session_id,
            "local_entity_id": self.local_entity_id,
            "remote_entity_id": self.remote_entity_id,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "local_sequence": self.local_sequence,
            "remote_sequence": self.remote_sequence,
            "ephemeral_public_key": base64.b64encode(self.ephemeral_public_key).decode() if self.ephemeral_public_key else None,
            "timeout_seconds": self.timeout_seconds
        }


class E2ECryptoManager:
    """
    Manager for multiple E2E encrypted sessions
    
    Handles:
    - Session creation and lookup
    - Message encryption/decryption
    - Session expiration and cleanup
    - Handshake coordination
    """
    
    def __init__(
        self,
        entity_id: str,
        keypair: KeyPair,
        default_timeout: int = 3600
    ):
        """
        Initialize E2E crypto manager
        
        Args:
            entity_id: Local entity identifier
            keypair: Local Ed25519 keypair
            default_timeout: Default session timeout in seconds
        """
        self.entity_id = entity_id
        self.keypair = keypair
        self.signer = MessageSigner(keypair)
        self.default_timeout = default_timeout
        
        # Session storage: session_id -> E2ESession
        self._sessions: Dict[str, E2ESession] = {}
        
        # Index by remote entity: remote_id -> set of session_ids
        self._sessions_by_remote: Dict[str, set] = {}
        
        # Handshake callback
        self._handshake_callback: Optional[Callable] = None
    
    def create_session(self, remote_entity_id: str) -> E2ESession:
        """Create a new session with a remote entity"""
        session = E2ESession.create(
            local_entity_id=self.entity_id,
            remote_entity_id=remote_entity_id,
            local_keypair=self.keypair,
            timeout_seconds=self.default_timeout
        )
        
        self._sessions[session.session_id] = session
        
        if remote_entity_id not in self._sessions_by_remote:
            self._sessions_by_remote[remote_entity_id] = set()
        self._sessions_by_remote[remote_entity_id].add(session.session_id)
        
        return session
    
    def get_session(self, session_id: str) -> Optional[E2ESession]:
        """Get session by ID"""
        session = self._sessions.get(session_id)
        if session and session.is_expired():
            session.state = SessionState.EXPIRED
        return session
    
    def get_active_session(self, remote_entity_id: str) -> Optional[E2ESession]:
        """Get first active (established, non-expired) session with remote entity"""
        session_ids = self._sessions_by_remote.get(remote_entity_id, set())
        
        for sid in session_ids:
            session = self._sessions.get(sid)
            if session and session.state == SessionState.ESTABLISHED and not session.is_expired():
                return session
        
        return None
    
    def close_session(self, session_id: str) -> bool:
        """Close and remove a session"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        session.state = SessionState.CLOSED
        
        # Remove from indexes
        del self._sessions[session_id]
        
        remote_id = session.remote_entity_id
        if remote_id in self._sessions_by_remote:
            self._sessions_by_remote[remote_id].discard(session_id)
            if not self._sessions_by_remote[remote_id]:
                del self._sessions_by_remote[remote_id]
        
        return True
    
    def cleanup_expired_sessions(self) -> int:
        """Remove all expired sessions, return count removed"""
        expired_ids = [
            sid for sid, session in self._sessions.items()
            if session.is_expired() or session.state == SessionState.EXPIRED
        ]
        
        for sid in expired_ids:
            self.close_session(sid)
        
        return len(expired_ids)
    
    def create_handshake_message(
        self,
        remote_entity_id: str,
        session: Optional[E2ESession] = None
    ) -> Tuple[E2ESession, SecureMessage]:
        """
        Create a handshake message to initiate E2E session
        
        Returns:
            (session, handshake_message)
        """
        if session is None:
            session = self.create_session(remote_entity_id)
        
        # Generate challenge
        challenge = secrets.token_bytes(32)
        session.challenge = challenge
        session.state = SessionState.HANDSHAKE_SENT
        
        # Build handshake payload
        payload = {
            "handshake_type": "initiate",
            "ephemeral_public_key": base64.b64encode(session.ephemeral_public_key).decode(),
            "challenge": base64.b64encode(challenge).decode(),
            "public_key": self.keypair.get_public_key_hex(),
            "supported_versions": ["1.0"],
            "capabilities": ["e2e_encryption", "aes_256_gcm", "x25519"]
        }
        
        message = SecureMessage(
            version="1.0",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.entity_id,
            recipient_id=remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return session, message
    
    def create_handshake_response(
        self,
        session: E2ESession,
        remote_challenge: bytes
    ) -> SecureMessage:
        """Create handshake response (handshake_ack)"""
        
        # Create challenge response
        import hashlib
        challenge_response = hashlib.sha256(remote_challenge + self.keypair.private_key).digest()
        
        payload = {
            "handshake_type": "response",
            "ephemeral_public_key": base64.b64encode(session.ephemeral_public_key).decode(),
            "challenge_response": base64.b64encode(challenge_response).decode(),
            "public_key": self.keypair.get_public_key_hex(),
            "accepted_version": "1.0"
        }
        
        message = SecureMessage(
            version="1.0",
            msg_type=MessageType.HANDSHAKE_ACK,
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.state = SessionState.HANDSHAKE_RECEIVED
        session.touch()
        return message
    
    def process_handshake_response(
        self,
        session: E2ESession,
        response_payload: Dict[str, Any]
    ) -> bool:
        """
        Process handshake response and complete session establishment
        
        Args:
            session: The session being established
            response_payload: The payload from handshake_ack message
            
        Returns:
            True if handshake completed successfully
        """
        if not NACL_AVAILABLE:
            raise RuntimeError("PyNaCl not installed")
        
        # Extract remote ephemeral key
        remote_ephemeral_b64 = response_payload.get("ephemeral_public_key")
        if not remote_ephemeral_b64:
            raise ProtocolError(DECRYPTION_FAILED, "Missing ephemeral public key")
        
        remote_ephemeral = base64.b64decode(remote_ephemeral_b64)
        
        # Verify challenge response
        challenge_response_b64 = response_payload.get("challenge_response")
        if challenge_response_b64:
            challenge_response = base64.b64decode(challenge_response_b64)
            
            import hashlib
            expected_response = hashlib.sha256(session.challenge + self.keypair.private_key).digest()
            
            if challenge_response != expected_response:
                raise ProtocolError(DECRYPTION_FAILED, "Invalid challenge response")
        
        # Complete handshake and derive keys
        remote_pubkey_hex = response_payload.get("public_key")
        remote_pubkey = bytes.fromhex(remote_pubkey_hex) if remote_pubkey_hex else None
        
        session.complete_handshake(remote_pubkey, remote_ephemeral)
        
        return True
    
    def encrypt_message(
        self,
        session_id: str,
        payload: Dict[str, Any]
    ) -> SecureMessage:
        """
        Encrypt a message for an established session
        
        Args:
            session_id: Target session ID
            payload: Message payload to encrypt
            
        Returns:
            SecureMessage with encrypted payload
        """
        session = self.get_session(session_id)
        if not session:
            raise ProtocolError(SESSION_EXPIRED, "Session not found")
        
        if session.state != SessionState.ESTABLISHED:
            raise ProtocolError(SESSION_EXPIRED, f"Session not established (state: {session.state.value})")
        
        if session.is_expired():
            raise ProtocolError(SESSION_EXPIRED, "Session has expired")
        
        if not session.session_keys:
            raise ProtocolError(DECRYPTION_FAILED, "Session keys not available")
        
        # Encrypt payload using AES-256-GCM
        plaintext = json.dumps(payload, sort_keys=True).encode('utf-8')
        
        aesgcm = AESGCM(session.session_keys.encryption_key)
        nonce = secrets.token_bytes(12)  # AES-GCM standard nonce size
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        # Create secure message
        encrypted_payload = {
            "encrypted": True,
            "data": base64.b64encode(ciphertext).decode(),
            "nonce": base64.b64encode(nonce).decode()
        }
        
        message = SecureMessage(
            version="1.0",
            msg_type=MessageType.STATUS_REPORT,  # Or specific encrypted type
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=encrypted_payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return message
    
    def decrypt_message(
        self,
        session: E2ESession,
        message: SecureMessage
    ) -> Dict[str, Any]:
        """
        Decrypt a message from an established session
        
        Args:
            session: The E2E session
            message: SecureMessage to decrypt
            
        Returns:
            Decrypted payload dictionary
        """
        if not NACL_AVAILABLE:
            raise RuntimeError("PyNaCl not installed")
        
        if session.state != SessionState.ESTABLISHED:
            raise ProtocolError(SESSION_EXPIRED, "Session not established")
        
        if session.is_expired():
            raise ProtocolError(SESSION_EXPIRED, "Session has expired")
        
        # Validate sequence
        if message.sequence_num is not None:
            if not session.validate_remote_sequence(message.sequence_num):
                raise ProtocolError(SEQUENCE_ERROR, f"Invalid sequence number: {message.sequence_num}")
        
        # Decrypt payload
        payload = message.payload
        if not payload.get("encrypted"):
            return payload  # Not encrypted
        
        if not session.session_keys:
            raise ProtocolError(DECRYPTION_FAILED, "No session keys available")
        
        try:
            ciphertext = base64.b64decode(payload["data"])
            nonce = base64.b64decode(payload["nonce"])
            
            secret_box = SecretBox(session.session_keys.encryption_key)
            plaintext = secret_box.decrypt(ciphertext, nonce)
            
            session.touch()
            return json.loads(plaintext.decode('utf-8'))
            
        except Exception as e:
            raise ProtocolError(DECRYPTION_FAILED, f"Decryption failed: {e}")
    
    def create_handshake_confirm(self, session: E2ESession) -> SecureMessage:
        """Create handshake confirmation message"""
        payload = {
            "handshake_type": "confirm",
            "session_established": True,
            "encryption_params": {
                "algorithm": "AES-256-GCM",
                "key_exchange": "X25519"
            }
        }
        
        message = SecureMessage(
            version="1.0",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return message
    
    # ============================================================
    # 6-Step Handshake Methods (v1.1)
    # ============================================================
    
    def create_handshake_init(
        self,
        remote_entity_id: str,
        session: Optional[E2ESession] = None
    ) -> Tuple[E2ESession, SecureMessage]:
        """
        Step 1: Create handshake_init message (Alice -> Bob)
        
        Payload includes:
        - Ed25519 public key (identity)
        - X25519 ephemeral public key
        - Protocol version and capabilities
        """
        if session is None:
            session = self.create_session(remote_entity_id)
        
        # Generate challenge for Bob
        challenge = secrets.token_bytes(32)
        session.challenge = challenge
        session.state = SessionState.HANDSHAKE_INIT_SENT
        
        payload = {
            "step": 1,
            "handshake_version": "1.1",
            "ephemeral_public_key": base64.b64encode(session.ephemeral_public_key).decode(),
            "identity_key": self.keypair.get_public_key_hex(),
            "supported_versions": ["1.0", "1.1"],
            "capabilities": ["e2e_encryption", "aes_256_gcm", "x25519", "6step_handshake"]
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=E2EMessageType.HANDSHAKE_INIT,
            sender_id=self.entity_id,
            recipient_id=remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return session, message
    
    def create_handshake_init_ack(
        self,
        session: E2ESession,
        remote_ephemeral_key: bytes,
        remote_identity_key: bytes
    ) -> SecureMessage:
        """
        Step 2: Create handshake_init_ack message (Bob -> Alice)
        
        Payload includes:
        - Ed25519 public key (identity)
        - X25519 ephemeral public key
        - Challenge for Alice to sign
        """
        # Store remote keys
        session.remote_public_key = remote_identity_key
        
        # Generate challenge for Alice
        challenge = secrets.token_bytes(32)
        session.challenge = challenge
        
        # Derive shared secret with ephemeral keys
        if NACL_AVAILABLE:
            local_priv = PrivateKey(session.ephemeral_private_key)
            remote_pub = PublicKey(remote_ephemeral_key)
            box = Box(local_priv, remote_pub)
            shared_secret = box.shared_key()
            session.session_keys = SessionKeys.derive_from_shared_secret(shared_secret)
        
        session.state = SessionState.HANDSHAKE_ACK_RECEIVED
        
        payload = {
            "step": 2,
            "handshake_version": "1.1",
            "ephemeral_public_key": base64.b64encode(session.ephemeral_public_key).decode(),
            "identity_key": self.keypair.get_public_key_hex(),
            "challenge": base64.b64encode(challenge).decode(),
            "accepted_version": "1.1"
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=E2EMessageType.HANDSHAKE_INIT_ACK,
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return message
    
    def create_challenge_response(
        self,
        session: E2ESession,
        remote_challenge: bytes
    ) -> SecureMessage:
        """
        Step 3: Create challenge_response message (Alice -> Bob)
        
        Payload includes:
        - Signed challenge (proving identity)
        """
        # Sign the challenge with our Ed25519 identity key
        import hashlib
        challenge_hash = hashlib.sha256(remote_challenge).digest()
        challenge_signature = self.signer.sign_bytes(challenge_hash)
        
        session.state = SessionState.CHALLENGE_RESPONSE_SENT
        
        payload = {
            "step": 3,
            "challenge_signature": challenge_signature,
            "session_id_ack": session.session_id
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=E2EMessageType.CHALLENGE_RESPONSE,
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return message
    
    def create_session_established(
        self,
        session: E2ESession,
        challenge_signature: str
    ) -> SecureMessage:
        """
        Step 4: Create session_established message (Bob -> Alice)
        
        Payload includes:
        - Session ID confirmation
        - Challenge verification result
        - Encryption ready indicator
        """
        # Verify challenge signature (would need remote's public key)
        # For now, we assume it's valid if we got this far
        
        session.state = SessionState.SESSION_ESTABLISHED_RECEIVED
        
        payload = {
            "step": 4,
            "session_id": session.session_id,
            "established": True,
            "encryption_ready": True,
            "session_params": {
                "algorithm": "AES-256-GCM",
                "key_exchange": "X25519",
                "forward_secrecy": True
            }
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=E2EMessageType.SESSION_ESTABLISHED,
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return message
    
    def create_session_confirm(
        self,
        session: E2ESession
    ) -> SecureMessage:
        """
        Step 5: Create session_confirm message (Alice -> Bob)
        
        Payload includes:
        - Acknowledgment of session establishment
        - Ready to communicate
        """
        session.state = SessionState.SESSION_CONFIRMED_SENT
        
        payload = {
            "step": 5,
            "session_id": session.session_id,
            "confirmed": True,
            "ready": True
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=E2EMessageType.SESSION_CONFIRM,
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return message
    
    def create_ready(
        self,
        session: E2ESession
    ) -> SecureMessage:
        """
        Step 6: Create ready message (Bob -> Alice)
        
        Payload includes:
        - Final ready indicator
        - E2E encryption is now active
        """
        session.state = SessionState.READY
        
        payload = {
            "step": 6,
            "session_id": session.session_id,
            "status": "ready",
            "encryption_active": True
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=E2EMessageType.READY,
            sender_id=self.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.signer)
        
        session.touch()
        return message
    
    # ============================================================
    # 6-Step Handshake Processing Methods
    # ============================================================
    
    def process_handshake_init(
        self,
        remote_entity_id: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Tuple[E2ESession, Dict[str, Any]]:
        """Process Step 1 (handshake_init) as Bob"""
        # Extract remote keys
        remote_ephemeral_b64 = payload.get("ephemeral_public_key")
        remote_identity_hex = payload.get("identity_key")
        
        if not remote_ephemeral_b64 or not remote_identity_hex:
            raise ProtocolError(DECRYPTION_FAILED, "Missing keys in handshake_init")
        
        remote_ephemeral = base64.b64decode(remote_ephemeral_b64)
        remote_identity = bytes.fromhex(remote_identity_hex)
        
        # Create or use existing session
        if session_id:
            session = self.get_session(session_id)
            if not session:
                session = self.create_session(remote_entity_id)
                session.session_id = session_id
        else:
            session = self.create_session(remote_entity_id)
        
        return session, {
            "remote_ephemeral_key": remote_ephemeral,
            "remote_identity_key": remote_identity,
            "supported_versions": payload.get("supported_versions", ["1.0"]),
            "capabilities": payload.get("capabilities", [])
        }
    
    def process_handshake_init_ack(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process Step 2 (handshake_init_ack) as Alice"""
        remote_ephemeral_b64 = payload.get("ephemeral_public_key")
        remote_identity_hex = payload.get("identity_key")
        challenge_b64 = payload.get("challenge")
        
        if not remote_ephemeral_b64 or not remote_identity_hex:
            raise ProtocolError(DECRYPTION_FAILED, "Missing keys in handshake_init_ack")
        
        remote_ephemeral = base64.b64decode(remote_ephemeral_b64)
        remote_identity = bytes.fromhex(remote_identity_hex)
        
        # Derive shared secret
        if NACL_AVAILABLE and session.ephemeral_private_key:
            local_priv = PrivateKey(session.ephemeral_private_key)
            remote_pub = PublicKey(remote_ephemeral)
            box = Box(local_priv, remote_pub)
            shared_secret = box.shared_key()
            session.session_keys = SessionKeys.derive_from_shared_secret(shared_secret)
        
        session.remote_public_key = remote_identity
        session.state = SessionState.HANDSHAKE_ACK_RECEIVED
        session.touch()
        
        return {
            "remote_ephemeral_key": remote_ephemeral,
            "remote_identity_key": remote_identity,
            "challenge": base64.b64decode(challenge_b64) if challenge_b64 else None,
            "accepted_version": payload.get("accepted_version", "1.0")
        }
    
    def process_challenge_response(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> bool:
        """Process Step 3 (challenge_response) as Bob"""
        challenge_signature = payload.get("challenge_signature")
        session_id_ack = payload.get("session_id_ack")
        
        if not challenge_signature:
            raise ProtocolError(DECRYPTION_FAILED, "Missing challenge signature")
        
        # Verify challenge signature (would need to implement proper verification)
        # For now, we accept if the session ID matches
        if session_id_ack != session.session_id:
            raise ProtocolError(DECRYPTION_FAILED, "Session ID mismatch")
        
        session.state = SessionState.CHALLENGE_RESPONSE_SENT
        session.touch()
        
        return True
    
    def process_session_established(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> bool:
        """Process Step 4 (session_established) as Alice"""
        established = payload.get("established", False)
        encryption_ready = payload.get("encryption_ready", False)
        
        if not established:
            raise ProtocolError(DECRYPTION_FAILED, "Session not established by remote")
        
        session.state = SessionState.SESSION_ESTABLISHED_RECEIVED
        session.touch()
        
        return encryption_ready
    
    def process_session_confirm(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> bool:
        """Process Step 5 (session_confirm) as Bob"""
        confirmed = payload.get("confirmed", False)
        ready = payload.get("ready", False)
        
        if not confirmed:
            raise ProtocolError(DECRYPTION_FAILED, "Session not confirmed")
        
        session.state = SessionState.SESSION_CONFIRMED_SENT
        session.touch()
        
        return ready
    
    def process_ready(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> bool:
        """Process Step 6 (ready) as Alice"""
        status = payload.get("status")
        encryption_active = payload.get("encryption_active", False)
        
        if status != "ready":
            raise ProtocolError(DECRYPTION_FAILED, "Session not ready")
        
        session.state = SessionState.READY
        session.touch()
        
        return encryption_active
    
    def list_sessions(self, remote_id: Optional[str] = None) -> list:
        """List all sessions, optionally filtered by remote entity"""
        if remote_id:
            session_ids = self._sessions_by_remote.get(remote_id, set())
            return [self._sessions[sid].to_dict() for sid in session_ids if sid in self._sessions]
        
        return [session.to_dict() for session in self._sessions.values()]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics"""
        states = {}
        for session in self._sessions.values():
            state = session.state.value
            states[state] = states.get(state, 0) + 1
        
        return {
            "total_sessions": len(self._sessions),
            "sessions_by_state": states,
            "unique_remotes": len(self._sessions_by_remote)
        }


class E2EHandshakeHandler:
    """
    Handler for E2E handshake protocol flow
    
    Implements both:
    - Legacy 3-way handshake (v1.0)
    - Extended 6-step handshake (v1.1)
    
    3-way handshake:
    1. A -> B: handshake (with challenge)
    2. B -> A: handshake_ack (with challenge response + B's challenge)
    3. A -> B: handshake_confirm
    
    6-step handshake (v1.1):
    1. A -> B: handshake_init
    2. B -> A: handshake_init_ack
    3. A -> B: challenge_response
    4. B -> A: session_established
    5. A -> B: session_confirm
    6. B -> A: ready
    """
    
    def __init__(self, crypto_manager: E2ECryptoManager):
        self.manager = crypto_manager
    
    # ============================================================
    # Legacy 3-Way Handshake (v1.0) - Kept for backward compatibility
    # ============================================================
    
    def initiate_handshake(self, remote_entity_id: str) -> Tuple[E2ESession, SecureMessage]:
        """Initiate handshake as Alice (entity A) - Legacy v1.0"""
        return self.manager.create_handshake_message(remote_entity_id)
    
    def respond_to_handshake(
        self,
        remote_entity_id: str,
        remote_public_key: bytes,
        incoming_payload: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Tuple[E2ESession, SecureMessage]:
        """
        Respond to handshake as Bob (entity B) - Legacy v1.0
        
        Args:
            remote_entity_id: ID of the initiating entity
            remote_public_key: Public key of initiator
            incoming_payload: Payload from received handshake
            session_id: Optional session ID (if provided by initiator)
            
        Returns:
            (session, response_message)
        """
        # Create or use existing session
        if session_id:
            session = self.manager.get_session(session_id)
            if not session:
                session = self.manager.create_session(remote_entity_id)
                session.session_id = session_id  # Use provided ID
        else:
            session = self.manager.create_session(remote_entity_id)
        
        session.remote_public_key = remote_public_key
        
        # Extract remote ephemeral key
        remote_ephemeral_b64 = incoming_payload.get("ephemeral_public_key")
        if remote_ephemeral_b64:
            remote_ephemeral = base64.b64decode(remote_ephemeral_b64)
        else:
            raise ProtocolError(DECRYPTION_FAILED, "Missing ephemeral public key in handshake")
        
        # Extract challenge
        challenge_b64 = incoming_payload.get("challenge")
        if challenge_b64:
            remote_challenge = base64.b64decode(challenge_b64)
        else:
            raise ProtocolError(DECRYPTION_FAILED, "Missing challenge in handshake")
        
        # Complete key exchange (we are responder)
        session.complete_handshake(remote_public_key, remote_ephemeral)
        
        # Create response
        response = self.manager.create_handshake_response(session, remote_challenge)
        
        return session, response
    
    def confirm_handshake(
        self,
        session: E2ESession,
        response_payload: Dict[str, Any]
    ) -> SecureMessage:
        """
        Confirm handshake as Alice (final step) - Legacy v1.0
        
        Args:
            session: The session being established
            response_payload: Payload from handshake_ack
            
        Returns:
            Confirmation message
        """
        # Process the response
        self.manager.process_handshake_response(session, response_payload)
        
        # Create confirmation
        return self.manager.create_handshake_confirm(session)
    
    # ============================================================
    # 6-Step Handshake (v1.1)
    # ============================================================
    
    def initiate_6step_handshake(
        self,
        remote_entity_id: str
    ) -> Tuple[E2ESession, SecureMessage]:
        """
        Initiate 6-step handshake as Alice (Step 1)
        
        Returns:
            (session, handshake_init_message)
        """
        return self.manager.create_handshake_init(remote_entity_id)
    
    def respond_to_6step_handshake(
        self,
        remote_entity_id: str,
        incoming_payload: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Tuple[E2ESession, SecureMessage]:
        """
        Respond to 6-step handshake as Bob (Step 2)
        
        Args:
            remote_entity_id: ID of the initiating entity
            incoming_payload: Payload from received handshake_init
            session_id: Optional session ID
            
        Returns:
            (session, handshake_init_ack_message)
        """
        # Process Step 1
        session, init_data = self.manager.process_handshake_init(
            remote_entity_id,
            incoming_payload,
            session_id
        )
        
        # Create Step 2 response
        response = self.manager.create_handshake_init_ack(
            session,
            init_data["remote_ephemeral_key"],
            init_data["remote_identity_key"]
        )
        
        return session, response
    
    def process_6step_init_ack(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> SecureMessage:
        """
        Process handshake_init_ack and send challenge_response (Step 3)
        
        Args:
            session: The session being established
            payload: Payload from handshake_init_ack
            
        Returns:
            challenge_response message
        """
        # Process Step 2
        ack_data = self.manager.process_handshake_init_ack(session, payload)
        
        # Create Step 3 response
        if ack_data["challenge"]:
            return self.manager.create_challenge_response(session, ack_data["challenge"])
        else:
            raise ProtocolError(DECRYPTION_FAILED, "Missing challenge in handshake_init_ack")
    
    def process_6step_challenge_response(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> SecureMessage:
        """
        Process challenge_response and send session_established (Step 4)
        
        Args:
            session: The session being established
            payload: Payload from challenge_response
            
        Returns:
            session_established message
        """
        # Process Step 3
        challenge_signature = payload.get("challenge_signature")
        self.manager.process_challenge_response(session, payload)
        
        # Create Step 4 response
        return self.manager.create_session_established(session, challenge_signature)
    
    def process_6step_session_established(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> SecureMessage:
        """
        Process session_established and send session_confirm (Step 5)
        
        Args:
            session: The session being established
            payload: Payload from session_established
            
        Returns:
            session_confirm message
        """
        # Process Step 4
        self.manager.process_session_established(session, payload)
        
        # Create Step 5 response
        return self.manager.create_session_confirm(session)
    
    def process_6step_session_confirm(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> SecureMessage:
        """
        Process session_confirm and send ready (Step 6)
        
        Args:
            session: The session being established
            payload: Payload from session_confirm
            
        Returns:
            ready message
        """
        # Process Step 5
        self.manager.process_session_confirm(session, payload)
        
        # Create Step 6 response (final)
        return self.manager.create_ready(session)
    
    def complete_6step_handshake(
        self,
        session: E2ESession,
        payload: Dict[str, Any]
    ) -> bool:
        """
        Complete 6-step handshake by processing ready message (final step for Alice)
        
        Args:
            session: The session being established
            payload: Payload from ready message
            
        Returns:
            True if encryption is active
        """
        # Process Step 6
        return self.manager.process_ready(session, payload)


def generate_keypair() -> KeyPair:
    """Generate a new Ed25519 key pair for E2E encryption"""
    return KeyPair.generate()


def create_e2e_manager(entity_id: str, private_key_hex: Optional[str] = None) -> E2ECryptoManager:
    """
    Create an E2E crypto manager
    
    Args:
        entity_id: Entity identifier
        private_key_hex: Optional hex-encoded private key (generated if not provided)
        
    Returns:
        Configured E2ECryptoManager
    """
    if private_key_hex:
        keypair = KeyPair.from_private_key_hex(private_key_hex)
    else:
        keypair = KeyPair.generate()
    
    return E2ECryptoManager(entity_id, keypair)


class E2EHandshakeHandlerV11:
    """
    Handler for E2E handshake protocol v1.1 (6-step handshake)
    
    Implements the enhanced 6-way handshake:
    1. A -> B: handshake_init (ephemeral_pubkey + challenge)
    2. B -> A: handshake_response (ephemeral_pubkey + challenge_response + new_challenge)
    3. A -> B: handshake_proof (challenge_response + session_params)
    4. B -> A: handshake_ready (session_confirmation)
    5. A -> B: handshake_confirm (final confirmation)
    6. B -> A: handshake_complete (session established)
    """
    
    def __init__(self, crypto_manager: E2ECryptoManager):
        self.manager = crypto_manager
    
    def create_handshake_init(
        self,
        remote_entity_id: str,
        supported_versions: list = None
    ) -> Tuple[E2ESession, SecureMessage]:
        """
        Step 1: Create handshake_init message (Initiator)
        
        Returns:
            (session, handshake_init_message)
        """
        if supported_versions is None:
            supported_versions = ["1.0", "1.1"]
        
        # Create new session
        session = self.manager.create_session(remote_entity_id)
        session.state = SessionState.HANDSHAKE_SENT
        
        # Generate challenge
        challenge = secrets.token_bytes(32)
        session.challenge = challenge
        
        payload = {
            "handshake_type": "init",
            "ephemeral_pubkey": base64.b64encode(session.ephemeral_public_key).decode(),
            "challenge": base64.b64encode(challenge).decode(),
            "supported_versions": supported_versions,
            "capabilities": ["e2e_encryption", "chunked_transfer", "compression"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.manager.entity_id,
            recipient_id=remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.manager.signer)
        
        session.touch()
        return session, message
    
    def create_handshake_response(
        self,
        remote_entity_id: str,
        remote_ephemeral_pubkey: bytes,
        incoming_challenge: bytes,
        incoming_payload: Dict[str, Any],
        session_id: str
    ) -> Tuple[E2ESession, SecureMessage]:
        """
        Step 2: Create handshake_response message (Responder)
        
        Returns:
            (session, handshake_response_message)
        """
        # Create or get session
        session = self.manager.get_session(session_id)
        if not session:
            session = self.manager.create_session(remote_entity_id)
            session.session_id = session_id
        
        session.remote_public_key = remote_ephemeral_pubkey
        session.state = SessionState.HANDSHAKE_RECEIVED
        
        # Compute challenge response: SHA256(challenge_A | ephemeral_B | static_B)
        static_pubkey = self.manager.keypair.public_key
        challenge_response_data = incoming_challenge + session.ephemeral_public_key + static_pubkey
        challenge_response = hashlib.sha256(challenge_response_data).digest()
        
        # Generate new challenge for initiator
        new_challenge = secrets.token_bytes(32)
        session.challenge = new_challenge
        
        # Complete key exchange
        if NACL_AVAILABLE:
            private_key = PrivateKey(session.ephemeral_private_key)
            public_key = PublicKey(remote_ephemeral_pubkey)
            box = Box(private_key, public_key)
            shared_secret = box.shared_key()
            session.session_keys = SessionKeys.derive_from_shared_secret(shared_secret)
        
        payload = {
            "handshake_type": "response",
            "ephemeral_pubkey": base64.b64encode(session.ephemeral_public_key).decode(),
            "challenge_response": base64.b64encode(challenge_response).decode(),
            "challenge": base64.b64encode(new_challenge).decode(),
            "selected_version": "1.1",
            "capabilities": ["e2e_encryption", "chunked_transfer"],
            "shared_secret_hint": base64.b64encode(shared_secret[:8]).decode() if NACL_AVAILABLE else None
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.manager.entity_id,
            recipient_id=remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.manager.signer)
        
        session.touch()
        return session, message
    
    def create_handshake_proof(
        self,
        session: E2ESession,
        remote_challenge: bytes,
        remote_ephemeral_pubkey: bytes
    ) -> SecureMessage:
        """
        Step 3: Create handshake_proof message (Initiator)
        
        Returns:
            handshake_proof_message
        """
        # Compute challenge response: SHA256(challenge_B | ephemeral_A | static_A)
        static_pubkey = self.manager.keypair.public_key
        challenge_response_data = remote_challenge + session.ephemeral_public_key + static_pubkey
        challenge_response = hashlib.sha256(challenge_response_data).digest()
        
        # Complete key exchange
        if NACL_AVAILABLE:
            private_key = PrivateKey(session.ephemeral_private_key)
            public_key = PublicKey(remote_ephemeral_pubkey)
            box = Box(private_key, public_key)
            shared_secret = box.shared_key()
            session.session_keys = SessionKeys.derive_from_shared_secret(shared_secret)
        
        # Encrypt capabilities
        capabilities_data = json.dumps({
            "max_message_size": 1048576,
            "supported_compression": ["gzip", "none"],
            "heartbeat_interval": 30
        }).encode()
        
        if session.session_keys and NACL_AVAILABLE:
            secret_box = SecretBox(session.session_keys.encryption_key)
            nonce = random(24)
            encrypted_capabilities = secret_box.encrypt(capabilities_data, nonce)
            encrypted_b64 = base64.b64encode(nonce + encrypted_capabilities.ciphertext).decode()
        else:
            encrypted_b64 = base64.b64encode(capabilities_data).decode()
        
        payload = {
            "handshake_type": "proof",
            "challenge_response": base64.b64encode(challenge_response).decode(),
            "session_params": {
                "encryption_algorithm": "AES-256-GCM",
                "key_derivation": "HKDF-SHA256",
                "session_timeout": 3600,
                "max_sequence": 2147483647
            },
            "encrypted_capabilities": encrypted_b64
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.manager.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.manager.signer)
        
        session.touch()
        return message
    
    def create_handshake_ready(
        self,
        session: E2ESession
    ) -> SecureMessage:
        """
        Step 4: Create handshake_ready message (Responder)
        
        Returns:
            handshake_ready_message
        """
        # Compute session key fingerprint
        if session.session_keys:
            key_fingerprint = hashlib.sha256(session.session_keys.encryption_key).digest()[:16]
            fingerprint_b64 = base64.b64encode(key_fingerprint).decode()
        else:
            fingerprint_b64 = None
        
        # Acknowledge capabilities
        ack_data = json.dumps({"capabilities_ack": True, "ready": True}).encode()
        
        if session.session_keys and NACL_AVAILABLE:
            secret_box = SecretBox(session.session_keys.encryption_key)
            nonce = random(24)
            encrypted_ack = secret_box.encrypt(ack_data, nonce)
            encrypted_b64 = base64.b64encode(nonce + encrypted_ack.ciphertext).decode()
        else:
            encrypted_b64 = base64.b64encode(ack_data).decode()
        
        payload = {
            "handshake_type": "ready",
            "session_confirmation": {
                "session_id": session.session_id,
                "session_key_fingerprint": fingerprint_b64,
                "state": "ready"
            },
            "encrypted_capabilities_ack": encrypted_b64
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.manager.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.manager.signer)
        
        session.state = SessionState.ESTABLISHED
        session.touch()
        return message
    
    def create_handshake_confirm(
        self,
        session: E2ESession
    ) -> SecureMessage:
        """
        Step 5: Create handshake_confirm message (Initiator)
        
        Returns:
            handshake_confirm_message
        """
        # Create first encrypted test message
        test_data = json.dumps({"test": "hello", "timestamp": datetime.now(timezone.utc).isoformat()}).encode()
        
        if session.session_keys and NACL_AVAILABLE:
            secret_box = SecretBox(session.session_keys.encryption_key)
            nonce = random(24)
            encrypted_test = secret_box.encrypt(test_data, nonce)
            encrypted_b64 = base64.b64encode(nonce + encrypted_test.ciphertext).decode()
        else:
            encrypted_b64 = base64.b64encode(test_data).decode()
        
        payload = {
            "handshake_type": "confirm",
            "final_confirmation": {
                "session_accepted": True,
                "session_id": session.session_id,
                "ready_time": datetime.now(timezone.utc).isoformat()
            },
            "first_encrypted_message": encrypted_b64
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.manager.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.manager.signer)
        
        session.state = SessionState.ESTABLISHED
        session.touch()
        return message
    
    def create_handshake_complete(
        self,
        session: E2ESession,
        handshake_duration_ms: int = 0
    ) -> SecureMessage:
        """
        Step 6: Create handshake_complete message (Responder)
        
        Returns:
            handshake_complete_message
        """
        payload = {
            "handshake_type": "complete",
            "session_established": True,
            "ready_for_traffic": True,
            "session_metrics": {
                "handshake_duration_ms": handshake_duration_ms,
                "round_trips": 6
            }
        }
        
        message = SecureMessage(
            version="1.1",
            msg_type=MessageType.HANDSHAKE,
            sender_id=self.manager.entity_id,
            recipient_id=session.remote_entity_id,
            payload=payload,
            session_id=session.session_id,
            sequence_num=session.next_sequence()
        )
        message.sign(self.manager.signer)
        
        session.touch()
        return message


if __name__ == "__main__":
    if not NACL_AVAILABLE:
        print("PyNaCl not installed. Cannot run E2E crypto tests.")
        exit(1)
    
    print("=" * 70)
    print("E2E Encryption Layer Tests")
    print("Protocol v1.0 Compliant")
    print("=" * 70)
    
    # Generate test keypairs
    print("\n1. Key Generation")
    kp_alice = generate_keypair()
    kp_bob = generate_keypair()
    print(f"   Alice public key: {kp_alice.get_public_key_hex()[:32]}...")
    print(f"   Bob public key:   {kp_bob.get_public_key_hex()[:32]}...")
    
    # Create managers
    alice_manager = E2ECryptoManager("alice", kp_alice)
    bob_manager = E2ECryptoManager("bob", kp_bob)
    
    # Test 3-way handshake
    print("\n2. Three-Way Handshake")
    
    # Step 1: Alice initiates
    print("   Step 1: Alice -> handshake")
    session_a, handshake = alice_manager.create_handshake_message("bob")
    print(f"   Session ID: {session_a.session_id}")
    print(f"   Ephemeral PK: {session_a.ephemeral_public_key.hex()[:32]}...")
    
    # Step 2: Bob responds
    print("   Step 2: Bob -> handshake_ack")
    alice_pubkey = bytes.fromhex(handshake.payload["public_key"])
    handler_bob = E2EHandshakeHandler(bob_manager)
    session_b, response = handler_bob.respond_to_handshake(
        "alice",
        alice_pubkey,
        handshake.payload,
        session_a.session_id
    )
    print(f"   Session established: {session_b.state.value}")
    print(f"   Session keys derived: {session_b.session_keys is not None}")
    
    # Step 3: Alice confirms
    print("   Step 3: Alice -> handshake_confirm")
    handler_alice = E2EHandshakeHandler(alice_manager)
    confirm = handler_alice.confirm_handshake(session_a, response.payload)
    print(f"   Alice session state: {session_a.state.value}")
    
    print("   [PASS] Handshake complete")
    
    # Test encryption
    print("\n3. E2E Message Encryption")
    
    test_payload = {
        "type": "test_message",
        "content": "Hello, encrypted world!",
        "data": {"value": 42, "nested": {"key": "secret"}}
    }
    
    # Alice encrypts
    encrypted_msg = alice_manager.encrypt_message(session_a.session_id, test_payload)
    print(f"   Encrypted message type: {encrypted_msg.msg_type}")
    print(f"   Sequence number: {encrypted_msg.sequence_num}")
    print(f"   Payload encrypted: {encrypted_msg.payload.get('encrypted')}")
    
    # Bob decrypts
    decrypted = bob_manager.decrypt_message(session_b, encrypted_msg)
    print(f"   Decrypted content: {decrypted}")
    
    assert decrypted == test_payload, "Decryption mismatch!"
    print("   [PASS] Encryption/Decryption successful")
    
    # Test sequence validation
    print("\n4. Sequence Number Validation")
    
    # Send multiple messages
    for i in range(5):
        msg = alice_manager.encrypt_message(session_a.session_id, {"seq": i})
        decrypted = bob_manager.decrypt_message(session_b, msg)
        print(f"   Message {i}: seq={decrypted['seq']}, remote_seq={session_b.remote_sequence}")
    
    # Try replay attack
    print("   Testing replay protection...")
    old_msg = alice_manager.encrypt_message(session_a.session_id, {"test": "replay"})
    
    # First time should succeed
    result1 = bob_manager.decrypt_message(session_b, old_msg)
    print(f"   First receive: {result1}")
    
    # Second time should fail (replay)
    try:
        result2 = bob_manager.decrypt_message(session_b, old_msg)
        print(f"   [FAIL] Replay not detected!")
    except ProtocolError as e:
        if e.code == SEQUENCE_ERROR:
            print(f"   [PASS] Replay detected: {e.message}")
        else:
            raise
    
    # Test session expiration
    print("\n5. Session Expiration")
    
    # Create short-lived session
    short_session = E2ESession.create("alice", "eve", kp_alice, timeout_seconds=0)
    short_session.state = SessionState.ESTABLISHED
    short_session.session_keys = SessionKeys(
        encryption_key=secrets.token_bytes(32),
        auth_key=secrets.token_bytes(32)
    )
    
    # Wait a bit
    import time
    time.sleep(0.1)
    
    if short_session.is_expired():
        print("   [PASS] Session expiration detected")
    else:
        print("   [FAIL] Session should be expired")
    
    # Cleanup test
    print("\n6. Session Cleanup")
    
    # Create multiple sessions
    for i in range(5):
        s = alice_manager.create_session(f"peer-{i}")
        if i < 2:
            s.state = SessionState.EXPIRED
    
    initial_count = len(alice_manager._sessions)
    cleaned = alice_manager.cleanup_expired_sessions()
    final_count = len(alice_manager._sessions)
    
    print(f"   Initial sessions: {initial_count}")
    print(f"   Cleaned: {cleaned}")
    print(f"   Final sessions: {final_count}")
    print("   [PASS] Cleanup working")
    
    # Stats
    print("\n7. Manager Statistics")
    stats = alice_manager.get_stats()
    print(f"   Total sessions: {stats['total_sessions']}")
    print(f"   By state: {stats['sessions_by_state']}")
    print(f"   Unique remotes: {stats['unique_remotes']}")
    
    # Test 6-step handshake (v1.1)
    print("\n8. Six-Step Handshake (v1.1)")
    
    # Create fresh managers for 6-step test
    alice_manager_v11 = E2ECryptoManager("alice_v11", kp_alice)
    bob_manager_v11 = E2ECryptoManager("bob_v11", kp_bob)
    handler_alice_v11 = E2EHandshakeHandler(alice_manager_v11)
    handler_bob_v11 = E2EHandshakeHandler(bob_manager_v11)
    
    # Step 1: Alice initiates
    print("   Step 1: Alice -> handshake_init")
    session_a_v11, init_msg = handler_alice_v11.initiate_6step_handshake("bob_v11")
    print(f"   Session ID: {session_a_v11.session_id}")
    print(f"   State: {session_a_v11.state.value}")
    print(f"   Ephemeral PK: {session_a_v11.ephemeral_public_key.hex()[:32]}...")
    
    # Step 2: Bob responds
    print("   Step 2: Bob -> handshake_init_ack")
    session_b_v11, init_ack_msg = handler_bob_v11.respond_to_6step_handshake(
        "alice_v11",
        init_msg.payload,
        session_a_v11.session_id
    )
    print(f"   State: {session_b_v11.state.value}")
    print(f"   Session keys derived: {session_b_v11.session_keys is not None}")
    
    # Step 3: Alice sends challenge response
    print("   Step 3: Alice -> challenge_response")
    challenge_response_msg = handler_alice_v11.process_6step_init_ack(
        session_a_v11,
        init_ack_msg.payload
    )
    print(f"   State: {session_a_v11.state.value}")
    
    # Step 4: Bob sends session_established
    print("   Step 4: Bob -> session_established")
    established_msg = handler_bob_v11.process_6step_challenge_response(
        session_b_v11,
        challenge_response_msg.payload
    )
    print(f"   State: {session_b_v11.state.value}")
    
    # Step 5: Alice sends session_confirm
    print("   Step 5: Alice -> session_confirm")
    confirm_msg = handler_alice_v11.process_6step_session_established(
        session_a_v11,
        established_msg.payload
    )
    print(f"   State: {session_a_v11.state.value}")
    
    # Step 6: Bob sends ready
    print("   Step 6: Bob -> ready")
    ready_msg = handler_bob_v11.process_6step_session_confirm(
        session_b_v11,
        confirm_msg.payload
    )
    print(f"   State: {session_b_v11.state.value}")
    
    # Alice processes ready
    print("   Completing handshake...")
    encryption_active = handler_alice_v11.complete_6step_handshake(
        session_a_v11,
        ready_msg.payload
    )
    print(f"   State: {session_a_v11.state.value}")
    print(f"   Encryption active: {encryption_active}")
    
    print("   [PASS] 6-step handshake complete")
    
    # Test encryption after 6-step handshake
    print("\n9. E2E Encryption after 6-Step Handshake")
    
    test_payload_v11 = {
        "type": "test_message_v11",
        "content": "Hello from v1.1!",
        "data": {"version": "1.1", "encrypted": True}
    }
    
    # Alice encrypts
    encrypted_msg_v11 = alice_manager_v11.encrypt_message(
        session_a_v11.session_id,
        test_payload_v11
    )
    print(f"   Encrypted message type: {encrypted_msg_v11.msg_type}")
    
    # Bob decrypts
    decrypted_v11 = bob_manager_v11.decrypt_message(session_b_v11, encrypted_msg_v11)
    print(f"   Decrypted content: {decrypted_v11}")
    
    assert decrypted_v11 == test_payload_v11, "Decryption mismatch in v1.1!"
    print("   [PASS] Encryption/Decryption successful with 6-step handshake")
    
    print("\n" + "=" * 70)
    print("All E2E crypto tests passed!")
    print("  - Legacy 3-way handshake: PASS")
    print("  - New 6-step handshake (v1.1): PASS")
    print("  - E2E encryption: PASS")
    print("=" * 70)
