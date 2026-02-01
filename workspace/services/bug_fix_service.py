#!/usr/bin/env python3
"""
Bug Fix Service - Integrated Bug Fix Module

エラーログ解析、根本原因分析、修正案生成を統合したサービスモジュール。
入力: エラーログ + コード
出力: 分析レポート + 修正案 + 修正コード
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from services.bug_fix_analyzer import BugFixAnalyzer, ErrorInfo, ErrorType, ErrorSeverity
from services.root_cause_analyzer import RootCauseAnalyzer, RootCause, RootCauseCategory
from services.fix_generator import FixGenerator, GeneratedFix, FixOption, FixStrategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BugFixReport:
    """バグ修正レポート"""
    original_error_log: str
    source_code: Optional[str]
    error_info: ErrorInfo
    root_causes: List[RootCause]
    generated_fix: GeneratedFix
    timestamp: datetime = field(default_factory=datetime.now)
    processing_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "processing_time_ms": self.processing_time_ms,
            "error_type": self.error_info.error_type.name,
            "error_message": self.error_info.error_message,
            "root_causes": [{"category": c.category.name, "confidence": c.confidence} for c in self.root_causes],
            "fix_options_count": len(self.generated_fix.fix_options),
        }
    
    def to_markdown(self) -> str:
        lines = [
            "# Bug Fix Analysis Report",
            f"Generated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Processing Time: {self.processing_time_ms:.2f}ms",
            "",
            "## Error Summary",
            f"- Type: {self.error_info.error_type.name}",
            f"- Message: {self.error_info.error_message}",
            f"- Location: {self.error_info.error_file or 'Unknown'}:{self.error_info.error_line or '?'}",
            "",
            "## Root Causes",
        ]
        for i, cause in enumerate(self.root_causes[:5], 1):
            lines.append(f"{i}. [{cause.category.name}] {cause.description} (confidence: {cause.confidence:.2f})")
        
        lines.extend(["", "## Fix Options"])
        for i, opt in enumerate(self.generated_fix.fix_options[:5], 1):
            marker = "(RECOMMENDED) " if i == self.generated_fix.recommended_option + 1 else ""
            lines.append(f"{i}. {marker}{opt.strategy.name}: {opt.description}")
        
        return "\n".join(lines)
    
    def get_fix_code(self, option_index: Optional[int] = None) -> str:
        if option_index is None:
            option_index = self.generated_fix.recommended_option
        if 0 <= option_index < len(self.generated_fix.fix_options):
            return self.generated_fix.fix_options[option_index].code_after
        return ""


class BugFixService:
    """バグ修正統合サービス"""
    
    def __init__(self, project_root: Optional[str] = None):
        self.analyzer = BugFixAnalyzer(project_root=project_root)
        self.root_cause_analyzer = RootCauseAnalyzer()
        self.fix_generator = FixGenerator()
        self.project_root = project_root
        
    def analyze_and_fix(self, error_log: str, 
                        source_code: Optional[str] = None,
                        file_path: Optional[str] = None) -> BugFixReport:
        import time
        start_time = time.time()
        
        logger.info("Starting bug fix analysis...")
        
        error_info = self.analyzer.analyze(error_log, source_code)
        
        code_context = source_code
        if not code_context and file_path and error_info.error_line:
            code_context = self._load_code_context(file_path, error_info.error_line)
        
        root_causes = self.root_cause_analyzer.analyze(error_info, code_context)
        generated_fix = self.fix_generator.generate(error_info, root_causes, code_context)
        
        processing_time = (time.time() - start_time) * 1000
        logger.info(f"Analysis complete in {processing_time:.2f}ms")
        
        return BugFixReport(
            original_error_log=error_log,
            source_code=source_code,
            error_info=error_info,
            root_causes=root_causes,
            generated_fix=generated_fix,
            processing_time_ms=processing_time
        )
    
    def _load_code_context(self, file_path: str, line_number: int, context_lines: int = 5) -> Optional[str]:
        try:
            path = Path(file_path)
            if not path.is_absolute() and self.project_root:
                path = Path(self.project_root) / path
            if not path.exists():
                return None
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            start = max(0, line_number - context_lines - 1)
            end = min(len(lines), line_number + context_lines)
            return ''.join(lines[start:end])
        except Exception as e:
            logger.warning(f"Could not load code context: {e}")
            return None


def analyze_bug(error_log: str, source_code: Optional[str] = None,
                file_path: Optional[str] = None, project_root: Optional[str] = None) -> BugFixReport:
    service = BugFixService(project_root=project_root)
    return service.analyze_and_fix(error_log, source_code, file_path)


def quick_fix(error_log: str, source_code: Optional[str] = None) -> Optional[str]:
    try:
        report = analyze_bug(error_log, source_code)
        return report.get_fix_code()
    except Exception as e:
        logger.error(f"Quick fix failed: {e}")
        return None


def example_usage():
    error_log = """
Traceback (most recent call last):
  File "app.py", line 42, in process_data
    result = user.get_profile()
  File "models.py", line 15, in get_profile
    return self.profile.name
AttributeError: 'NoneType' object has no attribute 'name'
"""
    source_code = """
class User:
    def __init__(self, profile=None):
        self.profile = profile
    def get_profile(self):
        return self.profile.name
"""
    report = analyze_bug(error_log, source_code)
    print("ERROR TYPE:", report.error_info.error_type.name)
    print("ROOT CAUSES:", [c.category.name for c in report.root_causes])
    print("FIX OPTIONS:", len(report.generated_fix.fix_options))
    print("BEST FIX:")
    print(report.get_fix_code())
    return report


if __name__ == "__main__":
    example_usage()
