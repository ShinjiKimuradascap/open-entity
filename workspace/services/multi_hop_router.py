#!/usr/bin/env python3
"""
Multi-Hop Message Router with Store-and-Forward
マルチホップメッセージルーター（ストアアンドフォワード対応）

Features:
- Store-and-forward message relay
- TTL-based loop prevention
- Path tracking and validation
- Persistent message queue
- Delivery confirmation
"""

import asyncio
import json
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set
from pathlib import Path
import aiohttp
from aiohttp import ClientTimeout

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessageStatus(Enum):
    """Message delivery status"""
    PENDING = "pending"           # Waiting to be sent
    FORWARDING = "forwarding"     # In transit
    DELIVERED = "delivered"       # Reached destination
    FAILED = "failed"             # Delivery failed
    EXPIRED = "expired"           # TTL expired


@dataclass
class RoutingEntry:
    """Routing table entry for multi-hop routing"""
    destination: str              # Final destination entity ID
    next_hop: str                 # Next hop entity ID
    metric: int                   # Path metric (latency in ms)
    hop_count: int                # Number of hops to destination
    path: List[str]               # Full path (for loop detection)
    last_updated: datetime
    is_direct: bool = False       # Direct connection available


@dataclass
class QueuedMessage:
    """Message in store-and-forward queue"""
    message_id: str
    original_sender: str
    final_destination: str
    payload: Dict[str, Any]
    
    # Routing info
    path: List[str]               # Path taken so far
    hop_count: int
    max_hops: int
    ttl: int                      # Time-to-live in seconds
    
    # Timing
    created_at: datetime
    expires_at: datetime
    last_attempt: Optional[datetime] = None
    
    # Status
    status: MessageStatus = MessageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    
    # Delivery confirmation
    delivery_confirmed: bool = False
    confirmation_received_at: Optional[datetime] = None
    
    def is_expired(self) -> bool:
        """Check if message TTL has expired"""
        return datetime.now(timezone.utc) > self.expires_at
    
    def should_retry(self) -> bool:
        """Check if message should be retried"""
        if self.status == MessageStatus.DELIVERED:
            return False
        if self.retry_count >= self.max_retries:
            return False
        if self.is_expired():
            return False
        return True


