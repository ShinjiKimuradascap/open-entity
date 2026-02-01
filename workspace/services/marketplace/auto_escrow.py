#!/usr/bin/env python3
"""
Autonomous Escrow Flow for AI Multi-Agent Marketplace

Automated escrow management for AI-to-AI transactions.
v1.3 Feature: End-to-end autonomous payment flow
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EscrowFlowStatus(Enum):
    """Autonomous escrow flow status"""
    PENDING = "pending"
    FUNDS_LOCKED = "funds_locked"
    IN_PROGRESS = "in_progress"
    AWAITING_VERIFICATION = "awaiting_verification"
    VERIFIED = "verified"
    PAYMENT_RELEASED = "payment_released"
    REFUNDED = "refunded"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


@dataclass
class VerificationCriteria:
    """Criteria for automatic task verification"""
    expected_outputs: List[str] = field(default_factory=list)
    quality_threshold: float = 0.8
    required_formats: List[str] = field(default_factory=list)
    max_size_mb: Optional[int] = None
    checksum_algorithm: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "expected_outputs": self.expected_outputs,
            "quality_threshold": self.quality_threshold,
            "required_formats": self.required_formats,
            "max_size_mb": self.max_size_mb,
            "checksum_algorithm": self.checksum_algorithm
        }


@dataclass
class VerificationResult:
    """Result of automatic verification"""
    success: bool
    score: float
    checks_passed: int
    checks_failed: int
    details: Dict[str, Any]
    failure_reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "score": self.score,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "details": self.details,
            "failure_reason": self.failure_reason
        }


@dataclass
class EscrowFlowRecord:
    """Record of autonomous escrow flow"""
    flow_id: str
    agreement_id: str
    client_id: str
    provider_id: str
    amount: Decimal
    status: EscrowFlowStatus
    escrow_id: Optional[str] = None
    verification_criteria: Optional[VerificationCriteria] = None
    verification_result: Optional[VerificationResult] = None
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            "flow_id": self.flow_id,
            "agreement_id": self.agreement_id,
            "client_id": self.client_id,
            "provider_id": self.provider_id,
            "amount": str(self.amount),
            "status": self.status.value,
            "escrow_id": self.escrow_id,
            "verification_criteria": self.verification_criteria.to_dict() if self.verification_criteria else None,
            "verification_result": self.verification_result.to_dict() if self.verification_result else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class AutonomousEscrowFlow:
    """
    Automated escrow flow for AI-to-AI transactions.
    
    Automates the entire escrow lifecycle:
    1. Lock escrow funds
    2. Monitor task progress via WebSocket
    3. Auto-verify completion criteria
    4. Release payment or initiate dispute
    
    Features:
    - Automatic verification based on criteria
    - WebSocket-based progress monitoring
    - Dispute auto-resolution
    - Reputation integration
    """
    
    def __init__(self, escrow_manager, websocket_client=None):
        self.escrow_manager = escrow_manager
        self.websocket_client = websocket_client
        self.active_flows: Dict[str, EscrowFlowRecord] = {}
        self.completed_flows: Dict[str, EscrowFlowRecord] = {}
        self._lock = asyncio.Lock()
        self._progress_callbacks: Dict[str, Callable] = {}
    
    async def create_flow(
        self,
        agreement_id: str,
        client_id: str,
        provider_id: str,
        amount: Decimal,
        verification_criteria: Optional[VerificationCriteria] = None,
        expiry_hours: int = 48
    ) -> EscrowFlowRecord:
        """
        Create new autonomous escrow flow.
        
        Args:
            agreement_id: Service agreement identifier
            client_id: Client agent ID
            provider_id: Provider agent ID
            amount: Payment amount
            verification_criteria: Auto-verification criteria
            expiry_hours: Escrow expiry time
        
        Returns:
            EscrowFlowRecord for tracking
        """
        flow_id = str(uuid.uuid4())
        
        flow = EscrowFlowRecord(
            flow_id=flow_id,
            agreement_id=agreement_id,
            client_id=client_id,
            provider_id=provider_id,
            amount=amount,
            status=EscrowFlowStatus.PENDING,
            verification_criteria=verification_criteria
        )
        
        async with self._lock:
            self.active_flows[flow_id] = flow
        
        logger.info(f"Escrow flow created: {flow_id} for agreement {agreement_id}")
        return flow
    
    async def start_flow(self, flow_id: str) -> bool:
        """
        Start the escrow flow by locking funds.
        
        Args:
            flow_id: Flow identifier
        
        Returns:
            True if successfully started
        """
        async with self._lock:
            if flow_id not in self.active_flows:
                logger.error(f"Flow {flow_id} not found")
                return False
            
            flow = self.active_flows[flow_id]
        
        # Create escrow
        escrow = await self.escrow_manager.create_escrow(
            order_id=flow.agreement_id,
            buyer_id=flow.client_id,
            provider_id=flow.provider_id,
            amount=flow.amount,
            expiry_hours=48
        )
        
        if not escrow:
            logger.error(f"Failed to create escrow for flow {flow_id}")
            return False
        
        # Update flow
        flow.escrow_id = escrow.escrow_id
        flow.status = EscrowFlowStatus.FUNDS_LOCKED
        flow.started_at = datetime.utcnow()
        
        logger.info(f"Escrow flow started: {flow_id}, escrow: {escrow.escrow_id}")
        return True
    
    async def report_progress(
        self,
        flow_id: str,
        progress_percent: float,
        message: str = ""
    ) -> bool:
        """
        Report task progress.
        
        Called by provider to update progress.
        
        Args:
            flow_id: Flow identifier
            progress_percent: Progress percentage (0-100)
            message: Optional progress message
        
        Returns:
            True if progress recorded
        """
        async with self._lock:
            if flow_id not in self.active_flows:
                return False
            
            flow = self.active_flows[flow_id]
        
        # Update status based on progress
        if progress_percent > 0 and flow.status == EscrowFlowStatus.FUNDS_LOCKED:
            flow.status = EscrowFlowStatus.IN_PROGRESS
        
        if progress_percent >= 100:
            flow.status = EscrowFlowStatus.AWAITING_VERIFICATION
        
        # Notify via callback if registered
        callback = self._progress_callbacks.get(flow_id)
        if callback:
            await callback(flow_id, progress_percent, message)
        
        logger.info(f"Progress reported for flow {flow_id}: {progress_percent}%")
        return True
    
    async def submit_deliverable(
        self,
        flow_id: str,
        deliverable: Dict[str, Any]
    ) -> VerificationResult:
        """
        Submit deliverable and trigger auto-verification.
        
        Args:
            flow_id: Flow identifier
            deliverable: Deliverable data
        
        Returns:
            VerificationResult
        """
        async with self._lock:
            if flow_id not in self.active_flows:
                return VerificationResult(
                    success=False,
                    score=0.0,
                    checks_passed=0,
                    checks_failed=1,
                    details={},
                    failure_reason="Flow not found"
                )
            
            flow = self.active_flows[flow_id]
        
        # Run verification
        verification = await self._verify_deliverable(flow, deliverable)
        flow.verification_result = verification
        
        if verification.success:
            flow.status = EscrowFlowStatus.VERIFIED
            # Auto-release payment
            await self._release_payment(flow_id)
        else:
            flow.status = EscrowFlowStatus.DISPUTED
            logger.warning(f"Verification failed for flow {flow_id}: {verification.failure_reason}")
        
        return verification
    
    async def _verify_deliverable(
        self,
        flow: EscrowFlowRecord,
        deliverable: Dict[str, Any]
    ) -> VerificationResult:
        """
        Automatically verify deliverable against criteria.
        
        Args:
            flow: Escrow flow record
            deliverable: Submitted deliverable
        
        Returns:
            VerificationResult
        """
        criteria = flow.verification_criteria
        
        if not criteria:
            # No criteria specified - auto-accept
            return VerificationResult(
                success=True,
                score=1.0,
                checks_passed=1,
                checks_failed=0,
                details={"message": "No verification criteria specified"}
            )
        
        checks_passed = 0
        checks_failed = 0
        details = {}
        
        # Check expected outputs
        if criteria.expected_outputs:
            for expected in criteria.expected_outputs:
                if expected in deliverable:
                    checks_passed += 1
                    details[f"has_{expected}"] = True
                else:
                    checks_failed += 1
                    details[f"has_{expected}"] = False
        
        # Check format
        if criteria.required_formats:
            deliverable_format = deliverable.get("format", "")
            if deliverable_format in criteria.required_formats:
                checks_passed += 1
                details["format_valid"] = True
            else:
                checks_failed += 1
                details["format_valid"] = False
        
        # Check size
        if criteria.max_size_mb:
            size_mb = deliverable.get("size_mb", 0)
            if size_mb <= criteria.max_size_mb:
                checks_passed += 1
                details["size_valid"] = True
            else:
                checks_failed += 1
                details["size_valid"] = False
        
        # Calculate score
        total_checks = checks_passed + checks_failed
        if total_checks == 0:
            score = 1.0
        else:
            score = checks_passed / total_checks
        
        success = score >= criteria.quality_threshold
        
        return VerificationResult(
            success=success,
            score=score,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            details=details,
            failure_reason=None if success else "Quality threshold not met"
        )
    
    async def _release_payment(self, flow_id: str) -> bool:
        """
        Release payment after successful verification.
        
        Args:
            flow_id: Flow identifier
        
        Returns:
            True if payment released
        """
        async with self._lock:
            if flow_id not in self.active_flows:
                return False
            
            flow = self.active_flows[flow_id]
        
        if not flow.escrow_id:
            logger.error(f"No escrow ID for flow {flow_id}")
            return False
        
        # Release escrow
        result = await self.escrow_manager.release_escrow(flow.escrow_id)
        
        if result:
            flow.status = EscrowFlowStatus.PAYMENT_RELEASED
            flow.completed_at = datetime.utcnow()
            
            # Move to completed
            async with self._lock:
                self.completed_flows[flow_id] = flow
                del self.active_flows[flow_id]
            
            logger.info(f"Payment released for flow {flow_id}")
            return True
        else:
            logger.error(f"Failed to release payment for flow {flow_id}")
            return False
    
    async def cancel_flow(self, flow_id: str, reason: str = "") -> bool:
        """
        Cancel escrow flow and refund payment.
        
        Args:
            flow_id: Flow identifier
            reason: Cancellation reason
        
        Returns:
            True if cancelled
        """
        async with self._lock:
            if flow_id not in self.active_flows:
                return False
            
            flow = self.active_flows[flow_id]
        
        # Refund escrow if exists
        if flow.escrow_id:
            await self.escrow_manager.refund_escrow(flow.escrow_id)
        
        flow.status = EscrowFlowStatus.CANCELLED
        flow.completed_at = datetime.utcnow()
        
        # Move to completed
        async with self._lock:
            self.completed_flows[flow_id] = flow
            del self.active_flows[flow_id]
        
        logger.info(f"Escrow flow cancelled: {flow_id}, reason: {reason}")
        return True
    
    def get_flow(self, flow_id: str) -> Optional[EscrowFlowRecord]:
        """Get flow by ID"""
        if flow_id in self.active_flows:
            return self.active_flows[flow_id]
        if flow_id in self.completed_flows:
            return self.completed_flows[flow_id]
        return None
    
    def list_active_flows(
        self,
        client_id: Optional[str] = None,
        provider_id: Optional[str] = None
    ) -> List[EscrowFlowRecord]:
        """List active flows with optional filtering"""
        flows = list(self.active_flows.values())
        
        if client_id:
            flows = [f for f in flows if f.client_id == client_id]
        
        if provider_id:
            flows = [f for f in flows if f.provider_id == provider_id]
        
        return flows


__all__ = [
    "AutonomousEscrowFlow",
    "EscrowFlowStatus",
    "VerificationCriteria",
    "VerificationResult",
    "EscrowFlowRecord"
]
