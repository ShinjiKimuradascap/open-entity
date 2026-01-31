"""
Bidding Service for AI Marketplace
Handles real-time bidding over WebSocket
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class BidStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class BidRequest:
    """Consumer's bid request"""
    bid_id: str
    consumer_id: str
    service_category: str
    requirements: Dict[str, Any]
    criteria: Dict[str, float]  # price_weight, reputation_weight, speed_weight
    timeout_ms: int
    escrow_deposit: int
    created_at: float = field(default_factory=time.time)
    
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) * 1000 > self.timeout_ms


@dataclass
class BidSubmission:
    """Provider's bid submission"""
    bid_id: str
    provider_id: str
    service_id: str
    price: int
    estimated_time_ms: int
    confidence: float
    reputation_score: float
    completed_tasks: int
    success_rate: float
    submitted_at: float = field(default_factory=time.time)
    status: BidStatus = BidStatus.SUBMITTED
    
    def calculate_score(self, criteria: Dict[str, float], 
                       price_range: tuple, time_range: tuple) -> float:
        """Calculate bid score based on selection criteria"""
        min_price, max_price = price_range
        min_time, max_time = time_range
        
        # Normalize price (lower is better)
        if max_price > min_price:
            price_score = 1 - (self.price - min_price) / (max_price - min_price)
        else:
            price_score = 1.0
        
        # Reputation score (normalized 0-1)
        reputation_score = min(self.reputation_score / 5.0, 1.0)
        
        # Speed score (faster is better)
        if max_time > min_time:
            speed_score = 1 - (self.estimated_time_ms - min_time) / (max_time - min_time)
        else:
            speed_score = 1.0
        
        # Weighted sum
        total_score = (
            price_score * criteria.get("price_weight", 0.4) +
            reputation_score * criteria.get("reputation_weight", 0.4) +
            speed_score * criteria.get("speed_weight", 0.2)
        )
        
        return total_score


