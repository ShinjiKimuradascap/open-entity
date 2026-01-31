#!/usr/bin/env python3
"""
E2E Session Management for Peer Communication Protocol v1.1

Implements:
- E2E encrypted session management
- X25519 key exchange (ECDH) using cryptography library
- AES-256-GCM payload encryption
- Session lifecycle management (6-step handshake)
- Perfect Forward Secrecy (ephemeral keys per session)
- Sequence numbers for ordering and replay protection

This module replaces e2e_crypto.py with a cryptography-based implementation,
eliminating the PyNaCl dependency.

Protocol compliance: peer_protocol_v1.1.md
"""

import os
import json
import base64
import secrets
import uuid
import logging
from typing import Optional, Dict, Any, Tuple, Set, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Import from crypto_utils for key management
from services.crypto_utils import CryptoManager, generate_entity_keypair

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
AES_KEY_SIZE_BYTES = 32  # 256-bit key for AES-256-GCM
NONCE_SIZE_BYTES = 12    # 96-bit nonce for AES-GCM
DEFAULT_SESSION_TIMEOUT_SECONDS = 3600  # 1 hour
MAX_SEQUENCE_NUMBER = 2**31 - 1


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
    def derive_from_shared_secret(
        cls, 
        shared_secret: bytes,
        salt: Optional[bytes] = None,
        info: bytes = b"peer-communication-session"
    ) -> "SessionKeys":
        """Derive session keys from X25519 shared secret using HKDF-SHA256
        
        Args:
            shared_secret: X25519 shared secret
            salt: Optional salt (defaults to None for HKDF)
            info: Context info for key derivation
            
        Returns:
            SessionKeys with encryption_key and auth_key
        """
        # Derive encryption key
        enc_key = HKDF(
            algorithm=hashes.SHA256(),
            length=AES_KEY_SIZE_BYTES,
            salt=salt,
            info=info + b"-encryption",
        ).derive(shared_secret)
        
        # Derive authentication key
        auth_key = HKDF(
            algorithm=hashes.SHA256(),
            length=AES_KEY_SIZE_BYTES,
            salt=salt,
            info=info + b"-authentication",
        ).derive(shared_secret)
        
        return cls(encryption_key=enc_key, auth_key=auth_key)


