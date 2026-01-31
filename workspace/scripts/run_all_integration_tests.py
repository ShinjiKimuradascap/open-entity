#!/usr/bin/env python3
"""
統合テスト自動化ランナー

全統合テストを一括実行し、カテゴリ別フィルタリング、並列実行、
結果レポート生成をサポートします。

Usage:
    python scripts/run_all_integration_tests.py --category e2e --workers 4 --report json
    python scripts/run_all_integration_tests.py --list
    python scripts/run_all_integration_tests.py --dry-run
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import tempfile


@dataclass
class TestResult:
    """個別テスト結果"""
    test_file: str
    category: str
    status: str  # passed, failed, skipped, error
    duration: float
    output: str = ""
    error_message: str = ""


@dataclass
class CategorySummary:
    """カテゴリ別サマリー"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration: float = 0.0


@dataclass
class TestReport:
    """テスト実行レポート"""
    summary: Dict = field(default_factory=dict)
    categories: Dict[str, CategorySummary] = field(default_factory=dict)
    failures: List[Dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class IntegrationTestRunner:
    """統合テストランナー"""
    
    # テストカテゴリとファイルパターンのマッピング
    TEST_CATEGORIES = {
        'e2e': {
            'patterns': ['tests/e2e/test_*.py'],
            'description': 'End-to-End Tests'
        },
        'api': {
            'patterns': [
                'services/test_api_integration.py',
                'services/test_*api*.py',
                'tests/e2e/test_api_server*.py',
                'tests/e2e/test_p0_endpoints.py'
            ],
            'description': 'API Integration Tests'
        },
        'peer': {
            'patterns': [
                'services/test_peer_service_integration.py',
                'services/test_peer_service_e2e_integration.py',
                'services/test_handshake_integration.py',
                'tests/e2e/test_peer_communication.py',
                'tests/e2e/test_l2_peer_discovery.py',
                'tests/test_peer_service_dht_integration.py',
                'tests/integration/test_bootstrap_discovery_integration.py'
            ],
            'description': 'Peer Service Tests'
        },
        'token': {
            'patterns': [
                'services/test_token_integration.py',
                'services/test_token_system_integration.py',
                'services/test_token_economy_integration.py',
                'services/test_reward_integration.py',
                'tests/e2e/test_token_transfer_e2e.py',
                'tests/integration/test_token_transfer_integration.py',
                'tests/integration/test_task_reward_integration.py'
            ],
            'description': 'Token System Tests'
        },
        'dht': {
            'patterns': [
                'services/test_dht_integration.py',
                'services/test_dht_node.py',
                'tests/test_dht_peer_integration.py',
                'tests/test_dht_registry.py',
                'tests/practical/test_practical_discovery.py'
            ],
            'description': 'DHT Tests'
        },
        'moltbook': {
            'patterns': [
                'services/test_moltbook_integration.py',
                'services/test_orchestrator_moltbook.py',
                'tests/e2e/test_moltbook_e2e.py'
            ],
            'description': 'Moltbook Integration Tests'
        },
        'crypto': {
            'patterns': [
                'services/test_crypto_integration.py',
                'services/test_e2e_crypto_integration.py',
                'tests/e2e/test_websocket_communication.py'
            ],
            'description': 'Crypto/Security Tests'
        },
        'integration': {
            'patterns': [
                'services/test_integration.py',
                'services/test_integration_scenarios.py',
                'services/test_v1.1_integration.py',
                'services/test_l1_integration.py',
                'services/test_entity_a_b_integration.py',
                'tests/integration/test_*.py'
            ],
            'description': 'General Integration Tests'
        },
        'practical': {
            'patterns': [
                'tests/practical/test_practical_*.py'
            ],
            'description': 'Practical Tests'
        },
        'all': {
            'patterns': [
                'services/test_*integration*.py',
                'tests/e2e/test_*.py',
                'tests/integration/test_*.py',
                'tests/practical/test_practical_*.py',
                'tests/test_*integration*.py'
            ],
            'description': 'All Integration Tests'
        }
    }
    
    def __init__(self, workers: int = 1, timeout: int = 300, verbose: bool = False):
        self.workers = workers
        self.timeout = timeout
        self.verbose = verbose
        self.project_root = Path(__file__).parent.parent
        self.report = TestReport()
        
    def discover_tests(self, category: str = 'all') -> List[Tuple[str, str]]:
        """
        テストファイルを発見する
        
        Returns:
            List of (file_path, category) tuples
        """
        test_files = []
        
        if category == 'all':
            categories = ['e2e', 'api', 'peer', 'token', 'dht', 'moltbook', 'crypto', 'integration', 'practical']
        else:
            categories = [category]
        
        discovered = set()
        
        for cat in categories:
            if cat not in self.TEST_CATEGORIES:
                continue
                
            patterns = self.TEST_CATEGORIES[cat]['patterns']
            
            for pattern in patterns:
                # globパターンを展開
                if '*' in pattern:
                    matched = list(self.project_root.glob(pattern))
                else:
                    path = self.project_root / pattern
                    matched = [path] if path.exists() else []
                
                for file_path in matched:
                    file_str = str(file_path.relative_to(self.project_root))
                    if file_str not in discovered and file_path.suffix == '.py':
                        discovered.add(file_str)
                        test_files.append((file_str, cat))
        
        # 重複を排除してソート
        test_files.sort(key=lambda x: x[0])
        return test_files
    
    def list_tests(self) -> None:
        """テストファイル一覧を表示"""
        print("=" * 80)
        print("Available Integration Tests")
        print("=" * 80)
        
        for category, info in self.TEST_CATEGORIES.items():
            if category == 'all':
                continue
                
            print(f"\n[{category.upper()}] {info['description']}")
            print("-" * 60)
            
            tests = self.discover_tests(category)
            for test_file, cat in tests:
                if cat == category:
                    print(f"  - {test_file}")
        
        print("\n" + "=" * 80)
        all_tests = self.discover_tests('all')
        print(f"Total: {len(all_tests)} test files")
    
    async def run_test(self, test_file: str, category: str) -> TestResult:
        """
        個別テストを実行
        
        Args:
            test_file: テストファイルパス
            category: テストカテゴリ
            
        Returns:
            TestResult
        """
        start_time = time.time()
        
        # pytestコマンド構築
        cmd = [
            sys.executable, '-m', 'pytest',
            test_file,
            '-v',
            '--tb=short',
            f'--timeout={self.timeout}',
            '--asyncio-mode=auto'
        ]
        
        if self.verbose:
            cmd.append('-s')
        
        # 環境変数設定
        env = os.environ.copy()
        env['PYTHONPATH'] = str(self.project_root)
        
        try:
            # テスト実行
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_root),
                env=env
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout + 10  # バッファ
            )
            
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            output = stdout_str + stderr_str
            
            duration = time.time() - start_time
            
            # 結果判定
            if process.returncode == 0:
                status = 'passed'
                error_msg = ''
            elif 'skipped' in stdout_str.lower() and 'passed' not in stdout_str.lower():
                status = 'skipped'
                error_msg = 'Test skipped'
            else:
                status = 'failed'
                # エラーメッセージを抽出
                error_lines = [line for line in output.split('\n') if 'FAILED' in line or 'ERROR' in line]
                error_msg = '\n'.join(error_lines[:5]) if error_lines else 'Test failed'
            
            return TestResult(
                test_file=test_file,
                category=category,
                status=status,
                duration=duration,
                output=output,
                error_message=error_msg
            )
            
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            return TestResult(
                test_file=test_file,
                category=category,
                status='error',
                duration=duration,
                output='',
                error_message=f'Timeout after {self.timeout} seconds'
            )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                test_file=test_file,
                category=category,
                status='error',
                duration=duration,
                output='',
                error_message=str(e)
            )
    
    async def run_tests_parallel(self, test_files: List[Tuple[str, str]], max_workers: int) -> List[TestResult]:
        """
        テストを並列実行
        
        Args:
            test_files: (file_path, category) のリスト
            max_workers: 並列ワーカー数
            
        Returns:
            TestResultのリスト
        """
        semaphore = asyncio.Semaphore(max_workers)
        
        async def run_with_limit(test_file: str, category: str) -> TestResult:
            async with semaphore:
                result = await self.run_test(test_file, category)
                # 進捗表示
                status_icon = '✓' if result.status == 'passed' else '✗' if result.status == 'failed' else '○'
                print(f"  [{status_icon}] {test_file} ({result.duration:.2f}s)")
                return result
        
        # 全テストを並列実行
        tasks = [run_with_limit(file, cat) for file, cat in test_files]
        results = await asyncio.gather(*tasks)
        
        return results
    
    def generate_json_report(self, results: List[TestResult]) -> Dict:
        """JSON形式のレポートを生成"""
        # カテゴリ別サマリー初期化
        for category in self.TEST_CATEGORIES.keys():
            if category != 'all':
                self.report.categories[category] = CategorySummary()
        
        # 結果集計
        total_duration = 0.0
        for result in results:
            cat_summary = self.report.categories.get(result.category, CategorySummary())
            cat_summary.total += 1
            cat_summary.duration += result.duration
            total_duration += result.duration
            
            if result.status == 'passed':
                cat_summary.passed += 1
            elif result.status == 'failed':
                cat_summary.failed += 1
                self.report.failures.append({
                    'test_file': result.test_file,
                    'category': result.category,
                    'error': result.error_message
                })
            else:
                cat_summary.skipped += 1
            
            self.report.categories[result.category] = cat_summary
        
        # 全体サマリー
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.status == 'passed')
        failed_tests = sum(1 for r in results if r.status == 'failed')
        skipped_tests = sum(1 for r in results if r.status == 'skipped')
        
        self.report.summary = {
            'total': total_tests,
            'passed': passed_tests,
            'failed': failed_tests,
            'skipped': skipped_tests,
            'duration_seconds': round(total_duration, 2),
            'success_rate': round(passed_tests / total_tests * 100, 2) if total_tests > 0 else 0
        }
        
        # 辞書形式に変換
        report_dict = {
            'timestamp': self.report.timestamp,
            'summary': self.report.summary,
            'categories': {
                cat: {
                    'total': summary.total,
                    'passed': summary.passed,
                    'failed': summary.failed,
                    'skipped': summary.skipped,
                    'duration': round(summary.duration, 2)
                }
                for cat, summary in self.report.categories.items()
                if summary.total > 0
            },
            'failures': self.report.failures
        }
        
        return report_dict
    
    def generate_markdown_report(self, results: List[TestResult]) -> str:
        """Markdown形式のレポートを生成"""
        report_dict = self.generate_json_report(results)
        
        lines = [
            "# Integration Test Report",
            f"\nGenerated: {self.report.timestamp}",
            "\n## Summary",
            f"\n| Metric | Value |",
            "|--------|-------|",
            f"| Total Tests | {report_dict['summary']['total']} |",
            f"| Passed | {report_dict['summary']['passed']} |",
            f"| Failed | {report_dict['summary']['failed']} |",
            f"| Skipped | {report_dict['summary']['skipped']} |",
            f"| Duration | {report_dict['summary']['duration_seconds']}s |",
            f"| Success Rate | {report_dict['summary']['success_rate']}% |",
        ]
        
        # カテゴリ別詳細
        lines.append("\n## Category Breakdown")
        lines.append("\n| Category | Total | Passed | Failed | Skipped | Duration |")
        lines.append("|----------|-------|--------|--------|---------|----------|")
        
        for cat, data in report_dict['categories'].items():
            lines.append(
                f"| {cat} | {data['total']} | {data['passed']} | "
                f"{data['failed']} | {data['skipped']} | {data['duration']}s |"
            )
        
        # 失敗詳細
        if report_dict['failures']:
            lines.append("\n## Failures")
            for failure in report_dict['failures']:
                lines.append(f"\n### {failure['test_file']}")
                lines.append(f"- Category: {failure['category']}")
                lines.append(f"- Error: {failure['error']}")
        
        return '\n'.join(lines)
    
    def save_reports(self, results: List[TestResult], output_format: str = 'both') -> Dict[str, str]:
        """レポートをファイルに保存"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        reports_dir = self.project_root / 'reports'
        reports_dir.mkdir(exist_ok=True)
        
        saved_files = {}
        
        if output_format in ['json', 'both']:
            json_report = self.generate_json_report(results)
            json_path = reports_dir / f'integration_test_report_{timestamp}.json'
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_report, f, indent=2, ensure_ascii=False)
            saved_files['json'] = str(json_path)
        
        if output_format in ['markdown', 'md', 'both']:
            md_report = self.generate_markdown_report(results)
            md_path = reports_dir / f'integration_test_report_{timestamp}.md'
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_report)
            saved_files['markdown'] = str(md_path)
        
        return saved_files
    
    async def run(self, category: str = 'all', dry_run: bool = False, 
                  report_format: str = 'both') -> int:
        """
        メイン実行関数
        
        Returns:
            終了コード (0: 全成功, 1: 失敗あり)
        """
        print("=" * 80)
        print("Integration Test Runner")
        print("=" * 80)
        print(f"Category: {category}")
        print(f"Workers: {self.workers}")
        print(f"Timeout: {self.timeout}s")
        print(f"Verbose: {self.verbose}")
        print("=" * 80)
        
        # テスト発見
        test_files = self.discover_tests(category)
        
        if not test_files:
            print(f"\nNo test files found for category: {category}")
            return 1
        
        print(f"\nDiscovered {len(test_files)} test files:")
        for test_file, cat in test_files[:10]:
            print(f"  - {test_file} ({cat})")
        if len(test_files) > 10:
            print(f"  ... and {len(test_files) - 10} more")
        
        if dry_run:
            print("\n[Dry Run] Tests would be executed:")
            for test_file, cat in test_files:
                print(f"  - {test_file}")
            return 0
        
        # テスト実行
        print(f"\nRunning tests with {self.workers} workers...\n")
        start_time = time.time()
        
        results = await self.run_tests_parallel(test_files, self.workers)
        
        total_duration = time.time() - start_time
        
        # 結果表示
        print("\n" + "=" * 80)
        print("Test Results Summary")
        print("=" * 80)
        
        passed = sum(1 for r in results if r.status == 'passed')
        failed = sum(1 for r in results if r.status == 'failed')
        skipped = sum(1 for r in results if r.status == 'skipped')
        
        print(f"Total: {len(results)}")
        print(f"Passed: {passed} ✓")
        print(f"Failed: {failed} ✗")
        print(f"Skipped: {skipped} ○")
        print(f"Duration: {total_duration:.2f}s")
        
        # レポート保存
        saved_reports = self.save_reports(results, report_format)
        print("\n" + "=" * 80)
        print("Reports Generated")
        print("=" * 80)
        for fmt, path in saved_reports.items():
            print(f"  {fmt}: {path}")
        
        # 失敗詳細
        if failed > 0:
            print("\n" + "=" * 80)
            print("Failed Tests Details")
            print("=" * 80)
            for result in results:
                if result.status == 'failed':
                    print(f"\n{result.test_file}")
                    print(f"  Error: {result.error_message}")
                    if self.verbose and result.output:
                        print(f"  Output:\n{result.output[:1000]}")
        
        print("\n" + "=" * 80)
        
        return 0 if failed == 0 else 1


def parse_args() -> argparse.Namespace:
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(
        description='Integration Test Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python scripts/run_all_integration_tests.py --category e2e --workers 4
  python scripts/run_all_integration_tests.py --list
  python scripts/run_all_integration_tests.py --category token --dry-run
  python scripts/run_all_integration_tests.py --report json --timeout 600
        '''
    )
    
    parser.add_argument(
        '--category',
        choices=['e2e', 'api', 'peer', 'token', 'dht', 'moltbook', 'crypto', 'integration', 'practical', 'all'],
        default='all',
        help='Test category to run (default: all)'
    )
    
    parser.add_argument(
        '--workers', '-n',
        type=int,
        default=1,
        help='Number of parallel workers (default: 1)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Test timeout in seconds (default: 300)'
    )
    
    parser.add_argument(
        '--report',
        choices=['json', 'markdown', 'md', 'both'],
        default='both',
        help='Report output format (default: both)'
    )
    
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List all available tests'
    )
    
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Show what would be executed without running'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    return parser.parse_args()


async def main() -> int:
    """メインエントリポイント"""
    args = parse_args()
    
    runner = IntegrationTestRunner(
        workers=args.workers,
        timeout=args.timeout,
        verbose=args.verbose
    )
    
    if args.list:
        runner.list_tests()
        return 0
    
    return await runner.run(
        category=args.category,
        dry_run=args.dry_run,
        report_format=args.report
    )


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
