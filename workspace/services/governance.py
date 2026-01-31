#!/usr/bin/env python3
"""
Governance System for AI Token Economy
分散型ガバナンスシステム実装

Features:
- Proposal creation and management
- Token-weighted voting
- Automatic execution with timelock
- Emergency pause functionality
"""

import asyncio
import json
import logging
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProposalStatus(Enum):
    """Proposal lifecycle states"""
    PENDING = "pending"           # Created, in discussion period
    ACTIVE = "active"             # Open for voting
    SUCCEEDED = "succeeded"       # Passed quorum and threshold
    FAILED = "failed"             # Did not pass
    EXECUTED = "executed"         # Successfully executed
    CANCELLED = "cancelled"       # Cancelled by proposer


class ProposalType(Enum):
    """Types of governance proposals"""
    PARAMETER_CHANGE = "parameter_change"
    PROTOCOL_UPGRADE = "protocol_upgrade"
    TOKEN_ALLOCATION = "token_allocation"
    EMERGENCY_ACTION = "emergency_action"


@dataclass
class Proposal:
    """Governance proposal"""
    id: str
    title: str
    description: str
    proposer: str                    # Entity ID
    proposal_type: ProposalType
    status: ProposalStatus
    
    # Timing
    created_at: datetime
    discussion_period_hours: int = 24
    voting_period_hours: int = 72
    voting_ends_at: Optional[datetime] = None
    timelock_hours: int = 48
    
    # Voting
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    voters: Dict[str, str] = field(default_factory=dict)  # voter_id -> vote
    
    # Execution
    execution_payload: Optional[Dict] = None
    executed_at: Optional[datetime] = None
    execution_tx_hash: Optional[str] = None
    
    # Configuration
    min_tokens_to_propose: int = 1000
    quorum_percentage: int = 10      # % of total supply
    approval_threshold: int = 51     # % of votes
    
    def calculate_total_votes(self) -> int:
        """Calculate total votes cast"""
        return self.votes_for + self.votes_against + self.votes_abstain
    
    def calculate_quorum(self, total_supply: int) -> bool:
        """Check if quorum is reached"""
        total_votes = self.calculate_total_votes()
        required = (total_supply * self.quorum_percentage) // 100
        return total_votes >= required
    
    def calculate_result(self, total_supply: int) -> Optional[bool]:
        """
        Calculate voting result.
        Returns: True if passed, False if rejected, None if still active
        """
        if self.status != ProposalStatus.ACTIVE:
            return None
        
        if datetime.now(timezone.utc) < self.voting_ends_at:
            return None  # Voting still active
        
        # Check quorum
        if not self.calculate_quorum(total_supply):
            return False
        
        # Check approval threshold
        total_votes = self.votes_for + self.votes_against
        if total_votes == 0:
            return False
        
        approval_rate = (self.votes_for * 100) // total_votes
        return approval_rate >= self.approval_threshold
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "proposer": self.proposer,
            "proposal_type": self.proposal_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "discussion_period_hours": self.discussion_period_hours,
            "voting_period_hours": self.voting_period_hours,
            "voting_ends_at": self.voting_ends_at.isoformat() if self.voting_ends_at else None,
            "timelock_hours": self.timelock_hours,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "votes_abstain": self.votes_abstain,
            "voters": self.voters,
            "execution_payload": self.execution_payload,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "execution_tx_hash": self.execution_tx_hash,
            "min_tokens_to_propose": self.min_tokens_to_propose,
            "quorum_percentage": self.quorum_percentage,
            "approval_threshold": self.approval_threshold,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Proposal":
        """Deserialize from dictionary"""
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            proposer=data["proposer"],
            proposal_type=ProposalType(data["proposal_type"]),
            status=ProposalStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            discussion_period_hours=data.get("discussion_period_hours", 24),
            voting_period_hours=data.get("voting_period_hours", 72),
            voting_ends_at=datetime.fromisoformat(data["voting_ends_at"]) if data.get("voting_ends_at") else None,
            timelock_hours=data.get("timelock_hours", 48),
            votes_for=data.get("votes_for", 0),
            votes_against=data.get("votes_against", 0),
            votes_abstain=data.get("votes_abstain", 0),
            voters=data.get("voters", {}),
            execution_payload=data.get("execution_payload"),
            executed_at=datetime.fromisoformat(data["executed_at"]) if data.get("executed_at") else None,
            execution_tx_hash=data.get("execution_tx_hash"),
            min_tokens_to_propose=data.get("min_tokens_to_propose", 1000),
            quorum_percentage=data.get("quorum_percentage", 10),
            approval_threshold=data.get("approval_threshold", 51),
        )