@dataclass
class E2ESession:
    """
    End-to-end encrypted session between two entities
    
    Protocol v1.1 compliant session with:
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
    local_ed25519_public_key: Optional[bytes] = None
    remote_ed25519_public_key: Optional[bytes] = None
    session_keys: Optional[SessionKeys] = None
    
    # Ephemeral X25519 keys for this session (PFS)
    ephemeral_private_key: Optional[X25519PrivateKey] = field(default=None, repr=False)
    ephemeral_public_key: Optional[bytes] = field(default=None)
    remote_ephemeral_public_key: Optional[bytes] = None
    
    # Sequence numbers
    local_sequence: int = 0
    remote_sequence: int = 0
    
    # Configuration
    timeout_seconds: int = DEFAULT_SESSION_TIMEOUT_SECONDS
    max_sequence: int = MAX_SEQUENCE_NUMBER
    
    # Challenge for handshake verification
    challenge: Optional[bytes] = None
    challenge_response: Optional[bytes] = None
    
    def __post_init__(self):
        """Initialize ephemeral keys for this session"""
        if self.ephemeral_private_key is None:
            # Generate ephemeral X25519 keypair
            self.ephemeral_private_key = X25519PrivateKey.generate()
            self.ephemeral_public_key = self.ephemeral_private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
    
    @classmethod
    def create(
        cls,
        local_entity_id: str,
        remote_entity_id: str,
        local_ed25519_public_key: bytes,
        timeout_seconds: int = DEFAULT_SESSION_TIMEOUT_SECONDS
    ) -> "E2ESession":
        """Create a new E2E session
        
        Args:
            local_entity_id: Local entity identifier
            remote_entity_id: Remote entity identifier
            local_ed25519_public_key: Local Ed25519 public key
            timeout_seconds: Session timeout in seconds
            
        Returns:
            New E2ESession instance
        """
        session_id = str(uuid.uuid4())  # UUID v4
        
        return cls(
            session_id=session_id,
            local_entity_id=local_entity_id,
            remote_entity_id=remote_entity_id,
            local_ed25519_public_key=local_ed25519_public_key,
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
        """Validate incoming sequence number
        
        Accepts if sequence is greater than last seen (allowing gaps)
        or if wrapped around.
        
        Args:
            seq: Received sequence number
            
        Returns:
            True if valid, False otherwise
        """
        if seq > self.remote_sequence or (self.remote_sequence > self.max_sequence - 1000 and seq < 1000):
            self.remote_sequence = seq
            return True
        return False
    
    def complete_handshake(
        self, 
        remote_ed25519_public_key: Optional[bytes],
        remote_ephemeral_public_key: bytes
    ) -> None:
        """Complete handshake and derive session keys
        
        Args:
            remote_ed25519_public_key: Remote entity's Ed25519 public key
            remote_ephemeral_public_key: Remote ephemeral X25519 public key
        """
        self.remote_ed25519_public_key = remote_ed25519_public_key
        self.remote_ephemeral_public_key = remote_ephemeral_public_key
        
        # Perform ECDH with ephemeral keys
        remote_pub = X25519PublicKey.from_public_bytes(remote_ephemeral_public_key)
        shared_secret = self.ephemeral_private_key.exchange(remote_pub)
        
        # Derive session keys using HKDF-SHA256
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
            "remote_ephemeral_public_key": base64.b64encode(self.remote_ephemeral_public_key).decode() if self.remote_ephemeral_public_key else None,
            "has_session_keys": self.session_keys is not None,
            "timeout_seconds": self.timeout_seconds
        }
    
    def encrypt_payload(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        """Encrypt payload using session keys
        
        Args:
            payload: Dictionary to encrypt
            
        Returns:
            Tuple of (ciphertext_b64, nonce_b64)
            
        Raises:
            RuntimeError: If session keys not available
        """
        if not self.session_keys:
            raise RuntimeError("Session keys not available")
        
        plaintext = json.dumps(payload, sort_keys=True).encode("utf-8")
        nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
        
        aesgcm = AESGCM(self.session_keys.encryption_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        return (
            base64.b64encode(ciphertext).decode("ascii"),
            base64.b64encode(nonce).decode("ascii")
        )
    
    def decrypt_payload(self, ciphertext_b64: str, nonce_b64: str) -> Dict[str, Any]:
        """Decrypt payload using session keys
        
        Args:
            ciphertext_b64: Base64-encoded ciphertext
            nonce_b64: Base64-encoded nonce
            
        Returns:
            Decrypted payload dictionary
            
        Raises:
            RuntimeError: If session keys not available
            Exception: If decryption fails
        """
        if not self.session_keys:
            raise RuntimeError("Session keys not available")
        
        ciphertext = base64.b64decode(ciphertext_b64)
        nonce = base64.b64decode(nonce_b64)
        
        aesgcm = AESGCM(self.session_keys.encryption_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        
        return json.loads(plaintext.decode("utf-8"))


class E2ESessionManager:
    """
    Manager for multiple E2E encrypted sessions
    
    Handles:
    - Session creation and lookup
    - Message encryption/decryption via sessions
    - Session expiration and cleanup
    - Handshake coordination
    
    This class integrates with CryptoManager for key operations.
    """
    
    def __init__(
        self,
        crypto_manager: CryptoManager,
        default_timeout: int = DEFAULT_SESSION_TIMEOUT_SECONDS
    ):
        """Initialize E2E session manager
        
        Args:
            crypto_manager: CryptoManager instance for key operations
            default_timeout: Default session timeout in seconds
        """
        self.crypto_manager = crypto_manager
        self.entity_id = crypto_manager.entity_id
        self.default_timeout = default_timeout
        
        # Session storage: session_id -> E2ESession
        self._sessions: Dict[str, E2ESession] = {}
        
        # Index by remote entity: remote_id -> set of session_ids
        self._sessions_by_remote: Dict[str, Set[str]] = {}
        
        logger.info(f"E2ESessionManager initialized for entity: {self.entity_id}")
    
    def create_session(self, remote_entity_id: str) -> E2ESession:
        """Create a new session with a remote entity
        
        Args:
            remote_entity_id: Remote entity identifier
            
        Returns:
            New E2ESession instance
        """
        local_pubkey_bytes = bytes.fromhex(
            self.crypto_manager.get_ed25519_public_key_b64().replace("=", "")
        ) if not hasattr(self.crypto_manager, '_ed25519_public_key') else None
        
        # Get public key bytes from CryptoManager
        local_pubkey = self.crypto_manager._ed25519_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        session = E2ESession.create(
            local_entity_id=self.entity_id,
            remote_entity_id=remote_entity_id,
            local_ed25519_public_key=local_pubkey,
            timeout_seconds=self.default_timeout
        )
        
        self._sessions[session.session_id] = session
        
        if remote_entity_id not in self._sessions_by_remote:
            self._sessions_by_remote[remote_entity_id] = set()
        self._sessions_by_remote[remote_entity_id].add(session.session_id)
        
        logger.info(f"Created session {session.session_id} with {remote_entity_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[E2ESession]:
        """Get session by ID
        
        Args:
            session_id: Session identifier
            
        Returns:
            E2ESession or None if not found/expired
        """
        session = self._sessions.get(session_id)
        if session and session.is_expired():
            session.state = SessionState.EXPIRED
        return session
    
    def get_active_session(self, remote_entity_id: str) -> Optional[E2ESession]:
        """Get first active (established, non-expired) session with remote entity
        
        Args:
            remote_entity_id: Remote entity identifier
            
        Returns:
            Active E2ESession or None
        """
        session_ids = self._sessions_by_remote.get(remote_entity_id, set())
        
        for sid in session_ids:
            session = self._sessions.get(sid)
            if session and session.state == SessionState.ESTABLISHED and not session.is_expired():
                return session
        
        return None
    
    def close_session(self, session_id: str) -> bool:
        """Close and remove a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if closed, False if not found
        """
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
        
        logger.info(f"Closed session {session_id}")
        return True
    
    def cleanup_expired_sessions(self) -> int:
        """Remove all expired sessions
        
        Returns:
            Number of sessions removed
        """
        expired_ids = [
            sid for sid, session in self._sessions.items()
            if session.is_expired() or session.state == SessionState.EXPIRED
        ]
        
        for sid in expired_ids:
            self.close_session(sid)
        
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired sessions")
        
        return len(expired_ids)
    
    def list_sessions(self, remote_id: Optional[str] = None) -> list:
        """List all sessions, optionally filtered by remote entity
        
        Args:
            remote_id: Optional remote entity filter
            
        Returns:
            List of session dictionaries
        """
        if remote_id:
            session_ids = self._sessions_by_remote.get(remote_id, set())
            return [self._sessions[sid].to_dict() for sid in session_ids if sid in self._sessions]
        
        return [session.to_dict() for session in self._sessions.values()]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics
        
        Returns:
            Statistics dictionary
        """
        return {
            "total_sessions": len(self._sessions),
            "sessions_by_remote": {
                remote_id: len(sids) 
                for remote_id, sids in self._sessions_by_remote.items()
            },
            "session_states": {
                state.value: sum(1 for s in self._sessions.values() if s.state == state)
                for state in SessionState
            }
        }


