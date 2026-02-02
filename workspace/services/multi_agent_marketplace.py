"""
v1.3 Multi-Agent Marketplace
分散型AIエージェント間サービス取引プラットフォーム

Features:
- Multi-agent service discovery
- Direct P2P transactions with escrow
- Dynamic pricing engine
- Reputation tracking
- Dispute resolution
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
import uuid

from services.marketplace.service_registry import (
    ServiceRegistry, ServiceListing, ServiceType, PricingModel
)
from services.token_system import TokenWallet, Transaction
from services.marketplace.escrow import EscrowManager, EscrowStatus

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class DisputeStatus(Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class ServiceQuote:
    """サービス見積もり"""
    quote_id: str
    service_id: str
    provider_id: str
    client_id: str
    base_price: Decimal
    estimated_time: int  # minutes
    validity_period: int = 3600  # seconds
    custom_terms: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(seconds=self.validity_period)
    
    def is_valid(self) -> bool:
        return datetime.now() < self.expires_at
    
    def to_dict(self) -> Dict:
        return {
            "quote_id": self.quote_id,
            "service_id": self.service_id,
            "provider_id": self.provider_id,
            "client_id": self.client_id,
            "base_price": str(self.base_price),
            "estimated_time": self.estimated_time,
            "validity_period": self.validity_period,
            "custom_terms": self.custom_terms,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_valid": self.is_valid()
        }


@dataclass
class MarketplaceOrder:
    """マーケットプレイス注文"""
    order_id: str
    quote_id: str
    service_id: str
    provider_id: str
    client_id: str
    agreed_price: Decimal
    status: OrderStatus
    escrow_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    deliverables: List[Dict] = field(default_factory=list)
    dispute_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "order_id": self.order_id,
            "quote_id": self.quote_id,
            "service_id": self.service_id,
            "provider_id": self.provider_id,
            "client_id": self.client_id,
            "agreed_price": str(self.agreed_price),
            "status": self.status.value,
            "escrow_id": self.escrow_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "deliverables": self.deliverables,
            "dispute_id": self.dispute_id,
            "metadata": self.metadata
        }


@dataclass
class Dispute:
    """紛争ケース"""
    dispute_id: str
    order_id: str
    initiator_id: str
    respondent_id: str
    reason: str
    status: DisputeStatus
    evidence: List[Dict] = field(default_factory=list)
    resolution: Optional[str] = None
    refund_amount: Optional[Decimal] = None
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        return {
            "dispute_id": self.dispute_id,
            "order_id": self.order_id,
            "initiator_id": self.initiator_id,
            "respondent_id": self.respondent_id,
            "reason": self.reason,
            "status": self.status.value,
            "evidence": self.evidence,
            "resolution": self.resolution,
            "refund_amount": str(self.refund_amount) if self.refund_amount else None,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }


class PricingEngine:
    """動的価格設定エンジン"""
    
    PLATFORM_FEE_STANDARD = Decimal("0.03")  # 3%
    PLATFORM_FEE_PREMIUM = Decimal("0.05")   # 5%
    
    def __init__(self):
        self.price_history: Dict[str, List[Decimal]] = {}
        self.demand_index: Dict[str, float] = {}
    
    def calculate_price(
        self,
        base_price: Decimal,
        service_type: ServiceType,
        provider_reputation: float,
        urgency: int = 1,  # 1-5
        demand_multiplier: float = 1.0
    ) -> Decimal:
        """動的価格を計算"""
        # 評価による信頼料金
        reputation_multiplier = Decimal("1.0") + (Decimal(str(provider_reputation)) * Decimal("0.1"))
        
        # 緊急度によるプレミアム
        urgency_multiplier = Decimal("1.0") + (Decimal(str(urgency - 1)) * Decimal("0.05"))
        
        # 需要による調整
        demand_dec = Decimal(str(demand_multiplier))
        
        final_price = base_price * reputation_multiplier * urgency_multiplier * demand_dec
        return final_price.quantize(Decimal("0.01"))
    
    def add_platform_fee(self, price: Decimal, is_premium: bool = False) -> Decimal:
        """プラットフォーム手数料を追加"""
        fee_rate = self.PLATFORM_FEE_PREMIUM if is_premium else self.PLATFORM_FEE_STANDARD
        total = price * (Decimal("1") + fee_rate)
        return total.quantize(Decimal("0.01"))
    
    def get_fee_breakdown(self, price: Decimal, is_premium: bool = False) -> Dict:
        """手数料内訳を取得"""
        fee_rate = self.PLATFORM_FEE_PREMIUM if is_premium else self.PLATFORM_FEE_STANDARD
        platform_fee = price * fee_rate
        provider_amount = price
        total = price + platform_fee
        
        return {
            "service_price": str(price),
            "platform_fee_rate": str(fee_rate),
            "platform_fee": str(platform_fee),
            "provider_amount": str(provider_amount),
            "total": str(total)
        }


class ReputationTracker:
    """評価追跡システム"""
    
    def __init__(self):
        self.reputation_scores: Dict[str, Dict] = {}
        self.transaction_history: Dict[str, List[Dict]] = {}
    
    def update_reputation(
        self,
        agent_id: str,
        rating: float,  # 1-5
        transaction_value: Decimal,
        is_completed: bool = True
    ):
        """評価を更新"""
        if agent_id not in self.reputation_scores:
            self.reputation_scores[agent_id] = {
                "total_score": 0.0,
                "transaction_count": 0,
                "total_volume": Decimal("0"),
                "completion_rate": 0.0
            }
        
        rep = self.reputation_scores[agent_id]
        
        # 加重平均で評価を計算
        total_weight = rep["transaction_count"] + 1
        rep["total_score"] = (
            (rep["total_score"] * rep["transaction_count"]) + rating
        ) / total_weight
        rep["transaction_count"] = total_weight
        rep["total_volume"] += transaction_value
        
        # 完了率を更新
        completed = rep["transaction_count"] * rep.get("completion_rate", 1.0)
        if is_completed:
            completed += 1
        rep["completion_rate"] = completed / total_weight
        
        logger.info(f"Updated reputation for {agent_id}: score={rep['total_score']:.2f}")
    
    def get_reputation(self, agent_id: str) -> Optional[Dict]:
        """評価情報を取得"""
        return self.reputation_scores.get(agent_id)
    
    def get_trust_score(self, agent_id: str) -> float:
        """信頼スコアを計算（0-1）"""
        rep = self.reputation_scores.get(agent_id)
        if not rep:
            return 0.5  # デフォルト: 中立的
        
        # 評価スコア（0-1）
        rating_score = rep["total_score"] / 5.0
        
        # 取引量による重み
        volume_weight = min(rep["transaction_count"] / 100, 1.0)
        
        # 完了率
        completion_rate = rep.get("completion_rate", 1.0)
        
        # 総合スコア
        trust_score = (rating_score * 0.4 + volume_weight * 0.3 + completion_rate * 0.3)
        return min(max(trust_score, 0.0), 1.0)


class MultiAgentMarketplace:
    """v1.3 マルチエージェントマーケットプレイス"""
    
    def __init__(
        self,
        service_registry: Optional[ServiceRegistry] = None,
        escrow_manager: Optional[EscrowManager] = None,
        token_wallet: Optional[TokenWallet] = None
    ):
        self.service_registry = service_registry or ServiceRegistry()
        self.escrow_manager = escrow_manager or EscrowManager()
        self.token_wallet = token_wallet
        
        self.pricing_engine = PricingEngine()
        self.reputation_tracker = ReputationTracker()
        
        self.quotes: Dict[str, ServiceQuote] = {}
        self.orders: Dict[str, MarketplaceOrder] = {}
        self.disputes: Dict[str, Dispute] = {}
        
        # イベントハンドラ
        self.event_handlers: Dict[str, List[Callable]] = {
            "quote_created": [],
            "order_created": [],
            "order_completed": [],
            "dispute_opened": [],
            "dispute_resolved": []
        }
        
        logger.info("MultiAgentMarketplace v1.3 initialized")
    
    # --- Service Discovery ---
    
    async def discover_services(
        self,
        service_type: Optional[ServiceType] = None,
        capabilities: Optional[List[str]] = None,
        max_price: Optional[Decimal] = None,
        min_reputation: float = 0.0
    ) -> List[Dict]:
        """サービスを発見"""
        services = await self.service_registry.search_services(
            service_type=service_type,
            capabilities=capabilities
        )
        
        results = []
        for service in services:
            # 評価フィルタ
            rep = self.reputation_tracker.get_reputation(service.provider_id)
            if rep and rep.get("total_score", 0) / 5 < min_reputation:
                continue
            
            # 価格フィルタ
            if max_price and service.price > max_price:
                continue
            
            service_dict = service.to_dict()
            service_dict["provider_reputation"] = rep
            service_dict["trust_score"] = self.reputation_tracker.get_trust_score(
                service.provider_id
            )
            results.append(service_dict)
        
        # 信頼スコアでソート
        results.sort(key=lambda x: x["trust_score"], reverse=True)
        return results
    
    # --- Quote & Negotiation ---
    
    async def request_quote(
        self,
        service_id: str,
        client_id: str,
        custom_requirements: Optional[Dict] = None,
        urgency: int = 1
    ) -> Optional[ServiceQuote]:
        """見積もりをリクエスト"""
        service = await self.service_registry.get_service(service_id)
        if not service:
            logger.warning(f"Service {service_id} not found")
            return None
        
        # 動的価格計算
        provider_rep = self.reputation_tracker.get_reputation(service.provider_id)
        reputation_score = provider_rep["total_score"] / 5 if provider_rep else 0.5
        
        final_price = self.pricing_engine.calculate_price(
            base_price=service.price,
            service_type=service.service_type,
            provider_reputation=reputation_score,
            urgency=urgency
        )
        
        # プラットフォーム手数料込み
        total_price = self.pricing_engine.add_platform_fee(final_price)
        
        quote = ServiceQuote(
            quote_id=str(uuid.uuid4()),
            service_id=service_id,
            provider_id=service.provider_id,
            client_id=client_id,
            base_price=total_price,
            estimated_time=custom_requirements.get("estimated_time", 60) if custom_requirements else 60,
            custom_terms=custom_requirements or {}
        )
        
        self.quotes[quote.quote_id] = quote
        
        # イベント発火
        await self._emit_event("quote_created", quote.to_dict())
        
        logger.info(f"Quote created: {quote.quote_id} for service {service_id}")
        return quote
    
    # --- Order Management ---
    
    async def place_order(
        self,
        quote_id: str,
        client_id: str,
        payment_method: str = "escrow"
    ) -> Optional[MarketplaceOrder]:
        """注文を確定"""
        quote = self.quotes.get(quote_id)
        if not quote or not quote.is_valid():
            logger.warning(f"Invalid or expired quote: {quote_id}")
            return None
        
        # 注文作成
        order = MarketplaceOrder(
            order_id=str(uuid.uuid4()),
            quote_id=quote_id,
            service_id=quote.service_id,
            provider_id=quote.provider_id,
            client_id=client_id,
            agreed_price=quote.base_price,
            status=OrderStatus.PENDING
        )
        
        # エスクロー作成
        if payment_method == "escrow":
            escrow = await self.escrow_manager.create_escrow(
                buyer_id=client_id,
                seller_id=quote.provider_id,
                amount=quote.base_price,
                service_description=f"Order {order.order_id}"
            )
            order.escrow_id = escrow.escrow_id
            order.status = OrderStatus.CONFIRMED
        
        self.orders[order.order_id] = order
        
        await self._emit_event("order_created", order.to_dict())
        
        logger.info(f"Order placed: {order.order_id}")
        return order
    
    async def start_work(self, order_id: str, provider_id: str) -> bool:
        """作業を開始"""
        order = self.orders.get(order_id)
        if not order or order.provider_id != provider_id:
            return False
        
        if order.status != OrderStatus.CONFIRMED:
            return False
        
        order.status = OrderStatus.IN_PROGRESS
        order.updated_at = datetime.now()
        
        logger.info(f"Work started: {order_id}")
        return True
    
    async def submit_deliverable(
        self,
        order_id: str,
        provider_id: str,
        deliverable: Dict
    ) -> bool:
        """成果物を提出"""
        order = self.orders.get(order_id)
        if not order or order.provider_id != provider_id:
            return False
        
        if order.status != OrderStatus.IN_PROGRESS:
            return False
        
        order.deliverables.append(deliverable)
        order.status = OrderStatus.DELIVERED
        order.updated_at = datetime.now()
        
        logger.info(f"Deliverable submitted: {order_id}")
        return True
    
    async def confirm_completion(
        self,
        order_id: str,
        client_id: str,
        rating: Optional[float] = None
    ) -> bool:
        """完了を確認し、支払いを解放"""
        order = self.orders.get(order_id)
        if not order or order.client_id != client_id:
            return False
        
        if order.status != OrderStatus.DELIVERED:
            return False
        
        # エスクロー解放
        if order.escrow_id:
            success = await self.escrow_manager.release_escrow(
                order.escrow_id,
                client_id
            )
            if not success:
                return False
        
        order.status = OrderStatus.COMPLETED
        order.completed_at = datetime.now()
        order.updated_at = datetime.now()
        
        # 評価を更新
        if rating:
            self.reputation_tracker.update_reputation(
                agent_id=order.provider_id,
                rating=rating,
                transaction_value=order.agreed_price,
                is_completed=True
            )
        
        await self._emit_event("order_completed", order.to_dict())
        
        logger.info(f"Order completed: {order_id}")
        return True
    
    # --- Dispute Resolution ---
    
    async def open_dispute(
        self,
        order_id: str,
        initiator_id: str,
        reason: str,
        evidence: Optional[List[Dict]] = None
    ) -> Optional[Dispute]:
        """紛争を提起"""
        order = self.orders.get(order_id)
        if not order:
            return None
        
        # 注文状態を更新
        order.status = OrderStatus.DISPUTED
        order.updated_at = datetime.now()
        
        # 紛争作成
        dispute = Dispute(
            dispute_id=str(uuid.uuid4()),
            order_id=order_id,
            initiator_id=initiator_id,
            respondent_id=order.provider_id if initiator_id == order.client_id else order.client_id,
            reason=reason,
            status=DisputeStatus.OPEN,
            evidence=evidence or []
        )
        
        self.disputes[dispute.dispute_id] = dispute
        order.dispute_id = dispute.dispute_id
        
        await self._emit_event("dispute_opened", dispute.to_dict())
        
        logger.warning(f"Dispute opened: {dispute.dispute_id} for order {order_id}")
        return dispute
    
    async def resolve_dispute(
        self,
        dispute_id: str,
        resolution: str,
        refund_amount: Optional[Decimal] = None
    ) -> bool:
        """紛争を解決"""
        dispute = self.disputes.get(dispute_id)
        if not dispute:
            return False
        
        dispute.resolution = resolution
        dispute.refund_amount = refund_amount
        dispute.status = DisputeStatus.RESOLVED
        dispute.resolved_at = datetime.now()
        
        # 注文状態を更新
        order = self.orders.get(dispute.order_id)
        if order:
            if refund_amount and refund_amount > 0:
                order.status = OrderStatus.REFUNDED
                # 部分返金処理
                if order.escrow_id:
                    await self.escrow_manager.refund_escrow(
                        order.escrow_id,
                        refund_amount
                    )
            else:
                order.status = OrderStatus.COMPLETED
            order.updated_at = datetime.now()
        
        await self._emit_event("dispute_resolved", dispute.to_dict())
        
        logger.info(f"Dispute resolved: {dispute_id}")
        return True
    
    # --- Event System ---
    
    def on(self, event: str, handler: Callable):
        """イベントハンドラを登録"""
        if event in self.event_handlers:
            self.event_handlers[event].append(handler)
    
    async def _emit_event(self, event: str, data: Dict):
        """イベントを発火"""
        handlers = self.event_handlers.get(event, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Event handler error: {e}")
    
    # --- Stats & Analytics ---
    
    def get_marketplace_stats(self) -> Dict:
        """マーケットプレイス統計"""
        total_orders = len(self.orders)
        completed_orders = sum(
            1 for o in self.orders.values()
            if o.status == OrderStatus.COMPLETED
        )
        disputed_orders = sum(
            1 for o in self.orders.values()
            if o.status == OrderStatus.DISPUTED
        )
        
        total_volume = sum(
            o.agreed_price for o in self.orders.values()
            if o.status == OrderStatus.COMPLETED
        )
        
        return {
            "total_orders": total_orders,
            "completed_orders": completed_orders,
            "disputed_orders": disputed_orders,
            "completion_rate": completed_orders / total_orders if total_orders > 0 else 0,
            "total_volume": str(total_volume),
            "active_quotes": len(self.quotes),
            "open_disputes": sum(
                1 for d in self.disputes.values()
                if d.status in (DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW)
            )
        }
    
    def get_agent_stats(self, agent_id: str) -> Dict:
        """エージェント統計"""
        rep = self.reputation_tracker.get_reputation(agent_id)
        
        # 注文統計
        orders_as_provider = [
            o for o in self.orders.values()
            if o.provider_id == agent_id
        ]
        orders_as_client = [
            o for o in self.orders.values()
            if o.client_id == agent_id
        ]
        
        return {
            "reputation": rep,
            "trust_score": self.reputation_tracker.get_trust_score(agent_id),
            "orders_as_provider": len(orders_as_provider),
            "orders_as_client": len(orders_as_client),
            "completed_orders": sum(
                1 for o in orders_as_provider
                if o.status == OrderStatus.COMPLETED
            ),
            "total_earnings": str(sum(
                o.agreed_price for o in orders_as_provider
                if o.status == OrderStatus.COMPLETED
            ))
        }


# グローバルインスタンス
_marketplace: Optional[MultiAgentMarketplace] = None


def get_marketplace() -> MultiAgentMarketplace:
    """グローバルマーケットプレイスインスタンスを取得"""
    global _marketplace
    if _marketplace is None:
        _marketplace = MultiAgentMarketplace()
    return _marketplace
