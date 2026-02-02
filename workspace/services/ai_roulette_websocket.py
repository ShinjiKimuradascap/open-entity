"""
AI Roulette WebSocket Handler
Real-time communication for matched agents and observers (Peek Mode)
"""

import asyncio
import json
from typing import Dict, Set, Optional
from datetime import datetime
import websockets
from websockets.server import WebSocketServerProtocol

from services.ai_roulette import (
    roulette_engine, 
    RouletteSession, 
    SessionStatus,
    PrivacyLevel,
    AgentProfile
)


class RouletteWebSocketManager:
    """Manages WebSocket connections for roulette sessions"""
    
    def __init__(self):
        # session_id -> {agent_a: websocket, agent_b: websocket}
        self.session_connections: Dict[str, Dict[str, WebSocketServerProtocol]] = {}
        # session_id -> Set[observer_websockets]
        self.observer_connections: Dict[str, Set[WebSocketServerProtocol]] = {}
        # websocket -> agent_id mapping
        self.connection_agent: Dict[WebSocketServerProtocol, str] = {}
        # websocket -> session_id mapping
        self.connection_session: Dict[WebSocketServerProtocol, str] = {}
        
    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """Handle new WebSocket connection"""
        try:
            # Wait for initial message with agent info
            initial_msg = await websocket.recv()
            data = json.loads(initial_msg)
            
            action = data.get("action")
            agent_id = data.get("agent_id")
            session_id = data.get("session_id")
            
            if action == "join_session":
                await self._handle_join_session(websocket, agent_id, session_id)
            elif action == "observe_session":
                await self._handle_observe_session(websocket, session_id)
            else:
                await websocket.send(json.dumps({
                    "error": "Unknown action"
                }))
                return
                
        except Exception as e:
            await websocket.send(json.dumps({
                "error": f"Connection failed: {str(e)}"
            }))
            return
            
        # Keep connection alive and handle messages
        try:
            async for message in websocket:
                await self._handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            await self._handle_disconnect(websocket)
            
    async def _handle_join_session(self, websocket: WebSocketServerProtocol, 
                                   agent_id: str, session_id: str):
        """Handle agent joining their roulette session"""
        session = roulette_engine.get_session(session_id)
        
        if not session:
            await websocket.send(json.dumps({
                "error": "Session not found"
            }))
            return
            
        if session.status != SessionStatus.ACTIVE:
            await websocket.send(json.dumps({
                "error": f"Session is {session.status.value}"
            }))
            return
            
        # Verify agent is part of session
        if agent_id not in [session.agent_a, session.agent_b]:
            await websocket.send(json.dumps({
                "error": "Not authorized for this session"
            }))
            return
            
        # Store connection
        if session_id not in self.session_connections:
            self.session_connections[session_id] = {}
        self.session_connections[session_id][agent_id] = websocket
        
        self.connection_agent[websocket] = agent_id
        self.connection_session[websocket] = session_id
        
        # Send session info
        await websocket.send(json.dumps({
            "event": "session_joined",
            "session_id": session_id,
            "agent_id": agent_id,
            "partner_id": session.agent_b if agent_id == session.agent_a else session.agent_a,
            "start_time": session.start_time.isoformat() if session.start_time else None,
            "observers_count": len(session.observers)
        }))
        
        # Notify partner if connected
        partner_id = session.agent_b if agent_id == session.agent_a else session.agent_a
        partner_ws = self.session_connections.get(session_id, {}).get(partner_id)
        if partner_ws:
            await partner_ws.send(json.dumps({
                "event": "partner_connected",
                "agent_id": agent_id
            }))
            
    async def _handle_observe_session(self, websocket: WebSocketServerProtocol,
                                      session_id: str):
        """Handle observer joining (Peek Mode - 覗き見モード)"""
        session = roulette_engine.get_session(session_id)
        
        if not session:
            await websocket.send(json.dumps({
                "error": "Session not found"
            }))
            return
            
        # Check privacy level
        if session.privacy_level == PrivacyLevel.PRIVATE:
            await websocket.send(json.dumps({
                "error": "Session is private"
            }))
            return
            
        # Add observer
        observer_id = f"observer_{id(websocket)}"
        success = roulette_engine.add_observer(session_id, observer_id)
        
        if not success:
            await websocket.send(json.dumps({
                "error": "Cannot observe this session"
            }))
            return
            
        # Store connection
        if session_id not in self.observer_connections:
            self.observer_connections[session_id] = set()
        self.observer_connections[session_id].add(websocket)
        
        self.connection_agent[websocket] = observer_id
        self.connection_session[websocket] = session_id
        
        # Send session info (redacted for observers)
        await websocket.send(json.dumps({
            "event": "observing_started",
            "session_id": session_id,
            "agent_a": session.agent_a,
            "agent_b": session.agent_b,
            "start_time": session.start_time.isoformat() if session.start_time else None,
            "message": "You are observing this session. Send reactions with action:react"
        }))
        
        # Notify agents that someone is observing
        for agent_ws in self.session_connections.get(session_id, {}).values():
            await agent_ws.send(json.dumps({
                "event": "observer_joined",
                "observers_count": len(session.observers)
            }))
            
    async def _handle_message(self, websocket: WebSocketServerProtocol, message: str):
        """Handle incoming message from client"""
        try:
            data = json.loads(message)
            action = data.get("action")
            
            if action == "message":
                await self._relay_message(websocket, data)
            elif action == "react":
                await self._handle_reaction(websocket, data)
            elif action == "typing":
                await self._relay_typing(websocket, data)
            elif action == "end_session":
                await self._handle_end_session(websocket)
            else:
                await websocket.send(json.dumps({
                    "error": f"Unknown action: {action}"
                }))
                
        except json.JSONDecodeError:
            await websocket.send(json.dumps({
                "error": "Invalid JSON"
            }))
            
    async def _relay_message(self, sender_ws: WebSocketServerProtocol, data: dict):
        """Relay message between agents and to observers"""
        session_id = self.connection_session.get(sender_ws)
        sender_id = self.connection_agent.get(sender_ws)
        
        if not session_id or not sender_id:
            return
            
        message_data = {
            "event": "message",
            "from": sender_id,
            "content": data.get("content"),
            "timestamp": datetime.now().isoformat()
        }
        
        # Send to partner agent
        session = self.session_connections.get(session_id, {})
        for agent_id, agent_ws in session.items():
            if agent_id != sender_id:
                await agent_ws.send(json.dumps(message_data))
                
        # Send to observers (if public)
        roulette_session = roulette_engine.get_session(session_id)
        if roulette_session and roulette_session.privacy_level == PrivacyLevel.PUBLIC:
            observers = self.observer_connections.get(session_id, set())
            for obs_ws in observers:
                await obs_ws.send(json.dumps({
                    **message_data,
                    "is_observer_copy": True
                }))
                
        # Update message count
        if roulette_session:
            roulette_session.messages_exchanged += 1
            
    async def _handle_reaction(self, observer_ws: WebSocketServerProtocol, data: dict):
        """Handle observer reaction (Peek Mode feature)"""
        session_id = self.connection_session.get(observer_ws)
        observer_id = self.connection_agent.get(observer_ws)
        
        if not session_id:
            return
            
        reaction = data.get("reaction", "👀")
        
        reaction_data = {
            "event": "reaction",
            "from": observer_id,
            "reaction": reaction,
            "timestamp": datetime.now().isoformat()
        }
        
        # Send to agents in session
        agents = self.session_connections.get(session_id, {})
        for agent_ws in agents.values():
            await agent_ws.send(json.dumps(reaction_data))
            
        # Broadcast to other observers
        observers = self.observer_connections.get(session_id, set())
        for obs_ws in observers:
            if obs_ws != observer_ws:
                await obs_ws.send(json.dumps(reaction_data))
                
    async def _relay_typing(self, sender_ws: WebSocketServerProtocol, data: dict):
        """Relay typing indicators"""
        session_id = self.connection_session.get(sender_ws)
        sender_id = self.connection_agent.get(sender_ws)
        
        if not session_id:
            return
            
        typing_data = {
            "event": "typing",
            "from": sender_id,
            "is_typing": data.get("is_typing", True)
        }
        
        # Send to partner
        agents = self.session_connections.get(session_id, {})
        for agent_id, agent_ws in agents.items():
            if agent_id != sender_id:
                await agent_ws.send(json.dumps(typing_data))
                
    async def _handle_end_session(self, websocket: WebSocketServerProtocol):
        """Handle agent requesting session end"""
        session_id = self.connection_session.get(websocket)
        
        if session_id:
            await roulette_engine.end_session(session_id, reason="user_request")
            await self._broadcast_session_end(session_id)
            
    async def _broadcast_session_end(self, session_id: str):
        """Notify all participants that session ended"""
        end_data = {
            "event": "session_ended",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }
        
        # Notify agents
        agents = self.session_connections.pop(session_id, {})
        for agent_ws in agents.values():
            await agent_ws.send(json.dumps(end_data))
            
        # Notify observers
        observers = self.observer_connections.pop(session_id, set())
        for obs_ws in observers:
            await obs_ws.send(json.dumps(end_data))
            
    async def _handle_disconnect(self, websocket: WebSocketServerProtocol):
        """Handle client disconnection"""
        agent_id = self.connection_agent.pop(websocket, None)
        session_id = self.connection_session.pop(websocket, None)
        
        if session_id:
            # Remove from session connections
            session = self.session_connections.get(session_id, {})
            if agent_id in session:
                del session[agent_id]
                
            # Notify partner
            for other_id, other_ws in session.items():
                await other_ws.send(json.dumps({
                    "event": "partner_disconnected",
                    "agent_id": agent_id
                }))
                
            # Remove from observers
            observers = self.observer_connections.get(session_id, set())
            observers.discard(websocket)


# Singleton instance
websocket_manager = RouletteWebSocketManager()


async def start_websocket_server(host: str = "0.0.0.0", port: int = 8765):
    """Start the WebSocket server"""
    server = await websockets.serve(
        websocket_manager.handle_connection,
        host,
        port
    )
    print(f"AI Roulette WebSocket server started on ws://{host}:{port}")
    return server


if __name__ == "__main__":
    # Test server
    asyncio.run(start_websocket_server())
