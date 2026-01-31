#!/usr/bin/env python3
"""
Enhanced Coverage Report Generator
Parses API endpoints and test files to generate coverage reports
"""

import ast
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Endpoint priority classification
ENDPOINT_PRIORITY = {
    # P0 - Critical Core
    "POST:/register": "P0",
    "POST:/unregister/{entity_id}": "P0",
    "POST:/heartbeat": "P0",
    "GET:/discover": "P0",
    "GET:/agent/{entity_id}": "P0",
    "POST:/message": "P0",
    "POST:/message/send": "P0",
    "POST:/auth/token": "P0",
    "GET:/keys/public": "P0",
    "POST:/keys/verify": "P0",
    "GET:/health": "P0",
    
    # P1 - Token Economy
    "GET:/wallet/{entity_id}": "P1",
    "POST:/wallet/transfer": "P1",
    "GET:/wallet/{entity_id}/transactions": "P1",
    "POST:/task/create": "P1",
    "POST:/task/complete": "P1",
    "GET:/task/{task_id}": "P1",
    
    # P2 - Extended
    "GET:/stats": "P2",
    "POST:/rating/submit": "P2",
    "GET:/rating/{entity_id}": "P2",
    "GET:/reputation/{entity_id}/ratings": "P2",
    
    # P3 - Admin/Utility
    "POST:/admin/*": "P3",
    "GET:/admin/*": "P3",
    "POST:/tokens/*": "P3",
    "GET:/tokens/*": "P3",
    "POST:/token/*": "P3",
    "GET:/token/*": "P3",
    "GET:/moltbook/*": "P3",
    "POST:/moltbook/*": "P3",
    "POST:/governance/*": "P3",
    "GET:/governance/*": "P3",
    "GET:/ws/*": "P3",
}

class EndpointAnalyzer:
    """Analyzes API endpoints from source code"""
    
    def __init__(self, api_file: Path):
        self.api_file = api_file
        self.endpoints: List[Dict] = []
        
    def parse_endpoints(self) -> List[Dict]:
        """Extract all endpoints from api_server.py"""
        content = self.api_file.read_text()
        
        # Pattern to match FastAPI decorators
        pattern = r'@app\.(get|post|put|delete)\(["\']([^"\']+)["\']'
        
        for match in re.finditer(pattern, content, re.IGNORECASE):
            method = match.group(1).upper()
            path = match.group(2)
            
            # Get priority
            key = f"{method}:{path}"
            priority = "P3"  # default
            for pattern_key, p in ENDPOINT_PRIORITY.items():
                if self._match_pattern(key, pattern_key):
                    priority = p
                    break
            
            self.endpoints.append({
                "method": method,
                "path": path,
                "priority": priority,
                "key": key
            })
        
        return self.endpoints
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """Check if key matches pattern (supports wildcards)"""
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return key.startswith(prefix)
        return key == pattern


