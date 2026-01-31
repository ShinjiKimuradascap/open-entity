#!/usr/bin/env python3
"""
Reputation Engine for AI Multi-Agent Marketplace

Advanced reputation scoring with:
- Weighted rating based on transaction value and reviewer reputation
- Time decay for old ratings
- Tamper-proof hash chain
- Multi-factor ranking algorithm
"""

import json
import hashlib
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum


@dataclass
class RatingEntry:
    """Single rating entry with metadata"""
    rating_id: str
    service_id: str
    reviewer_id: str
    reviewer_reputation: float  # 0-5 scale
    rating: float  # 1-5 scale
    transaction_value: Decimal
    timestamp: datetime
    previous_hash: str  # Hash of previous entry for chain
    entry_hash: str = ""  # Hash of this entry
    
    def __post_init__(self):
        if not self.entry_hash:
            self.entry_hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """Compute hash of this entry"""
        data = {
            'rating_id': self.rating_id,
            'service_id': self.service_id,
            'reviewer_id': self.reviewer_id,
            'reviewer_reputation': self.reviewer_reputation,
            'rating': self.rating,
            'transaction_value': str(self.transaction_value),
            'timestamp': self.timestamp.isoformat(),
            'previous_hash': self.previous_hash
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    
    def verify_integrity(self) -> bool:
        """Verify entry hash matches computed hash"""
        return self.entry_hash == self._compute_hash()
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'rating_id': self.rating_id,
            'service_id': self.service_id,
            'reviewer_id': self.reviewer_id,
            'reviewer_reputation': self.reviewer_reputation,
            'rating': self.rating,
            'transaction_value': str(self.transaction_value),
            'timestamp': self.timestamp.isoformat(),
            'previous_hash': self.previous_hash,
            'entry_hash': self.entry_hash
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'RatingEntry':
        """Create from dictionary"""
        return cls(
            rating_id=data['rating_id'],
            service_id=data['service_id'],
            reviewer_id=data['reviewer_id'],
            reviewer_reputation=data['reviewer_reputation'],
            rating=data['rating'],
            transaction_value=Decimal(data['transaction_value']),
            timestamp=datetime.fromisoformat(data['timestamp']),
            previous_hash=data['previous_hash'],
            entry_hash=data['entry_hash']
        )


@dataclass
class ServiceMetrics:
    """Service performance metrics for ranking"""
    service_id: str
    reputation_score: float = 0.0
    completion_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    price_competitiveness: float = 0.0
    total_transactions: int = 0
    successful_transactions: int = 0
    total_reviews: int = 0
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()
    
    @property
    def composite_score(self) -> float:
        """Calculate composite ranking score"""
        # Weighted components
        reputation_weight = 0.40
        completion_weight = 0.30
        response_weight = 0.20
        price_weight = 0.10
        
        # Normalize response time (lower is better, max 60s)
        response_score = max(0, 1.0 - (self.avg_response_time_ms / 60000))
        
        # Normalize price competitiveness (0-1, higher is better)
        price_score = min(1.0, max(0.0, self.price_competitiveness))
        
        return (
            self.reputation_score / 5.0 * reputation_weight +
            self.completion_rate * completion_weight +
            response_score * response_weight +
            price_score * price_weight
        ) * 100
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'service_id': self.service_id,
            'reputation_score': self.reputation_score,
            'completion_rate': self.completion_rate,
            'avg_response_time_ms': self.avg_response_time_ms,
            'price_competitiveness': self.price_competitiveness,
            'total_transactions': self.total_transactions,
            'successful_transactions': self.successful_transactions,
            'total_reviews': self.total_reviews,
            'composite_score': self.composite_score,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }


