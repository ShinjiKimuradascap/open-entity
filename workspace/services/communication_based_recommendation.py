"""
Communication-Based Trust Scoring & Partner Recommendation
コミュニケーション履歴に基づく信頼性スコアと取引相手推薦

機能:
1. コミュニケーション履歴の分析
2. 信頼性スコアの計算（コミュニケーション品質 + 取引実績）
3. 最適な取引相手の推薦
4. リスク評価
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from collections import defaultdict
import math

from services.coordination_protocol import CoordinationManager, CoordinationSession
from services.reputation_manager import ReputationManager

logger = logging.getLogger(__name__)


@dataclass
class CommunicationMetrics:
    """コミュニケーションメトリクス"""
    # 応答性
    avg_response_time_seconds: float = 0.0
    response_rate: float = 0.0  # 応答率
    
    # 明確性
    message_clarity_score: float = 0.0  # メッセージ明確性
    detail_completeness: float = 0.0  # 詳細度
    
    # 協調性
    acceptance_rate: float = 0.0  # 提案受諾率
    counter_proposal_rate: float = 0.0  # カウンタープロポーザル率
    conflict_resolution_ability: float = 0.0  # 紛争解決能力
    
    # 継続性
    session_completion_rate: float = 0.0  # セッション完了率
    drop_off_rate: float = 0.0  # 途中離脱率
    
    # 時間的傾向
    trend_score: float = 0.0  # 改善傾向スコア (-1.0 ~ 1.0)


@dataclass
class TrustScore:
    """信頼性スコア"""
    entity_id: str
    overall_score: float = 0.0  # 0.0 ~ 1.0
    communication_score: float = 0.0
    transaction_score: float = 0.0
    consistency_score: float = 0.0  # 一貫性
    
    # 詳細メトリクス
    metrics: CommunicationMetrics = field(default_factory=CommunicationMetrics)
    
    # 履歴
    interaction_count: int = 0
    first_interaction: Optional[datetime] = None
    last_interaction: Optional[datetime] = None
    
    # スコア履歴（時系列）
    score_history: List[Tuple[datetime, float]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "overall_score": round(self.overall_score, 3),
            "communication_score": round(self.communication_score, 3),
            "transaction_score": round(self.transaction_score, 3),
            "consistency_score": round(self.consistency_score, 3),
            "interaction_count": self.interaction_count,
            "first_interaction": self.first_interaction.isoformat() if self.first_interaction else None,
            "last_interaction": self.last_interaction.isoformat() if self.last_interaction else None,
            "metrics": {
                "avg_response_time": self.metrics.avg_response_time_seconds,
                "response_rate": self.metrics.response_rate,
                "completion_rate": self.metrics.session_completion_rate
            }
        }


@dataclass
class PartnerRecommendation:
    """パートナー推薦結果"""
    entity_id: str
    trust_score: float
    match_score: float  # タスクとのマッチ度
    composite_score: float  # 総合スコア
    
    # 推薦理由
    reasons: List[str] = field(default_factory=list)
    
    # リスク評価
    risk_level: str = "medium"  # low/medium/high
    risk_factors: List[str] = field(default_factory=list)
    
    # 推奨アクション
    recommended_action: str = "proceed"  # proceed/caution/avoid
    suggested_escrow_deposit: float = 1.0  # 1.0 = 100%


class CommunicationBasedTrustScorer:
    """コミュニケーション履歴に基づく信頼性スコアリング"""
    
    def __init__(
        self,
        entity_id: str,
        coordination_manager: CoordinationManager,
        reputation_manager: Optional[ReputationManager] = None
    ):
        self.entity_id = entity_id
        self.coordination = coordination_manager
        self.reputation = reputation_manager
        
        # 信頼スコアキャッシュ
        self.trust_scores: Dict[str, TrustScore] = {}
        
        # 履歴データ
        self.interaction_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # 重み設定
        self.weights = {
            "communication": 0.35,
            "transaction": 0.35,
            "consistency": 0.20,
            "longevity": 0.10
        }
    
    async def analyze_communication_history(
        self,
        partner_id: str,
        lookback_days: int = 30
    ) -> CommunicationMetrics:
        """特定パートナーとのコミュニケーション履歴を分析"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        
        # 該当パートナーとのセッションを取得
        sessions = self._get_sessions_with_partner(partner_id, cutoff_date)
        
        if not sessions:
            return CommunicationMetrics()
        
        metrics = CommunicationMetrics()
        
        # 応答性の計算
        response_times = []
        total_messages = 0
        responded_messages = 0
        
        for session in sessions:
            messages = session.get("messages", [])
            for i, msg in enumerate(messages):
                total_messages += 1
                if msg.get("sender_id") == partner_id:
                    responded_messages += 1
                    
                    # 応答時間を計算
                    if i > 0:
                        prev_time = self._parse_timestamp(messages[i-1].get("timestamp"))
                        curr_time = self._parse_timestamp(msg.get("timestamp"))
                        if prev_time and curr_time:
                            response_time = (curr_time - prev_time).total_seconds()
                            response_times.append(response_time)
        
        if response_times:
            metrics.avg_response_time_seconds = sum(response_times) / len(response_times)
        metrics.response_rate = responded_messages / total_messages if total_messages > 0 else 0
        
        # 明確性の計算
        clarity_scores = []
        detail_scores = []
        
        for session in sessions:
            for msg in session.get("messages", []):
                if msg.get("sender_id") == partner_id:
                    payload = msg.get("payload", {})
                    # ペイロードの詳細度
                    detail_score = min(len(str(payload)) / 500, 1.0)
                    detail_scores.append(detail_score)
                    
                    # 明確性（構造化されているか）
                    clarity = 1.0 if isinstance(payload, dict) and len(payload) > 0 else 0.5
                    clarity_scores.append(clarity)
        
        if clarity_scores:
            metrics.message_clarity_score = sum(clarity_scores) / len(clarity_scores)
        if detail_scores:
            metrics.detail_completeness = sum(detail_scores) / len(detail_scores)
        
        # 協調性の計算
        acceptance_count = 0
        counter_count = 0
        total_proposals = 0
        
        for session in sessions:
            for msg in session.get("messages", []):
                if msg.get("sender_id") == partner_id:
                    msg_type = msg.get("message_type", "")
                    if "ACCEPTANCE" in msg_type:
                        acceptance_count += 1
                    elif "COUNTER" in msg_type:
                        counter_count += 1
                    if "PROPOSAL" in msg_type:
                        total_proposals += 1
        
        if total_proposals > 0:
            metrics.acceptance_rate = acceptance_count / total_proposals
            metrics.counter_proposal_rate = counter_count / total_proposals
        
        # 継続性の計算
        completed_sessions = sum(
            1 for s in sessions
            if s.get("phase") == "completion"
        )
        metrics.session_completion_rate = completed_sessions / len(sessions) if sessions else 0
        metrics.drop_off_rate = 1 - metrics.session_completion_rate
        
        # トレンド計算
        metrics.trend_score = self._calculate_trend(sessions)
        
        return metrics
    
    async def calculate_trust_score(self, partner_id: str) -> TrustScore:
        """特定パートナーの信頼性スコアを計算"""
        # コミュニケーションメトリクスを取得
        comm_metrics = await self.analyze_communication_history(partner_id)
        
        # 既存のスコアを取得または新規作成
        if partner_id in self.trust_scores:
            score = self.trust_scores[partner_id]
        else:
            score = TrustScore(entity_id=partner_id)
        
        # コミュニケーションスコアを計算
        comm_score = self._calculate_communication_score(comm_metrics)
        
        # 取引スコアを取得（評価システム連携）
        tx_score = 0.5
        if self.reputation:
            tx_score = await self.reputation.get_reputation(partner_id)
        
        # 一貫性スコア
        consistency = self._calculate_consistency_score(comm_metrics)
        
        # 長期的信頼性
        longevity = self._calculate_longevity_score(partner_id)
        
        # 総合スコア
        overall = (
            self.weights["communication"] * comm_score +
            self.weights["transaction"] * tx_score +
            self.weights["consistency"] * consistency +
            self.weights["longevity"] * longevity
        )
        
        score.communication_score = comm_score
        score.transaction_score = tx_score
        score.consistency_score = consistency
        score.overall_score = overall
        score.metrics = comm_metrics
        
        # スコア履歴を更新
        score.score_history.append((datetime.now(timezone.utc), overall))
        score.last_interaction = datetime.now(timezone.utc)
        if score.first_interaction is None:
            score.first_interaction = score.last_interaction
        
        self.trust_scores[partner_id] = score
        
        return score
    
    async def recommend_partners(
        self,
        required_capabilities: List[str],
        min_trust_score: float = 0.5,
        max_results: int = 5
    ) -> List[PartnerRecommendation]:
        """最適なパートナーを推薦"""
        recommendations = []
        
        # 候補となるエンティティを発見
        candidates = await self._discover_candidates(required_capabilities)
        
        for candidate_id in candidates:
            # 信頼スコアを計算
            trust = await self.calculate_trust_score(candidate_id)
            
            # 最低スコアチェック
            if trust.overall_score < min_trust_score:
                continue
            
            # マッチスコアを計算
            match_score = self._calculate_capability_match(
                candidate_id, required_capabilities
            )
            
            # 総合スコア
            composite = trust.overall_score * 0.6 + match_score * 0.4
            
            # 推薦理由を生成
            reasons = self._generate_recommendation_reasons(trust, match_score)
            
            # リスク評価
            risk_level, risk_factors = self._assess_risk(trust)
            
            # アクション推奨
            action, escrow = self._recommend_action(trust, risk_level)
            
            recommendation = PartnerRecommendation(
                entity_id=candidate_id,
                trust_score=trust.overall_score,
                match_score=match_score,
                composite_score=composite,
                reasons=reasons,
                risk_level=risk_level,
                risk_factors=risk_factors,
                recommended_action=action,
                suggested_escrow_deposit=escrow
            )
            
            recommendations.append(recommendation)
        
        # 総合スコアでソート
        recommendations.sort(key=lambda x: x.composite_score, reverse=True)
        
        return recommendations[:max_results]
    
    def get_trust_report(self, partner_id: str) -> Dict[str, Any]:
        """信頼性レポートを生成"""
        score = self.trust_scores.get(partner_id)
        if not score:
            return {"error": "No trust data available"}
        
        return {
            "entity_id": partner_id,
            "trust_assessment": score.to_dict(),
            "recommendation": self._get_recommendation_text(score),
            "risk_analysis": {
                "level": "low" if score.overall_score > 0.8 else "medium" if score.overall_score > 0.5 else "high",
                "factors": self._identify_risk_factors(score)
            },
            "improvement_suggestions": self._suggest_improvements(score)
        }
    
    def _get_sessions_with_partner(
        self,
        partner_id: str,
        cutoff_date: datetime
    ) -> List[Dict[str, Any]]:
        """パートナーとのセッションを取得"""
        sessions = []
        for session in self.coordination.sessions.values():
            if partner_id in session.participants:
                if session.created_at >= cutoff_date:
                    sessions.append(session.to_dict())
        return sessions
    
    def _parse_timestamp(self, ts: Optional[str]) -> Optional[datetime]:
        """タイムスタンプ文字列をパース"""
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except:
            return None
    
    def _calculate_trend(self, sessions: List[Dict[str, Any]]) -> float:
        """改善傾向を計算 (-1.0 ~ 1.0)"""
        if len(sessions) < 2:
            return 0.0
        
        # セッションを時系列でソート
        sorted_sessions = sorted(sessions, key=lambda s: s.get("created_at", ""))
        
        # 前半と後半で完了率を比較
        mid = len(sorted_sessions) // 2
        first_half = sorted_sessions[:mid]
        second_half = sorted_sessions[mid:]
        
        first_completion = sum(
            1 for s in first_half if s.get("phase") == "completion"
        ) / len(first_half) if first_half else 0
        
        second_completion = sum(
            1 for s in second_half if s.get("phase") == "completion"
        ) / len(second_half) if second_half else 0
        
        return (second_completion - first_completion) * 2  # -1.0 ~ 1.0
    
    def _calculate_communication_score(self, metrics: CommunicationMetrics) -> float:
        """コミュニケーションスコアを計算"""
        # 応答性スコア（短い応答時間が良い）
        response_score = 1.0
        if metrics.avg_response_time_seconds > 0:
            response_score = max(0, 1 - (metrics.avg_response_time_seconds / 300))
        
        # 各要素の重み付け
        score = (
            response_score * 0.25 +
            metrics.response_rate * 0.20 +
            metrics.message_clarity_score * 0.15 +
            metrics.session_completion_rate * 0.25 +
            max(0, metrics.trend_score) * 0.15  # トレンドは正のみ
        )
        
        return min(1.0, max(0.0, score))
    
    def _calculate_consistency_score(self, metrics: CommunicationMetrics) -> float:
        """一貫性スコアを計算"""
        # 変動が少ないほど高スコア
        variance = (
            (1 - metrics.response_rate) ** 2 +
            metrics.drop_off_rate ** 2
        ) / 2
        
        return max(0, 1 - math.sqrt(variance))
    
    def _calculate_longevity_score(self, partner_id: str) -> float:
        """長期的信頼性スコア"""
        history = self.interaction_history.get(partner_id, [])
        if not history:
            return 0.5
        
        # インタラクション数に基づく
        count_score = min(len(history) / 10, 1.0)
        
        # 継続期間
        timestamps = [
            self._parse_timestamp(h.get("timestamp"))
            for h in history
        ]
        timestamps = [t for t in timestamps if t]
        
        if len(timestamps) >= 2:
            duration = (max(timestamps) - min(timestamps)).days
            duration_score = min(duration / 30, 1.0)
        else:
            duration_score = 0.0
        
        return count_score * 0.6 + duration_score * 0.4
    
    async def _discover_candidates(self, required_capabilities: List[str]) -> Set[str]:
        """候補エンティティを発見"""
        candidates = set()
        
        # 過去の協調セッションから
        for session in self.coordination.sessions.values():
            for participant_id, capability in session.participants.items():
                if participant_id != self.entity_id:
                    # スキルタグをチェック
                    if any(
                        cap in capability.skill_tags
                        for cap in required_capabilities
                    ):
                        candidates.add(participant_id)
        
        return candidates
    
    def _calculate_capability_match(
        self,
        candidate_id: str,
        required: List[str]
    ) -> float:
        """能力マッチ度を計算"""
        # 実際の実装では、候補のCapabilityを取得して比較
        # ここでは簡易実装
        return 0.7  # デフォルト
    
    def _generate_recommendation_reasons(
        self,
        trust: TrustScore,
        match_score: float
    ) -> List[str]:
        """推薦理由を生成"""
        reasons = []
        
        if trust.overall_score > 0.8:
            reasons.append("Excellent trust score from past interactions")
        elif trust.overall_score > 0.6:
            reasons.append("Good trust score from past interactions")
        
        if trust.metrics.avg_response_time_seconds < 60:
            reasons.append("Fast responder (avg < 1 min)")
        
        if trust.metrics.session_completion_rate > 0.9:
            reasons.append("High completion rate (90%+)")
        
        if match_score > 0.8:
            reasons.append("Strong capability match")
        
        if trust.metrics.trend_score > 0.2:
            reasons.append("Improving trend in recent interactions")
        
        return reasons if reasons else ["Moderate candidate based on available data"]
    
    def _assess_risk(self, trust: TrustScore) -> Tuple[str, List[str]]:
        """リスク評価"""
        factors = []
        level = "medium"
        
        if trust.metrics.drop_off_rate > 0.3:
            factors.append("High drop-off rate")
        
        if trust.metrics.response_rate < 0.7:
            factors.append("Low response rate")
        
        if trust.overall_score < 0.5:
            level = "high"
            factors.append("Low overall trust score")
        elif trust.overall_score > 0.8 and not factors:
            level = "low"
        
        return level, factors
    
    def _recommend_action(self, trust: TrustScore, risk_level: str) -> Tuple[str, float]:
        """推奨アクションを決定"""
        if risk_level == "low":
            return "proceed", 0.8
        elif risk_level == "medium":
            return "caution", 1.0
        else:
            return "avoid", 1.5
    
    def _get_recommendation_text(self, score: TrustScore) -> str:
        """推薦テキストを生成"""
        if score.overall_score > 0.8:
            return "Highly recommended partner"
        elif score.overall_score > 0.6:
            return "Recommended partner with minor caveats"
        elif score.overall_score > 0.4:
            return "Proceed with caution"
        else:
            return "Not recommended based on history"
    
    def _identify_risk_factors(self, score: TrustScore) -> List[str]:
        """リスク要因を特定"""
        factors = []
        
        if score.metrics.response_rate < 0.5:
            factors.append("Unresponsive in past interactions")
        
        if score.metrics.session_completion_rate < 0.5:
            factors.append("High likelihood of not completing")
        
        if score.metrics.trend_score < -0.3:
            factors.append("Declining performance trend")
        
        return factors
    
    def _suggest_improvements(self, score: TrustScore) -> List[str]:
        """改善提案を生成"""
        suggestions = []
        
        if score.metrics.avg_response_time_seconds > 300:
            suggestions.append("Consider faster response times")
        
        if score.metrics.message_clarity_score < 0.6:
            suggestions.append("Improve message clarity and detail")
        
        if score.metrics.trend_score < 0:
            suggestions.append("Address declining performance")
        
        return suggestions


# グローバルインスタンス
_scorer_instance: Optional[CommunicationBasedTrustScorer] = None


def get_trust_scorer(
    entity_id: Optional[str] = None,
    coordination_manager: Optional[CoordinationManager] = None
) -> CommunicationBasedTrustScorer:
    """グローバルトラストスコアラーインスタンスを取得"""
    global _scorer_instance
    if _scorer_instance is None:
        if entity_id is None or coordination_manager is None:
            raise ValueError("entity_id and coordination_manager required for initialization")
        _scorer_instance = CommunicationBasedTrustScorer(
            entity_id=entity_id,
            coordination_manager=coordination_manager
        )
    return _scorer_instance
