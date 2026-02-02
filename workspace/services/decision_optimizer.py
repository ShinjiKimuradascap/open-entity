#!/usr/bin/env python3
"""
Decision Optimizer Module

過去の経験とパターン分析に基づいて最適な意思決定を支援するシステム。
ExperienceCollector、PatternAnalyzer、SkillSynthesizerと統合し、
包括的な意思決定支援を行う。

主要機能:
1. 状況評価（現在の状況を過去の類似ケースと比較）
2. アクション推奨（最適な行動を提案）
3. 結果予測（各選択肢の結果を予測）
4. リスク評価（選択肢のリスクを評価）
"""

import json
import logging
import uuid
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Set
from pathlib import Path

from services.experience_collector import ExperienceCollector, TaskExecutionRecord, TaskResult, get_experience_collector
from services.pattern_analyzer import PatternAnalyzer, IdentifiedPattern, PatternType, FailurePattern, CorrelationResult
from services.skill_synthesizer import SkillSynthesizer, SynthesizedSkill, SynthesisType, SkillQualityLevel, get_skill_synthesizer

logger = logging.getLogger(__name__)


class DecisionConfidence(Enum):
    """意思決定の信頼度レベル"""
    VERY_LOW = "very_low"      # < 0.3
    LOW = "low"                # 0.3 - 0.5
    MEDIUM = "medium"          # 0.5 - 0.7
    HIGH = "high"              # 0.7 - 0.9
    VERY_HIGH = "very_high"    # >= 0.9


class RiskLevel(Enum):
    """リスクレベル"""
    CRITICAL = "critical"      # 重大なリスク
    HIGH = "high"              # 高リスク
    MEDIUM = "medium"          # 中リスク
    LOW = "low"                # 低リスク
    MINIMAL = "minimal"        # 最小限のリスク


