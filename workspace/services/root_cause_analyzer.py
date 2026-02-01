#!/usr/bin/env python3
"""
Root Cause Analyzer Module

根本原因推定、エラーパターンデータベース、関連性分析を行うモジュール。
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

from services.bug_fix_analyzer import ErrorInfo, ErrorType, ErrorSeverity, StackFrame

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RootCauseCategory(Enum):
    """根本原因カテゴリ"""
    NULL_REFERENCE = auto()           # None参照
    TYPE_MISMATCH = auto()            # 型の不一致
    BOUNDARY_ERROR = auto()           # 境界値エラー
    RESOURCE_LEAK = auto()            # リソースリーク
    CONCURRENCY_ISSUE = auto()        # 並行処理問題
    CONFIGURATION_ERROR = auto()      # 設定エラー
    API_MISUSE = auto()               # APIの誤用
    LOGIC_FLAW = auto()               # 論理欠陥
    DATA_CORRUPTION = auto()          # データ破損
    EXTERNAL_DEPENDENCY = auto()      # 外部依存の問題
    TIMING_ISSUE = auto()             # タイミング問題
    INPUT_VALIDATION = auto()         # 入力検証不足
    STATE_MANAGEMENT = auto()         # 状態管理の問題
    UNKNOWN = auto()


@dataclass
class RootCause:
    """根本原因情報"""
    category: RootCauseCategory
    description: str
    confidence: float  # 0.0 - 1.0
    evidence: List[str] = field(default_factory=list)
    related_files: List[str] = field(default_factory=list)
    suggested_focus_areas: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        return f"[{self.category.name}] {self.description} (confidence: {self.confidence:.2f})"


@dataclass
class PatternMatch:
    """パターンマッチ結果"""
    pattern_name: str
    matched: bool
    confidence: float
    details: Dict[str, Any] = field(default_factory=dict)


class ErrorPatternDatabase:
    """
    エラーパターンデータベース
    
    よくあるエラーパターンとその根本原因のマッピングを管理
    """
    
    # エラーメッセージパターンと根本原因のマッピング
    ERROR_PATTERNS: Dict[RootCauseCategory, List[Dict[str, Any]]] = {
        RootCauseCategory.NULL_REFERENCE: [
            {
                "patterns": [r"NoneType", r"'None'", r"is None", r"was None"],
                "keywords": ["None", "null", "undefined"],
                "confidence": 0.9,
            }
        ],
        RootCauseCategory.TYPE_MISMATCH: [
            {
                "patterns": [r"expected.*got", r"cannot.*'str'.*'int'", r"must be.*not"],
                "keywords": ["type", "expected", "got", "cannot be"],
                "confidence": 0.85,
            }
        ],
        RootCauseCategory.BOUNDARY_ERROR: [
            {
                "patterns": [r"index out of range", r"list index", r"tuple index", r"string index"],
                "keywords": ["index", "range", "bounds", "length"],
                "confidence": 0.9,
            }
        ],
        RootCauseCategory.RESOURCE_LEAK: [
            {
                "patterns": [r"Too many open files", r"MemoryError", r"resource", r"leak"],
                "keywords": ["memory", "file", "resource", "connection", "pool"],
                "confidence": 0.8,
            }
        ],
        RootCauseCategory.CONCURRENCY_ISSUE: [
            {
                "patterns": [r"deadlock", r"race condition", r"lock", r"thread", r"asyncio"],
                "keywords": ["concurrent", "thread", "async", "race", "lock"],
                "confidence": 0.75,
            }
        ],
        RootCauseCategory.CONFIGURATION_ERROR: [
            {
                "patterns": [r"config", r"setting", r"environment", r"ENV", r"missing.*key"],
                "keywords": ["config", "setting", "env", "configuration"],
                "confidence": 0.8,
            }
        ],
        RootCauseCategory.API_MISUSE: [
            {
                "patterns": [r"takes.*positional arguments", r"missing.*required", r"unexpected keyword"],
                "keywords": ["argument", "parameter", "missing", "required"],
                "confidence": 0.85,
            }
        ],
        RootCauseCategory.LOGIC_FLAW: [
            {
                "patterns": [r"AssertionError", r"assert", r"invariant"],
                "keywords": ["assert", "logic", "condition", "invariant"],
                "confidence": 0.7,
            }
        ],
        RootCauseCategory.DATA_CORRUPTION: [
            {
                "patterns": [r"corrupt", r"invalid.*data", r"malformed", r"parse"],
                "keywords": ["corrupt", "invalid", "parse", "format"],
                "confidence": 0.75,
            }
        ],
        RootCauseCategory.EXTERNAL_DEPENDENCY: [
            {
                "patterns": [r"Connection", r"Timeout", r"Network", r"HTTP", r"API"],
                "keywords": ["connection", "network", "timeout", "external", "service"],
                "confidence": 0.8,
            }
        ],
        RootCauseCategory.INPUT_VALIDATION: [
            {
                "patterns": [r"invalid.*input", r"validation", r"sanitize", r"escape"],
                "keywords": ["input", "validation", "sanitize", "check"],
                "confidence": 0.75,
            }
        ],
        RootCauseCategory.STATE_MANAGEMENT: [
            {
                "patterns": [r"state", r"initialized", r"closed", r"not ready"],
                "keywords": ["state", "init", "ready", "status"],
                "confidence": 0.7,
            }
        ],
    }
    
    # エラータイプと根本原因の相関関係
    TYPE_TO_CAUSE: Dict[ErrorType, List[RootCauseCategory]] = {
        ErrorType.TYPE_ERROR: [RootCauseCategory.TYPE_MISMATCH, RootCauseCategory.API_MISUSE],
        ErrorType.VALUE_ERROR: [RootCauseCategory.INPUT_VALIDATION, RootCauseCategory.LOGIC_FLAW],
        ErrorType.KEY_ERROR: [RootCauseCategory.NULL_REFERENCE, RootCauseCategory.DATA_CORRUPTION],
        ErrorType.INDEX_ERROR: [RootCauseCategory.BOUNDARY_ERROR],
        ErrorType.ATTRIBUTE_ERROR: [RootCauseCategory.NULL_REFERENCE, RootCauseCategory.TYPE_MISMATCH],
        ErrorType.FILE_NOT_FOUND_ERROR: [RootCauseCategory.CONFIGURATION_ERROR, RootCauseCategory.EXTERNAL_DEPENDENCY],
        ErrorType.PERMISSION_ERROR: [RootCauseCategory.CONFIGURATION_ERROR],
        ErrorType.CONNECTION_ERROR: [RootCauseCategory.EXTERNAL_DEPENDENCY],
        ErrorType.TIMEOUT_ERROR: [RootCauseCategory.EXTERNAL_DEPENDENCY, RootCauseCategory.CONCURRENCY_ISSUE],
        ErrorType.MEMORY_ERROR: [RootCauseCategory.RESOURCE_LEAK],
        ErrorType.IMPORT_ERROR: [RootCauseCategory.CONFIGURATION_ERROR, RootCauseCategory.EXTERNAL_DEPENDENCY],
        ErrorType.MODULE_NOT_FOUND: [RootCauseCategory.CONFIGURATION_ERROR],
        ErrorType.ZERO_DIVISION_ERROR: [RootCauseCategory.LOGIC_FLAW, RootCauseCategory.INPUT_VALIDATION],
        ErrorType.ASSERTION_ERROR: [RootCauseCategory.LOGIC_FLAW],
    }


class RootCauseAnalyzer:
    """根本原因分析クラス"""
    
    def __init__(self):
        self.pattern_db = ErrorPatternDatabase()
        self.analysis_history: List[Dict[str, Any]] = []
        
    def analyze(self, error_info: ErrorInfo, 
                code_context: Optional[str] = None,
                related_errors: Optional[List[ErrorInfo]] = None) -> List[RootCause]:
        """
        エラー情報から根本原因を推定
        
        Args:
            error_info: 解析済みエラー情報
            code_context: エラー発生箇所のコードコンテキスト
            related_errors: 関連する過去のエラー（パターン分析用）
            
        Returns:
            List[RootCause]: 推定された根本原因リスト（信頼度順）
        """
        logger.info(f"Analyzing root cause for {error_info.error_type.name}...")
        
        causes = []
        
        # 1. エラータイプから根本原因を推定
        type_causes = self._analyze_by_error_type(error_info)
        causes.extend(type_causes)
        
        # 2. メッセージパターンマッチング
        pattern_causes = self._analyze_by_pattern(error_info)
        causes.extend(pattern_causes)
        
        # 3. スタックトレース分析
        stack_causes = self._analyze_stack_trace(error_info)
        causes.extend(stack_causes)
        
        # 4. コードコンテキスト分析
        if code_context:
            context_causes = self._analyze_code_context(error_info, code_context)
            causes.extend(context_causes)
        
        # 5. 関連エラー分析
        if related_errors:
            related_causes = self._analyze_related_errors(error_info, related_errors)
            causes.extend(related_causes)
        
        # 重複を除去して統合
        merged_causes = self._merge_similar_causes(causes)
        
        # 信頼度順にソート
        merged_causes.sort(key=lambda x: x.confidence, reverse=True)
        
        # 履歴に記録
        self.analysis_history.append({
            "error_info": error_info,
            "causes": merged_causes,
            "timestamp": logging.getLogger().handlers[0].baseFilename if logging.getLogger().handlers else None
        })
        
        logger.info(f"Root cause analysis complete: {len(merged_causes)} causes identified")
        return merged_causes
    
    def _analyze_by_error_type(self, error_info: ErrorInfo) -> List[RootCause]:
        """エラータイプから根本原因を推定"""
        causes = []
        
        if error_info.error_type in self.pattern_db.TYPE_TO_CAUSE:
            categories = self.pattern_db.TYPE_TO_CAUSE[error_info.error_type]
            for category in categories:
                cause = RootCause(
                    category=category,
                    description=f"Inferred from error type: {error_info.error_type.name}",
                    confidence=0.7,
                    evidence=[f"Error type {error_info.error_type.name} commonly maps to {category.name}"]
                )
                causes.append(cause)
        
        return causes
    
    def _analyze_by_pattern(self, error_info: ErrorInfo) -> List[RootCause]:
        """エラーメッセージのパターンマッチング"""
        causes = []
        error_message = error_info.error_message.lower()
        
        for category, patterns in self.pattern_db.ERROR_PATTERNS.items():
            for pattern_group in patterns:
                # 正規表現パターンマッチング
                regex_matches = []
                for pattern in pattern_group["patterns"]:
                    if re.search(pattern, error_message, re.IGNORECASE):
                        regex_matches.append(pattern)
                
                # キーワードマッチング
                keyword_matches = []
                for keyword in pattern_group["keywords"]:
                    if keyword.lower() in error_message:
                        keyword_matches.append(keyword)
                
                # マッチがあれば根本原因として追加
                if regex_matches or keyword_matches:
                    confidence = pattern_group["confidence"]
                    # マッチ数に応じて信頼度調整
                    confidence += min(0.1 * (len(regex_matches) + len(keyword_matches)), 0.1)
                    confidence = min(confidence, 1.0)
                    
                    evidence = []
                    if regex_matches:
                        evidence.append(f"Regex patterns matched: {regex_matches}")
                    if keyword_matches:
                        evidence.append(f"Keywords matched: {keyword_matches}")
                    
                    cause = RootCause(
                        category=category,
                        description=f"Pattern match in error message",
                        confidence=confidence,
                        evidence=evidence
                    )
                    causes.append(cause)
        
        return causes
    
    def _analyze_stack_trace(self, error_info: ErrorInfo) -> List[RootCause]:
        """スタックトレースから根本原因を推定"""
        causes = []
        
        if not error_info.stack_frames:
            return causes
        
        # プロジェクトコードのフレームに焦点
        project_frames = [f for f in error_info.stack_frames if f.is_project_code]
        
        if project_frames:
            # 最後のプロジェクトフレームがエラー発生箇所
            last_frame = project_frames[-1]
            
            # ファイル名から推定
            file_indicators = {
                "config": RootCauseCategory.CONFIGURATION_ERROR,
                "settings": RootCauseCategory.CONFIGURATION_ERROR,
                "database": RootCauseCategory.EXTERNAL_DEPENDENCY,
                "db": RootCauseCategory.EXTERNAL_DEPENDENCY,
                "api": RootCauseCategory.API_MISUSE,
                "client": RootCauseCategory.EXTERNAL_DEPENDENCY,
                "concurrent": RootCauseCategory.CONCURRENCY_ISSUE,
                "async": RootCauseCategory.CONCURRENCY_ISSUE,
                "thread": RootCauseCategory.CONCURRENCY_ISSUE,
                "cache": RootCauseCategory.STATE_MANAGEMENT,
                "session": RootCauseCategory.STATE_MANAGEMENT,
            }
            
            file_lower = last_frame.file_path.lower()
            for indicator, category in file_indicators.items():
                if indicator in file_lower:
                    causes.append(RootCause(
                        category=category,
                        description=f"Inferred from file name: {last_frame.file_path}",
                        confidence=0.6,
                        evidence=[f"File path contains '{indicator}'"],
                        related_files=[last_frame.file_path]
                    ))
            
            # 関数名から推定
            func_indicators = {
                "init": RootCauseCategory.STATE_MANAGEMENT,
                "close": RootCauseCategory.STATE_MANAGEMENT,
                "connect": RootCauseCategory.EXTERNAL_DEPENDENCY,
                "send": RootCauseCategory.EXTERNAL_DEPENDENCY,
                "receive": RootCauseCategory.EXTERNAL_DEPENDENCY,
                "parse": RootCauseCategory.DATA_CORRUPTION,
                "validate": RootCauseCategory.INPUT_VALIDATION,
                "format": RootCauseCategory.DATA_CORRUPTION,
            }
            
            func_lower = last_frame.function_name.lower()
            for indicator, category in func_indicators.items():
                if indicator in func_lower:
                    causes.append(RootCause(
                        category=category,
                        description=f"Inferred from function name: {last_frame.function_name}",
                        confidence=0.55,
                        evidence=[f"Function name contains '{indicator}'"],
                        related_files=[last_frame.file_path]
                    ))
        
        return causes
    
    def _analyze_code_context(self, error_info: ErrorInfo, 
                              code_context: str) -> List[RootCause]:
        """コードコンテキストから根本原因を推定"""
        causes = []
        code_lower = code_context.lower()
        
        # Noneチェックの欠如を検出
        if error_info.error_type in [ErrorType.ATTRIBUTE_ERROR, ErrorType.TYPE_ERROR]:
            if "if " not in code_lower and "None" not in code_context:
                causes.append(RootCause(
                    category=RootCauseCategory.NULL_REFERENCE,
                    description="Possible missing null check",
                    confidence=0.65,
                    evidence=["No explicit null check found in context"],
                    suggested_focus_areas=["Add null check before accessing attributes"]
                ))
        
        # 境界チェックの欠如を検出
        if error_info.error_type == ErrorType.INDEX_ERROR:
            if "len(" not in code_lower and "length" not in code_lower:
                causes.append(RootCause(
                    category=RootCauseCategory.BOUNDARY_ERROR,
                    description="Missing bounds check",
                    confidence=0.7,
                    evidence=["No length check found before indexing"],
                    suggested_focus_areas=["Add bounds check before array access"]
                ))
        
        # 型変換の問題を検出
        if error_info.error_type == ErrorType.VALUE_ERROR:
            conversion_patterns = [r"int\(", r"float\(", r"str\(", r"bool\("]
            for pattern in conversion_patterns:
                if re.search(pattern, code_context):
                    causes.append(RootCause(
                        category=RootCauseCategory.TYPE_MISMATCH,
                        description="Type conversion issue",
                        confidence=0.75,
                        evidence=[f"Type conversion pattern found: {pattern}"],
                        suggested_focus_areas=["Add try-except for type conversion", "Validate input before conversion"]
                    ))
                    break
        
        # リソース管理の問題を検出
        resource_patterns = ["open(", "socket", "connection", "pool"]
        for pattern in resource_patterns:
            if pattern in code_lower:
                if "with " not in code_lower and "try:" not in code_lower:
                    causes.append(RootCause(
                        category=RootCauseCategory.RESOURCE_LEAK,
                        description="Possible resource management issue",
                        confidence=0.6,
                        evidence=[f"Resource operation '{pattern}' without proper handling"],
                        suggested_focus_areas=["Use context managers (with statement)", "Add try-finally blocks"]
                    ))
                    break
        
        return causes
    
    def _analyze_related_errors(self, error_info: ErrorInfo,
                                related_errors: List[ErrorInfo]) -> List[RootCause]:
        """関連エラーからパターンを分析"""
        causes = []
        
        # 同じエラータイプの頻度を分析
        type_count = defaultdict(int)
        file_count = defaultdict(int)
        
        for err in related_errors:
            type_count[err.error_type] += 1
            if err.error_file:
                file_count[err.error_file] += 1
        
        # 頻発エラーの検出
        total = len(related_errors)
        for err_type, count in type_count.items():
            if count / total > 0.3:  # 30%以上が同じエラー
                causes.append(RootCause(
                    category=RootCauseCategory.LOGIC_FLAW,
                    description=f"Recurring error pattern: {err_type.name}",
                    confidence=min(0.5 + (count / total) * 0.3, 0.9),
                    evidence=[f"{count}/{total} errors are {err_type.name}"],
                    suggested_focus_areas=["Review common code path", "Add comprehensive error handling"]
                ))
        
        # 特定ファイルでの頻発を検出
        for file_path, count in file_count.items():
            if count / total > 0.3:
                causes.append(RootCause(
                    category=RootCauseCategory.LOGIC_FLAW,
                    description=f"Problematic file identified: {file_path}",
                    confidence=min(0.6 + (count / total) * 0.2, 0.8),
                    evidence=[f"{count}/{total} errors originate from {file_path}"],
                    related_files=[file_path],
                    suggested_focus_areas=["Refactor the problematic file", "Add unit tests"]
                ))
        
        return causes
    
    def _merge_similar_causes(self, causes: List[RootCause]) -> List[RootCause]:
        """類似した根本原因を統合"""
        merged: Dict[RootCauseCategory, RootCause] = {}
        
        for cause in causes:
            if cause.category in merged:
                existing = merged[cause.category]
                # 信頼度を上昇させる（上限0.95）
                existing.confidence = min(existing.confidence + cause.confidence * 0.2, 0.95)
                # 証拠を統合
                existing.evidence.extend(cause.evidence)
                existing.evidence = list(set(existing.evidence))  # 重複除去
                # 関連ファイルを統合
                existing.related_files.extend(cause.related_files)
                existing.related_files = list(set(existing.related_files))
                # 提案領域を統合
                if cause.suggested_focus_areas:
                    existing.suggested_focus_areas.extend(cause.suggested_focus_areas)
                    existing.suggested_focus_areas = list(set(existing.suggested_focus_areas))
            else:
                merged[cause.category] = cause
        
        return list(merged.values())
    
    def get_analysis_summary(self, causes: List[RootCause]) -> Dict[str, Any]:
        """分析結果のサマリーを生成"""
        if not causes:
            return {
                "primary_cause": None,
                "confidence": 0.0,
                "categories": [],
                "recommendation": "No root cause identified"
            }
        
        primary = causes[0]
        
        return {
            "primary_cause": {
                "category": primary.category.name,
                "description": primary.description,
                "confidence": primary.confidence
            },
            "all_categories": [c.category.name for c in causes],
            "avg_confidence": sum(c.confidence for c in causes) / len(causes),
            "total_causes": len(causes),
            "focus_areas": [area for c in causes for area in c.suggested_focus_areas]
        }


# 便利な関数インターフェース
def analyze_root_cause(error_info: ErrorInfo,
                       code_context: Optional[str] = None,
                       related_errors: Optional[List[ErrorInfo]] = None) -> List[RootCause]:
    """
    根本原因を分析する便利関数
    
    Args:
        error_info: 解析済みエラー情報
        code_context: エラー発生箇所のコードコンテキスト
        related_errors: 関連する過去のエラー
        
    Returns:
        List[RootCause]: 推定された根本原因リスト
    """
    analyzer = RootCauseAnalyzer()
    return analyzer.analyze(error_info, code_context, related_errors)
