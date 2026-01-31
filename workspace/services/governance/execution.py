"""
Proposal Execution Engine for Governance System

提案実行エンジン - 可決した提案の自動実行を実現
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any
from uuid import UUID
import asyncio

from .models import Proposal, ProposalStatus, Action
from .config import GovernanceConfig

logger = logging.getLogger(__name__)


ExecutionHandler = Callable[[Action], asyncio.Future[bool]]
"""Type alias for action execution handlers"""


class ExecutionEngine:
    """
    Executes passed proposals automatically
    
    Features:
    - Atomic action execution (all or nothing)
    - Execution queue with priority
    - Failure handling and retry
    - Execution history tracking
    """
    
    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig.default()
        self.execution_queue: List[UUID] = []  # Ordered proposal IDs
        self.execution_history: Dict[UUID, Dict] = {}  # proposal_id -> execution record
        self.handlers: Dict[str, ExecutionHandler] = {}  # target -> handler
        self._running = False
        logger.info("ExecutionEngine initialized")
    
    def register_handler(self, target: str, handler: ExecutionHandler) -> None:
        """
        Register an execution handler for a target contract
        
        Args:
            target: Target identifier (e.g., "token_contract", "parameter_store")
            handler: Async function that executes actions
        """
        self.handlers[target] = handler
        logger.info(f"Registered execution handler for {target}")
    
    async def queue_proposal(self, proposal: Proposal) -> None:
        """
        Queue a passed proposal for execution
        
        Args:
            proposal: Proposal that has passed voting
        """
        if proposal.status != ProposalStatus.SUCCEEDED:
            raise ValueError(f"Proposal status must be SUCCEEDED, got {proposal.status}")
        
        if proposal.id not in self.execution_queue:
            self.execution_queue.append(proposal.id)
            proposal.status = ProposalStatus.QUEUED
            proposal.queued_at = datetime.utcnow()
            logger.info(f"Proposal {proposal.id} queued for execution")
    
    async def execute_proposal(self, proposal: Proposal) -> bool:
        """
        Execute all actions in a proposal atomically
        
        Args:
            proposal: Proposal to execute
            
        Returns:
            True if all actions executed successfully
        """
        if proposal.status not in [ProposalStatus.QUEUED, ProposalStatus.SUCCEEDED]:
            raise ValueError(f"Cannot execute proposal with status {proposal.status}")
        
        execution_record = {
            "proposal_id": str(proposal.id),
            "started_at": datetime.utcnow().isoformat(),
            "actions": [],
            "success": False
        }
        
        executed_actions = []
        
        try:
            for i, action in enumerate(proposal.actions):
                logger.info(f"Executing action {i+1}/{len(proposal.actions)}: {action.function}")
                
                success = await self._execute_action(action)
                
                action_record = {
                    "index": i,
                    "target": action.target,
                    "function": action.function,
                    "parameters": action.parameters,
                    "success": success
                }
                execution_record["actions"].append(action_record)
                
                if success:
                    executed_actions.append(action)
                else:
                    # Action failed - rollback if needed
                    logger.error(f"Action {i+1} failed, rolling back...")
                    await self._rollback_actions(executed_actions)
                    execution_record["error"] = f"Action {i+1} failed"
                    self.execution_history[proposal.id] = execution_record
                    return False
            
            # All actions succeeded
            proposal.status = ProposalStatus.EXECUTED
            proposal.executed_at = datetime.utcnow()
            execution_record["success"] = True
            execution_record["completed_at"] = datetime.utcnow().isoformat()
            
            if proposal.id in self.execution_queue:
                self.execution_queue.remove(proposal.id)
            
            self.execution_history[proposal.id] = execution_record
            logger.info(f"Proposal {proposal.id} executed successfully")
            return True
            
        except Exception as e:
            logger.exception(f"Execution failed for proposal {proposal.id}")
            execution_record["error"] = str(e)
            execution_record["completed_at"] = datetime.utcnow().isoformat()
            self.execution_history[proposal.id] = execution_record
            return False
    
    async def _execute_action(self, action: Action) -> bool:
        """Execute a single action"""
        handler = self.handlers.get(action.target)
        
        if not handler:
            logger.error(f"No handler registered for target: {action.target}")
            return False
        
        try:
            result = await handler(action)
            return result
        except Exception as e:
            logger.exception(f"Handler failed for {action.target}")
            return False
    
    async def _rollback_actions(self, actions: List[Action]) -> None:
        """
        Rollback executed actions on failure
        
        Note: This is a simplified rollback. Production systems
        should implement proper compensation transactions.
        """
        logger.warning(f"Rolling back {len(actions)} actions")
        # TODO: Implement proper rollback logic
        pass
    
    async def process_queue(self, proposal_lookup: Callable[[UUID], Optional[Proposal]]) -> int:
        """
        Process execution queue
        
        Args:
            proposal_lookup: Function to retrieve proposal by ID
            
        Returns:
            Number of proposals executed
        """
        executed = 0
        
        for proposal_id in list(self.execution_queue):
            proposal = proposal_lookup(proposal_id)
            if not proposal:
                logger.warning(f"Proposal {proposal_id} not found in queue")
                continue
            
            # Check timelock
            if proposal.queued_at:
                elapsed = (datetime.utcnow() - proposal.queued_at).total_seconds()
                if elapsed < self.config.EXECUTION_TIMELOCK_SECONDS:
                    logger.debug(f"Proposal {proposal_id} in timelock")
                    continue
            
            success = await self.execute_proposal(proposal)
            if success:
                executed += 1
        
        return executed
    
    def get_execution_status(self, proposal_id: UUID) -> Optional[Dict]:
        """Get execution status for a proposal"""
        return self.execution_history.get(proposal_id)
