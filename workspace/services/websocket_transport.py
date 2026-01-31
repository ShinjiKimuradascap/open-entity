#!/usr/bin/env python3
"""
WebSocket Transport for AI Collaboration Network
WebSocketトランスポート層

Features:
- Bidirectional real-time communication
- Automatic reconnection
- Heartbeat/ping-pong
- Integration with PeerService
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional, Any, Callable, Set
import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WSConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class WSConnectionConfig:
    """WebSocket connection configuration"""
    heartbeat_interval: float = 30.0  # seconds
    reconnect_interval: float = 5.0
    max_reconnect_attempts: int = 10
    connection_timeout: float = 10.0
    ping_timeout: float = 10.0
    close_timeout: float = 5.0


@dataclass
class WSMessage:
    """WebSocket message wrapper"""
    message_type: str
    payload: Any
    sender_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
    
    def to_json(self) -> str:
        return json.dumps({
            "type": self.message_type,
            "payload": self.payload,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        })
    
    @classmethod
    def from_json(cls, data: str) -> "WSMessage":
        obj = json.loads(data)
        return cls(
            message_type=obj["type"],
            payload=obj["payload"],
            sender_id=obj.get("sender_id"),
            timestamp=datetime.fromisoformat(obj["timestamp"]) if obj.get("timestamp") else None
        )


class WebSocketClient:
    """
    WebSocket client with auto-reconnection.
    
    Maintains persistent connection to WebSocket server
    with automatic reconnection and heartbeat.
    """
    
    def __init__(
        self,
        uri: str,
        entity_id: str,
        config: Optional[WSConnectionConfig] = None,
        message_handler: Optional[Callable[[WSMessage], None]] = None
    ):
        self.uri = uri
        self.entity_id = entity_id
        self.config = config or WSConnectionConfig()
        self.message_handler = message_handler
        
        self._state = WSConnectionState.DISCONNECTED
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        self._lock = asyncio.Lock()
        self._running = False
        
    @property
    def state(self) -> WSConnectionState:
        return self._state
    
    @property
    def is_connected(self) -> bool:
        return self._state == WSConnectionState.CONNECTED and self._websocket is not None
    
    async def connect(self) -> bool:
        """Connect to WebSocket server"""
        async with self._lock:
            if self._state in (WSConnectionState.CONNECTED, WSConnectionState.CONNECTING):
                return True
            
            self._state = WSConnectionState.CONNECTING
            self._running = True
        
        try:
            logger.info(f"Connecting to {self.uri}")
            
            self._websocket = await websockets.connect(
                self.uri,
                subprotocols=["ai-collaboration-v1"],
                ping_interval=self.config.heartbeat_interval,
                ping_timeout=self.config.ping_timeout,
                close_timeout=self.config.close_timeout
            )
            
            # Send authentication/identification
            await self._send_identification()
            
            self._state = WSConnectionState.CONNECTED
            self._reconnect_attempts = 0
            
            logger.info(f"Connected to {self.uri}")
            
            # Start message receiver
            asyncio.create_task(self._receive_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._state = WSConnectionState.ERROR
            return False
    
    async def _send_identification(self):
        """Send entity identification after connection"""
        ident_msg = WSMessage(
            message_type="identify",
            payload={"entity_id": self.entity_id, "version": "1.2"}
        )
        await self._websocket.send(ident_msg.to_json())
    
    async def disconnect(self):
        """Disconnect from server"""
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
        
        self._state = WSConnectionState.DISCONNECTED
        logger.info("Disconnected")
    
    async def send(self, message: WSMessage) -> bool:
        """Send message through WebSocket"""
        if not self.is_connected:
            logger.warning("Cannot send: not connected")
            return False
        
        try:
            await self._websocket.send(message.to_json())
            return True
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return False
    
    async def _receive_loop(self):
        """Main receive loop"""
        try:
            while self._running and self.is_connected:
                try:
                    data = await asyncio.wait_for(
                        self._websocket.recv(),
                        timeout=self.config.heartbeat_interval * 2
                    )
                    
                    # Parse and handle message
                    try:
                        message = WSMessage.from_json(data)
                        if self.message_handler:
                            await self._handle_message(message)
                    except json.JSONDecodeError:
                        logger.warning(f"Received invalid JSON: {data[:100]}")
                        
                except asyncio.TimeoutError:
                    # Check if still connected
                    if self.is_connected:
                        continue
                    else:
                        break
                        
        except ConnectionClosed:
            logger.info("Connection closed")
        except Exception as e:
            logger.error(f"Receive error: {e}")
        finally:
            await self._handle_disconnect()
    
    async def _handle_message(self, message: WSMessage):
        """Handle incoming message"""
        if message.message_type == "ping":
            # Respond with pong
            await self.send(WSMessage(
                message_type="pong",
                payload=message.payload
            ))
        elif self.message_handler:
            await self.message_handler(message)
    
    async def _handle_disconnect(self):
        """Handle unexpected disconnection"""
        self._state = WSConnectionState.DISCONNECTED
        
        if self._running and self._reconnect_attempts < self.config.max_reconnect_attempts:
            self._state = WSConnectionState.RECONNECTING
            self._reconnect_attempts += 1
            
            logger.info(f"Reconnecting in {self.config.reconnect_interval}s (attempt {self._reconnect_attempts})")
            await asyncio.sleep(self.config.reconnect_interval)
            await self.connect()
        else:
            logger.error("Max reconnection attempts reached")
            self._state = WSConnectionState.ERROR


class WebSocketServer:
    """
    WebSocket server for accepting peer connections.
    
    Manages multiple client connections and routes messages.
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        message_handler: Optional[Callable[[str, WSMessage], None]] = None
    ):
        self.host = host
        self.port = port
        self.message_handler = message_handler
        
        self._clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        self._running = False
        self._server: Optional[websockets.WebSocketServer] = None
        
    async def start(self):
        """Start WebSocket server"""
        self._running = True
        
        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            subprotocols=["ai-collaboration-v1"]
        )
        
        logger.info(f"WebSocket server started on {self.host}:{self.port}")
        
    async def stop(self):
        """Stop WebSocket server"""
        self._running = False
        
        # Close all client connections
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
        
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        logger.info("WebSocket server stopped")
        
    async def _handle_client(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """Handle new client connection"""
        entity_id = None
        
        try:
            # Wait for identification
            data = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            message = WSMessage.from_json(data)
            
            if message.message_type == "identify":
                entity_id = message.payload.get("entity_id")
                if entity_id:
                    self._clients[entity_id] = websocket
                    logger.info(f"Client identified: {entity_id}")
                    
                    # Send acknowledgement
                    await websocket.send(WSMessage(
                        message_type="identified",
                        payload={"status": "ok", "entity_id": entity_id}
                    ).to_json())
            
            # Handle messages
            async for data in websocket:
                try:
                    message = WSMessage.from_json(data)
                    
                    if self.message_handler:
                        await self.message_handler(entity_id, message)
                        
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from {entity_id}")
                    
        except asyncio.TimeoutError:
            logger.warning("Client identification timeout")
        except ConnectionClosed:
            logger.info(f"Client disconnected: {entity_id}")
        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            if entity_id and entity_id in self._clients:
                del self._clients[entity_id]
    
    async def send_to(self, entity_id: str, message: WSMessage) -> bool:
        """Send message to specific client"""
        if entity_id not in self._clients:
            return False
        
        try:
            await self._clients[entity_id].send(message.to_json())
            return True
        except Exception as e:
            logger.error(f"Failed to send to {entity_id}: {e}")
            return False
    
    async def broadcast(self, message: WSMessage, exclude: Optional[Set[str]] = None):
        """Broadcast message to all clients"""
        exclude = exclude or set()
        
        tasks = []
        for entity_id, client in self._clients.items():
            if entity_id not in exclude:
                tasks.append(client.send(message.to_json()))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_connected_clients(self) -> Set[str]:
        """Get set of connected client IDs"""
        return set(self._clients.keys())


# Convenience functions
async def create_websocket_client(
    uri: str,
    entity_id: str,
    message_handler: Optional[Callable[[WSMessage], None]] = None
) -> WebSocketClient:
    """Create and connect WebSocket client"""
    client = WebSocketClient(uri, entity_id, message_handler=message_handler)
    await client.connect()
    return client


async def create_websocket_server(
    host: str = "0.0.0.0",
    port: int = 8765,
    message_handler: Optional[Callable[[str, WSMessage], None]] = None
) -> WebSocketServer:
    """Create and start WebSocket server"""
    server = WebSocketServer(host, port, message_handler)
    await server.start()
    return server
