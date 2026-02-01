#!/usr/bin/env python3
"""
WebSocket Bidding Integration
Integrates BiddingService with WebSocketManager for real-time bidding

Features:
- Broadcast bid requests to connected providers via WebSocket
- Receive bid submissions from providers
- Real-time bid status updates
- Automatic winner selection and notification
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable
from datetime import datetime, timezone

from services.bidding_service import (
    BiddingService, BidRequest, BidSubmission, BidStatus
)
from services.websocket_manager import WebSocketManager, WSMessageType
from services.marketplace_models import AgentProfile

logger = logging.getLogger(__name__)


# WebSocket message types for bidding
class BiddingMessageType:
    """WebSocket message types for bidding protocol"""
    # Bid lifecycle
    BID_REQUEST = "bid_request"           # Consumer broadcasts bid request
    BID_REQUEST_ACK = "bid_request_ack"   # Acknowledgment
    BID_SUBMIT = "bid_submit"             # Provider submits bid
    BID_SUBMIT_ACK = "bid_submit_ack"     # Acknowledgment
    BID_STATUS = "bid_status"             # Status query/update
    BID_RESULT = "bid_result"             # Winner announced
    BID_CANCEL = "bid_cancel"             # Cancel bid request
    
    # Real-time updates
    BID_UPDATE = "bid_update"             # New bid received (broadcast)
    BID_COUNTDOWN = "bid_countdown"       # Time remaining
    BID_EXPIRED = "bid_expired"           # Bid window closed


@dataclass
class WebSocketBidRequest:
    """Extended bid request with WebSocket metadata"""
    bid_request: BidRequest
    consumer_ws_id: str
    broadcasted_at: Optional[float] = None
    submissions: List[BidSubmission] = field(default_factory=list)
    status: str = "pending"  # pending, active, closed, cancelled


class WebSocketBiddingIntegration:
    """
    Integrates BiddingService with WebSocketManager
    
    Provides real-time bidding over WebSocket:
    1. Consumer creates bid request -> broadcast to providers
    2. Providers submit bids via WebSocket
    3. Automatic winner selection on timeout
    4. Real-time notifications to all participants
    """
    
    def __init__(
        self,
        bidding_service: BiddingService,
        websocket_manager: WebSocketManager
    ):
        self.bidding_service = bidding_service
        self.ws_manager = websocket_manager
        
        # Track WebSocket-specific bid state
        self._ws_bids: Dict[str, WebSocketBidRequest] = {}
        
        # Provider capability cache (entity_id -> capabilities)
        self._provider_capabilities: Dict[str, List[str]] = {}
        
        # Callbacks for bid events
        self._on_winner_selected: Optional[Callable[[str, BidSubmission], Awaitable[None]]] = None
        self._on_bid_received: Optional[Callable[[str, BidSubmission], Awaitable[None]]] = None
        
        # Statistics
        self._stats = {
            "requests_broadcasted": 0,
            "submissions_received": 0,
            "winners_selected": 0,
            "notifications_sent": 0
        }
    
    def register_handlers(self) -> None:
        """Register WebSocket message handlers for bidding"""
        self.ws_manager.register_handler(
            BiddingMessageType.BID_REQUEST,
            self._handle_bid_request
        )
        self.ws_manager.register_handler(
            BiddingMessageType.BID_SUBMIT,
            self._handle_bid_submit
        )
        self.ws_manager.register_handler(
            BiddingMessageType.BID_STATUS,
            self._handle_bid_status
        )
        self.ws_manager.register_handler(
            BiddingMessageType.BID_CANCEL,
            self._handle_bid_cancel
        )
        logger.info("Registered WebSocket bidding handlers")
    
    def set_winner_callback(
        self,
        callback: Callable[[str, BidSubmission], Awaitable[None]]
    ) -> None:
        """Set callback for winner selection events"""
        self._on_winner_selected = callback
    
    def set_bid_received_callback(
        self,
        callback: Callable[[str, BidSubmission], Awaitable[None]]
    ) -> None:
        """Set callback for bid submission events"""
        self._on_bid_received = callback
    
    async def create_and_broadcast_bid_request(
        self,
        consumer_id: str,
        service_category: str,
        requirements: Dict[str, Any],
        criteria: Dict[str, float],
        timeout_ms: int = 5000,
        escrow_deposit: int = 0,
        target_capabilities: Optional[List[str]] = None
    ) -> Optional[BidRequest]:
        """
        Create a bid request and broadcast to providers
        
        Args:
            consumer_id: Consumer's entity ID
            service_category: Service category
            requirements: Task requirements
            criteria: Selection criteria weights
            timeout_ms: Bid submission timeout
            escrow_deposit: Token deposit amount
            target_capabilities: Required provider capabilities (optional filter)
        
        Returns:
            BidRequest if created and broadcast, None otherwise
        """
        # Create bid request via BiddingService
        bid_request = await self.bidding_service.create_bid_request(
            consumer_id=consumer_id,
            service_category=service_category,
            requirements=requirements,
            criteria=criteria,
            timeout_ms=timeout_ms,
            escrow_deposit=escrow_deposit
        )
        
        if not bid_request:
            logger.warning(f"Failed to create bid request for {consumer_id}")
            return None
        
        # Track WebSocket state
        ws_bid = WebSocketBidRequest(
            bid_request=bid_request,
            consumer_ws_id=consumer_id,
            broadcasted_at=time.time()
        )
        self._ws_bids[bid_request.bid_id] = ws_bid
        
        # Broadcast to providers
        await self._broadcast_bid_request(
            bid_request,
            target_capabilities
        )
        
        # Schedule timeout handling
        asyncio.create_task(
            self._handle_bid_timeout(bid_request.bid_id, timeout_ms)
        )
        
        self._stats["requests_broadcasted"] += 1
        
        logger.info(
            f"Created and broadcast bid {bid_request.bid_id} "
            f"from {consumer_id} for {service_category}"
        )
        
        return bid_request
    
    async def _broadcast_bid_request(
        self,
        bid_request: BidRequest,
        target_capabilities: Optional[List[str]] = None
    ) -> int:
        """
        Broadcast bid request to connected providers
        
        Args:
            bid_request: The bid request to broadcast
            target_capabilities: Only broadcast to providers with these capabilities
        
        Returns:
            Number of providers notified
        """
        message = {
            "type": BiddingMessageType.BID_REQUEST,
            "payload": {
                "bid_id": bid_request.bid_id,
                "consumer_id": bid_request.consumer_id,
                "service_category": bid_request.service_category,
                "requirements": bid_request.requirements,
                "criteria": bid_request.criteria,
                "timeout_ms": bid_request.timeout_ms,
                "escrow_deposit": bid_request.escrow_deposit,
                "created_at": bid_request.created_at,
                "expires_at": bid_request.created_at + (bid_request.timeout_ms / 1000)
            }
        }
        
        # Broadcast with capability filter if specified
        if target_capabilities:
            # Check each peer's capabilities
            sent_count = 0
            for entity_id in self.ws_manager.get_connected_peers():
                peer_caps = self.ws_manager.get_peer_capabilities(entity_id) or set()
                if all(cap in peer_caps for cap in target_capabilities):
                    if await self.ws_manager.send_to_peer(entity_id, message):
                        sent_count += 1
            return sent_count
        else:
            # Broadcast to all
            return await self.ws_manager.broadcast(
                message,
                exclude=bid_request.consumer_id
            )
    
    async def _handle_bid_request(
        self,
        entity_id: str,
        message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle incoming bid request from consumer
        
        Note: In practice, bid requests are typically created via API
        and then broadcast. This handler supports direct WS creation.
        """
        payload = message.get("payload", {})
        
        # Validate required fields
        required = ["service_category", "requirements", "criteria"]
        if not all(f in payload for f in required):
            return {
                "type": BiddingMessageType.BID_REQUEST_ACK,
                "payload": {
                    "success": False,
                    "error": "Missing required fields"
                }
            }
        
        # Create and broadcast
        bid_request = await self.create_and_broadcast_bid_request(
            consumer_id=entity_id,
            service_category=payload["service_category"],
            requirements=payload["requirements"],
            criteria=payload["criteria"],
            timeout_ms=payload.get("timeout_ms", 5000),
            escrow_deposit=payload.get("escrow_deposit", 0),
            target_capabilities=payload.get("target_capabilities")
        )
        
        if bid_request:
            return {
                "type": BiddingMessageType.BID_REQUEST_ACK,
                "payload": {
                    "success": True,
                    "bid_id": bid_request.bid_id,
                    "timeout_ms": bid_request.timeout_ms
                }
            }
        else:
            return {
                "type": BiddingMessageType.BID_REQUEST_ACK,
                "payload": {
                    "success": False,
                    "error": "Failed to create bid request (rate limit or validation error)"
                }
            }
    
    async def _handle_bid_submit(
        self,
        entity_id: str,
        message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle bid submission from provider"""
        payload = message.get("payload", {})
        
        bid_id = payload.get("bid_id")
        if not bid_id:
            return {
                "type": BiddingMessageType.BID_SUBMIT_ACK,
                "payload": {"success": False, "error": "Missing bid_id"}
            }
        
        # Check if bid is still active
        if bid_id not in self._ws_bids:
            return {
                "type": BiddingMessageType.BID_SUBMIT_ACK,
                "payload": {"success": False, "error": "Bid request not found or expired"}
            }
        
        ws_bid = self._ws_bids[bid_id]
        if ws_bid.status != "pending":
            return {
                "type": BiddingMessageType.BID_SUBMIT_ACK,
                "payload": {"success": False, "error": "Bid request is no longer active"}
            }
        
        # Submit via BiddingService
        submission = await self.bidding_service.submit_bid(
            bid_id=bid_id,
            provider_id=entity_id,
            service_id=payload.get("service_id", ""),
            price=payload.get("price", 0),
            estimated_time_ms=payload.get("estimated_time_ms", 0),
            confidence=payload.get("confidence", 0.5),
            reputation_score=payload.get("reputation_score", 0.0),
            completed_tasks=payload.get("completed_tasks", 0),
            success_rate=payload.get("success_rate", 0.0)
        )
        
        if not submission:
            return {
                "type": BiddingMessageType.BID_SUBMIT_ACK,
                "payload": {"success": False, "error": "Bid submission rejected"}
            }
        
        # Track in WebSocket state
        ws_bid.submissions.append(submission)
        self._stats["submissions_received"] += 1
        
        # Notify consumer of new bid
        await self._notify_new_bid(ws_bid, submission)
        
        # Trigger callback if set
        if self._on_bid_received:
            await self._on_bid_received(bid_id, submission)
        
        logger.info(f"Provider {entity_id} submitted bid for {bid_id} at price {submission.price}")
        
        return {
            "type": BiddingMessageType.BID_SUBMIT_ACK,
            "payload": {
                "success": True,
                "bid_id": bid_id,
                "provider_id": entity_id,
                "status": submission.status.value
            }
        }
    
    async def _notify_new_bid(
        self,
        ws_bid: WebSocketBidRequest,
        submission: BidSubmission
    ) -> None:
        """Notify consumer of new bid submission"""
        message = {
            "type": BiddingMessageType.BID_UPDATE,
            "payload": {
                "bid_id": ws_bid.bid_request.bid_id,
                "provider_id": submission.provider_id,
                "price": submission.price,
                "estimated_time_ms": submission.estimated_time_ms,
                "confidence": submission.confidence,
                "reputation_score": submission.reputation_score,
                "total_submissions": len(ws_bid.submissions),
                "time_remaining_ms": max(
                    0,
                    int(
                        (ws_bid.bid_request.created_at + ws_bid.bid_request.timeout_ms / 1000 - time.time()) * 1000
                    )
                )
            }
        }
        
        await self.ws_manager.send_to_peer(
            ws_bid.consumer_ws_id,
            message
        )
        self._stats["notifications_sent"] += 1
    
    async def _handle_bid_status(
        self,
        entity_id: str,
        message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle bid status query"""
        payload = message.get("payload", {})
        bid_id = payload.get("bid_id")
        
        if not bid_id:
            return {
                "type": BiddingMessageType.BID_STATUS,
                "payload": {"error": "Missing bid_id"}
            }
        
        # Get status from BiddingService
        status = self.bidding_service.get_bid_status(bid_id)
        
        # Enhance with WebSocket state
        if bid_id in self._ws_bids:
            ws_bid = self._ws_bids[bid_id]
            status["ws_status"] = ws_bid.status
            status["broadcasted_at"] = ws_bid.broadcasted_at
        
        return {
            "type": BiddingMessageType.BID_STATUS,
            "payload": status
        }
    
    async def _handle_bid_cancel(
        self,
        entity_id: str,
        message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle bid cancellation request"""
        payload = message.get("payload", {})
        bid_id = payload.get("bid_id")
        
        if not bid_id or bid_id not in self._ws_bids:
            return {
                "type": BiddingMessageType.BID_CANCEL,
                "payload": {"success": False, "error": "Bid not found"}
            }
        
        ws_bid = self._ws_bids[bid_id]
        
        # Only consumer can cancel
        if ws_bid.consumer_ws_id != entity_id:
            return {
                "type": BiddingMessageType.BID_CANCEL,
                "payload": {"success": False, "error": "Only consumer can cancel"}
            }
        
        # Mark as cancelled
        ws_bid.status = "cancelled"
        
        # Notify all bidders
        await self._broadcast_bid_result(bid_id, None, "cancelled")
        
        logger.info(f"Bid {bid_id} cancelled by consumer {entity_id}")
        
        return {
            "type": BiddingMessageType.BID_CANCEL,
            "payload": {"success": True, "bid_id": bid_id}
        }
    
    async def _handle_bid_timeout(self, bid_id: str, timeout_ms: int) -> None:
        """Handle bid timeout and winner selection"""
        await asyncio.sleep(timeout_ms / 1000)
        
        if bid_id not in self._ws_bids:
            return
        
        ws_bid = self._ws_bids[bid_id]
        
        # Skip if already closed or cancelled
        if ws_bid.status != "pending":
            return
        
        ws_bid.status = "closed"
        
        # Select winner
        winner = await self.bidding_service.select_winner(bid_id, auto_select=True)
        
        # Broadcast result
        await self._broadcast_bid_result(bid_id, winner, "completed")
        
        self._stats["winners_selected"] += 1
        
        if winner:
            logger.info(
                f"Bid {bid_id} completed. Winner: {winner.provider_id} "
                f"at price {winner.price}"
            )
            
            # Trigger callback
            if self._on_winner_selected:
                await self._on_winner_selected(bid_id, winner)
        else:
            logger.info(f"Bid {bid_id} completed with no winner")
    
    async def _broadcast_bid_result(
        self,
        bid_id: str,
        winner: Optional[BidSubmission],
        result_status: str
    ) -> int:
        """Broadcast bid result to all participants"""
        ws_bid = self._ws_bids.get(bid_id)
        if not ws_bid:
            return 0
        
        # Notify consumer
        consumer_message = {
            "type": BiddingMessageType.BID_RESULT,
            "payload": {
                "bid_id": bid_id,
                "status": result_status,
                "winner": {
                    "provider_id": winner.provider_id,
                    "price": winner.price,
                    "estimated_time_ms": winner.estimated_time_ms,
                    "reputation_score": winner.reputation_score
                } if winner else None,
                "total_submissions": len(ws_bid.submissions),
                "submissions": [
                    {
                        "provider_id": s.provider_id,
                        "price": s.price,
                        "status": s.status.value
                    }
                    for s in ws_bid.submissions
                ]
            }
        }
        
        await self.ws_manager.send_to_peer(
            ws_bid.consumer_ws_id,
            consumer_message
        )
        
        # Notify all providers
        provider_message = {
            "type": BiddingMessageType.BID_RESULT,
            "payload": {
                "bid_id": bid_id,
                "status": result_status,
                "winner": {
                    "provider_id": winner.provider_id,
                    "price": winner.price
                } if winner else None,
                "you_won": False  # Will be True for winner
            }
        }
        
        sent_count = 0
        for submission in ws_bid.submissions:
            msg = provider_message.copy()
            msg["payload"] = msg["payload"].copy()
            msg["payload"]["you_won"] = (winner and submission.provider_id == winner.provider_id)
            
            if await self.ws_manager.send_to_peer(submission.provider_id, msg):
                sent_count += 1
        
        self._stats["notifications_sent"] += sent_count + 1
        
        return sent_count + 1  # +1 for consumer
    
    def get_stats(self) -> Dict[str, Any]:
        """Get integration statistics"""
        return {
            **self._stats,
            "active_ws_bids": len([b for b in self._ws_bids.values() if b.status == "pending"]),
            "total_ws_bids": len(self._ws_bids)
        }
    
    def get_active_bids(self) -> List[Dict[str, Any]]:
        """Get list of active bid requests"""
        return [
            {
                "bid_id": wb.bid_request.bid_id,
                "consumer_id": wb.bid_request.consumer_id,
                "service_category": wb.bid_request.service_category,
                "status": wb.status,
                "submissions_count": len(wb.submissions),
                "time_remaining_ms": max(
                    0,
                    int(
                        (wb.bid_request.created_at + wb.bid_request.timeout_ms / 1000 - time.time()) * 1000
                    )
                )
            }
            for wb in self._ws_bids.values()
            if wb.status == "pending"
        ]


# Singleton instance
_ws_bidding_integration: Optional[WebSocketBiddingIntegration] = None


def get_websocket_bidding_integration(
    bidding_service: Optional[BiddingService] = None,
    websocket_manager: Optional[WebSocketManager] = None
) -> WebSocketBiddingIntegration:
    """Get or create singleton WebSocket bidding integration"""
    global _ws_bidding_integration
    if _ws_bidding_integration is None:
        if bidding_service is None:
            from services.bidding_service import get_bidding_service
            bidding_service = get_bidding_service()
        if websocket_manager is None:
            from services.websocket_manager import get_websocket_manager
            websocket_manager = get_websocket_manager()
        
        _ws_bidding_integration = WebSocketBiddingIntegration(
            bidding_service=bidding_service,
            websocket_manager=websocket_manager
        )
    return _ws_bidding_integration


async def init_websocket_bidding_integration() -> WebSocketBiddingIntegration:
    """Initialize and register WebSocket bidding integration"""
    integration = get_websocket_bidding_integration()
    integration.register_handlers()
    return integration


# Example usage / demo
async def demo():
    """Demo of WebSocket bidding integration"""
    logging.basicConfig(level=logging.INFO)
    
    # Initialize services
    from services.bidding_service import get_bidding_service
    from services.websocket_manager import get_websocket_manager
    
    bidding_service = get_bidding_service()
    await bidding_service.start()
    
    ws_manager = get_websocket_manager()
    await ws_manager.start()
    
    # Initialize integration
    integration = await init_websocket_bidding_integration()
    
    # Set callbacks
    async def on_winner(bid_id: str, winner: BidSubmission):
        print(f"🎉 Winner selected for {bid_id}: {winner.provider_id} at ${winner.price}")
    
    async def on_bid(bid_id: str, submission: BidSubmission):
        print(f"💰 New bid for {bid_id} from {submission.provider_id}: ${submission.price}")
    
    integration.set_winner_callback(on_winner)
    integration.set_bid_received_callback(on_bid)
    
    print("WebSocket Bidding Integration ready!")
    print(f"Stats: {integration.get_stats()}")
    
    # Simulate bid request (would be triggered by WebSocket in real usage)
    bid_request = await integration.create_and_broadcast_bid_request(
        consumer_id="demo_consumer",
        service_category="code_review",
        requirements={"language": "python", "complexity": "medium"},
        criteria={"price_weight": 0.4, "reputation_weight": 0.4, "speed_weight": 0.2},
        timeout_ms=3000
    )
    
    if bid_request:
        print(f"Created bid request: {bid_request.bid_id}")
        
        # Simulate provider bids
        await bidding_service.submit_bid(
            bid_id=bid_request.bid_id,
            provider_id="provider_001",
            service_id="svc_001",
            price=80,
            estimated_time_ms=2000,
            confidence=0.95,
            reputation_score=4.5,
            completed_tasks=100,
            success_rate=0.98
        )
        
        await bidding_service.submit_bid(
            bid_id=bid_request.bid_id,
            provider_id="provider_002",
            service_id="svc_002",
            price=60,
            estimated_time_ms=3000,
            confidence=0.90,
            reputation_score=4.0,
            completed_tasks=50,
            success_rate=0.95
        )
        
        # Wait for timeout
        await asyncio.sleep(3.5)
    
    # Cleanup
    await bidding_service.stop()
    await ws_manager.stop()
    
    print(f"Final stats: {integration.get_stats()}")


if __name__ == "__main__":
    asyncio.run(demo())
