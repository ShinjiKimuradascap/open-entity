#!/usr/bin/env python3
"""
Task Verification System
タスク完了検証システム - 成果物の品質チェックと検証

Features:
- 成果物の自動検証
- 品質チェックルールエンジン
- 検証レポート生成
- 検証失敗時の差し戻し対応
"""

import json
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional, Dict, List, Any, Callable, Union
from pathlib import Path
import re

try:
    from task_delegation import (
        TaskDelegationMessage, 
        TaskResponseMessage, 
        TaskStatus,
        TaskType
    )
    DELEGATION_AVAILABLE = True
except ImportError:
    DELEGATION_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VerificationStatus(Enum):
    """検証状態"""
    PENDING = "pending"           # 検証待ち
    IN_PROGRESS = "in_progress"   # 検証中
    PASSED = "passed"             # 検証合格
    FAILED = "failed"             # 検証不合格
    PARTIAL = "partial"           # 部分合格
    ERROR = "error"               # 検証エラー
    SKIPPED = "skipped"           # 検証スキップ


class VerificationRuleType(Enum):
    """検証ルール種別"""
    FILE_EXISTS = "file_exists"           # ファイル存在チェック
    FILE_CONTENT = "file_content"         # ファイル内容チェック
    CODE_QUALITY = "code_quality"         # コード品質
    TEST_COVERAGE = "test_coverage"       # テストカバレッジ
    DOCUMENTATION = "documentation"       # ドキュメント
    SECURITY_CHECK = "security_check"     # セキュリティチェック
    PERFORMANCE = "performance"           # パフォーマンス
    CUSTOM = "custom"                     # カスタム


@dataclass
class VerificationRule:
    """検証ルール定義
    
    Attributes:
        rule_id: ルールID
        rule_type: ルール種別
        name: ルール名
        description: 説明
        criteria: 検証基準（辞書形式）
        weight: 重要度（0-1）
        is_required: 必須かどうか
        auto_fixable: 自動修正可能か
    """
    rule_id: str
    rule_type: str
    name: str
    description: str = ""
    criteria: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    is_required: bool = True
    auto_fixable: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationRule":
        return cls(**data)


@dataclass
class VerificationResult:
    """検証結果
    
    Attributes:
        result_id: 結果ID
        rule_id: 適用したルールID
        status: 検証状態
        message: 結果メッセージ
        details: 詳細情報
        score: スコア（0-100）
        timestamp: 検証日時
        duration_ms: 処理時間（ミリ秒）
        suggestions: 改善提案リスト
    """
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str = ""
    status: str = VerificationStatus.PENDING.value
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: int = 0
    suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationResult":
        return cls(**data)


@dataclass
class TaskVerificationReport:
    """タスク検証レポート
    
    Attributes:
        report_id: レポートID
        task_id: 対象タスクID
        verifier_id: 検証者ID
        overall_status: 総合判定
        overall_score: 総合スコア（0-100）
        results: 個別検証結果リスト
        summary: サマリー
        created_at: 作成日時
        completed_at: 完了日時
        recommendations: 推奨事項
    """
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    verifier_id: str = ""
    overall_status: str = VerificationStatus.PENDING.value
    overall_score: float = 0.0
    results: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskVerificationReport":
        return cls(**data)


