#!/usr/bin/env python3
"""
AI Service Matching Engine for Multi-Agent Marketplace

Handles intelligent matching between service buyers and providers.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
import logging

from .service_registry import ServiceRegistry, ServiceListing, ServiceType
from .order_book import OrderBook, ServiceOrder, OrderStatus

logger = logging.getLogger(__name__)


class MatchStrategy(Enum):
    """Matching strategies"""
    PRICE_OPTIMIZED = "price_optimized"      # Lowest price
    QUALITY_OPTIMIZED = "quality_optimized"  # Highest reputation
    BALANCED = "balanced"                    # Balance price/quality
    FASTEST = "fastest"                      # Fastest completion


@dataclass
class MatchCriteria:
    """Criteria for service matching"""
    required_capabilities: List[str]
    max_price: Optional[Decimal] = None
    min_reputation: float = 0.0
    preferred_providers: Optional[List[str]] = None
    excluded_providers: Optional[List[str]] = None
    max_completion_time: Optional[int] = None  # seconds
    strategy: MatchStrategy = MatchStrategy.BALANCED


@dataclass
class MatchScore:
    """Match score for a provider"""
    service_id: str
    provider_id: str
    score: float  # 0.0 - 1.0
    price_score: float
    reputation_score: float
    capability_score: float
    availability_score: float
    estimated_cost: Decimal
    estimated_time: int  # seconds


@dataclass
class MatchResult:
    """Result of a matching operation"""
    success: bool
    matches: List[MatchScore]
    top_match: Optional[MatchScore] = None
    message: str = ""
    search_time_ms: int = 0


class ServiceMatchingEngine:
    """
    Intelligent service matching engine.
    
    Matches service requests with optimal providers based on
    price, reputation, capabilities, and availability.
    """
    
    def __init__(
        self,
        registry: ServiceRegistry,
        order_book: OrderBook
    ):
        self._registry = registry
        self._order_book = order_book
        self._availability_cache: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._lock = asyncio.Lock()
    
    async def find_matches(
        self,
        criteria: MatchCriteria,
        limit: int = 10
    ) -> MatchResult:
        """
        Find matching services based on criteria.
        
        Args:
            criteria: Matching criteria
            limit: Maximum number of matches to return
            
        Returns:
            MatchResult with ranked matches
        """
        start_time = datetime.utcnow()
        
        try:
            # Search for candidate services
            candidates = await self._registry.search_services(
                service_type=None,  # Search all types
                capabilities=criteria.required_capabilities,
                min_reputation=criteria.min_reputation,
                max_price=criteria.max_price,
                limit=100  # Get more for scoring
            )
            
            # Filter out excluded providers
            if criteria.excluded_providers:
                candidates = [
                    c for c in candidates 
                    if c.provider_id not in criteria.excluded_providers
                ]
            
            # Filter to preferred providers if specified
            if criteria.preferred_providers:
                preferred = [
                    c for c in candidates 
                    if c.provider_id in criteria.preferred_providers
                ]
                if preferred:
                    candidates = preferred
            
            # Score each candidate
            scored_matches = []
            for listing in candidates:
                score = await self._compute_match_score(
                    listing, criteria
                )
                if score.score > 0.3:  # Minimum threshold
                    scored_matches.append(score)
            
            # Sort by strategy
            scored_matches = self._sort_by_strategy(
                scored_matches, criteria.strategy
            )
            
            # Limit results
            scored_matches = scored_matches[:limit]
            
            elapsed_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return MatchResult(
                success=len(scored_matches) > 0,
                matches=scored_matches,
                top_match=scored_matches[0] if scored_matches else None,
                message=f"Found {len(scored_matches)} matches",
                search_time_ms=elapsed_ms
            )
            
        except Exception as e:
            logger.error(f"Error in find_matches: {e}")
            return MatchResult(
                success=False,
                matches=[],
                message=f"Matching error: {str(e)}"
            )
    
    async def match_order_auto(
        self,
        order_id: str,
        criteria: MatchCriteria
    ) -> Tuple[bool, Optional[str], str]:
        """
        Automatically match an order with the best provider.
        
        Args:
            order_id: Order to match
            criteria: Matching criteria
            
        Returns:
            (success, provider_id, message)
        """
        # Get the order
        order = await self._order_book.get_order(order_id)
        if not order:
            return False, None, "Order not found"
        
        if order.status != OrderStatus.PENDING:
            return False, None, f"Order not pending (status: {order.status.value})"
        
        # Find matches
        result = await self.find_matches(criteria, limit=1)
        
        if not result.success or not result.top_match:
            return False, None, "No suitable providers found"
        
        top_match = result.top_match
        
        # Perform the match
        match_result = await self._order_book.match_order(
            order_id=order_id,
            provider_id=top_match.provider_id
        )
        
        if match_result.success:
            logger.info(
                f"Auto-matched order {order_id} with provider {top_match.provider_id} "
                f"(score: {top_match.score:.2f})"
            )
            return True, top_match.provider_id, "Successfully matched"
        else:
            return False, None, match_result.message
    
    async def check_availability(self, service_id: str) -> Tuple[bool, Optional[int]]:
        """
        Check if a service is available and estimate wait time.
        
        Returns:
            (is_available, estimated_wait_seconds)
        """
        # Check cache
        cache_key = f"avail:{service_id}"
        if cache_key in self._availability_cache:
            cached_time = self._availability_cache[cache_key]
            if datetime.utcnow() - cached_time < self._cache_ttl:
                return True, 0  # Cached as available
        
        # Get service info
        listing = await self._registry.get_service(service_id)
        if not listing:
            return False, None
        
        # Check pending orders for this service
        pending = await self._order_book.get_pending_orders(service_id)
        
        # Estimate based on queue length
        # Assume each service can handle 5 concurrent requests
        concurrent_capacity = 5
        queue_length = len(pending)
        
        if queue_length < concurrent_capacity:
            # Update cache
            self._availability_cache[cache_key] = datetime.utcnow()
            return True, 0
        else:
            # Estimate wait time (30s per service on average)
            wait_time = (queue_length - concurrent_capacity + 1) * 30
            return True, wait_time
    
    async def _compute_match_score(
        self,
        listing: ServiceListing,
        criteria: MatchCriteria
    ) -> MatchScore:
        """Compute match score for a service listing."""
        
        # Price score (lower is better, normalized 0-1)
        price_score = 0.5
        if criteria.max_price and criteria.max_price > 0:
            price_ratio = float(listing.price / criteria.max_price)
            price_score = max(0, 1 - price_ratio)
        
        # Reputation score (0-5 scale, normalized)
        reputation_score = listing.reputation_score / 5.0
        
        # Capability match score
        if criteria.required_capabilities:
            matched_caps = set(criteria.required_capabilities) & set(listing.capabilities)
            capability_score = len(matched_caps) / len(criteria.required_capabilities)
        else:
            capability_score = 1.0
        
        # Availability score
        is_available, wait_time = await self.check_availability(listing.service_id)
        if not is_available:
            availability_score = 0.0
        elif wait_time == 0:
            availability_score = 1.0
        else:
            # Degrade score based on wait time (linear, 5 min max)
            availability_score = max(0, 1 - (wait_time / 300))
        
        # Combined score (weighted)
        weights = self._get_strategy_weights(criteria.strategy)
        
        score = (
            weights['price'] * price_score +
            weights['reputation'] * reputation_score +
            weights['capability'] * capability_score +
            weights['availability'] * availability_score
        )
        
        # Estimate completion time
        estimated_time = 60  # Base 60 seconds
        if wait_time:
            estimated_time += wait_time
        
        return MatchScore(
            service_id=listing.service_id,
            provider_id=listing.provider_id,
            score=score,
            price_score=price_score,
            reputation_score=reputation_score,
            capability_score=capability_score,
            availability_score=availability_score,
            estimated_cost=listing.price,
            estimated_time=estimated_time
        )
    
    def _get_strategy_weights(self, strategy: MatchStrategy) -> Dict[str, float]:
        """Get weights for each strategy."""
        weights = {
            MatchStrategy.PRICE_OPTIMIZED: {
                'price': 0.5,
                'reputation': 0.15,
                'capability': 0.2,
                'availability': 0.15
            },
            MatchStrategy.QUALITY_OPTIMIZED: {
                'price': 0.15,
                'reputation': 0.5,
                'capability': 0.2,
                'availability': 0.15
            },
            MatchStrategy.BALANCED: {
                'price': 0.25,
                'reputation': 0.25,
                'capability': 0.25,
                'availability': 0.25
            },
            MatchStrategy.FASTEST: {
                'price': 0.15,
                'reputation': 0.15,
                'capability': 0.2,
                'availability': 0.5
            }
        }
        return weights.get(strategy, weights[MatchStrategy.BALANCED])
    
    def _sort_by_strategy(
        self,
        matches: List[MatchScore],
        strategy: MatchStrategy
    ) -> List[MatchScore]:
        """Sort matches based on strategy."""
        if strategy == MatchStrategy.PRICE_OPTIMIZED:
            return sorted(matches, key=lambda m: (m.estimated_cost, -m.score))
        elif strategy == MatchStrategy.QUALITY_OPTIMIZED:
            return sorted(matches, key=lambda m: (-m.reputation_score, -m.score))
        elif strategy == MatchStrategy.FASTEST:
            return sorted(matches, key=lambda m: (m.estimated_time, -m.score))
        else:  # BALANCED
            return sorted(matches, key=lambda m: -m.score)
    
    async def get_market_insights(self) -> Dict:
        """Get marketplace insights for analytics."""
        registry_stats = await self._registry.get_stats()
        order_stats = await self._order_book.get_stats()
        
        return {
            'total_services': registry_stats.get('total_services', 0),
            'active_services': registry_stats.get('active_services', 0),
            'total_orders': order_stats.get('total_orders', 0),
            'pending_orders': order_stats.get('pending_orders', 0),
            'total_volume': str(order_stats.get('total_volume', 0)),
            'avg_reputation': registry_stats.get('avg_reputation', 0),
            'timestamp': datetime.utcnow().isoformat()
        }


# Convenience function for creating the engine
async def create_matching_engine(
    registry: ServiceRegistry,
    order_book: OrderBook
) -> ServiceMatchingEngine:
    """Create a new service matching engine."""
    return ServiceMatchingEngine(registry, order_book)
