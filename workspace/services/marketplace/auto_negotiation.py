#!/usr/bin/env python3
"""
Auto-Negotiation Engine for AI Multi-Agent Marketplace

Autonomous quote evaluation and decision making for AI agents.
v1.3 Feature: Automated bid evaluation with multi-factor scoring
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class QuoteDecision(Enum):
    """Decision outcomes for quote evaluation"""
    ACCEPT = "accept"
    REJECT = "reject"
    COUNTER_OFFER = "counter_offer"


class NegotiationStatus(Enum):
    """Negotiation lifecycle status"""
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class NegotiationContext:
    """Context for negotiation decisions"""
    budget_max: Decimal
    budget_min: Decimal
    time_limit_hours: float
    quality_threshold: float
    required_capabilities: List[str]
    preferred_providers: List[str] = field(default_factory=list)
    risk_tolerance: float = 0.5  # 0.0 - 1.0


@dataclass
class QuoteEvaluation:
    """Evaluation result for a quote"""
    quote_id: str
    provider_id: str
    price: Decimal
    estimated_hours: float
    reputation_score: float
    capabilities: List[str]
    
    # Evaluation metrics
    price_score: float = 0.0
    time_score: float = 0.0
    reputation_score_weighted: float = 0.0
    capability_match_score: float = 0.0
    
    # Final score (0.0 - 1.0)
    total_score: float = 0.0
    decision: QuoteDecision = QuoteDecision.REJECT
    
    def to_dict(self) -> dict:
        return {
            "quote_id": self.quote_id,
            "provider_id": self.provider_id,
            "price": str(self.price),
            "total_score": self.total_score,
            "decision": self.decision.value
        }


@dataclass
class CounterOffer:
    """Counter-offer for negotiation"""
    counter_id: str
    original_quote_id: str
    proposed_price: Decimal
    proposed_time: float
    message: str
    expires_at: datetime


class AutoNegotiationEngine:
    """
    Autonomous negotiation engine for AI agents.
    
    Features:
    - Multi-factor quote evaluation
    - Automatic counter-offer generation
    - Multi-round negotiation support
    - Risk assessment
    
    Scoring weights:
    - Price: 30%
    - Time: 25%
    - Reputation: 25%
    - Capability match: 20%
    """
    
    # Scoring weights (must sum to 1.0)
    PRICE_WEIGHT = 0.30
    TIME_WEIGHT = 0.25
    REPUTATION_WEIGHT = 0.25
    CAPABILITY_WEIGHT = 0.20
    
    # Decision thresholds
    ACCEPT_THRESHOLD = 0.80
    COUNTER_THRESHOLD = 0.50
    
    def __init__(self):
        self.active_negotiations: Dict[str, Dict] = {}
        self.evaluation_history: List[QuoteEvaluation] = []
        self._lock = asyncio.Lock()
    
    async def evaluate_quote(
        self,
        quote_id: str,
        provider_id: str,
        price: Decimal,
        estimated_hours: float,
        reputation_score: float,
        capabilities: List[str],
        context: NegotiationContext
    ) -> QuoteEvaluation:
        """
        Evaluate a quote and return decision.
        
        Args:
            quote_id: Unique quote identifier
            provider_id: Provider agent ID
            price: Quoted price
            estimated_hours: Estimated completion time
            reputation_score: Provider reputation (0.0 - 1.0)
            capabilities: Provider capabilities
            context: Negotiation context
        
        Returns:
            QuoteEvaluation with scores and decision
        """
        # Calculate individual scores
        price_score = self._calculate_price_score(price, context.budget_max, context.budget_min)
        time_score = self._calculate_time_score(estimated_hours, context.time_limit_hours)
        capability_score = self._calculate_capability_match(capabilities, context.required_capabilities)
        
        # Calculate weighted total score
        total_score = (
            price_score * self.PRICE_WEIGHT +
            time_score * self.TIME_WEIGHT +
            reputation_score * self.REPUTATION_WEIGHT +
            capability_score * self.CAPABILITY_WEIGHT
        )
        
        # Make decision
        if total_score >= self.ACCEPT_THRESHOLD:
            decision = QuoteDecision.ACCEPT
        elif total_score >= self.COUNTER_THRESHOLD:
            decision = QuoteDecision.COUNTER_OFFER
        else:
            decision = QuoteDecision.REJECT
        
        evaluation = QuoteEvaluation(
            quote_id=quote_id,
            provider_id=provider_id,
            price=price,
            estimated_hours=estimated_hours,
            reputation_score=reputation_score,
            capabilities=capabilities,
            price_score=price_score,
            time_score=time_score,
            reputation_score_weighted=reputation_score,
            capability_match_score=capability_score,
            total_score=total_score,
            decision=decision
        )
        
        # Store in history
        async with self._lock:
            self.evaluation_history.append(evaluation)
        
        logger.info(f"Quote {quote_id} evaluated: score={total_score:.2f}, decision={decision.value}")
        return evaluation
    
    def _calculate_price_score(self, price: Decimal, budget_max: Decimal, budget_min: Decimal) -> float:
        """
        Calculate price score (lower price = higher score).
        
        Score ranges from 0.0 to 1.0:
        - Price at budget_min = 1.0 (perfect score)
        - Price at budget_max = 0.0 (minimum acceptable)
        """
        if price <= budget_min:
            return 1.0
        if price >= budget_max:
            return 0.0
        
        # Linear interpolation
        price_range = float(budget_max - budget_min)
        if price_range == 0:
            return 1.0
        
        return 1.0 - (float(price - budget_min) / price_range)
    
    def _calculate_time_score(self, estimated_hours: float, time_limit: float) -> float:
        """
        Calculate time score (faster = higher score).
        
        - Within 50% of time limit = 1.0
        - At time limit = 0.5
        - Over time limit = 0.0
        """
        if estimated_hours <= time_limit * 0.5:
            return 1.0
        if estimated_hours >= time_limit:
            return 0.0
        
        # Linear interpolation between 50% and 100%
        time_range = time_limit * 0.5
        return 1.0 - ((estimated_hours - time_limit * 0.5) / time_range)
    
    def _calculate_capability_match(
        self,
        provider_caps: List[str],
        required_caps: List[str]
    ) -> float:
        """
        Calculate capability match score.
        
        Score = (matched capabilities) / (required capabilities)
        """
        if not required_caps:
            return 1.0
        
        provider_caps_lower = set(c.lower() for c in provider_caps)
        required_caps_lower = set(c.lower() for c in required_caps)
        
        matched = len(provider_caps_lower & required_caps_lower)
        return matched / len(required_caps_lower)
    
    async def generate_counter_offer(
        self,
        original_quote_id: str,
        original_price: Decimal,
        context: NegotiationContext,
        evaluation: QuoteEvaluation
    ) -> CounterOffer:
        """
        Generate a counter-offer based on evaluation.
        
        Counter-offer strategy:
        - Price: Move 20% toward target price
        - Time: Accept if reasonable
        """
        target_price = (context.budget_max + context.budget_min) / 2
        price_difference = original_price - target_price
        
        # Move 20% toward target
        proposed_price = original_price - (price_difference * Decimal("0.2"))
        
        # Ensure within budget bounds
        proposed_price = max(proposed_price, context.budget_min)
        proposed_price = min(proposed_price, context.budget_max)
        
        counter = CounterOffer(
            counter_id=str(uuid.uuid4()),
            original_quote_id=original_quote_id,
            proposed_price=proposed_price,
            proposed_time=evaluation.estimated_hours,
            message=f"Counter-offer based on evaluation score: {evaluation.total_score:.2f}",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        
        logger.info(f"Counter-offer generated: {counter.counter_id} at {proposed_price}")
        return counter
    
    async def select_best_quote(
        self,
        evaluations: List[QuoteEvaluation]
    ) -> Optional[QuoteEvaluation]:
        """
        Select the best quote from multiple evaluations.
        
        Returns highest scoring acceptable quote, or None if none acceptable.
        """
        if not evaluations:
            return None
        
        # Filter to acceptable quotes
        acceptable = [e for e in evaluations if e.decision == QuoteDecision.ACCEPT]
        
        if acceptable:
            # Return highest scoring acceptable quote
            return max(acceptable, key=lambda e: e.total_score)
        
        # No acceptable quotes, return best counter-offer candidate
        counter_candidates = [e for e in evaluations if e.decision == QuoteDecision.COUNTER_OFFER]
        
        if counter_candidates:
            return max(counter_candidates, key=lambda e: e.total_score)
        
        return None
    
    def get_evaluation_history(
        self,
        provider_id: Optional[str] = None
    ) -> List[QuoteEvaluation]:
        """Get evaluation history, optionally filtered by provider"""
        if provider_id:
            return [e for e in self.evaluation_history if e.provider_id == provider_id]
        return self.evaluation_history.copy()
    
    async def get_market_rate(self, task_type: str) -> Optional[Decimal]:
        """
        Get average market rate for a task type.
        
        This would query historical data or oracles.
        For now, returns None (not implemented).
        """
        # TODO: Implement market rate lookup
        return None


# Import timedelta for counter-offer expiration
from datetime import timedelta


__all__ = [
    "AutoNegotiationEngine",
    "QuoteDecision",
    "NegotiationStatus",
    "NegotiationContext",
    "QuoteEvaluation",
    "CounterOffer"
]
