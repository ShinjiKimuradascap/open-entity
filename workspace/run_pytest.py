#!/usr/bin/env python3
"""
Test runner for pytest execution
"""
import subprocess
import sys

def run_tests():
    """Run pytest tests"""
    # Run voice synthesis tests
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit/test_voice_synthesis.py", "-v", "--tb=short"],
        capture_output=True,
        text=True
    )
    print("=== STDOUT ===")
    print(result.stdout)
    print("=== STDERR ===")
    print(result.stderr)
    print(f"=== Return Code: {result.returncode} ===")
    return result.returncode

if __name__ == "__main__":
    exit(run_tests())
