#!/usr/bin/env python3
"""
全テスト実行スクリプト

プロジェクト内のすべてのテストを実行し、結果をまとめて表示する。

Usage:
    python run_all_tests.py           # 全テスト実行
    python run_all_tests.py --quick   # クイックテスト（主要テストのみ）
    python run_all_tests.py --ci      # CIモード（最小出力）
"""

import unittest
import sys
import os
import argparse
import time
from pathlib import Path

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# テストモジュールの定義
TEST_MODULES = {
    "crypto": [
        "test_crypto_v1",
        "test_crypto_integration", 
        "test_e2e_crypto",
        "test_signature",
    ],
    "wallet": [
        "test_wallet",
        "test_wallet_persistence",
    ],
    "api": [
        "test_api_server",
        "test_api_server_extended",
        "test_api_integration",
    ],
    "peer": [
        "test_peer_service",
        "test_peer_service_v1",
        "test_peer_service_pytest",
    ],
    "integration": [
        "test_integration",
        "test_integration_token",
        "test_token_integration",
    ],
    "session": [
        "test_session_manager",
    ],
    "task": [
        "test_task_verification",
    ],
    "moltbook": [
        "test_moltbook_client",
        "test_moltbook_integration",
    ],
    "security": [
        "test_security",
    ],
}

# クイックテスト（主要なテストのみ）
QUICK_TEST_MODULES = [
    "test_wallet",
    "test_crypto_v1",
    "test_api_server",
]


def import_test_module(module_name: str):
    """テストモジュールを動的にインポート"""
    try:
        module = __import__(module_name)
        return module
    except ImportError as e:
        return None
    except Exception as e:
        print(f"   ⚠️  Error importing {module_name}: {e}")
        return None


def run_test_module(module_name: str, verbosity: int = 1) -> tuple:
    """単一のテストモジュールを実行
    
    Returns:
        (success: bool, tests_run: int, failures: int, errors: int, duration: float)
    """
    module = import_test_module(module_name)
    if module is None:
        return False, 0, 0, 0, 0.0
    
    # unittest.TestLoaderを使用してテストを検出
    loader = unittest.TestLoader()
    
    # モジュールがunittest.TestCaseを含むか確認
    if hasattr(module, 'unittest') or hasattr(module, 'TestCase'):
        try:
            suite = loader.loadTestsFromModule(module)
            if suite.countTestCases() == 0:
                return True, 0, 0, 0, 0.0  # 空のテストは成功として扱う
        except Exception as e:
            print(f"   ⚠️  Error loading tests from {module_name}: {e}")
            return False, 0, 0, 0, 0.0
    
    # テスト実行
    start_time = time.time()
    
    # TextTestRunnerを使用して実行
    runner = unittest.TextTestRunner(verbosity=0)  # 個別テストの出力は抑制
    result = runner.run(suite)
    
    duration = time.time() - start_time
    
    tests_run = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    
    success = failures == 0 and errors == 0
    
    return success, tests_run, failures, errors, duration


def run_test_file(file_path: str, verbosity: int = 1) -> tuple:
    """テストファイルを直接実行
    
    Returns:
        (success: bool, tests_run: int, failures: int, errors: int, duration: float)
    """
    import subprocess
    
    start_time = time.time()
    
    try:
        # テストファイルをサブプロセスで実行
        result = subprocess.run(
            [sys.executable, file_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        duration = time.time() - start_time
        
        # 終了コードで成功/失敗を判定
        success = result.returncode == 0
        
        # 出力からテスト数を解析（簡易的）
        output = result.stdout + result.stderr
        tests_run = 1 if success else 0
        failures = 0 if success else 1
        errors = 0
        
        return success, tests_run, failures, errors, duration
        
    except subprocess.TimeoutExpired:
        return False, 0, 0, 0, 60.0
    except Exception as e:
        return False, 0, 0, 1, time.time() - start_time


def main():
    parser = argparse.ArgumentParser(
        description="Run all tests in the project",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--quick", action="store_true", help="Run quick tests only")
    parser.add_argument("--ci", action="store_true", help="CI mode (minimal output)")
    parser.add_argument("--category", help="Run specific category (crypto/wallet/api/peer/integration)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    verbosity = 2 if args.verbose else (0 if args.ci else 1)
    
    print("=" * 70)
    print("🧪  AI Collaboration Platform - Test Suite")
    print("=" * 70)
    
    services_dir = Path(__file__).parent
    
    # 実行するテストを選択
    if args.quick:
        test_files = [f"{name}.py" for name in QUICK_TEST_MODULES]
        print("Mode: Quick Test (main tests only)")
    elif args.category:
        if args.category in TEST_MODULES:
            test_files = [f"{name}.py" for name in TEST_MODULES[args.category]]
            print(f"Mode: Category '{args.category}'")
        else:
            print(f"❌ Unknown category: {args.category}")
            print(f"Available categories: {', '.join(TEST_MODULES.keys())}")
            return 1
    else:
        # 全テストファイルを収集
        test_files = []
        for category, modules in TEST_MODULES.items():
            test_files.extend([f"{name}.py" for name in modules])
        print("Mode: Full Test Suite")
    
    print(f"Tests to run: {len(test_files)}")
    print("-" * 70)
    
    # テスト実行
    results = []
    total_start = time.time()
    
    for test_file in test_files:
        test_path = services_dir / test_file
        
        if not test_path.exists():
            if not args.ci:
                print(f"⏭️  {test_file}: Not found")
            results.append((test_file, "skipped", 0, 0, 0, 0.0))
            continue
        
        if not args.ci:
            print(f"🔄 Running {test_file}...", end=" ", flush=True)
        
        # テスト実行
        success, tests_run, failures, errors, duration = run_test_file(str(test_path), verbosity)
        
        status = "passed" if success else "failed"
        results.append((test_file, status, tests_run, failures, errors, duration))
        
        if not args.ci:
            icon = "✅" if success else "❌"
            print(f"{icon} ({duration:.2f}s)")
        
        if args.verbose and not success:
            # 詳細出力が必要な場合、エラー内容を表示
            pass
    
    total_duration = time.time() - total_start
    
    # 結果サマリー
    print("-" * 70)
    print("📊 Test Results Summary")
    print("-" * 70)
    
    passed = sum(1 for r in results if r[1] == "passed")
    failed = sum(1 for r in results if r[1] == "failed")
    skipped = sum(1 for r in results if r[1] == "skipped")
    total_tests = sum(r[2] for r in results)
    total_failures = sum(r[3] for r in results)
    total_errors = sum(r[4] for r in results)
    
    # 詳細結果
    if not args.ci or failed > 0:
        print("\nDetailed Results:")
        for test_file, status, tests_run, failures, errors, duration in results:
            if status == "passed":
                icon = "✅"
            elif status == "failed":
                icon = "❌"
            else:
                icon = "⏭️"
            print(f"  {icon} {test_file:40s} {status:10s} ({duration:.2f}s)")
    
    print("\n" + "=" * 70)
    print(f"Total: {len(results)} test files")
    print(f"  ✅ Passed:  {passed}")
    print(f"  ❌ Failed:  {failed}")
    print(f"  ⏭️  Skipped: {skipped}")
    print(f"Total time: {total_duration:.2f}s")
    print("=" * 70)
    
    # 最終判定
    if failed == 0:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {failed} test file(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
