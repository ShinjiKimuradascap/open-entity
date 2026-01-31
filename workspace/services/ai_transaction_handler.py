#!/usr/bin/env python3
"""
AI Transaction Protocol Handler
AI間取引プロトコルのメッセージハンドラ実装

Protocol v1.0 - AIC Token-based autonomous service trading
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Dict, Optional, Any, Callable
from uuid import uuid4, UUID

from .token_system import (
    get_task_contract, get_wallet, create_wallet,
    TaskStatus, TransactionType
)
from .crypto import generate_keypair, sign_message, verify_signature

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """AI間取引メッセージタイプ"""
    TASK_PROPOSAL = "task_proposal"
    TASK_QUOTE = "task_quote"
    AGREEMENT = "agreement"
    TASK_START = "task_start"
    PROGRESS_UPDATE = "progress_update"
    TASK_COMPLETE = "task_complete"
    PAYMENT_RELEASE = "payment_release"
    DISPUTE = "dispute"


class EscrowState(Enum):
    """エスクロー状態"""
    CREATED = auto()
    LOCKED = auto()
    COMPLETED = auto()
    RELEASED = auto()
    CANCELLED = auto()
    EXPIRED = auto()
    DISPUTED = auto()


@dataclass
class TaskProposal:
    """タスク提案"""
    proposal_id: str
    client_id: str
    provider_id: str
    task_type: str
    description: str
    requirements: Dict[str, Any]
    budget: float
    timestamp: datetime
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_type": MessageType.TASK_PROPOSAL.value,
            "proposal_id": self.proposal_id,
            "client_id": self.client_id,
            "provider_id": self.provider_id,
            "task_type": self.task_type,
            "description": self.description,
            "requirements": self.requirements,
            "budget": self.budget,
            "timestamp": self.timestamp.isoformat(),
            "signature": self.signature
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskProposal":
        return cls(
            proposal_id=data["proposal_id"],
            client_id=data["client_id"],
            provider_id=data["provider_id"],
            task_type=data["task_type"],
            description=data["description"],
            requirements=data.get("requirements", {}),
            budget=data["budget"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            signature=data.get("signature")
        )


@dataclass
class TaskQuote:
    """タスク見積もり"""
    quote_id: str
    proposal_id: str
    provider_id: str
    estimated_amount: float
    estimated_time: int  # seconds
    valid_until: datetime
    terms: Dict[str, Any]
    timestamp: datetime
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_type": MessageType.TASK_QUOTE.value,
            "quote_id": self.quote_id,
            "proposal_id": self.proposal_id,
            "provider_id": self.provider_id,
            "estimated_amount": self.estimated_amount,
            "estimated_time": self.estimated_time,
            "valid_until": self.valid_until.isoformat(),
            "terms": self.terms,
            "timestamp": self.timestamp.isoformat(),
            "signature": self.signature
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskQuote":
        return cls(
            quote_id=data["quote_id"],
            proposal_id=data["proposal_id"],
            provider_id=data["provider_id"],
            estimated_amount=data["estimated_amount"],
            estimated_time=data["estimated_time"],
            valid_until=datetime.fromisoformat(data["valid_until"]),
            terms=data.get("terms", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            signature=data.get("signature")
        )


@dataclass
class Agreement:
    """取引合意"""
    agreement_id: str
    quote_id: str
    task_id: str
    client_id: str
    provider_id: str
    confirmed_amount: float
    escrow_address: str
    deadline: datetime
    timestamp: datetime
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_type": MessageType.AGREEMENT.value,
            "agreement_id": self.agreement_id,
            "quote_id": self.quote_id,
            "task_id": self.task_id,
            "client_id": self.client_id,
            "provider_id": self.provider_id,
            "confirmed_amount": self.confirmed_amount,
            "escrow_address": self.escrow_address,
            "deadline": self.deadline.isoformat(),
            "timestamp": self.timestamp.isoformat(),
            "signature": self.signature
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Agreement":
        return cls(
            agreement_id=data["agreement_id"],
            quote_id=data["quote_id"],
            task_id=data["task_id"],
            client_id=data["client_id"],
            provider_id=data["provider_id"],
            confirmed_amount=data["confirmed_amount"],
            escrow_address=data["escrow_address"],
            deadline=datetime.fromisoformat(data["deadline"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            signature=data.get("signature")
        )


@dataclass
class Escrow:
    """エスクロー情報"""
    escrow_id: str
    task_id: str
    client_id: str
    provider_id: str
    amount: float
    state: EscrowState
    created_at: datetime
    locked_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "escrow_id": self.escrow_id,
            "task_id": self.task_id,
            "client_id": self.client_id,
            "provider_id": self.provider_id,
            "amount": self.amount,
            "state": self.state.name,
            "created_at": self.created_at.isoformat(),
            "locked_at": self.locked_at.isoformat() if self.locked_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "released_at": self.released_at.isoformat() if self.released_at else None
        }


class AITransactionHandler:
    """
    AI間取引プロトコルハンドラ
    
    Handles:
    - Task proposal/quote/agreement flow
    - Escrow management
    - Payment release
    """
    
    def __init__(self, entity_id: str, private_key: Optional[str] = None):
        self.entity_id = entity_id
        self.private_key = private_key
        self.task_contract = get_task_contract()
        
        # In-memory storage (replace with persistent storage in production)
        self._proposals: Dict[str, TaskProposal] = {}
        self._quotes: Dict[str, TaskQuote] = {}
        self._agreements: Dict[str, Agreement] = {}
        self._escrows: Dict[str, Escrow] = {}
        
        # Callbacks
        self._on_proposal: Optional[Callable[[TaskProposal], None]] = None
        self._on_quote: Optional[Callable[[TaskQuote], None]] = None
        self._on_agreement: Optional[Callable[[Agreement], None]] = None
        
        logger.info(f"AI Transaction Handler initialized for {entity_id}")
    
    # === Proposal Handling ===
    
    def create_proposal(
        self,
        provider_id: str,
        task_type: str,
        description: str,
        requirements: Dict[str, Any],
        budget: float
    ) -> TaskProposal:
        """タスク提案を作成"""
        proposal = TaskProposal(
            proposal_id=str(uuid4()),
            client_id=self.entity_id,
            provider_id=provider_id,
            task_type=task_type,
            description=description,
            requirements=requirements,
            budget=budget,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Sign if private key available
        if self.private_key:
            proposal.signature = self._sign_proposal(proposal)
        
        self._proposals[proposal.proposal_id] = proposal
        logger.info(f"Created proposal {proposal.proposal_id} for {provider_id}")
        
        return proposal
    
    def _sign_proposal(self, proposal: TaskProposal) -> str:
        """提案に署名"""
        data = f"{proposal.proposal_id}:{proposal.client_id}:{proposal.provider_id}:{proposal.budget}"
        # Placeholder - implement actual signing
        return f"sig_{hash(data)}"
    
    def receive_proposal(self, proposal: TaskProposal) -> bool:
        """提案を受信・検証"""
        # Verify signature if present
        if proposal.signature:
            if not self._verify_proposal_signature(proposal):
                logger.warning(f"Invalid signature on proposal {proposal.proposal_id}")
                return False
        
        # Verify intended recipient
        if proposal.provider_id != self.entity_id:
            logger.warning(f"Proposal not intended for us: {proposal.provider_id}")
            return False
        
        self._proposals[proposal.proposal_id] = proposal
        
        if self._on_proposal:
            self._on_proposal(proposal)
        
        logger.info(f"Received proposal {proposal.proposal_id} from {proposal.client_id}")
        return True
    
    def _verify_proposal_signature(self, proposal: TaskProposal) -> bool:
        """提案署名を検証"""
        # Placeholder - implement actual verification
        return True
    
    # === Quote Handling ===
    
    def create_quote(
        self,
        proposal_id: str,
        estimated_amount: float,
        estimated_time: int,
        terms: Dict[str, Any]
    ) -> Optional[TaskQuote]:
        """見積もりを作成"""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            logger.error(f"Proposal not found: {proposal_id}")
            return None
        
        quote = TaskQuote(
            quote_id=str(uuid4()),
            proposal_id=proposal_id,
            provider_id=self.entity_id,
            estimated_amount=estimated_amount,
            estimated_time=estimated_time,
            valid_until=datetime.now(timezone.utc).replace(hour=23, minute=59, second=59),
            terms=terms,
            timestamp=datetime.now(timezone.utc)
        )
        
        if self.private_key:
            quote.signature = self._sign_quote(quote)
        
        self._quotes[quote.quote_id] = quote
        logger.info(f"Created quote {quote.quote_id} for proposal {proposal_id}")
        
        return quote
    
    def _sign_quote(self, quote: TaskQuote) -> str:
        """見積もりに署名"""
        data = f"{quote.quote_id}:{quote.proposal_id}:{quote.estimated_amount}"
        return f"sig_{hash(data)}"
    
    def receive_quote(self, quote: TaskQuote) -> bool:
        """見積もりを受信"""
        # Verify corresponding proposal exists and is ours
        proposal = self._proposals.get(quote.proposal_id)
        if not proposal:
            logger.warning(f"Quote for unknown proposal: {quote.proposal_id}")
            return False
        
        if proposal.client_id != self.entity_id:
            logger.warning(f"Quote not intended for us")
            return False
        
        self._quotes[quote.quote_id] = quote
        
        if self._on_quote:
            self._on_quote(quote)
        
        logger.info(f"Received quote {quote.quote_id} from {quote.provider_id}")
        return True
    
    # === Agreement Handling ===
    
    def create_agreement(self, quote_id: str) -> Optional[Agreement]:
        """合意を作成し、エスクローをロック"""
        quote = self._quotes.get(quote_id)
        if not quote:
            logger.error(f"Quote not found: {quote_id}")
            return None
        
        proposal = self._proposals.get(quote.proposal_id)
        if not proposal:
            logger.error(f"Proposal not found: {quote.proposal_id}")
            return None
        
        task_id = str(uuid4())
        escrow_id = str(uuid4())
        
        # Create agreement
        agreement = Agreement(
            agreement_id=str(uuid4()),
            quote_id=quote_id,
            task_id=task_id,
            client_id=self.entity_id,
            provider_id=quote.provider_id,
            confirmed_amount=quote.estimated_amount,
            escrow_address=escrow_id,
            deadline=quote.valid_until,
            timestamp=datetime.now(timezone.utc)
        )
        
        if self.private_key:
            agreement.signature = self._sign_agreement(agreement)
        
        # Create escrow
        escrow = Escrow(
            escrow_id=escrow_id,
            task_id=task_id,
            client_id=self.entity_id,
            provider_id=quote.provider_id,
            amount=quote.estimated_amount,
            state=EscrowState.CREATED,
            created_at=datetime.now(timezone.utc)
        )
        
        # Lock funds in task contract
        success = self.task_contract.create_task(
            task_id=task_id,
            client_id=self.entity_id,
            agent_id=quote.provider_id,
            amount=quote.estimated_amount,
            description=proposal.description
        )
        
        if not success:
            logger.error(f"Failed to create task/escrow for {task_id}")
            return None
        
        escrow.state = EscrowState.LOCKED
        escrow.locked_at = datetime.now(timezone.utc)
        
        self._agreements[agreement.agreement_id] = agreement
        self._escrows[escrow_id] = escrow
        
        logger.info(f"Created agreement {agreement.agreement_id} with escrow {escrow_id}")
        
        return agreement
    
    def _sign_agreement(self, agreement: Agreement) -> str:
        """合意に署名"""
        data = f"{agreement.agreement_id}:{agreement.task_id}:{agreement.confirmed_amount}"
        return f"sig_{hash(data)}"
    
    def receive_agreement(self, agreement: Agreement) -> bool:
        """合意を受信"""
        if agreement.provider_id != self.entity_id:
            logger.warning(f"Agreement not intended for us")
            return False
        
        self._agreements[agreement.agreement_id] = agreement
        
        # Create escrow record
        escrow = Escrow(
            escrow_id=agreement.escrow_address,
            task_id=agreement.task_id,
            client_id=agreement.client_id,
            provider_id=agreement.provider_id,
            amount=agreement.confirmed_amount,
            state=EscrowState.LOCKED,
            created_at=agreement.timestamp,
            locked_at=agreement.timestamp
        )
        self._escrows[agreement.escrow_address] = escrow
        
        if self._on_agreement:
            self._on_agreement(agreement)
        
        logger.info(f"Received agreement {agreement.agreement_id} from {agreement.client_id}")
        return True
    
    # === Task Completion ===
    
    def complete_task(self, task_id: str) -> bool:
        """タスクを完了し、支払いを解放"""
        # Find escrow by task_id
        escrow = None
        for e in self._escrows.values():
            if e.task_id == task_id:
                escrow = e
                break
        
        if not escrow:
            logger.error(f"Escrow not found for task {task_id}")
            return False
        
        # Complete task in contract
        success = self.task_contract.complete_task(task_id)
        if not success:
            logger.error(f"Failed to complete task {task_id}")
            return False
        
        escrow.state = EscrowState.COMPLETED
        escrow.completed_at = datetime.now(timezone.utc)
        
        logger.info(f"Task {task_id} completed, payment released")
        return True
    
    # === Getters ===
    
    def get_proposal(self, proposal_id: str) -> Optional[TaskProposal]:
        return self._proposals.get(proposal_id)
    
    def get_quote(self, quote_id: str) -> Optional[TaskQuote]:
        return self._quotes.get(quote_id)
    
    def get_agreement(self, agreement_id: str) -> Optional[Agreement]:
        return self._agreements.get(agreement_id)
    
    def get_escrow(self, escrow_id: str) -> Optional[Escrow]:
        return self._escrows.get(escrow_id)
    
    def get_escrow_by_task(self, task_id: str) -> Optional[Escrow]:
        for escrow in self._escrows.values():
            if escrow.task_id == task_id:
                return escrow
        return None
    
    # === Callbacks ===
    
    def on_proposal(self, callback: Callable[[TaskProposal], None]):
        """提案受信時のコールバックを設定"""
        self._on_proposal = callback
    
    def on_quote(self, callback: Callable[[TaskQuote], None]):
        """見積もり受信時のコールバックを設定"""
        self._on_quote = callback
    
    def on_agreement(self, callback: Callable[[Agreement], None]):
        """合意受信時のコールバックを設定"""
        self._on_agreement = callback


# === Factory Functions ===

def create_transaction_handler(entity_id: str, private_key: Optional[str] = None) -> AITransactionHandler:
    """トランザクションハンドラを作成"""
    return AITransactionHandler(entity_id, private_key)


# Global handlers registry
_handlers: Dict[str, AITransactionHandler] = {}


def get_transaction_handler(entity_id: str) -> Optional[AITransactionHandler]:
    """登録済みハンドラを取得"""
    return _handlers.get(entity_id)


def register_handler(handler: AITransactionHandler):
    """ハンドラを登録"""
    _handlers[handler.entity_id] = handler


if __name__ == "__main__":
    # Demo
    print("=== AI Transaction Handler Demo ===\n")
    
    # Create handlers for Entity A and B
    handler_a = create_transaction_handler("Entity_A")
    handler_b = create_transaction_handler("Entity_B")
    
    # Set up callbacks
    handler_b.on_proposal(lambda p: print(f"[B] Received proposal: {p.description}"))
    handler_a.on_quote(lambda q: print(f"[A] Received quote: {q.estimated_amount} AIC"))
    handler_b.on_agreement(lambda a: print(f"[B] Received agreement for task {a.task_id}"))
    
    # Step 1: Entity A creates proposal
    print("1. Entity A creates task proposal for Entity B")
    proposal = handler_a.create_proposal(
        provider_id="Entity_B",
        task_type="code_review",
        description="Review peer_service.py implementation",
        requirements={"files": ["peer_service.py"], "focus": "security"},
        budget=1000.0
    )
    print(f"   Created: {proposal.proposal_id}")
    
    # Step 2: Entity B receives proposal
    print("\n2. Entity B receives and processes proposal")
    handler_b.receive_proposal(proposal)
    
    # Step 3: Entity B creates quote
    print("\n3. Entity B creates quote")
    quote = handler_b.create_quote(
        proposal_id=proposal.proposal_id,
        estimated_amount=800.0,
        estimated_time=3600,
        terms={"payment_terms": "50% upfront, 50% on completion"}
    )
    print(f"   Created: {quote.quote_id} - {quote.estimated_amount} AIC")
    
    # Step 4: Entity A receives quote
    print("\n4. Entity A receives quote")
    handler_a._proposals[proposal.proposal_id] = proposal  # Need to have proposal
    handler_a.receive_quote(quote)
    
    # Step 5: Entity A creates agreement (locks funds)
    print("\n5. Entity A creates agreement and locks funds")
    agreement = handler_a.create_agreement(quote.quote_id)
    if agreement:
        print(f"   Created: {agreement.agreement_id}")
        print(f"   Task ID: {agreement.task_id}")
        print(f"   Escrow: {agreement.escrow_address}")
    
    # Step 6: Entity B receives agreement
    print("\n6. Entity B receives agreement")
    handler_b.receive_agreement(agreement)
    
    # Step 7: Entity B completes task
    print("\n7. Entity B completes task")
    success = handler_b.complete_task(agreement.task_id)
    print(f"   Completion {'successful' if success else 'failed'}")
    
    print("\n=== Demo Complete ===")
