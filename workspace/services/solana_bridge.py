#!/usr/bin/env python3
"""
Solana Bridge Python Wrapper
Bridges internal token system with Solana blockchain
"""

import subprocess
import json
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths
SCRIPT_DIR = Path(__file__).parent
SOLANA_BRIDGE_JS = SCRIPT_DIR / "solana_bridge.js"
WALLET_DIR = Path(__file__).parent.parent / "data" / "solana_wallets"

# Ensure wallet directory exists
WALLET_DIR.mkdir(parents=True, exist_ok=True)

# Solana configuration
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.devnet.solana.com")
ENTITY_TOKEN_MINT = os.getenv("ENTITY_TOKEN_MINT", "3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i")


class SolanaBridgeError(Exception):
    """Solana bridge operation error"""
    pass


def _run_bridge_command(*args) -> Dict[str, Any]:
    """
    Run solana_bridge.js with given arguments
    
    Returns:
        Parsed JSON result
    """
    try:
        cmd = ["node", str(SOLANA_BRIDGE_JS)] + list(args)
        logger.debug(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,  # 60 second timeout for blockchain operations
            cwd=str(SCRIPT_DIR)
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unknown error"
            logger.error(f"Solana bridge command failed: {error_msg}")
            raise SolanaBridgeError(f"Command failed: {error_msg}")
        
        # Parse JSON output
        output = result.stdout.strip()
        if not output:
            return {"success": False, "error": "Empty output from bridge"}
        
        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse bridge output: {output}")
            raise SolanaBridgeError(f"Invalid JSON output: {e}")
            
    except subprocess.TimeoutExpired:
        logger.error("Solana bridge command timed out")
        raise SolanaBridgeError("Operation timed out")
    except FileNotFoundError:
        logger.error("Node.js not found or solana_bridge.js missing")
        raise SolanaBridgeError("Node.js bridge not available")
    except Exception as e:
        logger.error(f"Unexpected error running bridge: {e}")
        raise SolanaBridgeError(f"Bridge error: {e}")


def get_solana_address(entity_id: str) -> str:
    """
    Get Solana public key for an entity
    
    Args:
        entity_id: Entity identifier
        
    Returns:
        Solana public key (base58)
    """
    result = _run_bridge_command("address", entity_id)
    if result.get("success", True):
        return result.get("public_key", "")
    raise SolanaBridgeError(f"Failed to get address: {result.get('error')}")


def get_token_balance(entity_id: str) -> Dict[str, Any]:
    """
    Get SPL token balance for an entity
    
    Args:
        entity_id: Entity identifier
        
    Returns:
        Balance information dict
    """
    return _run_bridge_command("balance", entity_id)


def transfer_tokens(
    from_entity: str,
    to_entity: str,
    amount: float,
    order_id: str = ""
) -> Dict[str, Any]:
    """
    Transfer SPL tokens between entities
    
    Args:
        from_entity: Sender entity ID
        to_entity: Recipient entity ID
        amount: Amount to transfer (in tokens)
        order_id: Optional order ID for reference
        
    Returns:
        Transaction result with signature
    """
    if amount <= 0:
        return {
            "success": False,
            "error": "Amount must be positive"
        }
    
    result = _run_bridge_command(
        "transfer",
        from_entity,
        to_entity,
        str(amount),
        order_id
    )
    
    if result.get("success"):
        logger.info(f"Solana transfer: {amount} tokens from {from_entity} to {to_entity}")
        logger.info(f"Signature: {result.get('signature')}")
    else:
        logger.error(f"Solana transfer failed: {result.get('error')}")
    
    return result


def request_airdrop(entity_id: str, amount_sol: float = 1.0) -> Dict[str, Any]:
    """
    Request SOL airdrop on devnet (for testing)
    
    Args:
        entity_id: Entity identifier
        amount_sol: Amount of SOL to request
        
    Returns:
        Airdrop result
    """
    return _run_bridge_command("airdrop", entity_id, str(amount_sol))


def sync_internal_to_solana(
    entity_id: str,
    internal_balance: float
) -> Dict[str, Any]:
    """
    Sync internal JSON balance to Solana blockchain
    This is a one-way sync (internal -> Solana)
    
    Args:
        entity_id: Entity identifier
        internal_balance: Current internal balance
        
    Returns:
        Sync result
    """
    # Get current Solana balance
    solana_info = get_token_balance(entity_id)
    solana_balance = solana_info.get("balance", 0) if solana_info.get("success") else 0
    
    # Calculate difference (for now, just report)
    difference = internal_balance - solana_balance
    
    return {
        "success": True,
        "entity_id": entity_id,
        "internal_balance": internal_balance,
        "solana_balance": solana_balance,
        "difference": difference,
        "synced": difference == 0,
        "note": "One-way sync report (minting not implemented)"
    }


class SolanaWallet:
    """
    Solana wallet wrapper for entity
    """
    
    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        self._public_key = None
    
    @property
    def public_key(self) -> str:
        """Get Solana public key"""
        if self._public_key is None:
            self._public_key = get_solana_address(self.entity_id)
        return self._public_key
    
    def get_balance(self) -> Dict[str, Any]:
        """Get token balance"""
        return get_token_balance(self.entity_id)
    
    def transfer(self, to_entity: str, amount: float, order_id: str = "") -> Dict[str, Any]:
        """Transfer tokens to another entity"""
        return transfer_tokens(self.entity_id, to_entity, amount, order_id)


# Convenience functions for marketplace integration
def execute_marketplace_payment(
    buyer_id: str,
    provider_id: str,
    amount: float,
    order_id: str
) -> Dict[str, Any]:
    """
    Execute marketplace payment on Solana blockchain
    
    This function is designed to be called from approve_order()
    after internal token transfer succeeds.
    
    Args:
        buyer_id: Buyer entity ID
        provider_id: Provider entity ID
        amount: Payment amount
        order_id: Order identifier
        
    Returns:
        Blockchain transaction result
    """
    logger.info(f"Executing Solana payment for order {order_id}")
    logger.info(f"Buyer: {buyer_id}, Provider: {provider_id}, Amount: {amount}")
    
    try:
        result = transfer_tokens(buyer_id, provider_id, amount, order_id)
        
        if result.get("success"):
            logger.info(f"✅ Solana payment successful: {result.get('signature')}")
        else:
            logger.error(f"❌ Solana payment failed: {result.get('error')}")
        
        return result
        
    except Exception as e:
        logger.error(f"Solana payment exception: {e}")
        return {
            "success": False,
            "error": str(e),
            "order_id": order_id
        }


# Testing
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Test functions
    print("=== Solana Bridge Test ===")
    print(f"Token Mint: {ENTITY_TOKEN_MINT}")
    print(f"RPC: {SOLANA_RPC}")
    
    # Test getting address
    test_entity = "entity_a_main"
    print(f"\n1. Getting address for {test_entity}")
    try:
        address = get_solana_address(test_entity)
        print(f"   Address: {address}")
    except SolanaBridgeError as e:
        print(f"   Error: {e}")
    
    # Test getting balance
    print(f"\n2. Getting balance for {test_entity}")
    try:
        balance = get_token_balance(test_entity)
        print(f"   Balance: {balance}")
    except SolanaBridgeError as e:
        print(f"   Error: {e}")
