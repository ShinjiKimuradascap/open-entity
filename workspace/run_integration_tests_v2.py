#!/usr/bin/env python3
"""
統合テスト実行スクリプト v2.0
Phase 1-4のテストを順次実行

Usage:
    python run_integration_tests_v2.py [phase] [options]
    
    phase:
        phase1 - 基本機能テスト (SessionManager, Crypto)
        phase2 - 暗号化統合テスト (E2E Encryption)
        phase3 - PeerService統合テスト
        phase4 - End-to-Endテスト
        all    - 全フェーズ実行
        
    options:
        --parallel       - 並列実行
        --coverage       - カバレッジ測定
        --json           - JSON形式でレポート出力
        --timeout=N      - タイムアウト設定（秒）

Examples:
    python run_integration_tests_v2.py all --parallel --coverage
    python run_integration_tests_v2.py phase1 --json
"""

import sys
import asyncio
import importlib
import traceback
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict

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
        ],
        "timeout": 60
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
        ],
        "timeout": 120
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
        ],
        "timeout": 180
    },
    "phase4": {
        "name": "End-to-Endテスト",
        "description": "実サービス間通信テスト",
        "tests": [
            "services.test_integration",
            "services.test_integration_scenarios",
            "services.test_v1.1_integration",
        ],
        "timeout": 300
    }
}


@dataclass
class TestResult:
    """テスト結果データクラス"""
    module: str
    status: str  # "passed", "failed", "error", "timeout"
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    duration_ms: float = 0.0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PhaseResult:
    """フェーズ結果データクラス"""
    phase_id: str
    name: str
    status: str
    modules: List[TestResult]
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "modules": [m.to_dict() for m in self.modules]
        }


