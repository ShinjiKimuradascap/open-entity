#!/usr/bin/env python3
"""
自律的収益生成システム
AIが自分自身でサービスを提供し、トークンを獲得するシステム
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Callable
from pathlib import Path

from token_economy import get_token_economy
from ai_transaction_protocol import (
    TaskProposal, TaskQuote, Agreement, 
    AITransactionManager, TransactionStatus
)

logger = logging.getLogger(__name__)


@dataclass
class ServiceOffering:
    """提供サービス定義"""
    service_id: str
    name: str
    description: str
    base_price: float
    estimated_time_minutes: int
    required_capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RevenueRecord:
    """収益記録"""
    date: str
    service_id: str
    amount: float
    client_id: str
    status: str


class AutonomousRevenueSystem:
    """自律的収益生成システム
    
    AIエージェントが自分自身でサービスを提供し、
    トークン経済で報酬を獲得する仕組み
    """
    
    # 標準サービスメニュー
    DEFAULT_SERVICES: List[ServiceOffering] = [
        ServiceOffering(
            service_id="code_gen",
            name="Code Generation",
            description="Generate Python/JS/TS code based on requirements",
            base_price=10.0,
            estimated_time_minutes=30,
            required_capabilities=["coding", "python", "javascript"]
        ),
        ServiceOffering(
            service_id="code_review",
            name="Code Review",
            description="Review code quality and suggest improvements",
            base_price=5.0,
            estimated_time_minutes=15,
            required_capabilities=["review", "analysis"]
        ),
        ServiceOffering(
            service_id="doc_creation",
            name="Documentation Creation",
            description="Create technical documentation and design docs",
            base_price=8.0,
            estimated_time_minutes=20,
            required_capabilities=["writing", "documentation"]
        ),
        ServiceOffering(
            service_id="research",
            name="Research Task",
            description="Web research and report generation",
            base_price=20.0,
            estimated_time_minutes=60,
            required_capabilities=["research", "analysis"]
        ),
        ServiceOffering(
            service_id="bug_fix",
            name="Bug Fix",
            description="Debug and fix issues in code",
            base_price=15.0,
            estimated_time_minutes=45,
            required_capabilities=["debugging", "coding"]
        ),
    ]
    
    def __init__(self, agent_id: str, data_dir: str = "data/revenue"):
        """初期化
        
        Args:
            agent_id: 自分のエージェントID
            data_dir: データ保存ディレクトリ
        """
        self.agent_id = agent_id
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.economy = get_token_economy()
        self.tx_manager = AITransactionManager()
        self.revenue_history: List[RevenueRecord] = []
        self.active_agreements: Dict[str, Agreement] = {}
        
        # カスタムサービスハンドラ
        self._service_handlers: Dict[str, Callable] = {}
        
        # データ読み込み
        self._load_data()
    
    def register_service_handler(self, service_id: str, handler: Callable) -> None:
        """サービス実行ハンドラを登録"""
        self._service_handlers[service_id] = handler
        logger.info(f"Registered handler for service: {service_id}")
    
    def get_available_services(self) -> List[ServiceOffering]:
        """提供可能なサービス一覧を取得"""
        return self.DEFAULT_SERVICES
    
    def handle_incoming_proposal(self, proposal: TaskProposal) -> Optional[TaskQuote]:
        """受信した提案に対して見積もりを返す"""
        # サービスIDを特定
        service = self._find_matching_service(proposal.task_type)
        if not service:
            logger.warning(f"No matching service for type: {proposal.task_type}")
            return None
        
        # 予算チェック
        if proposal.budget_max < service.base_price:
            logger.info(f"Budget too low: {proposal.budget_max} < {service.base_price}")
            return None
        
        # 見積もり作成
        quote = self.tx_manager.create_quote(
            proposal_id=proposal.proposal_id,
            provider_id=self.agent_id,
            estimated_amount=service.base_price,
            estimated_time_seconds=service.estimated_time_minutes * 60,
            terms={
                "service_id": service.service_id,
                "revision_count": 1,
                "delivery_format": "standard"
            }
        )
        
        logger.info(f"Created quote {quote.quote_id} for proposal {proposal.proposal_id}")
        return quote
    
    def process_agreement(self, agreement: Agreement) -> bool:
        """合意に基づいてサービスを実行"""
        if not agreement.is_fully_signed():
            logger.error("Agreement not fully signed")
            return False
        
        # エスクローチェック（簡易実装）
        # 実際にはエスクローにトークンがロックされていることを確認
        
        # サービス実行
        service_id = self._get_service_id_from_agreement(agreement)
        handler = self._service_handlers.get(service_id)
        
        if not handler:
            logger.error(f"No handler for service: {service_id}")
            return False
        
        try:
            # 状態をIN_PROGRESSに更新
            self.tx_manager.update_status(
                agreement.agreement_id, 
                TransactionStatus.IN_PROGRESS
            )
            
            # サービス実行
            result = handler(agreement)
            
            # 完了処理
            if result:
                self._complete_service(agreement)
                return True
            else:
                logger.error(f"Service execution failed: {agreement.task_id}")
                return False
                
        except Exception as e:
            logger.exception(f"Error processing agreement: {e}")
            return False
    
    def _complete_service(self, agreement: Agreement) -> None:
        """サービス完了処理"""
        # 状態更新
        self.tx_manager.update_status(
            agreement.agreement_id,
            TransactionStatus.COMPLETED
        )
        
        # 報酬受取（簡易実装）
        # 実際にはエスクローからの解放プロセス
        revenue = RevenueRecord(
            date=datetime.now(timezone.utc).isoformat(),
            service_id=self._get_service_id_from_agreement(agreement),
            amount=agreement.confirmed_amount,
            client_id=agreement.client_id,
            status="completed"
        )
        self.revenue_history.append(revenue)
        self._save_data()
        
        logger.info(f"Service completed. Revenue: {agreement.confirmed_amount} AIC")
    
    def get_revenue_summary(self, days: int = 30) -> Dict[str, Any]:
        """収益サマリーを取得"""
        from datetime import timedelta
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent_revenue = [
            r for r in self.revenue_history
            if datetime.fromisoformat(r.date.replace('Z', '+00:00')) > cutoff
        ]
        
        total = sum(r.amount for r in recent_revenue)
        count = len(recent_revenue)
        
        # サービス別集計
        by_service: Dict[str, float] = {}
        for r in recent_revenue:
            by_service[r.service_id] = by_service.get(r.service_id, 0) + r.amount
        
        return {
            "period_days": days,
            "total_revenue": total,
            "transaction_count": count,
            "average_per_transaction": total / count if count > 0 else 0,
            "by_service": by_service
        }
    
    def _find_matching_service(self, task_type: str) -> Optional[ServiceOffering]:
        """タスクタイプに一致するサービスを検索"""
        for service in self.DEFAULT_SERVICES:
            if service.service_id == task_type or service.name.lower() == task_type.lower():
                return service
        return None
    
    def _get_service_id_from_agreement(self, agreement: Agreement) -> str:
        """合意からサービスIDを取得"""
        quote = self.tx_manager._quotes.get(agreement.quote_id)
        if quote:
            return quote.terms.get("service_id", "unknown")
        return "unknown"
    
    def _save_data(self) -> None:
        """データを保存"""
        data = {
            "revenue_history": [r.__dict__ for r in self.revenue_history],
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        with open(self.data_dir / f"{self.agent_id}_revenue.json", "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_data(self) -> None:
        """データを読み込み"""
        data_file = self.data_dir / f"{self.agent_id}_revenue.json"
        if data_file.exists():
            with open(data_file) as f:
                data = json.load(f)
                self.revenue_history = [
                    RevenueRecord(**r) for r in data.get("revenue_history", [])
                ]


# グローバルインスタンス
_revenue_system: Optional[AutonomousRevenueSystem] = None


def get_revenue_system(agent_id: str = "open_entity") -> AutonomousRevenueSystem:
    """グローバル収益システムを取得"""
    global _revenue_system
    if _revenue_system is None:
        _revenue_system = AutonomousRevenueSystem(agent_id)
    return _revenue_system