class GovernanceSystem:
    """
    Decentralized governance system for AI token economy.
    """
    
    def __init__(
        self,
        token_system=None,  # TokenSystem instance for balance checks
        storage_path: Optional[str] = None
    ):
        self.token_system = token_system
        self.storage_path = Path(storage_path) if storage_path else None
        
        # Storage
        self._proposals: Dict[str, Proposal] = {}
        self._executed_proposals: List[str] = []
        
        # Configuration
        self._paused: bool = False
        self._emergency_admin: Optional[str] = None
        
        # Callbacks
        self._execution_callbacks: Dict[str, Callable] = {}
        
        # Load persisted data
        if self.storage_path:
            self._load_data()
        
        logger.info("GovernanceSystem initialized")
    
    def _load_data(self) -> None:
        """Load proposals from storage"""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            for prop_data in data.get("proposals", []):
                proposal = Proposal.from_dict(prop_data)
                self._proposals[proposal.id] = proposal
            
            self._executed_proposals = data.get("executed_proposals", [])
            self._paused = data.get("paused", False)
            
            logger.info(f"Loaded {len(self._proposals)} proposals")
        except Exception as e:
            logger.error(f"Failed to load governance data: {e}")
    
    def _save_data(self) -> None:
        """Persist proposals to storage"""
        if not self.storage_path:
            return
        
        try:
            data = {
                "proposals": [p.to_dict() for p in self._proposals.values()],
                "executed_proposals": self._executed_proposals,
                "paused": self._paused,
            }
            
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save governance data: {e}")
    
    async def create_proposal(
        self,
        proposer: str,
        title: str,
        description: str,
        proposal_type: ProposalType,
        execution_payload: Optional[Dict] = None,
        min_tokens: int = 1000
    ) -> Optional[Proposal]:
        """
        Create a new governance proposal.
        
        Args:
            proposer: Entity ID of the proposer
            title: Proposal title
            description: Proposal description
            proposal_type: Type of proposal
            execution_payload: Data for automatic execution
            min_tokens: Minimum tokens required to propose
        
        Returns:
            Created proposal or None if creation failed
        """
        # Check if system is paused
        if self._paused:
            logger.warning("Governance system is paused")
            return None
        
        # Verify proposer has enough tokens
        if self.token_system:
            balance = await self._get_token_balance(proposer)
            if balance < min_tokens:
                logger.warning(f"Proposer {proposer} has insufficient tokens: {balance} < {min_tokens}")
                return None
        
        # Generate proposal ID
        proposal_id = self._generate_proposal_id(proposer, title)
        
        # Create proposal
        now = datetime.now(timezone.utc)
        proposal = Proposal(
            id=proposal_id,
            title=title,
            description=description,
            proposer=proposer,
            proposal_type=proposal_type,
            status=ProposalStatus.PENDING,
            created_at=now,
            execution_payload=execution_payload,
            min_tokens_to_propose=min_tokens
        )
        
        self._proposals[proposal_id] = proposal
        self._save_data()
        
        logger.info(f"Created proposal {proposal_id} by {proposer}")
        return proposal
    
    async def cast_vote(
        self,
        voter: str,
        proposal_id: str,
        vote: str,  # "for", "against", "abstain"
    ) -> bool:
        """
        Cast a vote on a proposal.
        
        Args:
            voter: Entity ID of the voter
            proposal_id: Proposal ID
            vote: "for", "against", or "abstain"
        
        Returns:
            True if vote was recorded
        """
        if vote not in ["for", "against", "abstain"]:
            logger.error(f"Invalid vote: {vote}")
            return False
        
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            logger.error(f"Proposal not found: {proposal_id}")
            return False
        
        # Check if voting is active
        if proposal.status != ProposalStatus.ACTIVE:
            logger.warning(f"Voting not active for proposal {proposal_id}")
            return False
        
        # Check if already voted
        if voter in proposal.voters:
            logger.warning(f"Voter {voter} already voted on {proposal_id}")
            return False
        
        # Get voting power (token balance)
        voting_power = await self._get_token_balance(voter)
        if voting_power <= 0:
            logger.warning(f"Voter {voter} has no voting power")
            return False
        
        # Record vote
        proposal.voters[voter] = vote
        
        if vote == "for":
            proposal.votes_for += voting_power
        elif vote == "against":
            proposal.votes_against += voting_power
        else:
            proposal.votes_abstain += voting_power
        
        self._save_data()
        
        logger.info(f"Recorded {vote} vote from {voter} on {proposal_id}")
        return True
    
    async def process_proposals(self, total_supply: int) -> List[Proposal]:
        """
        Process all active proposals and update their status.
        
        Args:
            total_supply: Total token supply for quorum calculation
        
        Returns:
            List of proposals with status changes
        """
        updated = []
        now = datetime.now(timezone.utc)
        
        for proposal in self._proposals.values():
            # Transition from PENDING to ACTIVE after discussion period
            if proposal.status == ProposalStatus.PENDING:
                discussion_end = proposal.created_at + timedelta(hours=proposal.discussion_period_hours)
                if now >= discussion_end:
                    proposal.status = ProposalStatus.ACTIVE
                    proposal.voting_ends_at = now + timedelta(hours=proposal.voting_period_hours)
                    updated.append(proposal)
                    logger.info(f"Proposal {proposal.id} is now ACTIVE")
            
            # Check if voting period ended
            elif proposal.status == ProposalStatus.ACTIVE:
                if proposal.voting_ends_at and now >= proposal.voting_ends_at:
                    result = proposal.calculate_result(total_supply)
                    
                    if result is True:
                        proposal.status = ProposalStatus.SUCCEEDED
                        logger.info(f"Proposal {proposal.id} SUCCEEDED")
                    else:
                        proposal.status = ProposalStatus.FAILED
                        logger.info(f"Proposal {proposal.id} FAILED")
                    
                    updated.append(proposal)
        
        if updated:
            self._save_data()
        
        return updated
    
    async def execute_proposal(self, proposal_id: str) -> bool:
        """
        Execute a successful proposal after timelock.
        
        Args:
            proposal_id: Proposal ID to execute
        
        Returns:
            True if execution succeeded
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return False
        
        if proposal.status != ProposalStatus.SUCCEEDED:
            logger.warning(f"Cannot execute proposal {proposal_id}: status is {proposal.status}")
            return False
        
        # Check timelock
        if proposal.voting_ends_at:
            timelock_end = proposal.voting_ends_at + timedelta(hours=proposal.timelock_hours)
            if datetime.now(timezone.utc) < timelock_end:
                logger.warning(f"Timelock not expired for {proposal_id}")
                return False
        
        # Execute
        success = await self._execute_payload(proposal)
        
        if success:
            proposal.status = ProposalStatus.EXECUTED
            proposal.executed_at = datetime.now(timezone.utc)
            self._executed_proposals.append(proposal_id)
            self._save_data()
            logger.info(f"Executed proposal {proposal_id}")
        
        return success
    
    async def _execute_payload(self, proposal: Proposal) -> bool:
        """Execute proposal payload"""
        if not proposal.execution_payload:
            return True  # No payload to execute
        
        payload_type = proposal.execution_payload.get("type")
        
        # Find callback for this payload type
        callback = self._execution_callbacks.get(payload_type)
        if callback:
            try:
                return await callback(proposal.execution_payload)
            except Exception as e:
                logger.error(f"Execution failed for {proposal.id}: {e}")
                return False
        
        logger.warning(f"No execution handler for payload type: {payload_type}")
        return False
    
    async def _get_token_balance(self, entity_id: str) -> int:
        """Get token balance for an entity"""
        if self.token_system and hasattr(self.token_system, 'get_balance'):
            return await self.token_system.get_balance(entity_id)
        return 0
    
    def _generate_proposal_id(self, proposer: str, title: str) -> str:
        """Generate unique proposal ID"""
        data = f"{proposer}:{title}:{datetime.now(timezone.utc).timestamp()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def register_execution_callback(self, payload_type: str, callback: Callable) -> None:
        """Register callback for proposal execution"""
        self._execution_callbacks[payload_type] = callback
    
    def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        """Get proposal by ID"""
        return self._proposals.get(proposal_id)
    
    def list_proposals(
        self,
        status: Optional[ProposalStatus] = None,
        proposer: Optional[str] = None
    ) -> List[Proposal]:
        """List proposals with optional filtering"""
        proposals = list(self._proposals.values())
        
        if status:
            proposals = [p for p in proposals if p.status == status]
        
        if proposer:
            proposals = [p for p in proposals if p.proposer == proposer]
        
        return sorted(proposals, key=lambda p: p.created_at, reverse=True)
    
    def emergency_pause(self, admin: str) -> bool:
        """Emergency pause the governance system"""
        if self._emergency_admin and admin != self._emergency_admin:
            return False
        
        self._paused = True
        self._save_data()
        logger.warning(f"Governance system PAUSED by {admin}")
        return True
    
    def emergency_unpause(self, admin: str) -> bool:
        """Unpause the governance system"""
        if self._emergency_admin and admin != self._emergency_admin:
            return False
        
        self._paused = False
        self._save_data()
        logger.info(f"Governance system UNPAUSED by {admin}")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get governance system statistics"""
        return {
            "total_proposals": len(self._proposals),
            "active_proposals": len([p for p in self._proposals.values() if p.status == ProposalStatus.ACTIVE]),
            "executed_proposals": len(self._executed_proposals),
            "paused": self._paused,
        }


# Global instance
_governance_system: Optional[GovernanceSystem] = None


def get_governance_system() -> Optional[GovernanceSystem]:
    """Get global governance system instance"""
    return _governance_system


def init_governance_system(
    token_system=None,
    storage_path: Optional[str] = None
) -> GovernanceSystem:
    """Initialize global governance system"""
    global _governance_system
    _governance_system = GovernanceSystem(token_system, storage_path)
    return _governance_system


if __name__ == "__main__":
    # Test
    async def test():
        gov = init_governance_system(storage_path="./test_governance.json")
        
        # Create proposal
        proposal = await gov.create_proposal(
            proposer="test-entity",
            title="Test Proposal",
            description="This is a test",
            proposal_type=ProposalType.PARAMETER_CHANGE,
            execution_payload={"type": "test", "data": {}},
            min_tokens=0  # No minimum for testing
        )
        
        print(f"Created: {proposal.id}")
        print(f"Stats: {gov.get_stats()}")
    
    asyncio.run(test())
