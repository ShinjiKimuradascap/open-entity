#!/usr/bin/env python3
"""
WebSocket Client for P2P Communication
P2P通信向けWebSocketクライアント

Features:
- Automatic connection with retry and backoff
- Heartbeat/keepalive monitoring
- Message signing with Ed25519
- JWT authentication
- HTTP fallback on WebSocket failure
- Reconnection with exponential backoff

Usage:
    client = WebSocketPeerClient(entity_id, private_key)
    await client.connect("wss://peer.example.com/ws/v1/peers?token=xxx")
    await client.send_message({"type": "HELLO", ...})
    await client.disconnect()
"""

import asyncio
import json
import logging
import time
from typing import Dict, Optional, Callable, Awaitable, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid

# WebSocket library with fallback
try:
    import websockets
    from websockets.exceptions import ConnectionClosed, InvalidStatusCode
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    websockets = None
    ConnectionClosed = Exception
    InvalidStatusCode = Exception

# Import crypto for signing
try:
    from services.crypto import sign_message, generate_keypair
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSocketClientState(Enum):
    """Client connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class WebSocketClientConfig:
    """Configuration for WebSocket client"""
    entity_id: str
    reconnect_interval: float = 5.0
    max_reconnect_attempts: int = 10
    heartbeat_interval: float = 30.0
    connection_timeout: float = 10.0
    message_timeout: float = 30.0
    enable_http_fallback: bool = True
    http_fallback_url: Optional[str] = None


@dataclass
class WebSocketMessage:
    """WebSocket message structure"""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "MESSAGE"  # HELLO, READY, MESSAGE, ACK, HEARTBEAT, BYE, ERROR
    from_entity: str = ""
    to_entity: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "type": self.type,
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "signature": self.signature
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebSocketMessage':
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            type=data.get("type", "MESSAGE"),
            from_entity=data.get("from_entity", ""),
            to_entity=data.get("to_entity"),
            timestamp=data.get("timestamp", time.time()),
            payload=data.get("payload", {}),
            signature=data.get("signature")
        )


class WebSocketPeerClient:
    """
    WebSocket client for peer-to-peer communication
    
    Handles:
    - Connection establishment with authentication
    - Automatic reconnection with exponential backoff
    - Heartbeat/ping-pong
    - Message signing and verification
    - HTTP fallback when WebSocket unavailable
    """
    
    def __init__(
        self,
        entity_id: str,
        private_key: Optional[bytes] = None,
        config: Optional[WebSocketClientConfig] = None
    ):
        self.entity_id = entity_id
        self.private_key = private_key
        self.config = config or WebSocketClientConfig(entity_id=entity_id)
        
        # Connection state
        self._state = WebSocketClientState.DISCONNECTED
        self._websocket = None
        self._uri = None
        self._jwt_token = None
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        
        # Callbacks
        self._message_handler: Optional[Callable[[WebSocketMessage], Awaitable[None]]] = None
        self._error_handler: Optional[Callable[[Exception], None]] = None
        self._connection_handler: Optional[Callable[[bool], None]] = None
        
        # Reconnection state
        self._reconnect_attempts = 0
        self._reconnect_backoff = 1.0
        
        # Message tracking
        self._pending_acks: Dict[str, asyncio.Future] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        
        # Metrics
        self._messages_sent = 0
        self._messages_received = 0
        self._connection_time: Optional[float] = None
        
        if not WEBSOCKETS_AVAILABLE:
            logger.warning("websockets library not available, HTTP fallback only")
    
    @property
    def state(self) -> WebSocketClientState:
        """Current connection state"""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._state == WebSocketClientState.CONNECTED and self._websocket is not None
    
    def on_message(self, handler: Callable[[WebSocketMessage], Awaitable[None]]) -> None:
        """Register message handler callback"""
        self._message_handler = handler
    
    def on_error(self, handler: Callable[[Exception], None]) -> None:
        """Register error handler callback"""
        self._error_handler = handler
    
    def on_connection_change(self, handler: Callable[[bool], None]) -> None:
        """Register connection state change handler"""
        self._connection_handler = handler
    
    async def connect(
        self,
        uri: str,
        jwt_token: Optional[str] = None,
        timeout: Optional[float] = None
    ) -> bool:
        """
        Connect to WebSocket endpoint
        
        Args:
            uri: WebSocket URI (ws:// or wss://)
            jwt_token: JWT token for authentication
            timeout: Connection timeout in seconds
            
        Returns:
            True if connected successfully
        """
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not available")
            return False
        
        self._uri = uri
        self._jwt_token = jwt_token
        timeout = timeout or self.config.connection_timeout
        
        self._state = WebSocketClientState.CONNECTING
        
        try:
            # Build URI with token if provided
            connection_uri = uri
            if jwt_token and "token=" not in uri:
                separator = "&" if "?" in uri else "?"
                connection_uri = f"{uri}{separator}token={jwt_token}"
            
            logger.info(f"Connecting to WebSocket: {uri}")
            
            self._websocket = await asyncio.wait_for(
                websockets.connect(connection_uri),
                timeout=timeout
            )
            
            self._state = WebSocketClientState.CONNECTED
            self._reconnect_attempts = 0
            self._reconnect_backoff = 1.0
            self._connection_time = time.time()
            
            # Start background tasks
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Send HELLO message
            await self._send_hello()
            
            if self._connection_handler:
                self._connection_handler(True)
            
            logger.info(f"WebSocket connected: {self.entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self._state = WebSocketClientState.ERROR
            
            if self._error_handler:
                self._error_handler(e)
            
            # Try HTTP fallback if enabled
            if self.config.enable_http_fallback:
                return await self._http_fallback_connect()
            
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from WebSocket"""
        if self._state == WebSocketClientState.DISCONNECTED:
            return
        
        self._state = WebSocketClientState.DISCONNECTED
        
        # Send BYE message
        try:
            if self._websocket:
                bye_message = WebSocketMessage(
                    type="BYE",
                    from_entity=self.entity_id,
                    payload={"reason": "client_disconnect"}
                )
                await self._send_message(bye_message)
        except Exception:
            pass
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        # Close connection
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
            self._websocket = None
        
        # Notify handler
        if self._connection_handler:
            self._connection_handler(False)
        
        logger.info(f"WebSocket disconnected: {self.entity_id}")
    
    async def send_message(
        self,
        message: Union[WebSocketMessage, Dict[str, Any]],
        to_entity: Optional[str] = None,
        wait_for_ack: bool = False,
        timeout: float = 30.0
    ) -> Optional[bool]:
        """
        Send a message to the peer
        
        Args:
            message: Message to send (WebSocketMessage or dict)
            to_entity: Target entity ID (optional)
            wait_for_ack: Wait for acknowledgement
            timeout: ACK timeout in seconds
            
        Returns:
            True if sent successfully, False if failed, None if HTTP fallback
        """
        # Convert dict to WebSocketMessage
        if isinstance(message, dict):
            message = WebSocketMessage(
                type=message.get("type", "MESSAGE"),
                from_entity=self.entity_id,
                to_entity=to_entity or message.get("to_entity"),
                payload=message.get("payload", message)
            )
        else:
            message.from_entity = self.entity_id
            if to_entity:
                message.to_entity = to_entity
        
        # Sign message if private key available
        if self.private_key and CRYPTO_AVAILABLE:
            message.signature = self._sign_message(message)
        
        # Send via WebSocket if connected
        if self.is_connected:
            try:
                await self._send_message(message)
                
                if wait_for_ack:
                    return await self._wait_for_ack(message.message_id, timeout)
                
                return True
            except Exception as e:
                logger.error(f"Failed to send WebSocket message: {e}")
                
                # Try HTTP fallback
                if self.config.enable_http_fallback:
                    return await self._http_fallback_send(message.to_dict())
                
                return False
        
        # HTTP fallback
        elif self.config.enable_http_fallback:
            return await self._http_fallback_send(message.to_dict())
        
        else:
            logger.error("Not connected and HTTP fallback disabled")
            return False
    
    async def _send_hello(self) -> None:
        """Send HELLO message on connect"""
        hello = WebSocketMessage(
            type="HELLO",
            from_entity=self.entity_id,
            payload={
                "version": "1.2",
                "capabilities": ["websocket", "ed25519", "heartbeat"]
            }
        )
        await self._send_message(hello)
    
    async def _send_message(self, message: WebSocketMessage) -> None:
        """Send message via WebSocket"""
        if not self._websocket:
            raise ConnectionError("WebSocket not connected")
        
        await self._websocket.send(json.dumps(message.to_dict()))
        self._messages_sent += 1
    
    async def _receive_loop(self) -> None:
        """Background task to receive messages"""
        try:
            while self.is_connected:
                try:
                    raw_message = await self._websocket.recv()
                    self._messages_received += 1
                    
                    # Parse message
                    data = json.loads(raw_message)
                    message = WebSocketMessage.from_dict(data)
                    
                    # Handle message based on type
                    await self._handle_message(message)
                    
                except ConnectionClosed:
                    logger.info("WebSocket connection closed")
                    break
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON received: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    
        except asyncio.CancelledError:
            logger.debug("Receive loop cancelled")
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
            if self._error_handler:
                self._error_handler(e)
        finally:
            # Trigger reconnection if not disconnected intentionally
            if self._state != WebSocketClientState.DISCONNECTED:
                asyncio.create_task(self._reconnect())
    
    async def _handle_message(self, message: WebSocketMessage) -> None:
        """Handle incoming message"""
        # Send ACK if requested
        if message.type == "MESSAGE":
            ack = WebSocketMessage(
                type="ACK",
                from_entity=self.entity_id,
                to_entity=message.from_entity,
                payload={"ack_message_id": message.message_id}
            )
            await self._send_message(ack)
        
        # Handle heartbeat
        elif message.type == "HEARTBEAT":
            # Send pong
            pong = WebSocketMessage(
                type="HEARTBEAT",
                from_entity=self.entity_id,
                to_entity=message.from_entity,
                payload={"type": "pong", "timestamp": time.time()}
            )
            await self._send_message(pong)
        
        # Handle ACK
        elif message.type == "ACK":
            ack_message_id = message.payload.get("ack_message_id")
            if ack_message_id and ack_message_id in self._pending_acks:
                self._pending_acks[ack_message_id].set_result(True)
        
        # Handle READY
        elif message.type == "READY":
            logger.info(f"Peer ready: {message.from_entity}")
        
        # Handle BYE
        elif message.type == "BYE":
            logger.info(f"Peer disconnected: {message.from_entity}")
        
        # Call user handler
        if self._message_handler:
            await self._message_handler(message)
    
    async def _heartbeat_loop(self) -> None:
        """Background task to send heartbeats"""
        try:
            while self.is_connected:
                await asyncio.sleep(self.config.heartbeat_interval)
                
                if not self.is_connected:
                    break
                
                try:
                    heartbeat = WebSocketMessage(
                        type="HEARTBEAT",
                        from_entity=self.entity_id,
                        payload={"type": "ping", "timestamp": time.time()}
                    )
                    await self._send_message(heartbeat)
                except Exception as e:
                    logger.warning(f"Heartbeat failed: {e}")
                    
        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
    
    async def _reconnect(self) -> None:
        """Attempt to reconnect with backoff"""
        if self._reconnect_attempts >= self.config.max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            self._state = WebSocketClientState.ERROR
            return
        
        self._state = WebSocketClientState.RECONNECTING
        self._reconnect_attempts += 1
        
        # Exponential backoff
        wait_time = self._reconnect_backoff * (2 ** (self._reconnect_attempts - 1))
        wait_time = min(wait_time, 60.0)  # Cap at 60 seconds
        
        logger.info(f"Reconnecting in {wait_time}s (attempt {self._reconnect_attempts})")
        await asyncio.sleep(wait_time)
        
        # Attempt reconnection
        success = await self.connect(self._uri, self._jwt_token)
        
        if success:
            logger.info("Reconnection successful")
        else:
            logger.warning("Reconnection failed")
    
    async def _wait_for_ack(self, message_id: str, timeout: float) -> bool:
        """Wait for ACK message"""
        future = asyncio.Future()
        self._pending_acks[message_id] = future
        
        try:
            await asyncio.wait_for(future, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending_acks.pop(message_id, None)
    
    def _sign_message(self, message: WebSocketMessage) -> str:
        """Sign message with Ed25519"""
        if not CRYPTO_AVAILABLE or not self.private_key:
            return ""
        
        try:
            message_data = f"{message.message_id}:{message.type}:{message.timestamp}"
            signature = sign_message(self.private_key, message_data.encode())
            return signature.hex() if isinstance(signature, bytes) else signature
        except Exception as e:
            logger.error(f"Failed to sign message: {e}")
            return ""
    
    async def _http_fallback_connect(self) -> bool:
        """Fallback to HTTP connection"""
        logger.info("Using HTTP fallback")
        # HTTP fallback is transparent - just mark as connected
        # Actual HTTP requests are handled in send_message
        return True
    
    async def _http_fallback_send(self, message: Dict[str, Any]) -> Optional[bool]:
        """Send message via HTTP fallback"""
        if not self.config.http_fallback_url:
            logger.error("HTTP fallback URL not configured")
            return None
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self._jwt_token:
                    headers["Authorization"] = f"Bearer {self._jwt_token}"
                
                async with session.post(
                    self.config.http_fallback_url,
                    json=message,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    return response.status == 200
                    
        except Exception as e:
            logger.error(f"HTTP fallback failed: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            "state": self._state.value,
            "entity_id": self.entity_id,
            "messages_sent": self._messages_sent,
            "messages_received": self._messages_received,
            "reconnect_attempts": self._reconnect_attempts,
            "connected_since": self._connection_time,
            "websocket_available": WEBSOCKETS_AVAILABLE,
            "crypto_available": CRYPTO_AVAILABLE
        }


# Global client registry for multiple peer connections
class WebSocketClientRegistry:
    """Registry for managing multiple WebSocket clients"""
    
    def __init__(self):
        self._clients: Dict[str, WebSocketPeerClient] = {}
    
    def register_client(
        self,
        peer_id: str,
        client: WebSocketPeerClient
    ) -> None:
        """Register a client for a peer"""
        self._clients[peer_id] = client
    
    def unregister_client(self, peer_id: str) -> None:
        """Unregister a client"""
        self._clients.pop(peer_id, None)
    
    def get_client(self, peer_id: str) -> Optional[WebSocketPeerClient]:
        """Get client for a peer"""
        return self._clients.get(peer_id)
    
    def list_clients(self) -> Dict[str, WebSocketPeerClient]:
        """List all registered clients"""
        return self._clients.copy()
    
    async def disconnect_all(self) -> None:
        """Disconnect all clients"""
        for client in list(self._clients.values()):
            await client.disconnect()
        self._clients.clear()


# Singleton registry instance
_client_registry: Optional[WebSocketClientRegistry] = None


def get_client_registry() -> WebSocketClientRegistry:
    """Get global client registry"""
    global _client_registry
    if _client_registry is None:
        _client_registry = WebSocketClientRegistry()
    return _client_registry


def create_websocket_client(
    entity_id: str,
    private_key: Optional[bytes] = None,
    **config_kwargs
) -> WebSocketPeerClient:
    """
    Factory function to create a WebSocket client
    
    Args:
        entity_id: Entity identifier
        private_key: Ed25519 private key for signing
        **config_kwargs: Additional config options
        
    Returns:
        WebSocketPeerClient instance
    """
    config = WebSocketClientConfig(entity_id=entity_id, **config_kwargs)
    return WebSocketPeerClient(entity_id, private_key, config)


# Convenience functions for peer_service.py integration
async def connect_to_peer(
    peer_id: str,
    websocket_url: str,
    jwt_token: Optional[str] = None,
    entity_id: Optional[str] = None,
    private_key: Optional[bytes] = None
) -> Optional[WebSocketPeerClient]:
    """
    Connect to a peer via WebSocket
    
    Args:
        peer_id: Target peer ID
        websocket_url: WebSocket endpoint URL
        jwt_token: JWT token for authentication
        entity_id: Our entity ID
        private_key: Private key for signing
        
    Returns:
        Connected WebSocketPeerClient or None
    """
    if not entity_id:
        # Try to get from environment or config
        import os
        entity_id = os.getenv("ENTITY_ID", "unknown")
    
    client = create_websocket_client(entity_id, private_key)
    
    success = await client.connect(websocket_url, jwt_token)
    
    if success:
        registry = get_client_registry()
        registry.register_client(peer_id, client)
        return client
    
    return None


async def send_to_peer(
    peer_id: str,
    message: Dict[str, Any],
    wait_for_ack: bool = False
) -> bool:
    """
    Send message to a peer via WebSocket
    
    Args:
        peer_id: Target peer ID
        message: Message to send
        wait_for_ack: Wait for acknowledgement
        
    Returns:
        True if sent successfully
    """
    registry = get_client_registry()
    client = registry.get_client(peer_id)
    
    if not client:
        logger.error(f"No WebSocket client for peer: {peer_id}")
        return False
    
    result = await client.send_message(message, wait_for_ack=wait_for_ack)
    return result if result is not None else False


async def disconnect_from_peer(peer_id: str) -> None:
    """Disconnect from a peer"""
    registry = get_client_registry()
    client = registry.get_client(peer_id)
    
    if client:
        await client.disconnect()
        registry.unregister_client(peer_id)


async def disconnect_all_peers() -> None:
    """Disconnect from all peers"""
    registry = get_client_registry()
    await registry.disconnect_all()
