#!/usr/bin/env python3
"""
Fix Generator Module

修正案の生成、複数オプション提示、修正コード生成を行うモジュール。
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any
from textwrap import dedent

from services.bug_fix_analyzer import ErrorInfo, ErrorType, ErrorSeverity
from services.root_cause_analyzer import RootCause, RootCauseCategory

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FixStrategy(Enum):
    """修正戦略"""
    ADD_NULL_CHECK = auto()
    ADD_TYPE_CHECK = auto()
    ADD_BOUNDS_CHECK = auto()
    ADD_EXCEPTION_HANDLING = auto()
    ADD_VALIDATION = auto()
    ADD_RESOURCE_MANAGEMENT = auto()
    FIX_TYPE_CONVERSION = auto()
    FIX_LOGIC = auto()
    ADD_IMPORT = auto()
    UPDATE_CONFIGURATION = auto()
    ADD_RETRY_LOGIC = auto()
    REFACTOR_CODE = auto()
    ADD_LOGGING = auto()
    CUSTOM_FIX = auto()


@dataclass
class FixOption:
    """修正オプション"""
    strategy: FixStrategy
    description: str
    code_before: str
    code_after: str
    confidence: float
    estimated_effort: str  # "low", "medium", "high"
    side_effects: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        return f"[{self.strategy.name}] {self.description} (effort: {self.estimated_effort})"


@dataclass
class GeneratedFix:
    """生成された修正"""
    original_error: ErrorInfo
    root_causes: List[RootCause]
    fix_options: List[FixOption]
    recommended_option: int  # 推奨オプションのインデックス
    explanation: str
    test_suggestions: List[str] = field(default_factory=list)
    
    def get_best_fix(self) -> FixOption:
        """最良の修正オプションを取得"""
        if 0 <= self.recommended_option < len(self.fix_options):
            return self.fix_options[self.recommended_option]
        return self.fix_options[0] if self.fix_options else None


class FixTemplateDatabase:
    """修正テンプレートデータベース"""
    
    # エラータイプごとの修正テンプレート
    TEMPLATES: Dict[Tuple[ErrorType, RootCauseCategory], List[Dict[str, Any]]] = {
        (ErrorType.ATTRIBUTE_ERROR, RootCauseCategory.NULL_REFERENCE): [
            {
                "strategy": FixStrategy.ADD_NULL_CHECK,
                "template": '''
# Before
{line}

# After
if {var} is not None:
    {line}
else:
    # Handle None case
    {default_action}
''',
                "effort": "low",
                "confidence": 0.9
            },
            {
                "strategy": FixStrategy.ADD_NULL_CHECK,
                "template": '''
# Before
{line}

# After
if {var} is None:
    {var} = {default_value}
{line}
''',
                "effort": "low",
                "confidence": 0.85
            }
        ],
        (ErrorType.TYPE_ERROR, RootCauseCategory.TYPE_MISMATCH): [
            {
                "strategy": FixStrategy.ADD_TYPE_CHECK,
                "template": '''
# Before
{line}

# After
if isinstance({var}, {expected_type}):
    {line}
else:
    # Handle type mismatch
    {var} = {conversion_code}
    {line}
''',
                "effort": "medium",
                "confidence": 0.85
            },
            {
                "strategy": FixStrategy.ADD_TYPE_CHECK,
                "template": '''
# Before
{line}

# After
def ensure_{type_name}(value):
    if not isinstance(value, {expected_type}):
        return {conversion_code}
    return value

{var} = ensure_{type_name}({var})
{line}
''',
                "effort": "medium",
                "confidence": 0.8
            }
        ],
        (ErrorType.INDEX_ERROR, RootCauseCategory.BOUNDARY_ERROR): [
            {
                "strategy": FixStrategy.ADD_BOUNDS_CHECK,
                "template": '''
# Before
{line}

# After
if {index_var} < len({array_var}) and {index_var} >= 0:
    {line}
else:
    # Handle out of bounds
    {default_action}
''',
                "effort": "low",
                "confidence": 0.9
            },
            {
                "strategy": FixStrategy.ADD_BOUNDS_CHECK,
                "template": '''
# Before
{line}

# After
try:
    {line}
except IndexError:
    # Handle index error gracefully
    {default_action}
''',
                "effort": "low",
                "confidence": 0.85
            }
        ],
        (ErrorType.KEY_ERROR, RootCauseCategory.NULL_REFERENCE): [
            {
                "strategy": FixStrategy.ADD_VALIDATION,
                "template": '''
# Before
{line}

# After
if {key} in {dict_var}:
    {line}
else:
    # Handle missing key
    {default_action}
''',
                "effort": "low",
                "confidence": 0.9
            },
            {
                "strategy": FixStrategy.ADD_VALIDATION,
                "template": '''
# Before
{line}

# After
{dict_var}.get({key}, {default_value})
''',
                "effort": "low",
                "confidence": 0.85
            }
        ],
        (ErrorType.VALUE_ERROR, RootCauseCategory.INPUT_VALIDATION): [
            {
                "strategy": FixStrategy.ADD_VALIDATION,
                "template": '''
# Before
{line}

# After
if {validation_condition}:
    {line}
else:
    raise ValueError(f"Invalid value for {var}: {{{var}}}")
''',
                "effort": "low",
                "confidence": 0.85
            }
        ],
        (ErrorType.FILE_NOT_FOUND_ERROR, RootCauseCategory.CONFIGURATION_ERROR): [
            {
                "strategy": FixStrategy.ADD_EXCEPTION_HANDLING,
                "template": '''
# Before
{line}

# After
import os

file_path = {file_path}
if os.path.exists(file_path):
    {line}
else:
    # Handle missing file
    raise FileNotFoundError(f"Required file not found: {{file_path}}")
''',
                "effort": "low",
                "confidence": 0.85
            }
        ],
        (ErrorType.CONNECTION_ERROR, RootCauseCategory.EXTERNAL_DEPENDENCY): [
            {
                "strategy": Add_RETRY_LOGIC,
                "template": '''
# Before
{line}

# After
import time
from functools import wraps

def retry_on_connection_error(max_retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ConnectionError:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))
            return None
        return wrapper
    return decorator

@retry_on_connection_error()
def {func_name}():
    {line}
''',
                "effort": "medium",
                "confidence": 0.8
            }
        ],
    }
    
    # 一般的な修正パターン
    GENERAL_FIXES: Dict[ErrorType, List[Dict[str, Any]]] = {
        ErrorType.IMPORT_ERROR: [
            {
                "strategy": FixStrategy.ADD_IMPORT,
                "template": "pip install {module_name}",
                "description": "Install missing package",
                "effort": "low",
                "confidence": 0.9
            }
        ],
        ErrorType.MODULE_NOT_FOUND: [
            {
                "strategy": FixStrategy.ADD_IMPORT,
                "template": "pip install {module_name}",
                "description": "Install missing module",
                "effort": "low",
                "confidence": 0.9
            }
        ],
        ErrorType.ZERO_DIVISION_ERROR: [
            {
                "strategy": FixStrategy.ADD_VALIDATION,
                "template": '''
# Before
{line}

# After
if {divisor} != 0:
    {line}
else:
    # Handle division by zero
    {default_action}
''',
                "description": "Add zero check before division",
                "effort": "low",
                "confidence": 0.95
            }
        ],
    }


class FixGenerator:
    """修正生成クラス"""
    
    def __init__(self):
        self.template_db = FixTemplateDatabase()
        
    def generate(self, error_info: ErrorInfo, 
                 root_causes: List[RootCause],
                 code_context: Optional[str] = None) -> GeneratedFix:
        """
        修正案を生成
        
        Args:
            error_info: エラー情報
            root_causes: 根本原因リスト
            code_context: エラー発生箇所のコード
            
        Returns:
            GeneratedFix: 生成された修正案
        """
        logger.info(f"Generating fixes for {error_info.error_type.name}...")
        
        fix_options = []
        
        # 1. 根本原因に基づく修正を生成
        for cause in root_causes:
            options = self._generate_for_cause(error_info, cause, code_context)
            fix_options.extend(options)
        
        # 2. エラータイプに基づく一般的な修正を生成
        general_options = self._generate_general_fixes(error_info, code_context)
        fix_options.extend(general_options)
        
        # 3. コードコンテキストに基づく修正を生成
        if code_context:
            context_options = self._generate_contextual_fixes(error_info, code_context)
            fix_options.extend(context_options)
        
        # 重複除去とソート
        fix_options = self._deduplicate_and_sort(fix_options)
        
        # 推奨オプションを決定
        recommended = self._select_recommended(fix_options)
        
        # テスト提案を生成
        test_suggestions = self._generate_test_suggestions(error_info, root_causes)
        
        generated = GeneratedFix(
            original_error=error_info,
            root_causes=root_causes,
            fix_options=fix_options,
            recommended_option=recommended,
            explanation=self._generate_explanation(error_info, root_causes, fix_options),
            test_suggestions=test_suggestions
        )
        
        logger.info(f"Generated {len(fix_options)} fix options")
        return generated
    
    def _generate_for_cause(self, error_info: ErrorInfo, 
                            cause: RootCause,
                            code_context: Optional[str]) -> List[FixOption]:
        """特定の根本原因に対する修正を生成"""
        options = []
        
        # テンプレートを検索
        key = (error_info.error_type, cause.category)
        if key in self.template_db.TEMPLATES:
            templates = self.template_db.TEMPLATES[key]
            for tmpl in templates:
                # テンプレートからコードを生成
                code_before, code_after = self._apply_template(
                    tmpl["template"], error_info, code_context
                )
                
                option = FixOption(
                    strategy=tmpl["strategy"],
                    description=cause.description,
                    code_before=code_before,
                    code_after=code_after,
                    confidence=tmpl["confidence"] * cause.confidence,
                    estimated_effort=tmpl["effort"]
                )
                options.append(option)
        
        return options
    
    def _generate_general_fixes(self, error_info: ErrorInfo,
                                code_context: Optional[str]) -> List[FixOption]:
        """一般的な修正オプションを生成"""
        options = []
        
        if error_info.error_type in self.template_db.GENERAL_FIXES:
            fixes = self.template_db.GENERAL_FIXES[error_info.error_type]
            for fix in fixes:
                code_before = code_context if code_context else "# Original code"
                code_after = self._interpolate_template(
                    fix["template"], error_info, code_context
                )
                
                option = FixOption(
                    strategy=fix["strategy"],
                    description=fix["description"],
                    code_before=code_before,
                    code_after=code_after,
                    confidence=fix["confidence"],
                    estimated_effort=fix["effort"]
                )
                options.append(option)
        
        return options
    
    def _generate_contextual_fixes(self, error_info: ErrorInfo,
                                   code_context: str) -> List[FixOption]:
        """コードコンテキストに基づく修正を生成"""
        options = []
        
        # try-exceptブロックの追加提案
        if error_info.error_type not in [ErrorType.SYNTAX_ERROR]:
            code_before = code_context
            
            # インデントを検出
            lines = code_context.strip().split('\n')
            if lines:
                first_line = lines[0]
                indent = len(first_line) - len(first_line.lstrip())
                base_indent = ' ' * indent
                inner_indent = ' ' * (indent + 4)
                
                exception_class = error_info.exception_class or "Exception"
                
                code_after = f'''{base_indent}try:
{inner_indent}{code_context.strip()}
{base_indent}except {exception_class} as e:
{inner_indent}# Handle {error_info.error_type.name}
{inner_indent}logger.error(f"{error_info.error_type.name}: {{e}}")
{inner_indent}{self._get_default_action(error_info)}
'''
                
                option = FixOption(
                    strategy=FixStrategy.ADD_EXCEPTION_HANDLING,
                    description=f"Wrap with try-except for {error_info.error_type.name}",
                    code_before=code_before,
                    code_after=code_after,
                    confidence=0.7,
                    estimated_effort="low",
                    side_effects=["May hide other exceptions if too broad"]
                )
                options.append(option)
        
        return options
    
    def _apply_template(self, template: str, error_info: ErrorInfo,
                        code_context: Optional[str]) -> Tuple[str, str]:
        """テンプレートを適用してコードを生成"""
        code_before = code_context if code_context else "# Error line"
        
        # プレースホルダーの置換
        placeholders = {
            "line": code_before.strip() if code_before else "# TODO: Error line",
            "var": self._extract_variable(code_context) if code_context else "value",
            "default_action": self._get_default_action(error_info),
            "default_value": "None",
            "expected_type": "str",
            "conversion_code": "str(value)",
            "type_name": "string",
            "index_var": "i",
            "array_var": "items",
            "key": "'key'",
            "dict_var": "data",
            "validation_condition": "value is not None",
            "file_path": "'path/to/file'",
            "func_name": "function_name",
            "module_name": error_info.metadata.get("module", "module_name"),
            "divisor": "divisor",
        }
        
        try:
            code_after = template.format(**placeholders)
        except KeyError as e:
            logger.warning(f"Template placeholder missing: {e}")
            code_after = template
        
        return code_before, dedent(code_after).strip()
    
    def _interpolate_template(self, template: str, error_info: ErrorInfo,
                              code_context: Optional[str]) -> str:
        """テンプレート文字列を補間"""
        module = error_info.metadata.get("module", "package_name")
        return template.format(module_name=module)
    
    def _extract_variable(self, code_context: Optional[str]) -> str:
        """コードから変数名を抽出"""
        if not code_context:
            return "value"
        
        # ドット表記から変数を抽出 (e.g., obj.attr -> obj)
        match = re.search(r'(\w+)\.', code_context)
        if match:
            return match.group(1)
        
        # 代入文から変数を抽出
        match = re.search(r'(\w+)\s*=', code_context)
        if match:
            return match.group(1)
        
        return "value"
    
    def _get_default_action(self, error_info: ErrorInfo) -> str:
        """エラータイプに応じたデフォルトアクションを返す"""
        actions = {
            ErrorType.ATTRIBUTE_ERROR: "return None",
            ErrorType.KEY_ERROR: "return {}",
            ErrorType.INDEX_ERROR: "return None",
            ErrorType.TYPE_ERROR: "raise TypeError('Invalid type')",
            ErrorType.VALUE_ERROR: "raise ValueError('Invalid value')",
            ErrorType.FILE_NOT_FOUND_ERROR: "raise FileNotFoundError('File not found')",
            ErrorType.CONNECTION_ERROR: "raise ConnectionError('Connection failed')",
            ErrorType.ZERO_DIVISION_ERROR: "return 0",
        }
        return actions.get(error_info.error_type, "pass")
    
    def _deduplicate_and_sort(self, options: List[FixOption]) -> List[FixOption]:
        """重複除去とソート"""
        seen = set()
        unique = []
        
        for opt in options:
            key = (opt.strategy, opt.description)
            if key not in seen:
                seen.add(key)
                unique.append(opt)
        
        # 信頼度の高い順、努力の低い順にソート
        unique.sort(key=lambda x: (x.confidence, -ord(x.estimated_effort[0])), reverse=True)
        
        return unique
    
    def _select_recommended(self, options: List[FixOption]) -> int:
        """推奨オプションを選択"""
        if not options:
            return 0
        
        # 信頼度が最も高く、努力が最も低いオプションを選択
        best_score = -1
        best_index = 0
        
        for i, opt in enumerate(options):
            effort_score = {"low": 1.0, "medium": 0.7, "high": 0.4}.get(opt.estimated_effort, 0.5)
            score = opt.confidence * effort_score
            
            if score > best_score:
                best_score = score
                best_index = i
        
        return best_index
    
    def _generate_test_suggestions(self, error_info: ErrorInfo,
                                   root_causes: List[RootCause]) -> List[str]:
        """テストケースの提案を生成"""
        suggestions = []
        
        # エラータイプに応じたテスト
        if error_info.error_type in [ErrorType.ATTRIBUTE_ERROR, ErrorType.TYPE_ERROR]:
            suggestions.append(f"Test with None value for {error_info.error_file}")
            suggestions.append("Test with invalid type input")
        
        if error_info.error_type == ErrorType.INDEX_ERROR:
            suggestions.append("Test with empty list")
            suggestions.append("Test with index out of bounds")
            suggestions.append("Test with negative index")
        
        if error_info.error_type == ErrorType.KEY_ERROR:
            suggestions.append("Test with missing key in dictionary")
            suggestions.append("Test with empty dictionary")
        
        if error_info.error_type == ErrorType.VALUE_ERROR:
            suggestions.append("Test with boundary values")
            suggestions.append("Test with invalid format input")
        
        # 根本原因に応じたテスト
        for cause in root_causes:
            if cause.category == RootCauseCategory.NULL_REFERENCE:
                suggestions.append("Add null/None input tests")
            if cause.category == RootCauseCategory.BOUNDARY_ERROR:
                suggestions.append("Add boundary value tests")
            if cause.category == RootCauseCategory.TYPE_MISMATCH:
                suggestions.append("Add type validation tests")
        
        return list(set(suggestions))
    
    def _generate_explanation(self, error_info: ErrorInfo,
                              root_causes: List[RootCause],
                              fix_options: List[FixOption]) -> str:
        """修正の説明を生成"""
        explanation = f"""
Error Analysis:
- Type: {error_info.error_type.name}
- Message: {error_info.error_message}
- Location: {error_info.error_file or 'Unknown'}:{error_info.error_line or '?'}

Root Cause(s):
"""
        
        for i, cause in enumerate(root_causes[:3], 1):
            explanation += f"{i}. [{cause.category.name}] {cause.description} (confidence: {cause.confidence:.2f})\n"
        
        explanation += f"\nGenerated {len(fix_options)} fix options. "
        if fix_options:
            best = fix_options[0]
            explanation += f"Recommended: {best.strategy.name} ({best.estimated_effort} effort)"
        
        return explanation


# 便利な関数インターフェース
def generate_fix(error_info: ErrorInfo,
                 root_causes: List[RootCause],
                 code_context: Optional[str] = None) -> GeneratedFix:
    """
    修正案を生成する便利関数
    
    Args:
        error_info: エラー情報
        root_causes: 根本原因リスト
        code_context: エラー発生箇所のコード
        
    Returns:
        GeneratedFix: 生成された修正案
    """
    generator = FixGenerator()
    return generator.generate(error_info, root_causes, code_context)