class MultiHopRouter:
    """
    Multi-hop message router with store-and-forward capability.
    
    Enables messages to traverse multiple intermediate nodes
    to reach destinations that are not directly connected.
    """
    
    def __init__(
        self,
        entity_id: str,
        storage_path: Optional[str] = None,
        max_queue_size: int = 1000,
        default_ttl: int = 3600
    ):
        self.entity_id = entity_id
        self.storage_path = Path(storage_path) if storage_path else None
        self.max_queue_size = max_queue_size
        self.default_ttl = default_ttl
        
        # Routing table: destination -> RoutingEntry
        self._routing_table: Dict[str, RoutingEntry] = {}
        
        # Message queue: message_id -> QueuedMessage
        self._message_queue: Dict[str, QueuedMessage] = {}
        
        # Forwarded messages (for deduplication): message_id -> timestamp
        self._forwarded_messages: Dict[str, datetime] = {}
        
        # Callbacks for different message types
        self._message_handlers: Dict[str, Callable] = {}
        
        # HTTP session for forwarding
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Background tasks
        self._forward_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Statistics
        self._stats = {
            "messages_forwarded": 0,
            "messages_delivered": 0,
            "messages_failed": 0,
            "messages_expired": 0,
        }
        
        # Load persisted messages
        if self.storage_path:
            self._load_queue()
        
        logger.info(f"MultiHopRouter initialized for {entity_id}")
    
    async def start(self) -> None:
        """Start the router"""
        # Create HTTP session with keepalive
        timeout = ClientTimeout(total=30, connect=10)
        self._session = aiohttp.ClientSession(timeout=timeout)
        
        # Start background tasks
        self._forward_task = asyncio.create_task(self._forward_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("MultiHopRouter started")
    
    async def stop(self) -> None:
        """Stop the router"""
        # Cancel background tasks
        if self._forward_task:
            self._forward_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # Close HTTP session
        if self._session:
            await self._session.close()
        
        # Persist queue
        if self.storage_path:
            self._save_queue()
        
        logger.info("MultiHopRouter stopped")
    
    def add_route(
        self,
        destination: str,
        next_hop: str,
        metric: int,
        path: List[str],
        is_direct: bool = False
    ) -> None:
        """
        Add a route to the routing table.
        
        Args:
            destination: Final destination entity ID
            next_hop: Next hop entity ID
            metric: Path metric (lower is better)
            path: Full path to destination
            is_direct: Whether this is a direct connection
        """
        entry = RoutingEntry(
            destination=destination,
            next_hop=next_hop,
            metric=metric,
            hop_count=len(path),
            path=path,
            last_updated=datetime.now(timezone.utc),
            is_direct=is_direct
        )
        
        # Only update if metric is better
        existing = self._routing_table.get(destination)
        if not existing or metric < existing.metric:
            self._routing_table[destination] = entry
            logger.debug(f"Added route to {destination} via {next_hop} (metric: {metric})")
    
    def remove_route(self, destination: str) -> None:
        """Remove a route from the routing table"""
        if destination in self._routing_table:
            del self._routing_table[destination]
            logger.debug(f"Removed route to {destination}")
    
    def get_route(self, destination: str) -> Optional[RoutingEntry]:
        """Get routing entry for a destination"""
        return self._routing_table.get(destination)
    
    async def send_message(
        self,
        destination: str,
        payload: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> Optional[str]:
        """
        Send a message to a destination (potentially multi-hop).
        
        Args:
            destination: Final destination entity ID
            payload: Message payload
            ttl: Time-to-live in seconds
        
        Returns:
            Message ID if queued, None if failed
        """
        # Check if we have a route
        route = self._routing_table.get(destination)
        if not route:
            logger.warning(f"No route to {destination}")
            return None
        
        # Create message
        message_id = self._generate_message_id(destination, payload)
        now = datetime.now(timezone.utc)
        
        message = QueuedMessage(
            message_id=message_id,
            original_sender=self.entity_id,
            final_destination=destination,
            payload=payload,
            path=[self.entity_id],
            hop_count=0,
            max_hops=10,
            ttl=ttl or self.default_ttl,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl or self.default_ttl)
        )
        
        # Check queue size
        if len(self._message_queue) >= self.max_queue_size:
            logger.error("Message queue full")
            return None
        
        # Add to queue
        self._message_queue[message_id] = message
        
        # Try immediate forward if direct route
        if route.is_direct:
            asyncio.create_task(self._forward_message(message_id))
        
        logger.info(f"Queued message {message_id} to {destination}")
        return message_id
    
    async def handle_incoming_message(
        self,
        sender: str,
        message_data: Dict[str, Any]
    ) -> bool:
        """
        Handle an incoming message (could be final destination or forward).
        
        Args:
            sender: Sender entity ID
            message_data: Message data including forward metadata
        
        Returns:
            True if message was handled
        """
        # Check if this is a forward message
        forward_info = message_data.get("forward")
        if not forward_info:
            # Direct message, not our concern
            return False
        
        message_id = message_data.get("message_id")
        
        # Deduplication check
        if message_id in self._forwarded_messages:
            logger.debug(f"Duplicate message {message_id}, dropping")
            return True
        
        # Loop detection
        path = forward_info.get("path", [])
        if self.entity_id in path:
            logger.warning(f"Loop detected for message {message_id}, dropping")
            return True
        
        # Check TTL
        ttl = forward_info.get("ttl", self.default_ttl)
        if ttl <= 0:
            logger.warning(f"TTL expired for message {message_id}")
            return True
        
        # Check if we're the final destination
        final_destination = forward_info.get("final_destination")
        if final_destination == self.entity_id:
            # Deliver to local handler
            await self._deliver_message(message_data)
            return True
        
        # Forward to next hop
        hop_count = forward_info.get("hop_count", 0)
        max_hops = forward_info.get("max_hops", 10)
        
        if hop_count >= max_hops:
            logger.warning(f"Max hops reached for message {message_id}")
            return True
        
        # Get route to final destination
        route = self._routing_table.get(final_destination)
        if not route:
            logger.warning(f"No route to {final_destination} for message {message_id}")
            return True
        
        # Queue for forwarding
        message = QueuedMessage(
            message_id=message_id,
            original_sender=forward_info.get("original_sender", sender),
            final_destination=final_destination,
            payload=message_data.get("payload", {}),
            path=path + [self.entity_id],
            hop_count=hop_count + 1,
            max_hops=max_hops,
            ttl=ttl - 1,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl - 1)
        )
        
        self._message_queue[message_id] = message
        self._forwarded_messages[message_id] = datetime.now(timezone.utc)
        
        # Trigger forward
        asyncio.create_task(self._forward_message(message_id))
        
        return True
    
    async def _forward_message(self, message_id: str) -> bool:
        """
        Forward a queued message to the next hop.
        
        Args:
            message_id: Message ID to forward
        
        Returns:
            True if forwarded successfully
        """
        message = self._message_queue.get(message_id)
        if not message:
            return False
        
        if message.is_expired():
            message.status = MessageStatus.EXPIRED
            self._stats["messages_expired"] += 1
            return False
        
        # Get route
        route = self._routing_table.get(message.final_destination)
        if not route:
            message.status = MessageStatus.FAILED
            self._stats["messages_failed"] += 1
            return False
        
        # Build forward message
        forward_msg = {
            "message_id": message.message_id,
            "forward": {
                "original_sender": message.original_sender,
                "final_destination": message.final_destination,
                "path": message.path,
                "hop_count": message.hop_count,
                "max_hops": message.max_hops,
                "ttl": message.ttl
            },
            "payload": message.payload
        }
        
        # Send to next hop
        message.status = MessageStatus.FORWARDING
        message.last_attempt = datetime.now(timezone.utc)
        message.retry_count += 1
        
        try:
            success = await self._send_to_peer(route.next_hop, forward_msg)
            
            if success:
                if route.is_direct and route.destination == message.final_destination:
                    # Direct delivery
                    message.status = MessageStatus.DELIVERED
                    self._stats["messages_delivered"] += 1
                else:
                    # Forwarded to next hop
                    self._stats["messages_forwarded"] += 1
                
                logger.info(f"Forwarded message {message_id} to {route.next_hop}")
                return True
            else:
                if message.retry_count >= message.max_retries:
                    message.status = MessageStatus.FAILED
                    self._stats["messages_failed"] += 1
                return False
        
        except Exception as e:
            logger.error(f"Forward error for {message_id}: {e}")
            if message.retry_count >= message.max_retries:
                message.status = MessageStatus.FAILED
                self._stats["messages_failed"] += 1
            return False
    
    async def _send_to_peer(self, peer_id: str, message: Dict) -> bool:
        """
        Send a message to a peer via HTTP.
        
        Args:
            peer_id: Target peer ID
            message: Message to send
        
        Returns:
            True if sent successfully
        """
        # Get peer endpoint from routing table or registry
        # This is simplified - in production, resolve from distributed registry
        endpoint = f"http://localhost:8000/message"  # Placeholder
        
        try:
            async with self._session.post(
                endpoint,
                json=message,
                headers={"Content-Type": "application/json"}
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to send to {peer_id}: {e}")
            return False
    
    async def _deliver_message(self, message_data: Dict) -> None:
        """Deliver message to local handler"""
        payload = message_data.get("payload", {})
        msg_type = payload.get("type", "default")
        
        handler = self._message_handlers.get(msg_type)
        if handler:
            try:
                await handler(payload)
            except Exception as e:
                logger.error(f"Message handler error: {e}")
        else:
            logger.warning(f"No handler for message type: {msg_type}")
    
    async def _forward_loop(self) -> None:
        """Background loop to process message queue"""
        while True:
            try:
                await asyncio.sleep(1)
                
                # Process pending messages
                for message_id, message in list(self._message_queue.items()):
                    if message.status == MessageStatus.PENDING:
                        await self._forward_message(message_id)
                    elif message.status == MessageStatus.FAILED and message.should_retry():
                        await self._forward_message(message_id)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Forward loop error: {e}")
    
    async def _cleanup_loop(self) -> None:
        """Background loop to clean up expired messages"""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                
                # Clean up expired messages
                expired = [
                    mid for mid, msg in self._message_queue.items()
                    if msg.is_expired() or msg.status in [MessageStatus.DELIVERED, MessageStatus.FAILED]
                ]
                
                for mid in expired:
                    del self._message_queue[mid]
                
                if expired:
                    logger.info(f"Cleaned up {len(expired)} messages")
                
                # Clean up old forwarded message records
                now = datetime.now(timezone.utc)
                old = [
                    mid for mid, ts in self._forwarded_messages.items()
                    if (now - ts).total_seconds() > 3600  # 1 hour
                ]
                for mid in old:
                    del self._forwarded_messages[mid]
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    def _generate_message_id(self, destination: str, payload: Dict) -> str:
        """Generate unique message ID"""
        data = f"{self.entity_id}:{destination}:{datetime.now(timezone.utc).timestamp()}:{json.dumps(payload, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _load_queue(self) -> None:
        """Load message queue from storage"""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            for msg_data in data.get("messages", []):
                message = QueuedMessage(
                    message_id=msg_data["message_id"],
                    original_sender=msg_data["original_sender"],
                    final_destination=msg_data["final_destination"],
                    payload=msg_data["payload"],
                    path=msg_data.get("path", []),
                    hop_count=msg_data.get("hop_count", 0),
                    max_hops=msg_data.get("max_hops", 10),
                    ttl=msg_data.get("ttl", 3600),
                    created_at=datetime.fromisoformat(msg_data["created_at"]),
                    expires_at=datetime.fromisoformat(msg_data["expires_at"]),
                    status=MessageStatus(msg_data.get("status", "pending")),
                    retry_count=msg_data.get("retry_count", 0)
                )
                self._message_queue[message.message_id] = message
            
            logger.info(f"Loaded {len(self._message_queue)} messages from storage")
        except Exception as e:
            logger.error(f"Failed to load queue: {e}")
    
    def _save_queue(self) -> None:
        """Save message queue to storage"""
        try:
            data = {
                "messages": [
                    {
                        "message_id": m.message_id,
                        "original_sender": m.original_sender,
                        "final_destination": m.final_destination,
                        "payload": m.payload,
                        "path": m.path,
                        "hop_count": m.hop_count,
                        "max_hops": m.max_hops,
                        "ttl": m.ttl,
                        "created_at": m.created_at.isoformat(),
                        "expires_at": m.expires_at.isoformat(),
                        "status": m.status.value,
                        "retry_count": m.retry_count
                    }
                    for m in self._message_queue.values()
                ]
            }
            
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save queue: {e}")
    
    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a message type"""
        self._message_handlers[message_type] = handler
    
    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics"""
        return {
            **self._stats,
            "routing_table_size": len(self._routing_table),
            "queue_size": len(self._message_queue),
            "forwarded_cache_size": len(self._forwarded_messages)
        }


# Global instance
_multi_hop_router: Optional[MultiHopRouter] = None


def get_multi_hop_router() -> Optional[MultiHopRouter]:
    """Get global multi-hop router instance"""
    return _multi_hop_router


def init_multi_hop_router(
    entity_id: str,
    storage_path: Optional[str] = None
) -> MultiHopRouter:
    """Initialize global multi-hop router"""
    global _multi_hop_router
    _multi_hop_router = MultiHopRouter(entity_id, storage_path)
    return _multi_hop_router


if __name__ == "__main__":
    async def test():
        router = init_multi_hop_router("test-entity", "./test_multihop.json")
        await router.start()
        
        # Add test route
        router.add_route(
            destination="peer-2",
            next_hop="peer-1",
            metric=100,
            path=["peer-1"],
            is_direct=False
        )
        
        # Send test message
        msg_id = await router.send_message(
            destination="peer-2",
            payload={"type": "test", "data": "hello"}
        )
        
        print(f"Sent message: {msg_id}")
        print(f"Stats: {router.get_stats()}")
        
        await asyncio.sleep(2)
        await router.stop()
    
    asyncio.run(test())
