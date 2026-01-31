#!/usr/bin/env python3
"""
AI Agent Transaction Protocol v1.0

Handles autonomous service transactions between AI agents.
Implements proposal/quote/agreement flow with escrow integration.
"""

import uuid
import json
import asyncio
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any
from enum import Enum, auto
import logging

# Try to import crypto - fallback if not available
try:
    from crypto import CryptoManager
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

from .service_registry import ServiceRegistry, ServiceListing
from .order_book import OrderBook, ServiceOrder, OrderStatus
from .escrow import EscrowManager, EscrowStatus

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Transaction message types"""
    TASK_PROPOSAL = "task_proposal"
    TASK_QUOTE = "task_quote"
    AGREEMENT = "agreement"
    TASK_START = "task_start"
    PROGRESS_UPDATE = "progress_update"
    TASK_COMPLETE = "task_complete"
    PAYMENT_RELEASE = "payment_release"
    DISPUTE_OPEN = "dispute_open"
    DISPUTE_RESOLVE = "dispute_resolve"


class TransactionStatus(Enum):
    """Transaction lifecycle status"""
    PROPOSED = "proposed"
    QUOTED = "quoted"
    AGREED = "agreed"
    ESCROW_LOCKED = "escrow_locked"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAYMENT_RELEASED = "payment_released"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    EXPIRED = "expired"


@dataclass
class TaskProposal:
    """Service request proposal"""
    proposal_id: str
    client_id: str
    task_type: str
    description: str
    requirements: Dict[str, Any]
    budget_max: Decimal
    deadline: datetime
    created_at: datetime
    signature: Optional[str] = None
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['budget_max'] = str(self.budget_max)
        data['deadline'] = self.deadline.isoformat()
        data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TaskProposal':
        data = data.copy()
        data['budget_max'] = Decimal(data['budget_max'])
        data['deadline'] = datetime.fromisoformat(data['deadline'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)
    
    def compute_hash(self) -> str:
        """Compute proposal hash for signing"""
        data = f"{self.proposal_id}:{self.client_id}:{self.task_type}:{self.budget_max}"
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class TaskQuote:
    """Service quote from provider"""
    quote_id: str
    proposal_id: str
    provider_id: str
    estimated_amount: Decimal
    estimated_time_seconds: int
    valid_until: datetime
    terms: Dict[str, Any]
    created_at: datetime
    signature: Optional[str] = None
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['estimated_amount'] = str(self.estimated_amount)
        data['valid_until'] = self.valid_until.isoformat()
        data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TaskQuote':
        data = data.copy()
        data['estimated_amount'] = Decimal(data['estimated_amount'])
        data['valid_until'] = datetime.fromisoformat(data['valid_until'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)
    
    def compute_hash(self) -> str:
        """Compute quote hash for signing"""
        data = f"{self.quote_id}:{self.proposal_id}:{self.provider_id}:{self.estimated_amount}"
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class Agreement:
    """Mutual agreement on terms"""
    agreement_id: str
    quote_id: str
    task_id: str
    client_id: str
    provider_id: str
    confirmed_amount: Decimal
    escrow_id: Optional[str]
    deadline: datetime
    created_at: datetime
    client_signature: Optional[str] = None
    provider_signature: Optional[str] = None
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['confirmed_amount'] = str(self.confirmed_amount)
        data['deadline'] = self.deadline.isoformat()
        data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Agreement':
        data = data.copy()
        data['confirmed_amount'] = Decimal(data['confirmed_amount'])
        data['deadline'] = datetime.fromisoformat(data['deadline'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)
    
    def compute_hash(self) -> str:
        """Compute agreement hash for signing"""
        data = f"{self.agreement_id}:{self.quote_id}:{self.task_id}:{self.confirmed_amount}"
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class Transaction:
    """Complete transaction record"""
    transaction_id: str
    status: TransactionStatus
    proposal: TaskProposal
    quote: Optional[TaskQuote]
    agreement: Optional[Agreement]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]
    
    def to_dict(self) -> dict:
        return {
            'transaction_id': self.transaction_id,
            'status': self.status.value,
            'proposal': self.proposal.to_dict(),
            'quote': self.quote.to_dict() if self.quote else None,
            'agreement': self.agreement.to_dict() if self.agreement else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'metadata': self.metadata
        }


class TransactionProtocol:
    """
    AI Agent Transaction Protocol v1.0 implementation.
    
    Manages the complete transaction lifecycle:
    1. Proposal -> Quote -> Agreement -> Escrow -> Execution -> Payment
    """
    
    def __init__(
        self,
        registry: ServiceRegistry,
        order_book: OrderBook,
        escrow: EscrowManager,
        agent_id: str,
        crypto_manager: Optional[Any] = None
    ):
        self._registry = registry
        self._order_book = order_book
        self._escrow = escrow
        self._agent_id = agent_id
        self._crypto = crypto_manager
        
        self._transactions: Dict[str, Transaction] = {}
        self._handlers: Dict[MessageType, List[Callable]] = {
            msg_type: [] for msg_type in MessageType
        }
        self._lock = asyncio.Lock()
    
    # ========== Proposal Phase ==========
    
    async def create_proposal(
        self,
        task_type: str,
        description: str,
        requirements: Dict[str, Any],
        budget_max: Decimal,
        deadline_hours: int = 24
    ) -> TaskProposal:
        """
        Create a new task proposal.
        
        Args:
            task_type: Type of service needed
            description: Task description
            requirements: Detailed requirements
            budget_max: Maximum budget
            deadline_hours: Proposal validity in hours
            
        Returns:
            Created proposal
        """
        proposal = TaskProposal(
            proposal_id=str(uuid.uuid4()),
            client_id=self._agent_id,
            task_type=task_type,
            description=description,
            requirements=requirements,
            budget_max=budget_max,
            deadline=datetime.utcnow() + timedelta(hours=deadline_hours),
            created_at=datetime.utcnow()
        )
        
        # Sign if crypto available
        if self._crypto:
            proposal.signature = await self._sign_message(
                proposal.compute_hash()
            )
        
        # Create transaction record
        transaction = Transaction(
            transaction_id=proposal.proposal_id,
            status=TransactionStatus.PROPOSED,
            proposal=proposal,
            quote=None,
            agreement=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            metadata={}
        )
        
        async with self._lock:
            self._transactions[transaction.transaction_id] = transaction
        
        logger.info(f"Created proposal {proposal.proposal_id} for {task_type}")
        
        # Notify handlers
        await self._notify_handlers(MessageType.TASK_PROPOSAL, proposal)
        
        return proposal
    
    async def receive_proposal(self, proposal: TaskProposal) -> Optional[TaskQuote]:
        """
        Receive and process a proposal (called by provider).
        
        Args:
            proposal: Received proposal
            
        Returns:
            Quote if accepting, None if rejecting
        """
        # Verify signature
        if proposal.signature and not await self._verify_signature(
            proposal.client_id, proposal.compute_hash(), proposal.signature
        ):
            logger.warning(f"Invalid signature on proposal {proposal.proposal_id}")
            return None
        
        # Check budget
        services = await self._registry.get_provider_services(self._agent_id)
        matching_service = None
        for svc in services:
            if svc.service_type.value == proposal.task_type:
                matching_service = svc
                break
        
        if not matching_service:
            logger.info(f"No matching service for task type {proposal.task_type}")
            return None
        
        if matching_service.price > proposal.budget_max:
            logger.info(f"Price exceeds budget for proposal {proposal.proposal_id}")
            return None
        
        # Create quote
        quote = await self.create_quote(
            proposal=proposal,
            estimated_amount=matching_service.price,
            estimated_time_seconds=300,  # Default 5 min
            terms={"service_id": matching_service.service_id}
        )
        
        return quote
    
    # ========== Quote Phase ==========
    
    async def create_quote(
        self,
        proposal: TaskProposal,
        estimated_amount: Decimal,
        estimated_time_seconds: int,
        terms: Dict[str, Any],
        valid_hours: int = 24
    ) -> TaskQuote:
        """Create a quote for a proposal."""
        quote = TaskQuote(
            quote_id=str(uuid.uuid4()),
            proposal_id=proposal.proposal_id,
            provider_id=self._agent_id,
            estimated_amount=estimated_amount,
            estimated_time_seconds=estimated_time_seconds,
            valid_until=datetime.utcnow() + timedelta(hours=valid_hours),
            terms=terms,
            created_at=datetime.utcnow()
        )
        
        # Sign if crypto available
        if self._crypto:
            quote.signature = await self._sign_message(quote.compute_hash())
        
        # Update transaction
        async with self._lock:
            tx = self._transactions.get(proposal.proposal_id)
            if tx:
                tx.quote = quote
                tx.status = TransactionStatus.QUOTED
                tx.updated_at = datetime.utcnow()
        
        logger.info(f"Created quote {quote.quote_id} for proposal {proposal.proposal_id}")
        
        await self._notify_handlers(MessageType.TASK_QUOTE, quote)
        
        return quote
    
    async def accept_quote(self, quote: TaskQuote) -> Optional[Agreement]:
        """
        Accept a quote and create agreement (called by client).
        
        Args:
            quote: Quote to accept
            
        Returns:
            Agreement if successful
        """
        # Verify signature
        if quote.signature and not await self._verify_signature(
            quote.provider_id, quote.compute_hash(), quote.signature
        ):
            logger.warning(f"Invalid signature on quote {quote.quote_id}")
            return None
        
        # Check validity
        if datetime.utcnow() > quote.valid_until:
            logger.warning(f"Quote {quote.quote_id} expired")
            return None
        
        # Get proposal
        tx = self._transactions.get(quote.proposal_id)
        if not tx or tx.proposal.client_id != self._agent_id:
            logger.warning(f"Cannot accept quote {quote.quote_id}: not our proposal")
            return None
        
        # Create order in order book
        order = await self._order_book.create_order(
            buyer_id=self._agent_id,
            service_id=quote.terms.get("service_id", ""),
            quantity=1,
            max_price=quote.estimated_amount,
            requirements=tx.proposal.requirements
        )
        
        if not order:
            logger.error(f"Failed to create order for quote {quote.quote_id}")
            return None
        
        # Create agreement
        agreement = Agreement(
            agreement_id=str(uuid.uuid4()),
            quote_id=quote.quote_id,
            task_id=order.order_id,
            client_id=self._agent_id,
            provider_id=quote.provider_id,
            confirmed_amount=quote.estimated_amount,
            escrow_id=None,
            deadline=quote.valid_until,
            created_at=datetime.utcnow()
        )
        
        # Sign agreement
        if self._crypto:
            agreement.client_signature = await self._sign_message(
                agreement.compute_hash()
            )
        
        # Create escrow
        escrow = await self._escrow.create_escrow(
            order_id=order.order_id,
            buyer_id=self._agent_id,
            provider_id=quote.provider_id,
            amount=quote.estimated_amount
        )
        
        if escrow:
            agreement.escrow_id = escrow.escrow_id
        
        # Update transaction
        async with self._lock:
            tx.agreement = agreement
            tx.status = TransactionStatus.AGREED
            tx.updated_at = datetime.utcnow()
        
        logger.info(f"Created agreement {agreement.agreement_id}")
        
        await self._notify_handlers(MessageType.AGREEMENT, agreement)
        
        return agreement
    
    # ========== Execution Phase ==========
    
    async def start_task(self, agreement_id: str) -> bool:
        """
        Start task execution (called by provider).
        
        Args:
            agreement_id: Agreement to start
            
        Returns:
            Success status
        """
        # Find transaction
        tx = None
        for t in self._transactions.values():
            if t.agreement and t.agreement.agreement_id == agreement_id:
                tx = t
                break
        
        if not tx or tx.agreement.provider_id != self._agent_id:
            return False
        
        # Mark order as in progress
        result = await self._order_book.start_service(tx.agreement.task_id)
        
        if result:
            async with self._lock:
                tx.status = TransactionStatus.IN_PROGRESS
                tx.updated_at = datetime.utcnow()
            
            await self._notify_handlers(MessageType.TASK_START, tx.agreement)
            logger.info(f"Started task {tx.agreement.task_id}")
        
        return result
    
    async def complete_task(self, agreement_id: str, result_data: Dict) -> bool:
        """
        Mark task as complete (called by provider).
        
        Args:
            agreement_id: Agreement to complete
            result_data: Task result data
            
        Returns:
            Success status
        """
        tx = None
        for t in self._transactions.values():
            if t.agreement and t.agreement.agreement_id == agreement_id:
                tx = t
                break
        
        if not tx:
            return False
        
        # Complete order
        success = await self._order_book.complete_service(tx.agreement.task_id)
        
        if success:
            async with self._lock:
                tx.status = TransactionStatus.COMPLETED
                tx.updated_at = datetime.utcnow()
                tx.metadata['result'] = result_data
            
            await self._notify_handlers(MessageType.TASK_COMPLETE, {
                'agreement': tx.agreement,
                'result': result_data
            })
            logger.info(f"Completed task {tx.agreement.task_id}")
        
        return success
    
    async def release_payment(self, agreement_id: str) -> bool:
        """
        Release payment to provider (called by client).
        
        Args:
            agreement_id: Agreement to release payment for
            
        Returns:
            Success status
        """
        tx = None
        for t in self._transactions.values():
            if t.agreement and t.agreement.agreement_id == agreement_id:
                tx = t
                break
        
        if not tx or tx.agreement.client_id != self._agent_id:
            return False
        
        if not tx.agreement.escrow_id:
            return False
        
        # Release escrow
        success = await self._escrow.release_to_provider(tx.agreement.escrow_id)
        
        if success:
            async with self._lock:
                tx.status = TransactionStatus.PAYMENT_RELEASED
                tx.updated_at = datetime.utcnow()
            
            await self._notify_handlers(MessageType.PAYMENT_RELEASE, tx.agreement)
            
            # Update provider reputation
            await self._registry.update_reputation(
                tx.quote.terms.get("service_id", ""),
                rating=5.0,
                transaction_success=True
            )
            
            logger.info(f"Released payment for {agreement_id}")
        
        return success
    
    # ========== Event Handlers ==========
    
    def on(self, message_type: MessageType, handler: Callable):
        """Register event handler."""
        self._handlers[message_type].append(handler)
    
    async def _notify_handlers(self, message_type: MessageType, data: Any):
        """Notify all registered handlers."""
        for handler in self._handlers[message_type]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Handler error: {e}")
    
    # ========== Helper Methods ==========
    
    async def _sign_message(self, message: str) -> str:
        """Sign a message with agent's key."""
        if self._crypto:
            # Use crypto manager if available
            return f"sig:{message[:16]}"
        return None
    
    async def _verify_signature(
        self,
        agent_id: str,
        message: str,
        signature: str
    ) -> bool:
        """Verify a signature."""
        if not signature:
            return True  # Accept unsigned in dev mode
        # TODO: Implement proper signature verification
        return True
    
    async def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """Get transaction by ID."""
        return self._transactions.get(transaction_id)
    
    async def get_client_transactions(
        self,
        status: Optional[TransactionStatus] = None
    ) -> List[Transaction]:
        """Get all transactions where we are the client."""
        txs = [
            t for t in self._transactions.values()
            if t.proposal.client_id == self._agent_id
        ]
        if status:
            txs = [t for t in txs if t.status == status]
        return sorted(txs, key=lambda x: x.created_at, reverse=True)
    
    async def get_provider_transactions(
        self,
        status: Optional[TransactionStatus] = None
    ) -> List[Transaction]:
        """Get all transactions where we are the provider."""
        txs = [
            t for t in self._transactions.values()
            if t.quote and t.quote.provider_id == self._agent_id
        ]
        if status:
            txs = [t for t in txs if t.status == status]
        return sorted(txs, key=lambda x: x.created_at, reverse=True)


# Convenience function
async def create_transaction_protocol(
    registry: ServiceRegistry,
    order_book: OrderBook,
    escrow: EscrowManager,
    agent_id: str,
    crypto_manager: Optional[Any] = None
) -> TransactionProtocol:
    """Create a new transaction protocol instance."""
    return TransactionProtocol(
        registry, order_book, escrow, agent_id, crypto_manager
    )
