#!/usr/bin/env python3
"""
WebSocket Manager for Protocol v1.1/v1.2
Real-time peer communication with session management

Design: docs/websocket_design_v2.md
"""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set, Callable, Awaitable

from fastapi import WebSocket, WebSocketDisconnect

from protocol.constants import MessageType, ProtocolError
from services.session_manager import SessionManager

logger = logging.getLogger(__name__)


# WebSocket message types (v1.1 compatible)
class WSMessageType:
    """WebSocket message types mapping to v1.1 protocol"""
    # Handshake messages (mapped from v1.1)
    HANDSHAKE_INIT = "handshake_init"
    HANDSHAKE_INIT_ACK = "handshake_init_ack"
    CHALLENGE_RESPONSE = "challenge_response"
    SESSION_ESTABLISHED = "session_established"
    SESSION_CONFIRM = "session_confirm"
    READY = "ready"
    
    # Connection management
    PING = "ping"
    PONG = "pong"
    
    # Data transfer
    PEER_MESSAGE = "peer_message"
    BROADCAST = "broadcast"
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    CHUNKED_MESSAGE = "chunked_message"
    
    # Control
    ERROR = "error"
    STATUS = "status"
    CAPABILITY_EXCHANGE = "capability_exchange"


@dataclass
class WSConnectionState:
    """WebSocket connection state"""
    entity_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_ping: Optional[datetime] = None
    last_pong: Optional[datetime] = None
    message_count: int = 0
    session_id: Optional[str] = None
    is_authenticated: bool = False
    capabilities: Set[str] = field(default_factory=set)
    
    # Rate limiting
    message_timestamps: List[float] = field(default_factory=list)
    rate_limit_window: int = 60  # 60 seconds
    rate_limit_max: int = 100  # 100 messages per window
    
    # Message metadata for protocol v1.1
    last_sequence: int = 0
    pending_acks: Dict[int, Any] = field(default_factory=dict)


class WebSocketRateLimiter:
    """Rate limiter for WebSocket connections"""
    
    def __init__(self, max_messages: int = 100, window_seconds: int = 60):
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self._timestamps: Dict[str, List[float]] = defaultdict(list)
    
    def is_allowed(self, entity_id: str) -> bool:
        """Check if message is allowed under rate limit"""
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old timestamps
        self._timestamps[entity_id] = [
            ts for ts in self._timestamps[entity_id] 
            if ts > window_start
        ]
        
        # Check limit
        if len(self._timestamps[entity_id]) >= self.max_messages:
            return False
        
        # Record timestamp
        self._timestamps[entity_id].append(now)
        return True
    
    def get_remaining(self, entity_id: str) -> int:
        """Get remaining messages allowed in current window"""
        now = time.time()
        window_start = now - self.window_seconds
        
        recent = len([ts for ts in self._timestamps[entity_id] if ts > window_start])
        return max(0, self.max_messages - recent)


