#!/usr/bin/env python3
"""
自動マッチング・評価システム統合モジュール (L2 Phase 2)

TaskMarketplaceと連携した自動マッチングと品質評価の統合システム
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from .matching_engine import ServiceMatchingEngine, MatchCriteria, MatchResult
from .order_book import OrderBook, ServiceOrder, OrderStatus
from .reputation_engine import ReputationEngine
from .service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


class EvaluationStatus(Enum):
    """評価ステータス"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskEvaluation:
    """タスク評価結果"""
    order_id: str
    provider_id: str
    buyer_id: str
    status: EvaluationStatus
    quality_score: float = 0.0  # 0-10
    completion_score: float = 0.0  # 0-10
    timeliness_score: float = 0.0  # 0-10
    communication_score: float = 0.0  # 0-10
    overall_score: float = 0.0  # 0-10
    feedback: str = ""
    evaluated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AutoMatchConfig:
    """自動マッチング設定"""
    enabled: bool = True
    auto_match_threshold: float = 0.8  # このスコア以上で自動マッチング
    max_auto_match_price: Decimal = Decimal("1000")
    require_reputation_min: float = 0.5
    evaluation_timeout_hours: int = 24
    quality_threshold: float = 7.0  # 品質スコアの閾値


class AutoMatchingEvaluator:
    """
    自動マッチング・評価システム
    
    機能:
    1. 注文に対する自動プロバイダーマッチング
    2. タスク完了後の自動評価
    3. 評価に基づく評判スコア更新
    4. 品質閾値に基づくインセンティブ/ペナルティ
    """
    
    def __init__(
        self,
        matching_engine: ServiceMatchingEngine,
        order_book: OrderBook,
        reputation_engine: ReputationEngine,
        config: Optional[AutoMatchConfig] = None
    ):
        self._matching_engine = matching_engine
        self._order_book = order_book
        self._reputation_engine = reputation_engine
        self._config = config or AutoMatchConfig()
        
        # 評価待ちタスク
        self._pending_evaluations: Dict[str, TaskEvaluation] = {}
        
        # コールバック
        self._on_match_callbacks: List[Callable] = []
        self._on_evaluate_callbacks: List[Callable] = []
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        logger.info("AutoMatchingEvaluator initialized")
    
    async def start(self):
        """自動マッチング・評価ループを開始"""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._processing_loop())
        logger.info("AutoMatchingEvaluator started")
    
    async def stop(self):
        """自動マッチング・評価ループを停止"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AutoMatchingEvaluator stopped")
    
    async def _processing_loop(self):
        """メイン処理ループ"""
        while self._running:
            try:
                # 1. マッチング待ちの注文を処理
                await self._process_pending_orders()
                
                # 2. 評価待ちのタスクを処理
                await self._process_pending_evaluations()
                
                # 3. 定期的な評価スコア更新
                await self._update_reputation_scores()
                
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
            
            await asyncio.sleep(30)  # 30秒ごとにチェック
    
    async def _process_pending_orders(self):
        """マッチング待ちの注文を自動マッチング"""
        if not self._config.enabled:
            return
        
        # PENDING状態の注文を取得
        pending_orders = await self._order_book.get_orders_by_status(OrderStatus.PENDING)
        
        for order in pending_orders:
            # 自動マッチング条件をチェック
            order_max_price = order.total_amount
            if order_max_price > self._config.max_auto_match_price:
                continue
            
            # マッチング実行
            criteria = MatchCriteria(
                required_capabilities=order.requirements.get("capabilities", []),
                max_price=order_max_price,
                min_reputation=self._config.require_reputation_min,
                strategy=order.requirements.get("strategy", "balanced")
            )
            
            result = await self._matching_engine.find_matches(criteria, limit=5)
            
            if result.success and result.top_match:
                top = result.top_match
                
                # 自動マッチングスコア閾値をチェック
                if top.score >= self._config.auto_match_threshold:
                    await self._execute_auto_match(order, top)
    
    async def _execute_auto_match(self, order: ServiceOrder, match: Any):
        """自動マッチングを実行"""
        try:
            logger.info(f"Auto-matching order {order.id} with provider {match.provider_id}")
            
            # 注文をプロバイダーにアサイン
            await self._order_book.assign_provider(order.id, match.provider_id)
            
            # コールバックを実行
            for callback in self._on_match_callbacks:
                try:
                    await callback(order, match)
                except Exception as e:
                    logger.error(f"Match callback error: {e}")
            
        except Exception as e:
            logger.error(f"Auto-match execution failed: {e}")
    
    async def submit_task_result(
        self,
        order_id: str,
        result_data: Dict[str, Any],
        provider_id: str
    ) -> TaskEvaluation:
        """
        タスク結果を提出して評価を開始
        
        Args:
            order_id: 注文ID
            result_data: タスク結果データ
            provider_id: プロバイダーID
            
        Returns:
            TaskEvaluation: 評価オブジェクト
        """
        evaluation = TaskEvaluation(
            order_id=order_id,
            provider_id=provider_id,
            buyer_id=result_data.get("buyer_id", ""),
            status=EvaluationStatus.PENDING
        )
        
        self._pending_evaluations[order_id] = evaluation
        
        logger.info(f"Task result submitted for evaluation: {order_id}")
        
        # 非同期で評価を実行
        asyncio.create_task(self._evaluate_task(order_id, result_data))
        
        return evaluation
    
    async def _evaluate_task(self, order_id: str, result_data: Dict[str, Any]):
        """タスクを評価"""
        evaluation = self._pending_evaluations.get(order_id)
        if not evaluation:
            return
        
        try:
            evaluation.status = EvaluationStatus.IN_PROGRESS
            
            # 1. 自動評価スコアリング
            scores = await self._calculate_auto_scores(order_id, result_data)
            
            evaluation.quality_score = scores.get("quality", 0)
            evaluation.completion_score = scores.get("completion", 0)
            evaluation.timeliness_score = scores.get("timeliness", 0)
            evaluation.communication_score = scores.get("communication", 0)
            
            # 総合スコア計算
            evaluation.overall_score = (
                evaluation.quality_score * 0.4 +
                evaluation.completion_score * 0.3 +
                evaluation.timeliness_score * 0.2 +
                evaluation.communication_score * 0.1
            )
            
            evaluation.status = EvaluationStatus.COMPLETED
            evaluation.evaluated_at = datetime.utcnow()
            
            # 2. 評判スコア更新
            await self._update_provider_reputation(evaluation)
            
            # 3. インセンティブ/ペナルティ適用
            await self._apply_incentive_or_penalty(evaluation)
            
            # コールバック実行
            for callback in self._on_evaluate_callbacks:
                try:
                    await callback(evaluation)
                except Exception as e:
                    logger.error(f"Evaluate callback error: {e}")
            
            logger.info(f"Task evaluation completed: {order_id} - Score: {evaluation.overall_score}")
            
        except Exception as e:
            evaluation.status = EvaluationStatus.FAILED
            logger.error(f"Task evaluation failed: {e}")
    
    async def _calculate_auto_scores(
        self,
        order_id: str,
        result_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        自動評価スコアを計算
        
        評価基準:
        - quality: 結果の品質
        - completion: 要件の完了度
        - timeliness: 納期遵守
        - communication: コミュニケーション品質
        """
        order = await self._order_book.get_order(order_id)
        
        scores = {
            "quality": 5.0,
            "completion": 5.0,
            "timeliness": 5.0,
            "communication": 5.0
        }
        
        if not order:
            return scores
        
        # 1. 完了度スコア
        requirements = order.requirements
        deliverables = result_data.get("deliverables", [])
        
        if requirements and deliverables:
            req_count = len(requirements.get("items", []))
            del_count = len([d for d in deliverables if d.get("completed")])
            if req_count > 0:
                scores["completion"] = min(10, (del_count / req_count) * 10)
        
        # 2. 納期スコア
        deadline = order.deadline
        completed_at = result_data.get("completed_at")
        if deadline and completed_at:
            # 納期遵守の計算
            scores["timeliness"] = 10.0  # TODO: 実際の納期データに基づく計算
        
        # 3. 品質スコア（結果データの品質指標）
        quality_indicators = result_data.get("quality_indicators", {})
        if quality_indicators:
            scores["quality"] = quality_indicators.get("auto_score", 5.0)
        
        return scores
    
    async def _update_provider_reputation(self, evaluation: TaskEvaluation):
        """プロバイダーの評判スコアを更新"""
        try:
            await self._reputation_engine.update_reputation(
                agent_id=evaluation.provider_id,
                order_id=evaluation.order_id,
                quality_score=evaluation.overall_score,
                feedback=evaluation.feedback
            )
        except Exception as e:
            logger.error(f"Reputation update failed: {e}")
    
    async def _apply_incentive_or_penalty(self, evaluation: TaskEvaluation):
        """
        評価スコアに基づいてインセンティブまたはペナルティを適用
        """
        score = evaluation.overall_score
        threshold = self._config.quality_threshold
        
        if score >= threshold + 2:
            # 高品質: ボーナス
            logger.info(f"High quality bonus for {evaluation.provider_id}: {score}")
            # TODO: トークンボーナス付与
            
        elif score < threshold - 2:
            # 低品質: ペナルティ
            logger.warning(f"Low quality penalty for {evaluation.provider_id}: {score}")
            # TODO: ペナルティ適用（評価スコア減少など）
    
    async def _process_pending_evaluations(self):
        """評価待ちのタスクを処理"""
        # タイムアウトチェック
        now = datetime.utcnow()
        timeout = self._config.evaluation_timeout_hours
        
        expired = []
        for order_id, evaluation in self._pending_evaluations.items():
            if evaluation.status == EvaluationStatus.PENDING:
                # タイムアウト処理
                if evaluation.evaluated_at:
                    hours_elapsed = (now - evaluation.evaluated_at).total_seconds() / 3600
                    if hours_elapsed > timeout:
                        expired.append(order_id)
        
        # 期限切れを削除
        for order_id in expired:
            del self._pending_evaluations[order_id]
            logger.warning(f"Evaluation timeout for order: {order_id}")
    
    async def _update_reputation_scores(self):
        """定期的な評価スコア更新"""
        # 毎回ではなく、一定間隔で実行
        pass
    
    def on_match(self, callback: Callable):
        """マッチング時コールバックを登録"""
        self._on_match_callbacks.append(callback)
    
    def on_evaluate(self, callback: Callable):
        """評価完了時コールバックを登録"""
        self._on_evaluate_callbacks.append(callback)
    
    def get_evaluation(self, order_id: str) -> Optional[TaskEvaluation]:
        """評価結果を取得"""
        return self._pending_evaluations.get(order_id)
    
    def get_config(self) -> AutoMatchConfig:
        """設定を取得"""
        return self._config
    
    def update_config(self, config: AutoMatchConfig):
        """設定を更新"""
        self._config = config
        logger.info("AutoMatchingEvaluator config updated")
