#!/usr/bin/env python3
"""
Relay Client - NAT Traversal Client for P2P Communication
NAT越えのためのリレークライアント

Features:
- Register with public relay servers
- Send/receive messages via relay
- Maintain relay connections with heartbeat
- Automatic relay selection and fallback
- E2E encryption preservation
"""

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
import aiohttp
from aiohttp import ClientTimeout, WSMsgType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RelayConnectionState(Enum):
    """Relay connection state"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    REGISTERING = "registering"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class RelayServer:
    """Relay server configuration"""
    relay_id: str
    url: str
    priority: int = 0
    last_latency: Optional[float] = None
    success_count: int = 0
    failure_count: int = 0
    
    @property
    def score(self) -> float:
        """Calculate relay score (higher is better)"""
        if self.failure_count > self.success_count:
            return -1000  # Avoid failed relays
        
        score = self.priority * 10 + self.success_count
        if self.last_latency:
            score -= self.last_latency  # Lower latency is better
        return score


@dataclass
class RelayConnection:
    """Active relay connection"""
    server: RelayServer
    state: RelayConnectionState
    session: Optional[aiohttp.ClientSession] = None
    ws: Optional[Any] = None  # WebSocket connection
    registered_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    heartbeat_interval: int = 60
    message_count: int = 0
    
    @property
    def is_active(self) -> bool:
        """Check if connection is active"""
        return self.state == RelayConnectionState.CONNECTED


@dataclass
class QueuedMessage:
    """Message queued for relay"""
    message_id: str
    target_id: str
    payload: Dict[str, Any]
    created_at: datetime
    retry_count: int = 0
    max_retries: int = 3


class RelayClient:
    """
    Relay client for NAT traversal.
    
    Manages connections to public relay servers and enables
    communication with peers behind NAT/firewall.
    """
    
    def __init__(
        self,
        entity_id: str,
        private_key: str,
        public_key: str,
        max_relays: int = 3,
        reconnect_interval: int = 30,
        message_queue_size: int = 1000
    ):
        self.entity_id = entity_id
        self.private_key = private_key
        self.public_key = public_key
        self.max_relays = max_relays
        self.reconnect_interval = reconnect_interval
        
        # Relay servers
        self._relays: List[RelayServer] = []
        self._connections: Dict[str, RelayConnection] = {}
        self._connections_lock = asyncio.Lock()
        
        # Message handling
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=message_queue_size)
        self._received_messages: asyncio.Queue = asyncio.Queue()
        self._message_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Statistics
        self._stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "messages_failed": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "connected_relays": 0
        }
        
        logger.info(f"RelayClient initialized: {entity_id}")
    
    # ========================================================================
    # Relay Management
    # ========================================================================
    
    def add_relay(self, relay_id: str, url: str, priority: int = 0):
        """
        Add a relay server.
        
        Args:
            relay_id: Relay identifier
            url: Relay URL (http:// or ws://)
            priority: Priority (higher = preferred)
        """
        relay = RelayServer(
            relay_id=relay_id,
            url=url,
            priority=priority
        )
        self._relays.append(relay)
        # Sort by priority
        self._relays.sort(key=lambda r: r.score, reverse=True)
        logger.info(f"Relay added: {relay_id} @ {url}")
    
    def remove_relay(self, relay_id: str):
        """
        Remove a relay server.
        
        Args:
            relay_id: Relay identifier
        """
        self._relays = [r for r in self._relays if r.relay_id != relay_id]
        logger.info(f"Relay removed: {relay_id}")
    
    async def connect(self):
        """Connect to relay servers"""
        self._running = True
        
        # Connect to top relays up to max_relays
        connect_tasks = []
        for relay in self._relays[:self.max_relays]:
            task = asyncio.create_task(self._connect_to_relay(relay))
            connect_tasks.append(task)
        
        await asyncio.gather(*connect_tasks, return_exceptions=True)
        
        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._receive_task = asyncio.create_task(self._receive_loop())
        
        connected = len([c for c in self._connections.values() if c.is_active])
        logger.info(f"Connected to {connected}/{len(self._relays)} relays")
    
    async def disconnect(self):
        """Disconnect from all relays"""
        self._running = False
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._receive_task:
            self._receive_task.cancel()
        
        # Close connections
        async with self._connections_lock:
            for conn in self._connections.values():
                if conn.ws:
                    await conn.ws.close()
                if conn.session:
                    await conn.session.close()
            self._connections.clear()
        
        logger.info("Disconnected from all relays")
    
    async def _connect_to_relay(self, relay: RelayServer):
        """
        Connect to a specific relay.
        
        Args:
            relay: Relay server to connect to
        """
        try:
            timeout = ClientTimeout(total=10)
            session = aiohttp.ClientSession(timeout=timeout)
            
            conn = RelayConnection(
                server=relay,
                state=RelayConnectionState.CONNECTING,
                session=session
            )
            
            async with self._connections_lock:
                self._connections[relay.relay_id] = conn
            
            # Try WebSocket first, fallback to HTTP
            ws_url = relay.url.replace("http://", "ws://").replace("https://", "wss://")
            ws_url = f"{ws_url}/relay/ws"
            
            try:
                ws = await session.ws_connect(ws_url)
                conn.ws = ws
                conn.state = RelayConnectionState.REGISTERING
                
                # Send registration
                await self._register_on_websocket(conn)
                
            except Exception as e:
                logger.warning(f"WebSocket failed for {relay.relay_id}: {e}")
                # Fallback to HTTP
                await self._register_via_http(conn)
            
            conn.state = RelayConnectionState.CONNECTED
            conn.registered_at = datetime.now(timezone.utc)
            relay.success_count += 1
            
            logger.info(f"Connected to relay: {relay.relay_id}")
            
        except Exception as e:
            logger.error(f"Failed to connect to relay {relay.relay_id}: {e}")
            relay.failure_count += 1
            if relay.relay_id in self._connections:
                del self._connections[relay.relay_id]
    
    async def _register_on_websocket(self, conn: RelayConnection):
        """Register via WebSocket"""
        registration = {
            "type": "register",
            "entity_id": self.entity_id,
            "public_key": self.public_key,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await conn.ws.send_json(registration)
        
        # Wait for acknowledgment
        msg = await conn.ws.receive(timeout=5)
        if msg.type == WSMsgType.TEXT:
            response = json.loads(msg.data)
            if response.get("type") == "register_ack":
                conn.heartbeat_interval = response.get("heartbeat_interval", 60)
    
    async def _register_via_http(self, conn: RelayConnection):
        """Register via HTTP"""
        url = f"{conn.server.url}/relay/register"
        data = {
            "entity_id": self.entity_id,
            "public_key": self.public_key,
            "connection_info": {"version": "1.0"}
        }
        
        async with conn.session.post(url, json=data) as resp:
            if resp.status == 200:
                result = await resp.json()
                conn.heartbeat_interval = result.get("heartbeat_interval", 60)
            else:
                raise Exception(f"Registration failed: {resp.status}")
    
    # ========================================================================
    # Message Handling
    # ========================================================================
    
    async def send_message(
        self,
        target_id: str,
        payload: Dict[str, Any],
        ttl: int = 300
    ) -> Dict[str, Any]:
        """
        Send a message via relay.
        
        Args:
            target_id: Target entity ID
            payload: E2E encrypted message payload
            ttl: Time-to-live in seconds
            
        Returns:
            Send result
        """
        message_id = secrets.token_hex(16)
        message = {
            "message_id": message_id,
            "sender_id": self.entity_id,
            "target_id": target_id,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ttl": ttl
        }
        
        # Select best connected relay
        relay_id = await self._select_relay()
        if not relay_id:
            # Queue for later
            await self._message_queue.put(QueuedMessage(
                message_id=message_id,
                target_id=target_id,
                payload=payload,
                created_at=datetime.now(timezone.utc)
            ))
            return {
                "success": False,
                "status": "queued",
                "message_id": message_id,
                "error": "No relay available"
            }
        
        try:
            async with self._connections_lock:
                conn = self._connections.get(relay_id)
            
            if not conn:
                raise Exception("Connection not found")
            
            if conn.ws:
                # Send via WebSocket
                await conn.ws.send_json({
                    "type": "forward",
                    "message": message
                })
            else:
                # Send via HTTP
                url = f"{conn.server.url}/relay/forward"
                async with conn.session.post(url, json=message) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP error: {resp.status}")
            
            conn.message_count += 1
            self._stats["messages_sent"] += 1
            self._stats["bytes_sent"] += len(json.dumps(payload))
            
            return {
                "success": True,
                "status": "sent",
                "message_id": message_id,
                "via_relay": relay_id
            }
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self._stats["messages_failed"] += 1
            return {
                "success": False,
                "status": "failed",
                "message_id": message_id,
                "error": str(e)
            }
    
    def add_message_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Add callback for received messages.
        
        Args:
            callback: Function to call when message is received
        """
        self._message_callbacks.append(callback)
    
    async def _receive_loop(self):
        """Background task to receive messages"""
        while self._running:
            try:
                # Check all WebSocket connections
                async with self._connections_lock:
                    connections = list(self._connections.values())
                
                for conn in connections:
                    if conn.ws and not conn.ws.closed:
                        try:
                            msg = await conn.ws.receive(timeout=1)
                            if msg.type == WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                await self._handle_message(data)
                        except asyncio.TimeoutError:
                            continue
                
                # Also check for HTTP-polling messages
                await self._poll_messages()
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Receive loop error: {e}")
                await asyncio.sleep(1)
    
    async def _handle_message(self, data: Dict[str, Any]):
        """
        Handle received message.
        
        Args:
            data: Message data
        """
        msg_type = data.get("type")
        
        if msg_type == "deliver":
            message = data.get("message", {})
            self._stats["messages_received"] += 1
            self._stats["bytes_received"] += len(json.dumps(message.get("payload", {})))
            
            # Notify callbacks
            for callback in self._message_callbacks:
                try:
                    callback(message)
                except Exception as e:
                    logger.error(f"Message callback error: {e}")
            
            logger.debug(f"Message received: {message.get('message_id')}")
            
        elif msg_type == "heartbeat_ack":
            relay_id = data.get("relay_id")
            async with self._connections_lock:
                if relay_id in self._connections:
                    self._connections[relay_id].last_heartbeat = datetime.now(timezone.utc)
    
    async def _poll_messages(self):
        """Poll for messages via HTTP (for non-WebSocket connections)"""
        async with self._connections_lock:
            connections = [
                c for c in self._connections.values()
                if c.is_active and not c.ws
            ]
        
        for conn in connections:
            try:
                url = f"{conn.server.url}/relay/messages/{self.entity_id}"
                async with conn.session.get(url, timeout=ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        messages = await resp.json()
                        for msg in messages:
                            await self._handle_message({"type": "deliver", "message": msg})
            except Exception:
                pass  # Ignore polling errors
    
    # ========================================================================
    # Maintenance
    # ========================================================================
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to relays"""
        while self._running:
            try:
                async with self._connections_lock:
                    connections = list(self._connections.items())
                
                for relay_id, conn in connections:
                    if not conn.is_active:
                        continue
                    
                    try:
                        if conn.ws:
                            await conn.ws.send_json({
                                "type": "heartbeat",
                                "entity_id": self.entity_id,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })
                        else:
                            # HTTP heartbeat
                            url = f"{conn.server.url}/relay/heartbeat"
                            async with conn.session.post(
                                url,
                                json={"entity_id": self.entity_id},
                                timeout=ClientTimeout(total=5)
                            ) as resp:
                                if resp.status == 200:
                                    conn.last_heartbeat = datetime.now(timezone.utc)
                        
                    except Exception as e:
                        logger.warning(f"Heartbeat failed for {relay_id}: {e}")
                        conn.state = RelayConnectionState.ERROR
                
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
                
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                await asyncio.sleep(5)
    
    async def _select_relay(self) -> Optional[str]:
        """
        Select best available relay.
        
        Returns:
            Relay ID or None
        """
        async with self._connections_lock:
            active = [
                (rid, c) for rid, c in self._connections.items()
                if c.is_active
            ]
            
            if not active:
                return None
            
            # Sort by score
            active.sort(key=lambda x: x[1].server.score, reverse=True)
            return active[0][0]
    
    # ========================================================================
    # Queries
    # ========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        async with self._connections_lock:
            connected = len([c for c in self._connections.values() if c.is_active])
        
        return {
            **self._stats,
            "connected_relays": connected,
            "total_relays": len(self._relays),
            "queued_messages": self._message_queue.qsize()
        }
    
    def is_connected(self) -> bool:
        """Check if connected to at least one relay"""
        return any(c.is_active for c in self._connections.values())


# ============================================================================
# Integration with PeerService
# ============================================================================

class RelayMessageRouter:
    """
    Message router that integrates RelayClient with PeerService.
    
    Automatically selects best path (direct or relay) for messages.
    """
    
    def __init__(
        self,
        relay_client: RelayClient,
        direct_send_callback: Callable[[str, Dict[str, Any]], Any]
    ):
        self.relay_client = relay_client
        self.direct_send = direct_send_callback
        
        # Track peer reachability
        self._direct_reachable: Set[str] = set()
        self._relay_reachable: Set[str] = set()
    
    async def send_message(
        self,
        target_id: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send message via best available path.
        
        Args:
            target_id: Target entity ID
            payload: Message payload
            
        Returns:
            Send result
        """
        # Try direct first if known to be reachable
        if target_id in self._direct_reachable:
            try:
                result = await self.direct_send(target_id, payload)
                if result.get("success"):
                    return result
                else:
                    # Mark as not directly reachable
                    self._direct_reachable.discard(target_id)
            except Exception:
                self._direct_reachable.discard(target_id)
        
        # Fall back to relay
        if self.relay_client.is_connected():
            result = await self.relay_client.send_message(target_id, payload)
            if result.get("success"):
                self._relay_reachable.add(target_id)
            return result
        
        # Try direct even if not known to be reachable
        try:
            result = await self.direct_send(target_id, payload)
            if result.get("success"):
                self._direct_reachable.add(target_id)
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"Direct and relay both failed: {e}"
            }
    
    def mark_direct_reachable(self, peer_id: str):
        """Mark peer as directly reachable"""
        self._direct_reachable.add(peer_id)
        self._relay_reachable.discard(peer_id)
    
    def mark_relay_reachable(self, peer_id: str):
        """Mark peer as reachable via relay"""
        self._relay_reachable.add(peer_id)


# ============================================================================
# Example Usage
# ============================================================================

async def example():
    """Example usage of RelayClient"""
    # Create client
    client = RelayClient(
        entity_id="peer-001",
        private_key="aa...",
        public_key="bb..."
    )
    
    # Add relays
    client.add_relay("relay-001", "http://localhost:9000", priority=10)
    client.add_relay("relay-002", "http://localhost:9001", priority=5)
    
    # Add message handler
    def on_message(msg):
        print(f"Received: {msg}")
    
    client.add_message_callback(on_message)
    
    # Connect
    await client.connect()
    
    # Send message
    result = await client.send_message(
        target_id="peer-002",
        payload={"encrypted": "...", "data": "Hello via relay"}
    )
    print(f"Send result: {result}")
    
    # Wait a bit
    await asyncio.sleep(5)
    
    # Get stats
    stats = client.get_stats()
    print(f"Stats: {stats}")
    
    # Disconnect
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(example())
