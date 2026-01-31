#!/usr/bin/env python3
"""
Chunked Message Transfer for Peer Protocol v1.1
Handles large message fragmentation and reassembly
"""

import hashlib
import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, Awaitable
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)


class ChunkStatus(Enum):
    """Status of a chunked transfer"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class MessageChunk:
    """Single chunk of a fragmented message"""
    transfer_id: str
    chunk_index: int
    total_chunks: int
    data: bytes
    checksum: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for transmission"""
        return {
            "transfer_id": self.transfer_id,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "data": base64.b64encode(self.data).decode('utf-8'),
            "checksum": self.checksum
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageChunk":
        """Create from dictionary"""
        return cls(
            transfer_id=data["transfer_id"],
            chunk_index=data["chunk_index"],
            total_chunks=data["total_chunks"],
            data=base64.b64decode(data["data"]),
            checksum=data["checksum"]
        )
    
    def verify_checksum(self) -> bool:
        """Verify chunk data integrity"""
        computed = hashlib.sha256(self.data).hexdigest()[:32]
        return computed == self.checksum


@dataclass
class ChunkedTransfer:
    """Complete chunked transfer state"""
    transfer_id: str
    sender_id: str
    recipient_id: str
    msg_type: str
    total_chunks: int
    chunks: Dict[int, MessageChunk] = field(default_factory=dict)
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: ChunkStatus = ChunkStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_complete(self) -> bool:
        """Check if all chunks received"""
        return len(self.chunks) == self.total_chunks
    
    def get_progress(self) -> float:
        """Get transfer progress (0.0 - 1.0)"""
        if self.total_chunks == 0:
            return 0.0
        return len(self.chunks) / self.total_chunks
    
    def assemble_message(self) -> Optional[Dict[str, Any]]:
        """Assemble chunks into complete message"""
        if not self.is_complete():
            return None
        
        # Sort chunks by index
        sorted_chunks = [self.chunks[i] for i in range(self.total_chunks)]
        
        # Concatenate data
        full_data = b''.join(chunk.data for chunk in sorted_chunks)
        
        # Memory limit check (50MB)
        MAX_MESSAGE_SIZE = 50 * 1024 * 1024  # 50MB
        if len(full_data) > MAX_MESSAGE_SIZE:
            logger.error(f"Message size {len(full_data)} exceeds maximum {MAX_MESSAGE_SIZE} bytes")
            return None
        
        try:
            # Parse JSON
            message = json.loads(full_data.decode('utf-8'))
            return message
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to assemble message: {e}")
            return None


class ChunkedTransferManager:
    """
    Manager for chunked message transfers
    - Handles fragmentation of large messages
    - Manages reassembly on receive
    - Automatic cleanup of expired transfers
    """
    
    DEFAULT_CHUNK_SIZE = 32768  # 32KB per chunk
    DEFAULT_MAX_TRANSFER_SIZE = 10485760  # 10MB max
    DEFAULT_EXPIRY_MINUTES = 30
    
    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_transfer_size: int = DEFAULT_MAX_TRANSFER_SIZE,
        expiry_minutes: int = DEFAULT_EXPIRY_MINUTES
    ):
        self.chunk_size = chunk_size
        self.max_transfer_size = max_transfer_size
        self.expiry_minutes = expiry_minutes
        
        # Active transfers (transfer_id -> ChunkedTransfer)
        self._transfers: Dict[str, ChunkedTransfer] = {}
        
        # Callbacks for transfer completion
        self._completion_callbacks: Dict[str, Callable[[str, Dict[str, Any]], Awaitable[None]]] = {}
        
        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    def start(self):
        """Start background cleanup task"""
        if not self._running:
            self._running = True
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("ChunkedTransferManager started")
    
    def stop(self):
        """Stop background cleanup task"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            logger.info("ChunkedTransferManager stopped")
    
    async def _cleanup_loop(self):
        """Periodic cleanup of expired transfers"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    def _cleanup_expired(self):
        """Remove expired transfers"""
        now = datetime.now(timezone.utc)
        expired = []
        
        for transfer_id, transfer in self._transfers.items():
            age_minutes = (now - transfer.received_at).total_seconds() / 60
            if age_minutes > self.expiry_minutes:
                expired.append(transfer_id)
        
        for transfer_id in expired:
            transfer = self._transfers.pop(transfer_id, None)
            if transfer:
                transfer.status = ChunkStatus.EXPIRED
                logger.debug(f"Cleaned up expired transfer: {transfer_id}")
    
    def create_transfer(
        self,
        sender_id: str,
        recipient_id: str,
        msg_type: str,
        message: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[MessageChunk]:
        """
        Create a chunked transfer from a message
        
        Args:
            sender_id: Sender entity ID
            recipient_id: Recipient entity ID
            msg_type: Message type
            message: Message to fragment
            metadata: Optional metadata
            
        Returns:
            List of message chunks
            
        Raises:
            ValueError: If message too large
        """
        # Serialize message
        message_json = json.dumps(message, separators=(',', ':')).encode('utf-8')
        
        if len(message_json) > self.max_transfer_size:
            raise ValueError(
                f"Message size {len(message_json)} exceeds maximum {self.max_transfer_size}"
            )
        
        # Generate transfer ID
        transfer_id = hashlib.sha256(
            f"{sender_id}:{recipient_id}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:32]
        
        # Calculate chunks needed
        total_chunks = (len(message_json) + self.chunk_size - 1) // self.chunk_size
        
        # Create transfer state first (transaction safety)
        transfer = ChunkedTransfer(
            transfer_id=transfer_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            msg_type=msg_type,
            total_chunks=total_chunks,
            metadata=metadata or {}
        )
        self._transfers[transfer_id] = transfer
        
        # Create chunks
        chunks = []
        for i in range(total_chunks):
            start = i * self.chunk_size
            end = min(start + self.chunk_size, len(message_json))
            chunk_data = message_json[start:end]
            
            chunk = MessageChunk(
                transfer_id=transfer_id,
                chunk_index=i,
                total_chunks=total_chunks,
                data=chunk_data,
                checksum=hashlib.sha256(chunk_data).hexdigest()[:32]
            )
            chunks.append(chunk)
        
        return chunks
    
    def receive_chunk(self, chunk: MessageChunk) -> Optional[ChunkedTransfer]:
        """
        Receive a chunk and update transfer state
        
        Args:
            chunk: Received chunk
            
        Returns:
            Updated ChunkedTransfer or None if invalid
        """
        # Verify chunk checksum
        if not chunk.verify_checksum():
            logger.warning(f"Chunk checksum failed: {chunk.transfer_id}:{chunk.chunk_index}")
            return None
        
        # Get or create transfer
        transfer = self._transfers.get(chunk.transfer_id)
        
        if transfer is None:
            # New transfer - auto-initialize with metadata from first chunk if available
            logger.warning(
                f"Received chunk for unknown transfer: {chunk.transfer_id}. "
                f"Transfer must be initialized before receiving chunks. "
                f"Call initialize_transfer() with transfer metadata first."
            )
            return None
        
        # Add chunk if not already received
        if chunk.chunk_index not in transfer.chunks:
            transfer.chunks[chunk.chunk_index] = chunk
            logger.debug(
                f"Received chunk {chunk.chunk_index + 1}/{chunk.total_chunks} "
                f"for {chunk.transfer_id}"
            )
        
        # Update status
        if transfer.is_complete():
            transfer.status = ChunkStatus.COMPLETED
        else:
            transfer.status = ChunkStatus.IN_PROGRESS
        
        return transfer
    
    def initialize_transfer(
        self,
        transfer_id: str,
        sender_id: str,
        recipient_id: str,
        msg_type: str,
        total_chunks: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChunkedTransfer:
        """
        Initialize a new incoming transfer
        
        Args:
            transfer_id: Transfer ID
            sender_id: Sender entity ID
            recipient_id: Recipient entity ID
            msg_type: Message type
            total_chunks: Expected total chunks
            metadata: Optional metadata
            
        Returns:
            Created ChunkedTransfer
        """
        transfer = ChunkedTransfer(
            transfer_id=transfer_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            msg_type=msg_type,
            total_chunks=total_chunks,
            metadata=metadata or {}
        )
        
        self._transfers[transfer_id] = transfer
        return transfer
    
    def get_transfer(self, transfer_id: str) -> Optional[ChunkedTransfer]:
        """Get transfer by ID"""
        return self._transfers.get(transfer_id)
    
    def register_completion_callback(
        self,
        transfer_id: str,
        callback: Callable[[str, Dict[str, Any]], Awaitable[None]]
    ):
        """Register callback for transfer completion"""
        self._completion_callbacks[transfer_id] = callback
    
    async def handle_completed_transfer(self, transfer: ChunkedTransfer):
        """Handle completed transfer - call callback and cleanup"""
        message = transfer.assemble_message()
        if message:
            callback = self._completion_callbacks.get(transfer.transfer_id)
            if callback:
                try:
                    await callback(transfer.transfer_id, message)
                except Exception as e:
                    logger.error(f"Completion callback failed: {e}")
        
        # Cleanup
        self._completion_callbacks.pop(transfer.transfer_id, None)
        # Keep transfer in _transfers for potential reassembly queries
    
    def get_stats(self) -> Dict[str, Any]:
        """Get transfer statistics"""
        return {
            "active_transfers": len(self._transfers),
            "by_status": {
                status.value: sum(
                    1 for t in self._transfers.values() if t.status == status
                )
                for status in ChunkStatus
            },
            "chunk_size": self.chunk_size,
            "max_transfer_size": self.max_transfer_size,
            "expiry_minutes": self.expiry_minutes
        }


class ChunkedMessageProtocol:
    """
    Protocol handler for chunked messages
    Integrates with PeerService for send/receive
    """
    
    def __init__(self, transfer_manager: ChunkedTransferManager):
        self.transfer_manager = transfer_manager
    
    def create_chunk_message(
        self,
        chunk: MessageChunk,
        sender_id: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a protocol message for a chunk
        
        Args:
            chunk: The chunk to send
            sender_id: Sender entity ID
            session_id: Optional session ID
            
        Returns:
            Protocol message dictionary
        """
        return {
            "version": "1.1",
            "msg_type": "chunk",
            "sender_id": sender_id,
            "payload": {
                "chunk": chunk.to_dict(),
                "progress": f"{chunk.chunk_index + 1}/{chunk.total_chunks}"
            },
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def parse_chunk_message(self, message: Dict[str, Any]) -> Optional[MessageChunk]:
        """
        Parse a chunk from a protocol message
        
        Args:
            message: Protocol message
            
        Returns:
            MessageChunk or None if invalid
        """
        payload = message.get("payload", {})
        chunk_data = payload.get("chunk")
        
        if not chunk_data:
            return None
        
        try:
            return MessageChunk.from_dict(chunk_data)
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse chunk: {e}")
            return None
    
    def create_transfer_init_message(
        self,
        transfer_id: str,
        sender_id: str,
        recipient_id: str,
        msg_type: str,
        total_chunks: int,
        total_size: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a transfer initialization message
        
        Args:
            transfer_id: Transfer ID
            sender_id: Sender entity ID
            recipient_id: Recipient entity ID
            msg_type: Original message type
            total_chunks: Total number of chunks
            total_size: Total message size in bytes
            metadata: Optional metadata
            
        Returns:
            Protocol message
        """
        return {
            "version": "1.1",
            "msg_type": "chunk_init",
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "payload": {
                "transfer_id": transfer_id,
                "msg_type": msg_type,
                "total_chunks": total_chunks,
                "total_size": total_size,
                "metadata": metadata or {}
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# Convenience function for quick chunking
def chunk_message(
    message: Dict[str, Any],
    sender_id: str,
    recipient_id: str,
    msg_type: str,
    chunk_size: int = 32768
) -> List[Dict[str, Any]]:
    """
    Quick function to chunk a message into protocol messages
    
    Args:
        message: Message to chunk
        sender_id: Sender entity ID
        recipient_id: Recipient entity ID
        msg_type: Message type
        chunk_size: Chunk size in bytes
        
    Returns:
        List of protocol messages ready to send
    """
    manager = ChunkedTransferManager(chunk_size=chunk_size)
    
    chunks = manager.create_transfer(
        sender_id=sender_id,
        recipient_id=recipient_id,
        msg_type=msg_type,
        message=message
    )
    
    protocol = ChunkedMessageProtocol(manager)
    
    messages = []
    for chunk in chunks:
        msg = protocol.create_chunk_message(chunk, sender_id)
        messages.append(msg)
    
    return messages


if __name__ == "__main__":
    # Test chunked transfer
    print("=" * 60)
    print("Chunked Transfer Test")
    print("=" * 60)
    
    # Create test message
    test_message = {
        "type": "large_data",
        "data": "x" * 100000,  # 100KB of data
        "metadata": {"test": True}
    }
    
    # Create transfer
    manager = ChunkedTransferManager(chunk_size=32768)
    
    chunks = manager.create_transfer(
        sender_id="entity-a",
        recipient_id="entity-b",
        msg_type="test",
        message=test_message
    )
    
    print(f"\nMessage size: {len(json.dumps(test_message))} bytes")
    print(f"Chunk size: {manager.chunk_size} bytes")
    print(f"Total chunks: {len(chunks)}")
    
    # Simulate receiving
    transfer_id = chunks[0].transfer_id
    
    manager.initialize_transfer(
        transfer_id=transfer_id,
        sender_id="entity-a",
        recipient_id="entity-b",
        msg_type="test",
        total_chunks=len(chunks)
    )
    
    # Receive chunks in random order
    import random
    shuffled = chunks.copy()
    random.shuffle(shuffled)
    
    for chunk in shuffled:
        transfer = manager.receive_chunk(chunk)
        print(f"Received chunk {chunk.chunk_index}: progress {transfer.get_progress():.1%}")
    
    # Assemble
    final_transfer = manager.get_transfer(transfer_id)
    assembled = final_transfer.assemble_message()
    
    if assembled == test_message:
        print("\n[PASS] Message reassembled correctly!")
    else:
        print("\n[FAIL] Message mismatch!")
    
    print(f"\nStats: {manager.get_stats()}")