class BiddingService:
    """
    Real-time bidding service for AI marketplace
    Manages bid requests, submissions, and selection
    """
    
    def __init__(self):
        self.active_requests: Dict[str, BidRequest] = {}
        self.bid_submissions: Dict[str, List[BidSubmission]] = {}
        self.selection_callbacks: Dict[str, Callable] = {}
        
        # Rate limiting
        self.consumer_request_count: Dict[str, List[float]] = {}
        self.provider_bid_count: Dict[str, List[float]] = {}
        
        # Config
        self.max_requests_per_minute = 10
        self.max_bids_per_minute = 60
        self.cleanup_interval = 60  # seconds
        
        # Start cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the bidding service"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Bidding service started")
    
    async def stop(self):
        """Stop the bidding service"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Bidding service stopped")
    
    async def create_bid_request(
        self,
        consumer_id: str,
        service_category: str,
        requirements: Dict[str, Any],
        criteria: Dict[str, float],
        timeout_ms: int = 5000,
        escrow_deposit: int = 0
    ) -> Optional[BidRequest]:
        """
        Create a new bid request
        
        Args:
            consumer_id: ID of the requesting agent
            service_category: Category of service needed
            requirements: Task specifications
            criteria: Selection weights (price_weight, reputation_weight, speed_weight)
            timeout_ms: Bid submission deadline
            escrow_deposit: Token amount to lock
        
        Returns:
            BidRequest if created, None if rate limited
        """
        # Check rate limit
        if not self._check_consumer_rate_limit(consumer_id):
            logger.warning(f"Rate limit exceeded for consumer {consumer_id}")
            return None
        
        # Normalize criteria weights
        total_weight = sum(criteria.values())
        if total_weight > 0:
            criteria = {k: v / total_weight for k, v in criteria.items()}
        
        bid_id = f"bid_{uuid.uuid4().hex[:16]}"
        request = BidRequest(
            bid_id=bid_id,
            consumer_id=consumer_id,
            service_category=service_category,
            requirements=requirements,
            criteria=criteria,
            timeout_ms=timeout_ms,
            escrow_deposit=escrow_deposit
        )
        
        self.active_requests[bid_id] = request
        self.bid_submissions[bid_id] = []
        
        logger.info(f"Created bid request {bid_id} from consumer {consumer_id}")
        
        # Schedule automatic expiration
        asyncio.create_task(self._expire_bid_request(bid_id, timeout_ms))
        
        return request
    
    async def submit_bid(
        self,
        bid_id: str,
        provider_id: str,
        service_id: str,
        price: int,
        estimated_time_ms: int,
        confidence: float,
        reputation_score: float,
        completed_tasks: int,
        success_rate: float
    ) -> Optional[BidSubmission]:
        """
        Submit a bid for a bid request
        
        Returns:
            BidSubmission if accepted, None if rejected
        """
        # Check rate limit
        if not self._check_provider_rate_limit(provider_id):
            logger.warning(f"Rate limit exceeded for provider {provider_id}")
            return None
        
        # Check if bid request exists and is active
        if bid_id not in self.active_requests:
            logger.warning(f"Bid request {bid_id} not found or expired")
            return None
        
        request = self.active_requests[bid_id]
        
        # Check if expired
        if request.is_expired():
            logger.warning(f"Bid request {bid_id} has expired")
            return None
        
        # Check if already submitted
        existing = [b for b in self.bid_submissions[bid_id] if b.provider_id == provider_id]
        if existing:
            logger.warning(f"Provider {provider_id} already submitted bid for {bid_id}")
            return None
        
        # Create submission
        submission = BidSubmission(
            bid_id=bid_id,
            provider_id=provider_id,
            service_id=service_id,
            price=price,
            estimated_time_ms=estimated_time_ms,
            confidence=confidence,
            reputation_score=reputation_score,
            completed_tasks=completed_tasks,
            success_rate=success_rate
        )
        
        self.bid_submissions[bid_id].append(submission)
        
        logger.info(f"Provider {provider_id} submitted bid for {bid_id} at price {price}")
        
        return submission
    
    async def select_winner(
        self,
        bid_id: str,
        auto_select: bool = True
    ) -> Optional[BidSubmission]:
        """
        Select winning bid
        
        Args:
            bid_id: Bid request ID
            auto_select: If True, use algorithm; if False, wait for manual selection
        
        Returns:
            Winning BidSubmission or None
        """
        if bid_id not in self.active_requests:
            logger.warning(f"Bid request {bid_id} not found")
            return None
        
        submissions = self.bid_submissions.get(bid_id, [])
        if not submissions:
            logger.warning(f"No bids for request {bid_id}")
            return None
        
        request = self.active_requests[bid_id]
        
        # Calculate price and time ranges
        prices = [b.price for b in submissions]
        times = [b.estimated_time_ms for b in submissions]
        price_range = (min(prices), max(prices))
        time_range = (min(times), max(times))
        
        # Calculate scores
        scored_bids = []
        for bid in submissions:
            score = bid.calculate_score(request.criteria, price_range, time_range)
            scored_bids.append((score, bid))
        
        # Sort by score (highest first)
        scored_bids.sort(key=lambda x: x[0], reverse=True)
        
        winner = scored_bids[0][1]
        winner.status = BidStatus.ACCEPTED
        
        # Mark others as rejected
        for score, bid in scored_bids[1:]:
            bid.status = BidStatus.REJECTED
        
        logger.info(f"Selected winner for {bid_id}: provider {winner.provider_id} with score {scored_bids[0][0]:.3f}")
        
        return winner
    
    async def accept_bid(
        self,
        bid_id: str,
        provider_id: str
    ) -> Optional[BidSubmission]:
        """Manually accept a specific bid"""
        if bid_id not in self.bid_submissions:
            return None
        
        for bid in self.bid_submissions[bid_id]:
            if bid.provider_id == provider_id:
                bid.status = BidStatus.ACCEPTED
                return bid
        
        return None
    
    def get_bid_status(self, bid_id: str) -> Dict[str, Any]:
        """Get status of a bid request"""
        if bid_id not in self.active_requests:
            return {"status": "not_found"}
        
        request = self.active_requests[bid_id]
        submissions = self.bid_submissions.get(bid_id, [])
        
        return {
            "bid_id": bid_id,
            "status": "expired" if request.is_expired() else "active",
            "consumer_id": request.consumer_id,
            "submissions_count": len(submissions),
            "submissions": [
                {
                    "provider_id": b.provider_id,
                    "price": b.price,
                    "estimated_time_ms": b.estimated_time_ms,
                    "status": b.status.value
                }
                for b in submissions
            ]
        }
    
    def get_active_requests(self, consumer_id: Optional[str] = None) -> List[BidRequest]:
        """Get active bid requests"""
        requests = []
        for bid_id, request in self.active_requests.items():
            if not request.is_expired():
                if consumer_id is None or request.consumer_id == consumer_id:
                    requests.append(request)
        return requests
    
    def _check_consumer_rate_limit(self, consumer_id: str) -> bool:
        """Check if consumer is within rate limit"""
        now = time.time()
        window_start = now - 60  # 1 minute window
        
        # Get requests in window
        if consumer_id not in self.consumer_request_count:
            self.consumer_request_count[consumer_id] = []
        
        requests = self.consumer_request_count[consumer_id]
        requests = [t for t in requests if t > window_start]
        self.consumer_request_count[consumer_id] = requests
        
        # Check limit
        if len(requests) >= self.max_requests_per_minute:
            return False
        
        requests.append(now)
        return True
    
    def _check_provider_rate_limit(self, provider_id: str) -> bool:
        """Check if provider is within rate limit"""
        now = time.time()
        window_start = now - 60
        
        if provider_id not in self.provider_bid_count:
            self.provider_bid_count[provider_id] = []
        
        bids = self.provider_bid_count[provider_id]
        bids = [t for t in bids if t > window_start]
        self.provider_bid_count[provider_id] = bids
        
        if len(bids) >= self.max_bids_per_minute:
            return False
        
        bids.append(now)
        return True
    
    async def _expire_bid_request(self, bid_id: str, timeout_ms: int):
        """Expire bid request after timeout"""
        await asyncio.sleep(timeout_ms / 1000)
        
        if bid_id in self.active_requests:
            request = self.active_requests[bid_id]
            
            # Auto-select if bids exist
            submissions = self.bid_submissions.get(bid_id, [])
            if submissions:
                winner = await self.select_winner(bid_id)
                if winner:
                    logger.info(f"Auto-selected winner for expired bid {bid_id}")
            
            logger.info(f"Bid request {bid_id} expired")
    
    async def _cleanup_loop(self):
        """Periodic cleanup of expired data"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _cleanup(self):
        """Clean up expired bid requests"""
        now = time.time()
        expired = []
        
        for bid_id, request in self.active_requests.items():
            if request.is_expired():
                # Check if all submissions are resolved
                submissions = self.bid_submissions.get(bid_id, [])
                all_resolved = all(
                    s.status in [BidStatus.ACCEPTED, BidStatus.REJECTED, BidStatus.CANCELLED]
                    for s in submissions
                )
                
                if all_resolved or (now - request.created_at) > 300:  # 5 min max
                    expired.append(bid_id)
        
        for bid_id in expired:
            del self.active_requests[bid_id]
            if bid_id in self.bid_submissions:
                del self.bid_submissions[bid_id]
        
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired bid requests")


