#!/usr/bin/env python3
"""
Tests for Reputation Manager
"""

import sys
import os
import json
import tempfile
import shutil
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

import unittest
from datetime import datetime, timezone

from reputation_manager import (
    ReputationManager, ReputationEvent, EntityReputation,
    ReputationTier, get_reputation_manager, initialize_reputation_manager
)
from task_evaluation import TaskEvaluation, EvaluationStatus


class TestReputationEvent(unittest.TestCase):
    """Test ReputationEvent dataclass"""
    
    def test_event_creation(self):
        """Test creating a reputation event"""
        event = ReputationEvent(
            entity_id="entity-1",
            event_type="task_complete",
            score_delta=2.0,
            previous_score=50.0,
            new_score=52.0,
            task_id="task-001",
            reason="Task completed successfully"
        )
        
        self.assertEqual(event.entity_id, "entity-1")
        self.assertEqual(event.event_type, "task_complete")
        self.assertEqual(event.score_delta, 2.0)
        self.assertEqual(event.previous_score, 50.0)
        self.assertEqual(event.new_score, 52.0)
        self.assertEqual(event.task_id, "task-001")
        self.assertEqual(event.reason, "Task completed successfully")
    
    def test_event_to_dict(self):
        """Test converting event to dictionary"""
        event = ReputationEvent(
            entity_id="entity-1",
            event_type="task_complete",
            score_delta=2.0,
            previous_score=50.0,
            new_score=52.0
        )
        
        data = event.to_dict()
        self.assertEqual(data["entity_id"], "entity-1")
        self.assertEqual(data["event_type"], "task_complete")
        self.assertEqual(data["score_delta"], 2.0)
        self.assertIn("timestamp", data)
    
    def test_event_from_dict(self):
        """Test creating event from dictionary"""
        data = {
            "entity_id": "entity-1",
            "event_type": "task_fail",
            "score_delta": -10.0,
            "previous_score": 60.0,
            "new_score": 50.0,
            "task_id": "task-002",
            "reason": "Task failed"
        }
        
        event = ReputationEvent.from_dict(data)
        self.assertEqual(event.entity_id, "entity-1")
        self.assertEqual(event.event_type, "task_fail")
        self.assertEqual(event.score_delta, -10.0)


class TestEntityReputation(unittest.TestCase):
    """Test EntityReputation dataclass"""
    
    def test_default_creation(self):
        """Test creating reputation with defaults"""
        rep = EntityReputation(entity_id="entity-1")
        
        self.assertEqual(rep.entity_id, "entity-1")
        self.assertEqual(rep.current_score, 50.0)
        self.assertEqual(rep.total_tasks_completed, 0)
        self.assertEqual(rep.total_tasks_failed, 0)
        self.assertEqual(rep.current_streak, 0)
    
    def test_tier_calculation(self):
        """Test tier calculation based on score"""
        test_cases = [
            (10.0, ReputationTier.UNTRUSTED.value),
            (30.0, ReputationTier.NOVICE.value),
            (50.0, ReputationTier.RELIABLE.value),
            (70.0, ReputationTier.EXPERT.value),
            (90.0, ReputationTier.ELITE.value),
        ]
        
        for score, expected_tier in test_cases:
            rep = EntityReputation(entity_id="test", current_score=score)
            self.assertEqual(rep.tier, expected_tier, f"Score {score} should be {expected_tier}")
    
    def test_success_rate(self):
        """Test success rate calculation"""
        rep = EntityReputation(
            entity_id="entity-1",
            total_tasks_completed=8,
            total_tasks_failed=2
        )
        
        self.assertEqual(rep.success_rate, 80.0)
    
    def test_success_rate_zero_division(self):
        """Test success rate with no tasks"""
        rep = EntityReputation(entity_id="entity-1")
        self.assertEqual(rep.success_rate, 0.0)
    
    def test_to_dict(self):
        """Test converting to dictionary"""
        rep = EntityReputation(
            entity_id="entity-1",
            current_score=75.0,
            total_tasks_completed=10
        )
        
        data = rep.to_dict()
        self.assertEqual(data["entity_id"], "entity-1")
        self.assertEqual(data["current_score"], 75.0)
        self.assertEqual(data["tier"], ReputationTier.EXPERT.value)
        self.assertEqual(data["total_tasks_completed"], 10)
        self.assertIn("success_rate", data)
    
    def test_from_dict(self):
        """Test creating from dictionary"""
        data = {
            "entity_id": "entity-1",
            "current_score": 80.0,
            "total_tasks_completed": 5,
            "total_tasks_failed": 1,
            "current_streak": 3
        }
        
        rep = EntityReputation.from_dict(data)
        self.assertEqual(rep.entity_id, "entity-1")
        self.assertEqual(rep.current_score, 80.0)
        self.assertEqual(rep.total_tasks_completed, 5)


