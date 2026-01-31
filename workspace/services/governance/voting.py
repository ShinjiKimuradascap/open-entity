"""
Voting Management Module for Governance System

投票管理モジュール - AI間の分散合意形成を実現
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from .models import Proposal, ProposalStatus, Vote, VoteType
from .config import GovernanceConfig

logger = logging.getLogger(__name__)


class VotingManager:
    """
    Manages voting lifecycle for governance proposals
    
    Features:
    - Secure vote casting with signature verification
    - Voting power calculation (token-based)
    - Quorum tracking
    - Vote delegation support
    """
    
    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig.default()
        self.votes: Dict[UUID, List[Vote]] = {}  # proposal_id -> votes
        self.voter_registry: Dict[str, Decimal] = {}  # voter -> voting power
        logger.info("VotingManager initialized")
    
    def cast_vote(
        self,
        proposal: Proposal,
        voter: str,
        vote_type: VoteType,
        voting_power: Decimal,
        signature: Optional[str] = None
    ) -> Vote:
        """
        Cast a vote on a proposal
        
        Args:
            proposal: Target proposal
            voter: Voter address/ID
            vote_type: FOR, AGAINST, or ABSTAIN
            voting_power: Token-based voting power
            signature: Cryptographic signature (optional)
            
        Returns:
            Vote record
            
        Raises:
            ValueError: If voting is not allowed
        """
        # Validate voting period
        if proposal.status != ProposalStatus.ACTIVE:
            raise ValueError(f"Proposal is not active (status: {proposal.status})")
        
        now = datetime.utcnow()
        if proposal.voting_start and now < proposal.voting_start:
            raise ValueError("Voting has not started yet")
        if proposal.voting_end and now > proposal.voting_end:
            raise ValueError("Voting period has ended")
        
        # Check if already voted
        existing_votes = self.votes.get(proposal.id, [])
        if any(v.voter == voter for v in existing_votes):
            raise ValueError(f"Voter {voter} has already voted")
        
        # Check minimum voting power
        if voting_power < self.config.MIN_TOKENS_TO_VOTE:
            raise ValueError(
                f"Voting power {voting_power} below minimum {self.config.MIN_TOKENS_TO_VOTE}"
            )
        
        # Create vote
        vote = Vote(
            voter=voter,
            proposal_id=proposal.id,
            vote_type=vote_type,
            voting_power=voting_power
        )
        
        # Store vote
        if proposal.id not in self.votes:
            self.votes[proposal.id] = []
        self.votes[proposal.id].append(vote)
        
        # Update proposal tallies
        self._update_tally(proposal)
        
        logger.info(f"Vote cast: {voter} voted {vote_type.value} on {proposal.id}")
        return vote
    
    def _update_tally(self, proposal: Proposal) -> None:
        """Update vote tallies on proposal"""
        votes = self.votes.get(proposal.id, [])
        
        proposal.votes_for = sum(
            v.voting_power for v in votes if v.vote_type == VoteType.FOR
        )
        proposal.votes_against = sum(
            v.voting_power for v in votes if v.vote_type == VoteType.AGAINST
        )
        proposal.votes_abstain = sum(
            v.voting_power for v in votes if v.vote_type == VoteType.ABSTAIN
        )
        proposal.voters = [v.voter for v in votes]
    
    def check_quorum(self, proposal: Proposal) -> bool:
        """
        Check if quorum has been reached
        
        Returns:
            True if quorum met
        """
        total_voting_power = sum(self.voter_registry.values())
        if total_voting_power == 0:
            return False
        
        quorum_threshold = total_voting_power * (self.config.QUORUM_PERCENTAGE / 100)
        return proposal.quorum_votes >= quorum_threshold
    
    def check_passed(self, proposal: Proposal) -> bool:
        """
        Check if proposal has passed voting
        
        Requirements:
        1. Quorum reached
        2. For votes > Against votes
        3. For percentage >= threshold
        """
        if not self.check_quorum(proposal):
            return False
        
        if proposal.votes_for <= proposal.votes_against:
            return False
        
        if proposal.for_percentage < self.config.PASS_THRESHOLD_PERCENTAGE:
            return False
        
        return True
    
    def get_voter_history(self, voter: str) -> List[Vote]:
        """Get all votes cast by a voter"""
        all_votes = []
        for votes in self.votes.values():
            all_votes.extend([v for v in votes if v.voter == voter])
        return sorted(all_votes, key=lambda v: v.timestamp)
    
    def get_proposal_votes(self, proposal_id: UUID) -> List[Vote]:
        """Get all votes for a specific proposal"""
        return self.votes.get(proposal_id, [])
