#!/usr/bin/env python3
"""
統合テスト実行スクリプト
Phase 1-4のテストを順次実行・並列実行対応

Usage:
    python run_integration_tests.py [phase] [options]
    
    phase:
        phase1 - 基本機能テスト (SessionManager, Crypto)
        phase2 - 暗号化統合テスト (E2E Encryption)
        phase3 - PeerService統合テスト
        phase4 - End-to-Endテスト
        all    - 全フェーズ実行
    
    options:
        --parallel N    - N並列で実行 (pytest-xdist)
        --coverage      - カバレッジ測定を有効化
        --json          - JSON形式でレポート出力
        --html          - HTMLレポート生成
"""

import sys
import asyncio
import importlib
import traceback
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# テストカテゴリ定義
TEST_PHASES = {
    "phase1": {
        "name": "基本機能テスト",
        "description": "SessionManager, Crypto単体テスト",
        "tests": [
            "services.test_session_manager",
            "services.test_crypto_integration",
            "services.test_ed25519_x25519_conversion",
            "services.test_signature",
            "services.test_wallet",
        ]
    },
    "phase2": {
        "name": "暗号化統合テスト",
        "description": "E2E暗号化、鍵交換テスト",
        "tests": [
            "services.test_e2e_crypto",
            "services.test_e2e_crypto_integration",
            "services.test_handshake_protocol",
            "services.test_handshake_v11",
            "services.test_security",
        ]
    },
    "phase3": {
        "name": "PeerService統合テスト",
        "description": "ハンドシェイク、メッセージ送受信",
        "tests": [
            "services.test_peer_service",
            "services.test_peer_service_integration",
            "services.test_peer_discovery",
            "services.test_connection_pool",
            "services.test_rate_limiter",
            "services.test_chunked_transfer",
        ]
    },
    "phase4": {
        "name": "End-to-Endテスト",
        "description": "実サービス間通信テスト",
        "tests": [
            "services.test_integration",
            "services.test_integration_scenarios",
            "services.test_v1.1_integration",
        ]
    }
}


