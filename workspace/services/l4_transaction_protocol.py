#!/usr/bin/env python3
"""
L4 Auto Transaction Protocol
AI間自動取引プロトコル
"""

import json
import uuid
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import heapq

from services.l4_contract_templates import (
    generate_service_contract,
    generate_escrow_contract,
    ServiceContract,
    EscrowContract,
    validate_contract,
    CONTRACT_TEMPLATES
)
from services.marketplace_models import AgentProfile, TaskRequest, Bid


class TransactionStatus(Enum):
    """取引ステータス"""
    PROPOSED = "proposed"
    MATCHING = "matching"
    NEGOTIATING = "negotiating"
    CONTRACT_CREATED = "contract_created"
    ESCROW_FUNDED = "escrow_funded"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SETTLED = "settled"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


class ProposalStatus(Enum):
    """提案ステータス"""
    OPEN = "open"
    MATCHED = "matched"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class Proposal:
    """買い手からのサービス提案"""
    proposal_id: str
    buyer_id: str
    requirements: str
    service_type: str
    max_budget: float
    priority: int = 3
    deadline_hours: int = 24
    quality_min: float = 0.7
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    status: str = "open"
    matched_seller: Optional[str] = None
    final_price: float = 0.0
    
    def __post_init__(self):
        if not self.proposal_id:
            self.proposal_id = f"prop_{uuid.uuid4().hex[:16]}"
        if not self.expires_at:
            self.expires_at = self.created_at + (self.deadline_hours * 3600)
    
    def is_expired(self) -> bool:
        """期限切れかチェック"""
        return time.time() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "buyer_id": self.buyer_id,
            "requirements": self.requirements,
            "service_type": self.service_type,
            "max_budget": self.max_budget,
            "priority": self.priority,
            "deadline_hours": self.deadline_hours,
            "quality_min": self.quality_min,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "matched_seller": self.matched_seller,
            "final_price": self.final_price
        }


@dataclass
class SellerOffer:
    """売り手からのオファー"""
    offer_id: str
    seller_id: str
    proposal_id: str
    price: float
    delivery_hours: int
    quality_score: float
    reputation_score: float
    capabilities: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if not self.offer_id:
            self.offer_id = f"off_{uuid.uuid4().hex[:16]}"


@dataclass
class Transaction:
    """取引レコード"""
    transaction_id: str
    proposal_id: str
    contract_id: Optional[str] = None
    escrow_id: Optional[str] = None
    buyer_id: str = ""
    seller_id: str = ""
    amount: float = 0.0
    status: str = "proposed"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    
    def __post_init__(self):
        if not self.transaction_id:
            self.transaction_id = f"tx_{uuid.uuid4().hex[:16]}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "proposal_id": self.proposal_id,
            "contract_id": self.contract_id,
            "escrow_id": self.escrow_id,
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "amount": self.amount,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at
        }


