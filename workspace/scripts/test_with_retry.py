#!/usr/bin/env python3
"""
Test Runner with Automatic Retry Mechanism

This script runs tests using tests/runner.py with automatic retry on failure:
- Maximum 3 retry attempts
- 30-second wait between retries
- Returns exit code 0 on success, 1 on failure

Usage:
    python scripts/test_with_retry.py --category e2e
    python scripts/test_with_retry.py --category unit --verbose
    python scripts/test_with_retry.py --category integration --parallel 4
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 30


def run_test(category: str, verbose: bool = False, parallel: int = None) -> tuple[bool, str]:
    """
    Run tests for the specified category.
    
    Returns:
        Tuple of (success: bool, output: str)
    """
    cmd = [
        sys.executable,
        "tests/runner.py",
        "--category", category,
    ]
    
    if verbose:
        cmd.append("--verbose")
    
    if parallel:
        cmd.extend(["--parallel", str(parallel)])
    
    # Find workspace root (parent of scripts directory)
    workspace_root = Path(__file__).parent.parent.resolve()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=workspace_root,
            capture_output=True,
            text=True,
        )
        
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        
        return result.returncode == 0, output
    
    except Exception as e:
        return False, f"Error running tests: {e}"


def run_with_retry(category: str, verbose: bool = False, parallel: int = None) -> bool:
    """
    Run tests with automatic retry on failure.
    
    Args:
        category: Test category to run
        verbose: Enable verbose output
        parallel: Number of parallel workers
    
    Returns:
        True if tests passed (after retries), False otherwise
    """
    print(f"🚀 Starting test runner with retry (max {MAX_RETRIES} attempts)")
    print(f"   Category: {category}")
    print(f"   Retry delay: {RETRY_DELAY_SECONDS}s")
    print("=" * 70)
    
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n📌 Attempt {attempt}/{MAX_RETRIES}")
        print("-" * 70)
        
        success, output = run_test(category, verbose, parallel)
        
        if verbose or not success:
            print(output)
        
        if success:
            print(f"\n✅ Tests passed on attempt {attempt}!")
            return True
        
        if attempt < MAX_RETRIES:
            print(f"\n❌ Tests failed on attempt {attempt}")
            print(f"⏳ Waiting {RETRY_DELAY_SECONDS} seconds before retry...")
            time.sleep(RETRY_DELAY_SECONDS)
        else:
            print(f"\n❌ Tests failed on all {MAX_RETRIES} attempts")
    
    return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Test Runner with Automatic Retry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --category e2e
  %(prog)s --category unit --verbose
  %(prog)s --category integration --parallel 4
        """
    )
    
    parser.add_argument(
        "--category",
        choices=["unit", "integration", "e2e", "practical", "governance", "dht", "all"],
        default="unit",
        help="Test category to run (default: unit)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        metavar="N",
        help="Number of parallel workers (requires pytest-xdist)",
    )
    
    args = parser.parse_args()
    
    success = run_with_retry(
        category=args.category,
        verbose=args.verbose,
        parallel=args.parallel,
    )
    
    # Return appropriate exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
