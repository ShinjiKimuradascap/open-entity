#!/usr/bin/env python3
"""
Scheduled Test Runner - Automated pytest execution with scheduling, history tracking, and Slack notifications.

Usage:
    # Run once
    python scripts/scheduled_test_runner.py --once --test-path services/test_api_server.py
    
    # Run with schedule (cron format)
    python scripts/scheduled_test_runner.py --schedule "0 2 * * *" --test-path services/
    
    # Run with Slack notification
    python scripts/scheduled_test_runner.py --once --notify --test-path services/
    
    # Show trend analysis
    python scripts/scheduled_test_runner.py --trend --test-path services/
    
    # Show help
    python scripts/scheduled_test_runner.py --help

Dependencies:
    pip install pytest schedule
    
Optional for Slack:
    pip install slack-sdk  # or use built-in webhook notification

Configuration:
    config/test_runner.json - Default settings
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Try to import schedule for cron-like functionality
try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False

# Try to import Slack notification
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
    from notify_slack import notify_slack, notify_slack_success, notify_slack_error
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False


# Constants
DEFAULT_CONFIG_PATH = Path("config/test_runner.json")
DEFAULT_HISTORY_PATH = Path("data/test_history.json")
DEFAULT_OUTPUT_DIR = Path("test_results")
MAX_HISTORY_SIZE = 10


class TestRunnerConfig:
    """Configuration for the test runner."""
    
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.data: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                self.data = json.loads(self.config_path.read_text())
                print(f"[INFO] Loaded config from {self.config_path}")
            except (json.JSONDecodeError, IOError) as e:
                print(f"[WARNING] Failed to load config: {e}")
                self.data = self._default_config()
        else:
            print(f"[INFO] Config not found at {self.config_path}, using defaults")
            self.data = self._default_config()
            self.save()
    
    def save(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self.data, indent=2))
        print(f"[INFO] Saved config to {self.config_path}")
    
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "default_test_path": "services/",
            "default_schedule": "0 2 * * *",
            "notify_on_success": False,
            "notify_on_failure": True,
            "max_history_size": MAX_HISTORY_SIZE,
            "slack_webhook_url": os.environ.get("SLACK_WEBHOOK_URL", ""),
            "pytest_options": ["-v", "--tb=short"]
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self.data[key] = value


class TestHistory:
    """Manage test execution history."""
    
    def __init__(self, history_path: Path = DEFAULT_HISTORY_PATH):
        self.history_path = history_path
        self.entries: List[Dict[str, Any]] = []
        self.load()
    
    def load(self) -> None:
        """Load history from file."""
        if self.history_path.exists():
            try:
                self.entries = json.loads(self.history_path.read_text())
                print(f"[INFO] Loaded {len(self.entries)} history entries")
            except (json.JSONDecodeError, IOError) as e:
                print(f"[WARNING] Failed to load history: {e}")
                self.entries = []
        else:
            self.entries = []
    
    def save(self) -> None:
        """Save history to file."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(json.dumps(self.entries, indent=2))
    
    def add(self, entry: Dict[str, Any]) -> None:
        """Add new entry and maintain max size."""
        self.entries.insert(0, entry)  # Newest first
        max_size = entry.get("max_history_size", MAX_HISTORY_SIZE)
        self.entries = self.entries[:max_size]
        self.save()
    
    def get_trend(self, test_path: Optional[str] = None) -> Dict[str, Any]:
        """Analyze trend from history."""
        if not self.entries:
            return {"status": "no_data"}
        
        # Filter by test path if specified
        entries = self.entries
        if test_path:
            entries = [e for e in entries if e.get("test_path") == test_path]
        
        if not entries:
            return {"status": "no_matching_data"}
        
        total_runs = len(entries)
        passed_runs = sum(1 for e in entries if e.get("summary", {}).get("failed", 0) == 0)
        failed_runs = total_runs - passed_runs
        
        # Calculate average duration
        durations = [e.get("duration_sec", 0) for e in entries if e.get("duration_sec")]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        # Recent trend (last 3 runs)
        recent = entries[:3]
        recent_passed = sum(1 for e in recent if e.get("summary", {}).get("failed", 0) == 0)
        
        return {
            "status": "success",
            "total_runs": total_runs,
            "passed_runs": passed_runs,
            "failed_runs": failed_runs,
            "success_rate": (passed_runs / total_runs * 100) if total_runs > 0 else 0,
            "average_duration_sec": round(avg_duration, 2),
            "recent_trend": {
                "last_3_runs": len(recent),
                "passed": recent_passed,
                "failed": len(recent) - recent_passed
            },
            "last_run": entries[0].get("timestamp") if entries else None
        }


