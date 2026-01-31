#!/usr/bin/env python3
"""Test Report Generator - Creates test reports from pytest output

Usage:
    python scripts/generate_test_report.py [json-file|--html|--all]
    
    json-file   - Path to pytest JSON output
    --html      - Generate HTML report using pytest-html
    --all       - Generate all category reports
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def generate_markdown_report(results):
    lines = []
    lines.append("# Integration Test Report")
    lines.append(f"\nGenerated: {datetime.now().isoformat()}")
    lines.append(f"\n## Summary")
    lines.append(f"\nTotal Tests: {results.get('total', 0)}")
    lines.append(f"Passed: {results.get('passed', 0)}")
    lines.append(f"Failed: {results.get('failed', 0)}")
    lines.append(f"Duration: {results.get('duration', 0):.2f}s")
    
    success_rate = 0
    total = results.get('total', 0)
    passed = results.get('passed', 0)
    if total > 0:
        success_rate = (passed / total) * 100
    lines.append(f"Success Rate: {success_rate:.1f}%")
    
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_test_report.py <pytest-json-output>")
        sys.exit(1)
    
    json_file = Path(sys.argv[1])
    if not json_file.exists():
        print(f"Error: File not found: {json_file}")
        sys.exit(1)
    
    data = json.loads(json_file.read_text())
    
    results = {
        'total': data.get('summary', {}).get('total', 0),
        'passed': data.get('summary', {}).get('passed', 0),
        'failed': data.get('summary', {}).get('failed', 0),
        'duration': data.get('duration', 0)
    }
    
    report = generate_markdown_report(results)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path("docs/test_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = report_dir / f"test_report_{timestamp}.md"
    report_file.write_text(report)
    
    print(f"Report saved to: {report_file}")


def generate_html_report(category: str = "all"):
    """Generate HTML report using pytest-html"""
    report_dir = Path("docs/test_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"test_report_{category}_{timestamp}.html"
    
    cmd = [
        "python", "-m", "pytest",
        "services/", "tests/",
        "-v", "--tb=short",
        f"--html={report_file}", "--self-contained-html"
    ]
    
    if category != "all":
        cmd.extend(["-m", category])
    
    print(f"Generating HTML report: {report_file}")
    try:
        subprocess.run(cmd, check=False)
        print(f"✅ Report saved: {report_file}")
        return report_file
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def generate_all_reports():
    """Generate reports for all categories"""
    categories = ["unit", "integration", "crypto", "session", "peer"]
    reports = {}
    
    for cat in categories:
        report = generate_html_report(cat)
        if report:
            reports[cat] = report
    
    # Summary
    summary_file = Path("docs/test_reports") / "latest_reports.txt"
    with open(summary_file, "w") as f:
        f.write(f"# Test Reports\nGenerated: {datetime.now().isoformat()}\n\n")
        for cat, path in reports.items():
            f.write(f"- {cat}: {path}\n")
    
    print(f"\n📊 Summary: {summary_file}")
    return reports


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_test_report.py <json-file|--html|--all>")
        sys.exit(1)
    
    arg = sys.argv[1]
    
    if arg == "--html":
        generate_html_report()
    elif arg == "--all":
        generate_all_reports()
    else:
        # Original JSON processing
        json_file = Path(arg)
        if not json_file.exists():
            print(f"Error: File not found: {json_file}")
            sys.exit(1)
        
        data = json.loads(json_file.read_text())
        results = {
            'total': data.get('summary', {}).get('total', 0),
            'passed': data.get('summary', {}).get('passed', 0),
            'failed': data.get('summary', {}).get('failed', 0),
            'duration': data.get('duration', 0)
        }
        
        report = generate_markdown_report(results)
        report_dir = Path("docs/test_reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"test_report_{timestamp}.md"
        report_file.write_text(report)
        print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
