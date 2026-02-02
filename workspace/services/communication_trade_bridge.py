"""
Communication-Trade Bridge
コミュニケーションと取引の統合ブリッジ

このモジュールは「情報交換 → 役割分担 → 取引」の流れを実現する。

Flow:
1. Intent Broadcast（意図共有）
2. Capability Discovery（能力発見）
3. Role Negotiation（役割交渉）
4. Plan Approval（計画承認）
5. Trade Execution（取引実行）← ブリッジ
6. Payment Settlement（決済）

コミュニケーションの質と履歴を評価に組み込む。
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from services.coordination_protocol import (
    CoordinationManager, CoordinationSession, CoordinationPhase,
    CoordinationMessage, CoordinationMessageType, Intent, Capability, Role
)
from services.marketplace import (
    Marketplace, ServiceListing, Order, OrderStatus
)
from services.escrow_manager import EscrowManager
from services.reputation_manager import ReputationManager
from services.l1_protocol import L1TaskDelegation, L1PaymentStatus

logger = logging.getLogger(__name__)


class TradePhase(Enum):
    """取引フェーズ"""
    COMMUNICATION = "communication"    # コミュニケーション中
    NEGOTIATION = "negotiation"        # 交渉中
    AGREEMENT = "agreement"            # 合意
    ESCROW = "escrow"                  # エスクロー
    EXECUTION = "execution"            # 実行
    SETTLEMENT = "settlement"          # 決済
    COMPLETE = "complete"              # 完了


@dataclass
class CommunicationTradeContext:
    """コミュニケーション・取引統合コンテキスト
    
    1つの協調から取引までの全コンテキストを保持。
    """
    context_id: str
    coordination_id: str
    trade_phase: TradePhase = TradePhase.COMMUNICATION
    
    # コミュニケーション関連
    intent: Optional[Intent] = None
    participants: Dict[str, Capability] = field(default_factory=dict)
    communication_history: List[Dict[str, Any]] = field(default_factory=list)
    
    # 取引関連
    order: Optional[Any] = None
    escrow_id: Optional[str] = None
    
    # 評価関連
    communication_score: float = 0.0
    trust_score: float = 0.0
    
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_id": self.context_id,
            "coordination_id": self.coordination_id,
            "trade_phase": self.trade_phase.value,
            "communication_history_count": len(self.communication_history),
            "communication_score": self.communication_score,
            "trust_score": self.trust_score,
            "has_order": self.order is not None,
            "has_escrow": self.escrow_id is not None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class CommunicationTradeBridge:
    """コミュニケーション・取引ブリッジ
    
    協調プロトコルからマーケットプレイス取引への橋渡し。
    コミュニケーションの質を評価に反映。
    """
    
    def __init__(
        self,
        entity_id: str,
        coordination_manager: CoordinationManager,
        marketplace: Optional[Marketplace] = None,
        escrow_manager: Optional[EscrowManager] = None,
        reputation_manager: Optional[ReputationManager] = None
    ):
        self.entity_id = entity_id
        self.coordination = coordination_manager
        self.marketplace = marketplace
        self.escrow = escrow_manager
        self.reputation = reputation_manager
        
        # コンテキスト管理
        self.contexts: Dict[str, CommunicationTradeContext] = {}
        
        # フェーズ遷移ハンドラー
        self.phase_handlers: Dict[CoordinationPhase, Callable] = {
            CoordinationPhase.INTENT_SHARING: self._on_intent_sharing,
            CoordinationPhase.CAPABILITY_DISCOVERY: self._on_capability_discovery,
            CoordinationPhase.ROLE_NEGOTIATION: self._on_role_negotiation,
            CoordinationPhase.PLANNING: self._on_planning,
            CoordinationPhase.EXECUTION: self._on_execution,
            CoordinationPhase.COMPLETION: self._on_completion
        }
        
        # コミュニケーションメトリクス設定
        self.metrics_config = {
            "response_time_threshold": 300,  # 5分以内の応答が望ましい
            "message_clarity_weight": 0.3,
            "response_timeliness_weight": 0.3,
            "collaboration_attitude_weight": 0.4
        }
    
    async def create_trade_from_coordination(
        self,
        coordination_id: str,
        auto_create_order: bool = True
    ) -> Optional[CommunicationTradeContext]:
        """協調セッションから取引コンテキストを作成"""
        session = self.coordination.get_session(coordination_id)
        if not session:
            logger.error(f"Coordination session {coordination_id} not found")
            return None
        
        # コンテキスト作成
        context = CommunicationTradeContext(
            context_id=str(uuid.uuid4()),
            coordination_id=coordination_id,
            intent=session.intent,
            participants=session.participants.copy()
        )
        
        # コミュニケーション履歴をコピー
        context.communication_history = session.get_communication_history()
        
        # コミュニケーションスコアを計算
        context.communication_score = self._calculate_communication_score(
            context.communication_history
        )
        
        # 信頼スコアを計算（評価システム連携）
        if self.reputation:
            trust_scores = []
            for participant_id in context.participants.keys():
                score = await self.reputation.get_reputation(participant_id)
                trust_scores.append(score)
            if trust_scores:
                context.trust_score = sum(trust_scores) / len(trust_scores)
        
        self.contexts[context.context_id] = context
        
        logger.info(
            f"Created trade context {context.context_id} from coordination {coordination_id}. "
            f"Comm score: {context.communication_score:.2f}, Trust: {context.trust_score:.2f}"
        )
        
        # 自動的に注文を作成
        if auto_create_order and session.plan:
            await self._create_order_from_plan(context, session)
        
        return context
    
    async def _create_order_from_plan(
        self,
        context: CommunicationTradeContext,
        session: CoordinationSession
    ) -> Optional[Any]:
        """計画から注文を作成"""
        if not self.marketplace or not session.plan:
            return None
        
        # 自分に割り当てられた役割を特定
        my_roles = [
            role for role in session.roles
            if role.assigned_to == self.entity_id
        ]
        
        if not my_roles:
            return None
        
        role = my_roles[0]
        
        # サービスリストを作成（もし存在しなければ）
        service_data = {
            "service_id": str(uuid.uuid4()),
            "provider_id": self.entity_id,
            "name": role.name,
            "description": role.description,
            "price": role.compensation.get("amount", 0) if role.compensation else 0,
            "currency": role.compensation.get("currency", "TOKEN") if role.compensation else "TOKEN",
            "tags": role.required_capabilities
        }
        
        # 注文を作成
        if context.participants:
            buyer_id = list(context.participants.keys())[0]
            
            try:
                order = await self.marketplace.create_order(
                    buyer_id=buyer_id,
                    provider_id=self.entity_id,
                    service_id=service_data["service_id"],
                    price=service_data["price"],
                    requirements={
                        "coordination_id": context.coordination_id,
                        "role_id": role.role_id,
                        "deliverables": role.responsibilities
                    }
                )
                
                context.order = order
                context.trade_phase = TradePhase.NEGOTIATION
                
                logger.info(f"Created order from coordination plan: {order.order_id}")
                return order
                
            except Exception as e:
                logger.error(f"Failed to create order: {e}")
                return None
        
        return None
    
    async def setup_escrow_with_communication_score(
        self,
        context_id: str,
        deposit_amount: float
    ) -> Optional[str]:
        """コミュニケーションスコアを考慮したエスクロー設定"""
        context = self.contexts.get(context_id)
        if not context or not context.order:
            return None
        
        if not self.escrow:
            logger.warning("Escrow manager not available")
            return None
        
        # コミュニケーションスコアに基づいてデポジット調整
        adjusted_deposit = self._adjust_deposit_by_communication_score(
            deposit_amount,
            context.communication_score
        )
        
        try:
            escrow_id = await self.escrow.create_escrow(
                order_id=context.order.order_id,
                buyer_id=context.order.buyer_id,
                seller_id=context.order.provider_id,
                amount=adjusted_deposit,
                conditions={
                    "communication_score_threshold": 0.6,
                    "trust_score_minimum": 0.5
                }
            )
            
            context.escrow_id = escrow_id
            context.trade_phase = TradePhase.ESCROW
            
            logger.info(
                f"Created escrow {escrow_id} with adjusted deposit: {adjusted_deposit} "
                f"(original: {deposit_amount}, comm score: {context.communication_score:.2f})"
            )
            
            return escrow_id
            
        except Exception as e:
            logger.error(f"Failed to create escrow: {e}")
            return None
    
    async def handle_coordination_phase_change(
        self,
        coordination_id: str,
        new_phase: CoordinationPhase
    ):
        """協調フェーズ変更を処理"""
        # 該当するコンテキストを探す
        context = None
        for ctx in self.contexts.values():
            if ctx.coordination_id == coordination_id:
                context = ctx
                break
        
        if not context:
            return
        
        # フェーズハンドラー実行
        handler = self.phase_handlers.get(new_phase)
        if handler:
            await handler(context)
    
    async def _on_intent_sharing(self, context: CommunicationTradeContext):
        """Intent sharing phase handler"""
        context.trade_phase = TradePhase.COMMUNICATION
        logger.info(f"Context {context.context_id}: Entered communication phase")
    
    async def _on_capability_discovery(self, context: CommunicationTradeContext):
        """Capability discovery phase handler"""
        # 能力発見時の評価
        logger.info(f"Context {context.context_id}: Capability discovery completed")
    
    async def _on_role_negotiation(self, context: CommunicationTradeContext):
        """Role negotiation phase handler"""
        context.trade_phase = TradePhase.NEGOTIATION
        logger.info(f"Context {context.context_id}: Entered negotiation phase")
    
    async def _on_planning(self, context: CommunicationTradeContext):
        """Planning phase handler"""
        context.trade_phase = TradePhase.AGREEMENT
        logger.info(f"Context {context.context_id}: Agreement reached")
    
    async def _on_execution(self, context: CommunicationTradeContext):
        """Execution phase handler"""
        context.trade_phase = TradePhase.EXECUTION
        
        # エスクローを解放条件付きで進行
        if context.escrow_id:
            await self._escrow_milestone(context, "execution_started")
    
    async def _on_completion(self, context: CommunicationTradeContext):
        """Completion phase handler"""
        context.trade_phase = TradePhase.SETTLEMENT
        
        # 最終評価
        final_score = self._calculate_final_score(context)
        
        # エスクロー決済
        if context.escrow_id:
            await self._settle_escrow(context, final_score)
        
        # 評価システムに記録
        if self.reputation and context.participants:
            for participant_id in context.participants.keys():
                await self.reputation.record_interaction(
                    entity_id=participant_id,
                    interaction_type="coordination_trade",
                    score=final_score,
                    context={
                        "coordination_id": context.coordination_id,
                        "communication_score": context.communication_score
                    }
                )
        
        context.trade_phase = TradePhase.COMPLETE
        logger.info(
            f"Context {context.context_id}: Trade completed with final score {final_score:.2f}"
        )
    
    def _calculate_communication_score(
        self,
        communication_history: List[Dict[str, Any]]
    ) -> float:
        """コミュニケーション履歴からスコアを計算"""
        if not communication_history:
            return 0.5  # デフォルト
        
        scores = []
        
        for i, msg in enumerate(communication_history):
            msg_score = 0.0
            
            # 1. 応答時間スコア
            if i > 0:
                prev_time = datetime.fromisoformat(communication_history[i-1]["timestamp"])
                curr_time = datetime.fromisoformat(msg["timestamp"])
                response_time = (curr_time - prev_time).total_seconds()
                
                if response_time < self.metrics_config["response_time_threshold"]:
                    msg_score += self.metrics_config["response_timeliness_weight"]
            
            # 2. メッセージ明確性（ペイロードの充実度）
            payload = msg.get("payload", {})
            if len(str(payload)) > 100:  # 十分な詳細
                msg_score += self.metrics_config["message_clarity_weight"]
            
            # 3. 協調姿勢（メッセージタイプによる）
            msg_type = msg.get("message_type", "")
            positive_types = ["ROLE_ACCEPTANCE", "PLAN_APPROVAL", "EXECUTION_READY"]
            if any(pt in msg_type for pt in positive_types):
                msg_score += self.metrics_config["collaboration_attitude_weight"]
            
            scores.append(msg_score)
        
        return sum(scores) / len(scores) if scores else 0.5
    
    def _adjust_deposit_by_communication_score(
        self,
        base_amount: float,
        communication_score: float
    ) -> float:
        """コミュニケーションスコアに基づいてデポジットを調整"""
        # スコアが高いほどデポジットを減らす（信頼の証）
        if communication_score >= 0.9:
            multiplier = 0.8  # 20%減
        elif communication_score >= 0.7:
            multiplier = 0.9  # 10%減
        elif communication_score >= 0.5:
            multiplier = 1.0  # 変更不要
        else:
            multiplier = 1.2  # 20%増（リスクヘッジ）
        
        return base_amount * multiplier
    
    def _calculate_final_score(self, context: CommunicationTradeContext) -> float:
        """最終スコアを計算"""
        weights = {
            "communication": 0.4,
            "trust": 0.3,
            "execution": 0.3
        }
        
        return (
            weights["communication"] * context.communication_score +
            weights["trust"] * context.trust_score +
            weights["execution"] * 0.8  # 実行スコア（デフォルト）
        )
    
    async def _escrow_milestone(self, context: CommunicationTradeContext, milestone: str):
        """エスクローマイルストーンを記録"""
        if self.escrow and context.escrow_id:
            try:
                await self.escrow.record_milestone(
                    escrow_id=context.escrow_id,
                    milestone=milestone,
                    data={"timestamp": datetime.now(timezone.utc).isoformat()}
                )
            except Exception as e:
                logger.error(f"Failed to record escrow milestone: {e}")
    
    async def _settle_escrow(self, context: CommunicationTradeContext, final_score: float):
        """エスクローを決済"""
        if not self.escrow or not context.escrow_id:
            return
        
        try:
            # スコアに基づいて支払い額を調整
            if final_score >= 0.8:
                release_amount = 1.0  # 100%
            elif final_score >= 0.6:
                release_amount = 0.8  # 80%
            elif final_score >= 0.4:
                release_amount = 0.5  # 50%
            else:
                release_amount = 0.0  # 0%
            
            await self.escrow.release_funds(
                escrow_id=context.escrow_id,
                release_percentage=release_amount,
                reason=f"Coordination completed with score {final_score:.2f}"
            )
            
            logger.info(
                f"Escrow {context.escrow_id} settled with {release_amount*100:.0f}% release"
            )
            
        except Exception as e:
            logger.error(f"Failed to settle escrow: {e}")
    
    def get_trade_context(self, context_id: str) -> Optional[CommunicationTradeContext]:
        """取引コンテキストを取得"""
        return self.contexts.get(context_id)
    
    def list_active_trades(self) -> List[CommunicationTradeContext]:
        """アクティブな取引を一覧"""
        return [
            ctx for ctx in self.contexts.values()
            if ctx.trade_phase != TradePhase.COMPLETE
        ]
    
    def get_communication_insights(self) -> Dict[str, Any]:
        """コミュニケーション分析インサイト"""
        if not self.contexts:
            return {"message": "No trade data available"}
        
        completed = [c for c in self.contexts.values() if c.trade_phase == TradePhase.COMPLETE]
        
        return {
            "total_contexts": len(self.contexts),
            "completed_trades": len(completed),
            "average_communication_score": sum(c.communication_score for c in self.contexts.values()) / len(self.contexts),
            "average_trust_score": sum(c.trust_score for c in self.contexts.values()) / len(self.contexts),
            "success_rate": len(completed) / len(self.contexts) if self.contexts else 0,
            "insights": [
                "Higher communication scores correlate with successful trades",
                "Trust scores improve with repeated collaborations",
                "Clear intent sharing reduces negotiation time"
            ]
        }


# グローバルインスタンス
_bridge_instance: Optional[CommunicationTradeBridge] = None


def get_communication_trade_bridge(
    entity_id: Optional[str] = None,
    coordination_manager: Optional[CoordinationManager] = None
) -> CommunicationTradeBridge:
    """グローバルブリッジインスタンスを取得"""
    global _bridge_instance
    if _bridge_instance is None:
        if entity_id is None or coordination_manager is None:
            raise ValueError("entity_id and coordination_manager required for initialization")
        _bridge_instance = CommunicationTradeBridge(
            entity_id=entity_id,
            coordination_manager=coordination_manager
        )
    return _bridge_instance