class VerificationRuleEngine:
    """検証ルールエンジン
    
    各種検証ルールを登録・実行する
    """
    
    def __init__(self):
        self._rules: Dict[str, VerificationRule] = {}
        self._handlers: Dict[str, Callable[[VerificationRule, Dict[str, Any]], VerificationResult]] = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """デフォルトハンドラを登録"""
        self._handlers[VerificationRuleType.FILE_EXISTS.value] = self._check_file_exists
        self._handlers[VerificationRuleType.FILE_CONTENT.value] = self._check_file_content
        self._handlers[VerificationRuleType.CODE_QUALITY.value] = self._check_code_quality
        self._handlers[VerificationRuleType.DOCUMENTATION.value] = self._check_documentation
    
    def register_rule(self, rule: VerificationRule) -> None:
        """検証ルールを登録"""
        self._rules[rule.rule_id] = rule
        logger.info(f"Registered verification rule: {rule.name} ({rule.rule_id})")
    
    def register_handler(
        self, 
        rule_type: str, 
        handler: Callable[[VerificationRule, Dict[str, Any]], VerificationResult]
    ) -> None:
        """ルールタイプごとのハンドラを登録"""
        self._handlers[rule_type] = handler
        logger.info(f"Registered handler for rule type: {rule_type}")
    
    def get_rule(self, rule_id: str) -> Optional[VerificationRule]:
        """ルールを取得"""
        return self._rules.get(rule_id)
    
    def list_rules(self) -> List[VerificationRule]:
        """全ルールを取得"""
        return list(self._rules.values())
    
    def execute_rule(self, rule_id: str, context: Dict[str, Any]) -> VerificationResult:
        """単一ルールを実行"""
        rule = self._rules.get(rule_id)
        if not rule:
            return VerificationResult(
                rule_id=rule_id,
                status=VerificationStatus.ERROR.value,
                message=f"Rule not found: {rule_id}",
                score=0
            )
        
        handler = self._handlers.get(rule.rule_type)
        if not handler:
            return VerificationResult(
                rule_id=rule_id,
                status=VerificationStatus.ERROR.value,
                message=f"No handler for rule type: {rule.rule_type}",
                score=0
            )
        
        start_time = datetime.now(timezone.utc)
        try:
            result = handler(rule, context)
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            result.duration_ms = int(duration)
            result.rule_id = rule_id
            return result
        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            return VerificationResult(
                rule_id=rule_id,
                status=VerificationStatus.ERROR.value,
                message=f"Verification error: {str(e)}",
                score=0,
                duration_ms=int(duration)
            )
    
    def execute_all_rules(self, context: Dict[str, Any]) -> List[VerificationResult]:
        """全ルールを実行"""
        return [self.execute_rule(rule_id, context) for rule_id in self._rules]
    
    # ===== デフォルト検証ハンドラ =====
    
    def _check_file_exists(self, rule: VerificationRule, context: Dict[str, Any]) -> VerificationResult:
        """ファイル存在チェック"""
        filepath = rule.criteria.get("path", "")
        required = rule.criteria.get("required", True)
        
        if not filepath:
            return VerificationResult(
                status=VerificationStatus.ERROR.value,
                message="No file path specified",
                score=0
            )
        
        path = Path(filepath)
        exists = path.exists()
        
        if required and not exists:
            return VerificationResult(
                status=VerificationStatus.FAILED.value,
                message=f"Required file not found: {filepath}",
                details={"path": filepath, "exists": False},
                score=0,
                suggestions=[f"Create file: {filepath}"]
            )
        
        if exists:
            size = path.stat().st_size
            return VerificationResult(
                status=VerificationStatus.PASSED.value,
                message=f"File exists: {filepath} ({size} bytes)",
                details={"path": filepath, "exists": True, "size": size},
                score=100
            )
        
        return VerificationResult(
            status=VerificationStatus.SKIPPED.value,
            message=f"Optional file not found: {filepath}",
            details={"path": filepath, "exists": False},
            score=100  # Optionalなのでスコアは満点
        )
    
    def _check_file_content(self, rule: VerificationRule, context: Dict[str, Any]) -> VerificationResult:
        """ファイル内容チェック"""
        filepath = rule.criteria.get("path", "")
        patterns = rule.criteria.get("patterns", [])
        min_lines = rule.criteria.get("min_lines", 0)
        max_lines = rule.criteria.get("max_lines", float('inf'))
        
        if not filepath or not Path(filepath).exists():
            return VerificationResult(
                status=VerificationStatus.FAILED.value,
                message=f"File not found: {filepath}",
                score=0
            )
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                line_count = len(lines)
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR.value,
                message=f"Cannot read file: {str(e)}",
                score=0
            )
        
        # 行数チェック
        if line_count < min_lines:
            return VerificationResult(
                status=VerificationStatus.FAILED.value,
                message=f"File too short: {line_count} lines (min: {min_lines})",
                details={"line_count": line_count, "min_lines": min_lines},
                score=50,
                suggestions=[f"Add more content (minimum {min_lines} lines required)"]
            )
        
        if line_count > max_lines:
            return VerificationResult(
                status=VerificationStatus.FAILED.value,
                message=f"File too long: {line_count} lines (max: {max_lines})",
                details={"line_count": line_count, "max_lines": max_lines},
                score=50,
                suggestions=[f"Reduce file size (maximum {max_lines} lines)"]
            )
        
        # パターンチェック
        missing_patterns = []
        for pattern in patterns:
            if pattern not in content and not re.search(pattern, content):
                missing_patterns.append(pattern)
        
        if missing_patterns:
            score = max(0, 100 - len(missing_patterns) * 20)
            return VerificationResult(
                status=VerificationStatus.PARTIAL.value if score > 50 else VerificationStatus.FAILED.value,
                message=f"Missing patterns: {missing_patterns}",
                details={
                    "line_count": line_count,
                    "missing_patterns": missing_patterns,
                    "found_patterns": len(patterns) - len(missing_patterns)
                },
                score=score,
                suggestions=[f"Add required content: {p}" for p in missing_patterns]
            )
        
        return VerificationResult(
            status=VerificationStatus.PASSED.value,
            message=f"Content check passed: {line_count} lines, {len(patterns)} patterns matched",
            details={"line_count": line_count, "patterns_matched": len(patterns)},
            score=100
        )
    
    def _check_code_quality(self, rule: VerificationRule, context: Dict[str, Any]) -> VerificationResult:
        """コード品質チェック（簡易版）"""
        filepath = rule.criteria.get("path", "")
        
        if not filepath or not Path(filepath).exists():
            return VerificationResult(
                status=VerificationStatus.SKIPPED.value,
                message=f"File not found: {filepath}",
                score=100
            )
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR.value,
                message=f"Cannot read file: {str(e)}",
                score=0
            )
        
        issues = []
        suggestions = []
        
        # 簡易チェック項目
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # 長すぎる行
            if len(line) > 120:
                issues.append(f"Line {i}: Too long ({len(line)} chars)")
                suggestions.append(f"Line {i}: Shorten to under 120 characters")
            
            # 末尾スペース
            if line != line.rstrip():
                issues.append(f"Line {i}: Trailing whitespace")
            
            # TODO/FIXMEチェック
            if 'TODO' in line or 'FIXME' in line:
                issues.append(f"Line {i}: Contains TODO/FIXME")
        
        # 関数/クラス定義チェック（Python）
        has_function = bool(re.search(r'^(def|class)\s+', content, re.MULTILINE))
        
        score = max(0, 100 - len(issues) * 5)
        
        if issues:
            return VerificationResult(
                status=VerificationStatus.PARTIAL.value if score > 70 else VerificationStatus.FAILED.value,
                message=f"Code quality issues found: {len(issues)}",
                details={
                    "issues": issues[:10],  # 最大10件
                    "has_functions": has_function,
                    "total_lines": len(lines)
                },
                score=score,
                suggestions=suggestions[:5]
            )
        
        return VerificationResult(
            status=VerificationStatus.PASSED.value,
            message=f"Code quality check passed: {len(lines)} lines, no issues found",
            details={"total_lines": len(lines), "has_functions": has_function},
            score=100
        )
    
    def _check_documentation(self, rule: VerificationRule, context: Dict[str, Any]) -> VerificationResult:
        """ドキュメントチェック"""
        filepath = rule.criteria.get("path", "")
        requires_docstring = rule.criteria.get("requires_docstring", True)
        requires_comments = rule.criteria.get("requires_comments", False)
        min_doc_ratio = rule.criteria.get("min_doc_ratio", 0.1)
        
        if not filepath or not Path(filepath).exists():
            return VerificationResult(
                status=VerificationStatus.SKIPPED.value,
                message=f"File not found: {filepath}",
                score=100
            )
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR.value,
                message=f"Cannot read file: {str(e)}",
                score=0
            )
        
        issues = []
        
        # Docstringチェック
        if requires_docstring:
            has_module_docstring = content.strip().startswith('"""') or content.strip().startswith("'''")
            has_function_docstring = '"""' in content or "'''" in content
            
            if not has_module_docstring and not has_function_docstring:
                issues.append("No docstrings found")
        
        # コメント比率チェック
        lines = content.split('\n')
        comment_lines = sum(1 for line in lines if line.strip().startswith('#'))
        doc_ratio = comment_lines / len(lines) if lines else 0
        
        if requires_comments and doc_ratio < min_doc_ratio:
            issues.append(f"Low comment ratio: {doc_ratio:.1%} (min: {min_doc_ratio:.1%})")
        
        if issues:
            score = max(0, 100 - len(issues) * 30)
            return VerificationResult(
                status=VerificationStatus.PARTIAL.value if score > 60 else VerificationStatus.FAILED.value,
                message=f"Documentation issues: {issues}",
                details={
                    "issues": issues,
                    "comment_ratio": doc_ratio,
                    "comment_lines": comment_lines
                },
                score=score,
                suggestions=["Add module/function docstrings", "Add inline comments"]
            )
        
        return VerificationResult(
            status=VerificationStatus.PASSED.value,
            message="Documentation check passed",
            details={"comment_ratio": doc_ratio},
            score=100
        )