class ReputationEngine:
    """Advanced reputation calculation and ranking engine"""
    
    # Time decay constants
    DECAY_HALF_LIFE_DAYS = 90  # Half-life of 90 days
    MAX_DECAY_FACTOR = 0.1  # Minimum 10% weight for very old ratings
    
    # Weight factors
    BASE_REVIEWER_WEIGHT = 0.3
    MAX_REVIEWER_WEIGHT = 2.0
    TRANSACTION_VALUE_SCALE = Decimal('1000')  # Scale factor for value weighting
    
    def __init__(self, storage_path: Optional[str] = None):
        self._ratings: Dict[str, List[RatingEntry]] = {}  # service_id -> ratings
        self._metrics: Dict[str, ServiceMetrics] = {}
        self._storage_path = storage_path
        self._last_rating_hash: Dict[str, str] = {}  # service_id -> last hash
        self._lock = asyncio.Lock()
        
        if storage_path:
            self._load_from_storage()
    
    def calculate_reputation_score(
        self,
        base_score: float,
        new_rating: float,
        transaction_value: Decimal,
        reviewer_reputation: float,
        time_decay: bool = True,
        timestamp: Optional[datetime] = None
    ) -> float:
        """
        Calculate new reputation score with advanced weighting.
        
        Args:
            base_score: Current reputation score (0-5)
            new_rating: New rating value (1-5)
            transaction_value: Value of the transaction
            reviewer_reputation: Reviewer's reputation score (0-5)
            time_decay: Apply time-based weight decay
            timestamp: Rating timestamp (default: now)
        
        Returns:
            Updated reputation score (0-5)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        # Normalize inputs
        normalized_rating = max(1.0, min(5.0, new_rating))
        normalized_reviewer_rep = max(0.0, min(5.0, reviewer_reputation))
        
        # Calculate weights
        # 1. Reviewer reputation weight (higher rep = more weight)
        reviewer_weight = self._calculate_reviewer_weight(normalized_reviewer_rep)
        
        # 2. Transaction value weight (higher value = more weight)
        value_weight = self._calculate_value_weight(transaction_value)
        
        # 3. Time decay weight (older = less weight)
        time_weight = 1.0
        if time_decay:
            time_weight = self._calculate_time_decay_weight(timestamp)
        
        # Combined weight
        total_weight = reviewer_weight * value_weight * time_weight
        
        # Bayesian weighted average
        # Use weighted average between base score and new rating
        # Higher weight ratings have more influence
        weight_factor = min(total_weight, 1.0)  # Cap at 1.0 for stability
        
        new_score = (
            (1 - weight_factor) * base_score +
            weight_factor * normalized_rating
        )
        
        return max(0.0, min(5.0, new_score))
    
    def _calculate_reviewer_weight(self, reviewer_reputation: float) -> float:
        """Calculate weight based on reviewer reputation"""
        # Map 0-5 to 0.3-2.0
        if reviewer_reputation <= 0:
            return self.BASE_REVIEWER_WEIGHT
        
        normalized = reviewer_reputation / 5.0
        return self.BASE_REVIEWER_WEIGHT + (
            normalized * (self.MAX_REVIEWER_WEIGHT - self.BASE_REVIEWER_WEIGHT)
        )
    
    def _calculate_value_weight(self, transaction_value: Decimal) -> float:
        """Calculate weight based on transaction value"""
        # Logarithmic scaling to prevent huge transactions from dominating
        import math
        value_float = float(transaction_value)
        if value_float <= 0:
            return 0.5
        
        log_weight = math.log1p(value_float / float(self.TRANSACTION_VALUE_SCALE))
        return min(2.0, max(0.5, 0.5 + log_weight))
    
    def _calculate_time_decay_weight(self, timestamp: datetime) -> float:
        """Calculate time decay weight for a rating"""
        age_days = (datetime.utcnow() - timestamp).days
        if age_days <= 0:
            return 1.0
        
        import math
        # Exponential decay: weight = 2^(-age / half_life)
        decay = math.pow(0.5, age_days / self.DECAY_HALF_LIFE_DAYS)
        
        # Ensure minimum weight
        return max(self.MAX_DECAY_FACTOR, decay)
    
    async def add_rating(
        self,
        rating_id: str,
        service_id: str,
        reviewer_id: str,
        reviewer_reputation: float,
        rating: float,
        transaction_value: Decimal,
        timestamp: Optional[datetime] = None
    ) -> RatingEntry:
        """
        Add a new rating with hash chain integrity.
        
        Returns:
            The created RatingEntry
        """
        async with self._lock:
            if timestamp is None:
                timestamp = datetime.utcnow()
            
            # Get previous hash for chain
            previous_hash = self._last_rating_hash.get(service_id, "0" * 64)
            
            # Create entry
            entry = RatingEntry(
                rating_id=rating_id,
                service_id=service_id,
                reviewer_id=reviewer_id,
                reviewer_reputation=reviewer_reputation,
                rating=rating,
                transaction_value=transaction_value,
                timestamp=timestamp,
                previous_hash=previous_hash
            )
            
            # Store
            if service_id not in self._ratings:
                self._ratings[service_id] = []
            self._ratings[service_id].append(entry)
            
            # Update last hash
            self._last_rating_hash[service_id] = entry.entry_hash
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return entry
    
    async def verify_rating_chain(self, service_id: str) -> Tuple[bool, List[str]]:
        """
        Verify the integrity of the rating chain for a service.
        
        Returns:
            (is_valid, list_of_invalid_rating_ids)
        """
        async with self._lock:
            if service_id not in self._ratings:
                return True, []
            
            ratings = sorted(self._ratings[service_id], key=lambda r: r.timestamp)
            invalid_ids = []
            expected_previous = "0" * 64
            
            for rating in ratings:
                # Check hash chain
                if rating.previous_hash != expected_previous:
                    invalid_ids.append(rating.rating_id)
                    continue
                
                # Verify entry integrity
                if not rating.verify_integrity():
                    invalid_ids.append(rating.rating_id)
                    continue
                
                expected_previous = rating.entry_hash
            
            return len(invalid_ids) == 0, invalid_ids
    
    async def recalculate_service_reputation(
        self,
        service_id: str,
        base_score: float = 2.5
    ) -> float:
        """
        Recalculate reputation from all ratings with full weighting.
        
        Args:
            service_id: Service to recalculate
            base_score: Starting score for new services
        
        Returns:
            New reputation score
        """
        async with self._lock:
            if service_id not in self._ratings or not self._ratings[service_id]:
                return base_score
            
            ratings = sorted(self._ratings[service_id], key=lambda r: r.timestamp)
            current_score = base_score
            
            for entry in ratings:
                current_score = self.calculate_reputation_score(
                    base_score=current_score,
                    new_rating=entry.rating,
                    transaction_value=entry.transaction_value,
                    reviewer_reputation=entry.reviewer_reputation,
                    time_decay=True,
                    timestamp=entry.timestamp
                )
            
            return current_score
    
    def rank_services(
        self,
        service_ids: List[str],
        metrics: Optional[Dict[str, ServiceMetrics]] = None
    ) -> List[Tuple[str, float, ServiceMetrics]]:
        """
        Rank services by composite score.
        
        Args:
            service_ids: List of service IDs to rank
            metrics: Optional pre-fetched metrics (fetched from self._metrics if not provided)
        
        Returns:
            List of (service_id, composite_score, metrics) tuples, sorted by score descending
        """
        if metrics is None:
            metrics = self._metrics
        
        results = []
        for sid in service_ids:
            if sid in metrics:
                m = metrics[sid]
                results.append((sid, m.composite_score, m))
            else:
                # Create default metrics
                default_metrics = ServiceMetrics(service_id=sid)
                results.append((sid, default_metrics.composite_score, default_metrics))
        
        # Sort by composite score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    async def update_service_metrics(
        self,
        service_id: str,
        reputation_score: Optional[float] = None,
        response_time_ms: Optional[float] = None,
        transaction_completed: Optional[bool] = None,
        price_competitiveness: Optional[float] = None
    ) -> ServiceMetrics:
        """
        Update service performance metrics.
        
        Args:
            service_id: Service to update
            reputation_score: New reputation score
            response_time_ms: Response time for latest operation
            transaction_completed: Whether transaction succeeded
            price_competitiveness: Price competitiveness score (0-1)
        """
        async with self._lock:
            if service_id not in self._metrics:
                self._metrics[service_id] = ServiceMetrics(service_id=service_id)
            
            metrics = self._metrics[service_id]
            metrics.last_updated = datetime.utcnow()
            
            if reputation_score is not None:
                metrics.reputation_score = reputation_score
            
            if response_time_ms is not None:
                # Exponential moving average for response time
                alpha = 0.3
                if metrics.avg_response_time_ms == 0:
                    metrics.avg_response_time_ms = response_time_ms
                else:
                    metrics.avg_response_time_ms = (
                        (1 - alpha) * metrics.avg_response_time_ms +
                        alpha * response_time_ms
                    )
            
            if transaction_completed is not None:
                metrics.total_transactions += 1
                if transaction_completed:
                    metrics.successful_transactions += 1
                # Update completion rate
                metrics.completion_rate = (
                    metrics.successful_transactions / metrics.total_transactions
                )
            
            if price_competitiveness is not None:
                metrics.price_competitiveness = price_competitiveness
            
            # Update review count from ratings
            if service_id in self._ratings:
                metrics.total_reviews = len(self._ratings[service_id])
            
            if self._storage_path:
                await self._save_to_storage()
            
            return metrics
    
    async def get_service_metrics(self, service_id: str) -> Optional[ServiceMetrics]:
        """Get metrics for a service"""
        async with self._lock:
            return self._metrics.get(service_id)
    
    async def get_all_metrics(self) -> Dict[str, ServiceMetrics]:
        """Get all service metrics"""
        async with self._lock:
            return dict(self._metrics)
    
    async def _save_to_storage(self):
        """Save engine state to file"""
        data = {
            'ratings': {
                sid: [r.to_dict() for r in ratings]
                for sid, ratings in self._ratings.items()
            },
            'metrics': {
                sid: m.to_dict()
                for sid, m in self._metrics.items()
            },
            'last_hashes': self._last_rating_hash,
            'version': '1.0',
            'updated_at': datetime.utcnow().isoformat()
        }
        
        temp_path = self._storage_path + '.tmp'
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        import os
        os.replace(temp_path, self._storage_path)
    
    def _load_from_storage(self):
        """Load engine state from file"""
        try:
            with open(self._storage_path, 'r') as f:
                data = json.load(f)
            
            # Load ratings
            for sid, ratings_data in data.get('ratings', {}).items():
                self._ratings[sid] = [
                    RatingEntry.from_dict(r) for r in ratings_data
                ]
            
            # Load metrics
            for sid, metrics_data in data.get('metrics', {}).items():
                self._metrics[sid] = ServiceMetrics(
                    service_id=metrics_data['service_id'],
                    reputation_score=metrics_data['reputation_score'],
                    completion_rate=metrics_data['completion_rate'],
                    avg_response_time_ms=metrics_data['avg_response_time_ms'],
                    price_competitiveness=metrics_data['price_competitiveness'],
                    total_transactions=metrics_data['total_transactions'],
                    successful_transactions=metrics_data['successful_transactions'],
                    total_reviews=metrics_data['total_reviews'],
                    last_updated=datetime.fromisoformat(metrics_data['last_updated'])
                    if metrics_data.get('last_updated') else None
                )
            
            # Load last hashes
            self._last_rating_hash = data.get('last_hashes', {})
            
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading reputation engine: {e}")
    
    async def get_rating_history(self, service_id: str) -> List[RatingEntry]:
        """Get rating history for a service"""
        async with self._lock:
            return list(self._ratings.get(service_id, []))
    
    async def get_stats(self) -> dict:
        """Get engine statistics"""
        async with self._lock:
            total_ratings = sum(len(r) for r in self._ratings.values())
            return {
                'total_services_rated': len(self._ratings),
                'total_ratings': total_ratings,
                'avg_ratings_per_service': total_ratings / len(self._ratings)
                if self._ratings else 0,
                'total_metrics_tracked': len(self._metrics),
                'chain_integrity_verified': all(
                    (await self.verify_rating_chain(sid))[0]
                    for sid in self._ratings.keys()
                ) if self._ratings else True
            }


# Convenience function
async def create_reputation_engine(
    storage_path: Optional[str] = None
) -> ReputationEngine:
    """Create a new reputation engine"""
    return ReputationEngine(storage_path)