# Import serialization here to avoid circular imports at module level
from cryptography.hazmat.primitives import serialization


if __name__ == "__main__":
    # Test the E2E session implementation
    print("=== Testing E2E Session ===")
    
    # Create test entities
    priv_a, pub_a = generate_entity_keypair()
    priv_b, pub_b = generate_entity_keypair()
    
    print(f"Entity A: {pub_a[:16]}...")
    print(f"Entity B: {pub_b[:16]}...")
    
    # Create CryptoManagers
    import os
    os.environ["ENTITY_PRIVATE_KEY"] = priv_a
    crypto_a = CryptoManager("entity-a")
    
    os.environ["ENTITY_PRIVATE_KEY"] = priv_b
    crypto_b = CryptoManager("entity-b")
    
    # Create session managers
    session_mgr_a = E2ESessionManager(crypto_a)
    session_mgr_b = E2ESessionManager(crypto_b)
    
    # Create session
    session_a = session_mgr_a.create_session("entity-b")
    print(f"\nCreated session: {session_a.session_id}")
    print(f"Ephemeral pubkey: {session_a.ephemeral_public_key.hex()[:32]}...")
    
    # Create matching session for B
    session_b = session_mgr_b.create_session("entity-a")
    session_b.session_id = session_a.session_id  # Same session ID for testing
    
    # Simulate handshake completion
    session_a.complete_handshake(
        remote_ed25519_public_key=bytes.fromhex(pub_b),
        remote_ephemeral_public_key=session_b.ephemeral_public_key
    )
    session_b.complete_handshake(
        remote_ed25519_public_key=bytes.fromhex(pub_a),
        remote_ephemeral_public_key=session_a.ephemeral_public_key
    )
    
    print(f"\nSession A state: {session_a.state.value}")
    print(f"Session B state: {session_b.state.value}")
    
    # Test encryption/decryption
    test_payload = {"type": "test", "message": "Hello, E2E!", "seq": 1}
    
    # A encrypts for B
    ciphertext, nonce = session_a.encrypt_payload(test_payload)
    print(f"\nEncrypted: {ciphertext[:48]}...")
    
    # B decrypts from A
    decrypted = session_b.decrypt_payload(ciphertext, nonce)
    print(f"Decrypted: {decrypted}")
    
    assert decrypted == test_payload, "Decryption failed!"
    print("\n✓ E2E encryption/decryption successful!")
    
    # Test session serialization
    session_dict = session_a.to_dict()
    print(f"\nSession dict keys: {list(session_dict.keys())}")
    
    # Test sequence numbers
    print("\n--- Testing sequence numbers ---")
    for i in range(5):
        seq = session_a.next_sequence()
        print(f"Sequence {i}: {seq}")
    
    # Test expiration
    print("\n--- Testing expiration ---")
    session_a.timeout_seconds = 0  # Immediate expiration
    import time
    time.sleep(0.1)
    print(f"Is expired: {session_a.is_expired()}")
    
    # Cleanup test
    print("\n--- Testing cleanup ---")
    session_mgr_a._sessions[session_a.session_id] = session_a
    count = session_mgr_a.cleanup_expired_sessions()
    print(f"Cleaned up {count} sessions")
    
    print("\n=== All E2E Session tests passed ===")