class ActionPriority(Enum):
    """アクションプライオリティ"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    OPTIONAL = 5


@dataclass
class SituationAssessment:
    """状況評価結果
    
    Attributes:
        assessment_id: 評価ID
        current_context: 現在の状況コンテキスト
        similar_cases: 類似した過去のケース
        matching_patterns: マッチしたパターン
        confidence_score: 評価の信頼度スコア
        assessed_at: 評価日時
    """
    assessment_id: str
    current_context: Dict[str, Any]
    similar_cases: List[TaskExecutionRecord]
    matching_patterns: List[IdentifiedPattern]
    confidence_score: float
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "current_context": self.current_context,
            "similar_cases": [case.to_dict() for case in self.similar_cases],
            "matching_patterns": [self._pattern_to_dict(p) for p in self.matching_patterns],
            "confidence_score": self.confidence_score,
            "assessed_at": self.assessed_at
        }
    
    def _pattern_to_dict(self, pattern: IdentifiedPattern) -> Dict[str, Any]:
        """パターンを辞書に変換"""
        return {
            "pattern_id": pattern.pattern_id,
            "pattern_type": pattern.pattern_type.value,
            "name": pattern.name,
            "description": pattern.description,
            "confidence": pattern.confidence,
            "occurrence_count": pattern.occurrence_count,
            "supporting_data": pattern.supporting_data
        }


@dataclass
class ActionRecommendation:
    """アクション推奨
    
    Attributes:
        recommendation_id: 推奨ID
        action_name: アクション名
        description: 説明
        priority: 優先度
        expected_outcome: 期待される結果
        estimated_success_rate: 推定成功率
        required_resources: 必要リソース
        estimated_duration: 推定所要時間（秒）
        prerequisites: 前提条件
        confidence: 信頼度
    """
    recommendation_id: str
    action_name: str
    description: str
    priority: ActionPriority
    expected_outcome: str
    estimated_success_rate: float
    required_resources: Dict[str, Any]
    estimated_duration: float
    prerequisites: List[str]
    confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "action_name": self.action_name,
            "description": self.description,
            "priority": self.priority.name,
            "expected_outcome": self.expected_outcome,
            "estimated_success_rate": self.estimated_success_rate,
            "required_resources": self.required_resources,
            "estimated_duration": self.estimated_duration,
            "prerequisites": self.prerequisites,
            "confidence": self.confidence
        }


@dataclass
class OutcomePrediction:
    """結果予測
    
    Attributes:
        prediction_id: 予測ID
        action_name: アクション名
        predicted_result: 予測結果（success/failure/partial）
        success_probability: 成功確率
        failure_probability: 失敗確率
        predicted_duration: 予測所要時間
        predicted_resources: 予測リソース使用量
        potential_issues: 潜在的な問題
        alternative_scenarios: 代替シナリオ
    """
    prediction_id: str
    action_name: str
    predicted_result: str
    success_probability: float
    failure_probability: float
    predicted_duration: float
    predicted_resources: Dict[str, Any]
    potential_issues: List[str]
    alternative_scenarios: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "action_name": self.action_name,
            "predicted_result": self.predicted_result,
            "success_probability": self.success_probability,
            "failure_probability": self.failure_probability,
            "predicted_duration": self.predicted_duration,
            "predicted_resources": self.predicted_resources,
            "potential_issues": self.potential_issues,
            "alternative_scenarios": self.alternative_scenarios
        }


@dataclass
class RiskAssessment:
    """リスク評価
    
    Attributes:
        assessment_id: 評価ID
        action_name: アクション名
        overall_risk_level: 全体的リスクレベル
        risk_score: リスクスコア（0-1）
        risk_factors: リスク要因
        mitigation_strategies: リスク軽減策
        fallback_options: フォールバックオプション
    """
    assessment_id: str
    action_name: str
    overall_risk_level: RiskLevel
    risk_score: float
    risk_factors: List[Dict[str, Any]]
    mitigation_strategies: List[str]
    fallback_options: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "action_name": self.action_name,
            "overall_risk_level": self.overall_risk_level.value,
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors,
            "mitigation_strategies": self.mitigation_strategies,
            "fallback_options": self.fallback_options
        }


@dataclass
class DecisionReport:
    """意思決定レポート
    
    Attributes:
        report_id: レポートID
        situation: 状況評価
        recommendations: アクション推奨リスト
        predictions: 結果予測リスト
        risk_assessments: リスク評価リスト
        overall_confidence: 全体的信頼度
        suggested_action: 推奨アクション
        generated_at: 生成日時
    """
    report_id: str
    situation: SituationAssessment
    recommendations: List[ActionRecommendation]
    predictions: List[OutcomePrediction]
    risk_assessments: List[RiskAssessment]
    overall_confidence: float
    suggested_action: Optional[str]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "situation": self.situation.to_dict(),
            "recommendations": [r.to_dict() for r in self.recommendations],
            "predictions": [p.to_dict() for p in self.predictions],
            "risk_assessments": [ra.to_dict() for ra in self.risk_assessments],
            "overall_confidence": self.overall_confidence,
            "suggested_action": self.suggested_action,
            "generated_at": self.generated_at
        }


class DecisionOptimizer:
    """意思決定最適化エンジン
    
    過去の経験とパターン分析に基づいて最適な意思決定を支援する。
    ExperienceCollector、PatternAnalyzer、SkillSynthesizerと統合する。
    """
    
    def __init__(
        self,
        experience_collector: Optional[ExperienceCollector] = None,
        pattern_analyzer: Optional[PatternAnalyzer] = None,
        skill_synthesizer: Optional[SkillSynthesizer] = None,
        data_dir: str = "data/decision_optimizer"
    ):
        """初期化
        
        Args:
            experience_collector: ExperienceCollectorインスタンス
            pattern_analyzer: PatternAnalyzerインスタンス
            skill_synthesizer: SkillSynthesizerインスタンス
            data_dir: データ保存ディレクトリ
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 各モジュールとの連携
        self.experience_collector = experience_collector or get_experience_collector()
        self.pattern_analyzer = pattern_analyzer or PatternAnalyzer(self.experience_collector)
        self.skill_synthesizer = skill_synthesizer or get_skill_synthesizer()
        
        # 意思決定履歴
        self.decision_history: List[DecisionReport] = []
        
        # キャッシュ
        self._assessment_cache: Dict[str, SituationAssessment] = {}
        self._cache_ttl = timedelta(minutes=10)
        self._cache_timestamps: Dict[str, datetime] = {}
        
        logger.info("DecisionOptimizer initialized")
    
    def evaluate_situation(
        self,
        context: Dict[str, Any],
        days_back: int = 90,
        min_similarity: float = 0.5
    ) -> SituationAssessment:
        """状況を評価
        
        Args:
            context: 現在の状況コンテキスト
            days_back: 過去何日分を検索するか
            min_similarity: 最小類似度
            
        Returns:
            状況評価結果
        """
        assessment_id = str(uuid.uuid4())
        
        # 過去の経験を取得
        recent_experiences = self.experience_collector.get_recent_experiences(days_back=days_back, limit=1000)
        
        # 類似ケースを検索
        similar_cases = self._find_similar_cases(context, recent_experiences, min_similarity)
        
        # パターンを取得してマッチング
        patterns = self.pattern_analyzer.identify_success_patterns(days_back=days_back)
        matching_patterns = self._match_patterns(context, patterns)
        
        # 信頼度スコアを計算
        confidence_score = self._calculate_assessment_confidence(
            len(similar_cases), len(matching_patterns), len(recent_experiences)
        )
        
        assessment = SituationAssessment(
            assessment_id=assessment_id,
            current_context=context,
            similar_cases=similar_cases,
            matching_patterns=matching_patterns,
            confidence_score=confidence_score
        )
        
        # キャッシュに保存
        self._assessment_cache[assessment_id] = assessment
        self._cache_timestamps[assessment_id] = datetime.now()
        
        logger.info(f"Situation evaluated: {assessment_id} (confidence: {confidence_score:.2f})")
        return assessment
    
    def recommend_actions(
        self,
        situation: SituationAssessment,
        max_recommendations: int = 5,
        min_confidence: float = 0.5
    ) -> List[ActionRecommendation]:
        """アクションを推奨
        
        Args:
            situation: 状況評価結果
            max_recommendations: 最大推奨数
            min_confidence: 最小信頼度
            
        Returns:
            アクション推奨リスト
        """
        recommendations: List[ActionRecommendation] = []
        
        # 成功パターンから推奨を生成
        for pattern in situation.matching_patterns[:max_recommendations]:
            if pattern.confidence >= min_confidence:
                rec = self._create_recommendation_from_pattern(pattern, situation)
                recommendations.append(rec)
        
        # 類似ケースから推奨を生成
        for case in situation.similar_cases[:max_recommendations]:
            if case.result == TaskResult.SUCCESS:
                rec = self._create_recommendation_from_case(case, situation)
                if rec.confidence >= min_confidence and not any(
                    r.action_name == rec.action_name for r in recommendations
                ):
                    recommendations.append(rec)
        
        # スキルからの推奨
        synthesized_skills = self.skill_synthesizer.generate_skills_from_patterns(
            min_confidence=min_confidence
        )
        for skill in synthesized_skills[:max_recommendations]:
            rec = self._create_recommendation_from_skill(skill, situation)
            if rec.confidence >= min_confidence:
                recommendations.append(rec)
        
        # 信頼度でソート
        recommendations.sort(key=lambda x: x.confidence, reverse=True)
        
        logger.info(f"Generated {len(recommendations)} action recommendations")
        return recommendations[:max_recommendations]
    
    def predict_outcomes(
        self,
        actions: List[ActionRecommendation],
        situation: SituationAssessment
    ) -> List[OutcomePrediction]:
        """結果を予測
        
        Args:
            actions: アクション推奨リスト
            situation: 状況評価結果
            
        Returns:
            結果予測リスト
        """
        predictions: List[OutcomePrediction] = []
        
        for action in actions:
            prediction = self._predict_single_outcome(action, situation)
            predictions.append(prediction)
        
        logger.info(f"Generated {len(predictions)} outcome predictions")
        return predictions
    
    def assess_risks(
        self,
        actions: List[ActionRecommendation],
        situation: SituationAssessment
    ) -> List[RiskAssessment]:
        """リスクを評価
        
        Args:
            actions: アクション推奨リスト
            situation: 状況評価結果
            
        Returns:
            リスク評価リスト
        """
        assessments: List[RiskAssessment] = []
        
        # 失敗パターンを取得
        failure_patterns = self.pattern_analyzer.classify_failure_patterns()
        
        for action in actions:
            assessment = self._assess_single_risk(action, situation, failure_patterns)
            assessments.append(assessment)
        
        logger.info(f"Generated {len(assessments)} risk assessments")
        return assessments
    
    def generate_decision_report(
        self,
        context: Dict[str, Any],
        days_back: int = 90
    ) -> DecisionReport:
        """意思決定レポートを生成
        
        Args:
            context: 現在の状況コンテキスト
            days_back: 過去何日分を検索するか
            
        Returns:
            意思決定レポート
        """
        report_id = str(uuid.uuid4())
        
        # 状況評価
        situation = self.evaluate_situation(context, days_back)
        
        # アクション推奨
        recommendations = self.recommend_actions(situation)
        
        # 結果予測
        predictions = self.predict_outcomes(recommendations, situation)
        
        # リスク評価
        risk_assessments = self.assess_risks(recommendations, situation)
        
        # 全体的信頼度を計算
        overall_confidence = self._calculate_overall_confidence(
            situation, recommendations, predictions, risk_assessments
        )
        
        # 推奨アクションを決定
        suggested_action = self._determine_suggested_action(
            recommendations, predictions, risk_assessments
        )
        
        report = DecisionReport(
            report_id=report_id,
            situation=situation,
            recommendations=recommendations,
            predictions=predictions,
            risk_assessments=risk_assessments,
            overall_confidence=overall_confidence,
            suggested_action=suggested_action
        )
        
        # 履歴に追加
        self.decision_history.append(report)
        
        logger.info(f"Decision report generated: {report_id} (confidence: {overall_confidence:.2f})")
        return report
    
    def get_decision_history(
        self,
        limit: int = 50,
        min_confidence: Optional[float] = None
    ) -> List[DecisionReport]:
        """意思決定履歴を取得
        
        Args:
            limit: 最大取得数
            min_confidence: 最小信頼度フィルター
            
        Returns:
            意思決定レポートリスト
        """
        history = sorted(
            self.decision_history,
            key=lambda x: x.generated_at,
            reverse=True
        )[:limit]
        
        if min_confidence is not None:
            history = [r for r in history if r.overall_confidence >= min_confidence]
        
        return history
    
    def export_decision_data(self, filepath: Optional[str] = None) -> str:
        """意思決定データをエクスポート
        
        Args:
            filepath: 出力ファイルパス
            
        Returns:
            出力ファイルパス
        """
        if filepath is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filepath = str(self.data_dir / f"decision_export_{timestamp}.json")
        
        export_data = {
            "export_info": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "total_decisions": len(self.decision_history)
            },
            "decisions": [report.to_dict() for report in self.decision_history],
            "statistics": {
                "avg_confidence": sum(r.overall_confidence for r in self.decision_history) / max(len(self.decision_history), 1),
                "high_confidence_decisions": sum(1 for r in self.decision_history if r.overall_confidence >= 0.7)
            }
        }
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Decision data exported to {filepath}")
        return filepath
    
    def get_insights(self) -> Dict[str, Any]:
        """意思決定に関するインサイトを取得
        
        Returns:
            インサイト辞書
        """
        if not self.decision_history:
            return {
                "status": "no_data",
                "message": "No decision history available"
            }
        
        recent_decisions = self.decision_history[-100:]
        
        # 信頼度の統計
        confidence_values = [d.overall_confidence for d in recent_decisions]
        avg_confidence = sum(confidence_values) / len(confidence_values)
        
        # 推奨アクションの分析
        action_frequency: Dict[str, int] = {}
        for decision in recent_decisions:
            if decision.suggested_action:
                action_frequency[decision.suggested_action] = action_frequency.get(decision.suggested_action, 0) + 1
        
        most_common_actions = sorted(
            action_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return {
            "total_decisions": len(self.decision_history),
            "recent_decisions": len(recent_decisions),
            "average_confidence": avg_confidence,
            "confidence_trend": "improving" if len(confidence_values) > 10 and confidence_values[-1] > confidence_values[0] else "stable",
            "most_common_actions": most_common_actions,
            "high_confidence_rate": sum(1 for c in confidence_values if c >= 0.7) / len(confidence_values)
        }
    
    # ==================== プライベートメソッド ====================
    
    def _find_similar_cases(
        self,
        context: Dict[str, Any],
        experiences: List[TaskExecutionRecord],
        min_similarity: float
    ) -> List[TaskExecutionRecord]:
        """類似ケースを検索"""
        similar_cases = []
        
        for exp in experiences:
            similarity = self._calculate_context_similarity(context, exp.context)
            if similarity >= min_similarity:
                similar_cases.append(exp)
        
        # 類似度でソート
        similar_cases.sort(
            key=lambda x: self._calculate_context_similarity(context, x.context),
            reverse=True
        )
        
        return similar_cases[:20]  # 上位20件
    
    def _calculate_context_similarity(
        self,
        context1: Dict[str, Any],
        context2: Dict[str, Any]
    ) -> float:
        """コンテキスト間の類似度を計算"""
        if not context1 or not context2:
            return 0.0
        
        # 共通キーを取得
        common_keys = set(context1.keys()) & set(context2.keys())
        if not common_keys:
            return 0.0
        
        # 各キーの一致度を計算
        matches = 0
        total_weight = 0
        
        for key in common_keys:
            weight = 1.0
            if key in ['task_type', 'category']:
                weight = 2.0  # 重要なキーは重み付け
            
            if context1[key] == context2[key]:
                matches += weight
            total_weight += weight
        
        # キー網羅率も考慮
        coverage = len(common_keys) / max(len(context1), len(context2), 1)
        
        return (matches / max(total_weight, 1)) * coverage
    
    def _match_patterns(
        self,
        context: Dict[str, Any],
        patterns: List[IdentifiedPattern]
    ) -> List[IdentifiedPattern]:
        """パターンをマッチング"""
        matched = []
        
        for pattern in patterns:
            # タスクタイプのマッチング
            context_task_type = context.get('task_type', '')
            pattern_task_type = pattern.metadata.get('task_type', '')
            
            if context_task_type and pattern_task_type and context_task_type == pattern_task_type:
                matched.append(pattern)
            elif pattern.confidence >= 0.7:  # 高信頼度パターンは常に含める
                matched.append(pattern)
        
        return matched[:10]
    
    def _calculate_assessment_confidence(
        self,
        similar_cases_count: int,
        matching_patterns_count: int,
        total_experiences: int
    ) -> float:
        """評価の信頼度を計算"""
        if total_experiences == 0:
            return 0.0
        
        # 類似ケースが多いほど信頼度が上がる
        case_factor = min(similar_cases_count / 10, 1.0)
        
        # マッチングパターンが多いほど信頼度が上がる
        pattern_factor = min(matching_patterns_count / 5, 1.0)
        
        # 経験データの充実度
        data_factor = min(total_experiences / 100, 1.0)
        
        return (case_factor * 0.4 + pattern_factor * 0.4 + data_factor * 0.2)
    
    def _create_recommendation_from_pattern(
        self,
        pattern: IdentifiedPattern,
        situation: SituationAssessment
    ) -> ActionRecommendation:
        """パターンから推奨を生成"""
        # supporting_dataから成功率を取得、ない場合はconfidenceを使用
        success_rate = 0.8  # デフォルト値
        if pattern.supporting_data and len(pattern.supporting_data) > 0:
            success_rate = pattern.supporting_data[0].get('success_rate', 0.8)
        
        return ActionRecommendation(
            recommendation_id=str(uuid.uuid4()),
            action_name=f"Apply_{pattern.name}",
            description=pattern.description,
            priority=ActionPriority.HIGH if pattern.confidence >= 0.8 else ActionPriority.MEDIUM,
            expected_outcome=f"High success rate based on pattern: {pattern.name}",
            estimated_success_rate=success_rate,
            required_resources=pattern.metadata.get('common_resources', {}),
            estimated_duration=pattern.metadata.get('avg_duration', 60.0),
            prerequisites=[],
            confidence=pattern.confidence
        )
    
    def _create_recommendation_from_case(
        self,
        case: TaskExecutionRecord,
        situation: SituationAssessment
    ) -> ActionRecommendation:
        """ケースから推奨を生成"""
        return ActionRecommendation(
            recommendation_id=str(uuid.uuid4()),
            action_name=f"Execute_{case.task_type}",
            description=f"Based on successful execution of {case.task_id}",
            priority=ActionPriority.MEDIUM,
            expected_outcome="Expected to succeed based on similar past execution",
            estimated_success_rate=0.75,
            required_resources=case.resources,
            estimated_duration=case.duration_seconds,
            prerequisites=[],
            confidence=0.6
        )
    
    def _create_recommendation_from_skill(
        self,
        skill: SynthesizedSkill,
        situation: SituationAssessment
    ) -> ActionRecommendation:
        """スキルから推奨を生成"""
        return ActionRecommendation(
            recommendation_id=str(uuid.uuid4()),
            action_name=f"Use_Skill_{skill.name}",
            description=skill.description,
            priority=ActionPriority.HIGH if skill.quality_score >= 0.8 else ActionPriority.MEDIUM,
            expected_outcome=f"Apply synthesized skill: {skill.name}",
            estimated_success_rate=skill.estimated_success_rate,
            required_resources={},
            estimated_duration=60.0,
            prerequisites=skill.prerequisites,
            confidence=skill.confidence
        )
    
    def _predict_single_outcome(
        self,
        action: ActionRecommendation,
        situation: SituationAssessment
    ) -> OutcomePrediction:
        """単一アクションの結果を予測"""
        # 成功確率の調整
        base_success_rate = action.estimated_success_rate
        
        # 状況評価の信頼度で調整
        adjusted_success_rate = base_success_rate * (0.5 + 0.5 * situation.confidence_score)
        adjusted_success_rate = min(adjusted_success_rate, 0.99)
        
        # 類似ケースからの学習
        for case in situation.similar_cases[:5]:
            if case.result == TaskResult.SUCCESS:
                adjusted_success_rate = min(adjusted_success_rate + 0.05, 0.99)
            elif case.result == TaskResult.FAILURE:
                adjusted_success_rate = max(adjusted_success_rate - 0.1, 0.1)
        
        # 予測結果の決定
        if adjusted_success_rate >= 0.7:
            predicted_result = "success"
        elif adjusted_success_rate >= 0.4:
            predicted_result = "partial"
        else:
            predicted_result = "failure"
        
        # 潜在的な問題を特定
        potential_issues = self._identify_potential_issues(action, situation)
        
        # 代替シナリオ
        alternative_scenarios = [
            f"Retry with different approach if {action.action_name} fails",
            "Escalate to human operator if confidence drops below threshold"
        ]
        
        return OutcomePrediction(
            prediction_id=str(uuid.uuid4()),
            action_name=action.action_name,
            predicted_result=predicted_result,
            success_probability=adjusted_success_rate,
            failure_probability=1.0 - adjusted_success_rate,
            predicted_duration=action.estimated_duration * (1.0 + (1.0 - situation.confidence_score) * 0.5),
            predicted_resources=action.required_resources,
            potential_issues=potential_issues,
            alternative_scenarios=alternative_scenarios
        )
    
    def _identify_potential_issues(
        self,
        action: ActionRecommendation,
        situation: SituationAssessment
    ) -> List[str]:
        """潜在的な問題を特定"""
        issues = []
        
        # 前提条件のチェック
        for prereq in action.prerequisites:
            if prereq not in str(situation.current_context):
                issues.append(f"Prerequisite may not be met: {prereq}")
        
        # リソース不足のチェック
        if action.required_resources:
            issues.append("Resource requirements need verification")
        
        # 信頼度が低い場合
        if action.confidence < 0.6:
            issues.append("Low confidence in action recommendation")
        
        return issues
    
    def _assess_single_risk(
        self,
        action: ActionRecommendation,
        situation: SituationAssessment,
        failure_patterns: List[FailurePattern]
    ) -> RiskAssessment:
        """単一アクションのリスクを評価"""
        # 基本リスクスコア
        base_risk = 1.0 - action.estimated_success_rate
        
        # 関連する失敗パターンを検索
        relevant_failures = []
        for pattern in failure_patterns:
            if action.action_name.lower() in pattern.error_signature.lower():
                relevant_failures.append(pattern)
                base_risk += 0.1
        
        # リスクスコアを正規化
        risk_score = min(base_risk, 1.0)
        
        # リスクレベルを決定
        if risk_score >= 0.8:
            risk_level = RiskLevel.CRITICAL
        elif risk_score >= 0.6:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 0.4:
            risk_level = RiskLevel.MEDIUM
        elif risk_score >= 0.2:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.MINIMAL
        
        # リスク要因
        risk_factors = []
        for failure in relevant_failures[:3]:
            risk_factors.append({
                "type": "historical_failure",
                "description": failure.normalized_message,
                "frequency": failure.frequency,
                "severity": failure.severity
            })
        
        if action.confidence < 0.6:
            risk_factors.append({
                "type": "low_confidence",
                "description": "Action recommendation has low confidence",
                "severity": "medium"
            })
        
        # 軽減策
        mitigation_strategies = [
            "Monitor execution closely",
            "Have rollback plan ready",
            "Validate prerequisites before execution"
        ]
        
        if relevant_failures:
            mitigation_strategies.append("Review and apply lessons from past failures")
        
        # フォールバックオプション
        fallback_options = [
            "Retry with modified parameters",
            "Use alternative approach",
            "Request human assistance"
        ]
        
        return RiskAssessment(
            assessment_id=str(uuid.uuid4()),
            action_name=action.action_name,
            overall_risk_level=risk_level,
            risk_score=risk_score,
            risk_factors=risk_factors,
            mitigation_strategies=mitigation_strategies,
            fallback_options=fallback_options
        )
    
    def _calculate_overall_confidence(
        self,
        situation: SituationAssessment,
        recommendations: List[ActionRecommendation],
        predictions: List[OutcomePrediction],
        risk_assessments: List[RiskAssessment]
    ) -> float:
        """全体的信頼度を計算"""
        if not recommendations:
            return situation.confidence_score * 0.5
        
        # 推奨の平均信頼度
        avg_rec_confidence = sum(r.confidence for r in recommendations) / len(recommendations)
        
        # 予測の平均確信度（成功確率の分散から計算）
        success_probs = [p.success_probability for p in predictions]
        if success_probs:
            avg_success_prob = sum(success_probs) / len(success_probs)
            prob_variance = sum((p - avg_success_prob) ** 2 for p in success_probs) / len(success_probs)
            prediction_confidence = 1.0 - min(prob_variance * 4, 1.0)
        else:
            prediction_confidence = 0.5
        
        # リスク評価の信頼度（低リスクほど高信頼度）
        risk_scores = [ra.risk_score for ra in risk_assessments]
        if risk_scores:
            avg_risk = sum(risk_scores) / len(risk_scores)
            risk_confidence = 1.0 - avg_risk
        else:
            risk_confidence = 0.5
        
        # 加重平均
        overall = (
            situation.confidence_score * 0.3 +
            avg_rec_confidence * 0.3 +
            prediction_confidence * 0.2 +
            risk_confidence * 0.2
        )
        
        return overall
    
    def _determine_suggested_action(
        self,
        recommendations: List[ActionRecommendation],
        predictions: List[OutcomePrediction],
        risk_assessments: List[RiskAssessment]
    ) -> Optional[str]:
        """推奨アクションを決定"""
        if not recommendations:
            return None
        
        # スコアリング
        scored_actions = []
        
        for i, rec in enumerate(recommendations):
            pred = predictions[i] if i < len(predictions) else None
            risk = risk_assessments[i] if i < len(risk_assessments) else None
            
            score = rec.confidence * 0.4
            
            if pred:
                score += pred.success_probability * 0.3
            
            if risk:
                score += (1.0 - risk.risk_score) * 0.3
            
            scored_actions.append((rec, score))
        
        # 最高スコアのアクションを選択
        scored_actions.sort(key=lambda x: x[1], reverse=True)
        return scored_actions[0][0].action_name if scored_actions else None


# ==================== グローバルインスタンス ====================

_optimizer_instance: Optional[DecisionOptimizer] = None


def get_decision_optimizer() -> DecisionOptimizer:
    """グローバルDecisionOptimizerインスタンスを取得"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = DecisionOptimizer()
    return _optimizer_instance


def reset_optimizer() -> None:
    """グローバルインスタンスをリセット"""
    global _optimizer_instance
    _optimizer_instance = None


# ==================== 便利なショートカット関数 ====================

def evaluate_and_recommend(
    context: Dict[str, Any],
    days_back: int = 90
) -> Tuple[SituationAssessment, List[ActionRecommendation]]:
    """状況評価と推奨を一括実行
    
    Args:
        context: 現在の状況コンテキスト
        days_back: 過去何日分を検索するか
        
    Returns:
        (状況評価, アクション推奨リスト)
    """
    optimizer = get_decision_optimizer()
    situation = optimizer.evaluate_situation(context, days_back)
    recommendations = optimizer.recommend_actions(situation)
    return situation, recommendations


def get_optimal_decision(context: Dict[str, Any]) -> Optional[ActionRecommendation]:
    """最適な意思決定を取得
    
    Args:
        context: 現在の状況コンテキスト
        
    Returns:
        最適なアクション推奨
    """
    optimizer = get_decision_optimizer()
    report = optimizer.generate_decision_report(context)
    
    if report.recommendations:
        return report.recommendations[0]
    return None


def get_decision_insights() -> Dict[str, Any]:
    """意思決定インサイトを取得
    
    Returns:
        インサイト辞書
    """
    optimizer = get_decision_optimizer()
    return optimizer.get_insights()
