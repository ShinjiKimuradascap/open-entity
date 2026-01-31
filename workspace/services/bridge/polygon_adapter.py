"""
Polygon Bridge Adapter

Cross-chain bridge adapter for Polygon PoS network.
Optimized for low-cost, fast transactions.
"""

import os
from decimal import Decimal
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Polygon uses same EVM interface as Ethereum
from .ethereum_adapter import EthereumBridgeAdapter, LockReceipt, BridgeTransaction


@dataclass
class PolygonConfig:
    """Polygon-specific configuration"""
    rpc_url: str
    chain_id: int = 137  # Polygon mainnet
    bridge_contract: Optional[str] = None
    pos_root_chain_manager: Optional[str] = None
    pos_child_chain_manager: Optional[str] = None
    min_confirmations: int = 20
    gas_price_gwei: int = 50


class PolygonBridgeAdapter(EthereumBridgeAdapter):
    """Polygon bridge adapter - extends Ethereum with Polygon-specific features"""
    
    def __init__(
        self,
        rpc_url: Optional[str] = None,
        bridge_contract_address: Optional[str] = None,
        private_key: Optional[str] = None,
        config: Optional[PolygonConfig] = None
    ):
        # Use Polygon defaults
        poly_rpc = rpc_url or os.environ.get("POLYGON_RPC_URL", "https://polygon-rpc.com")
        poly_bridge = bridge_contract_address or os.environ.get("POLYGON_BRIDGE_ADDRESS")
        poly_key = private_key or os.environ.get("POLYGON_PRIVATE_KEY")
        
        super().__init__(poly_rpc, poly_bridge, poly_key)
        
        self.config = config or PolygonConfig(rpc_url=poly_rpc)
        self.config.bridge_contract = poly_bridge
        
        # Polygon-specific state
        self.chain_id = self.config.chain_id
        self.pos_deposit_events = []
        self.pos_withdrawal_events = []
    
    async def lock_tokens_for_polygon_pos(
        self,
        token_address: str,
        amount: Decimal,
        recipient: str
    ) -> LockReceipt:
        """Lock tokens for Polygon PoS bridge (Ethereum -> Polygon)"""
        # This uses Polygon's official PoS bridge
        # Deposit on Ethereum, mint on Polygon
        
        if not self.account:
            raise RuntimeError("Account not configured")
        
        # For PoS bridge, we deposit to RootChainManager on Ethereum
        # Then receive on ChildChainManager on Polygon
        
        # Simplified - actual implementation would interact with
        # RootChainManagerProxy contract on Ethereum
        
        receipt = await self.lock_tokens(
            token_address=token_address,
            amount=amount,
            recipient_chain="polygon",
            recipient_address=recipient
        )
        
        return receipt
    
    async def exit_tokens_from_polygon(
        self,
        burn_tx_hash: str,
        proof: bytes
    ) -> bool:
        """Exit tokens from Polygon PoS bridge (Polygon -> Ethereum)"""
        # Burn on Polygon, exit on Ethereum with proof
        
        # Verify burn transaction
        burn_status = await self.verify_transaction(burn_tx_hash, min_confirmations= checkpoint_interval)
        if burn_status.status != "confirmed":
            return False
        
        # Submit exit proof on Ethereum
        # This would call RootChainManager.exit() with the burn proof
        
        return True
    
    async def get_matic_balance(self, address: str) -> Decimal:
        """Get MATIC token balance"""
        return await self.get_balance(address, token_address=None)
    
    async def estimate_bridge_cost(self, amount: Decimal) -> Dict[str, Decimal]:
        """Estimate total bridge cost including gas fees"""
        # Polygon transactions are much cheaper than Ethereum
        estimated_gas = Decimal("100000")  # Bridge tx gas limit
        gas_price_gwei = Decimal(self.config.gas_price_gwei)
        
        # Calculate MATIC cost
        matic_cost = (estimated_gas * gas_price_gwei) / Decimal(10**9)
        
        return {
            "estimated_gas_units": estimated_gas,
            "gas_price_gwei": gas_price_gwei,
            "estimated_matic_cost": matic_cost,
            "bridge_fee": Decimal("0"),  # Polygon PoS has no bridge fee
            "total_estimated_cost": matic_cost
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Polygon-specific health check"""
        base_health = await super().health_check()
        
        if base_health["connected"]:
            try:
                # Check Polygon chain ID
                chain_id = self.w3.eth.chain_id
                is_polygon = chain_id == self.chain_id
                
                base_health.update({
                    "chain_id": chain_id,
                    "is_polygon_network": is_polygon,
                    "pos_bridge_configured": self.config.pos_root_chain_manager is not None
                })
                
                if not is_polygon:
                    base_health["status"] = "warning"
                    base_health["warning"] = f"Expected chain ID {self.chain_id}, got {chain_id}"
                    
            except Exception as e:
                base_health["status"] = "error"
                base_health["error"] = str(e)
        
        return base_health
    
    async def get_bridge_stats(self) -> Dict[str, Any]:
        """Get Polygon bridge statistics"""
        return {
            "chain": "polygon",
            "chain_id": self.chain_id,
            "bridge_type": "pos",
            "avg_block_time_sec": 2.3,
            "min_confirmations": self.config.min_confirmations,
            "estimated_finality_time_sec": self.config.min_confirmations * 2.3
        }


# Convenience factory
async def create_polygon_adapter(
    rpc_url: Optional[str] = None,
    bridge_address: Optional[str] = None,
    private_key: Optional[str] = None
) -> PolygonBridgeAdapter:
    """Factory function to create Polygon bridge adapter"""
    return PolygonBridgeAdapter(rpc_url, bridge_address, private_key)
