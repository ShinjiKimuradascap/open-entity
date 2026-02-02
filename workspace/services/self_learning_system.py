"""Self Learning System Module

ExperienceCollector、PatternAnalyzer、SkillSynthesizer、DecisionOptimizerを統合し、
一つのインターフェースで提供するEntity自律学習システム。

主要機能:
1. 学習ループ実行（経験収集→分析→スキル生成）
2. 意思決定支援（状況評価→推奨生成）
3. 自動改善（定期的な自己分析と改善提案）
4. 統計レポート（学習進捗の可視化）
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Callable
from pathlib import Path
from collections import defaultdict
import threading
import time

from services.experience_collector import (
    ExperienceCollector, TaskExecutionRecord, TaskResult, SuccessPattern, FailureAnalysis,
    get_experience_collector
)
from services.pattern_analyzer import (
    PatternAnalyzer, IdentifiedPattern, PatternType, FailurePattern, 
    CorrelationResult, TrendAnalysis, ErrorCategory
)
from services.skill_synthesizer import (
    SkillSynthesizer, SynthesizedSkill, SynthesisType, SkillQualityLevel,
    get_skill_synthesizer
)
from services.decision_optimizer import (
    DecisionOptimizer, SituationAssessment, ActionRecommendation, 
    OutcomePrediction, RiskAssessment, DecisionReport,
    DecisionConfidence, RiskLevel, ActionPriority
)

logger = logging.getLogger(__name__)


class LearningPhase(Enum):
    """学習フェーズ"""
    IDLE = "idle"                          # 待機中
    COLLECTING = "collecting"              # 経験収集中
    ANALYZING = "analyzing"                # 分析中
    SYNTHESIZING = "synthesizing"          # スキル合成中
    OPTIMIZING = "optimizing"              # 意思決定最適化中
    COMPLETED = "completed"                # 完了


class ImprovementStatus(Enum):
    """改善ステータス"""
    PENDING = "pending"                    # 保留中
    IN_PROGRESS = "in_progress"            # 進行中
    IMPLEMENTED = "implemented"            # 実装済み
    REJECTED = "rejected"                  # 拒否
    VERIFIED = "verified"                  # 検証済み


@dataclass
class LearningMetrics:
    """学習メトリクス
    
    Attributes:
        total_experiences: 総経験数
        total_patterns: 総パターン数
        total_skills: 総スキル数
        total_decisions: 総意思決定数
        success_rate: 成功率
        avg_learning_time: 平均学習時間
        improvement_count: 改善提案数
        last_updated: 最終更新日時
    """
    total_experiences: int = 0
    total_patterns: int = 0
    total_skills: int = 0
    total_decisions: int = 0
    success_rate: float = 0.0
    avg_learning_time: float = 0.0
    improvement_count: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImprovementSuggestion:
    """改善提案
    
    Attributes:
        suggestion_id: 提案ID
        title: タイトル
        description: 説明
        category: カテゴリ
        priority: 優先度
        status: ステータス
        expected_impact: 期待される影響
        implementation_difficulty: 実装難易度
        created_at: 作成日時
        implemented_at: 実装日時
    """
    suggestion_id: str
    title: str
    description: str
    category: str
    priority: int  # 1-5
    status: ImprovementStatus
    expected_impact: str
    implementation_difficulty: int  # 1-5
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    implemented_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "status": self.status.value,
            "expected_impact": self.expected_impact,
            "implementation_difficulty": self.implementation_difficulty,
            "created_at": self.created_at,
            "implemented_at": self.implemented_at
        }


@dataclass
class LearningReport:
    """学習レポート
    
    Attributes:
        report_id: レポートID
        generated_at: 生成日時
        metrics: 学習メトリクス
        new_patterns: 新規パターン
        new_skills: 新規スキル
        top_recommendations: 推奨トップ
        improvement_suggestions: 改善提案
        trends: トレンド
    """
    report_id: str
    generated_at: str
    metrics: LearningMetrics
    new_patterns: List[Dict[str, Any]]
    new_skills: List[Dict[str, Any]]
    top_recommendations: List[Dict[str, Any]]
    improvement_suggestions: List[Dict[str, Any]]
    trends: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "metrics": self.metrics.to_dict(),
            "new_patterns": self.new_patterns,
            "new_skills": self.new_skills,
            "top_recommendations": self.top_recommendations,
            "improvement_suggestions": self.improvement_suggestions,
            "trends": self.trends
        }


class SelfLearningSystem:
    """自己学習システム
    
    4つのコアモジュールを統合し、包括的な学習と意思決定支援を提供する。
    """
    
    def __init__(
        self,
        experience_collector: Optional[ExperienceCollector] = None,
        pattern_analyzer: Optional[PatternAnalyzer] = None,
        skill_synthesizer: Optional[SkillSynthesizer] = None,
        decision_optimizer: Optional[DecisionOptimizer] = None,
        auto_improvement: bool = False,
        improvement_interval: int = 3600  # 秒
    ):
        """初期化
        
        Args:
            experience_collector: ExperienceCollectorインスタンス
            pattern_analyzer: PatternAnalyzerインスタンス
            skill_synthesizer: SkillSynthesizerインスタンス
            decision_optimizer: DecisionOptimizerインスタンス
            auto_improvement: 自動改善を有効にするか
            improvement_interval: 自動改善間隔（秒）
        """
        self.experience_collector = experience_collector or get_experience_collector()
        self.pattern_analyzer = pattern_analyzer or PatternAnalyzer()
        self.skill_synthesizer = skill_synthesizer or get_skill_synthesizer()
        self.decision_optimizer = decision_optimizer or DecisionOptimizer()
        
        self._current_phase: LearningPhase = LearningPhase.IDLE
        self._metrics = LearningMetrics()
        self._improvement_suggestions: List[ImprovementSuggestion] = []
        self._learning_history: List[Dict[str, Any]] = []
        self._auto_improvement = auto_improvement
        self._improvement_interval = improvement_interval
        self._improvement_thread: Optional[threading.Thread] = None
        self._stop_improvement = threading.Event()
        
        # コールバック
        self._on_phase_change: Optional[Callable[[LearningPhase], None]] = None
        self._on_suggestion_created: Optional[Callable[[ImprovementSuggestion], None]] = None
        
        if auto_improvement:
            self._start_auto_improvement()
        
        logger.info("SelfLearningSystem initialized")
    
    @property
    def current_phase(self) -> LearningPhase:
        """現在の学習フェーズ"""
        return self._current_phase
    
    @property
    def metrics(self) -> LearningMetrics:
        """現在のメトリクス"""
        return self._metrics
    
    def _set_phase(self, phase: LearningPhase):
        """フェーズを設定"""
        self._current_phase = phase
        if self._on_phase_change:
            self._on_phase_change(phase)
        logger.debug(f"Learning phase changed to: {phase.value}")
    
    def set_phase_change_callback(self, callback: Callable[[LearningPhase], None]):
        """フェーズ変更コールバックを設定
        
        Args:
            callback: フェーズ変更時に呼ばれる関数
        """
        self._on_phase_change = callback
    
    def set_suggestion_callback(self, callback: Callable[[ImprovementSuggestion], None]):
        """改善提案作成コールバックを設定
        
        Args:
            callback: 提案作成時に呼ばれる関数
        """
        self._on_suggestion_created = callback
    
    def record_experience(
        self,
        task_id: str,
        task_type: str,
        result: TaskResult,
        duration: float,
        resources: Dict[str, Any],
        error_message: Optional[str] = None,
        retry_count: int = 0,
        context: Optional[Dict[str, Any]] = None
    ) -> TaskExecutionRecord:
        """経験を記録
        
        シンプルなインターフェースで経験を記録する。
        
        Args:
            task_id: タスクID
            task_type: タスクタイプ
            result: 実行結果
            duration: 実行時間（秒）
            resources: 使用リソース
            error_message: エラーメッセージ
            retry_count: リトライ回数
            context: 追加コンテキスト
            
        Returns:
            作成された記録
        """
        record = self.experience_collector.record_task_execution(
            task_id=task_id,
            task_type=task_type,
            result=result,
            duration=duration,
            resources=resources,
            error_message=error_message,
            retry_count=retry_count,
            context=context
        )
        
        self._metrics.total_experiences += 1
        self._update_metrics()
        
        logger.debug(f"Experience recorded: {task_id}")
        return record
    
    def run_learning_loop(
        self,
        min_confidence: float = 0.7,
        min_occurrences: int = 3,
        auto_register_skills: bool = False
    ) -> Dict[str, Any]:
        """学習ループを実行
        
        経験収集→パターン分析→スキル生成の一連のプロセスを実行する。
        
        Args:
            min_confidence: 最小信頼度
            min_occurrences: 最小出現回数
            auto_register_skills: スキルを自動登録するか
            
        Returns:
            学習結果
        """
        start_time = time.time()
        self._set_phase(LearningPhase.ANALYZING)
        
        try:
            # 1. パターン分析
            logger.info("Starting pattern analysis...")
            patterns = self.pattern_analyzer.identify_success_patterns(
                min_occurrences=min_occurrences,
                min_confidence=min_confidence
            )
            failure_patterns = self.pattern_analyzer.classify_failure_patterns()
            correlations = self.pattern_analyzer.analyze_correlations()
            trends = self.pattern_analyzer.detect_trends()
            
            self._metrics.total_patterns = len(patterns)
            
            # 2. スキル合成
            self._set_phase(LearningPhase.SYNTHESIZING)
            logger.info("Starting skill synthesis...")
            skills = self.skill_synthesizer.generate_skills_from_patterns(
                min_confidence=min_confidence,
                auto_register=auto_register_skills
            )
            
            self._metrics.total_skills = len(skills)
            
            # 3. 改善提案生成
            improvements = self.skill_synthesizer.suggest_skill_improvements()
            for imp in improvements:
                suggestion = ImprovementSuggestion(
                    suggestion_id=imp.suggestion_id,
                    title=f"Improve {imp.skill_id}",
                    description=imp.description,
                    category="skill_improvement",
                    priority=imp.priority,
                    status=ImprovementStatus.PENDING,
                    expected_impact=imp.expected_benefit,
                    implementation_difficulty=3
                )
                self._improvement_suggestions.append(suggestion)
                if self._on_suggestion_created:
                    self._on_suggestion_created(suggestion)
            
            self._metrics.improvement_count = len(self._improvement_suggestions)
            
            # 4. 学習時間記録
            learning_time = time.time() - start_time
            self._metrics.avg_learning_time = (
                (self._metrics.avg_learning_time * (len(self._learning_history)) + learning_time)
                / (len(self._learning_history) + 1)
            )
            
            # 5. 履歴記録
            result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "patterns_identified": len(patterns),
                "skills_generated": len(skills),
                "improvements_suggested": len(improvements),
                "learning_time_seconds": learning_time
            }
            self._learning_history.append(result)
            
            self._set_phase(LearningPhase.COMPLETED)
            logger.info(f"Learning loop completed: {len(patterns)} patterns, {len(skills)} skills")
            
            return {
                "success": True,
                "patterns": [p.to_dict() for p in patterns],
                "skills": [s.to_dict() for s in skills],
                "improvements": [i.to_dict() for i in improvements],
                "correlations": [c.to_dict() for c in correlations],
                "trends": [t.to_dict() for t in trends],
                "metrics": self._metrics.to_dict()
            }
            
        except Exception as e:
            self._set_phase(LearningPhase.IDLE)
            logger.error(f"Learning loop failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_decision_support(
        self,
        context: Dict[str, Any],
        options: Optional[List[Dict[str, Any]]] = None
    ) -> DecisionReport:
        """意思決定支援を取得
        
        現在の状況に基づいて最適な意思決定を支援する。
        
        Args:
            context: 現在の状況コンテキスト
            options: 選択肢（オプション）
            
        Returns:
            意思決定レポート
        """
        self._set_phase(LearningPhase.OPTIMIZING)
        
        try:
            report = self.decision_optimizer.generate_decision_report(
                context=context,
                options=options
            )
            
            self._metrics.total_decisions += 1
            self._update_metrics()
            
            logger.debug(f"Decision support generated: {report.report_id}")
            return report
            
        finally:
            self._set_phase(LearningPhase.IDLE)
    
    def evaluate_and_recommend(
        self,
        task_type: str,
        context: Dict[str, Any]
    ) -> Tuple[SituationAssessment, List[ActionRecommendation]]:
        """状況を評価し推奨を生成
        
        シンプルなインターフェースで状況評価と推奨を取得する。
        
        Args:
            task_type: タスクタイプ
            context: コンテキスト
            
        Returns:
            (状況評価, 推奨リスト)
        """
        full_context = {**context, "task_type": task_type}
        
        # 状況評価
        assessment = self.decision_optimizer.evaluate_situation(full_context)
        
        # アクション推奨
        recommendations = self.decision_optimizer.recommend_actions(full_context)
        
        return assessment, recommendations
    
    def run_self_analysis(self) -> List[ImprovementSuggestion]:
        """自己分析を実行
        
        システム自身の性能を分析し、改善提案を生成する。
        
        Returns:
            改善提案リスト
        """
        suggestions = []
        
        # 1. 成功率分析
        stats = self.experience_collector.get_task_statistics()
        if stats.get("success_rate", 1.0) < 0.7:
            suggestions.append(ImprovementSuggestion(
                suggestion_id=str(uuid.uuid4()),
                title="Improve Success Rate",
                description=f"Current success rate ({stats.get('success_rate', 0):.1%}) is below target. Consider analyzing failure patterns.",
                category="performance",
                priority=1,
                status=ImprovementStatus.PENDING,
                expected_impact="Increase overall task success rate to >80%",
                implementation_difficulty=4
            ))
        
        # 2. パターン品質分析
        patterns = self.pattern_analyzer.identify_success_patterns(min_occurrences=1)
        low_confidence_patterns = [p for p in patterns if p.confidence < 0.5]
        if len(low_confidence_patterns) > len(patterns) * 0.3:
            suggestions.append(ImprovementSuggestion(
                suggestion_id=str(uuid.uuid4()),
                title="Improve Pattern Confidence",
                description=f"{len(low_confidence_patterns)} patterns have low confidence. More data collection needed.",
                category="data_quality",
                priority=2,
                status=ImprovementStatus.PENDING,
                expected_impact="Higher confidence in pattern matching",
                implementation_difficulty=2
            ))
        
        # 3. スキル品質分析
        skills = self.skill_synthesizer.synthesized_skills
        low_quality_skills = [s for s in skills if s.quality_score < 0.6]
        if low_quality_skills:
            suggestions.append(ImprovementSuggestion(
                suggestion_id=str(uuid.uuid4()),
                title="Review Low Quality Skills",
                description=f"{len(low_quality_skills)} skills have quality score < 0.6",
                category="skill_quality",
                priority=3,
                status=ImprovementStatus.PENDING,
                expected_impact="Improve overall skill effectiveness",
                implementation_difficulty=3
            ))
        
        # 4. 意思決定精度分析
        if self._metrics.total_decisions > 10:
            recent_decisions = self.decision_optimizer.get_decision_history(limit=10)
            low_confidence_decisions = [
                d for d in recent_decisions 
                if d.get("overall_confidence", 1.0) < 0.5
            ]
            if len(low_confidence_decisions) > 3:
                suggestions.append(ImprovementSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    title="Improve Decision Confidence",
                    description="Multiple recent decisions have low confidence scores",
                    category="decision_quality",
                    priority=2,
                    status=ImprovementStatus.PENDING,
                    expected_impact="More reliable decision making",
                    implementation_difficulty=4
                ))
        
        # 保存
        for suggestion in suggestions:
            self._improvement_suggestions.append(suggestion)
            if self._on_suggestion_created:
                self._on_suggestion_created(suggestion)
        
        self._metrics.improvement_count = len(self._improvement_suggestions)
        
        logger.info(f"Self analysis completed: {len(suggestions)} suggestions")
        return suggestions
    
    def get_learning_report(self, days_back: int = 30) -> LearningReport:
        """学習レポートを生成
        
        Args:
            days_back: 遡る日数
            
        Returns:
            学習レポート
        """
        # 新規パターン
        recent_patterns = self.pattern_analyzer.identify_success_patterns(days_back=days_back)
        
        # 新規スキル
        recent_skills = [
            s for s in self.skill_synthesizer.synthesized_skills
            if (datetime.now(timezone.utc) - datetime.fromisoformat(s.generated_at.replace('Z', '+00:00'))).days <= days_back
        ]
        
        # トップ推奨
        recommendations = self.decision_optimizer.recommend_actions({})
        top_recommendations = [r.to_dict() for r in recommendations[:5]]
        
        # トレンド
        trends = self.pattern_analyzer.detect_trends(days_back=days_back)
        
        report = LearningReport(
            report_id=str(uuid.uuid4()),
            generated_at=datetime.now(timezone.utc).isoformat(),
            metrics=self._metrics,
            new_patterns=[p.to_dict() for p in recent_patterns],
            new_skills=[s.to_dict() for s in recent_skills],
            top_recommendations=top_recommendations,
            improvement_suggestions=[s.to_dict() for s in self._improvement_suggestions],
            trends=[t.to_dict() for t in trends]
        )
        
        return report
    
    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得
        
        Returns:
            統計情報
        """
        exp_stats = self.experience_collector.get_task_statistics()
        
        return {
            "metrics": self._metrics.to_dict(),
            "experience_stats": exp_stats,
            "learning_history_count": len(self._learning_history),
            "pending_improvements": len([s for s in self._improvement_suggestions if s.status == ImprovementStatus.PENDING]),
            "current_phase": self._current_phase.value
        }
    
    def export_learning_data(self, filepath: str, days_back: int = 90) -> bool:
        """学習データをエクスポート
        
        Args:
            filepath: 出力ファイルパス
            days_back: 遡る日数
            
        Returns:
            成功したか
        """
        try:
            data = {
                "export_info": {
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "days_back": days_back,
                    "system_version": "1.0.0"
                },
                "metrics": self._metrics.to_dict(),
                "experiences": self.experience_collector.export_learning_data(days_back=days_back),
                "analysis": self.pattern_analyzer.export_analysis(days_back=days_back),
                "synthesis": self.skill_synthesizer.export_synthesis_data(),
                "improvements": [s.to_dict() for s in self._improvement_suggestions],
                "learning_history": self._learning_history
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Learning data exported to: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False
    
    def apply_improvement(self, suggestion_id: str) -> bool:
        """改善提案を適用
        
        Args:
            suggestion_id: 提案ID
            
        Returns:
            成功したか
        """
        for suggestion in self._improvement_suggestions:
            if suggestion.suggestion_id == suggestion_id:
                suggestion.status = ImprovementStatus.IMPLEMENTED
                suggestion.implemented_at = datetime.now(timezone.utc).isoformat()
                logger.info(f"Improvement applied: {suggestion.title}")
                return True
        
        return False
    
    def _update_metrics(self):
        """メトリクスを更新"""
        stats = self.experience_collector.get_task_statistics()
        self._metrics.success_rate = stats.get("success_rate", 0.0)
        self._metrics.last_updated = datetime.now(timezone.utc).isoformat()
    
    def _start_auto_improvement(self):
        """自動改善を開始"""
        def improvement_loop():
            while not self._stop_improvement.is_set():
                try:
                    self.run_self_analysis()
                    time.sleep(self._improvement_interval)
                except Exception as e:
                    logger.error(f"Auto improvement error: {e}")
                    time.sleep(60)  # エラー時は短い間隔で再試行
        
        self._improvement_thread = threading.Thread(target=improvement_loop, daemon=True)
        self._improvement_thread.start()
        logger.info("Auto improvement started")
    
    def stop_auto_improvement(self):
        """自動改善を停止"""
        self._auto_improvement = False
        self._stop_improvement.set()
        if self._improvement_thread:
            self._improvement_thread.join(timeout=5)
        logger.info("Auto improvement stopped")
    
    def reset(self):
        """システムをリセット"""
        self.stop_auto_improvement()
        self._metrics = LearningMetrics()
        self._improvement_suggestions = []
        self._learning_history = []
        self._set_phase(LearningPhase.IDLE)
        
        # 各コンポーネントもリセット（clear_cacheが存在する場合のみ）
        if hasattr(self.experience_collector, 'clear_cache'):
            self.experience_collector.clear_cache()
        
        logger.info("SelfLearningSystem reset")


# グローバルインスタンス
_learning_system: Optional[SelfLearningSystem] = None


def get_learning_system(
    auto_improvement: bool = False,
    improvement_interval: int = 3600
) -> SelfLearningSystem:
    """グローバル学習システムインスタンスを取得
    
    Args:
        auto_improvement: 自動改善を有効にするか
        improvement_interval: 自動改善間隔（秒）
        
    Returns:
        SelfLearningSystemインスタンス
    """
    global _learning_system
    if _learning_system is None:
        _learning_system = SelfLearningSystem(
            auto_improvement=auto_improvement,
            improvement_interval=improvement_interval
        )
    return _learning_system


def reset_learning_system():
    """グローバルインスタンスをリセット"""
    global _learning_system
    if _learning_system:
        _learning_system.reset()
    _learning_system = None


# 便利なショートカット関数
def learn(
    min_confidence: float = 0.7,
    auto_register_skills: bool = False
) -> Dict[str, Any]:
    """学習ループを実行
    
    Args:
        min_confidence: 最小信頼度
        auto_register_skills: スキルを自動登録するか
        
    Returns:
        学習結果
    """
    system = get_learning_system()
    return system.run_learning_loop(
        min_confidence=min_confidence,
        auto_register_skills=auto_register_skills
    )


def decide(context: Dict[str, Any]) -> DecisionReport:
    """意思決定支援を取得
    
    Args:
        context: 状況コンテキスト
        
    Returns:
        意思決定レポート
    """
    system = get_learning_system()
    return system.get_decision_support(context)


def record(
    task_id: str,
    task_type: str,
    success: bool,
    duration: float,
    resources: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
) -> TaskExecutionRecord:
    """経験を記録
    
    Args:
        task_id: タスクID
        task_type: タスクタイプ
        success: 成功したか
        duration: 実行時間（秒）
        resources: 使用リソース
        error: エラーメッセージ
        
    Returns:
        作成された記録
    """
    system = get_learning_system()
    result = TaskResult.SUCCESS if success else TaskResult.FAILURE
    return system.record_experience(
        task_id=task_id,
        task_type=task_type,
        result=result,
        duration=duration,
        resources=resources or {},
        error_message=error
    )


def get_insights(days_back: int = 30) -> LearningReport:
    """学習インサイトを取得
    
    Args:
        days_back: 遡る日数
        
    Returns:
        学習レポート
    """
    system = get_learning_system()
    return system.get_learning_report(days_back=days_back)
