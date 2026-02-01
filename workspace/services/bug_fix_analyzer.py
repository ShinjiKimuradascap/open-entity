#!/usr/bin/env python3
"""
Bug Fix Analyzer Module

エラーログのパース、エラータイプ分類、スタックトレース解析を行うモジュール。
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """エラータイプの分類"""
    SYNTAX_ERROR = auto()
    RUNTIME_ERROR = auto()
    LOGIC_ERROR = auto()
    TYPE_ERROR = auto()
    VALUE_ERROR = auto()
    KEY_ERROR = auto()
    INDEX_ERROR = auto()
    ATTRIBUTE_ERROR = auto()
    IMPORT_ERROR = auto()
    MODULE_NOT_FOUND = auto()
    ZERO_DIVISION_ERROR = auto()
    FILE_NOT_FOUND_ERROR = auto()
    PERMISSION_ERROR = auto()
    TIMEOUT_ERROR = auto()
    CONNECTION_ERROR = auto()
    MEMORY_ERROR = auto()
    RECURSION_ERROR = auto()
    NOT_IMPLEMENTED_ERROR = auto()
    ASSERTION_ERROR = auto()
    CUSTOM_EXCEPTION = auto()
    UNKNOWN = auto()


class ErrorSeverity(Enum):
    """エラーの重要度"""
    CRITICAL = "critical"      # システム停止レベル
    HIGH = "high"              # 主要機能に影響
    MEDIUM = "medium"          # 一部機能に影響
    LOW = "low"                # 軽微な問題
    WARNING = "warning"        # 警告（エラーではないが注意が必要）


@dataclass
class StackFrame:
    """スタックフレーム情報"""
    file_path: str
    line_number: int
    function_name: str
    code_context: Optional[str] = None
    is_project_code: bool = False
    
    def __str__(self) -> str:
        ctx = f" | {self.code_context[:50]}..." if self.code_context else ""
        marker = " [PROJECT]" if self.is_project_code else ""
        return f"  File \"{self.file_path}\", line {self.line_number}, in {self.function_name}{marker}{ctx}"


@dataclass
class ErrorInfo:
    """解析されたエラー情報"""
    error_type: ErrorType
    error_message: str
    original_traceback: str
    stack_frames: List[StackFrame] = field(default_factory=list)
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    error_line: Optional[int] = None
    error_file: Optional[str] = None
    exception_class: Optional[str] = None
    context_lines: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "error_type": self.error_type.name,
            "error_message": self.error_message,
            "severity": self.severity.value,
            "error_line": self.error_line,
            "error_file": self.error_file,
            "exception_class": self.exception_class,
            "stack_frames": [
                {
                    "file": f.file_path,
                    "line": f.line_number,
                    "function": f.function_name,
                    "is_project": f.is_project_code
                }
                for f in self.stack_frames
            ],
            "metadata": self.metadata
        }


class ErrorPatternDatabase:
    """エラーパターンデータベース"""
    
    # Python標準エラーのパターン
    PYTHON_ERROR_PATTERNS: Dict[ErrorType, List[str]] = {
        ErrorType.SYNTAX_ERROR: [
            r"SyntaxError",
            r"IndentationError",
            r"TabError",
        ],
        ErrorType.TYPE_ERROR: [
            r"TypeError",
        ],
        ErrorType.VALUE_ERROR: [
            r"ValueError",
        ],
        ErrorType.KEY_ERROR: [
            r"KeyError",
        ],
        ErrorType.INDEX_ERROR: [
            r"IndexError",
        ],
        ErrorType.ATTRIBUTE_ERROR: [
            r"AttributeError",
        ],
        ErrorType.IMPORT_ERROR: [
            r"ImportError",
        ],
        ErrorType.MODULE_NOT_FOUND: [
            r"ModuleNotFoundError",
        ],
        ErrorType.ZERO_DIVISION_ERROR: [
            r"ZeroDivisionError",
        ],
        ErrorType.FILE_NOT_FOUND_ERROR: [
            r"FileNotFoundError",
        ],
        ErrorType.PERMISSION_ERROR: [
            r"PermissionError",
        ],
        ErrorType.TIMEOUT_ERROR: [
            r"TimeoutError",
            r"asyncio\.TimeoutError",
        ],
        ErrorType.CONNECTION_ERROR: [
            r"ConnectionError",
            r"ConnectionRefusedError",
            r"ConnectionResetError",
        ],
        ErrorType.MEMORY_ERROR: [
            r"MemoryError",
        ],
        ErrorType.RECURSION_ERROR: [
            r"RecursionError",
        ],
        ErrorType.NOT_IMPLEMENTED_ERROR: [
            r"NotImplementedError",
        ],
        ErrorType.ASSERTION_ERROR: [
            r"AssertionError",
        ],
    }
    
    # 重要度判定パターン
    SEVERITY_PATTERNS: Dict[ErrorSeverity, List[str]] = {
        ErrorSeverity.CRITICAL: [
            r"MemoryError",
            r"RecursionError",
            r"SystemExit",
            r"KeyboardInterrupt",
        ],
        ErrorSeverity.HIGH: [
            r"ConnectionError",
            r"PermissionError",
            r"ImportError",
            r"ModuleNotFoundError",
        ],
        ErrorSeverity.MEDIUM: [
            r"TypeError",
            r"ValueError",
            r"KeyError",
            r"IndexError",
            r"AttributeError",
        ],
        ErrorSeverity.LOW: [
            r"FileNotFoundError",
            r"TimeoutError",
        ],
    }


class BugFixAnalyzer:
    """バグ修正分析クラス"""
    
    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root) if project_root else None
        self.pattern_db = ErrorPatternDatabase()
        
    def analyze(self, error_log: str, source_code: Optional[str] = None) -> ErrorInfo:
        """
        エラーログを解析してエラー情報を抽出
        
        Args:
            error_log: エラーログ文字列
            source_code: 関連するソースコード（オプション）
            
        Returns:
            ErrorInfo: 解析されたエラー情報
        """
        logger.info("Starting error analysis...")
        
        # エラータイプを判定
        error_type = self._classify_error_type(error_log)
        
        # エラーメッセージを抽出
        error_message = self._extract_error_message(error_log)
        
        # スタックトレースを解析
        stack_frames = self._parse_stack_trace(error_log)
        
        # 重要度を判定
        severity = self._determine_severity(error_type, error_log)
        
        # エラー発生位置を特定
        error_line, error_file = self._locate_error(error_log, stack_frames)
        
        # 例外クラス名を抽出
        exception_class = self._extract_exception_class(error_log)
        
        # コンテキスト行を抽出（ソースコードがある場合）
        context_lines = []
        if source_code and error_line:
            context_lines = self._extract_context_lines(source_code, error_line)
        
        error_info = ErrorInfo(
            error_type=error_type,
            error_message=error_message,
            original_traceback=error_log,
            stack_frames=stack_frames,
            severity=severity,
            error_line=error_line,
            error_file=error_file,
            exception_class=exception_class,
            context_lines=context_lines,
            metadata=self._extract_metadata(error_log)
        )
        
        logger.info(f"Analysis complete: {error_type.name} at line {error_line}")
        return error_info
    
    def _classify_error_type(self, error_log: str) -> ErrorType:
        """エラーログからエラータイプを判定"""
        for error_type, patterns in self.pattern_db.PYTHON_ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_log):
                    return error_type
        return ErrorType.UNKNOWN
    
    def _extract_error_message(self, error_log: str) -> str:
        """エラーメッセージを抽出"""
        # 最後の行をエラーメッセージとして抽出
        lines = error_log.strip().split('\n')
        
        for line in reversed(lines):
            line = line.strip()
            # エラータイプ: メッセージ の形式を探す
            match = re.search(r'(\w+Error):\s*(.+)', line)
            if match:
                return match.group(2).strip()
            # または単純にメッセージ部分
            if line and not line.startswith('File ') and not line.startswith('Traceback'):
                return line
                
        return "Unknown error"
    
    def _parse_stack_trace(self, error_log: str) -> List[StackFrame]:
        """スタックトレースを解析してフレームリストを作成"""
        frames = []
        
        # Pythonスタックトレースのパターン
        # File "path", line N, in function_name
        pattern = r'File "([^"]+)", line (\d+), in (\w+)'
        
        for match in re.finditer(pattern, error_log):
            file_path = match.group(1)
            line_number = int(match.group(2))
            function_name = match.group(3)
            
            # プロジェクトコードかどうかを判定
            is_project = self._is_project_code(file_path)
            
            # コードコンテキストを抽出（可能な場合）
            code_context = None
            if is_project and self.project_root:
                code_context = self._get_code_context(file_path, line_number)
            
            frame = StackFrame(
                file_path=file_path,
                line_number=line_number,
                function_name=function_name,
                code_context=code_context,
                is_project_code=is_project
            )
            frames.append(frame)
        
        return frames
    
    def _is_project_code(self, file_path: str) -> bool:
        """パスがプロジェクトコードかどうかを判定"""
        if not self.project_root:
            # 標準ライブラリやサードパーティを除外
            excluded = ['site-packages', 'lib/python', '/usr/lib', 'venv', '.venv']
            return not any(ex in file_path for ex in excluded)
        
        try:
            path = Path(file_path)
            return self.project_root in path.parents or self.project_root == path.parent
        except:
            return False
    
    def _get_code_context(self, file_path: str, line_number: int, context: int = 2) -> Optional[str]:
        """指定行の周辺コードを取得"""
        try:
            full_path = self.project_root / file_path if self.project_root else Path(file_path)
            if not full_path.exists():
                return None
                
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            start = max(0, line_number - context - 1)
            end = min(len(lines), line_number + context)
            
            context_lines = lines[start:end]
            return ''.join(context_lines).strip()
        except Exception as e:
            logger.warning(f"Could not read code context: {e}")
            return None
    
    def _determine_severity(self, error_type: ErrorType, error_log: str) -> ErrorSeverity:
        """エラーの重要度を判定"""
        # エラータイプから重要度を判定
        for severity, patterns in self.pattern_db.SEVERITY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_log):
                    return severity
        
        # デフォルトはMEDIUM
        return ErrorSeverity.MEDIUM
    
    def _locate_error(self, error_log: str, stack_frames: List[StackFrame]) -> Tuple[Optional[int], Optional[str]]:
        """エラー発生位置を特定"""
        # スタックフレームからプロジェクトコードの最後のフレームを使用
        for frame in reversed(stack_frames):
            if frame.is_project_code:
                return frame.line_number, frame.file_path
        
        # プロジェクトコードがない場合は最後のフレーム
        if stack_frames:
            return stack_frames[-1].line_number, stack_frames[-1].file_path
            
        # パターンマッチで行番号を探す
        match = re.search(r'line (\d+)', error_log)
        if match:
            return int(match.group(1)), None
            
        return None, None
    
    def _extract_exception_class(self, error_log: str) -> Optional[str]:
        """例外クラス名を抽出"""
        match = re.search(r'(\w+Error):', error_log)
        if match:
            return match.group(1)
        return None
    
    def _extract_context_lines(self, source_code: str, error_line: int, context: int = 3) -> List[str]:
        """エラー行の周辺コードを抽出"""
        lines = source_code.split('\n')
        start = max(0, error_line - context - 1)
        end = min(len(lines), error_line + context)
        return lines[start:end]
    
    def _extract_metadata(self, error_log: str) -> Dict[str, Any]:
        """追加メタデータを抽出"""
        metadata = {}
        
        # タイムスタンプを探す
        timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})', error_log)
        if timestamp_match:
            metadata['timestamp'] = timestamp_match.group(1)
        
        # モジュール名を探す
        module_match = re.search(r'module\s+\'([^\']+)\'', error_log)
        if module_match:
            metadata['module'] = module_match.group(1)
        
        # 関数名を探す
        func_match = re.search(r'function\s+(\w+)', error_log)
        if func_match:
            metadata['function'] = func_match.group(1)
            
        return metadata


# 便利な関数インターフェース
def analyze_error(error_log: str, source_code: Optional[str] = None, 
                  project_root: Optional[str] = None) -> ErrorInfo:
    """
    エラーログを解析する便利関数
    
    Args:
        error_log: エラーログ文字列
        source_code: 関連するソースコード（オプション）
        project_root: プロジェクトルートパス（オプション）
        
    Returns:
        ErrorInfo: 解析されたエラー情報
    """
    analyzer = BugFixAnalyzer(project_root=project_root)
    return analyzer.analyze(error_log, source_code)