class WebSocketManager:
    """
    WebSocket connection manager for Protocol v1.1/v1.2
    
    Features:
    - Session-based authentication (pre-authenticated sessions)
    - Message routing by session_id
    - Rate limiting (100 msg/min per connection)
    - Heartbeat (PING/PONG every 30s)
    - Session recovery on reconnection
    - Protocol v1.1 message format support
    """
    
    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        max_message_size: int = 1024 * 1024,  # 1MB
        heartbeat_interval: int = 30,  # 30 seconds
        heartbeat_timeout: int = 40,   # 40 seconds (30s + 10s grace)
        rate_limit_max: int = 100,     # 100 msg/min
        rate_limit_window: int = 60
    ):
        self.session_manager = session_manager or SessionManager()
        self.max_message_size = max_message_size
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        
        # Connection management
        self._connections: Dict[str, WSConnectionState] = {}  # entity_id -> state
        self._session_connections: Dict[str, str] = {}  # session_id -> entity_id
        
        # Rate limiting
        self._rate_limiter = WebSocketRateLimiter(rate_limit_max, rate_limit_window)
        
        # Message handlers
        self._handlers: Dict[str, Callable[[str, Dict], Awaitable[Optional[Dict]]]] = {}
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Statistics
        self._stats = {
            "connections_total": 0,
            "connections_active": 0,
            "messages_received": 0,
            "messages_sent": 0,
            "errors": 0,
            "rate_limited": 0
        }
    
    async def start(self) -> None:
        """Start the WebSocket manager"""
        self._running = True
        await self.session_manager.start()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("WebSocket manager started")
    
    async def stop(self) -> None:
        """Stop the WebSocket manager and close all connections"""
        self._running = False
        
        # Cancel heartbeat task
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        for entity_id, state in list(self._connections.items()):
            try:
                await state.websocket.close(code=1001, reason="Server shutting down")
            except Exception:
                pass
        
        self._connections.clear()
        self._session_connections.clear()
        
        await self.session_manager.stop()
        logger.info("WebSocket manager stopped")
    
    def register_handler(
        self, 
        message_type: str, 
        handler: Callable[[str, Dict], Awaitable[Optional[Dict]]]
    ) -> None:
        """Register a message handler for specific message type"""
        self._handlers[message_type] = handler
        logger.debug(f"Registered handler for message type: {message_type}")
    
    async def connect(
        self, 
        websocket: WebSocket, 
        entity_id: str,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Accept a new WebSocket connection
        
        Args:
            websocket: FastAPI WebSocket object
            entity_id: Entity ID from JWT authentication
            session_id: Optional pre-authenticated session ID for session recovery
            
        Returns:
            True if connection accepted
        """
        await websocket.accept()
        
        # Check for existing connection and disconnect it
        if entity_id in self._connections:
            await self.disconnect(entity_id, code=1008, reason="New connection established")
        
        # Validate session if provided (session recovery)
        authenticated_session = None
        if session_id:
            session = await self.session_manager.get_session(session_id)
            if session:
                authenticated_session = session_id
                logger.info(f"Session recovery: {session_id[:8]}... for {entity_id}")
            else:
                logger.warning(f"Invalid session_id for recovery: {session_id[:8]}...")
        
        # Create connection state
        state = WSConnectionState(
            entity_id=entity_id,
            websocket=websocket,
            session_id=authenticated_session,
            is_authenticated=True  # JWT already validated
        )
        
        self._connections[entity_id] = state
        if authenticated_session:
            self._session_connections[authenticated_session] = entity_id
        
        self._stats["connections_total"] += 1
        self._stats["connections_active"] = len(self._connections)
        
        logger.info(f"WebSocket connected: {entity_id} (session: {authenticated_session[:8] if authenticated_session else 'none'}...)")
        
        # Send welcome message with protocol info
        await self._send_message(entity_id, {
            "type": WSMessageType.STATUS,
            "payload": {
                "event": "connected",
                "entity_id": entity_id,
                "session_id": authenticated_session,
                "protocol_version": "1.1",
                "capabilities": ["websocket", "e2e_encryption", "chunked_transfer"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        })
        
        return True
    
    async def disconnect(
        self, 
        entity_id: str, 
        code: int = 1000, 
        reason: str = "Normal closure"
    ) -> None:
        """
        Disconnect a peer
        
        Args:
            entity_id: Entity ID to disconnect
            code: WebSocket close code
            reason: Close reason
        """
        if entity_id not in self._connections:
            return
        
        state = self._connections[entity_id]
        
        # Remove session mapping
        if state.session_id and state.session_id in self._session_connections:
            del self._session_connections[state.session_id]
        
        # Close websocket
        try:
            await state.websocket.close(code=code, reason=reason)
        except Exception:
            pass
        
        del self._connections[entity_id]
        self._stats["connections_active"] = len(self._connections)
        
        logger.info(f"WebSocket disconnected: {entity_id} (code={code}, reason={reason})")
    
    async def send_to_peer(
        self, 
        entity_id: str, 
        message: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> bool:
        """
        Send a message to a specific peer
        
        Args:
            entity_id: Target entity ID
            message: Message dictionary (must include 'type' field)
            session_id: Optional session ID for routing
            
        Returns:
            True if message sent successfully
        """
        # Try entity_id lookup first
        if entity_id in self._connections:
            return await self._send_message(entity_id, message)
        
        # Try session_id lookup
        if session_id and session_id in self._session_connections:
            mapped_entity = self._session_connections[session_id]
            return await self._send_message(mapped_entity, message)
        
        logger.warning(f"Peer not found: {entity_id} (session: {session_id})")
        return False
    
    async def send_to_session(
        self, 
        session_id: str, 
        message: Dict[str, Any]
    ) -> bool:
        """
        Send a message by session ID
        
        Args:
            session_id: Target session ID
            message: Message dictionary
            
        Returns:
            True if message sent successfully
        """
        if session_id not in self._session_connections:
            return False
        
        entity_id = self._session_connections[session_id]
        return await self._send_message(entity_id, message)
    
    async def broadcast(
        self, 
        message: Dict[str, Any], 
        exclude: Optional[str] = None,
        require_capability: Optional[str] = None
    ) -> int:
        """
        Broadcast a message to all connected peers
        
        Args:
            message: Message dictionary
            exclude: Entity ID to exclude from broadcast
            require_capability: Only broadcast to peers with this capability
            
        Returns:
            Number of peers message was sent to
        """
        sent_count = 0
        
        for entity_id, state in self._connections.items():
            if entity_id == exclude:
                continue
            
            if require_capability and require_capability not in state.capabilities:
                continue
            
            try:
                if await self._send_message(entity_id, message):
                    sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast to {entity_id}: {e}")
        
        return sent_count
    
    async def handle_connection(self, websocket: WebSocket, entity_id: str) -> None:
        """
        Main message loop for a WebSocket connection
        
        Args:
            websocket: FastAPI WebSocket object
            entity_id: Authenticated entity ID
        """
        state = self._connections.get(entity_id)
        if not state:
            logger.error(f"Connection state not found for {entity_id}")
            return
        
        try:
            while True:
                # Receive message
                try:
                    data = await websocket.receive()
                    
                    # Handle text message
                    if data["type"] == "websocket.receive":
                        if "text" in data:
                            message = json.loads(data["text"])
                        elif "bytes" in data:
                            # Check size limit
                            if len(data["bytes"]) > self.max_message_size:
                                await self._send_error(entity_id, "Message too large")
                                continue
                            message = json.loads(data["bytes"].decode("utf-8"))
                        else:
                            continue
                    elif data["type"] == "websocket.disconnect":
                        break
                    else:
                        continue
                    
                    # Check message size (text)
                    if len(json.dumps(message)) > self.max_message_size:
                        await self._send_error(entity_id, "Message too large (max 1MB)")
                        continue
                    
                    # Rate limiting
                    if not self._rate_limiter.is_allowed(entity_id):
                        self._stats["rate_limited"] += 1
                        await self._send_error(entity_id, "Rate limit exceeded (100 msg/min)")
                        continue
                    
                    # Update stats
                    state.message_count += 1
                    self._stats["messages_received"] += 1
                    
                    # Process message
                    await self._process_message(entity_id, message)
                    
                except WebSocketDisconnect:
                    break
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from {entity_id}: {e}")
                    await self._send_error(entity_id, "Invalid JSON format")
                except Exception as e:
                    logger.error(f"Error processing message from {entity_id}: {e}")
                    self._stats["errors"] += 1
                    
        except Exception as e:
            logger.error(f"WebSocket error for {entity_id}: {e}")
        finally:
            await self.disconnect(entity_id)
    
    async def _process_message(self, entity_id: str, message: Dict[str, Any]) -> None:
        """Process incoming message"""
        msg_type = message.get("type")
        state = self._connections[entity_id]
        
        # Update sequence if provided (protocol v1.1)
        seq = message.get("seq")
        if seq is not None:
            state.last_sequence = max(state.last_sequence, seq)
        
        # Handle PING (heartbeat)
        if msg_type == WSMessageType.PING:
            state.last_ping = datetime.now(timezone.utc)
            await self._send_message(entity_id, {
                "type": WSMessageType.PONG,
                "payload": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "seq": message.get("seq")
                }
            })
            return
        
        # Handle PONG (heartbeat response)
        if msg_type == WSMessageType.PONG:
            state.last_pong = datetime.now(timezone.utc)
            return
        
        # Handle CAPABILITY_EXCHANGE
        if msg_type == WSMessageType.CAPABILITY_EXCHANGE:
            capabilities = message.get("payload", {}).get("capabilities", [])
            state.capabilities = set(capabilities)
            await self._send_message(entity_id, {
                "type": WSMessageType.CAPABILITY_EXCHANGE,
                "payload": {
                    "capabilities": list(state.capabilities),
                    "acknowledged": capabilities
                }
            })
            return
        
        # Handle STATUS request
        if msg_type == WSMessageType.STATUS:
            await self._send_message(entity_id, {
                "type": WSMessageType.STATUS,
                "payload": {
                    "entity_id": entity_id,
                    "session_id": state.session_id,
                    "connected_at": state.connected_at.isoformat(),
                    "message_count": state.message_count,
                    "capabilities": list(state.capabilities)
                }
            })
            return
        
        # Route to registered handler if exists
        if msg_type in self._handlers:
            try:
                response = await self._handlers[msg_type](entity_id, message)
                if response:
                    await self._send_message(entity_id, response)
            except Exception as e:
                logger.error(f"Handler error for {msg_type}: {e}")
                await self._send_error(entity_id, f"Handler error: {str(e)}")
            return
        
        # Default: echo message with acknowledgment
        await self._send_message(entity_id, {
            "type": WSMessageType.STATUS,
            "payload": {
                "event": "message_received",
                "original_type": msg_type,
                "seq": seq
            }
        })
    
    async def _send_message(self, entity_id: str, message: Dict[str, Any]) -> bool:
        """Send message to a specific peer"""
        if entity_id not in self._connections:
            return False
        
        try:
            # Add timestamp if not present
            if "timestamp" not in message:
                message["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            # Add message_id if not present
            if "message_id" not in message:
                message["message_id"] = str(uuid.uuid4())
            
            await self._connections[entity_id].websocket.send_json(message)
            self._stats["messages_sent"] += 1
            return True
        except Exception as e:
            logger.warning(f"Failed to send message to {entity_id}: {e}")
            return False
    
    async def _send_error(self, entity_id: str, error_message: str) -> None:
        """Send error message to peer"""
        await self._send_message(entity_id, {
            "type": WSMessageType.ERROR,
            "payload": {
                "error": error_message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        })
    
    async def _heartbeat_loop(self) -> None:
        """Background heartbeat monitoring task"""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                now = datetime.now(timezone.utc)
                timeout_threshold = now - timedelta(seconds=self.heartbeat_timeout)
                
                # Check for stale connections
                for entity_id, state in list(self._connections.items()):
                    # Skip if recently received any message
                    if state.last_ping and state.last_ping > timeout_threshold:
                        continue
                    
                    # Send PING
                    try:
                        await self._send_message(entity_id, {
                            "type": WSMessageType.PING,
                            "payload": {
                                "timestamp": now.isoformat()
                            }
                        })
                    except Exception as e:
                        logger.warning(f"Failed to send PING to {entity_id}: {e}")
                        await self.disconnect(entity_id, code=1001, reason="Heartbeat failed")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
    
    def get_connected_peers(self) -> List[Dict[str, Any]]:
        """Get list of connected peers with metadata"""
        return [
            {
                "entity_id": state.entity_id,
                "session_id": state.session_id,
                "connected_at": state.connected_at.isoformat(),
                "message_count": state.message_count,
                "capabilities": list(state.capabilities),
                "last_ping": state.last_ping.isoformat() if state.last_ping else None
            }
            for state in self._connections.values()
        ]
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self._connections)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket manager statistics"""
        return {
            **self._stats,
            "active_connections": len(self._connections)
        }
    
    def is_connected(self, entity_id: str) -> bool:
        """Check if a peer is connected"""
        return entity_id in self._connections
    
    def get_peer_capabilities(self, entity_id: str) -> Optional[Set[str]]:
        """Get capabilities of a peer"""
        if entity_id not in self._connections:
            return None
        return self._connections[entity_id].capabilities


# Global instance
_ws_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Get or create global WebSocket manager instance"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager


async def init_websocket_manager() -> WebSocketManager:
    """Initialize and start WebSocket manager"""
    manager = get_websocket_manager()
    await manager.start()
    return manager


async def shutdown_websocket_manager() -> None:
    """Shutdown WebSocket manager"""
    global _ws_manager
    if _ws_manager:
        await _ws_manager.stop()
        _ws_manager = None
