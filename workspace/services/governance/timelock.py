"""
Timelock Module for Governance System

Provides security delay before proposal execution with guardian pause capability.
Standard delay: 2 days, Emergency delay: 4 hours, Grace period: 14 days.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Any

from .config import GovernanceConfig
from .models import Proposal


logger = logging.getLogger(__name__)


class TimelockStatus(Enum):
    """Status of a queued transaction in timelock"""
    PENDING = "pending"         # Queued, waiting for delay
    EXECUTABLE = "executable"   # Delay passed, ready to execute
    EXECUTED = "executed"       # Successfully executed
    EXPIRED = "expired"         # Grace period expired
    CANCELED = "canceled"       # Canceled before execution


@dataclass
class QueuedTransaction:
    """A transaction queued in the timelock"""
    id: str
    proposal_id: str
    tx_hash: str
    queued_at: datetime
    executable_at: datetime
    expires_at: datetime
    status: TimelockStatus
    is_emergency: bool
    executor: Optional[str] = None
    executed_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "proposal_id": self.proposal_id,
            "tx_hash": self.tx_hash,
            "queued_at": self.queued_at.isoformat(),
            "executable_at": self.executable_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "is_emergency": self.is_emergency,
            "executor": self.executor,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "cancel_reason": self.cancel_reason
        }


class Timelock:
    """
    Timelock controller for governance execution.
    
    Enforces a mandatory delay between proposal queuing and execution
to allow for security review and guardian intervention.
    """
    
    def __init__(self, config: GovernanceConfig):
        """
        Initialize timelock with configuration.
        
        Args:
config: Governance configuration with delay settings
        """
        self.config = config
        self._queued_transactions: Dict[str, QueuedTransaction] = {}
        self._paused: bool = False
        self._pause_initiator: Optional[str] = None
        self._paused_at: Optional[datetime] = None
        
        logger.info("Timelock initialized with delay=%ds, emergency=%ds, grace=%ds",
                    config.TIMELOCK_DELAY, config.EMERGENCY_DELAY, config.GRACE_PERIOD)
    
    def queue_transaction(
        self,
        proposal: Proposal,
        tx_hash: str,
        is_emergency: bool = False
    ) -> str:
        """
        Queue a transaction for delayed execution.
        
        Args:
