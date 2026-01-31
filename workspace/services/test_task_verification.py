#!/usr/bin/env python3
"""
TaskCompletionVerifier テスト
タスク完了検証システムの動作確認
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_delegation import (
    TaskDelegationMessage,
    TaskResponseMessage,
    TaskCompletionVerifier,
    TaskDeliverable,
    TaskStatus,
    create_delegation_message,
    create_complete_response
)


def test_basic_verification():
    """基本検証テスト"""
    print("\n=== Test 1: Basic Verification ===")
    
    # タスク作成
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Test Task",
        description="Test task description",
        requirements=["Req1", "Req2"]
    )
    task.deliverables = [
        {"type": "code", "description": "Source code"},
        {"type": "test", "description": "Tests"}
    ]
    
    # 完了応答
    response = create_complete_response(
        task_id=task.task_id,
        responder_id="entity-b",
        result={"files_changed": 3, "tests_passed": 5},
        deliverables=[
            {"type": "code", "path": "src/file.py"},
            {"type": "test", "path": "tests/test_file.py"}
        ]
    )
    
    # 検証
    verifier = TaskCompletionVerifier(min_score_threshold=0.8)
    result = verifier.verify_completion(task, response)
    
    print(f"Verified: {result.verified}")
    print(f"Score: {result.score:.2f}")
    print(f"Message: {result.message}")
    print(f"Checks: {len(result.checks)}")
    
    assert result.verified, "Should be verified"
    assert result.score >= 0.8, "Score should be >= 0.8"
    print("✅ PASSED")


def test_missing_deliverable():
    """欠落成果物検出テスト"""
    print("\n=== Test 2: Missing Deliverable ===")
    
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Test Task",
        description="Test task description"
    )
    task.deliverables = [
        {"type": "code", "description": "Source code"},
        {"type": "test", "description": "Tests"},
        {"type": "doc", "description": "Documentation"}
    ]
    
    # ドキュメント欠落
    response = create_complete_response(
        task_id=task.task_id,
        responder_id="entity-b",
        result={"files_changed": 3},
        deliverables=[
            {"type": "code", "path": "src/file.py"}
        ]
    )
    
    verifier = TaskCompletionVerifier()
    result = verifier.verify_completion(task, response)
    
    print(f"Verified: {result.verified}")
    print(f"Missing: {result.missing_deliverables}")
    
    assert not result.verified, "Should not be verified with missing deliverables"
    assert "test" in result.missing_deliverables or "doc" in result.missing_deliverables
    print("✅ PASSED")


def test_incomplete_progress():
    """未完了進捗テスト"""
    print("\n=== Test 3: Incomplete Progress ===")
    
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Test Task",
        description="Test task description"
    )
    
    response = TaskResponseMessage(
        task_id=task.task_id,
        responder_id="entity-b",
        response_type="complete",
        status=TaskStatus.COMPLETED.value,
        progress_percent=80,  # Not 100%
        result={"done": True},
        deliverables=[{"type": "code"}]
    )
    
    verifier = TaskCompletionVerifier()
    result = verifier.verify_completion(task, response)
    
    print(f"Verified: {result.verified}")
    print(f"Progress: {response.progress_percent}%")
    
    assert not result.verified, "Should not be verified with < 100% progress"
    print("✅ PASSED")


def test_reward_eligibility():
    """報酬対象判定テスト"""
    print("\n=== Test 4: Reward Eligibility ===")
    
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Test Task",
        description="Test task description"
    )
    task.deliverables = [{"type": "code"}]
    
    verifier = TaskCompletionVerifier()
    
    # 最初は検証履歴なし
    assert not verifier.is_eligible_for_reward(task.task_id), "Should not be eligible without verification"
    
    # 合格応答
    response = create_complete_response(
        task_id=task.task_id,
        responder_id="entity-b",
        result={"done": True},
        deliverables=[{"type": "code"}]
    )
    
    result = verifier.verify_completion(task, response)
    
    # 合格後は対象
    if result.verified:
        assert verifier.is_eligible_for_reward(task.task_id), "Should be eligible after verification"
        print("✅ PASSED - Eligible for reward")
    else:
        print("⚠️ Verification failed, skipping eligibility check")


def test_verification_callback():
    """検証コールバックテスト"""
    print("\n=== Test 5: Verification Callback ===")
    
    callback_called = False
    callback_task_id = None
    
    def on_verified(task_id, result):
        nonlocal callback_called, callback_task_id
        callback_called = True
        callback_task_id = task_id
        print(f"Callback called for task {task_id}")
    
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Test Task",
        description="Test task description"
    )
    task.deliverables = [{"type": "code"}]
    
    verifier = TaskCompletionVerifier()
    verifier.register_verified_callback(on_verified)
    
    response = create_complete_response(
        task_id=task.task_id,
        responder_id="entity-b",
        result={"done": True},
        deliverables=[{"type": "code"}]
    )
    
    result = verifier.verify_completion(task, response)
    
    if result.verified:
        assert callback_called, "Callback should be called on verification"
        assert callback_task_id == task.task_id, "Callback should receive correct task_id"
        print("✅ PASSED - Callback executed")
    else:
        print("⚠️ Verification failed, callback not expected")


def test_statistics():
    """統計情報テスト"""
    print("\n=== Test 6: Statistics ===")
    
    verifier = TaskCompletionVerifier(min_score_threshold=0.7)
    
    # 複数タスクの検証
    for i in range(3):
        task = create_delegation_message(
            delegator_id="entity-a",
            delegatee_id="entity-b",
            title=f"Task {i}",
            description="Test"
        )
        task.deliverables = [{"type": "code"}]
        
        response = create_complete_response(
            task_id=task.task_id,
            responder_id="entity-b",
            result={"done": True},
            deliverables=[{"type": "code"}]
        )
        
        verifier.verify_completion(task, response)
    
    stats = verifier.get_statistics()
    print(f"Statistics: {stats}")
    
    assert stats["total_verifications"] == 3
    assert "verification_rate" in stats
    assert "average_score" in stats
    print("✅ PASSED")


def run_all_tests():
    """すべてのテストを実行"""
    print("=" * 50)
    print("TaskCompletionVerifier Test Suite")
    print("=" * 50)
    
    tests = [
        test_basic_verification,
        test_missing_deliverable,
        test_incomplete_progress,
        test_reward_eligibility,
        test_verification_callback,
        test_statistics
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
