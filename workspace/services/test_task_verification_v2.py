#!/usr/bin/env python3
"""
TaskCompletionVerifier テスト
タスク完了検証システムの動作確認
Protocol v0.3準拠
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_delegation import (
    TaskDelegationMessage,
    TaskResponseMessage,
    TaskTracker,
    TaskCompletionVerifier,
    VerificationResult,
    TaskStatus,
    TaskPriority,
    TaskType,
    create_delegation_message,
    create_complete_response,
    create_accept_response
)


def test_basic_verification():
    """基本検証テスト"""
    print("\n=== Test 1: Basic Verification ===")
    
    tracker = TaskTracker()
    verifier = TaskCompletionVerifier(tracker)
    verifier.set_quality_threshold(70.0)
    
    # タスク作成
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Test Task",
        description="Test task description",
        task_type=TaskType.CODE,
        priority=TaskPriority.NORMAL
    )
    task.deliverables = [
        {"type": "code", "description": "Source code"},
        {"type": "test", "description": "Tests"}
    ]
    
    tracker.register_task(task)
    
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
    tracker.add_response(response)
    
    # 検証
    result = verifier.verify_completion(task.task_id)
    
    print(f"Verified: {result.verified}")
    print(f"Score: {result.score:.2f}")
    print(f"Checks: {result.checks}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    
    assert isinstance(result, VerificationResult), "Should return VerificationResult"
    assert result.score >= 0.0 and result.score <= 100.0, "Score should be 0-100"
    print("✅ PASSED")


def test_approve_reject():
    """承認/拒否テスト"""
    print("\n=== Test 2: Approve/Reject ===")
    
    tracker = TaskTracker()
    verifier = TaskCompletionVerifier(tracker)
    
    # タスク作成
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Test Task",
        description="Test task description"
    )
    tracker.register_task(task)
    
    # 完了応答
    response = create_complete_response(
        task_id=task.task_id,
        responder_id="entity-b",
        result={"done": True},
        deliverables=[{"type": "code"}]
    )
    tracker.add_response(response)
    
    # 承認
    approve_result = verifier.approve_completion(task.task_id, "entity-a", "LGTM")
    print(f"Approve result: {approve_result}")
    
    assert "approved" in approve_result, "Should have approved field"
    assert approve_result["task_id"] == task.task_id, "Should have correct task_id"
    
    # 拒否（別タスクでテスト）
    task2 = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Test Task 2",
        description="Test task description"
    )
    tracker.register_task(task2)
    
    reject_result = verifier.reject_completion(
        task2.task_id,
        "entity-a",
        "Needs improvement",
        required_fixes=["Add more tests"]
    )
    print(f"Reject result: {reject_result}")
    
    assert "approved" in reject_result, "Should have approved field"
    assert not reject_result["approved"], "Should not be approved"
    assert "required_fixes" in reject_result, "Should have required_fixes"
    
    print("✅ PASSED")


def test_verification_with_tracker():
    """TaskTracker連携テスト"""
    print("\n=== Test 3: Verification with TaskTracker ===")
    
    tracker = TaskTracker()
    verifier = TaskCompletionVerifier(tracker)
    
    # タスク作成と登録
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Integration Test Task",
        description="Test with tracker integration"
    )
    tracker.register_task(task)
    
    # 受諾応答
    accept_response = create_accept_response(task.task_id, "entity-b")
    tracker.add_response(accept_response)
    
    # 進捗応答
    progress_response = TaskResponseMessage(
        task_id=task.task_id,
        responder_id="entity-b",
        response_type="progress",
        status=TaskStatus.IN_PROGRESS.value,
        progress_percent=50,
        message="Halfway done"
    )
    tracker.add_response(progress_response)
    
    # 完了応答
    complete_response = create_complete_response(
        task_id=task.task_id,
        responder_id="entity-b",
        result={"files_changed": 2, "tests_passed": 3},
        deliverables=[{"type": "code"}, {"type": "test"}]
    )
    tracker.add_response(complete_response)
    
    # 検証
    result = verifier.verify_completion(task.task_id)
    
    print(f"Task status: {tracker.get_task(task.task_id).status}")
    print(f"Verification verified: {result.verified}")
    print(f"Verification score: {result.score}")
    
    # 統計確認
    stats = verifier.get_statistics()
    print(f"Verifier stats: {stats}")
    
    assert stats["total_completed"] >= 0, "Should have total_completed"
    assert "verification_rate" in stats, "Should have verification_rate"
    
    print("✅ PASSED")


def test_incomplete_progress():
    """未完了進捗テスト"""
    print("\n=== Test 4: Incomplete Progress ===")
    
    tracker = TaskTracker()
    verifier = TaskCompletionVerifier(tracker)
    
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Test Task",
        description="Test task description"
    )
    tracker.register_task(task)
    
    # 未完了応答 (progress_percent < 100)
    response = TaskResponseMessage(
        task_id=task.task_id,
        responder_id="entity-b",
        response_type="complete",
        status=TaskStatus.COMPLETED.value,
        progress_percent=80,  # Not 100%
        result={"done": True},
        deliverables=[{"type": "code"}]
    )
    tracker.add_response(response)
    
    result = verifier.verify_completion(task.task_id)
    
    print(f"Verified: {result.verified}")
    print(f"Score: {result.score}")
    print(f"Warnings: {result.warnings}")
    
    # 進捗率が100%でないため警告が出るはず
    assert any("progress" in w.lower() for w in result.warnings), "Should have progress warning"
    
    print("✅ PASSED")


def test_statistics():
    """統計情報テスト"""
    print("\n=== Test 5: Statistics ===")
    
    tracker = TaskTracker()
    verifier = TaskCompletionVerifier(tracker)
    
    # 複数タスクの検証
    for i in range(3):
        task = create_delegation_message(
            delegator_id="entity-a",
            delegatee_id="entity-b",
            title=f"Task {i}",
            description="Test"
        )
        tracker.register_task(task)
        
        response = create_complete_response(
            task_id=task.task_id,
            responder_id="entity-b",
            result={"done": True},
            deliverables=[{"type": "code"}]
        )
        tracker.add_response(response)
        
        # 検証実行
        verifier.verify_completion(task.task_id)
    
    stats = verifier.get_statistics()
    print(f"Statistics: {stats}")
    
    assert "total_verified" in stats, "Should have total_verified"
    assert "total_completed" in stats, "Should have total_completed"
    assert "verification_rate" in stats, "Should have verification_rate"
    assert "average_score" in stats, "Should have average_score"
    assert stats["total_completed"] == 3, "Should have 3 completed tasks"
    
    print("✅ PASSED")


def test_threshold_adjustment():
    """閾値調整テスト"""
    print("\n=== Test 6: Quality Threshold Adjustment ===")
    
    tracker = TaskTracker()
    verifier = TaskCompletionVerifier(tracker)
    
    # 低品質スコアのタスク作成
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Low Quality Task",
        description="Task with minimal deliverables"
    )
    tracker.register_task(task)
    
    # 最小限の応答
    response = TaskResponseMessage(
        task_id=task.task_id,
        responder_id="entity-b",
        response_type="complete",
        status=TaskStatus.COMPLETED.value,
        progress_percent=100,
        message="Done",  # 短いメッセージ
        result={},
        deliverables=[]
    )
    tracker.add_response(response)
    
    # 高い閾値で検証
    verifier.set_quality_threshold(90.0)
    result_high = verifier.verify_completion(task.task_id)
    print(f"High threshold (90): verified={result_high.verified}, score={result_high.score:.2f}")
    
    # 低い閾値で検証
    verifier.set_quality_threshold(50.0)
    result_low = verifier.verify_completion(task.task_id)
    print(f"Low threshold (50): verified={result_low.verified}, score={result_low.score:.2f}")
    
    # スコアは同じだが、検証結果は閾値によって変わる
    assert result_high.score == result_low.score, "Score should be same"
    
    print("✅ PASSED")


def test_custom_verifier():
    """カスタム検証関数テスト"""
    print("\n=== Test 7: Custom Verifier ===")
    
    tracker = TaskTracker()
    verifier = TaskCompletionVerifier(tracker)
    
    custom_called = False
    
    def custom_verifier(response: TaskResponseMessage) -> VerificationResult:
        nonlocal custom_called
        custom_called = True
        return VerificationResult(
            verified=True,
            score=95.0,
            checks={"custom_check": True},
            errors=[],
            warnings=["Custom warning"]
        )
    
    # カスタム検証関数を登録
    verifier.register_verifier("custom_task", custom_verifier)
    
    # カスタムタイプのタスク作成
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Custom Task",
        description="Task with custom verifier",
        task_type=TaskType.CUSTOM
    )
    task.task_type = "custom_task"  # カスタムタイプに変更
    tracker.register_task(task)
    
    response = create_complete_response(
        task_id=task.task_id,
        responder_id="entity-b",
        result={"done": True},
        deliverables=[{"type": "custom"}]
    )
    tracker.add_response(response)
    
    # 検証実行
    result = verifier.verify_completion(task.task_id)
    
    print(f"Custom verifier called: {custom_called}")
    print(f"Result: {result.to_dict()}")
    
    assert custom_called, "Custom verifier should be called"
    assert result.score == 95.0, "Should use custom score"
    assert "custom_check" in result.checks, "Should have custom check"
    
    print("✅ PASSED")


def run_all_tests():
    """すべてのテストを実行"""
    print("=" * 60)
    print("TaskCompletionVerifier Test Suite")
    print("Protocol v0.3 Compliant")
    print("=" * 60)
    
    tests = [
        test_basic_verification,
        test_approve_reject,
        test_verification_with_tracker,
        test_incomplete_progress,
        test_statistics,
        test_threshold_adjustment,
        test_custom_verifier
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
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
