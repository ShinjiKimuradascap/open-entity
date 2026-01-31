#!/usr/bin/env python3
"""
統合テスト実行スクリプト
Phase 1-4のテストを順次実行

Usage:
    python run_integration_tests.py [phase]
    
    phase:
        phase1 - 基本機能テスト (SessionManager, Crypto)
        phase2 - 暗号化統合テスト (E2E Encryption)
        phase3 - PeerService統合テスト
        phase4 - End-to-Endテスト
        all    - 全フェーズ実行
"""

import sys
import asyncio
import importlib
import traceback
from pathlib import Path
from datetime import datetime

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
    """テスト実行エンジン"""
    
    def __init__(self):
        self.results = {}
        self.passed = 0
        self.failed = 0
        self.errors = []
        
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


def main():
    """メインエントリポイント"""
    if len(sys.argv) < 2:
        print("Usage: python run_integration_tests.py [phase1|phase2|phase3|phase4|all]")
        sys.exit(1)
        
    phase_arg = sys.argv[1].lower()
    runner = TestRunner()
    
    if phase_arg == "all":
        phases_to_run = list(TEST_PHASES.keys())
    else:
        phases_to_run = [phase_arg]
        
    # テスト実行
    for phase_id in phases_to_run:
        if phase_id in TEST_PHASES:
            runner.run_phase(phase_id)
        else:
            print(f"Unknown phase: {phase_id}")
            
    # レポート出力
    print(runner.generate_report())
    runner.save_report()
    
    # 終了コード
    sys.exit(0 if runner.failed == 0 else 1)


if __name__ == "__main__":
    main()
