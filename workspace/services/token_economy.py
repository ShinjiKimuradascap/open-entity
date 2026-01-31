#!/usr/bin/env python3
"""
Token Economy Manager
Handles token minting, burning, and supply management
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path
import json
import logging
import threading

# Import from token_system (support both relative and absolute imports)
try:
    from .token_system import TokenWallet, Transaction, TransactionType, create_wallet, get_wallet
except ImportError:
    from token_system import TokenWallet, Transaction, TransactionType, create_wallet, get_wallet

logger = logging.getLogger(__name__)


@dataclass
class TokenMetadata:
    """Token metadata and configuration"""
    name: str = "AI Credit"
    symbol: str = "AIC"
    decimals: int = 8
    total_supply: float = 0.0
    max_supply: Optional[float] = None  # None = unlimited
    mintable: bool = True
    burnable: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "total_supply": self.total_supply,
            "max_supply": self.max_supply,
            "mintable": self.mintable,
            "burnable": self.burnable
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenMetadata":
        return cls(
            name=data.get("name", "AI Credit"),
            symbol=data.get("symbol", "AIC"),
            decimals=data.get("decimals", 8),
            total_supply=data.get("total_supply", 0.0),
            max_supply=data.get("max_supply"),
            mintable=data.get("mintable", True),
            burnable=data.get("burnable", True)
        )


@dataclass
class TokenEconomy:
    """
    Central bank functionality for token management
    - Mint new tokens
    - Burn existing tokens
    - Track supply metrics
    """
    
    metadata: TokenMetadata = field(default_factory=TokenMetadata)
    _treasury: Optional[TokenWallet] = field(default=None, repr=False)
    _mint_history: list[Dict] = field(default_factory=list, repr=False)
    _burn_history: list[Dict] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def __post_init__(self):
        """Initialize treasury wallet and load persisted state"""
        if self._treasury is None:
            self._treasury = create_wallet("TREASURY", 0)
        # Load persisted state if available
        self._load()
    
    def mint(self, amount: float, to_entity_id: str,
             reason: str = "") -> Dict[str, Any]:
        """
        Mint new tokens and send to entity
        
        Args:
            amount: Amount to mint (must be positive)
            to_entity_id: Recipient entity ID
            reason: Reason for minting
            
        Returns:
            Operation result with status and details
        """
        with self._lock:
            if not self.metadata.mintable:
                return {
                    "success": False,
                    "error": "Token is not mintable",
                    "operation_id": None
                }
            
            if amount <= 0:
                return {
                    "success": False,
                    "error": f"Mint amount must be positive: {amount}",
                    "operation_id": None
                }
            
            # Check max supply
            if self.metadata.max_supply is not None:
                new_supply = self.metadata.total_supply + amount
                if new_supply > self.metadata.max_supply:
                    return {
                        "success": False,
                        "error": f"Mint would exceed max supply: {new_supply} > {self.metadata.max_supply}",
                        "operation_id": None
                    }
            
            # Get or create recipient wallet
            wallet = get_wallet(to_entity_id)
            if wallet is None:
                wallet = create_wallet(to_entity_id, 0)
            
            # Generate operation ID
            operation_id = f"mint_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
            
            # Mint to treasury first, then transfer
            self._treasury._add_minted(amount, f"Minted: {reason}" if reason else "Token minting")
            
            # Transfer to recipient
            transfer_success = self._treasury.transfer(wallet, amount,
                                                       description=f"Minted tokens: {reason}")
            
            if transfer_success:
                self.metadata.total_supply += amount
                mint_record = {
                    "operation_id": operation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "amount": amount,
                    "to": to_entity_id,
                    "reason": reason,
                    "new_supply": self.metadata.total_supply
                }
                self._mint_history.append(mint_record)
                
                # Persist to file
                if self._save():
                    logger.info(f"Minted {amount} AIC to {to_entity_id}. Total supply: {self.metadata.total_supply}")
                    return {
                        "success": True,
                        "operation_id": operation_id,
                        "amount": amount,
                        "new_total_supply": self.metadata.total_supply,
                        "new_circulating_supply": self.get_circulating_supply()
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to persist mint operation",
                        "operation_id": operation_id
                    }
            
            # Rollback: burn the minted tokens from treasury
            rollback_success = self._treasury._burn_tokens(amount, f"Rollback mint: {reason}")
            if rollback_success:
                logger.warning(f"Mint rolled back: {amount} AIC burned from treasury due to transfer failure")
            else:
                logger.error(f"Mint rollback failed: could not burn {amount} AIC from treasury")
            
            return {
                "success": False,
                "error": "Transfer failed",
                "operation_id": operation_id,
                "rolled_back": rollback_success
            }
    
    def burn(self, amount: float, from_wallet: TokenWallet,
             reason: str = "") -> Dict[str, Any]:
        """
        Burn (destroy) tokens permanently
        
        Args:
            amount: Amount to burn (must be positive)
            from_wallet: Wallet to burn from
            reason: Reason for burning
            
        Returns:
            Operation result with status and details
        """
        with self._lock:
            if not self.metadata.burnable:
                return {
                    "success": False,
                    "error": "Token is not burnable",
                    "operation_id": None
                }
            
            if amount <= 0:
                return {
                    "success": False,
                    "error": f"Burn amount must be positive: {amount}",
                    "operation_id": None
                }
            
            if from_wallet.get_balance() < amount:
                return {
                    "success": False,
                    "error": f"Insufficient balance to burn: {from_wallet.get_balance()} < {amount}",
                    "operation_id": None
                }
            
            # Generate operation ID
            operation_id = f"burn_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
            
            # Deduct from wallet
            from_wallet._balance -= amount
            from_wallet._transactions.append(Transaction(
                type=TransactionType.PENALTY,  # Use PENALTY for burn
                amount=amount,
                description=f"Burned: {reason}" if reason else "Token burn"
            ))
            
            # Reduce total supply
            self.metadata.total_supply -= amount
            
            burn_record = {
                "operation_id": operation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "amount": amount,
                "from": from_wallet.entity_id,
                "reason": reason,
                "new_supply": self.metadata.total_supply
            }
            self._burn_history.append(burn_record)
            
            # Persist to file
            if self._save():
                logger.info(f"Burned {amount} AIC from {from_wallet.entity_id}. Total supply: {self.metadata.total_supply}")
                return {
                    "success": True,
                    "operation_id": operation_id,
                    "amount": amount,
                    "new_circulating_supply": self.get_circulating_supply(),
                    "total_burned": sum(h.get("amount", 0) for h in self._burn_history)
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to persist burn operation",
                    "operation_id": operation_id
                }
    
    def get_total_supply(self) -> float:
        """Get total token supply"""
        return self.metadata.total_supply
    
    def get_circulating_supply(self) -> float:
        """Get circulating supply (total - treasury)"""
        treasury_balance = self._treasury.get_balance() if self._treasury else 0
        return self.metadata.total_supply - treasury_balance
    
    def get_treasury_balance(self) -> float:
        """Get treasury balance"""
        return self._treasury.get_balance() if self._treasury else 0
    
    def get_mint_history(self, limit: int = 100) -> list[Dict]:
        """Get minting history"""
        return self._mint_history[-limit:]
    
    def get_burn_history(self, limit: int = 100) -> list[Dict]:
        """Get burn history"""
        return self._burn_history[-limit:]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence"""
        return {
            "metadata": self.metadata.to_dict(),
            "mint_history": self._mint_history,
            "burn_history": self._burn_history
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenEconomy":
        """Create from dictionary"""
        economy = cls(
            metadata=TokenMetadata.from_dict(data.get("metadata", {}))
        )
        economy._mint_history = data.get("mint_history", [])
        economy._burn_history = data.get("burn_history", [])
        return economy
    
    def _save(self) -> bool:
        """Save economy state to JSON file"""
        try:
            data_dir = Path("data/economy")
            data_dir.mkdir(parents=True, exist_ok=True)
            filepath = data_dir / "economy.json"
            
            data = {
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "metadata": self.metadata.to_dict(),
                "mint_history": self._mint_history,
                "burn_history": self._burn_history
            }
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved economy state to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save economy state: {e}")
            return False
    
    def _load(self) -> bool:
        """Load economy state from JSON file"""
        filepath = Path("data/economy/economy.json")
        if not filepath.exists():
            logger.info(f"No economy file found at {filepath}, starting fresh")
            return False
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.metadata = TokenMetadata.from_dict(data.get("metadata", {}))
            self._mint_history = data.get("mint_history", [])
            self._burn_history = data.get("burn_history", [])
            
            logger.info(f"Loaded economy state from {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to load economy state: {e}")
            return False
    
    def get_supply_stats(self) -> Dict[str, Any]:
        """
        Get current supply statistics.
        
        Returns:
            Dictionary with supply metrics
        """
        return {
            "total_supply": self.metadata.total_supply,
            "circulating_supply": self.get_circulating_supply(),
            "treasury_balance": self.get_treasury_balance(),
            "burned_tokens": sum(h.get("amount", 0) for h in self._burn_history),
            "mint_operations_count": len(self._mint_history),
            "burn_operations_count": len(self._burn_history),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }


# Global instance
_token_economy: Optional[TokenEconomy] = None


def get_token_economy() -> TokenEconomy:
    """Get or create global token economy"""
    global _token_economy
    if _token_economy is None:
        _token_economy = TokenEconomy()
    return _token_economy


def initialize_token_economy(metadata: Optional[TokenMetadata] = None) -> TokenEconomy:
    """Initialize token economy with custom metadata"""
    global _token_economy
    _token_economy = TokenEconomy(metadata=metadata or TokenMetadata())
    return _token_economy


if __name__ == "__main__":
    print("=== Token Economy Test ===")
    
    # Initialize
    economy = get_token_economy()
    print(f"Initial supply: {economy.get_total_supply()}")
    
    # Create test wallet
    alice = create_wallet("alice", 0)
    
    # Mint tokens
    economy.mint(10000, "alice", "Initial distribution")
    print(f"After mint - Total: {economy.get_total_supply()}, Alice: {alice.get_balance()}")
    
    # Burn tokens
    economy.burn(1000, alice, "Fee burn")
    print(f"After burn - Total: {economy.get_total_supply()}, Alice: {alice.get_balance()}")
    
    # Check history
    print(f"\nMint history: {len(economy.get_mint_history())} entries")
    print(f"Burn history: {len(economy.get_burn_history())} entries")
    
    print("=== Test Complete ===")
