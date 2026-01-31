#!/usr/bin/env python3
"""
Binary Protocol (CBOR) for AI Collaboration Network
CBORベースバイナリプロトコル

Features:
- Efficient binary serialization
- Smaller message sizes than JSON
- Fast encoding/decoding
- Schema versioning
"""

import struct
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Union, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import cbor2, fallback to JSON
try:
    import cbor2
    CBOR_AVAILABLE = True
except ImportError:
    CBOR_AVAILABLE = False
    logger.warning("cbor2 not available, using JSON fallback")


class MessageType(Enum):
    """Binary protocol message types"""
    HEARTBEAT = 0x01
    HANDSHAKE = 0x02
    DATA = 0x03
    ACK = 0x04
    ERROR = 0x05
    DISCOVERY = 0x06
    TASK = 0x07
    CHAT = 0x08


class ProtocolVersion(Enum):
    """Protocol versions"""
    V1_0 = 0x10
    V1_1 = 0x11
    V1_2 = 0x12


@dataclass
class BinaryMessage:
    """Binary protocol message structure"""
    message_type: MessageType
    payload: Any
    version: ProtocolVersion = ProtocolVersion.V1_2
    message_id: Optional[str] = None
    sender_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    signature: Optional[bytes] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class CBORCodec:
    """
    CBOR encoder/decoder with schema support.
    
    Provides efficient binary serialization for network messages.
    """
    
    def __init__(self, use_compression: bool = True):
        self.use_compression = use_compression and CBOR_AVAILABLE
        self._encode_count = 0
        self._decode_count = 0
        self._bytes_saved = 0
        
    def encode(self, message: BinaryMessage) -> bytes:
        """Encode message to CBOR bytes"""
        # Build message structure
        msg_struct = {
            "v": message.version.value,
            "t": message.message_type.value,
            "p": message.payload,
            "ts": message.timestamp.isoformat() if message.timestamp else None,
        }
        
        if message.message_id:
            msg_struct["id"] = message.message_id
        if message.sender_id:
            msg_struct["s"] = message.sender_id
        if message.signature:
            msg_struct["sig"] = message.signature
        
        if self.use_compression:
            encoded = cbor2.dumps(msg_struct)
        else:
            import json
            encoded = json.dumps(msg_struct).encode("utf-8")
        
        # Add header with length
        header = struct.pack("!I", len(encoded))
        result = header + encoded
        
        self._encode_count += 1
        return result
    
    def decode(self, data: bytes) -> Optional[BinaryMessage]:
        """Decode CBOR bytes to message"""
        if len(data) < 4:
            return None
        
        # Read header
        msg_len = struct.unpack("!I", data[:4])[0]
        
        if len(data) < 4 + msg_len:
            return None
        
        encoded = data[4:4+msg_len]
        
        try:
            if self.use_compression:
                msg_struct = cbor2.loads(encoded)
            else:
                import json
                msg_struct = json.loads(encoded.decode("utf-8"))
            
            self._decode_count += 1
            
            return BinaryMessage(
                version=ProtocolVersion(msg_struct.get("v", 0x12)),
                message_type=MessageType(msg_struct["t"]),
                payload=msg_struct["p"],
                message_id=msg_struct.get("id"),
                sender_id=msg_struct.get("s"),
                timestamp=datetime.fromisoformat(msg_struct["ts"]) if msg_struct.get("ts") else None,
                signature=msg_struct.get("sig")
            )
            
        except Exception as e:
            logger.error(f"Decode error: {e}")
            return None
    
    def compare_size(self, message: BinaryMessage) -> Dict[str, int]:
        """Compare CBOR vs JSON size"""
        import json
        
        # CBOR size
        cbor_bytes = self.encode(message)
        cbor_size = len(cbor_bytes)
        
        # JSON size
        json_struct = {
            "version": message.version.name,
            "type": message.message_type.name,
            "payload": message.payload,
            "timestamp": message.timestamp.isoformat() if message.timestamp else None,
            "message_id": message.message_id,
            "sender_id": message.sender_id
        }
        json_bytes = json.dumps(json_struct).encode("utf-8")
        json_size = len(json_bytes)
        
        return {
            "cbor": cbor_size,
            "json": json_size,
            "savings": json_size - cbor_size,
            "savings_percent": round((json_size - cbor_size) / json_size * 100, 1)
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get codec statistics"""
        return {
            "encode_count": self._encode_count,
            "decode_count": self._decode_count,
            "cbor_available": CBOR_AVAILABLE,
            "compression_enabled": self.use_compression
        }


class BinaryProtocolHandler:
    """
    High-level binary protocol handler.
    
    Manages message framing, encoding, and type routing.
    """
    
    def __init__(self):
        self.codec = CBORCodec()
        self._handlers: Dict[MessageType, Any] = {}
        self._buffer = b""
        
    def register_handler(self, msg_type: MessageType, handler: callable):
        """Register handler for message type"""
        self._handlers[msg_type] = handler
        
    def encode_message(
        self,
        msg_type: MessageType,
        payload: Any,
        sender_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> bytes:
        """Encode message for sending"""
        message = BinaryMessage(
            message_type=msg_type,
            payload=payload,
            sender_id=sender_id,
            message_id=message_id
        )
        return self.codec.encode(message)
    
    def feed_data(self, data: bytes) -> List[BinaryMessage]:
        """
        Feed incoming data and extract complete messages.
        
        Returns list of decoded messages.
        """
        self._buffer += data
        messages = []
        
        while len(self._buffer) >= 4:
            # Read message length
            msg_len = struct.unpack("!I", self._buffer[:4])[0]
            
            # Check if complete message available
            if len(self._buffer) < 4 + msg_len:
                break
            
            # Extract and decode message
            msg_data = self._buffer[:4+msg_len]
            message = self.codec.decode(msg_data)
            
            if message:
                messages.append(message)
            
            # Remove processed bytes from buffer
            self._buffer = self._buffer[4+msg_len:]
        
        return messages
    
    async def process_message(self, message: BinaryMessage):
        """Process decoded message"""
        handler = self._handlers.get(message.message_type)
        if handler:
            await handler(message)
        else:
            logger.warning(f"No handler for message type: {message.message_type}")


# Message builders for common types
def build_heartbeat_payload(
    entity_id: str,
    timestamp: Optional[datetime] = None
) -> Dict[str, Any]:
    """Build heartbeat message payload"""
    return {
        "entity_id": entity_id,
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "type": "heartbeat"
    }


def build_handshake_payload(
    entity_id: str,
    public_key: Optional[bytes] = None,
    supported_versions: List[str] = None
) -> Dict[str, Any]:
    """Build handshake message payload"""
    return {
        "entity_id": entity_id,
        "public_key": public_key.hex() if public_key else None,
        "supported_versions": supported_versions or ["1.2"],
        "type": "handshake_request"
    }


def build_task_payload(
    task_id: str,
    task_type: str,
    parameters: Dict[str, Any],
    priority: int = 5
) -> Dict[str, Any]:
    """Build task message payload"""
    return {
        "task_id": task_id,
        "task_type": task_type,
        "parameters": parameters,
        "priority": priority,
        "created_at": datetime.now(timezone.utc).isoformat()
    }


# Convenience functions
def create_binary_protocol_handler() -> BinaryProtocolHandler:
    """Create binary protocol handler"""
    return BinaryProtocolHandler()


def encode_simple(
    msg_type: MessageType,
    payload: Any,
    sender_id: Optional[str] = None
) -> bytes:
    """Simple encoding without handler"""
    codec = CBORCodec()
    message = BinaryMessage(
        message_type=msg_type,
        payload=payload,
        sender_id=sender_id
    )
    return codec.encode(message)


# Version info
PROTOCOL_VERSION = "1.2.0"
CBOR_VERSION = cbor2.__version__ if CBOR_AVAILABLE else "N/A"