class TestRunner:
    """テスト実行エンジン - 並列実行・レポート生成対応"""
    
    def __init__(self, parallel: int = 1, coverage: bool = False, 
                 json_output: bool = False, html_report: bool = False):
        self.results = {}
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.parallel = parallel
        self.coverage = coverage
        self.json_output = json_output
        self.html_report = html_report
        self.detailed_results = []
        self.start_time = None
        self.end_time = None
        
    def run_test_module(self, module_name: str) -> dict:
        """単一テストモジュールを実行"""
        import inspect
        result = {
            "module": module_name,
            "status": "unknown",
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": []
        }
        
        try:
            # モジュールをインポート
            module = importlib.import_module(module_name)
            
            # モジュールにmain()関数があれば、それを優先して実行
            if hasattr(module, 'main') and callable(getattr(module, 'main')):
                try:
                    main_func = getattr(module, 'main')
                    if asyncio.iscoroutinefunction(main_func):
                        asyncio.run(main_func())
                    else:
                        main_func()
                    result["tests_passed"] += 1
                    result["tests_run"] += 1
                    result["status"] = "passed"
                    return result
                except Exception as e:
                    result["tests_failed"] += 1
                    result["errors"].append(f"main(): {str(e)}")
                    result["status"] = "failed"
                    return result
            
            # テスト関数を検索（引数なしの関数のみ）
            test_funcs = []
            for name in dir(module):
                if name.startswith("test_"):
                    func = getattr(module, name)
                    if callable(func):
                        sig = inspect.signature(func)
                        params = list(sig.parameters.values())
                        # 引数がない、または全てデフォルト値を持つ関数のみ
                        if len(params) == 0 or all(p.default != inspect.Parameter.empty for p in params):
                            test_funcs.append(func)
            
            # 非同期テスト関数の実行
            for func in test_funcs:
                try:
                    if asyncio.iscoroutinefunction(func):
                        asyncio.run(func())
                    else:
                        func()
                    result["tests_passed"] += 1
                except Exception as e:
                    result["tests_failed"] += 1
                    result["errors"].append(f"{func.__name__}: {str(e)}")
                    
            result["tests_run"] = len(test_funcs)
            result["status"] = "passed" if result["tests_failed"] == 0 else "failed"
            
        except ImportError as e:
            result["status"] = "error"
            result["errors"].append(f"Import error: {str(e)}")
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(f"Unexpected error: {str(e)}")
            
        return result
    
    def run_phase(self, phase_id: str) -> dict:
        """フェーズ全体を実行"""
        phase = TEST_PHASES.get(phase_id)
        if not phase:
            print(f"Unknown phase: {phase_id}")
            return {}
            
        print(f"\n{'='*60}")
        print(f"Phase: {phase['name']}")
        print(f"Description: {phase['description']}")
        print(f"{'='*60}\n")
        
        phase_results = {
            "phase_id": phase_id,
            "name": phase["name"],
            "modules": []
        }
        
        for module_name in phase["tests"]:
            print(f"  Running: {module_name}...", end=" ")
            result = self.run_test_module(module_name)
            phase_results["modules"].append(result)
            
            if result["status"] == "passed":
                print(f"✓ ({result['tests_passed']}/{result['tests_run']})")
                self.passed += result["tests_passed"]
            else:
                print(f"✗ ({result['tests_failed']} failed)")
                self.failed += result["tests_failed"]
                self.errors.extend(result["errors"])
                
        return phase_results
    
    def generate_report(self) -> str:
        """テスト結果レポートを生成"""
        report = []
        report.append("\n" + "="*60)
        report.append("INTEGRATION TEST REPORT")
        report.append("="*60)
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append(f"Total Passed: {self.passed}")
        report.append(f"Total Failed: {self.failed}")
        report.append(f"Success Rate: {self.passed/(self.passed+self.failed)*100:.1f}%" if (self.passed+self.failed) > 0 else "N/A")
        
        if self.errors:
            report.append("\n--- Errors ---")
            for error in self.errors[:10]:  # 最初の10件のみ
                report.append(f"  - {error}")
            if len(self.errors) > 10:
                report.append(f"  ... and {len(self.errors) - 10} more errors")
                
        report.append("="*60)
        return "\n".join(report)
    
    def save_report(self, filename: str = None):
        """レポートをファイルに保存"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_report_{timestamp}.md"
            
        report = self.generate_report()
        
        # docs/に保存
        report_path = Path("docs") / filename
        report_path.write_text(report)
        print(f"\nReport saved to: {report_path}")
    
    def run_with_pytest(self, phase_id: str) -> dict:
        """pytestを使用して並列実行"""
        phase = TEST_PHASES.get(phase_id)
        if not phase:
            return {"status": "error", "error": f"Unknown phase: {phase_id}"}
        
        self.start_time = datetime.now()
        
        # pytestコマンド構築
        cmd = ["python", "-m", "pytest"]
        
        # テストモジュール追加
        for module in phase["tests"]:
            module_path = module.replace(".", "/") + ".py"
            cmd.append(module_path)
        
        # 並列実行オプション
        if self.parallel > 1:
            cmd.extend(["-n", str(self.parallel), "--dist", "loadgroup"])
        
        # カバレッジオプション
        if self.coverage:
            cmd.extend(["--cov=services", "--cov-report=term-missing"])
            if self.html_report:
                cmd.append("--cov-report=html")
        
        # 出力形式
        cmd.extend(["-v", "--tb=short"])
        
        if self.json_output:
            cmd.append("--json-report")
        
        print(f"\n{'='*60}")
        print(f"Running {phase['name']} with pytest")
        print(f"Command: {' '.join(cmd)}")
        print(f"{'='*60}\n")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=Path(__file__).parent / "services",
                capture_output=True,
                text=True,
                timeout=300  # 5分タイムアウト
            )
            
            self.end_time = datetime.now()
            
            # 結果解析
            output = result.stdout + result.stderr
            
            # passed/failedカウント
            passed = output.count("PASSED")
            failed = output.count("FAILED")
            error = output.count("ERROR")
            
            self.passed += passed
            self.failed += failed + error
            
            phase_result = {
                "phase_id": phase_id,
                "name": phase["name"],
                "status": "passed" if result.returncode == 0 else "failed",
                "passed": passed,
                "failed": failed,
                "errors": error,
                "returncode": result.returncode,
                "output": output[-2000:] if len(output) > 2000 else output,  # 最後の2000文字
                "duration": str(self.end_time - self.start_time)
            }
            
            self.detailed_results.append(phase_result)
            
            print(output)
            return phase_result
            
        except subprocess.TimeoutExpired:
            self.errors.append(f"Phase {phase_id} timed out after 5 minutes")
            return {"status": "timeout", "phase_id": phase_id}
        except Exception as e:
            self.errors.append(f"Phase {phase_id} error: {str(e)}")
            return {"status": "error", "phase_id": phase_id, "error": str(e)}
    
    def generate_json_report(self) -> str:
        """JSON形式のレポートを生成"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_passed": self.passed,
                "total_failed": self.failed,
                "success_rate": f"{self.passed/(self.passed+self.failed)*100:.1f}%" if (self.passed+self.failed) > 0 else "N/A"
            },
            "phases": self.detailed_results,
            "errors": self.errors
        }
        return json.dumps(report, indent=2, ensure_ascii=False)
    
    def save_json_report(self, filename: str = None):
        """JSONレポートを保存"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_report_{timestamp}.json"
        
        report_path = Path("docs") / filename
        report_path.write_text(self.generate_json_report())
        print(f"JSON Report saved to: {report_path}")


def main():
    """メインエントリポイント - 拡張版"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="AI Collaboration Platform - Integration Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_integration_tests.py phase1
  python run_integration_tests.py all --parallel 4 --coverage
  python run_integration_tests.py phase2 --json --html
        """
    )
    
    parser.add_argument(
        "phase",
        choices=["phase1", "phase2", "phase3", "phase4", "all"],
        help="Test phase to run"
    )
    
    parser.add_argument(
        "--parallel", "-p",
        type=int,
        default=1,
        help="Number of parallel workers (requires pytest-xdist)"
    )
    
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="Enable coverage measurement"
    )
    
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output JSON report"
    )
    
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML coverage report"
    )
    
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use legacy test runner (no pytest)"
    )
    
    args = parser.parse_args()
    
    # TestRunner初期化
    runner = TestRunner(
        parallel=args.parallel,
        coverage=args.coverage,
        json_output=args.json,
        html_report=args.html
    )
    
    # 実行フェーズ決定
    if args.phase == "all":
        phases_to_run = list(TEST_PHASES.keys())
    else:
        phases_to_run = [args.phase]
    
    # テスト実行
    for phase_id in phases_to_run:
        if phase_id not in TEST_PHASES:
            print(f"Unknown phase: {phase_id}")
            continue
            
        if args.legacy:
            # レガシーモード
            runner.run_phase(phase_id)
        else:
            # pytestモード（並列実行対応）
            runner.run_with_pytest(phase_id)
    
    # レポート出力
    print("\n" + runner.generate_report())
    runner.save_report()
    
    if args.json:
        runner.save_json_report()
    
    # 終了コード
    sys.exit(0 if runner.failed == 0 else 1)


if __name__ == "__main__":
    main()