class TestReputationManager(unittest.TestCase):
    """Test ReputationManager class"""
    
    def setUp(self):
        """Create temporary directory for test data"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = ReputationManager(data_dir=self.temp_dir)
    
    def tearDown(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_get_reputation_create_new(self):
        """Test getting reputation creates new entity"""
        rep = self.manager.get_reputation("new-entity")
        
        self.assertEqual(rep.entity_id, "new-entity")
        self.assertEqual(rep.current_score, 50.0)
        self.assertEqual(rep.tier, ReputationTier.RELIABLE.value)
    
    def test_update_from_evaluation_pass(self):
        """Test updating reputation from passed evaluation"""
        evaluation = TaskEvaluation(
            task_id="task-001",
            evaluator_id="eval-1",
            status=EvaluationStatus.FINALIZED.value,
            overall_score=90.0,
            verdict="pass"
        )
        
        rep = self.manager.update_reputation_from_evaluation("entity-1", evaluation)
        
        self.assertGreater(rep.current_score, 50.0)  # Score should increase
        self.assertEqual(rep.total_tasks_completed, 1)
        self.assertEqual(rep.current_streak, 1)
    
    def test_update_from_evaluation_fail(self):
        """Test updating reputation from failed evaluation"""
        evaluation = TaskEvaluation(
            task_id="task-001",
            evaluator_id="eval-1",
            status=EvaluationStatus.FINALIZED.value,
            overall_score=40.0,
            verdict="fail"
        )
        
        rep = self.manager.update_reputation_from_evaluation("entity-1", evaluation)
        
        self.assertLess(rep.current_score, 50.0)  # Score should decrease
        self.assertEqual(rep.total_tasks_failed, 1)
        self.assertEqual(rep.current_streak, 0)
    
    def test_update_from_evaluation_partial(self):
        """Test updating reputation from partial evaluation"""
        evaluation = TaskEvaluation(
            task_id="task-001",
            evaluator_id="eval-1",
            status=EvaluationStatus.FINALIZED.value,
            overall_score=75.0,
            verdict="partial"
        )
        
        rep = self.manager.update_reputation_from_evaluation("entity-1", evaluation)
        
        self.assertEqual(rep.total_tasks_completed, 1)
        self.assertEqual(rep.current_streak, 0)  # Streak resets on partial
    
    def test_streak_bonus(self):
        """Test streak bonus calculation"""
        # Complete 3 tasks successfully
        for i in range(3):
            evaluation = TaskEvaluation(
                task_id=f"task-{i}",
                evaluator_id="eval-1",
                status=EvaluationStatus.FINALIZED.value,
                overall_score=90.0,
                verdict="pass"
            )
            rep = self.manager.update_reputation_from_evaluation("entity-1", evaluation)
        
        self.assertGreaterEqual(rep.current_streak, 3)
        self.assertEqual(rep.max_streak, 3)
    
    def test_delay_penalty(self):
        """Test delay penalty application"""
        evaluation = TaskEvaluation(
            task_id="task-001",
            evaluator_id="eval-1",
            status=EvaluationStatus.FINALIZED.value,
            overall_score=80.0,
            verdict="pass"
        )
        
        rep_without_delay = self.manager.update_reputation_from_evaluation("entity-no-delay", evaluation)
        rep_with_delay = self.manager.update_reputation_from_evaluation("entity-delay", evaluation, was_delayed=True)
        
        self.assertEqual(rep_with_delay.total_tasks_delayed, 1)
        # Delayed score should be lower
        self.assertLess(rep_with_delay.current_score, rep_without_delay.current_score)
    
    def test_score_bounds(self):
        """Test score boundaries (0-100)"""
        # Try to exceed max score
        for i in range(50):
            evaluation = TaskEvaluation(
                task_id=f"task-{i}",
                evaluator_id="eval-1",
                status=EvaluationStatus.FINALIZED.value,
                overall_score=100.0,
                verdict="pass"
            )
            rep = self.manager.update_reputation_from_evaluation("entity-max", evaluation)
        
        self.assertLessEqual(rep.current_score, 100.0)
        
        # Try to go below min score
        for i in range(20):
            evaluation = TaskEvaluation(
                task_id=f"task-fail-{i}",
                evaluator_id="eval-1",
                status=EvaluationStatus.FINALIZED.value,
                overall_score=0.0,
                verdict="fail"
            )
            rep = self.manager.update_reputation_from_evaluation("entity-min", evaluation)
        
        self.assertGreaterEqual(rep.current_score, 0.0)
    
    def test_manual_adjustment(self):
        """Test manual reputation adjustment"""
        rep = self.manager.get_reputation("entity-1")
        initial_score = rep.current_score
        
        rep = self.manager.apply_manual_adjustment("entity-1", 10.0, "Bonus for excellence", "admin-1")
        
        self.assertEqual(rep.current_score, initial_score + 10.0)
        self.assertEqual(len(rep.historical_scores), 2)  # Initial + adjustment
    
    def test_manual_adjustment_bounds(self):
        """Test manual adjustment respects bounds"""
        # Try to exceed max
        rep = self.manager.apply_manual_adjustment("entity-1", 100.0, "Big bonus", "admin")
        self.assertLessEqual(rep.current_score, 100.0)
        
        # Try to go below min
        rep = self.manager.apply_manual_adjustment("entity-1", -200.0, "Big penalty", "admin")
        self.assertGreaterEqual(rep.current_score, 0.0)
    
    def test_get_entity_history(self):
        """Test getting entity history"""
        # Create some evaluations
        for i in range(5):
            evaluation = TaskEvaluation(
                task_id=f"task-{i}",
                evaluator_id="eval-1",
                status=EvaluationStatus.FINALIZED.value,
                overall_score=80.0,
                verdict="pass"
            )
            self.manager.update_reputation_from_evaluation("entity-1", evaluation)
        
        history = self.manager.get_entity_history("entity-1")
        self.assertGreaterEqual(len(history), 5)
        
        # Test limit
        history_limited = self.manager.get_entity_history("entity-1", limit=3)
        self.assertEqual(len(history_limited), 3)
    
    def test_get_entity_events(self):
        """Test getting entity events"""
        evaluation = TaskEvaluation(
            task_id="task-001",
            evaluator_id="eval-1",
            status=EvaluationStatus.FINALIZED.value,
            overall_score=80.0,
            verdict="pass"
        )
        self.manager.update_reputation_from_evaluation("entity-1", evaluation)
        
        events = self.manager.get_entity_events("entity-1")
        self.assertGreaterEqual(len(events), 1)
        
        # Test filter by type
        complete_events = self.manager.get_entity_events("entity-1", event_type="task_complete")
        self.assertEqual(len(complete_events), 1)
    
    def test_get_leaderboard(self):
        """Test leaderboard functionality"""
        # Create multiple entities with different scores
        entities = [
            ("entity-high", 95.0, "pass"),
            ("entity-mid", 70.0, "pass"),
            ("entity-low", 40.0, "fail"),
        ]
        
        for entity_id, score, verdict in entities:
            evaluation = TaskEvaluation(
                task_id=f"task-{entity_id}",
                evaluator_id="eval-1",
                status=EvaluationStatus.FINALIZED.value,
                overall_score=score,
                verdict=verdict
            )
            self.manager.update_reputation_from_evaluation(entity_id, evaluation)
        
        leaderboard = self.manager.get_leaderboard(limit=10)
        self.assertEqual(len(leaderboard), 3)
        
        # Check ranking order (highest first)
        self.assertEqual(leaderboard[0]["entity_id"], "entity-high")
        self.assertEqual(leaderboard[2]["entity_id"], "entity-low")
    
    def test_get_leaderboard_by_tier(self):
        """Test leaderboard filtered by tier"""
        # Create entities in different tiers
        for i, (entity_id, score) in enumerate([
            ("entity-elite", 90.0),
            ("entity-expert", 75.0),
            ("entity-elite2", 85.0),
        ]):
            evaluation = TaskEvaluation(
                task_id=f"task-{entity_id}",
                evaluator_id="eval-1",
                status=EvaluationStatus.FINALIZED.value,
                overall_score=score,
                verdict="pass"
            )
            self.manager.update_reputation_from_evaluation(entity_id, evaluation)
        
        elite_leaderboard = self.manager.get_leaderboard(tier=ReputationTier.ELITE.value)
        self.assertEqual(len(elite_leaderboard), 2)
    
    def test_get_tier_distribution(self):
        """Test tier distribution"""
        distribution = self.manager.get_tier_distribution()
        
        self.assertIn(ReputationTier.UNTRUSTED.value, distribution)
        self.assertIn(ReputationTier.ELITE.value, distribution)
    
    def test_get_statistics(self):
        """Test overall statistics"""
        # Create some data
        evaluation = TaskEvaluation(
            task_id="task-001",
            evaluator_id="eval-1",
            status=EvaluationStatus.FINALIZED.value,
            overall_score=80.0,
            verdict="pass"
        )
        self.manager.update_reputation_from_evaluation("entity-1", evaluation)
        
        stats = self.manager.get_statistics()
        
        self.assertIn("total_entities", stats)
        self.assertIn("average_score", stats)
        self.assertIn("tier_distribution", stats)
        self.assertEqual(stats["total_entities"], 1)
    
    def test_reset_reputation(self):
        """Test reputation reset"""
        # Build up some reputation
        evaluation = TaskEvaluation(
            task_id="task-001",
            evaluator_id="eval-1",
            status=EvaluationStatus.FINALIZED.value,
            overall_score=95.0,
            verdict="pass"
        )
        self.manager.update_reputation_from_evaluation("entity-1", evaluation)
        
        rep = self.manager.get_reputation("entity-1")
        self.assertGreater(rep.current_score, 50.0)
        
        # Reset
        rep = self.manager.reset_reputation("entity-1", "Test reset")
        self.assertEqual(rep.current_score, 50.0)
        self.assertEqual(rep.current_streak, 0)
    
    def test_persistence(self):
        """Test data persistence"""
        # Create data
        evaluation = TaskEvaluation(
            task_id="task-001",
            evaluator_id="eval-1",
            status=EvaluationStatus.FINALIZED.value,
            overall_score=80.0,
            verdict="pass"
        )
        self.manager.update_reputation_from_evaluation("entity-1", evaluation)
        
        # Create new manager instance (should load saved data)
        new_manager = ReputationManager(data_dir=self.temp_dir)
        rep = new_manager.get_reputation("entity-1")
        
        self.assertNotEqual(rep.current_score, 50.0)  # Should have loaded saved score
        self.assertEqual(rep.total_tasks_completed, 1)
    
    def test_calculate_weighted_score(self):
        """Test weighted score calculation"""
        scores = [50.0, 60.0, 70.0, 80.0, 90.0]
        weighted = self.manager._calculate_weighted_score(scores)
        
        # Weighted average should be higher than simple average (newer scores weighted more)
        simple_avg = sum(scores) / len(scores)
        self.assertGreater(weighted, simple_avg)
    
    def test_empty_scores_weighted_average(self):
        """Test weighted average with empty scores"""
        weighted = self.manager._calculate_weighted_score([])
        self.assertEqual(weighted, 50.0)  # Should return baseline


class TestGlobalInstance(unittest.TestCase):
    """Test global instance functions"""
    
    def test_get_reputation_manager(self):
        """Test getting global instance"""
        manager1 = get_reputation_manager()
        manager2 = get_reputation_manager()
        
        self.assertIs(manager1, manager2)  # Same instance
    
    def test_initialize_reputation_manager(self):
        """Test initializing global instance"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = initialize_reputation_manager(data_dir=temp_dir)
            self.assertIsInstance(manager, ReputationManager)
            
            # Verify it's set as global
            global_manager = get_reputation_manager()
            self.assertIs(manager, global_manager)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestReputationEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestEntityReputation))
    suite.addTests(loader.loadTestsFromTestCase(TestReputationManager))
    suite.addTests(loader.loadTestsFromTestCase(TestGlobalInstance))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
