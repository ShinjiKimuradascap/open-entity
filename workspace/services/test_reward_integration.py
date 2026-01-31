#!/usr/bin/env python3
"""
Reward Integration Tests
報酬連携モジュールのテスト
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from reward_integration import (
    RewardRecord, RewardIntegration, AutoRewardEvaluator,
    get_reward_integration, initialize_reward_integration
)
from token_economy import get_token_economy
from token_system import get_wallet, create_wallet


def test_reward_record_dataclass():
    """Test 1: RewardRecordデータクラス"""
    print("Test 1: RewardRecord dataclass")
    
    record = RewardRecord(
        record_id="rec-001",
        task_id="task-001",
        evaluation_id="eval-001",
        recipient_id="entity-a",
        amount=100.0,
        status="issued",
        reason="Test reward"
    )
    
    # to_dict test
    data = record.to_dict()
    assert data["record_id"] == "rec-001"
    assert data["amount"] == 100.0
    
    # from_dict test
    restored = RewardRecord.from_dict(data)
    assert restored.record_id == record.record_id
    assert restored.amount == record.amount
    
    print("  ✓ RewardRecord serialization passed")


def test_reward_issuance():
    """Test 2: 報酬発行"""
    print("\nTest 2: Reward issuance")
    
    integration = RewardIntegration()
    economy = get_token_economy()
    initial_supply = economy.get_total_supply()
    
    # Issue reward
    record = integration.issue_reward(
        task_id="task-test-001",
        evaluation_id="eval-test-001",
        recipient_id="test-entity",
        amount=50.0,
        reason="Test completion"
    )
    
    assert record is not None
    assert record.status == "issued"
    assert record.amount == 50.0
    
    # Check token supply increased
    new_supply = economy.get_total_supply()
    assert new_supply == initial_supply + 50.0
    
    # Check wallet balance
    wallet = get_wallet("test-entity")
    assert wallet.get_balance() == 50.0
    
    print(f"  ✓ Issued {record.amount} AIC")
    print(f"  ✓ Token supply: {initial_supply} → {new_supply}")


def test_reward_lookup():
    """Test 3: 報酬記録検索"""
    print("\nTest 3: Reward lookup")
    
    integration = RewardIntegration()
    
    # Create multiple rewards
    integration.issue_reward("task-a", "eval-a", "entity-1", 10.0, "Task A")
    integration.issue_reward("task-b", "eval-b", "entity-1", 20.0, "Task B")
    integration.issue_reward("task-c", "eval-c", "entity-2", 30.0, "Task C")
    
    # Get by task
    found = integration.get_reward_by_task("task-a")
    assert found is not None
    assert found.amount == 10.0
    print("  ✓ Get by task ID works")
    
    # Get by evaluation
    found = integration.get_reward_by_evaluation("eval-b")
    assert found is not None
    assert found.amount == 20.0
    print("  ✓ Get by evaluation ID works")
    
    # Get entity rewards
    entity1_rewards = integration.get_entity_rewards("entity-1")
    assert len(entity1_rewards) == 2
    print(f"  ✓ Entity-1 has {len(entity1_rewards)} rewards")


def test_total_rewards_calculation():
    """Test 4: 報酬合計計算"""
    print("\nTest 4: Total rewards calculation")
    
    integration = RewardIntegration()
    
    # Calculate totals
    entity1_total = integration.get_total_rewards_issued("entity-1")
    entity2_total = integration.get_total_rewards_issued("entity-2")
    all_total = integration.get_total_rewards_issued()
    
    assert entity1_total == 30.0  # 10 + 20
    assert entity2_total == 30.0  # 30
    assert all_total >= 60.0  # At least our test amounts
    
    print(f"  ✓ Entity-1 total: {entity1_total} AIC")
    print(f"  ✓ Entity-2 total: {entity2_total} AIC")


def test_statistics():
    """Test 5: 統計情報"""
    print("\nTest 5: Statistics")
    
    integration = RewardIntegration()
    stats = integration.get_statistics()
    
    assert "total_records" in stats
    assert "issued" in stats
    assert "total_amount_issued" in stats
    assert "token_supply" in stats
    
    print(f"  ✓ Total records: {stats['total_records']}")
    print(f"  ✓ Issued count: {stats['issued']}")
    print(f"  ✓ Total amount: {stats['total_amount_issued']} AIC")


def test_integration_with_evaluation():
    """Test 6: 評価との統合"""
    print("\nTest 6: Integration with evaluation")
    
    from task_evaluation import TaskEvaluation, EvaluationStatus
    
    integration = RewardIntegration()
    
    # Create mock evaluation
    evaluation = TaskEvaluation(
        task_id="task-eval-test",
        evaluation_id="eval-test-123",
        evaluator_id="evaluator-1",
        status=EvaluationStatus.FINALIZED.value,
        overall_score=85.0,
        verdict="pass",
        reward_recommendation=100.0
    )
    
    # Issue from evaluation
    record = integration.issue_reward_from_evaluation(evaluation)
    
    assert record is not None
    assert record.status == "issued"
    assert record.amount == 100.0
    assert record.recipient_id == "evaluator-1"  # From evaluator_id
    
    print(f"  ✓ Auto-issued from evaluation: {record.amount} AIC")


def test_zero_reward_handling():
    """Test 7: ゼロ報酬処理"""
    print("\nTest 7: Zero reward handling")
    
    integration = RewardIntegration()
    
    # Should not issue for zero/negative
    record = integration.issue_reward(
        task_id="task-zero",
        evaluation_id="eval-zero",
        recipient_id="entity-z",
        amount=0.0
    )
    assert record is None
    print("  ✓ Zero amount rejected")
    
    record = integration.issue_reward(
        task_id="task-neg",
        evaluation_id="eval-neg",
        recipient_id="entity-z",
        amount=-10.0
    )
    assert record is None
    print("  ✓ Negative amount rejected")


def run_all_tests():
    """全テスト実行"""
    print("=== Reward Integration Tests ===\n")
    
    try:
        test_reward_record_dataclass()
        test_reward_issuance()
        test_reward_lookup()
        test_total_rewards_calculation()
        test_statistics()
        test_integration_with_evaluation()
        test_zero_reward_handling()
        
        print("\n" + "=" * 40)
        print("All 7 tests passed! ✓")
        print("=" * 40)
        return True
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