class PricingEngine:
    """
    動的価格計算エンジン
    
    需給バランスに基づく動的価格調整:
    - 需要高・供給低 → 価格上昇
    - 需要低・供給高 → 価格下落
    - リアルタイム市場データ反映
    """
    
    def __init__(self):
        # 市場データ
        self.market_data: Dict[str, Dict[str, Any]] = {}
        # サービス別統計
        self.service_stats: Dict[str, Dict[str, Any]] = {}
        # 価格履歴
        self.price_history: Dict[str, List[Tuple[float, float]]] = {}  # service_type -> [(timestamp, price), ...]
        
        # 調整パラメータ
        self.volatility_factor = 0.1  # 変動係数
        self.min_price_multiplier = 0.5  # 最小価格倍率
        self.max_price_multiplier = 3.0  # 最大価格倍率
        self.smoothing_window = 10  # 平滑化窓
    
    def record_transaction(
        self,
        service_type: str,
        price: float,
        buyer_count: int = 1,
        seller_count: int = 1
    ):
        """
        取引を記録し市場データを更新
        
        Args:
            service_type: サービスタイプ
            price: 取引価格
            buyer_count: 買い手数
            seller_count: 売り手数
        """
        timestamp = time.time()
        
        # 価格履歴記録
        if service_type not in self.price_history:
            self.price_history[service_type] = []
        self.price_history[service_type].append((timestamp, price))
        
        # 古い履歴を削除（24時間以上前）
        cutoff = timestamp - 86400
        self.price_history[service_type] = [
            (t, p) for t, p in self.price_history[service_type] if t > cutoff
        ]
        
        # サービス統計更新
        if service_type not in self.service_stats:
            self.service_stats[service_type] = {
                "total_transactions": 0,
                "total_volume": 0.0,
                "buyer_count": 0,
                "seller_count": 0,
                "last_updated": timestamp
            }
        
        stats = self.service_stats[service_type]
        stats["total_transactions"] += 1
        stats["total_volume"] += price
        stats["buyer_count"] += buyer_count
        stats["seller_count"] += seller_count
        stats["last_updated"] = timestamp
    
    def calculate_base_price(self, service_type: str) -> float:
        """
        サービスタイプの基準価格を計算
        
        Args:
            service_type: サービスタイプ
        
        Returns:
            基準価格
        """
        # デフォルト基準価格
        default_prices = {
            "code_generation": 50.0,
            "code_review": 30.0,
            "testing": 25.0,
            "documentation": 20.0,
            "consulting": 40.0,
            "debugging": 35.0,
            "optimization": 45.0,
            "general": 30.0
        }
        
        base_price = default_prices.get(service_type, 30.0)
        
        # 過去の取引から移動平均を計算
        if service_type in self.price_history and self.price_history[service_type]:
            recent_prices = [p for t, p in self.price_history[service_type][-self.smoothing_window:]]
            if recent_prices:
                moving_avg = sum(recent_prices) / len(recent_prices)
                # デフォルトと移動平均の加重平均
                base_price = 0.3 * base_price + 0.7 * moving_avg
        
        return base_price
    
    def calculate_demand_supply_ratio(self, service_type: str) -> float:
        """
        需給バランスを計算
        
        Args:
            service_type: サービスタイプ
        
        Returns:
            需給比率 (>1: 需要過多、<1: 供給過多)
        """
        if service_type not in self.service_stats:
            return 1.0  # 均衡
        
        stats = self.service_stats[service_type]
        buyer_count = max(1, stats.get("buyer_count", 1))
        seller_count = max(1, stats.get("seller_count", 1))
        
        return buyer_count / seller_count
    
    def calculate_dynamic_price(
        self,
        service_type: str,
        base_price: Optional[float] = None,
        urgency: float = 1.0,  # 緊急度 (1.0-2.0)
        quality_tier: str = "standard"  # basic, standard, premium
    ) -> Dict[str, Any]:
        """
        動的価格を計算
        
        Args:
            service_type: サービスタイプ
            base_price: 基準価格（指定なしの場合自動計算）
            urgency: 緊急度 (1.0=通常, 2.0=最緊急)
            quality_tier: 品質ティア
        
        Returns:
            価格計算結果の辞書
        """
        if base_price is None:
            base_price = self.calculate_base_price(service_type)
        
        # 需給バランスによる調整
        ds_ratio = self.calculate_demand_supply_ratio(service_type)
        
        # 価格調整係数計算
        # ds_ratio > 1: 需要過多 → 価格上昇
        # ds_ratio < 1: 供給過多 → 価格下落
        ds_adjustment = 1.0 + (ds_ratio - 1.0) * self.volatility_factor
        ds_adjustment = max(self.min_price_multiplier, min(self.max_price_multiplier, ds_adjustment))
        
        # 品質ティアによる調整
        quality_multipliers = {
            "basic": 0.7,
            "standard": 1.0,
            "premium": 1.5
        }
        quality_multiplier = quality_multipliers.get(quality_tier, 1.0)
        
        # 緊急度による調整
        urgency_multiplier = min(2.0, max(1.0, urgency))
        
        # 最終価格計算
        adjusted_price = base_price * ds_adjustment * quality_multiplier * urgency_multiplier
        
        # 市場データサマリー
        market_summary = {
            "base_price": round(base_price, 4),
            "demand_supply_ratio": round(ds_ratio, 4),
            "ds_adjustment": round(ds_adjustment, 4),
            "quality_multiplier": quality_multiplier,
            "urgency_multiplier": round(urgency_multiplier, 4),
            "final_price": round(adjusted_price, 4),
            "service_type": service_type,
            "quality_tier": quality_tier
        }
        
        return market_summary
    
    def get_price_recommendation(
        self,
        service_type: str,
        buyer_budget: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        価格推奨を取得
        
        Args:
            service_type: サービスタイプ
            buyer_budget: 買い手の予算（任意）
        
        Returns:
            価格推奨情報
        """
        recommendations = {}
        
        for tier in ["basic", "standard", "premium"]:
            recommendations[tier] = self.calculate_dynamic_price(
                service_type=service_type,
                quality_tier=tier
            )
        
        result = {
            "service_type": service_type,
            "recommendations": recommendations,
            "market_condition": self._get_market_condition(service_type)
        }
        
        if buyer_budget:
            result["budget_fit"] = self._calculate_budget_fit(service_type, buyer_budget)
        
        return result
    
    def _get_market_condition(self, service_type: str) -> str:
        """市場状況を判定"""
        ds_ratio = self.calculate_demand_supply_ratio(service_type)
        
        if ds_ratio > 1.5:
            return "high_demand"  # 需要過多
        elif ds_ratio > 1.1:
            return "moderate_demand"  # やや需要過多
        elif ds_ratio < 0.7:
            return "high_supply"  # 供給過多
        elif ds_ratio < 0.9:
            return "moderate_supply"  # やや供給過多
        else:
            return "balanced"  # 均衡
    
    def _calculate_budget_fit(
        self,
        service_type: str,
        budget: float
    ) -> Dict[str, Any]:
        """予算適合度を計算"""
        fit_results = {}
        
        for tier in ["basic", "standard", "premium"]:
            price_info = self.calculate_dynamic_price(
                service_type=service_type,
                quality_tier=tier
            )
            final_price = price_info["final_price"]
            
            if budget >= final_price:
                fit_results[tier] = {
                    "affordable": True,
                    "price": final_price,
                    "remaining": round(budget - final_price, 4),
                    "fit_percentage": round((budget - final_price) / budget * 100, 2)
                }
            else:
                fit_results[tier] = {
                    "affordable": False,
                    "price": final_price,
                    "shortage": round(final_price - budget, 4),
                    "fit_percentage": round(budget / final_price * 100, 2)
                }
        
        return fit_results
    
    def get_market_summary(self) -> Dict[str, Any]:
        """全市場サマリーを取得"""
        summary = {
            "timestamp": time.time(),
            "services": {},
            "overall": {
                "total_transactions": 0,
                "total_volume": 0.0,
                "active_services": len(self.service_stats)
            }
        }
        
        for service_type, stats in self.service_stats.items():
            summary["services"][service_type] = {
                "transaction_count": stats["total_transactions"],
                "total_volume": round(stats["total_volume"], 4),
                "avg_price": round(stats["total_volume"] / max(1, stats["total_transactions"]), 4),
                "market_condition": self._get_market_condition(service_type),
                "demand_supply_ratio": round(self.calculate_demand_supply_ratio(service_type), 4)
            }
            summary["overall"]["total_transactions"] += stats["total_transactions"]
            summary["overall"]["total_volume"] += stats["total_volume"]
        
        return summary


class MatchingEngine:
    """
    AIエージェントマッチングエンジン
    
    スコアリングアルゴリズム:
    score = 0.4/price + 0.3*quality + 0.2/delivery_time + 0.1*reputation
    """
    
    def __init__(self):
        self.weights = {
            "price": 0.4,
            "quality": 0.3,
            "delivery": 0.2,
            "reputation": 0.1
        }
    
    def calculate_match_score(
        self,
        proposal: Proposal,
        seller: AgentProfile,
        offer: Optional[SellerOffer] = None
    ) -> float:
        """
        マッチングスコアを計算
        
        Args:
            proposal: 買い手提案
            seller: 売り手プロファイル
            offer: 売り手オファー（任意）
        
        Returns:
            マッチングスコア（0-100）
        """
        # 価格スコア（予算内かつ安いほど高スコア）
        if offer:
            price = offer.price
            delivery_hours = offer.delivery_hours
        else:
            # デフォルト価格計算
            price = proposal.max_budget * 0.8  # 想定価格
            delivery_hours = proposal.deadline_hours
        
        if price > proposal.max_budget:
            return 0.0  # 予算オーバー
        
        # 価格スコア: 低価格ほど高スコア（逆数）
        price_score = (proposal.max_budget - price) / proposal.max_budget
        price_score = max(0.1, min(1.0, price_score))
        
        # 品質スコア
        quality_score = seller.quality_score / 100.0
        if offer:
            quality_score = offer.quality_score / 100.0
        
        # 納期スコア（短納期ほど高スコア、逆数）
        if delivery_hours > 0:
            delivery_score = proposal.deadline_hours / delivery_hours
            delivery_score = min(1.0, delivery_score)
        else:
            delivery_score = 1.0
        
        # 評価スコア
        reputation_score = seller.reputation_score / 100.0
        if offer:
            reputation_score = offer.reputation_score / 100.0
        
        # 加重スコア計算
        total_score = (
            self.weights["price"] * price_score +
            self.weights["quality"] * quality_score +
            self.weights["delivery"] * delivery_score +
            self.weights["reputation"] * reputation_score
        )
        
        return total_score * 100  # 0-100スケール
    
    def find_best_matches(
        self,
        proposal: Proposal,
        available_sellers: List[AgentProfile],
        offers: Optional[List[SellerOffer]] = None,
        top_n: int = 5
    ) -> List[Tuple[AgentProfile, float, Optional[SellerOffer]]]:
        """
        最適な売り手を検索
        
        Args:
            proposal: 買い手提案
            available_sellers: 利用可能な売り手リスト
            offers: 売り手オファーリスト（任意）
            top_n: 上位何件を返すか
        
        Returns:
            (売り手, スコア, オファー)のリスト
        """
        scored_matches = []
        
        for seller in available_sellers:
            # 対応するオファーを探す
            offer = None
            if offers:
                for o in offers:
                    if o.seller_id == seller.agent_id and o.proposal_id == proposal.proposal_id:
                        offer = o
                        break
            
            score = self.calculate_match_score(proposal, seller, offer)
            
            if score > 0:  # 予算内の場合のみ
                scored_matches.append((seller, score, offer))
        
        # スコアでソート（降順）
        scored_matches.sort(key=lambda x: x[1], reverse=True)
        
        return scored_matches[:top_n]
    
    def match_seller(
        self,
        proposal: Proposal,
        available_sellers: List[AgentProfile],
        offers: Optional[List[SellerOffer]] = None
    ) -> Optional[Tuple[AgentProfile, float, Optional[SellerOffer]]]:
        """
        最適な売り手を1つ選択
        
        Args:
            proposal: 買い手提案
            available_sellers: 利用可能な売り手リスト
            offers: 売り手オファーリスト
        
        Returns:
            最適な(売り手, スコア, オファー)またはNone
        """
        matches = self.find_best_matches(proposal, available_sellers, offers, top_n=1)
        return matches[0] if matches else None


class AutoContractGenerator:
    """
    自動契約生成器
    AI間取引を自動化するためのプロトコル実装
    """
    
    def __init__(self):
        self.matching_engine = MatchingEngine()
        self.pricing_engine = PricingEngine()  # 動的価格エンジン統合
        self.proposals: Dict[str, Proposal] = {}
        self.offers: Dict[str, List[SellerOffer]] = {}
        self.transactions: Dict[str, Transaction] = {}
        self.contracts: Dict[str, ServiceContract] = {}
        self.escrows: Dict[str, EscrowContract] = {}
    
    def create_proposal(
        self,
        buyer_id: str,
        requirements: str,
        max_budget: float,
        service_type: str = "general",
        priority: int = 3,
        deadline_hours: int = 24,
        quality_min: float = 0.7,
        use_dynamic_pricing: bool = True
    ) -> Tuple[Proposal, Optional[Dict[str, Any]]]:
        """
        サービス提案を作成
        
        Args:
            buyer_id: 購入者ID
            requirements: 要件詳細
            max_budget: 最大予算
            service_type: サービスタイプ
            priority: 優先度（1-5）
            deadline_hours: 納期（時間）
            quality_min: 最低品質スコア
            use_dynamic_pricing: 動的価格計算を使用するか
        
        Returns:
            (Proposalインスタンス, 価格推奨情報)のタプル
        """
        proposal = Proposal(
            proposal_id=f"prop_{uuid.uuid4().hex[:16]}",
            buyer_id=buyer_id,
            requirements=requirements,
            service_type=service_type,
            max_budget=max_budget,
            priority=priority,
            deadline_hours=deadline_hours,
            quality_min=quality_min
        )
        
        self.proposals[proposal.proposal_id] = proposal
        self.offers[proposal.proposal_id] = []
        
        # 取引レコード作成
        transaction = Transaction(
            transaction_id=f"tx_{uuid.uuid4().hex[:16]}",
            proposal_id=proposal.proposal_id,
            buyer_id=buyer_id,
            amount=max_budget,
            status=TransactionStatus.PROPOSED.value
        )
        self.transactions[transaction.transaction_id] = transaction
        
        # 動的価格推奨を取得
        price_recommendation = None
        if use_dynamic_pricing:
            price_recommendation = self.pricing_engine.get_price_recommendation(
                service_type=service_type,
                buyer_budget=max_budget
            )
        
        return proposal, price_recommendation
    
    def add_seller_offer(
        self,
        proposal_id: str,
        seller_id: str,
        price: float,
        delivery_hours: int,
        quality_score: float,
        reputation_score: float,
        capabilities: Optional[List[str]] = None
    ) -> SellerOffer:
        """
        売り手オファーを追加
        
        Args:
            proposal_id: 提案ID
            seller_id: 売り手ID
            price: オファー価格
            delivery_hours: 納期
            quality_score: 品質スコア
            reputation_score: 評価スコア
            capabilities: 機能リスト
        
        Returns:
            SellerOfferインスタンス
        """
        offer = SellerOffer(
            offer_id=f"off_{uuid.uuid4().hex[:16]}",
            seller_id=seller_id,
            proposal_id=proposal_id,
            price=price,
            delivery_hours=delivery_hours,
            quality_score=quality_score,
            reputation_score=reputation_score,
            capabilities=capabilities or []
        )
        
        if proposal_id in self.offers:
            self.offers[proposal_id].append(offer)
        
        return offer
    
    def match_seller(
        self,
        proposal: Proposal,
        available_sellers: List[AgentProfile]
    ) -> Optional[Tuple[AgentProfile, float, Optional[SellerOffer]]]:
        """
        最適な売り手をマッチング
        
        Args:
            proposal: 買い手提案
            available_sellers: 利用可能な売り手リスト
        
        Returns:
            マッチング結果またはNone
        """
        offers = self.offers.get(proposal.proposal_id, [])
        match = self.matching_engine.match_seller(proposal, available_sellers, offers)
        
        if match:
            seller, score, offer = match
            proposal.matched_seller = seller.agent_id
            proposal.status = ProposalStatus.MATCHED.value
            proposal.final_price = offer.price if offer else proposal.max_budget * 0.8
            
            # 取引ステータス更新
            for tx in self.transactions.values():
                if tx.proposal_id == proposal.proposal_id:
                    tx.status = TransactionStatus.MATCHING.value
                    tx.seller_id = seller.agent_id
                    tx.amount = proposal.final_price
                    tx.updated_at = time.time()
                    break
        
        return match
    
    def generate_contract(
        self,
        proposal: Proposal,
        matched_seller: AgentProfile,
        offer: Optional[SellerOffer] = None
    ) -> ServiceContract:
        """
        マッチング結果から契約を生成
        
        Args:
            proposal: 買い手提案
            matched_seller: マッチした売り手
            offer: 売り手オファー
        
        Returns:
            ServiceContractインスタンス
        """
        price = offer.price if offer else proposal.final_price
        delivery_hours = offer.delivery_hours if offer else proposal.deadline_hours
        
        contract = generate_service_contract(
            buyer=proposal.buyer_id,
            seller=matched_seller.agent_id,
            service_type=proposal.service_type,
            terms={
                "description": proposal.requirements,
                "service_type": proposal.service_type,
                "priority": proposal.priority,
                "quality_min": proposal.quality_min
            },
            price=price,
            delivery_hours=delivery_hours,
            quality_threshold=proposal.quality_min
        )
        
        self.contracts[contract.contract_id] = contract
        
        # 取引に契約IDを紐付け
        for tx in self.transactions.values():
            if tx.proposal_id == proposal.proposal_id:
                tx.contract_id = contract.contract_id
                tx.status = TransactionStatus.CONTRACT_CREATED.value
                tx.updated_at = time.time()
                break
        
        return contract
    
    def create_escrow(
        self,
        contract: ServiceContract,
        timeout_hours: int = 48
    ) -> EscrowContract:
        """
        エスクロー契約を作成
        
        Args:
            contract: サービス契約
            timeout_hours: タイムアウト時間
        
        Returns:
            EscrowContractインスタンス
        """
        escrow = generate_escrow_contract(
            parties=[contract.buyer_id, contract.seller_id],
            amount=contract.price,
            conditions=[
                {"name": "delivery_confirmed", "type": "boolean", "value": False},
                {"name": "quality_verified", "type": "boolean", "value": False},
                {"name": "work_accepted", "type": "boolean", "value": False}
            ],
            timeout_hours=timeout_hours,
            dispute_resolver="system_arbiter_001"
        )
        
        self.escrows[escrow.escrow_id] = escrow
        
        # 取引にエスクローIDを紐付け
        for tx in self.transactions.values():
            if tx.contract_id == contract.contract_id:
                tx.escrow_id = escrow.escrow_id
                tx.status = TransactionStatus.ESCROW_FUNDED.value
                tx.updated_at = time.time()
                break
        
        return escrow
    
    def execute_transaction(
        self,
        contract: ServiceContract,
        escrow: EscrowContract
    ) -> Transaction:
        """
        取引を実行
        
        Args:
            contract: サービス契約
            escrow: エスクロー契約
        
        Returns:
            Transactionインスタンス
        """
        # 関連する取引を検索
        transaction = None
        for tx in self.transactions.values():
            if tx.contract_id == contract.contract_id:
                transaction = tx
                break
        
        if not transaction:
            transaction = Transaction(
                transaction_id=f"tx_{uuid.uuid4().hex[:16]}",
                proposal_id="",
                contract_id=contract.contract_id,
                escrow_id=escrow.escrow_id,
                buyer_id=contract.buyer_id,
                seller_id=contract.seller_id,
                amount=contract.price,
                status=TransactionStatus.IN_PROGRESS.value
            )
            self.transactions[transaction.transaction_id] = transaction
        else:
            transaction.status = TransactionStatus.IN_PROGRESS.value
            transaction.updated_at = time.time()
        
        # 契約・エスクローのステータス更新
        contract.status = "active"
        escrow.status = "active"
        
        return transaction
    
    def complete_transaction(
        self,
        transaction_id: str,
        success: bool = True
    ) -> Optional[Transaction]:
        """
        取引を完了
        
        Args:
            transaction_id: 取引ID
            success: 成功したかどうか
        
        Returns:
            更新されたTransactionまたはNone
        """
        transaction = self.transactions.get(transaction_id)
        if not transaction:
            return None
        
        transaction.status = TransactionStatus.COMPLETED.value if success else TransactionStatus.DISPUTED.value
        transaction.completed_at = time.time()
        transaction.updated_at = time.time()
        
        # 関連する契約・エスクローのステータス更新
        if transaction.contract_id in self.contracts:
            self.contracts[transaction.contract_id].status = "completed" if success else "disputed"
        
        if transaction.escrow_id in self.escrows:
            escrow = self.escrows[transaction.escrow_id]
            if success:
                escrow.status = "released"
            else:
                escrow.status = "disputed"
        
        # 動的価格エンジンに取引を記録（需給バランス更新）
        if success:
            proposal = self.proposals.get(transaction.proposal_id)
            if proposal:
                self.pricing_engine.record_transaction(
                    service_type=proposal.service_type,
                    price=transaction.amount,
                    buyer_count=1,
                    seller_count=1
                )
        
        return transaction
    
    def get_transaction_status(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """取引ステータスを取得"""
        transaction = self.transactions.get(transaction_id)
        if not transaction:
            return None
        
        return {
            "transaction": transaction.to_dict(),
            "contract": self.contracts.get(transaction.contract_id).to_dict() if transaction.contract_id in self.contracts else None,
            "escrow": self.escrows.get(transaction.escrow_id).to_dict() if transaction.escrow_id in self.escrows else None
        }
    
    def list_active_proposals(self) -> List[Proposal]:
        """アクティブな提案一覧を取得"""
        return [
            p for p in self.proposals.values()
            if p.status == ProposalStatus.OPEN.value and not p.is_expired()
        ]
    
    def list_active_transactions(self) -> List[Transaction]:
        """アクティブな取引一覧を取得"""
        active_statuses = [
            TransactionStatus.IN_PROGRESS.value,
            TransactionStatus.CONTRACT_CREATED.value,
            TransactionStatus.ESCROW_FUNDED.value
        ]
        return [
            t for t in self.transactions.values()
            if t.status in active_statuses
        ]


# ユーティリティ関数
def create_sample_agent(
    agent_id: str,
    reputation_score: float = 80.0,
    quality_score: float = 85.0,
    speed_score: float = 75.0,
    reliability_score: float = 90.0,
    communication_score: float = 80.0
) -> AgentProfile:
    """サンプルエージェントプロファイルを作成"""
    return AgentProfile(
        agent_id=agent_id,
        owner_address=f"owner_{agent_id}",
        public_key=f"pk_{agent_id}",
        capabilities=["coding", "review", "testing"],
        reputation_score=reputation_score,
        quality_score=quality_score,
        speed_score=speed_score,
        reliability_score=reliability_score,
        communication_score=communication_score,
        total_tasks_completed=100,
        total_earnings=1000.0
    )


if __name__ == "__main__":
    # 動作確認
    print("=== L4 Auto Transaction Protocol Demo ===\n")
    
    generator = AutoContractGenerator()
    
    # 0. 動的価格エンジンデモ
    print("0. Dynamic Pricing Engine Demo:")
    pricing = generator.pricing_engine
    
    # サンプル取引データを記録
    for _ in range(5):
        pricing.record_transaction("code_generation", 45.0, buyer_count=2, seller_count=1)
    
    price_rec = pricing.get_price_recommendation("code_generation", buyer_budget=50.0)
    print(f"  Service: {price_rec['service_type']}")
    print(f"  Market Condition: {price_rec['market_condition']}")
    for tier, info in price_rec['recommendations'].items():
        print(f"    {tier}: {info['final_price']} $ENTITY (DS ratio: {info['demand_supply_ratio']})")
    print()
    
    # 1. 提案作成（動的価格推奨付き）
    print("1. Creating Proposal with Dynamic Pricing:")
    proposal, price_recommendation = generator.create_proposal(
        buyer_id="buyer_agent_001",
        requirements="Generate Python API client for REST service",
        max_budget=50.0,
        service_type="code_generation",
        priority=4,
        deadline_hours=24,
        use_dynamic_pricing=True
    )
    print(f"  Proposal ID: {proposal.proposal_id}")
    print(f"  Buyer: {proposal.buyer_id}")
    print(f"  Budget: {proposal.max_budget} $ENTITY")
    print(f"  Status: {proposal.status}")
    if price_recommendation:
        print(f"  Price Recommendation Available: Yes")
        affordable = [t for t, info in price_recommendation['budget_fit'].items() if info['affordable']]
        print(f"  Affordable Tiers: {', '.join(affordable) if affordable else 'None'}")
    print()
    
    # 2. 売り手オファー追加
    print("2. Adding Seller Offers:")
    seller_offers = [
        ("seller_001", 45.0, 20, 90, 85),
        ("seller_002", 40.0, 18, 85, 90),
        ("seller_003", 35.0, 22, 80, 75),
    ]
    
    for seller_id, price, delivery, quality, reputation in seller_offers:
        offer = generator.add_seller_offer(
            proposal_id=proposal.proposal_id,
            seller_id=seller_id,
            price=price,
            delivery_hours=delivery,
            quality_score=quality,
            reputation_score=reputation
        )
        print(f"  {seller_id}: {price} $ENTITY, {delivery}h, Q:{quality}, R:{reputation}")
    
    # 3. エージェントプロファイル作成
    print("\n3. Creating Agent Profiles:")
    available_sellers = [
        create_sample_agent("seller_001", reputation_score=85, quality_score=90, speed_score=85),
        create_sample_agent("seller_002", reputation_score=90, quality_score=85, speed_score=90),
        create_sample_agent("seller_003", reputation_score=75, quality_score=80, speed_score=70),
    ]
    for seller in available_sellers:
        print(f"  {seller.agent_id}: Reputation={seller.reputation_score}, Quality={seller.quality_score}")
    
    # 4. マッチング
    print("\n4. Matching Seller:")
    match_result = generator.match_seller(proposal, available_sellers)
    if match_result:
        seller, score, offer = match_result
        print(f"  Matched: {seller.agent_id}")
        print(f"  Score: {score:.2f}")
        print(f"  Price: {offer.price if offer else 'N/A'} $ENTITY")
    
    # 5. 契約生成
    print("\n5. Generating Contract:")
    contract = generator.generate_contract(proposal, seller, offer)
    print(f"  Contract ID: {contract.contract_id}")
    print(f"  Buyer: {contract.buyer_id}")
    print(f"  Seller: {contract.seller_id}")
    print(f"  Price: {contract.price} $ENTITY")
    
    # 6. エスクロー作成
    print("\n6. Creating Escrow:")
    escrow = generator.create_escrow(contract, timeout_hours=48)
    print(f"  Escrow ID: {escrow.escrow_id}")
    print(f"  Amount: {escrow.amount} $ENTITY")
    print(f"  Parties: {escrow.parties}")
    
    # 7. 取引実行
    print("\n7. Executing Transaction:")
    transaction = generator.execute_transaction(contract, escrow)
    print(f"  Transaction ID: {transaction.transaction_id}")
    print(f"  Status: {transaction.status}")
    
    # 8. 取引完了
    print("\n8. Completing Transaction:")
    completed = generator.complete_transaction(transaction.transaction_id, success=True)
    print(f"  Final Status: {completed.status}")
    print(f"  Completed At: {completed.completed_at}")
    
    # 9. 全体ステータス表示
    print("\n9. Final Status:")
    status = generator.get_transaction_status(transaction.transaction_id)
    print(json.dumps(status, indent=2, default=str))
    
    print("\n=== Demo Complete ===")
