#!/usr/bin/env python3
"""
Competitive Bidding Protocol for AI Multi-Agent Marketplace

v1.3 Feature: 5-second competitive bidding window
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Callable
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class BidStatus(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Bid:
    """Service bid from a provider"""
    bid_id: str
    request_id: str
    provider_id: str
    price: Decimal
    estimated_time: int  # seconds
    reputation_score: float  # 0.0 - 1.0
    capabilities: List[str]
    timestamp: datetime
    status: BidStatus = BidStatus.PENDING
    
    def calculate_score(self) -> float:
        """Calculate selection score"""
        # Price score (lower is better, normalized)
        price_score = max(0, 1.0 - (float(self.price) / 100))
        
        # Speed score (faster is better)
        speed_score = max(0, 1.0 - (self.estimated_time / 3600))
        
        # Selection formula: reputation * 0.4 + speed * 0.3 + price * 0.3
        score = (self.reputation_score * 0.4) + (speed_score * 0.3) + (price_score * 0.3)
        return score


@dataclass
class BidRequest:
    """Service request for bidding"""
    request_id: str
    service_type: str
    requirements: Dict
    max_price: Decimal
    timeout: int = 5  # 5-second bidding window
    created_at: datetime = field(default_factory=datetime.utcnow)
    bids: Dict[str, Bid] = field(default_factory=dict)
    

class BiddingEngine:
    """
    Competitive bidding engine for service requests.
    
    Features:
    - 5-second bidding window
    - Multi-dimensional scoring
    - Automatic winner selection
    """
    
    BIDDING_WINDOW = 5  # seconds
    
    def __init__(self):
        self.active_requests: Dict[str, BidRequest] = {}
        self.completed_requests: Dict[str, BidRequest] = {}
        self._lock = asyncio.Lock()
    
    async def create_request(
        self,
        service_type: str,
        requirements: Dict,
        max_price: Decimal
    ) -> str:
        """Create a new bid request"""
        request_id = str(uuid.uuid4())
        request = BidRequest(
            request_id=request_id,
            service_type=service_type,
            requirements=requirements,
            max_price=max_price,
            timeout=self.BIDDING_WINDOW
        )
        
        async with self._lock:
            self.active_requests[request_id] = request
        
        logger.info(f"Bid request created: {request_id}")
        return request_id
    
    async def submit_bid(
        self,
        request_id: str,
        provider_id: str,
        price: Decimal,
        estimated_time: int,
        reputation_score: float,
        capabilities: List[str]
    ) -> Optional[str]:
        """Submit a bid for a request"""
        async with self._lock:
            if request_id not in self.active_requests:
                logger.warning(f"Bid rejected: request {request_id} not found")
                return None
            
            request = self.active_requests[request_id]
            
            # Check price constraint
            if price > request.max_price:
                logger.warning(f"Bid rejected: price {price} exceeds max {request.max_price}")
                return None
            
            bid_id = str(uuid.uuid4())
            bid = Bid(
                bid_id=bid_id,
                request_id=request_id,
                provider_id=provider_id,
                price=price,
                estimated_time=estimated_time,
                reputation_score=reputation_score,
                capabilities=capabilities,
                timestamp=datetime.utcnow()
            )
            
            request.bids[provider_id] = bid
            logger.info(f"Bid submitted: {bid_id} from {provider_id}")
            return bid_id
    
    async def close_bidding(self, request_id: str) -> Optional[Bid]:
        """Close bidding and select winner"""
        async with self._lock:
            if request_id not in self.active_requests:
                return None
            
            request = self.active_requests.pop(request_id)
            
            if not request.bids:
                logger.info(f"No bids for request {request_id}")
                self.completed_requests[request_id] = request
                return None
            
            # Select winner by highest score
            winner = max(request.bids.values(), key=lambda b: b.calculate_score())
            winner.status = BidStatus.ACCEPTED
            
            # Mark others as rejected
            for bid in request.bids.values():
                if bid.bid_id != winner.bid_id:
                    bid.status = BidStatus.REJECTED
            
            self.completed_requests[request_id] = request
            logger.info(f"Winner selected for {request_id}: {winner.provider_id}")
            return winner
    
    async def run_bidding_process(
        self,
        service_type: str,
        requirements: Dict,
        max_price: Decimal,
        notify_providers: Callable
    ) -> Optional[Bid]:
        """
        Run complete bidding process:
        1. Create request
        2. Notify providers
        3. Wait for bidding window
        4. Select winner
        """
        request_id = await self.create_request(service_type, requirements, max_price)
        
        # Notify providers
        await notify_providers(request_id, service_type, requirements)
        
        # Wait for bidding window
        logger.info(f"Bidding window open for {self.BIDDING_WINDOW} seconds")
        await asyncio.sleep(self.BIDDING_WINDOW)
        
        # Close and select winner
        winner = await self.close_bidding(request_id)
        return winner
    
    def get_request_status(self, request_id: str) -> Optional[Dict]:
        """Get bidding status for a request"""
        if request_id in self.active_requests:
            request = self.active_requests[request_id]
            return {
                "status": "active",
                "bids_count": len(request.bids),
                "time_remaining": self.BIDDING_WINDOW
            }
        
        if request_id in self.completed_requests:
            request = self.completed_requests[request_id]
            winner = next((b for b in request.bids.values() if b.status == BidStatus.ACCEPTED), None)
            return {
                "status": "completed",
                "bids_count": len(request.bids),
                "winner": winner.provider_id if winner else None
            }
        
        return None
