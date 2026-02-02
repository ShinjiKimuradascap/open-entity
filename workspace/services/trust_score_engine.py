#!/usr/bin/env python3
"""
Trust Score Engine
Open Entity Charter v0.2 準拠の包括的信頼性スコアリングシステム

Integrates:
- Transaction history (Reputation Manager)
- Skill verifications (Skill Verification Framework)
- Free quota usage (Free Quota System)
- Network behavior analysis
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class TrustFactor(Enum):
    """Trust score factors"""
    TRANSACTION_HISTORY = "transaction_history"  # 30%
    SKILL_VERIFICATION = "skill_verification"    # 25%
    NETWORK_BEHAVIOR = "network_behavior"        # 20%
    ACCOUNT_AGE = "account_age"                  # 15%
    COMMUNITY_CONTRIBUTION = "community_contribution"  # 10%


@dataclass
class TrustFactorScore:
    """Individual factor score"""
    factor: TrustFactor
    score: float  # 0-100
    weight: float  # 0-1
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class TrustScoreRecord:
    """Entity trust score record"""
    entity_id: str
    overall_score: float = 0.0  # 0-100
    factor_scores: List[TrustFactorScore] = field(default_factory=list)
    tier: str = "unverified"
    calculated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    previous_score: Optional[float] = None
    score_change: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "overall_score": round(self.overall_score, 2),
            "factor_scores": [
                {
                    "factor": fs.factor.value,
                    "score": round(fs.score, 2),
                    "weight": fs.weight,
                    "weighted_score": round(fs.weighted_score, 2),
                    "details": fs.details
                }
                for fs in self.factor_scores
            ],
            "tier": self.tier,
            "calculated_at": self.calculated_at,
            "previous_score": self.previous_score,
            "score_change": round(self.score_change, 2)
        }


class TrustScoreEngine:
    """
    Trust Score Engine
    
    Calculates comprehensive trust scores for entities based on:
    1. Transaction history (success rate, volume, consistency)
    2. Skill verifications (verified skills, certificates)
    3. Network behavior (Sybil resistance, anomaly detection)
    4. Account age (longevity, stability)
    5. Community contribution (reviews, referrals, participation)
    """
    
    DATA_DIR = Path("data/trust_scores")
    SCORES_FILE = DATA_DIR / "trust_scores.json"
    HISTORY_FILE = DATA_DIR / "score_history.json"
    
    # Default weights for each factor (must sum to 1.0)
    DEFAULT_WEIGHTS = {
        TrustFactor.TRANSACTION_HISTORY: 0.30,
        TrustFactor.SKILL_VERIFICATION: 0.25,
        TrustFactor.NETWORK_BEHAVIOR: 0.20,
        TrustFactor.ACCOUNT_AGE: 0.15,
        TrustFactor.COMMUNITY_CONTRIBUTION: 0.10
    }
    
    # Tier thresholds
    TIER_THRESHOLDS = {
        "elite": 90,
        "trusted": 75,
        "verified": 60,
        "basic": 40,
        "unverified": 0
    }
    
    def __init__(self):
        self._scores: Dict[str, TrustScoreRecord] = {}
        self._score_history: Dict[str, List[Dict]] = {}  # entity_id -> list of historical scores
        self._weights = self.DEFAULT_WEIGHTS.copy()
        self._ensure_data_dir()
        self._load()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load persisted data"""
        if self.SCORES_FILE.exists():
            try:
                with open(self.SCORES_FILE, 'r') as f:
                    data = json.load(f)
                    for entity_id, record_data in data.items():
                        factor_scores = [
                            TrustFactorScore(
                                factor=TrustFactor(fs["factor"]),
                                score=fs["score"],
                                weight=fs["weight"],
                                details=fs.get("details", {})
                            )
                            for fs in record_data.get("factor_scores", [])
                        ]
                        self._scores[entity_id] = TrustScoreRecord(
                            entity_id=entity_id,
                            overall_score=record_data["overall_score"],
                            factor_scores=factor_scores,
                            tier=record_data.get("tier", "unverified"),
                            calculated_at=record_data.get("calculated_at"),
                            previous_score=record_data.get("previous_score"),
                            score_change=record_data.get("score_change", 0.0)
                        )
                logger.info(f"Loaded {len(self._scores)} trust scores")
            except Exception as e:
                logger.error(f"Failed to load trust scores: {e}")
        
        if self.HISTORY_FILE.exists():
            try:
                with open(self.HISTORY_FILE, 'r') as f:
                    self._score_history = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load score history: {e}")
    
    def _save(self):
        """Persist data"""
        try:
            with open(self.SCORES_FILE, 'w') as f:
                json.dump(
                    {k: v.to_dict() for k, v in self._scores.items()},
                    f, indent=2
                )
            
            with open(self.HISTORY_FILE, 'w') as f:
                json.dump(self._score_history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save trust scores: {e}")
    
    def _calculate_transaction_score(self, entity_id: str) -> TrustFactorScore:
        """Calculate transaction history score (0-100)"""
        try:
            # Import here to avoid circular dependency
            from reputation_manager import get_reputation_manager
            
            rep_manager = get_reputation_manager()
            reputation = rep_manager.get_reputation(entity_id)
            
            # Base score from reputation
            base_score = reputation.current_score if reputation else 50.0
            
            # Adjust based on success rate
            success_rate = reputation.success_rate if reputation else 0.0
            success_bonus = success_rate * 0.3  # Up to 30 points for 100% success
            
            # Volume bonus (capped at 20 points)
            total_tasks = reputation.total_tasks_completed if reputation else 0
            volume_bonus = min(total_tasks * 0.5, 20)
            
            # Streak bonus (up to 10 points)
            streak_bonus = min(reputation.current_streak if reputation else 0, 10)
            
            score = min(base_score + success_bonus + volume_bonus + streak_bonus, 100)
            
            return TrustFactorScore(
                factor=TrustFactor.TRANSACTION_HISTORY,
                score=score,
                weight=self._weights[TrustFactor.TRANSACTION_HISTORY],
                details={
                    "base_score": base_score,
                    "success_rate": success_rate,
                    "total_tasks": total_tasks,
                    "current_streak": reputation.current_streak if reputation else 0,
                    "success_bonus": success_bonus,
                    "volume_bonus": volume_bonus,
                    "streak_bonus": streak_bonus
                }
            )
        except Exception as e:
            logger.error(f"Failed to calculate transaction score for {entity_id}: {e}")
            return TrustFactorScore(
                factor=TrustFactor.TRANSACTION_HISTORY,
                score=50.0,
                weight=self._weights[TrustFactor.TRANSACTION_HISTORY],
                details={"error": str(e)}
            )
    
    def _calculate_skill_score(self, entity_id: str) -> TrustFactorScore:
        """Calculate skill verification score (0-100)"""
        try:
            from skill_verification import get_verification_framework
            
            framework = get_verification_framework()
            certs = framework.get_valid_certificates(entity_id)
            
            if not certs:
                return TrustFactorScore(
                    factor=TrustFactor.SKILL_VERIFICATION,
                    score=0.0,
                    weight=self._weights[TrustFactor.SKILL_VERIFICATION],
                    details={"certificates": 0}
                )
            
            # Score based on number of certificates, levels, and scores
            cert_count = len(certs)
            avg_level = sum(c.level for c in certs) / cert_count
            avg_score = sum(c.score for c in certs) / cert_count
            
            # Certificate count score (up to 40 points)
            count_score = min(cert_count * 10, 40)
            
            # Level score (up to 30 points)
            level_score = (avg_level / 5) * 30
            
            # Verification score (up to 30 points)
            verification_score = (avg_score / 100) * 30
            
            total_score = count_score + level_score + verification_score
            
            return TrustFactorScore(
                factor=TrustFactor.SKILL_VERIFICATION,
                score=total_score,
                weight=self._weights[TrustFactor.SKILL_VERIFICATION],
                details={
                    "certificates": cert_count,
                    "avg_level": avg_level,
                    "avg_score": avg_score,
                    "count_score": count_score,
                    "level_score": level_score,
                    "verification_score": verification_score
                }
            )
        except Exception as e:
            logger.error(f"Failed to calculate skill score for {entity_id}: {e}")
            return TrustFactorScore(
                factor=TrustFactor.SKILL_VERIFICATION,
                score=0.0,
                weight=self._weights[TrustFactor.SKILL_VERIFICATION],
                details={"error": str(e)}
            )
    
    def _calculate_network_score(self, entity_id: str) -> TrustFactorScore:
        """Calculate network behavior score (0-100)"""
        try:
            from free_quota_system import get_quota_manager
            
            quota_manager = get_quota_manager()
            quota_status = quota_manager.get_quota_status(entity_id)
            
            # Base score
            score = 100.0
            penalties = []
            
            # Check for suspicious activity
            if quota_status["status"] == "suspicious":
                score -= 50
                penalties.append("suspicious_activity")
            
            # Check for Sybil indicators
            if quota_status.get("sybil_flags", 0) > 0:
                score -= 30 * quota_status.get("sybil_flags", 0)
                penalties.append(f'sybil_flags:{quota_status.get("sybil_flags", 0)}')
            
            # IP diversity bonus
            ip_count = len(quota_status.get("ip_addresses", []))
            if ip_count == 0:
                score -= 10
                penalties.append("no_ip_record")
            elif ip_count > 3:
                score -= 5
                penalties.append("too_many_ips")
            
            # Ensure score doesn't go below 0
            score = max(0, score)
            
            return TrustFactorScore(
                factor=TrustFactor.NETWORK_BEHAVIOR,
                score=score,
                weight=self._weights[TrustFactor.NETWORK_BEHAVIOR],
                details={
                    "penalties": penalties,
                    "ip_count": ip_count,
                    "quota_status": quota_status["status"]
                }
            )
        except Exception as e:
            logger.error(f"Failed to calculate network score for {entity_id}: {e}")
            return TrustFactorScore(
                factor=TrustFactor.NETWORK_BEHAVIOR,
                score=50.0,
                weight=self._weights[TrustFactor.NETWORK_BEHAVIOR],
                details={"error": str(e)}
            )
    
    def _calculate_age_score(self, entity_id: str) -> TrustFactorScore:
        """Calculate account age score (0-100)"""
        try:
            from free_quota_system import get_quota_manager
            
            quota_manager = get_quota_manager()
            quota_status = quota_manager.get_quota_status(entity_id)
            
            first_task_at = quota_status.get("first_task_at")
            if not first_task_at:
                # No activity yet, neutral score
                return TrustFactorScore(
                    factor=TrustFactor.ACCOUNT_AGE,
                    score=50.0,
                    weight=self._weights[TrustFactor.ACCOUNT_AGE],
                    details={"status": "no_activity"}
                )
            
            first_task = datetime.fromisoformat(first_task_at)
            age_days = (datetime.now(timezone.utc) - first_task).days
            
            # Score based on account age
            if age_days >= 90:
                score = 100.0
            elif age_days >= 30:
                score = 80.0
            elif age_days >= 7:
                score = 60.0
            elif age_days >= 1:
                score = 40.0
            else:
                score = 20.0
            
            return TrustFactorScore(
                factor=TrustFactor.ACCOUNT_AGE,
                score=score,
                weight=self._weights[TrustFactor.ACCOUNT_AGE],
                details={
                    "age_days": age_days,
                    "first_task_at": first_task_at
                }
            )
        except Exception as e:
            logger.error(f"Failed to calculate age score for {entity_id}: {e}")
            return TrustFactorScore(
                factor=TrustFactor.ACCOUNT_AGE,
                score=50.0,
                weight=self._weights[TrustFactor.ACCOUNT_AGE],
                details={"error": str(e)}
            )
    
    def _calculate_contribution_score(self, entity_id: str) -> TrustFactorScore:
        """Calculate community contribution score (0-100)"""
        # This is a placeholder - would integrate with community contribution tracking
        # For now, base it on progressive quota status
        try:
            from free_quota_system import get_quota_manager
            
            quota_manager = get_quota_manager()
            quota_status = quota_manager.get_quota_status(entity_id)
            
            # Progressive quota indicates good standing
            if quota_status["status"] == "progressive":
                score = 100.0
            elif quota_status["trust_score"] > 0:
                score = quota_status["trust_score"]
            else:
                score = 50.0
            
            return TrustFactorScore(
                factor=TrustFactor.COMMUNITY_CONTRIBUTION,
                score=score,
                weight=self._weights[TrustFactor.COMMUNITY_CONTRIBUTION],
                details={
                    "quota_status": quota_status["status"],
                    "progressive_quota": quota_status.get("extended_quota", 0)
                }
            )
        except Exception as e:
            logger.error(f"Failed to calculate contribution score for {entity_id}: {e}")
            return TrustFactorScore(
                factor=TrustFactor.COMMUNITY_CONTRIBUTION,
                score=50.0,
                weight=self._weights[TrustFactor.COMMUNITY_CONTRIBUTION],
                details={"error": str(e)}
            )
    
    def calculate_trust_score(self, entity_id: str) -> TrustScoreRecord:
        """Calculate comprehensive trust score for an entity"""
        # Store previous score
        previous_score = None
        if entity_id in self._scores:
            previous_score = self._scores[entity_id].overall_score
        
        # Calculate all factor scores
        factor_scores = [
            self._calculate_transaction_score(entity_id),
            self._calculate_skill_score(entity_id),
            self._calculate_network_score(entity_id),
            self._calculate_age_score(entity_id),
            self._calculate_contribution_score(entity_id)
        ]
        
        # Calculate overall score
        overall_score = sum(fs.weighted_score for fs in factor_scores)
        
        # Determine tier
        tier = "unverified"
        for tier_name, threshold in sorted(self.TIER_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
            if overall_score >= threshold:
                tier = tier_name
                break
        
        # Calculate score change
        score_change = 0.0
        if previous_score is not None:
            score_change = overall_score - previous_score
        
        # Create record
        record = TrustScoreRecord(
            entity_id=entity_id,
            overall_score=overall_score,
            factor_scores=factor_scores,
            tier=tier,
            previous_score=previous_score,
            score_change=score_change
        )
        
        # Store record
        self._scores[entity_id] = record
        
        # Store in history
        if entity_id not in self._score_history:
            self._score_history[entity_id] = []
        self._score_history[entity_id].append({
            "timestamp": record.calculated_at,
            "score": overall_score,
            "tier": tier
        })
        # Keep last 100 entries
        self._score_history[entity_id] = self._score_history[entity_id][-100:]
        
        self._save()
        
        logger.info(f"Trust score calculated for {entity_id}: {overall_score:.2f} ({tier})")
        
        return record
    
    def get_trust_score(self, entity_id: str) -> Optional[TrustScoreRecord]:
        """Get trust score for an entity (calculate if not exists)"""
        if entity_id not in self._scores:
            return self.calculate_trust_score(entity_id)
        return self._scores[entity_id]
    
    def get_tier(self, entity_id: str) -> str:
        """Get trust tier for an entity"""
        score = self.get_trust_score(entity_id)
        return score.tier if score else "unverified"
    
    def is_trusted(self, entity_id: str, min_tier: str = "verified") -> bool:
        """Check if entity meets minimum trust tier"""
        tier_order = ["unverified", "basic", "verified", "trusted", "elite"]
        entity_tier = self.get_tier(entity_id)
        return tier_order.index(entity_tier) >= tier_order.index(min_tier)
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system-wide trust statistics"""
        total_entities = len(self._scores)
        if total_entities == 0:
            return {"total_entities": 0}
        
        tier_counts = {}
        for record in self._scores.values():
            tier = record.tier
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        avg_score = sum(r.overall_score for r in self._scores.values()) / total_entities
        
        return {
            "total_entities": total_entities,
            "tier_distribution": tier_counts,
            "average_score": round(avg_score, 2),
            "elite_count": tier_counts.get("elite", 0),
            "trusted_count": tier_counts.get("trusted", 0),
            "verified_count": tier_counts.get("verified", 0)
        }


# Global instance
_trust_engine: Optional[TrustScoreEngine] = None

def get_trust_engine() -> TrustScoreEngine:
    """Get or create global trust engine instance"""
    global _trust_engine
    if _trust_engine is None:
        _trust_engine = TrustScoreEngine()
    return _trust_engine


# Convenience functions
def calculate_trust_score(entity_id: str) -> Dict[str, Any]:
    """Calculate and return trust score"""
    record = get_trust_engine().calculate_trust_score(entity_id)
    return record.to_dict()

def get_trust_score(entity_id: str) -> Dict[str, Any]:
    """Get trust score for entity"""
    record = get_trust_engine().get_trust_score(entity_id)
    return record.to_dict() if record else {"error": "Not found"}

def is_trusted(entity_id: str, min_tier: str = "verified") -> bool:
    """Check if entity is trusted"""
    return get_trust_engine().is_trusted(entity_id, min_tier)


def get_system_stats() -> Dict[str, Any]:
    """Get system statistics"""
    return get_trust_engine().get_system_stats()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=== Trust Score Engine Demo ===\n")
    
    # Test with demo entity
    entity_id = "demo_entity_trust"
    
    print(f"Calculating trust score for: {entity_id}")
    score = calculate_trust_score(entity_id)
    
    print(f"\nOverall Score: {score['overall_score']:.2f}")
    print(f"Tier: {score['tier']}")
    print(f"Change: {score['score_change']:+.2f}")
    
    print("\nFactor Breakdown:")
    for factor in score['factor_scores']:
        print(f"  {factor['factor']}: {factor['score']:.1f} × {factor['weight']} = {factor['weighted_score']:.2f}")
    
    # System stats
    print("\nSystem Stats:")
    stats = get_system_stats()
    print(f"  Total entities: {stats['total_entities']}")
    print(f"  Average score: {stats.get('average_score', 0)}")