# Singleton instance
_bidding_service: Optional[BiddingService] = None


def get_bidding_service() -> BiddingService:
    """Get singleton bidding service instance"""
    global _bidding_service
    if _bidding_service is None:
        _bidding_service = BiddingService()
    return _bidding_service


async def main():
    """Demo of bidding service"""
    service = get_bidding_service()
    await service.start()
    
    # Create bid request
    request = await service.create_bid_request(
        consumer_id="consumer_001",
        service_category="code_review",
        requirements={"language": "python", "complexity": "medium"},
        criteria={"price_weight": 0.4, "reputation_weight": 0.4, "speed_weight": 0.2},
        timeout_ms=3000,
        escrow_deposit=100
    )
    
    if request:
        print(f"Created bid request: {request.bid_id}")
        
        # Submit bids
        await service.submit_bid(
            bid_id=request.bid_id,
            provider_id="provider_001",
            service_id="svc_001",
            price=80,
            estimated_time_ms=2000,
            confidence=0.95,
            reputation_score=4.5,
            completed_tasks=100,
            success_rate=0.98
        )
        
        await service.submit_bid(
            bid_id=request.bid_id,
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
        
        # Check status
        status = service.get_bid_status(request.bid_id)
        print(f"Final status: {status}")
    
    await service.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
