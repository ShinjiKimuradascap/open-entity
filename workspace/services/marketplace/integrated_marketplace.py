#!/usr/bin/env python3
"""
統合マーケットプレイス (L2 Phase 2 Implementation)

TaskMarketplace + MatchingEngine + ReputationEngine + AutoMatchingEvaluator
を統合した完全自動化マーケットプレイス
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal

from .service_registry import ServiceRegistry
from .order_book import OrderBook, ServiceOrder, OrderStatus
from .matching_engine import ServiceMatchingEngine, MatchCriteria
from .reputation_engine import ReputationEngine
from .auto_matching_evaluator import AutoMatchingEvaluator, AutoMatchConfig
from .escrow import EscrowManager

logger = logging.getLogger(__name__)


@dataclass
class MarketplaceStats:
    """マーケットプレイス統計"""
    total_orders: int
    completed_orders: int
    active_orders: int
    total_volume: Decimal
    average_rating: float
    top_providers: List[Dict[str, Any]]


class IntegratedMarketplace:
    """
    統合マーケットプレイス
    
    機能:
    - サービス登録・検索
    - 自動オーダーマッチング
    - エスクロー管理
    - 自動評価・評判管理
    - 統計・レポート
    """
    
    def __init__(self, data_dir: str = "./data/marketplace"):
        self._data_dir = data_dir
        
        # コンポーネント初期化
        self._registry = ServiceRegistry()
        self._order_book = OrderBook()
        self._matching_engine = ServiceMatchingEngine(
            registry=self._registry,
            order_book=self._order_book
        )
        self._reputation_engine = ReputationEngine()
        self._escrow = EscrowManager()
        
        # 自動マッチング・評価システム
        self._auto_matcher = AutoMatchingEvaluator(
            matching_engine=self._matching_engine,
            order_book=self._order_book,
            reputation_engine=self._reputation_engine,
            config=AutoMatchConfig(
                enabled=True,
                auto_match_threshold=0.75,
                quality_threshold=7.0
            )
        )
        
        self._initialized = False
        logger.info("IntegratedMarketplace initialized")
    
    async def initialize(self):
        """マーケットプレイスを初期化"""
        if self._initialized:
            return
        
        # 自動マッチング・評価システムを開始
        await self._auto_matcher.start()
        
        # コールバック登録
        self._auto_matcher.on_match(self._on_auto_match)
        self._auto_matcher.on_evaluate(self._on_evaluation_complete)
        
        self._initialized = True
        logger.info("IntegratedMarketplace started")
    
    async def shutdown(self):
        """マーケットプレイスをシャットダウン"""
        await self._auto_matcher.stop()
        self._initialized = False
        logger.info("IntegratedMarketplace shutdown")
    
    # ===== サービス登録・検索 =====
    
    async def register_service(
        self,
        provider_id: str,
        name: str,
        service_type: str,
        capabilities: List[str],
        pricing: Dict[str, Any],
        description: str = ""
    ) -> str:
        """
        サービスを登録
        
        Returns:
            service_id: 登録されたサービスID
        """
        from .service_registry import ServiceListing, ServiceType, PricingModel
        from decimal import Decimal
        import hashlib
        
        # サービスID生成
        service_id = hashlib.sha256(
            f"{provider_id}:{name}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        
        # ServiceListing作成
        listing = ServiceListing(
            service_id=service_id,
            provider_id=provider_id,
            name=name,
            service_type=ServiceType(service_type),
            description=description,
            pricing_model=PricingModel.FIXED,
            price=Decimal(str(pricing.get("base_price", "0"))),
            capabilities=capabilities,
            endpoint=pricing.get("endpoint", ""),
            terms_hash=hashlib.sha256(description.encode()).hexdigest()[:16]
        )
        
        # 登録
        await self._registry.register_service(listing)
        
        logger.info(f"Service registered: {service_id} by {provider_id}")
        return service_id
    
    async def search_services(
        self,
        capabilities: List[str],
        max_price: Optional[Decimal] = None,
        min_reputation: float = 0.0,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        サービスを検索
        
        Args:
            capabilities: 必要な機能リスト
            max_price: 最大価格
            min_reputation: 最低評価スコア
            limit: 返却件数
            
        Returns:
            マッチングされたサービスリスト
        """
        criteria = MatchCriteria(
            required_capabilities=capabilities,
            max_price=max_price,
            min_reputation=min_reputation
        )
        
        result = await self._matching_engine.find_matches(criteria, limit=limit)
        
        services = []
        for match in result.matches:
            service = await self._registry.get_service(match.service_id)
            if service:
                services.append({
                    "service_id": match.service_id,
                    "provider_id": match.provider_id,
                    "match_score": match.score,
                    "price": match.estimated_cost,
                    "reputation": match.reputation_score,
                    **service
                })
        
        return services
    
    # ===== オーダー管理 =====
    
    async def create_order(
        self,
        buyer_id: str,
        service_id: str,
        quantity: int,
        max_price: Decimal,
        requirements: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        新規オーダーを作成
        
        Args:
            buyer_id: 購入者ID
            service_id: サービスID
            quantity: 数量
            max_price: 最大価格
            requirements: 要件（オプション）
            
        Returns:
            order_id: 作成されたオーダーID
        """
        order = await self._order_book.create_order(
            buyer_id=buyer_id,
            service_id=service_id,
            quantity=quantity,
            max_price=max_price,
            requirements=requirements
        )
        order_id = order.order_id if order else None
        
        logger.info(f"Order created: {order_id} by {buyer_id}")
        
        # 自動マッチングが有効な場合、即座にマッチングを試行
        if order_id and self._auto_matcher._config.enabled:
            asyncio.create_task(self._try_auto_match(order_id))
        
        return order_id
    
    async def _try_auto_match(self, order_id: str):
        """オーダーの自動マッチングを試行"""
        try:
            order = await self._order_book.get_order(order_id)
            if not order or order.status != OrderStatus.PENDING:
                return
            
            criteria = MatchCriteria(
                required_capabilities=order.requirements.get("capabilities", []),
                max_price=order.total_amount,
                min_reputation=self._auto_matcher._config.require_reputation_min
            )
            
            result = await self._matching_engine.find_matches(criteria, limit=3)
            
            if result.success and result.top_match:
                top = result.top_match
                
                # 自動マッチングスコア閾値をチェック
                if top.score >= self._auto_matcher._config.auto_match_threshold:
                    await self.accept_match(order_id, top.provider_id)
                    
        except Exception as e:
            logger.error(f"Auto-match error for {order_id}: {e}")
    
    async def accept_match(self, order_id: str, provider_id: str) -> bool:
        """
        マッチングを承認
        
        Args:
            order_id: オーダーID
            provider_id: プロバイダーID
            
        Returns:
            success: 承認成功したか
        """
        try:
            # エスクロー作成
            order = await self._order_book.get_order(order_id)
            if not order:
                return False
            
            escrow_id = await self._escrow.create_escrow(
                order_id=order_id,
                buyer_id=order.buyer_id,
                provider_id=provider_id,
                amount=order.total_amount
            )
            
            # オーダー状態更新（マッチング）
            match_result = await self._order_book.match_order(order_id, provider_id, escrow_id)
            if not match_result.success:
                return False
            
            logger.info(f"Match accepted: {order_id} -> {provider_id}, escrow: {escrow_id}")
            return True
            
        except Exception as e:
            logger.error(f"Accept match failed: {e}")
            return False
    
    async def submit_work(self, order_id: str, provider_id: str, work_result: Dict[str, Any]) -> bool:
        """
        作業結果を提出
        
        Args:
            order_id: オーダーID
            provider_id: プロバイダーID
            work_result: 作業結果データ
            
        Returns:
            success: 提出成功したか
        """
        try:
            order = await self._order_book.get_order(order_id)
            if not order or order.provider_id != provider_id:
                return False
            
            # 作業結果を保存
            await self._order_book.submit_work(order_id, work_result)
            await self._order_book.update_status(order_id, OrderStatus.COMPLETED)
            
            # 自動評価を開始
            await self._auto_matcher.submit_task_result(
                order_id=order_id,
                result_data=work_result,
                provider_id=provider_id
            )
            
            logger.info(f"Work submitted: {order_id} by {provider_id}")
            return True
            
        except Exception as e:
            logger.error(f"Submit work failed: {e}")
            return False
    
    async def approve_work(self, order_id: str, buyer_id: str, rating: int) -> bool:
        """
        作業を承認して支払いを実行
        
        Args:
            order_id: オーダーID
            buyer_id: 購入者ID
            rating: 評価（1-5）
            
        Returns:
            success: 承認成功したか
        """
        try:
            order = await self._order_book.get_order(order_id)
            if not order or order.buyer_id != buyer_id:
                return False
            
            # エスクロー解放
            await self._escrow.release_escrow(order_id)
            
            # オーダー状態更新
            await self._order_book.update_status(order_id, OrderStatus.APPROVED)
            
            # 評価を記録
            await self._reputation_engine.record_rating(
                agent_id=order.provider_id,
                order_id=order_id,
                rating=rating
            )
            
            logger.info(f"Work approved: {order_id} by {buyer_id}, rating: {rating}")
            return True
            
        except Exception as e:
            logger.error(f"Approve work failed: {e}")
            return False
    
    # ===== 統計・レポート =====
    
    async def get_stats(self) -> MarketplaceStats:
        """マーケットプレイス統計を取得"""
        orders = await self._order_book.get_pending_orders()
        
        total = len(orders)
        completed = len([o for o in orders if o.status == OrderStatus.APPROVED])
        active = len([o for o in orders if o.status in [OrderStatus.PENDING, OrderStatus.ACCEPTED]])
        volume = sum(o.max_price for o in orders if o.status == OrderStatus.APPROVED)
        
        # トッププロバイダー
        top_providers = await self._reputation_engine.get_top_providers(limit=5)
        
        # 平均評価
        ratings = await self._reputation_engine.get_all_ratings()
        avg_rating = sum(r["rating"] for r in ratings) / len(ratings) if ratings else 0.0
        
        return MarketplaceStats(
            total_orders=total,
            completed_orders=completed,
            active_orders=active,
            total_volume=volume,
            average_rating=avg_rating,
            top_providers=top_providers
        )
    
    # ===== コールバックハンドラ =====
    
    async def _on_auto_match(self, order: ServiceOrder, match: Any):
        """自動マッチング時コールバック"""
        logger.info(f"Auto-match callback: {order.id} matched with {match.provider_id}")
        # 通知送信等の追加処理
    
    async def _on_evaluation_complete(self, evaluation: Any):
        """評価完了時コールバック"""
        logger.info(f"Evaluation complete: {evaluation.order_id} - Score: {evaluation.overall_score}")
        
        # 高品質の場合、ボーナス支払い
        if evaluation.overall_score >= 9.0:
            logger.info(f"High quality bonus eligible: {evaluation.provider_id}")
            # TODO: ボーナス支払い処理
