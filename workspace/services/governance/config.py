"""
Governance System Configuration
"""

from decimal import Decimal
from dataclasses import dataclass


@dataclass
class GovernanceConfig:
    """Configuration for governance system"""
    
    # Token requirements
    MIN_TOKENS_TO_PROPOSE: Decimal = Decimal("1000")
    MIN_TOKENS_TO_VOTE: Decimal = Decimal("100")
    
    # Time periods (in seconds)
    DISCUSSION_PERIOD: int = 2 * 24 * 3600  # 2 days
    VOTING_PERIOD: int = 3 * 24 * 3600      # 3 days
    TIMELOCK_DELAY: int = 2 * 24 * 3600     # 2 days
    EMERGENCY_DELAY: int = 4 * 3600         # 4 hours
    GRACE_PERIOD: int = 14 * 24 * 3600      # 14 days
    
    # Voting thresholds
    QUORUM_PERCENTAGE: float = 10.0         # 10%
    APPROVAL_THRESHOLD: float = 51.0        # 51%
    
    # Voting power
    MAX_VOTING_POWER: Decimal = Decimal("1000000")  # Cap voting power
    DELEGATION_MULTIPLIER: float = 1.0      # No bonus for delegation
    
    # Guardian settings
    GUARDIAN_ADDRESSES: list = None
    GUARDIAN_THRESHOLD: int = 2             # 2-of-3 for emergency
    
    def __post_init__(self):
        if self.GUARDIAN_ADDRESSES is None:
            self.GUARDIAN_ADDRESSES = []
    
    @classmethod
    def default(cls) -> 'GovernanceConfig':
        """Get default configuration"""
        return cls()
    
    @classmethod
    def emergency(cls) -> 'GovernanceConfig':
        """Get emergency configuration (shortened periods)"""
        return cls(
            DISCUSSION_PERIOD=3600,      # 1 hour
            VOTING_PERIOD=4 * 3600,      # 4 hours
            TIMELOCK_DELAY=3600,         # 1 hour
            EMERGENCY_DELAY=1800         # 30 minutes
        )