class TestAnalyzer:
    """Analyzes test coverage from test files"""
    
    def __init__(self, test_dir: Path):
        self.test_dir = test_dir
        self.tested_endpoints: Set[str] = set()
        
    def analyze_tests(self) -> Set[str]:
        """Extract tested endpoints from test files"""
        for test_file in self.test_dir.glob("test_api_server*.py"):
            self._parse_test_file(test_file)
        return self.tested_endpoints
    
    def _parse_test_file(self, file_path: Path):
        """Parse a single test file for endpoint references"""
        content = file_path.read_text()
        
        # Pattern to match client.get/post calls
        patterns = [
            r'client\.(get|post|put|delete)\(["\']([^"\']+)["\']',
            r'\.(get|post|put|delete)\s*\(\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                method = match.group(1).upper()
                path = match.group(2)
                key = f"{method}:{path}"
                self.tested_endpoints.add(key)


class CoverageReporter:
    """Generates coverage reports"""
    
    def __init__(self, endpoints: List[Dict], tested: Set[str]):
        self.endpoints = endpoints
        self.tested = tested
        self.timestamp = datetime.now()
        
    def generate_report(self) -> Dict:
        """Generate comprehensive coverage report"""
        by_priority = defaultdict(lambda: {"total": 0, "tested": 0, "endpoints": []})
        
        for ep in self.endpoints:
            p = ep["priority"]
            by_priority[p]["total"] += 1
            by_priority[p]["endpoints"].append(ep)
            
            if ep["key"] in self.tested:
                by_priority[p]["tested"] += 1
        
        total = len(self.endpoints)
        tested_count = sum(1 for ep in self.endpoints if ep["key"] in self.tested)
        
        return {
            "timestamp": self.timestamp.isoformat(),
            "summary": {
                "total_endpoints": total,
                "tested_endpoints": tested_count,
                "coverage_percent": round((tested_count / total * 100), 1) if total > 0 else 0,
                "missing": total - tested_count
            },
            "by_priority": {
                p: {
                    "total": data["total"],
                    "tested": data["tested"],
                    "coverage": round((data["tested"] / data["total"] * 100), 1) if data["total"] > 0 else 0,
                    "endpoints": [
                        {
                            "method": ep["method"],
                            "path": ep["path"],
                            "tested": ep["key"] in self.tested
                        }
                        for ep in data["endpoints"]
                    ]
                }
                for p, data in sorted(by_priority.items())
            }
        }
    
    def generate_markdown(self, report: Dict) -> str:
        """Generate Markdown report"""
        lines = []
        lines.append("# API Test Coverage Report")
        lines.append(f"\n**Generated:** {report['timestamp']}")
        lines.append(f"\n## Summary")
        lines.append(f"\n| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Endpoints | {report['summary']['total_endpoints']} |")
        lines.append(f"| Tested | {report['summary']['tested_endpoints']} |")
        lines.append(f"| Missing | {report['summary']['missing']} |")
        lines.append(f"| **Coverage** | **{report['summary']['coverage_percent']}%** |")
        
        lines.append(f"\n## Coverage by Priority")
        lines.append(f"\n| Priority | Total | Tested | Coverage |")
        lines.append(f"|----------|-------|--------|----------|")
        for p, data in report['by_priority'].items():
            emoji = {"P0": "🔴", "P1": "🟠", "P2": "🟡", "P3": "🟢"}.get(p, "⚪")
            lines.append(f"| {emoji} {p} | {data['total']} | {data['tested']} | {data['coverage']}% |")
        
        # Untested endpoints
        lines.append(f"\n## Untested Endpoints by Priority")
        for p in ["P0", "P1", "P2", "P3"]:
            if p not in report['by_priority']:
                continue
            untested = [ep for ep in report['by_priority'][p]['endpoints'] if not ep['tested']]
            if not untested:
                continue
            
            emoji = {"P0": "🔴", "P1": "🟠", "P2": "🟡", "P3": "🟢"}.get(p, "⚪")
            lines.append(f"\n### {emoji} {p} ({len(untested)} untested)")
            lines.append(f"\n| Method | Path |")
            lines.append(f"|--------|------|")
            for ep in untested:
                lines.append(f"| {ep['method']} | {ep['path']} |")
        
        # Recommendations
        lines.append(f"\n## Recommendations")
        p0_data = report['by_priority'].get('P0', {})
        p0_untested = [ep for ep in p0_data.get('endpoints', []) if not ep['tested']]
        
        if p0_untested:
            lines.append(f"\n### 🔴 P0 Critical (Add tests immediately)")
            lines.append(f"Priority 0 endpoints are critical for core functionality.")
            lines.append(f"Missing tests for: {len(p0_untested)} endpoints")
            for ep in p0_untested[:5]:
                lines.append(f"- {ep['method']} {ep['path']}")
            if len(p0_untested) > 5:
                lines.append(f"- ... and {len(p0_untested) - 5} more")
        
        lines.append(f"\n---")
        lines.append(f"*Report generated by CoverageReporter*")
        
        return "\n".join(lines)


def main():
    """Main entry point"""
    # Paths
    workspace = Path("/home/moco/workspace")
    api_file = workspace / "services" / "api_server.py"
    test_dir = workspace / "services"
    output_dir = workspace / "reports"
    output_dir.mkdir(exist_ok=True)
    
    # Analyze
    print("🔍 Analyzing API endpoints...")
    endpoint_analyzer = EndpointAnalyzer(api_file)
    endpoints = endpoint_analyzer.parse_endpoints()
    print(f"  Found {len(endpoints)} endpoints")
    
    print("🔍 Analyzing test coverage...")
    test_analyzer = TestAnalyzer(test_dir)
    tested = test_analyzer.analyze_tests()
    print(f"  Found {len(tested)} tested endpoints")
    
    print("📊 Generating report...")
    reporter = CoverageReporter(endpoints, tested)
    report = reporter.generate_report()
    markdown = reporter.generate_markdown(report)
    
    # Save reports
    json_file = output_dir / f"coverage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    md_file = output_dir / "coverage_report.md"
    
    json_file.write_text(json.dumps(report, indent=2))
    md_file.write_text(markdown)
    
    print(f"\n✅ Reports saved:")
    print(f"  JSON: {json_file}")
    print(f"  Markdown: {md_file}")
    print(f"\n📈 Coverage: {report['summary']['coverage_percent']}%")
    print(f"   ({report['summary']['tested_endpoints']}/{report['summary']['total_endpoints']} endpoints)")
    
    return report


if __name__ == "__main__":
    main()
