"""
Knowledge-Task Integration
ナレッジ共有とタスク委譲の統合

機能:
1. タスクに最適なナレッジを自動検索・提案
2. タスク実行中のリアルタイムナレッジ取得
3. 実行結果からのナレッジ自動生成
4. ナレッジ品質に基づくタスク推薦

このモジュールは「知識」→「実行」→「学習」→「知識」の循環を実現する。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum

from services.knowledge_sharing import (
    KnowledgeSharingSystem, KnowledgeItem, KnowledgeType
)
from services.coordination_protocol import (
    CoordinationManager, CoordinationSession, CoordinationMessage,
    CoordinationMessageType, Intent
)
from services.l1_protocol import L1TaskDelegation, L1TaskStatus

logger = logging.getLogger(__name__)


class KnowledgeTaskPhase(Enum):
    """ナレッジ-タスク統合フェーズ"""
    KNOWLEDGE_DISCOVERY = "knowledge_discovery"    # ナレッジ発見
    KNOWLEDGE_ACQUISITION = "knowledge_acquisition"  # ナレッジ取得
    TASK_EXECUTION = "task_execution"              # タスク実行
    LEARNING_GENERATION = "learning_generation"    # 学習・生成
    KNOWLEDGE_FEEDBACK = "knowledge_feedback"      # フィードバック


@dataclass
class TaskKnowledgeContext:
    """タスク-ナレッジ統合コンテキスト"""
    context_id: str
    task_id: Optional[str] = None
    coordination_id: Optional[str] = None
    
    # ナレッジ関連
    relevant_knowledge: List[KnowledgeItem] = field(default_factory=list)
    acquired_knowledge: List[KnowledgeItem] = field(default_factory=list)
    generated_knowledge: List[KnowledgeItem] = field(default_factory=list)
    
    # タスク関連
    task_description: str = ""
    required_skills: List[str] = field(default_factory=list)
    execution_notes: List[str] = field(default_factory=list)
    
    # 統合メタデータ
    knowledge_applied_count: int = 0
    knowledge_effectiveness: float = 0.0  # 0.0 ~ 1.0
    
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_id": self.context_id,
            "task_id": self.task_id,
            "coordination_id": self.coordination_id,
            "relevant_knowledge_count": len(self.relevant_knowledge),
            "acquired_knowledge_count": len(self.acquired_knowledge),
            "generated_knowledge_count": len(self.generated_knowledge),
            "task_description": self.task_description[:100] + "..." if len(self.task_description) > 100 else self.task_description,
            "required_skills": self.required_skills,
            "knowledge_applied_count": self.knowledge_applied_count,
            "knowledge_effectiveness": round(self.knowledge_effectiveness, 3),
            "created_at": self.created_at.isoformat()
        }


@dataclass
class KnowledgeRecommendation:
    """ナレッジ推薦"""
    knowledge_item: KnowledgeItem
    relevance_score: float
    confidence: float
    application_suggestion: str
    expected_benefit: str


class KnowledgeTaskIntegrator:
    """ナレッジ-タスク統合マネージャー"""
    
    def __init__(
        self,
        entity_id: str,
        knowledge_manager: KnowledgeSharingSystem,
        coordination_manager: CoordinationManager
    ):
        self.entity_id = entity_id
        self.knowledge = knowledge_manager
        self.coordination = coordination_manager
        
        # コンテキスト管理
        self.contexts: Dict[str, TaskKnowledgeContext] = {}
        
        # ナレッジ適用履歴
        self.application_history: List[Dict[str, Any]] = []
        
        # コールバック
        self.on_knowledge_applied: Optional[Callable] = None
        self.on_knowledge_generated: Optional[Callable] = None
    
    async def prepare_task_with_knowledge(
        self,
        task_description: str,
        required_skills: List[str],
        coordination_id: Optional[str] = None
    ) -> TaskKnowledgeContext:
        """タスク実行前にナレッジを準備"""
        context = TaskKnowledgeContext(
            context_id=str(uuid.uuid4()),
            coordination_id=coordination_id,
            task_description=task_description,
            required_skills=required_skills
        )
        
        # 関連ナレッジを検索
        relevant = await self._search_relevant_knowledge(task_description, required_skills)
        context.relevant_knowledge = relevant
        
        logger.info(
            f"Found {len(relevant)} relevant knowledge items for task: {task_description[:50]}..."
        )
        
        # 高関連ナレッジを自動取得
        for item in relevant:
            if item.quality_score > 0.7:  # 高品質ナレッジのみ
                acquired = await self._acquire_knowledge(item)
                if acquired:
                    context.acquired_knowledge.append(acquired)
        
        self.contexts[context.context_id] = context
        
        return context
    
    async def recommend_knowledge_for_intent(
        self,
        intent: Intent,
        max_recommendations: int = 5
    ) -> List[KnowledgeRecommendation]:
        """意図に対してナレッジを推薦"""
        recommendations = []
        
        # 必要スキルを抽出
        required_skills = intent.requirements.get("skills", [])
        
        # ナレッジを検索
        all_knowledge = await self.knowledge.search_knowledge(
            query=intent.description,
            tags=required_skills
        )
        
        for item in all_knowledge:
            # 関連性スコアを計算
            relevance = self._calculate_knowledge_relevance(item, intent)
            
            if relevance > 0.5:  # 閾値以上のみ
                suggestion = self._generate_application_suggestion(item, intent)
                benefit = self._estimate_benefit(item, intent)
                
                recommendation = KnowledgeRecommendation(
                    knowledge_item=item,
                    relevance_score=relevance,
                    confidence=item.quality_score * relevance,
                    application_suggestion=suggestion,
                    expected_benefit=benefit
                )
                
                recommendations.append(recommendation)
        
        # スコアでソート
        recommendations.sort(key=lambda x: x.confidence, reverse=True)
        
        return recommendations[:max_recommendations]
    
    async def apply_knowledge_during_task(
        self,
        context_id: str,
        situation: str
    ) -> List[KnowledgeRecommendation]:
        """タスク実行中に状況に応じたナレッジを適用"""
        context = self.contexts.get(context_id)
        if not context:
            return []
        
        # 現在の状況に最適なナレッジを検索
        relevant = await self._search_relevant_knowledge(situation, context.required_skills)
        
        recommendations = []
        for item in relevant:
            # 既に取得済みかチェック
            if any(a.item_id == item.item_id for a in context.acquired_knowledge):
                continue
            
            relevance = self._calculate_situation_relevance(item, situation)
            
            if relevance > 0.7:
                # 即座に取得
                acquired = await self._acquire_knowledge(item)
                if acquired:
                    context.acquired_knowledge.append(acquired)
                    context.knowledge_applied_count += 1
                    
                    recommendation = KnowledgeRecommendation(
                        knowledge_item=acquired,
                        relevance_score=relevance,
                        confidence=relevance * acquired.quality_score,
                        application_suggestion=f"Apply to current situation: {situation[:50]}...",
                        expected_benefit="Immediate problem resolution"
                    )
                    recommendations.append(recommendation)
        
        # 履歴に記録
        if recommendations:
            self.application_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "context_id": context_id,
                "situation": situation,
                "applied_knowledge_count": len(recommendations)
            })
        
        # コールバック実行
        if self.on_knowledge_applied:
            await self.on_knowledge_applied(context, recommendations)
        
        return recommendations
    
    async def generate_knowledge_from_execution(
        self,
        context_id: str,
        execution_result: Dict[str, Any],
        effectiveness: float
    ) -> Optional[KnowledgeItem]:
        """実行結果からナレッジを生成"""
        context = self.contexts.get(context_id)
        if not context:
            return None
        
        # 効果が低い場合は学習価値が低い
        if effectiveness < 0.3:
            logger.info("Execution effectiveness too low, skipping knowledge generation")
            return None
        
        # ナレッジアイテムを作成
        knowledge_item = KnowledgeItem(
            item_id=str(uuid.uuid4()),
            item_type=KnowledgeType.EXPERIENCE,
            entity_id=self.entity_id,
            title=f"Execution experience: {context.task_description[:50]}...",
            description=f"Learned from executing task with {effectiveness:.2f} effectiveness",
            content={
                "task_description": context.task_description,
                "required_skills": context.required_skills,
                "execution_result": execution_result,
                "knowledge_applied": [k.item_id for k in context.acquired_knowledge],
                "effectiveness": effectiveness
            },
            tags=context.required_skills + ["generated", "experience"],
            quality_score=effectiveness,
            status=KnowledgeStatus.PRIVATE  # 初期は非公開
        )
        
        # ナレッジを保存
        await self.knowledge.publish_knowledge(knowledge_item)
        
        context.generated_knowledge.append(knowledge_item)
        context.knowledge_effectiveness = effectiveness
        
        logger.info(f"Generated new knowledge item: {knowledge_item.item_id}")
        
        # コールバック実行
        if self.on_knowledge_generated:
            await self.on_knowledge_generated(knowledge_item, context)
        
        return knowledge_item
    
    async def share_execution_knowledge(
        self,
        context_id: str,
        target_entities: List[str],
        share_threshold: float = 0.7
    ) -> bool:
        """実行ナレッジを他エンティティと共有"""
        context = self.contexts.get(context_id)
        if not context:
            return False
        
        # 高品質なナレッジのみ共有
        for knowledge in context.generated_knowledge:
            if knowledge.quality_score >= share_threshold:
                # ナレッジを公開
                await self.knowledge.update_knowledge_status(
                    knowledge.item_id,
                    KnowledgeStatus.PUBLISHED
                )
                
                # 特定エンティティに通知
                for entity_id in target_entities:
                    await self.knowledge.notify_knowledge_available(
                        entity_id=entity_id,
                        knowledge_id=knowledge.item_id,
                        reason="Relevant to your interests based on execution history"
                    )
                
                logger.info(f"Shared knowledge {knowledge.item_id} with {len(target_entities)} entities")
        
        return True
    
    async def find_best_knowledge_sources(
        self,
        skill_requirements: List[str],
        min_quality: float = 0.6
    ) -> List[Tuple[str, float]]:
        """最適なナレッジソースを発見"""
        sources = []
        
        # ナレッジを検索
        all_knowledge = await self.knowledge.search_knowledge_by_tags(skill_requirements)
        
        # エンティティごとに集計
        entity_scores: Dict[str, List[float]] = {}
        entity_counts: Dict[str, int] = {}
        
        for item in all_knowledge:
            if item.quality_score < min_quality:
                continue
            
            entity_id = item.entity_id
            
            if entity_id not in entity_scores:
                entity_scores[entity_id] = []
                entity_counts[entity_id] = 0
            
            entity_scores[entity_id].append(item.quality_score)
            entity_counts[entity_id] += 1
        
        # スコア計算（品質 × 数）
        for entity_id, scores in entity_scores.items():
            avg_quality = sum(scores) / len(scores)
            count_factor = min(entity_counts[entity_id] / 10, 1.0)  # 最大10件で飽和
            composite_score = avg_quality * 0.7 + count_factor * 0.3
            
            sources.append((entity_id, composite_score))
        
        # スコアでソート
        sources.sort(key=lambda x: x[1], reverse=True)
        
        return sources
    
    async def integrate_with_coordination(
        self,
        coordination_id: str
    ) -> Optional[TaskKnowledgeContext]:
        """協調セッションと統合"""
        session = self.coordination.get_session(coordination_id)
        if not session or not session.intent:
            return None
        
        # タスク準備
        context = await self.prepare_task_with_knowledge(
            task_description=session.intent.description,
            required_skills=session.intent.requirements.get("skills", []),
            coordination_id=coordination_id
        )
        
        # ナレッジ推薦
        recommendations = await self.recommend_knowledge_for_intent(session.intent)
        
        logger.info(
            f"Integrated with coordination {coordination_id}: "
            f"{len(recommendations)} knowledge recommendations"
        )
        
        return context
    
    def get_learning_statistics(self) -> Dict[str, Any]:
        """学習統計を取得"""
        total_contexts = len(self.contexts)
        total_applications = sum(c.knowledge_applied_count for c in self.contexts.values())
        avg_effectiveness = sum(
            c.knowledge_effectiveness for c in self.contexts.values()
        ) / total_contexts if total_contexts > 0 else 0
        
        return {
            "total_task_contexts": total_contexts,
            "total_knowledge_applications": total_applications,
            "average_effectiveness": round(avg_effectiveness, 3),
            "knowledge_generated": sum(
                len(c.generated_knowledge) for c in self.contexts.values()
            ),
            "top_skills": self._get_top_skills(),
            "learning_trend": self._calculate_learning_trend()
        }
    
    async def _search_relevant_knowledge(
        self,
        query: str,
        skills: List[str]
    ) -> List[KnowledgeItem]:
        """関連ナレッジを検索"""
        # ローカルナレッジ
        local = await self.knowledge.list_knowledge()
        
        # スキルタグでフィルタ
        relevant = [
            k for k in local
            if any(s in k.tags for s in skills) or s in k.title.lower()
        ]
        
        return relevant
    
    async def _acquire_knowledge(self, item: KnowledgeItem) -> Optional[KnowledgeItem]:
        """ナレッジを取得"""
        # 実際の取得処理
        # ここでは簡易的にコピーを返す
        from copy import deepcopy
        acquired = deepcopy(item)
        acquired.status = KnowledgeStatus.ACQUIRED
        acquired.source_entity = item.entity_id
        return acquired
    
    def _calculate_knowledge_relevance(
        self,
        item: KnowledgeItem,
        intent: Intent
    ) -> float:
        """ナレッジと意図の関連性を計算"""
        # スキルタグの重複
        required = set(intent.requirements.get("skills", []))
        available = set(item.tags)
        
        if not required:
            return 0.5
        
        overlap = len(required & available)
        skill_score = overlap / len(required)
        
        # 品質スコア
        quality_score = item.quality_score
        
        # 使用頻度（人気度）
        usage_score = min(item.usage_count / 10, 1.0)
        
        return skill_score * 0.5 + quality_score * 0.3 + usage_score * 0.2
    
    def _calculate_situation_relevance(
        self,
        item: KnowledgeItem,
        situation: str
    ) -> float:
        """状況との関連性を計算"""
        # キーワードマッチング（簡易実装）
        situation_words = set(situation.lower().split())
        item_words = set(item.title.lower().split() + item.description.lower().split())
        
        if not situation_words:
            return 0.0
        
        overlap = len(situation_words & item_words)
        return overlap / len(situation_words)
    
    def _generate_application_suggestion(
        self,
        item: KnowledgeItem,
        intent: Intent
    ) -> str:
        """適用提案を生成"""
        return f"Use '{item.title}' for {intent.description[:50]}..."
    
    def _estimate_benefit(
        self,
        item: KnowledgeItem,
        intent: Intent
    ) -> str:
        """期待効果を推定"""
        if item.quality_score > 0.8:
            return "Significant improvement in execution quality"
        elif item.quality_score > 0.6:
            return "Moderate improvement, reduced execution time"
        else:
            return "Basic guidance available"
    
    def _get_top_skills(self) -> List[Tuple[str, int]]:
        """トップスキルを取得"""
        skill_counts: Dict[str, int] = {}
        
        for context in self.contexts.values():
            for skill in context.required_skills:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
        
        sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_skills[:5]
    
    def _calculate_learning_trend(self) -> str:
        """学習トレンドを計算"""
        if len(self.contexts) < 3:
            return "insufficient_data"
        
        # 時系列でソート
        sorted_contexts = sorted(
            self.contexts.values(),
            key=lambda c: c.created_at
        )
        
        # 前半と後半で効果を比較
        mid = len(sorted_contexts) // 2
        first_avg = sum(c.knowledge_effectiveness for c in sorted_contexts[:mid]) / mid
        second_avg = sum(c.knowledge_effectiveness for c in sorted_contexts[mid:]) / (len(sorted_contexts) - mid)
        
        diff = second_avg - first_avg
        
        if diff > 0.1:
            return "improving"
        elif diff < -0.1:
            return "declining"
        else:
            return "stable"


import uuid  # インポート追加


# グローバルインスタンス
_integrator_instance: Optional[KnowledgeTaskIntegrator] = None


def get_knowledge_task_integrator(
    entity_id: Optional[str] = None,
    knowledge_manager: Optional[KnowledgeSharingSystem] = None,
    coordination_manager: Optional[CoordinationManager] = None
) -> KnowledgeTaskIntegrator:
    """グローバル統合マネージャーインスタンスを取得"""
    global _integrator_instance
    if _integrator_instance is None:
        if entity_id is None or knowledge_manager is None or coordination_manager is None:
            raise ValueError("All parameters required for initialization")
        _integrator_instance = KnowledgeTaskIntegrator(
            entity_id=entity_id,
            knowledge_manager=knowledge_manager,
            coordination_manager=coordination_manager
        )
    return _integrator_instance
