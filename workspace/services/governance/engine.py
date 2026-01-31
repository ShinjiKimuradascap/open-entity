"""
Governance Engine - Main Integration Module

Governanceエンジン - AI間の分散ガバナンスを統合管理
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any
from uuid import UUID
import asyncio

from .models import Proposal, ProposalStatus, ProposalType, Action, Vote, VoteType
from .config import GovernanceConfig
from .proposal import ProposalManager
from .voting import VotingManager
from .execution import ExecutionEngine

logger = logging.getLogger(__name__)


class GovernanceEngine:
    """
    Main governance system integrating proposals, voting, and execution
    
    Features:
    - End-to-end proposal lifecycle management
    - Token-weighted voting
    - Automatic execution of passed proposals
    - Integration with AI peer network
    """
    
    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig.default()
        
        # Sub-components
        self.proposal_manager = ProposalManager(config)
        self.voting_manager = VotingManager(config)
        self.execution_engine = ExecutionEngine(config)
        
        # Balance lookup callback (set by integrator)
        self._balance_lookup: Optional[Callable[[str], Decimal]] = None
        
        # Background task
        self._processing_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info("GovernanceEngine initialized")
    
    def set_balance_lookup(self, lookup: Callable[[str], Decimal]) -> None:
        """
        Set callback for retrieving token balances
        
        Args:
            lookup: Function(address) -> balance
        """
        self._balance_lookup = lookup
    
    def _get_balance(self, address: str) -> Decimal:
        """Get token balance for an address"""
        if self._balance_lookup:
            return self._balance_lookup(address)
        return Decimal("0")
    
    # ===== Proposal Lifecycle =====
    
    def create_proposal(
        self,
        proposer: str,
        title: str,
        description: str,
        proposal_type: ProposalType,
        actions: List[Action]
    ) -> Proposal:
        """
        Create a new governance proposal
        
        Args:
            proposer: Address of proposer
            title: Proposal title
            description: Detailed description
            proposal_type: Type of proposal
            actions: List of executable actions
            
        Returns:
            Created proposal
        """
        balance = self._get_balance(proposer)
        
        proposal = self.proposal_manager.create_proposal(
            proposer=proposer,
            title=title,
            description=description,
            proposal_type=proposal_type,
            actions=actions,
            proposer_balance=balance
        )
        
        logger.info(f"Governance proposal created: {proposal.id}")
        return proposal
    
    def activate_proposal(self, proposal_id: UUID) -> bool:
        """
        Activate a proposal for voting (after discussion period)
        
        Args:
            proposal_id: Proposal to activate
            
        Returns:
            True if activated
        """
        proposal = self.proposal_manager.get_proposal(proposal_id)
        if not proposal:
            return False
        
        # Check discussion period
        if proposal.discussion_end and datetime.utcnow() < proposal.discussion_end:
            logger.warning(f"Discussion period not over for {proposal_id}")
            return False
        
        proposal.status = ProposalStatus.ACTIVE
        proposal.voting_start = datetime.utcnow()
        proposal.voting_end = datetime.utcnow() + self.config.VOTING_PERIOD
        
        logger.info(f"Proposal {proposal_id} activated for voting")
        return True
    
    def cast_vote(
        self,
        proposal_id: UUID,
        voter: str,
        vote_type: VoteType
    ) -> Vote:
        """
        Cast a vote on an active proposal
        
        Args:
            proposal_id: Target proposal
            voter: Voter address
            vote_type: FOR, AGAINST, or ABSTAIN
            
        Returns:
            Vote record
        """
        proposal = self.proposal_manager.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        voting_power = self._get_balance(voter)
        
        vote = self.voting_manager.cast_vote(
            proposal=proposal,
            voter=voter,
            vote_type=vote_type,
            voting_power=voting_power
        )
        
        return vote
    
    def finalize_voting(self, proposal_id: UUID) -> bool:
        """
        Finalize voting and determine outcome
        
        Args:
            proposal_id: Proposal to finalize
            
        Returns:
            True if proposal passed
        """
        proposal = self.proposal_manager.get_proposal(proposal_id)
        if not proposal:
            return False
        
        if proposal.status != ProposalStatus.ACTIVE:
            logger.warning(f"Cannot finalize proposal with status {proposal.status}")
            return False
        
        # Check if voting period ended
        if proposal.voting_end and datetime.utcnow() < proposal.voting_end:
            logger.warning(f"Voting period not over for {proposal_id}")
            return False
        
        # Determine outcome
        passed = self.voting_manager.check_passed(proposal)
        
        if passed:
            proposal.status = ProposalStatus.SUCCEEDED
            logger.info(f"Proposal {proposal_id} passed")
        else:
            proposal.status = ProposalStatus.DEFEATED
            logger.info(f"Proposal {proposal_id} defeated")
        
        return passed
    
    async def queue_execution(self, proposal_id: UUID) -> None:
        """Queue a passed proposal for execution"""
        proposal = self.proposal_manager.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        await self.execution_engine.queue_proposal(proposal)
    
    # ===== Background Processing =====
    
    async def start(self) -> None:
        """Start background governance processing"""
        if self._running:
            return
        
        self._running = True
        self._processing_task = asyncio.create_task(self._processing_loop())
        logger.info("GovernanceEngine started")
    
    async def stop(self) -> None:
        """Stop background processing"""
        self._running = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        logger.info("GovernanceEngine stopped")
    
    async def _processing_loop(self) -> None:
        """Background loop for processing proposals"""
        while self._running:
            try:
                # Process execution queue
                await self.execution_engine.process_queue(
                    self.proposal_manager.get_proposal
                )
                
                # Auto-activate proposals after discussion period
                for proposal in self.proposal_manager.list_proposals():
                    if (proposal.status == ProposalStatus.PENDING and 
                        proposal.discussion_end and 
                        datetime.utcnow() >= proposal.discussion_end):
                        self.activate_proposal(proposal.id)
                
                # Auto-finalize proposals after voting period
                for proposal in self.proposal_manager.list_proposals():
                    if (proposal.status == ProposalStatus.ACTIVE and 
                        proposal.voting_end and 
                        datetime.utcnow() >= proposal.voting_end):
                        passed = self.finalize_voting(proposal.id)
                        if passed:
                            await self.queue_execution(proposal.id)
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.exception("Error in governance processing loop")
                await asyncio.sleep(60)
    
    # ===== Statistics =====
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get governance system statistics"""
        proposals = self.proposal_manager.list_proposals()
        
        return {
            "total_proposals": len(proposals),
            "by_status": {
                status.value: len([p for p in proposals if p.status == status])
                for status in ProposalStatus
            },
            "pending_execution": len(self.execution_engine.execution_queue),
            "total_executed": len([
                p for p in proposals if p.status == ProposalStatus.EXECUTED
            ])
        }
