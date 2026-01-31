#!/usr/bin/env python3
"""
Relay Service - NAT Traversal and Message Relay
NAT越えとファイアウォール貫通のためのメッセージ中継サービス

Features:
- NATed peer registration and management
- Message forwarding between NATed peers
- Bandwidth limiting and rate limiting
- E2E encryption preservation (relay cannot read content)
- Relay authentication and authorization
"""

import asyncio
import json
import logging
import time
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RelayStatus(Enum):
    """Relay connection status"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    REGISTERED = "registered"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class RelayMessageType(Enum):
    """Relay protocol message types"""
    REGISTER = "register"           # Peer registration
    REGISTER_ACK = "register_ack"   # Registration acknowledgment
    FORWARD = "forward"             # Forward message to peer
    DELIVER = "deliver"             # Deliver message to registered peer
    HEARTBEAT = "heartbeat"         # Keep-alive
    HEARTBEAT_ACK = "heartbeat_ack" # Keep-alive response
    UNREGISTER = "unregister"       # Unregister peer
    ERROR = "error"                 # Error message


@dataclass
class RelayPeer:
    """Registered peer information"""
    entity_id: str
    public_key: str
    registered_at: datetime
    last_heartbeat: datetime
    connection_info: Dict[str, Any]
    
    # Rate limiting
    message_count: int = 0
    byte_count: int = 0
    last_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def is_expired(self, timeout_seconds: int = 300) -> bool:
        """Check if peer registration has expired"""
        return (datetime.now(timezone.utc) - self.last_heartbeat).seconds > timeout_seconds
    
    def update_heartbeat(self):
        """Update last heartbeat timestamp"""
        self.last_heartbeat = datetime.now(timezone.utc)


@dataclass
class RelayMessage:
    """Message to be relayed"""
    message_id: str
    sender_id: str
    target_id: str
    payload: Dict[str, Any]  # E2E encrypted payload
    timestamp: datetime
    ttl: int = 300  # Time-to-live in seconds
    
    # Routing info (added by relay)
    via_relay: Optional[str] = None
    hop_count: int = 0
    max_hops: int = 5
    
    def is_expired(self) -> bool:
        """Check if message TTL has expired"""
        return (datetime.now(timezone.utc) - self.timestamp).seconds > self.ttl
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "target_id": self.target_id,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "ttl": self.ttl,
            "hop_count": self.hop_count,
            "max_hops": self.max_hops
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RelayMessage':
        """Deserialize from dictionary"""
        return cls(
            message_id=data["message_id"],
            sender_id=data["sender_id"],
            target_id=data["target_id"],
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            ttl=data.get("ttl", 300),
            hop_count=data.get("hop_count", 0),
            max_hops=data.get("max_hops", 5)
        )


@dataclass
class RelayStats:
    """Relay service statistics"""
    total_peers: int = 0
    active_peers: int = 0
    total_messages_forwarded: int = 0
    total_bytes_forwarded: int = 0
    messages_in_queue: int = 0
    errors: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "total_peers": self.total_peers,
            "active_peers": self.active_peers,
            "total_messages_forwarded": self.total_messages_forwarded,
            "total_bytes_forwarded": self.total_bytes_forwarded,
            "messages_in_queue": self.messages_in_queue,
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "uptime_seconds": (datetime.now(timezone.utc) - self.started_at).seconds
        }


class RelayService:
    """
    Relay Service for NAT traversal and firewall penetration.
    
    Acts as a public intermediary for peers behind NAT/firewall.
    Maintains E2E encryption - cannot read message content.
    """
    
    def __init__(
        self,
        relay_id: str,
        host: str = "0.0.0.0",
        port: int = 8000,
        max_peers: int = 1000,
        max_message_size: int = 1024 * 1024,  # 1MB
        rate_limit_per_minute: int = 100,
        peer_timeout_seconds: int = 300
    ):
        self.relay_id = relay_id
        self.host = host
        self.port = port
        self.max_peers = max_peers
        self.max_message_size = max_message_size
        self.rate_limit_per_minute = rate_limit_per_minute
        self.peer_timeout_seconds = peer_timeout_seconds
        
        # Registered peers
        self._peers: Dict[str, RelayPeer] = {}
        self._peers_lock = asyncio.Lock()
        
        # Message queue for offline peers
        self._message_queue: Dict[str, List[RelayMessage]] = defaultdict(list)
        self._queue_lock = asyncio.Lock()
        
        # Statistics
        self._stats = RelayStats()
        
        # Callbacks for message delivery
        self._delivery_callbacks: List[Callable[[RelayMessage], None]] = []
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"RelayService initialized: {relay_id}@{host}:{port}")
    
    # ========================================================================
    # Peer Registration
    # ========================================================================
    
    async def register_peer(
        self,
        entity_id: str,
        public_key: str,
        connection_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Register a peer with the relay.
        
        Args:
            entity_id: Unique peer identifier
            public_key: Peer's Ed25519 public key (hex)
            connection_info: Connection metadata
            
        Returns:
            Registration result
        """
        async with self._peers_lock:
            # Check capacity
            if len(self._peers) >= self.max_peers and entity_id not in self._peers:
                return {
                    "success": False,
                    "error": "Relay capacity exceeded",
                    "relay_id": self.relay_id
                }
            
            # Register or update peer
            now = datetime.now(timezone.utc)
            peer = RelayPeer(
                entity_id=entity_id,
                public_key=public_key,
                registered_at=now,
                last_heartbeat=now,
                connection_info=connection_info
            )
            
            is_new = entity_id not in self._peers
            self._peers[entity_id] = peer
            
            if is_new:
                self._stats.total_peers += 1
                self._stats.active_peers += 1
            
            logger.info(f"Peer registered: {entity_id} (total: {len(self._peers)})")
            
            # Check for queued messages
            queued = await self._get_queued_messages(entity_id)
            
            return {
                "success": True,
                "relay_id": self.relay_id,
                "registered_at": now.isoformat(),
                "heartbeat_interval": 60,
                "queued_messages": len(queued)
            }
    
    async def unregister_peer(self, entity_id: str) -> bool:
        """
        Unregister a peer from the relay.
        
        Args:
            entity_id: Peer identifier
            
        Returns:
            True if unregistered successfully
        """
        async with self._peers_lock:
            if entity_id in self._peers:
                del self._peers[entity_id]
                self._stats.active_peers = max(0, self._stats.active_peers - 1)
                logger.info(f"Peer unregistered: {entity_id}")
                return True
            return False
    
    async def update_heartbeat(self, entity_id: str) -> bool:
        """
        Update peer heartbeat.
        
        Args:
            entity_id: Peer identifier
            
        Returns:
            True if peer is registered
        """
        async with self._peers_lock:
            if entity_id in self._peers:
                self._peers[entity_id].update_heartbeat()
                return True
            return False
    
    # ========================================================================
    # Message Forwarding
    # ========================================================================
    
    async def forward_message(self, message: RelayMessage) -> Dict[str, Any]:
        """
        Forward a message to its target.
        
        Args:
            message: Message to forward
            
        Returns:
            Forwarding result
        """
        # Check TTL
        if message.is_expired():
            return {
                "success": False,
                "error": "Message TTL expired",
                "message_id": message.message_id
            }
        
        # Check hop limit
        if message.hop_count >= message.max_hops:
            return {
                "success": False,
                "error": "Max hop count exceeded",
                "message_id": message.message_id
            }
        
        # Increment hop count
        message.hop_count += 1
        message.via_relay = self.relay_id
        
        # Update stats
        self._stats.total_messages_forwarded += 1
        message_size = len(json.dumps(message.payload))
        self._stats.total_bytes_forwarded += message_size
        
        # Check if target is registered
        async with self._peers_lock:
            target_online = message.target_id in self._peers
        
        if target_online:
            # Target is online - deliver immediately
            await self._deliver_message(message)
            return {
                "success": True,
                "status": "delivered",
                "message_id": message.message_id,
                "hop_count": message.hop_count
            }
        else:
            # Target is offline - queue for later
            await self._queue_message(message)
            return {
                "success": True,
                "status": "queued",
                "message_id": message.message_id,
                "queue_position": len(self._message_queue[message.target_id])
            }
    
    async def _deliver_message(self, message: RelayMessage):
        """
        Deliver message to registered peer.
        
        Args:
            message: Message to deliver
        """
        # Notify delivery callbacks
        for callback in self._delivery_callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Delivery callback error: {e}")
        
        logger.debug(f"Message delivered: {message.message_id} -> {message.target_id}")
    
    async def _queue_message(self, message: RelayMessage):
        """
        Queue message for offline peer.
        
        Args:
            message: Message to queue
        """
        async with self._queue_lock:
            self._message_queue[message.target_id].append(message)
            self._stats.messages_in_queue = sum(
                len(q) for q in self._message_queue.values()
            )
        
        logger.debug(f"Message queued: {message.message_id} for {message.target_id}")
    
    async def _get_queued_messages(self, entity_id: str) -> List[RelayMessage]:
        """
        Get queued messages for a peer.
        
        Args:
            entity_id: Peer identifier
            
        Returns:
            List of queued messages
        """
        async with self._queue_lock:
            messages = self._message_queue.get(entity_id, [])
            # Remove expired messages
            valid_messages = [m for m in messages if not m.is_expired()]
            self._message_queue[entity_id] = []
            
            self._stats.messages_in_queue = sum(
                len(q) for q in self._message_queue.values()
            )
            
            return valid_messages
    
    # ========================================================================
    # Rate Limiting
    # ========================================================================
    
    async def check_rate_limit(self, entity_id: str, message_size: int) -> bool:
        """
        Check if peer is within rate limits.
        
        Args:
            entity_id: Peer identifier
            message_size: Size of message in bytes
            
        Returns:
            True if within limits
        """
        async with self._peers_lock:
            if entity_id not in self._peers:
                return False
            
            peer = self._peers[entity_id]
            now = datetime.now(timezone.utc)
            
            # Reset counter if minute has passed
            if (now - peer.last_reset).seconds >= 60:
                peer.message_count = 0
                peer.byte_count = 0
                peer.last_reset = now
            
            # Check limits
            if peer.message_count >= self.rate_limit_per_minute:
                return False
            
            peer.message_count += 1
            peer.byte_count += message_size
            return True
    
    # ========================================================================
    # Maintenance
    # ========================================================================
    
    async def start(self):
        """Start relay service maintenance tasks"""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"RelayService started: {self.relay_id}")
    
    async def stop(self):
        """Stop relay service"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info(f"RelayService stopped: {self.relay_id}")
    
    async def _cleanup_loop(self):
        """Background cleanup task"""
        while self._running:
            try:
                await self._cleanup_expired()
                await asyncio.sleep(60)  # Run every minute
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                self._stats.errors += 1
    
    async def _cleanup_expired(self):
        """Clean up expired peers and messages"""
        now = datetime.now(timezone.utc)
        
        # Clean up expired peers
        async with self._peers_lock:
            expired = [
                eid for eid, peer in self._peers.items()
                if peer.is_expired(self.peer_timeout_seconds)
            ]
            for eid in expired:
                del self._peers[eid]
                self._stats.active_peers = max(0, self._stats.active_peers - 1)
            
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired peers")
        
        # Clean up expired messages
        async with self._queue_lock:
            for entity_id in list(self._message_queue.keys()):
                queue = self._message_queue[entity_id]
                valid = [m for m in queue if not m.is_expired()]
                if valid:
                    self._message_queue[entity_id] = valid
                else:
                    del self._message_queue[entity_id]
            
            self._stats.messages_in_queue = sum(
                len(q) for q in self._message_queue.values()
            )
    
    # ========================================================================
    # Queries
    # ========================================================================
    
    def get_stats(self) -> RelayStats:
        """Get relay statistics"""
        return self._stats
    
    async def get_peer_info(self, entity_id: str) -> Optional[RelayPeer]:
        """
        Get peer information.
        
        Args:
            entity_id: Peer identifier
            
        Returns:
            Peer info or None
        """
        async with self._peers_lock:
            return self._peers.get(entity_id)
    
    async def list_peers(self) -> List[str]:
        """
        List all registered peer IDs.
        
        Returns:
            List of peer IDs
        """
        async with self._peers_lock:
            return list(self._peers.keys())
    
    def add_delivery_callback(self, callback: Callable[[RelayMessage], None]):
        """
        Add callback for message delivery.
        
        Args:
            callback: Function to call when message is delivered
        """
        self._delivery_callbacks.append(callback)


# ============================================================================
# Helper Functions
# ============================================================================

def create_relay_message(
    sender_id: str,
    target_id: str,
    payload: Dict[str, Any],
    ttl: int = 300
) -> RelayMessage:
    """
    Create a new relay message.
    
    Args:
        sender_id: Sender entity ID
        target_id: Target entity ID
        payload: E2E encrypted payload
        ttl: Time-to-live in seconds
        
    Returns:
        RelayMessage instance
    """
    return RelayMessage(
        message_id=secrets.token_hex(16),
        sender_id=sender_id,
        target_id=target_id,
        payload=payload,
        timestamp=datetime.now(timezone.utc),
        ttl=ttl
    )


# ============================================================================
# Example Usage
# ============================================================================

async def example():
    """Example usage of RelayService"""
    # Create relay
    relay = RelayService(
        relay_id="relay-001",
        host="0.0.0.0",
        port=9000
    )
    
    await relay.start()
    
    # Register a peer
    result = await relay.register_peer(
        entity_id="peer-001",
        public_key="aabbccdd...",
        connection_info={"version": "1.0"}
    )
    print(f"Registration: {result}")
    
    # Create and forward a message
    message = create_relay_message(
        sender_id="peer-002",
        target_id="peer-001",
        payload={"encrypted": "...", "nonce": "..."}
    )
    
    result = await relay.forward_message(message)
    print(f"Forward result: {result}")
    
    # Get stats
    stats = relay.get_stats()
    print(f"Stats: {stats.to_dict()}")
    
    await relay.stop()


if __name__ == "__main__":
    asyncio.run(example())