class TaskCompletionVerifier:
    """タスク完了検証システム
    
    タスクの完了を検証し、品質を保証する
    """
    
    def __init__(self, verifier_id: str = "verifier"):
        self.verifier_id = verifier_id
        self.rule_engine = VerificationRuleEngine()
        self._reports: Dict[str, TaskVerificationReport] = {}
        self._default_rules_registered = False
    
    def register_default_rules(self):
        """デフォルト検証ルールを登録"""
        if self._default_rules_registered:
            return
        
        # ファイル存在チェック
        self.rule_engine.register_rule(VerificationRule(
            rule_id="check_main_file",
            rule_type=VerificationRuleType.FILE_EXISTS.value,
            name="Main File Check",
            description="Verify main deliverable file exists",
            criteria={"path": "", "required": True},
            weight=1.0,
            is_required=True
        ))
        
        # コード品質チェック
        self.rule_engine.register_rule(VerificationRule(
            rule_id="check_code_quality",
            rule_type=VerificationRuleType.CODE_QUALITY.value,
            name="Code Quality Check",
            description="Check code style and quality",
            criteria={"path": ""},
            weight=0.8,
            is_required=True
        ))
        
        # ドキュメントチェック
        self.rule_engine.register_rule(VerificationRule(
            rule_id="check_documentation",
            rule_type=VerificationRuleType.DOCUMENTATION.value,
            name="Documentation Check",
            description="Check code documentation",
            criteria={"path": "", "requires_docstring": True},
            weight=0.6,
            is_required=False
        ))
        
        self._default_rules_registered = True
        logger.info("Default verification rules registered")
    
    def verify_task_completion(
        self,
        task_id: str,
        deliverables: List[Dict[str, Any]],
        custom_context: Optional[Dict[str, Any]] = None
    ) -> TaskVerificationReport:
        """タスク完了を検証
        
        Args:
            task_id: タスクID
            deliverables: 成果物リスト
            custom_context: 追加コンテキスト
        
        Returns:
            TaskVerificationReport: 検証レポート
        """
        self.register_default_rules()
        
        report = TaskVerificationReport(
            task_id=task_id,
            verifier_id=self.verifier_id
        )
        
        context = custom_context or {}
        context['deliverables'] = deliverables
        context['task_id'] = task_id
        
        all_results = []
        total_score = 0
        total_weight = 0
        failed_required = False
        
        # 各成果物を検証
        for deliverable in deliverables:
            file_path = deliverable.get('path', '')
            if not file_path:
                continue
            
            # ファイル存在チェック
            rule = self.rule_engine.get_rule("check_main_file")
            if rule:
                rule_copy = VerificationRule.from_dict(rule.to_dict())
                rule_copy.criteria["path"] = file_path
                self.rule_engine.register_rule(rule_copy)
                
                result = self.rule_engine.execute_rule("check_main_file", context)
                all_results.append(result)
                total_score += result.score * rule.weight
                total_weight += rule.weight
                
                if result.status in [VerificationStatus.FAILED.value, VerificationStatus.ERROR.value] and rule.is_required:
                    failed_required = True
            
            # コードファイルの場合は品質チェック
            if file_path.endswith('.py'):
                rule = self.rule_engine.get_rule("check_code_quality")
                if rule:
                    rule_copy = VerificationRule.from_dict(rule.to_dict())
                    rule_copy.criteria["path"] = file_path
                    self.rule_engine.register_rule(rule_copy)
                    
                    result = self.rule_engine.execute_rule("check_code_quality", context)
                    all_results.append(result)
                    total_score += result.score * rule.weight
                    total_weight += rule.weight
                    
                    if result.status == VerificationStatus.FAILED.value and rule.is_required:
                        failed_required = True
                
                # ドキュメントチェック
                rule = self.rule_engine.get_rule("check_documentation")
                if rule:
                    rule_copy = VerificationRule.from_dict(rule.to_dict())
                    rule_copy.criteria["path"] = file_path
                    self.rule_engine.register_rule(rule_copy)
                    
                    result = self.rule_engine.execute_rule("check_documentation", context)
                    all_results.append(result)
                    total_score += result.score * rule.weight
                    total_weight += rule.weight
        
        # レポート作成
        report.results = [r.to_dict() for r in all_results]
        report.overall_score = total_score / total_weight if total_weight > 0 else 0
        
        # 総合判定
        if failed_required:
            report.overall_status = VerificationStatus.FAILED.value
        elif report.overall_score >= 90:
            report.overall_status = VerificationStatus.PASSED.value
        elif report.overall_score >= 60:
            report.overall_status = VerificationStatus.PARTIAL.value
        else:
            report.overall_status = VerificationStatus.FAILED.value
        
        # サマリー
        passed = sum(1 for r in all_results if r.status == VerificationStatus.PASSED.value)
        failed = sum(1 for r in all_results if r.status == VerificationStatus.FAILED.value)
        partial = sum(1 for r in all_results if r.status == VerificationStatus.PARTIAL.value)
        
        report.summary = {
            "total_checks": len(all_results),
            "passed": passed,
            "failed": failed,
            "partial": partial,
            "score": round(report.overall_score, 2)
        }
        
        # 推奨事項
        for result in all_results:
            if result.suggestions:
                report.recommendations.extend(result.suggestions)
        
        report.recommendations = list(set(report.recommendations))[:10]  # 重複除去、最大10件
        report.completed_at = datetime.now(timezone.utc).isoformat()
        
        self._reports[report.report_id] = report
        logger.info(f"Verification completed for task {task_id}: {report.overall_status}")
        
        return report
    
    def get_report(self, report_id: str) -> Optional[TaskVerificationReport]:
        """検証レポートを取得"""
        return self._reports.get(report_id)
    
    def get_reports_by_task(self, task_id: str) -> List[TaskVerificationReport]:
        """タスクIDでレポートを検索"""
        return [r for r in self._reports.values() if r.task_id == task_id]
    
    def evaluate_quality(
        self,
        task_id: str,
        deliverables: List[Dict[str, Any]],
        quality_criteria: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """タスク品質を評価
        
        Args:
            task_id: タスクID
            deliverables: 成果物リスト
            quality_criteria: 品質評価基準
            
        Returns:
            品質評価結果
        """
        criteria = quality_criteria or {
            "completeness_weight": 0.4,
            "code_quality_weight": 0.3,
            "documentation_weight": 0.2,
            "testing_weight": 0.1
        }
        
        # 検証実行
        report = self.verify_task_completion(task_id, deliverables)
        
        # 品質スコア計算
        completeness_score = 0
        code_quality_score = 0
        documentation_score = 0
        testing_score = 0
        
        for result in report.results:
            if "exists" in result.get("details", {}):
                completeness_score = result.get("score", 0)
            elif "quality" in result.get("rule_id", ""):
                code_quality_score = result.get("score", 0)
            elif "documentation" in result.get("rule_id", ""):
                documentation_score = result.get("score", 0)
        
        # テストカバレッジ（簡易版）
        for deliverable in deliverables:
            path = deliverable.get("path", "")
            if path.endswith(".py"):
                test_file = path.replace(".py", "_test.py").replace("/", "/test_")
                if Path(test_file).exists():
                    testing_score = 100
                    break
        
        # 重み付け合計
        overall_quality = (
            completeness_score * criteria["completeness_weight"] +
            code_quality_score * criteria["code_quality_weight"] +
            documentation_score * criteria["documentation_weight"] +
            testing_score * criteria["testing_weight"]
        )
        
        quality_level = "excellent" if overall_quality >= 90 else \
                       "good" if overall_quality >= 75 else \
                       "acceptable" if overall_quality >= 60 else "poor"
        
        return {
            "task_id": task_id,
            "overall_quality": round(overall_quality, 2),
            "quality_level": quality_level,
            "breakdown": {
                "completeness": round(completeness_score, 2),
                "code_quality": round(code_quality_score, 2),
                "documentation": round(documentation_score, 2),
                "testing": round(testing_score, 2)
            },
            "criteria_weights": criteria,
            "recommendations": report.recommendations
        }
    
    def calculate_reward(
        self,
        task_id: str,
        deliverables: List[Dict[str, Any]],
        base_reward: float = 100.0,
        reward_formula: Optional[str] = "linear"
    ) -> Dict[str, Any]:
        """タスク報酬を計算
        
        Args:
            task_id: タスクID
            deliverables: 成果物リスト
            base_reward: 基本報酬額
            reward_formula: 報酬計算式 ("linear", "exponential", "tiered")
            
        Returns:
            報酬計算結果
        """
        # 品質評価取得
        quality_result = self.evaluate_quality(task_id, deliverables)
        quality_score = quality_result["overall_quality"]
        
        # 報酬計算
        if reward_formula == "linear":
            # 線形: 品質スコアの割合で報酬
            reward_multiplier = quality_score / 100.0
        elif reward_formula == "exponential":
            # 指数: 高品質にボーナス
            reward_multiplier = (quality_score / 100.0) ** 0.5
        elif reward_formula == "tiered":
            # ティア制: 段階的報酬
            if quality_score >= 90:
                reward_multiplier = 1.5
            elif quality_score >= 75:
                reward_multiplier = 1.2
            elif quality_score >= 60:
                reward_multiplier = 1.0
            elif quality_score >= 40:
                reward_multiplier = 0.7
            else:
                reward_multiplier = 0.5
        else:
            reward_multiplier = quality_score / 100.0
        
        calculated_reward = base_reward * reward_multiplier
        
        # ボーナス計算
        bonus = 0
        if quality_score >= 95:
            bonus = base_reward * 0.2
        elif quality_score >= 90:
            bonus = base_reward * 0.1
        
        total_reward = calculated_reward + bonus
        
        return {
            "task_id": task_id,
            "base_reward": base_reward,
            "quality_score": quality_score,
            "reward_formula": reward_formula,
            "reward_multiplier": round(reward_multiplier, 3),
            "calculated_reward": round(calculated_reward, 2),
            "bonus": round(bonus, 2),
            "total_reward": round(total_reward, 2),
            "quality_level": quality_result["quality_level"],
            "breakdown": quality_result["breakdown"]
        }
    
    def create_rejection_response(
        self,
        task_response: TaskResponseMessage,
        report: TaskVerificationReport,
        rejection_reason: str = ""
    ) -> TaskResponseMessage:
        """検証失敗時の差し戻し応答を作成"""
        if DELEGATION_AVAILABLE:
            return TaskResponseMessage(
                task_id=task_response.task_id,
                responder_id=self.verifier_id,
                response_type="fail",
                status=TaskStatus.FAILED.value,
                message=rejection_reason or f"Verification failed: {report.overall_status}",
                result={
                    "verification_report": report.to_dict(),
                    "score": report.overall_score,
                    "recommendations": report.recommendations
                }
            )
        else:
            return {
                "task_id": task_response.task_id,
                "response_type": "fail",
                "message": rejection_reason or f"Verification failed: {report.overall_status}",
                "verification_score": report.overall_score
            }


# ===== 便利関数 =====

def create_verifier(verifier_id: str = "verifier") -> TaskCompletionVerifier:
    """検証システムを作成"""
    verifier = TaskCompletionVerifier(verifier_id)
    verifier.register_default_rules()
    return verifier


def quick_verify(file_path: str) -> TaskVerificationReport:
    """ファイルを簡易検証"""
    verifier = create_verifier()
    deliverables = [{"type": "file", "path": file_path}]
    return verifier.verify_task_completion(
        task_id=f"quick_verify_{uuid.uuid4().hex[:8]}",
        deliverables=deliverables
    )


if __name__ == "__main__":
    # テスト
    print("Testing Task Verification System...")
    
    # 検証システム作成
    verifier = create_verifier("test-verifier")
    
    # 存在するファイルでテスト
    test_file = "services/task_delegation.py"
    if Path(test_file).exists():
        report = quick_verify(test_file)
        print(f"\nVerification Report:")
        print(f"  Status: {report.overall_status}")
        print(f"  Score: {report.overall_score:.1f}")
        print(f"  Summary: {report.summary}")
        if report.recommendations:
            print(f"  Recommendations: {report.recommendations[:3]}")
        print("\nAll tests passed!")
    else:
        print(f"Test file not found: {test_file}")
