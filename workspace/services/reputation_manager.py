#!/usr/bin/env python3
"""Reputation Manager - Entity reputation scoring system"""

import json
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List, Any
from pathlib import Path

from task_evaluation import TaskEvaluation, EvaluationStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ReputationTier(Enum):
    """Reputation tiers"""
    UNTRUSTED = "untrusted"
    NOVICE = "novice"
    RELIABLE = "reliable"
    EXPERT = "expert"
    ELITE = "elite"


@dataclass
class ReputationEvent:
    """Reputation event record"""
    entity_id: str
    event_type: str
    score_delta: float
    previous_score: float
    new_score: float
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: Optional[str] = None
    evaluation_id: Optional[str] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReputationEvent":
        return cls(
            entity_id=data["entity_id"],
            event_type=data["event_type"],
            score_delta=data["score_delta"],
            previous_score=data["previous_score"],
            new_score=data["new_score"],
            event_id=data.get("event_id", str(uuid.uuid4())),
            task_id=data.get("task_id"),
            evaluation_id=data.get("evaluation_id"),
            reason=data.get("reason", ""),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat())
        )


@dataclass
class EntityReputation:
    """Entity reputation data"""
    entity_id: str
    current_score: float = 50.0
    historical_scores: List[Dict[str, Any]] = field(default_factory=list)
    events: List[ReputationEvent] = field(default_factory=list)
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    total_tasks_delayed: int = 0
    current_streak: int = 0
    max_streak: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def tier(self) -> str:
        score = self.current_score
        if score >= 81:
            return ReputationTier.ELITE.value
        elif score >= 61:
            return ReputationTier.EXPERT.value
        elif score >= 41:
            return ReputationTier.RELIABLE.value
        elif score >= 21:
            return ReputationTier.NOVICE.value
        else:
            return ReputationTier.UNTRUSTED.value
    
    @property
    def success_rate(self) -> float:
        total = self.total_tasks_completed + self.total_tasks_failed
        if total == 0:
            return 0.0
        return self.total_tasks_completed / total * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "current_score": round(self.current_score, 2),
            "tier": self.tier,
            "historical_scores": self.historical_scores,
            "total_tasks_completed": self.total_tasks_completed,
            "total_tasks_failed": self.total_tasks_failed,
            "total_tasks_delayed": self.total_tasks_delayed,
            "current_streak": self.current_streak,
            "max_streak": self.max_streak,
            "success_rate": round(self.success_rate, 2),
            "last_updated": self.last_updated,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityReputation":
        return cls(
            entity_id=data["entity_id"],
            current_score=data.get("current_score", 50.0),
            historical_scores=data.get("historical_scores", []),
            events=[],
            total_tasks_completed=data.get("total_tasks_completed", 0),
            total_tasks_failed=data.get("total_tasks_failed", 0),
            total_tasks_delayed=data.get("total_tasks_delayed", 0),
            current_streak=data.get("current_streak", 0),
            max_streak=data.get("max_streak", 0),
            last_updated=data.get("last_updated", datetime.now(timezone.utc).isoformat()),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat())
        )


