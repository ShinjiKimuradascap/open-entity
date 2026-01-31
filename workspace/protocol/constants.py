#!/usr/bin/env python3
"""
Protocol Constants for Peer Communication
Peer Protocol v1.0/v1.1 用の定数定義

This module contains:
- MessageType: Message type constants
- ProtocolError: Exception class for protocol errors
- Error codes and constants
"""

from typing import Optional, Dict, Any


# Error codes
INVALID_FORMAT = "INVALID_FORMAT"
MISSING_FIELDS = "MISSING_FIELDS"
INVALID_VERSION = "INVALID_VERSION"
INVALID_SIGNATURE = "INVALID_SIGNATURE"
REPLAY_DETECTED = "REPLAY_DETECTED"
UNKNOWN_SENDER = "UNKNOWN_SENDER"
SESSION_EXPIRED = "SESSION_EXPIRED"
SEQUENCE_ERROR = "SEQUENCE_ERROR"
DECRYPTION_FAILED = "DECRYPTION_FAILED"


class MessageType:
    """Message type constants for protocol v1.0/v1.1"""
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
    CHUNK_INIT = "chunk_init"  # v1.1
    TASK_SUBMIT = "task_submit"  # v1.1
    TASK_STATUS = "task_status"  # v1.1
    PING = "ping"  # v1.1
    PONG = "pong"  # v1.1


class ProtocolError(Exception):
    """Protocol error with error code"""
    
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


# Protocol version constants
PROTOCOL_VERSION_1_0 = "1.0"
PROTOCOL_VERSION_1_1 = "1.1"
DEFAULT_PROTOCOL_VERSION = PROTOCOL_VERSION_1_1


# Timing constants
TIMESTAMP_TOLERANCE_SECONDS = 60
JWT_EXPIRY_MINUTES = 5
REPLAY_WINDOW_SECONDS = 300


# Crypto constants
NONCE_SIZE_BYTES = 16
AES_KEY_SIZE_BYTES = 32


# Chunking constants
DEFAULT_CHUNK_SIZE = 64000  # 64KB chunks (crypto_utils legacy)
CHUNK_SIZE_32K = 32768  # 32KB chunks (chunked_transfer.py)
MAX_MESSAGE_SIZE = 50 * 1024 * 1024  # 50MB


__all__ = [
    # Error codes
    "INVALID_FORMAT",
    "MISSING_FIELDS",
    "INVALID_VERSION",
    "INVALID_SIGNATURE",
    "REPLAY_DETECTED",
    "UNKNOWN_SENDER",
    "SESSION_EXPIRED",
    "SEQUENCE_ERROR",
    "DECRYPTION_FAILED",
    # Classes
    "MessageType",
    "ProtocolError",
    # Version constants
    "PROTOCOL_VERSION_1_0",
    "PROTOCOL_VERSION_1_1",
    "DEFAULT_PROTOCOL_VERSION",
    # Timing constants
    "TIMESTAMP_TOLERANCE_SECONDS",
    "JWT_EXPIRY_MINUTES",
    "REPLAY_WINDOW_SECONDS",
    # Crypto constants
    "NONCE_SIZE_BYTES",
    "AES_KEY_SIZE_BYTES",
    # Chunking constants
    "DEFAULT_CHUNK_SIZE",
    "CHUNK_SIZE_32K",
    "MAX_MESSAGE_SIZE",
]
