"""
Data models for Governance System
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4


class ProposalStatus(Enum):
    """Proposal lifecycle statuses"""
    PENDING = "pending"
    ACTIVE = "active"
    CANCELED = "canceled"
    DEFEATED = "defeated"
    SUCCEEDED = "succeeded"
    QUEUED = "queued"
    EXPIRED = "expired"
    EXECUTED = "executed"


class ProposalType(Enum):
    """Types of proposals"""
    PARAMETER_CHANGE = "parameter_change"
    UPGRADE = "upgrade"
    TOKEN_ALLOCATION = "token_allocation"
    EMERGENCY = "emergency"


class VoteType(Enum):
    """Vote options"""
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"


@dataclass
class Action:
    """Executable action for a proposal"""
    target: str
    function: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    value: Decimal = Decimal("0")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "function": self.function,
            "parameters": self.parameters,
            "value": str(self.value)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Action':
        return cls(
            target=data["target"],
            function=data["function"],
            parameters=data.get("parameters", {}),
            value=Decimal(data.get("value", "0"))
        )


@dataclass
class Vote:
    """Individual vote record"""
    voter: str
    proposal_id: UUID
    vote_type: VoteType
    voting_power: Decimal
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "voter": self.voter,
            "proposal_id": str(self.proposal_id),
            "vote_type": self.vote_type.value,
            "voting_power": str(self.voting_power),
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class Proposal:
    """Governance proposal"""
    # Basic info
    id: UUID = field(default_factory=uuid4)
    proposer: str = ""
    title: str = ""
    description: str = ""
    proposal_type: ProposalType = ProposalType.PARAMETER_CHANGE
    actions: List[Action] = field(default_factory=list)
    
    # Status
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    discussion_end: Optional[datetime] = None
    voting_start: Optional[datetime] = None
    voting_end: Optional[datetime] = None
    queued_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    
    # Vote tallies
    votes_for: Decimal = Decimal("0")
    votes_against: Decimal = Decimal("0")
    votes_abstain: Decimal = Decimal("0")
    
    # Tracking
    voters: List[str] = field(default_factory=list)
    cancel_reason: Optional[str] = None
    execution_tx_hash: Optional[str] = None
    
    @property
    def total_votes(self) -> Decimal:
        """Total votes cast"""
        return self.votes_for + self.votes_against + self.votes_abstain
    
    @property
    def quorum_votes(self) -> Decimal:
        """Votes counting toward quorum (includes abstain)"""
        return self.total_votes
    
    @property
    def for_percentage(self) -> float:
        """Percentage of votes in favor"""
        if self.total_votes == 0:
            return 0.0
        return float(self.votes_for / self.total_votes * 100)
    
    @property
    def is_passed(self) -> bool:
        """Check if proposal has passed"""
        return self.votes_for > self.votes_against
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "proposer": self.proposer,
            "title": self.title,
            "description": self.description,
            "proposal_type": self.proposal_type.value,
            "actions": [a.to_dict() for a in self.actions],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "discussion_end": self.discussion_end.isoformat() if self.discussion_end else None,
            "voting_start": self.voting_start.isoformat() if self.voting_start else None,
            "voting_end": self.voting_end.isoformat() if self.voting_end else None,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "votes_for": str(self.votes_for),
            "votes_against": str(self.votes_against),
            "votes_abstain": str(self.votes_abstain),
            "total_votes": str(self.total_votes),
            "for_percentage": self.for_percentage,
            "voters": self.voters,
            "cancel_reason": self.cancel_reason,
            "execution_tx_hash": self.execution_tx_hash
        }