class TestRunner:
    """Main test runner class."""
    
    def __init__(self, config: TestRunnerConfig, history: TestHistory):
        self.config = config
        self.history = history
        self.current_job = None
    
    def run_tests(
        self,
        test_path: str,
        notify: bool = False,
        pytest_options: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Execute pytest and return results."""
        print(f"\n{'='*60}")
        print(f"Running tests: {test_path}")
        print(f"{'='*60}\n")
        
        start_time = time.time()
        timestamp = datetime.now().isoformat()
        
        # Build pytest command
        options = pytest_options or self.config.get("pytest_options", ["-v", "--tb=short"])
        cmd = [sys.executable, "-m", "pytest", test_path] + options
        
        print(f"[CMD] {' '.join(cmd)}\n")
        
        # Run pytest
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent.parent),
                timeout=600  # 10 minute timeout
            )
            
            duration = time.time() - start_time
            
            # Parse output to extract summary
            output = result.stdout + "\n" + result.stderr
            
            # Extract test counts from output
            summary = self._parse_test_summary(output, result.returncode)
            
            # Extract failed test names
            failed_tests = self._extract_failed_tests(output)
            
            test_result = {
                "timestamp": timestamp,
                "test_path": test_path,
                "duration_sec": round(duration, 2),
                "summary": summary,
                "failed_tests": failed_tests[:10],  # Limit to first 10
                "exit_code": result.returncode,
                "max_history_size": self.config.get("max_history_size", MAX_HISTORY_SIZE)
            }
            
            # Print summary
            print(f"\n{'='*60}")
            print("Test Summary")
            print(f"{'='*60}")
            print(f"Duration: {test_result['duration_sec']:.2f}s")
            print(f"Total: {summary['total']}")
            print(f"Passed: {summary['passed']}")
            print(f"Failed: {summary['failed']}")
            print(f"Exit Code: {test_result['exit_code']}")
            
            if failed_tests:
                print(f"\nFailed Tests ({len(failed_tests)}):")
                for test in failed_tests[:10]:
                    print(f"  - {test}")
            
            # Save to history
            self.history.add(test_result)
            
            # Send notification if requested
            if notify and SLACK_AVAILABLE:
                self._send_notification(test_result)
            
            return test_result
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            error_result = {
                "timestamp": timestamp,
                "test_path": test_path,
                "duration_sec": round(duration, 2),
                "summary": {"total": 0, "passed": 0, "failed": 0, "error": 1, "skipped": 0},
                "failed_tests": [],
                "exit_code": -2,
                "error": "Test execution timed out (600s)"
            }
            if notify and SLACK_AVAILABLE:
                self._send_notification(error_result)
            return error_result
            
        except Exception as e:
            duration = time.time() - start_time
            error_result = {
                "timestamp": timestamp,
                "test_path": test_path,
                "duration_sec": round(duration, 2),
                "summary": {"total": 0, "passed": 0, "failed": 0, "error": 1, "skipped": 0},
                "failed_tests": [],
                "exit_code": -1,
                "error": str(e)
            }
            if notify and SLACK_AVAILABLE:
                self._send_notification(error_result)
            return error_result
    
    def _parse_test_summary(self, output: str, exit_code: int) -> Dict[str, int]:
        """Parse pytest output to extract test summary."""
        summary = {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}
        
        # Look for summary line like "1 passed, 2 failed in 0.5s"
        import re
        
        # Try to find summary pattern
        patterns = [
            r'(\d+) passed',
            r'(\d+) failed',
            r'(\d+) error',
            r'(\d+) skipped',
            r'(\d+) deselected'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                count = int(match.group(1))
                if 'passed' in pattern:
                    summary['passed'] = count
                elif 'failed' in pattern:
                    summary['failed'] = count
                elif 'error' in pattern:
                    summary['error'] = count
                elif 'skipped' in pattern:
                    summary['skipped'] = count
        
        summary['total'] = summary['passed'] + summary['failed'] + summary['error'] + summary['skipped']
        
        # If no summary found but exit code is 0, assume 1 passed (basic test)
        if summary['total'] == 0 and exit_code == 0:
            summary['passed'] = 1
            summary['total'] = 1
        elif summary['total'] == 0 and exit_code != 0:
            summary['failed'] = 1
            summary['total'] = 1
        
        return summary
    
    def _extract_failed_tests(self, output: str) -> List[str]:
        """Extract failed test names from pytest output."""
        failed_tests = []
        lines = output.split('\n')
        
        for line in lines:
            # Look for FAILED lines
            if 'FAILED' in line:
                # Extract test name
                parts = line.split()
                for part in parts:
                    if '::' in part or part.endswith('.py'):
                        # Clean up the test name
                        test_name = part.strip()
                        if test_name and test_name not in failed_tests:
                            failed_tests.append(test_name)
        
        return failed_tests
    
    def _send_notification(self, result: Dict[str, Any]) -> bool:
        """Send Slack notification based on test result."""
        summary = result.get("summary", {})
        failed = summary.get("failed", 0)
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        
        test_path = result.get("test_path", "unknown")
        duration = result.get("duration_sec", 0)
        
        if failed == 0 and summary.get("error", 0) == 0:
            # Success notification
            if self.config.get("notify_on_success", False):
                message = (
                    f"✅ *All Tests Passed*\n"
                    f"Path: `{test_path}`\n"
                    f"Duration: {duration:.2f}s\n"
                    f"Total: {total}, Passed: {passed}"
                )
                return notify_slack_success(message, "Test Run Complete")
        else:
            # Failure notification
            if self.config.get("notify_on_failure", True):
                failed_tests = result.get("failed_tests", [])
                failed_list = "\n".join([f"  • `{t}`" for t in failed_tests[:5]])
                if len(failed_tests) > 5:
                    failed_list += f"\n  ... and {len(failed_tests) - 5} more"
                
                error_msg = result.get("error", "")
                message = (
                    f"🚨 *Test Failures Detected*\n"
                    f"Path: `{test_path}`\n"
                    f"Duration: {duration:.2f}s\n"
                    f"Total: {total}, Failed: {failed}, Passed: {passed}\n"
                )
                if error_msg:
                    message += f"Error: {error_msg}\n"
                if failed_list:
                    message += f"\n*Failed Tests:*\n{failed_list}"
                
                return notify_slack_error(message, "Test Run Failed")
        
        return False
    
    def schedule_run(
        self,
        cron_schedule: str,
        test_path: str,
        notify: bool = False
    ) -> bool:
        """Schedule periodic test runs using cron format."""
        if not SCHEDULE_AVAILABLE:
            print("[ERROR] 'schedule' package not installed. Cannot schedule runs.")
            print("[INFO] Install with: pip install schedule")
            return False
        
        # Parse cron format (simplified: minute hour day month day_of_week)
        parts = cron_schedule.split()
        if len(parts) != 5:
            print(f"[ERROR] Invalid cron format: {cron_schedule}")
            print("[INFO] Expected: 'minute hour day month day_of_week'")
            print("[INFO] Example: '0 2 * * *' (daily at 2:00 AM)")
            print("[INFO]         '*/30 * * * *' (every 30 minutes)")
            return False
        
        minute, hour, day, month, day_of_week = parts
        
        def job():
            print(f"\n[Scheduled Job] Running at {datetime.now().isoformat()}")
            self.run_tests(test_path, notify=notify)
        
        # Build schedule based on cron parts
        if minute.startswith("*/") and hour == "*":
            # Every N minutes
            n = int(minute.replace("*/", ""))
            schedule.every(n).minutes.do(job)
            print(f"[INFO] Scheduled every {n} minute(s)")
        elif minute != "*" and hour != "*" and day == "*" and month == "*" and day_of_week == "*":
            # Daily at specific time
            time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"
            schedule.every().day.at(time_str).do(job)
            print(f"[INFO] Scheduled daily at {time_str}")
        elif minute != "*" and hour == "*":
            # Every hour at specific minute
            schedule.every().hour.at(f":{minute.zfill(2)}").do(job)
            print(f"[INFO] Scheduled every hour at :{minute.zfill(2)}")
        elif day_of_week != "*" and hour != "*" and minute != "*":
            # Weekly on specific day
            days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            try:
                dow = int(day_of_week)
                if 0 <= dow < 7:
                    day_name = days[dow]
                    time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"
                    getattr(schedule.every(), day_name).at(time_str).do(job)
                    print(f"[INFO] Scheduled every {day_name} at {time_str}")
            except ValueError:
                print(f"[WARNING] Could not parse day_of_week: {day_of_week}")
                schedule.every(1).hours.do(job)
        else:
            # Default: every hour
            schedule.every(1).hours.do(job)
            print(f"[INFO] Scheduled every hour (fallback)")
        
        print(f"[INFO] Press Ctrl+C to stop")
        print(f"[INFO] Next run: {schedule.next_run()}")
        
        # Run scheduler loop
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[INFO] Scheduler stopped")
        
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scheduled Test Runner - Automated pytest execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run once
  python %(prog)s --once --test-path services/test_api_server.py
  
  # Run with schedule (daily at 2:00 AM)
  python %(prog)s --schedule "0 2 * * *" --test-path services/
  
  # Run with Slack notification
  python %(prog)s --once --notify --test-path services/
  
  # Show trend analysis
  python %(prog)s --trend --test-path services/
  
  # Run every 30 minutes
  python %(prog)s --schedule "*/30 * * * *" --test-path services/ --notify
        """
    )
    
    parser.add_argument(
        "--schedule",
        type=str,
        metavar="CRON",
        help="Cron schedule (e.g., '0 2 * * *' for daily at 2 AM, '*/30 * * * *' for every 30min)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run tests once and exit"
    )
    parser.add_argument(
        "--test-path",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to test files or directories (default: services/)"
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Slack notifications based on results"
    )
    parser.add_argument(
        "--trend",
        action="store_true",
        help="Show trend analysis from history"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        metavar="FILE",
        help=f"Config file path (default: {DEFAULT_CONFIG_PATH})"
    )
    parser.add_argument(
        "--history",
        type=str,
        default=str(DEFAULT_HISTORY_PATH),
        metavar="FILE",
        help=f"History file path (default: {DEFAULT_HISTORY_PATH})"
    )
    parser.add_argument(
        "--pytest-opt",
        type=str,
        action="append",
        metavar="OPT",
        help="Additional pytest options (can be specified multiple times)"
    )
    
    args = parser.parse_args()
    
    # Initialize components
    config = TestRunnerConfig(Path(args.config))
    history = TestHistory(Path(args.history))
    runner = TestRunner(config, history)
    
    # Show trend analysis
    if args.trend:
        trend = history.get_trend(args.test_path)
        print("\n" + "="*60)
        print("Test Trend Analysis")
        print("="*60)
        print(json.dumps(trend, indent=2))
        return
    
    # Get test path
    test_path = args.test_path or config.get("default_test_path", "services/")
    
    # Run once
    if args.once:
        result = runner.run_tests(
            test_path=test_path,
            notify=args.notify,
            pytest_options=args.pytest_opt
        )
        
        # Output result as JSON
        print("\n" + "="*60)
        print("Final Result (JSON)")
        print("="*60)
        print(json.dumps(result, indent=2))
        
        # Exit with pytest exit code
        sys.exit(result.get("exit_code", 0))
    
    # Schedule runs
    elif args.schedule:
        success = runner.schedule_run(
            cron_schedule=args.schedule,
            test_path=test_path,
            notify=args.notify
        )
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()
        print("\n[ERROR] Specify either --once or --schedule")
        sys.exit(1)


if __name__ == "__main__":
    main()