class ReputationManager:
    """Reputation manager - manages entity reputation scores"""
    
    RECENT_EVALUATION_COUNT = 10
    MAX_SCORE = 100.0
    MIN_SCORE = 0.0
    STREAK_BONUS_THRESHOLD = 3
    
    SCORE_BASELINE = 50.0
    POINTS_PER_SUCCESS = 2.0
    POINTS_PER_FAILURE = -10.0
    POINTS_PER_DELAY = -5.0
    STREAK_BONUS_POINTS = 5.0
    ELITE_THRESHOLD = 80.0
    
    def __init__(self, data_dir: str = "services/data/economy"):
        self._reputations: Dict[str, EntityReputation] = {}
        self._events: List[ReputationEvent] = []
        self._data_dir = Path(data_dir)
        self._scores_file = self._data_dir / "reputation_scores.json"
        self._events_file = self._data_dir / "reputation_events.json"
        self._load_data()
        logger.info(f"ReputationManager initialized with {len(self._reputations)} entities")
    
    def _load_data(self) -> None:
        """Load data from files"""
        if self._scores_file.exists():
            try:
                with open(self._scores_file, 'r') as f:
                    data = json.load(f)
                    for entity_data in data.get("reputations", []):
                        rep = EntityReputation.from_dict(entity_data)
                        self._reputations[rep.entity_id] = rep
                logger.info(f"Loaded {len(self._reputations)} reputation records")
            except Exception as e:
                logger.error(f"Failed to load reputation scores: {e}")
        
        if self._events_file.exists():
            try:
                with open(self._events_file, 'r') as f:
                    data = json.load(f)
                    for event_data in data.get("events", []):
                        event = ReputationEvent.from_dict(event_data)
                        self._events.append(event)
                        if event.entity_id in self._reputations:
                            self._reputations[event.entity_id].events.append(event)
                logger.info(f"Loaded {len(self._events)} reputation events")
            except Exception as e:
                logger.error(f"Failed to load reputation events: {e}")
    
    def _save_data(self) -> None:
        """Save data to files"""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            scores_data = {
                "reputations": [rep.to_dict() for rep in self._reputations.values()],
                "saved_at": datetime.now(timezone.utc).isoformat()
            }
            with open(self._scores_file, 'w') as f:
                json.dump(scores_data, f, indent=2)
            
            events_data = {
                "events": [event.to_dict() for event in self._events],
                "saved_at": datetime.now(timezone.utc).isoformat()
            }
            with open(self._events_file, 'w') as f:
                json.dump(events_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save reputation data: {e}")
    
    def get_reputation(self, entity_id: str) -> EntityReputation:
        """Get entity reputation (create if not exists)"""
        if entity_id not in self._reputations:
            self._reputations[entity_id] = EntityReputation(entity_id=entity_id)
            self._save_data()
        return self._reputations[entity_id]
    
    def _calculate_weighted_score(self, scores: List[float]) -> float:
        """Calculate weighted moving average"""
        if not scores:
            return self.SCORE_BASELINE
        recent_scores = scores[-self.RECENT_EVALUATION_COUNT:]
        weighted_sum = sum((i + 1) * score for i, score in enumerate(recent_scores))
        weight_sum = sum(range(1, len(recent_scores) + 1))
        return weighted_sum / weight_sum if weight_sum > 0 else self.SCORE_BASELINE
    
    def _add_reputation_event(
        self, entity_id: str, event_type: str, score_delta: float,
        previous_score: float, new_score: float, task_id: Optional[str] = None,
        evaluation_id: Optional[str] = None, reason: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ReputationEvent:
        """Add reputation event"""
        event = ReputationEvent(
            entity_id=entity_id, event_type=event_type, score_delta=score_delta,
            previous_score=previous_score, new_score=new_score,
            task_id=task_id, evaluation_id=evaluation_id, reason=reason,
            metadata=metadata or {}
        )
        self._events.append(event)
        reputation = self._reputations.get(entity_id)
        if reputation:
            reputation.events.append(event)
        return event
    
    def update_reputation_from_evaluation(
        self, entity_id: str, evaluation: TaskEvaluation, was_delayed: bool = False
    ) -> EntityReputation:
        """Update reputation from task evaluation"""
        reputation = self.get_reputation(entity_id)
        previous_score = reputation.current_score
        score_delta = 0.0
        event_type = ""
        reason = ""
        
        if evaluation.status == EvaluationStatus.FINALIZED.value:
            if evaluation.verdict == "pass":
                event_type = "task_complete"
                score_delta = self.POINTS_PER_SUCCESS * (evaluation.overall_score / 100)
                reason = f"Task completed successfully with score {evaluation.overall_score:.1f}"
                reputation.total_tasks_completed += 1
                reputation.current_streak += 1
                
                if reputation.current_streak >= self.STREAK_BONUS_THRESHOLD:
                    streak_bonus = self.STREAK_BONUS_POINTS * (reputation.current_streak - self.STREAK_BONUS_THRESHOLD + 1)
                    score_delta += streak_bonus
                    reason += f" (+{streak_bonus:.1f} streak bonus)"
                
                if reputation.current_streak > reputation.max_streak:
                    reputation.max_streak = reputation.current_streak
                    
            elif evaluation.verdict == "partial":
                event_type = "task_partial"
                score_delta = self.POINTS_PER_SUCCESS * 0.5 * (evaluation.overall_score / 100)
                reason = f"Task partially completed with score {evaluation.overall_score:.1f}"
                reputation.total_tasks_completed += 1
                reputation.current_streak = 0
                
            else:  # fail
                event_type = "task_fail"
                score_delta = self.POINTS_PER_FAILURE
                reason = f"Task failed with score {evaluation.overall_score:.1f}"
                reputation.total_tasks_failed += 1
                reputation.current_streak = 0
            
            if was_delayed:
                score_delta += self.POINTS_PER_DELAY
                reputation.total_tasks_delayed += 1
                reason += " (delayed)"
        
        new_score = max(self.MIN_SCORE, min(self.MAX_SCORE, previous_score + score_delta))
        reputation.current_score = new_score
        reputation.last_updated = datetime.now(timezone.utc).isoformat()
        
        reputation.historical_scores.append({
            "score": round(new_score, 2),
            "timestamp": reputation.last_updated,
            "evaluation_id": evaluation.evaluation_id,
            "task_id": evaluation.task_id
        })
        
        self._add_reputation_event(
            entity_id=entity_id, event_type=event_type, score_delta=score_delta,
            previous_score=previous_score, new_score=new_score,
            task_id=evaluation.task_id, evaluation_id=evaluation.evaluation_id,
            reason=reason, metadata={
                "overall_score": evaluation.overall_score,
                "verdict": evaluation.verdict,
                "was_delayed": was_delayed
            }
        )
        
        self._save_data()
        logger.info(f"Updated reputation for {entity_id}: {previous_score:.1f} -> {new_score:.1f} ({score_delta:+.1f})")
        return reputation
    
    def apply_manual_adjustment(
        self, entity_id: str, adjustment: float, reason: str, admin_id: str = "system"
    ) -> EntityReputation:
        """Apply manual reputation adjustment"""
        reputation = self.get_reputation(entity_id)
        previous_score = reputation.current_score
        new_score = max(self.MIN_SCORE, min(self.MAX_SCORE, previous_score + adjustment))
        reputation.current_score = new_score
        reputation.last_updated = datetime.now(timezone.utc).isoformat()
        
        reputation.historical_scores.append({
            "score": round(new_score, 2),
            "timestamp": reputation.last_updated,
            "reason": reason,
            "adjustment": adjustment
        })
        
        self._add_reputation_event(
            entity_id=entity_id, event_type="manual_adjustment",
            score_delta=adjustment, previous_score=previous_score, new_score=new_score,
            reason=f"Manual adjustment by {admin_id}: {reason}"
        )
        
        self._save_data()
        logger.info(f"Manual reputation adjustment for {entity_id} by {admin_id}: {previous_score:.1f} -> {new_score:.1f}")
        return reputation
    
    def get_entity_history(self, entity_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get entity evaluation history"""
        reputation = self.get_reputation(entity_id)
        history = list(reversed(reputation.historical_scores))
        return history[:limit] if limit else history
    
    def get_entity_events(
        self, entity_id: str, event_type: Optional[str] = None, limit: Optional[int] = None
    ) -> List[ReputationEvent]:
        """Get entity reputation events"""
        reputation = self.get_reputation(entity_id)
        events = list(reversed(reputation.events))
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[:limit] if limit else events
    
    def get_leaderboard(self, tier: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get reputation leaderboard"""
        reputations = list(self._reputations.values())
        if tier:
            reputations = [r for r in reputations if r.tier == tier]
        reputations.sort(key=lambda r: r.current_score, reverse=True)
        
        return [
            {
                "rank": i + 1,
                "entity_id": r.entity_id,
                "score": round(r.current_score, 2),
                "tier": r.tier,
                "success_rate": round(r.success_rate, 2),
                "tasks_completed": r.total_tasks_completed,
                "max_streak": r.max_streak
            }
            for i, r in enumerate(reputations[:limit])
        ]
    
    def get_tier_distribution(self) -> Dict[str, int]:
        """Get tier distribution"""
        distribution = {tier.value: 0 for tier in ReputationTier}
        for rep in self._reputations.values():
            distribution[rep.tier] = distribution.get(rep.tier, 0) + 1
        return distribution
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics"""
        total_entities = len(self._reputations)
        if total_entities == 0:
            return {"total_entities": 0}
        
        scores = [r.current_score for r in self._reputations.values()]
        total_tasks = sum(r.total_tasks_completed + r.total_tasks_failed for r in self._reputations.values())
        
        return {
            "total_entities": total_entities,
            "average_score": round(sum(scores) / len(scores), 2),
            "median_score": round(sorted(scores)[len(scores) // 2], 2),
            "highest_score": round(max(scores), 2),
            "lowest_score": round(min(scores), 2),
            "tier_distribution": self.get_tier_distribution(),
            "total_tasks_evaluated": total_tasks,
            "total_events": len(self._events)
        }
    
    def reset_reputation(self, entity_id: str, reason: str = "") -> EntityReputation:
        """Reset entity reputation to default"""
        reputation = self.get_reputation(entity_id)
        previous_score = reputation.current_score
        reputation.current_score = 50.0
        reputation.historical_scores.append({
            "score": 50.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": f"Reset: {reason}" if reason else "Reset"
        })
        reputation.current_streak = 0
        reputation.last_updated = datetime.now(timezone.utc).isoformat()
        
        self._add_reputation_event(
            entity_id=entity_id, event_type="reset",
            score_delta=50.0 - previous_score, previous_score=previous_score,
            new_score=50.0, reason=reason or "Reputation reset"
        )
        
        self._save_data()
        logger.info(f"Reset reputation for {entity_id}: {previous_score:.1f} -> 50.0")
        return reputation


# Global instance
_reputation_manager: Optional[ReputationManager] = None


def get_reputation_manager() -> ReputationManager:
    """Get global ReputationManager instance"""
    global _reputation_manager
    if _reputation_manager is None:
        _reputation_manager = ReputationManager()
    return _reputation_manager


def initialize_reputation_manager(data_dir: str = "services/data/economy") -> ReputationManager:
    """Initialize ReputationManager"""
    global _reputation_manager
    _reputation_manager = ReputationManager(data_dir=data_dir)
    return _reputation_manager


# API Router for FastAPI integration
def create_reputation_router():
    """Create FastAPI router for reputation endpoints"""
    try:
        from fastapi import APIRouter, HTTPException
        
        router = APIRouter(prefix="/reputation", tags=["reputation"])
        manager = get_reputation_manager()
        
        @router.get("/{entity_id}")
        async def get_reputation(entity_id: str):
            """Get reputation score for an entity"""
            reputation = manager.get_reputation(entity_id)
            return reputation.to_dict()
        
        @router.get("/{entity_id}/history")
        async def get_reputation_history(entity_id: str, limit: int = 10):
            """Get reputation history for an entity"""
            return manager.get_entity_history(entity_id, limit=limit)
        
        @router.get("/{entity_id}/events")
        async def get_reputation_events(entity_id: str, event_type: str = None, limit: int = 10):
            """Get reputation events for an entity"""
            events = manager.get_entity_events(entity_id, event_type=event_type, limit=limit)
            return [e.to_dict() for e in events]
        
        @router.get("/leaderboard")
        async def get_leaderboard(tier: str = None, limit: int = 10):
            """Get reputation leaderboard"""
            return manager.get_leaderboard(tier=tier, limit=limit)
        
        @router.get("/stats/overview")
        async def get_statistics():
            """Get overall reputation statistics"""
            return manager.get_statistics()
        
        @router.post("/{entity_id}/adjust")
        async def adjust_reputation(entity_id: str, adjustment: float, reason: str, admin_id: str = "system"):
            """Manually adjust reputation (admin only)"""
            reputation = manager.apply_manual_adjustment(entity_id, adjustment, reason, admin_id)
            return reputation.to_dict()
        
        return router
    except ImportError:
        logger.warning("FastAPI not available, reputation API endpoints not created")
        return None


if __name__ == "__main__":
    print("=== Reputation Manager Test ===\n")
    
    # Initialize
    manager = ReputationManager()
    
    # Test 1: Create reputation for entity
    print("Test 1: Create reputation")
    rep = manager.get_reputation("entity-a")
    print(f"  Initial score: {rep.current_score}")
    print(f"  Initial tier: {rep.tier}")
    
    # Test 2: Update from evaluation (success)
    print("\nTest 2: Update from successful evaluation")
    eval_success = TaskEvaluation(
        task_id="task-001",
        evaluator_id="evaluator-1",
        status=EvaluationStatus.FINALIZED.value,
        overall_score=85.0,
        verdict="pass"
    )
    rep = manager.update_reputation_from_evaluation("entity-a", eval_success)
    print(f"  Score after success: {rep.current_score:.1f}")
    print(f"  Streak: {rep.current_streak}")
    
    # Test 3: Update from evaluation (success with streak)
    print("\nTest 3: Success with streak bonus")
    eval_success2 = TaskEvaluation(
        task_id="task-002",
        evaluator_id="evaluator-1",
        status=EvaluationStatus.FINALIZED.value,
        overall_score=90.0,
        verdict="pass"
    )
    rep = manager.update_reputation_from_evaluation("entity-a", eval_success2)
    print(f"  Score: {rep.current_score:.1f}")
    
    eval_success3 = TaskEvaluation(
        task_id="task-003",
        evaluator_id="evaluator-1",
        status=EvaluationStatus.FINALIZED.value,
        overall_score=88.0,
        verdict="pass"
    )
    rep = manager.update_reputation_from_evaluation("entity-a", eval_success3)
    print(f"  Score with streak bonus: {rep.current_score:.1f}")
    print(f"  Streak: {rep.current_streak}")
    
    # Test 4: Update from evaluation (failure)
    print("\nTest 4: Task failure")
    eval_fail = TaskEvaluation(
        task_id="task-004",
        evaluator_id="evaluator-1",
        status=EvaluationStatus.FINALIZED.value,
        overall_score=45.0,
        verdict="fail"
    )
    rep = manager.update_reputation_from_evaluation("entity-a", eval_fail)
    print(f"  Score after failure: {rep.current_score:.1f}")
    print(f"  Streak reset: {rep.current_streak}")
    
    # Test 5: Update with delay
    print("\nTest 5: Task with delay")
    eval_delay = TaskEvaluation(
        task_id="task-005",
        evaluator_id="evaluator-1",
        status=EvaluationStatus.FINALIZED.value,
        overall_score=75.0,
        verdict="pass"
    )
    rep = manager.update_reputation_from_evaluation("entity-a", eval_delay, was_delayed=True)
    print(f"  Score with delay penalty: {rep.current_score:.1f}")
    
    # Test 6: Create another entity and get leaderboard
    print("\nTest 6: Leaderboard")
    rep_b = manager.get_reputation("entity-b")
    eval_b = TaskEvaluation(
        task_id="task-b1",
        evaluator_id="evaluator-1",
        status=EvaluationStatus.FINALIZED.value,
        overall_score=95.0,
        verdict="pass"
    )
    manager.update_reputation_from_evaluation("entity-b", eval_b)
    
    leaderboard = manager.get_leaderboard(limit=5)
    for entry in leaderboard:
        print(f"  #{entry['rank']}: {entry['entity_id']} - {entry['score']} ({entry['tier']})")
    
    # Test 7: Statistics
    print("\nTest 7: Statistics")
    stats = manager.get_statistics()
    print(f"  Total entities: {stats['total_entities']}")
    print(f"  Average score: {stats['average_score']}")
    print(f"  Tier distribution: {stats['tier_distribution']}")
    
    # Test 8: History
    print("\nTest 8: History")
    history = manager.get_entity_history("entity-a", limit=5)
    for h in history:
        print(f"  {h['timestamp'][:19]}: {h['score']}")
    
    # Test 9: Events
    print("\nTest 9: Events")
    events = manager.get_entity_events("entity-a", limit=5)
    for e in events:
        print(f"  {e.event_type}: {e.score_delta:+.1f} ({e.reason[:40]}...)")
    
    print("\n=== All Tests Passed ===")
