"""
Proposal Management Module
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from .models import Proposal, ProposalStatus, ProposalType, Action
from .config import GovernanceConfig

logger = logging.getLogger(__name__)


class ProposalManager:
    """Manages governance proposals lifecycle"""
    
    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig.default()
        self.proposals: Dict[UUID, Proposal] = {}
        logger.info("ProposalManager initialized")
    
    def create_proposal(
        self,
        proposer: str,
        title: str,
        description: str,
        proposal_type: ProposalType,
        actions: List[Action],
        proposer_balance: Decimal
    ) -> Proposal:
        """
        Create a new proposal
        
        Args:
            proposer: Address of proposer
            title: Proposal title
            description: Proposal description
            proposal_type: Type of proposal
            actions: List of executable actions
            proposer_balance: Token balance of proposer
            
        Returns:
            Created proposal
            
        Raises:
            ValueError: If proposer doesn't have enough tokens
        """
        # Check minimum balance
        if proposer_balance < self.config.MIN_TOKENS_TO_PROPOSE:
            raise ValueError(
                f"Proposer must hold at least {self.config.MIN_TOKENS_TO_PROPOSE} "
                f"tokens (has {proposer_balance})"
            )
        
        # Check minimum actions
        if not actions:
            raise ValueError("Proposal must have at least one action")
        
        # Calculate time periods
        now = datetime.utcnow()
        
        # Emergency proposals skip discussion period
        if proposal_type == ProposalType.EMERGENCY:
            discussion_end = now
            voting_start = now
            voting_end = now + timedelta(seconds=self.config.VOTING_PERIOD // 3)
        else:
            discussion_end = now + timedelta(seconds=self.config.DISCUSSION_PERIOD)
            voting_start = discussion_end
            voting_end = voting_start + timedelta(seconds=self.config.VOTING_PERIOD)
        
        proposal = Proposal(
            proposer=proposer,
            title=title,
            description=description,
            proposal_type=proposal_type,
            actions=actions,
            discussion_end=discussion_end,
            voting_start=voting_start,
            voting_end=voting_end
        )
        
        # Set initial status
        if proposal_type == ProposalType.EMERGENCY:
            proposal.status = ProposalStatus.ACTIVE
        else:
            proposal.status = ProposalStatus.PENDING
        
        self.proposals[proposal.id] = proposal
        
        logger.info(
            f"Created proposal {proposal.id} by {proposer} "
            f"(type: {proposal_type.value})"
        )
        
        return proposal
    
    def get_proposal(self, proposal_id: UUID) -> Optional[Proposal]:
        """Get proposal by ID"""
        return self.proposals.get(proposal_id)
    
    def get_all_proposals(
        self,
        status: Optional[ProposalStatus] = None
    ) -> List[Proposal]:
        """Get all proposals, optionally filtered by status"""
        proposals = list(self.proposals.values())
        if status:
            proposals = [p for p in proposals if p.status == status]
        return proposals
    
    def cancel_proposal(
        self,
        proposal_id: UUID,
        canceller: str,
        reason: str
    ) -> bool:
        """
        Cancel a proposal
        
        Only proposer can cancel before voting starts
        """
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            logger.warning(f"Cannot cancel: proposal {proposal_id} not found")
            return False
        
        # Check if already canceled or executed
        if proposal.status in [ProposalStatus.CANCELED, ProposalStatus.EXECUTED]:
            logger.warning(f"Cannot cancel: proposal {proposal_id} already {proposal.status.value}")
            return False
        
        # Check if voting already started
        if proposal.voting_start and datetime.utcnow() >= proposal.voting_start:
            logger.warning(f"Cannot cancel: voting already started for {proposal_id}")
            return False
        
        # Check authorization
        if canceller != proposal.proposer:
            logger.warning(
                f"Cannot cancel: {canceller} is not proposer ({proposal.proposer})"
            )
            return False
        
        proposal.status = ProposalStatus.CANCELED
        proposal.cancel_reason = reason
        
        logger.info(f"Canceled proposal {proposal_id}: {reason}")
        return True
    
    def update_status(self, proposal_id: UUID) -> bool:
        """
        Update proposal status based on current time and votes
        
        Returns True if status was changed
        """
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            return False
        
        now = datetime.utcnow()
        old_status = proposal.status
        
        # State machine transitions
        if proposal.status == ProposalStatus.PENDING:
            if now >= proposal.voting_start:
                proposal.status = ProposalStatus.ACTIVE
                logger.info(f"Proposal {proposal_id} is now ACTIVE")
        
        elif proposal.status == ProposalStatus.ACTIVE:
            if now >= proposal.voting_end:
                # Check if quorum reached
                # (actual quorum check needs total supply)
                if proposal.is_passed:
                    proposal.status = ProposalStatus.SUCCEEDED
                    logger.info(f"Proposal {proposal_id} SUCCEEDED")
                else:
                    proposal.status = ProposalStatus.DEFEATED
                    logger.info(f"Proposal {proposal_id} DEFEATED")
        
        elif proposal.status == ProposalStatus.QUEUED:
            if proposal.queued_at:
                grace_deadline = proposal.queued_at + timedelta(
                    seconds=self.config.GRACE_PERIOD
                )
                if now > grace_deadline:
                    proposal.status = ProposalStatus.EXPIRED
                    logger.info(f"Proposal {proposal_id} EXPIRED")
        
        return proposal.status != old_status
    
    def update_all_statuses(self) -> int:
        """Update all proposal statuses, return count of changes"""
        changed = 0
        for proposal_id in self.proposals:
            if self.update_status(proposal_id):
                changed += 1
        return changed
    
    def record_vote(
        self,
        proposal_id: UUID,
        voter: str,
        voting_power: Decimal
    ) -> bool:
        """Record that a voter has voted (called by VotingManager)"""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            return False
        
        if voter not in proposal.voters:
            proposal.voters.append(voter)
        
        return True