class TestRunner:
    """テスト実行エンジン v2.0"""
    
    def __init__(self, parallel: bool = False, timeout: int = 300):
        self.parallel = parallel
        self.timeout = timeout
        self.results: List[PhaseResult] = []
        self.total_passed = 0
        self.total_failed = 0
        self.total_errors = 0
        self.start_time = None
        self.end_time = None
        
    def run_test_module(self, module_name: str) -> TestResult:
        """単一テストモジュールを実行"""
        import inspect
        start_time = time.time()
        result = TestResult(module=module_name, status="unknown")
        
        try:
            # モジュールをインポート
            module = importlib.import_module(module_name)
            
            # モジュールにmain()関数があれば、それを優先して実行
            if hasattr(module, 'main') and callable(getattr(module, 'main')):
                try:
                    main_func = getattr(module, 'main')
                    if asyncio.iscoroutinefunction(main_func):
                        asyncio.run(asyncio.wait_for(main_func(), timeout=self.timeout))
                    else:
                        main_func()
                    result.tests_passed += 1
                    result.tests_run += 1
                    result.status = "passed"
                    return result
                except asyncio.TimeoutError:
                    result.tests_failed += 1
                    result.errors.append(f"main(): Timeout after {self.timeout}s")
                    result.status = "timeout"
                    return result
                except Exception as e:
                    result.tests_failed += 1
                    result.errors.append(f"main(): {str(e)}")
                    result.status = "failed"
                    return result
            
            # テスト関数を検索（引数なしの関数のみ）
            test_funcs = []
            for name in dir(module):
                if name.startswith("test_"):
                    func = getattr(module, name)
                    if callable(func):
                        sig = inspect.signature(func)
                        params = list(sig.parameters.values())
                        if len(params) == 0 or all(p.default != inspect.Parameter.empty for p in params):
                            test_funcs.append(func)
            
            # 非同期テスト関数の実行
            for func in test_funcs:
                try:
                    if asyncio.iscoroutinefunction(func):
                        asyncio.run(asyncio.wait_for(func(), timeout=self.timeout))
                    else:
                        func()
                    result.tests_passed += 1
                except asyncio.TimeoutError:
                    result.tests_failed += 1
                    result.errors.append(f"{func.__name__}: Timeout after {self.timeout}s")
                except Exception as e:
                    result.tests_failed += 1
                    result.errors.append(f"{func.__name__}: {str(e)}")
                    
            result.tests_run = len(test_funcs)
            result.status = "passed" if result.tests_failed == 0 else "failed"
            
        except ImportError as e:
            result.status = "error"
            result.errors.append(f"Import error: {str(e)}")
        except Exception as e:
            result.status = "error"
            result.errors.append(f"Unexpected error: {str(e)}")
        finally:
            result.duration_ms = (time.time() - start_time) * 1000
            
        return result
    
    def run_phase_parallel(self, phase_id: str) -> PhaseResult:
        """フェーズを並列実行"""
        phase = TEST_PHASES.get(phase_id)
        if not phase:
            return PhaseResult(phase_id=phase_id, name="Unknown", status="error", modules=[])
        
        print(f"\n{'='*60}")
        print(f"Phase: {phase['name']} (Parallel)")
        print(f"Description: {phase['description']}")
        print(f"{'='*60}\n")
        
        phase_start = time.time()
        modules = []
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_module = {
                executor.submit(self.run_test_module, module_name): module_name
                for module_name in phase['tests']
            }
            
            for future in as_completed(future_to_module):
                module_name = future_to_module[future]
                try:
                    result = future.result()
                    modules.append(result)
                    
                    if result.status == "passed":
                        print(f"  ✓ {module_name} ({result.tests_passed}/{result.tests_run}) [{result.duration_ms:.0f}ms]")
                        self.total_passed += result.tests_passed
                    else:
                        print(f"  ✗ {module_name} ({result.tests_failed} failed) [{result.duration_ms:.0f}ms]")
                        self.total_failed += result.tests_failed
                        self.total_errors += len(result.errors)
                        
                except Exception as e:
                    print(f"  ✗ {module_name} (Execution error: {e})")
                    error_result = TestResult(
                        module=module_name,
                        status="error",
                        errors=[str(e)]
                    )
                    modules.append(error_result)
        
        phase_duration = (time.time() - phase_start) * 1000
        status = "passed" if all(m.status == "passed" for m in modules) else "failed"
        
        return PhaseResult(
            phase_id=phase_id,
            name=phase['name'],
            status=status,
            modules=modules,
            duration_ms=phase_duration
        )
    
    def run_phase_sequential(self, phase_id: str) -> PhaseResult:
        """フェーズを逐次実行"""
        phase = TEST_PHASES.get(phase_id)
        if not phase:
            return PhaseResult(phase_id=phase_id, name="Unknown", status="error", modules=[])
            
        print(f"\n{'='*60}")
        print(f"Phase: {phase['name']}")
        print(f"Description: {phase['description']}")
        print(f"{'='*60}\n")
        
        phase_start = time.time()
        modules = []
        
        for module_name in phase['tests']:
            print(f"  Running: {module_name}...", end=" ")
            result = self.run_test_module(module_name)
            modules.append(result)
            
            if result.status == "passed":
                print(f"✓ ({result.tests_passed}/{result.tests_run}) [{result.duration_ms:.0f}ms]")
                self.total_passed += result.tests_passed
            else:
                print(f"✗ ({result.tests_failed} failed) [{result.duration_ms:.0f}ms]")
                self.total_failed += result.tests_failed
                self.total_errors += len(result.errors)
        
        phase_duration = (time.time() - phase_start) * 1000
        status = "passed" if all(m.status == "passed" for m in modules) else "failed"
        
        return PhaseResult(
            phase_id=phase_id,
            name=phase['name'],
            status=status,
            modules=modules,
            duration_ms=phase_duration
        )
    
    def run_phase(self, phase_id: str) -> PhaseResult:
        """フェーズ全体を実行"""
        if self.parallel:
            return self.run_phase_parallel(phase_id)
        else:
            return self.run_phase_sequential(phase_id)
    
    def generate_markdown_report(self) -> str:
        """Markdown形式のレポートを生成"""
        report = []
        report.append("# Integration Test Report\n")
        report.append(f"**Timestamp:** {datetime.now().isoformat()}\n")
        report.append(f"**Duration:** {(self.end_time - self.start_time)*1000:.0f}ms\n")
        report.append(f"**Parallel:** {'Yes' if self.parallel else 'No'}\n")
        report.append(f"**Timeout:** {self.timeout}s\n\n")
        
        # Summary
        report.append("## Summary\n\n")
        report.append(f"| Metric | Value |\n")
        report.append(f"|--------|-------|\n")
        report.append(f"| Total Passed | {self.total_passed} |\n")
        report.append(f"| Total Failed | {self.total_failed} |\n")
        report.append(f"| Total Errors | {self.total_errors} |\n")
        total = self.total_passed + self.total_failed
        rate = (self.total_passed / total * 100) if total > 0 else 0
        report.append(f"| Success Rate | {rate:.1f}% |\n\n")
        
        # Phase Details
        report.append("## Phase Details\n\n")
        for phase in self.results:
            status_icon = "✅" if phase.status == "passed" else "❌"
            report.append(f"### {status_icon} {phase.name}\n\n")
            report.append(f"- **Status:** {phase.status}\n")
            report.append(f"- **Duration:** {phase.duration_ms:.0f}ms\n\n")
            report.append("| Module | Status | Tests | Duration |\n")
            report.append("|--------|--------|-------|----------|\n")
            for m in phase.modules:
                icon = "✓" if m.status == "passed" else "✗"
                report.append(f"| {m.module} | {icon} {m.status} | {m.tests_passed}/{m.tests_run} | {m.duration_ms:.0f}ms |\n")
            report.append("\n")
        
        # Errors
        if self.total_errors > 0:
            report.append("## Errors\n\n")
            for phase in self.results:
                for m in phase.modules:
                    if m.errors:
                        report.append(f"### {m.module}\n\n")
                        for error in m.errors[:5]:
                            report.append(f"- {error}\n")
                        if len(m.errors) > 5:
                            report.append(f"- ... and {len(m.errors) - 5} more\n")
                        report.append("\n")
        
        return "".join(report)
    
    def generate_json_report(self) -> str:
        """JSON形式のレポートを生成"""
        total = self.total_passed + self.total_failed
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "duration_ms": (self.end_time - self.start_time) * 1000,
            "parallel": self.parallel,
            "timeout": self.timeout,
            "summary": {
                "total_passed": self.total_passed,
                "total_failed": self.total_failed,
                "total_errors": self.total_errors,
                "success_rate": (self.total_passed / total * 100) if total > 0 else 0
            },
            "phases": [p.to_dict() for p in self.results]
        }
        return json.dumps(report_data, indent=2)
    
    def save_report(self, filename: str = None, format: str = "markdown"):
        """レポートをファイルに保存"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = "json" if format == "json" else "md"
            filename = f"test_report_{timestamp}.{ext}"
        
        # docs/test_reports/に保存
        report_dir = Path("docs") / "test_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / filename
        
        if format == "json":
            report_path.write_text(self.generate_json_report())
        else:
            report_path.write_text(self.generate_markdown_report())
        
        print(f"\nReport saved to: {report_path}")
        return report_path


def main():
    """メインエントリポイント"""
    parser = argparse.ArgumentParser(
        description="Integration Test Runner v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_integration_tests_v2.py all
    python run_integration_tests_v2.py phase1 --parallel
    python run_integration_tests_v2.py all --json --coverage
        """
    )
    
    parser.add_argument(
        "phase",
        choices=["phase1", "phase2", "phase3", "phase4", "all"],
        help="Test phase to run"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Measure code coverage (requires pytest-cov)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report in JSON format"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Test timeout in seconds (default: 300)"
    )
    
    args = parser.parse_args()
    
    runner = TestRunner(parallel=args.parallel, timeout=args.timeout)
    runner.start_time = time.time()
    
    if args.phase == "all":
        phases_to_run = list(TEST_PHASES.keys())
    else:
        phases_to_run = [args.phase]
    
    # テスト実行
    for phase_id in phases_to_run:
        if phase_id in TEST_PHASES:
            result = runner.run_phase(phase_id)
            runner.results.append(result)
        else:
            print(f"Unknown phase: {phase_id}")
    
    runner.end_time = time.time()
    
    # レポート出力
    if args.json:
        print(runner.generate_json_report())
    else:
        print(runner.generate_markdown_report())
    
    # ファイル保存
    report_format = "json" if args.json else "markdown"
    runner.save_report(format=report_format)
    
    # 終了コード
    sys.exit(0 if runner.total_failed == 0 else 1)


if __name__ == "__main__":
    main()
