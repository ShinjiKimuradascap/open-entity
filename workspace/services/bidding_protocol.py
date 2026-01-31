#!/usr/bin/env python3
"""
WebSocket Bidding Protocol
Real-time competitive bidding for v1.3 multi-agent marketplace
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Callable
from dataclasses import asdict

try:
    from services.marketplace_models import Bid, TaskRequest, BidStatus
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BiddingProtocol:
    """
    WebSocket-based competitive bidding protocol
    
    Features:
    - Real-time bid submission
    - 5-second bidding window
    - Automatic winner selection
    - Anti-sniping protection
    """
    
    BID_WINDOW_SECONDS = 5
    ANTI_SNIPING_EXTENSION = 2  # Extend if bid in last 2 seconds
    
    def __init__(self):
        self.active_sessions: Dict[str, "BiddingSession"] = {}
        self.bid_handlers: List[Callable] = []
        logger.info("BiddingProtocol initialized")
    
    async def create_session(
        self,
        task_request: "TaskRequest",
        eligible_agents: List[str]
    ) -> "BiddingSession":
        """Create new bidding session"""
        session = BiddingSession(
            task_request=task_request,
            eligible_agents=set(eligible_agents),
            protocol=self
        )
        self.active_sessions[task_request.request_id] = session
        logger.info(f"Created bidding session: {task_request.request_id}")
        return session
    
    async def submit_bid(
        self,
        session_id: str,
        bid: Bid,
        agent_signature: str
    ) -> bool:
        """Submit bid to active session"""
        if session_id not in self.active_sessions:
            logger.warning(f"Session not found: {session_id}")
            return False
        
        session = self.active_sessions[session_id]
        return await session.submit_bid(bid, agent_signature)
    
    def register_bid_handler(self, handler: Callable):
        """Register callback for bid events"""
        self.bid_handlers.append(handler)
    
    async def _notify_bid_handlers(self, event: dict):
        """Notify all registered handlers"""
        for handler in self.bid_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Bid handler error: {e}")


class BiddingSession:
    """Individual bidding session state"""
    
    def __init__(
        self,
        task_request: "TaskRequest",
        eligible_agents: set,
        protocol: BiddingProtocol
    ):
        self.task_request = task_request
        self.eligible_agents = eligible_agents
        self.protocol = protocol
        
        self.bids: Dict[str, Bid] = {}
        self.start_time: float = 0
        self.end_time: float = 0
        self.is_open: bool = False
        self.winner: Optional[Bid] = None
        
        self._lock = asyncio.Lock()
    
    async def start(self) -> List[Bid]:
        """Start bidding session and return results"""
        self.start_time = time.time()
        self.end_time = self.start_time + BiddingProtocol.BID_WINDOW_SECONDS
        self.is_open = True
        
        logger.info(f"Bidding started for {self.task_request.request_id}")
        
        # Notify eligible agents
        await self._notify_agents()
        
        # Wait for bidding window
        await self._wait_for_bids()
        
        # Close session
        self.is_open = False
        
        # Select winner
        self.winner = self._select_winner()
        
        logger.info(f"Bidding complete. Winner: {self.winner.bid_id if self.winner else 'None'}")
        
        return list(self.bids.values())
    
    async def _notify_agents(self):
        """Notify eligible agents of bidding opportunity"""
        event = {
            "type": "bidding_open",
            "task_id": self.task_request.request_id,
            "service_id": self.task_request.service_id,
            "max_price": self.task_request.max_price,
            "requirements": self.task_request.requirements,
            "deadline": self.end_time
        }
        await self.protocol._notify_bid_handlers(event)
    
    async def _wait_for_bids(self):
        """Wait for bidding window with anti-sniping"""
        while time.time() < self.end_time:
            remaining = self.end_time - time.time()
            if remaining > 0:
                await asyncio.sleep(min(0.1, remaining))
            else:
                break
    
    async def submit_bid(
        self,
        bid: Bid,
        agent_signature: str
    ) -> bool:
        """Submit bid to this session"""
        async with self._lock:
            if not self.is_open:
                logger.warning("Bidding session closed")
                return False
            
            if bid.agent_id not in self.eligible_agents:
                logger.warning(f"Agent {bid.agent_id} not eligible")
                return False
            
            if bid.price > self.task_request.max_price:
                logger.warning(f"Bid price {bid.price} exceeds max")
                return False
            
            # Store bid
            self.bids[bid.bid_id] = bid
            
            # Anti-sniping: extend if bid in last seconds
            remaining = self.end_time - time.time()
            if remaining < BiddingProtocol.ANTI_SNIPING_EXTENSION:
                self.end_time += BiddingProtocol.ANTI_SNIPING_EXTENSION
                logger.info(f"Anti-sniping: extended deadline by {BiddingProtocol.ANTI_SNIPING_EXTENSION}s")
            
            # Notify
            await self.protocol._notify_bid_handlers({
                "type": "bid_received",
                "task_id": self.task_request.request_id,
                "bid_id": bid.bid_id,
                "agent_id": bid.agent_id,
                "price": bid.price
            })
            
            return True
    
    def _select_winner(self) -> Optional[Bid]:
        """Select winning bid based on price and reputation"""
        if not self.bids:
            return None
        
        # Sort by price (lowest first)
        sorted_bids = sorted(self.bids.values(), key=lambda b: b.price)
        
        # Return lowest price bid
        # In production, would use selection score from marketplace_models
        return sorted_bids[0]
    
    def get_status(self) -> dict:
        """Get session status"""
        return {
            "task_id": self.task_request.request_id,
            "is_open": self.is_open,
            "bid_count": len(self.bids),
            "time_remaining": max(0, self.end_time - time.time()),
            "winner": self.winner.bid_id if self.winner else None
        }


class WebSocketBiddingHandler:
    """WebSocket handler for bidding protocol"""
    
    def __init__(self, bidding_protocol: BiddingProtocol):
        self.protocol = bidding_protocol
        self.connections: Dict[str, "WebSocketConnection"] = {}
    
    async def handle_connection(
        self,
        websocket: "WebSocket",
        agent_id: str
    ):
        """Handle WebSocket connection from agent"""
        self.connections[agent_id] = websocket
        logger.info(f"Agent connected: {agent_id}")
        
        try:
            async for message in websocket:
                await self._handle_message(agent_id, message)
        except Exception as e:
            logger.error(f"Connection error for {agent_id}: {e}")
        finally:
            del self.connections[agent_id]
            logger.info(f"Agent disconnected: {agent_id}")
    
    async def _handle_message(self, agent_id: str, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "bid_submit":
                await self._handle_bid_submit(agent_id, data)
            elif msg_type == "bid_status":
                await self._handle_bid_status(agent_id, data)
            else:
                logger.warning(f"Unknown message type: {msg_type}")
        
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from {agent_id}")
    
    async def _handle_bid_submit(self, agent_id: str, data: dict):
        """Handle bid submission"""
        if not MODELS_AVAILABLE:
            return
        
        session_id = data.get("task_id")
        bid_data = data.get("bid", {})
        
        bid = Bid(
            bid_id=bid_data.get("bid_id", ""),
            task_id=session_id,
            agent_id=agent_id,
            price=bid_data.get("price", 0.0),
            estimated_time=bid_data.get("estimated_time", 0),
            proposal=bid_data.get("proposal", "")
        )
        
        signature = data.get("signature", "")
        success = await self.protocol.submit_bid(session_id, bid, signature)
        
        # Send response
        if agent_id in self.connections:
            await self.connections[agent_id].send(json.dumps({
                "type": "bid_ack",
                "bid_id": bid.bid_id,
                "accepted": success
            }))
    
    async def _handle_bid_status(self, agent_id: str, data: dict):
        """Handle status request"""
        session_id = data.get("task_id")
        if session_id in self.protocol.active_sessions:
            status = self.protocol.active_sessions[session_id].get_status()
            if agent_id in self.connections:
                await self.connections[agent_id].send(json.dumps({
                    "type": "bid_status",
                    "status": status
                }))


# Global instance
_bidding_protocol: Optional[BiddingProtocol] = None


def get_bidding_protocol() -> BiddingProtocol:
    """Get or create global bidding protocol instance"""
    global _bidding_protocol
    if _bidding_protocol is None:
        _bidding_protocol = BiddingProtocol()
    return _bidding_protocol
