#!/usr/bin/env python3
"""
TaskCompletionVerifier テストスイート

services/task_verification.py の TaskCompletionVerifier クラスをテストする
"""

import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_verification import (
    TaskCompletionVerifier,
    VerificationRuleEngine,
    VerificationRule,
    VerificationResult,
    TaskVerificationReport,
    VerificationStatus,
    VerificationRuleType
)


class TestTaskCompletionVerifier:
    """TaskCompletionVerifier テストクラス"""
    
    def setup_test_files(self, temp_dir):
        """テスト用ファイルを作成"""
        # 有効なPythonファイル
        valid_py = os.path.join(temp_dir, "valid.py")
        with open(valid_py, 'w') as f:
            f.write('"""Valid module with docstring."""\n\n')
            f.write('def hello():\n')
            f.write('    """Say hello."""\n')
            f.write('    return "Hello"\n')
        
        # ドキュメントなしのPythonファイル
        no_doc_py = os.path.join(temp_dir, "no_doc.py")
        with open(no_doc_py, 'w') as f:
            f.write('def hello():\n')
            f.write('    return "Hello"\n')
        
        # 存在しないファイルパス
        nonexistent = os.path.join(temp_dir, "nonexistent.py")
        
        return valid_py, no_doc_py, nonexistent
    
    def test_init(self):
        """初期化テスト"""
        print("\n=== Test: Initialization ===")
        
        verifier = TaskCompletionVerifier(verifier_id="test_verifier")
        
        assert verifier.verifier_id == "test_verifier"
        assert isinstance(verifier.rule_engine, VerificationRuleEngine)
        assert verifier._default_rules_registered == False
        
        print("✅ PASSED: Initialization")
    
    def test_register_default_rules(self):
        """デフォルトルール登録テスト"""
        print("\n=== Test: Register Default Rules ===")
        
        verifier = TaskCompletionVerifier()
        verifier.register_default_rules()
        
        assert verifier._default_rules_registered == True
        
        # ルールが登録されているか確認
        assert verifier.rule_engine.get_rule("check_main_file") is not None
        assert verifier.rule_engine.get_rule("check_code_quality") is not None
        assert verifier.rule_engine.get_rule("check_documentation") is not None
        
        # 2回目の呼び出しは何もしない
        verifier.register_default_rules()
        assert verifier._default_rules_registered == True
        
        print("✅ PASSED: Default Rules Registration")
    
    def test_verify_task_completion_with_existing_file(self):
        """既存ファイルの検証テスト"""
        print("\n=== Test: Verify Existing File ===")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_py, _, _ = self.setup_test_files(temp_dir)
            
            verifier = TaskCompletionVerifier()
            
            deliverables = [
                {"path": valid_py, "type": "code"}
            ]
            
            report = verifier.verify_task_completion(
                task_id="test-task-1",
                deliverables=deliverables
            )
            
            assert isinstance(report, TaskVerificationReport)
            assert report.task_id == "test-task-1"
            assert report.verifier_id == "verifier"  # default
            assert len(report.results) > 0
            assert report.overall_score > 0
            assert report.completed_at is not None
            
            print(f"   Status: {report.overall_status}")
            print(f"   Score: {report.overall_score:.2f}")
            print(f"   Checks: {len(report.results)}")
            print("✅ PASSED: Existing File Verification")
    
    def test_verify_task_completion_with_nonexistent_file(self):
        """存在しないファイルの検証テスト"""
        print("\n=== Test: Verify Nonexistent File ===")
        
        verifier = TaskCompletionVerifier()
        
        deliverables = [
            {"path": "/nonexistent/path/file.py", "type": "code"}
        ]
        
        report = verifier.verify_task_completion(
            task_id="test-task-2",
            deliverables=deliverables
        )
        
        # 存在しないファイルは失敗するはず
        assert report.overall_status == VerificationStatus.FAILED.value
        assert any(
            r.get("status") == VerificationStatus.FAILED.value 
            for r in report.results
        )
        
        print(f"   Status: {report.overall_status}")
        print(f"   Score: {report.overall_score:.2f}")
        print("✅ PASSED: Nonexistent File Detection")
    
    def test_verify_multiple_deliverables(self):
        """複数成果物の検証テスト"""
        print("\n=== Test: Multiple Deliverables ===")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_py, no_doc_py, _ = self.setup_test_files(temp_dir)
            
            verifier = TaskCompletionVerifier()
            
            deliverables = [
                {"path": valid_py, "type": "code"},
                {"path": no_doc_py, "type": "code"}
            ]
            
            report = verifier.verify_task_completion(
                task_id="test-task-3",
                deliverables=deliverables
            )
            
            # 複数の検証結果がある
            assert len(report.results) >= 2
            
            # サマリーに正しい数が入っている
            assert report.summary["total_checks"] >= 2
            
            print(f"   Total Checks: {report.summary['total_checks']}")
            print(f"   Passed: {report.summary.get('passed', 0)}")
            print(f"   Failed: {report.summary.get('failed', 0)}")
            print("✅ PASSED: Multiple Deliverables")
    
    def test_empty_deliverables(self):
        """空の成果物リストテスト"""
        print("\n=== Test: Empty Deliverables ===")
        
        verifier = TaskCompletionVerifier()
        
        report = verifier.verify_task_completion(
            task_id="test-task-4",
            deliverables=[]
        )
        
        # 空の場合はスコア0
        assert report.overall_score == 0
        assert report.summary["total_checks"] == 0
        
        print("✅ PASSED: Empty Deliverables")
    
    def test_get_report(self):
        """レポート取得テスト"""
        print("\n=== Test: Get Report ===")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_py, _, _ = self.setup_test_files(temp_dir)
            
            verifier = TaskCompletionVerifier()
            
            deliverables = [{"path": valid_py, "type": "code"}]
            report = verifier.verify_task_completion(
                task_id="test-task-5",
                deliverables=deliverables
            )
            
            # レポートを取得
            retrieved = verifier.get_report(report.report_id)
            assert retrieved is not None
            assert retrieved.report_id == report.report_id
            assert retrieved.task_id == "test-task-5"
            
            # 存在しないID
            not_found = verifier.get_report("nonexistent-id")
            assert not_found is None
            
            print("✅ PASSED: Report Retrieval")
    
    def test_get_reports_by_task(self):
        """タスクIDでのレポート検索テスト"""
        print("\n=== Test: Get Reports by Task ID ===")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_py, _, _ = self.setup_test_files(temp_dir)
            
            verifier = TaskCompletionVerifier()
            
            deliverables = [{"path": valid_py, "type": "code"}]
            
            # 同じタスクIDで2回検証
            report1 = verifier.verify_task_completion(
                task_id="shared-task-id",
                deliverables=deliverables
            )
            report2 = verifier.verify_task_completion(
                task_id="shared-task-id",
                deliverables=deliverables
            )
            
            # タスクIDで検索
            reports = verifier.get_reports_by_task("shared-task-id")
            assert len(reports) == 2
            
            # 存在しないタスクID
            empty = verifier.get_reports_by_task("nonexistent-task")
            assert len(empty) == 0
            
            print(f"   Found {len(reports)} reports")
            print("✅ PASSED: Reports by Task ID")
    
    def test_custom_context(self):
        """カスタムコンテキストテスト"""
        print("\n=== Test: Custom Context ===")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_py, _, _ = self.setup_test_files(temp_dir)
            
            verifier = TaskCompletionVerifier()
            
            custom_context = {
                "author": "test_author",
                "priority": "high",
                "tags": ["test", "verification"]
            }
            
            deliverables = [{"path": valid_py, "type": "code"}]
            report = verifier.verify_task_completion(
                task_id="test-task-6",
                deliverables=deliverables,
                custom_context=custom_context
            )
            
            # 検証が正常に完了すること
            assert report is not None
            assert report.task_id == "test-task-6"
            
            print("✅ PASSED: Custom Context")
    
    def test_report_json_serialization(self):
        """レポートJSONシリアライゼーションテスト"""
        print("\n=== Test: Report JSON Serialization ===")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_py, _, _ = self.setup_test_files(temp_dir)
            
            verifier = TaskCompletionVerifier()
            
            deliverables = [{"path": valid_py, "type": "code"}]
            report = verifier.verify_task_completion(
                task_id="test-task-7",
                deliverables=deliverables
            )
            
            # JSON変換
            json_str = report.to_json()
            assert isinstance(json_str, str)
            assert "task_id" in json_str
            assert "overall_status" in json_str
            assert "results" in json_str
            
            print(f"   JSON length: {len(json_str)} chars")
            print("✅ PASSED: JSON Serialization")
    
    def test_quality_score_calculation(self):
        """品質スコア計算テスト"""
        print("\n=== Test: Quality Score Calculation ===")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # 高品質ファイル
            high_quality = os.path.join(temp_dir, "high_quality.py")
            with open(high_quality, 'w') as f:
                f.write('"""Module docstring."""\n\n')
                f.write('def func1():\n')
                f.write('    """Docstring 1."""\n')
                f.write('    pass\n\n')
                f.write('def func2():\n')
                f.write('    """Docstring 2."""\n')
                f.write('    pass\n')
            
            # 低品質ファイル
            low_quality = os.path.join(temp_dir, "low_quality.py")
            with open(low_quality, 'w') as f:
                f.write('def f():\n')
                f.write('    x=1+2\n')  # スペースなし、短い関数名
            
            verifier = TaskCompletionVerifier()
            
            # 高品質ファイルを検証
            report_high = verifier.verify_task_completion(
                task_id="quality-test-1",
                deliverables=[{"path": high_quality, "type": "code"}]
            )
            
            # 低品質ファイルを検証
            report_low = verifier.verify_task_completion(
                task_id="quality-test-2",
                deliverables=[{"path": low_quality, "type": "code"}]
            )
            
            print(f"   High Quality Score: {report_high.overall_score:.2f}")
            print(f"   Low Quality Score: {report_low.overall_score:.2f}")
            
            # 高品質の方がスコアが高いはず
            assert report_high.overall_score >= report_low.overall_score
            
            print("✅ PASSED: Quality Score Calculation")


def run_all_tests():
    """すべてのテストを実行"""
    print("=" * 60)
    print("TaskCompletionVerifier Test Suite")
    print("=" * 60)
    
    test_class = TestTaskCompletionVerifier()
    
    tests = [
        test_class.test_init,
        test_class.test_register_default_rules,
        test_class.test_verify_task_completion_with_existing_file,
        test_class.test_verify_task_completion_with_nonexistent_file,
        test_class.test_verify_multiple_deliverables,
        test_class.test_empty_deliverables,
        test_class.test_get_report,
        test_class.test_get_reports_by_task,
        test_class.test_custom_context,
        test_class.test_report_json_serialization,
        test_class.test_quality_score_calculation,
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
            print(f"❌ ERROR: {type(e).__name__}: {e}")
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