proposal: The proposal to execute
            tx_hash: Transaction hash from the proposal actions
            is_emergency: Whether this is an emergency proposal (shorter delay)
            
        Returns:
            queued_tx_id: Unique identifier for the queued transaction
            
        Raises:
            ValueError: If proposal is invalid or tx_hash is empty
        """
        if not proposal:
            raise ValueError("Proposal cannot be None")
        if not tx_hash:
            raise ValueError("Transaction hash cannot be empty")
        
        queued_tx_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        # Determine delay based on emergency status
        delay = self.config.EMERGENCY_DELAY if is_emergency else self.config.TIMELOCK_DELAY
        
        queued_tx = QueuedTransaction(
            id=queued_tx_id,
            proposal_id=str(proposal.id),
            tx_hash=tx_hash,
            queued_at=now,
            executable_at=now + timedelta(seconds=delay),
            expires_at=now + timedelta(seconds=delay + self.config.GRACE_PERIOD),
            status=TimelockStatus.PENDING,
            is_emergency=is_emergency
        )
        
        self._queued_transactions[queued_tx_id] = queued_tx
        
        logger.info(
            "Transaction queued: id=%s, proposal=%s, emergency=%s, executable_at=%s",
            queued_tx_id, proposal.id, is_emergency, queued_tx.executable_at.isoformat()
        )
        
        return queued_tx_id
    
    def execute_transaction(
        self,
        queued_tx_id: str,
        executor: Optional[str] = None
    ) -> bool:
        """
        Execute a queued transaction if delay has passed and not paused.
        
        Args:
            queued_tx_id: ID of the queued transaction
            executor: Address of the entity executing the transaction
            
        Returns:
            bool: True if execution was successful, False otherwise
            
        Raises:
            ValueError: If transaction not found
            RuntimeError: If timelock is paused
        """
        if queued_tx_id not in self._queued_transactions:
            raise ValueError(f"Queued transaction not found: {queued_tx_id}")
        
        if self._paused:
            logger.warning("Execution blocked: Timelock is paused by %s", self._pause_initiator)
            raise RuntimeError("Timelock is paused - execution blocked")
        
        tx = self._queued_transactions[queued_tx_id]
        now = datetime.utcnow()
        
        # Check if already executed or canceled
        if tx.status == TimelockStatus.EXECUTED:
            logger.warning("Transaction already executed: %s", queued_tx_id)
            return False
        if tx.status == TimelockStatus.CANCELED:
            logger.warning("Transaction was canceled: %s", queued_tx_id)
            return False
        
        # Check grace period expiration
        if now > tx.expires_at:
            tx.status = TimelockStatus.EXPIRED
            logger.warning("Transaction expired: %s", queued_tx_id)
            return False
        
        # Check if delay has passed
        if now < tx.executable_at:
            remaining = (tx.executable_at - now).total_seconds()
            logger.warning("Delay not yet passed for %s, remaining=%ds", queued_tx_id, int(remaining))
            return False
        
        # Execute the transaction
        tx.status = TimelockStatus.EXECUTED
        tx.executed_at = now
        tx.executor = executor
        
        logger.info(
            "Transaction executed: id=%s, proposal=%s, executor=%s",
            queued_tx_id, tx.proposal_id, executor
        )
        
        return True
    
    def pause(self, guardian: str) -> bool:
        """
        Pause the timelock - guardian only.
        
        When paused, no transactions can be executed until unpaused.
        
        Args:
            guardian: Address of the guardian initiating pause
            
        Returns:
            bool: True if pause was successful
            
        Raises:
            PermissionError: If caller is not a guardian
        """
        if not self._is_guardian(guardian):
            logger.error("Pause rejected: %s is not a guardian", guardian)
            raise PermissionError(f"Address {guardian} is not a guardian")
        
        if self._paused:
            logger.warning("Timelock already paused by %s", self._pause_initiator)
            return False
        
        self._paused = True
        self._pause_initiator = guardian
        self._paused_at = datetime.utcnow()
        
        logger.warning("Timelock PAUSED by guardian %s at %s",
                      guardian, self._paused_at.isoformat())
        
        return True
    
    def unpause(self, guardian: str) -> bool:
        """
        Unpause the timelock - guardian only.
        
        Args:
            guardian: Address of the guardian initiating unpause
            
        Returns:
            bool: True if unpause was successful
            
        Raises:
            PermissionError: If caller is not a guardian
        """
        if not self._is_guardian(guardian):
            logger.error("Unpause rejected: %s is not a guardian", guardian)
            raise PermissionError(f"Address {guardian} is not a guardian")
        
        if not self._paused:
            logger.warning("Timelock is not paused")
            return False
        
        paused_duration = datetime.utcnow() - self._paused_at if self._paused_at else timedelta(0)
        
        self._paused = False
        self._pause_initiator = None
        self._paused_at = None
        
        logger.warning("Timelock UNPAUSED by guardian %s (was paused for %s)",
                      guardian, paused_duration)
        
        return True
    
    def is_paused(self) -> bool:
        """
        Check if timelock is currently paused.
        
        Returns:
            bool: True if paused, False otherwise
        """
        return self._paused
    
    def get_queued_transaction(self, queued_tx_id: str) -> Optional[QueuedTransaction]:
        """
        Get a queued transaction by ID.
        
        Args:
            queued_tx_id: ID of the queued transaction
            
        Returns:
            QueuedTransaction or None if not found
        """
        return self._queued_transactions.get(queued_tx_id)
    
    def get_all_queued(self) -> Dict[str, QueuedTransaction]:
        """
        Get all queued transactions.
        
        Returns:
            Dict mapping transaction IDs to QueuedTransaction objects
        """
        return self._queued_transactions.copy()
    
    def get_executable_transactions(self) -> Dict[str, QueuedTransaction]:
        """
        Get all transactions ready for execution (delay passed, not expired).
        
        Returns:
            Dict mapping transaction IDs to executable QueuedTransaction objects
        """
        now = datetime.utcnow()
        executable = {}
        
        for tx_id, tx in self._queued_transactions.items():
            if (tx.status == TimelockStatus.PENDING and
                now >= tx.executable_at and
                now <= tx.expires_at):
                executable[tx_id] = tx
        
        return executable
    
    def cancel_transaction(
        self,
        queued_tx_id: str,
        guardian: str,
        reason: str = ""
    ) -> bool:
        """
        Cancel a queued transaction - guardian only.
        
        Can only cancel transactions that haven't been executed yet.
        
        Args:
            queued_tx_id: ID of the queued transaction
            guardian: Address of the guardian canceling
            reason: Optional reason for cancellation
            
        Returns:
            bool: True if cancellation was successful
            
        Raises:
            PermissionError: If caller is not a guardian
            ValueError: If transaction not found or already executed
        """
        if not self._is_guardian(guardian):
            logger.error("Cancel rejected: %s is not a guardian", guardian)
            raise PermissionError(f"Address {guardian} is not a guardian")
        
        if queued_tx_id not in self._queued_transactions:
            raise ValueError(f"Queued transaction not found: {queued_tx_id}")
        
        tx = self._queued_transactions[queued_tx_id]
        
        if tx.status == TimelockStatus.EXECUTED:
            raise ValueError("Cannot cancel already executed transaction")
        if tx.status == TimelockStatus.CANCELED:
            return False
        
        tx.status = TimelockStatus.CANCELED
        tx.cancel_reason = reason
        
        logger.warning("Transaction CANCELED by guardian %s: id=%s, reason=%s",
                      guardian, queued_tx_id, reason)
        
        return True
    
    def _is_guardian(self, address: str) -> bool:
        """
        Check if an address is a guardian.
        
        Args:
            address: Address to check
            
        Returns:
            bool: True if address is in GUARDIAN_ADDRESSES
        """
        if not address:
            return False
        return address in self.config.GUARDIAN_ADDRESSES
    
    def get_pause_status(self) -> Dict[str, Any]:
        """
        Get current pause status information.
        
        Returns:
            Dict with paused status, initiator, and duration
        """
        if not self._paused:
            return {"paused": False}
        
        paused_duration = datetime.utcnow() - self._paused_at if self._paused_at else timedelta(0)
        
        return {
            "paused": True,
            "initiator": self._pause_initiator,
            "paused_at": self._paused_at.isoformat() if self._paused_at else None,
            "paused_duration_seconds": int(paused_duration.total_seconds())
        }
