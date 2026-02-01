#!/usr/bin/env python3
"""
Solana SPL Token Transfer Module

This module provides Python interface for Solana SPL Token transfers.
Uses Node.js subprocess to interact with Solana blockchain.

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint (default: https://api.devnet.solana.com)
    ENTITY_TOKEN_MINT: $ENTITY token mint address
    ENTITY_SENDER_PRIVATE_KEY: Sender's private key (base58 or JSON array)
"""

import os
import json
import logging
import subprocess
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_RPC_URL = "https://api.devnet.solana.com"
ENTITY_TOKEN_MINT = "3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i"
DECIMALS = 9

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "solana_token_transfer.js"
)


@dataclass
class TransferResult:
    """Result of a token transfer operation"""
    success: bool
    signature: Optional[str] = None
    sender: Optional[str] = None
    recipient: Optional[str] = None
    amount: float = 0.0
    token_mint: Optional[str] = None
    explorer_url: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "signature": self.signature,
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "token_mint": self.token_mint,
            "explorer_url": self.explorer_url,
            "error": self.error
        }


class SolanaTokenManager:
    """Manager for Solana SPL Token operations"""
    
    def __init__(
        self,
        rpc_url: Optional[str] = None,
        token_mint: Optional[str] = None,
        sender_private_key: Optional[str] = None
    ):
        self.rpc_url = rpc_url or os.environ.get("SOLANA_RPC_URL", DEFAULT_RPC_URL)
        self.token_mint = token_mint or os.environ.get("ENTITY_TOKEN_MINT", ENTITY_TOKEN_MINT)
        self.sender_private_key = sender_private_key or os.environ.get("ENTITY_SENDER_PRIVATE_KEY")
        
        # Verify Node.js script exists
        if not os.path.exists(SCRIPT_PATH):
            raise FileNotFoundError(f"Solana transfer script not found: {SCRIPT_PATH}")
    
    async def transfer(
        self,
        recipient_address: str,
        amount: float,
        sender_private_key: Optional[str] = None,
        token_mint: Optional[str] = None
    ) -> TransferResult:
        """
        Transfer SPL tokens to a recipient
        
        Args:
            recipient_address: Recipient's Solana address (base58)
            amount: Amount to transfer (in token units, not lamports)
            sender_private_key: Override default sender key
            token_mint: Override default token mint
            
        Returns:
            TransferResult with transaction details
        """
        # Use provided or default sender key
        sender_key = sender_private_key or self.sender_private_key
        if not sender_key:
            return TransferResult(
                success=False,
                error="Sender private key not provided"
            )
        
        # Use provided or default token mint
        mint = token_mint or self.token_mint
        
        try:
            # Set environment variables for the script
            env = os.environ.copy()
            env["SOLANA_RPC_URL"] = self.rpc_url
            env["TOKEN_MINT"] = mint
            
            # Build command
            cmd = [
                "node", SCRIPT_PATH,
                sender_key,
                recipient_address,
                str(amount),
                mint
            ]
            
            logger.info(f"Initiating token transfer: {amount} tokens to {recipient_address}")
            
            # Execute transfer script
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=120  # 2 minute timeout
            )
            
            # Parse result
            if result.returncode == 0:
                output = json.loads(result.stdout)
                return TransferResult(
                    success=True,
                    signature=output.get("signature"),
                    sender=output.get("sender"),
                    recipient=output.get("recipient"),
                    amount=output.get("amount", amount),
                    token_mint=output.get("token_mint", mint),
                    explorer_url=output.get("explorer_url")
                )
            else:
                error_output = result.stderr or result.stdout
                try:
                    error_data = json.loads(error_output)
                    error_msg = error_data.get("error", "Unknown error")
                except json.JSONDecodeError:
                    error_msg = error_output or "Transfer failed"
                
                logger.error(f"Token transfer failed: {error_msg}")
                return TransferResult(
                    success=False,
                    error=error_msg,
                    recipient=recipient_address,
                    amount=amount
                )
                
        except subprocess.TimeoutExpired:
            logger.error("Token transfer timed out")
            return TransferResult(
                success=False,
                error="Transfer timed out after 120 seconds",
                recipient=recipient_address,
                amount=amount
            )
        except Exception as e:
            logger.error(f"Token transfer error: {e}")
            return TransferResult(
                success=False,
                error=str(e),
                recipient=recipient_address,
                amount=amount
            )
    
    def get_explorer_url(self, signature: str, cluster: str = "devnet") -> str:
        """Get Solana Explorer URL for a transaction"""
        return f"https://explorer.solana.com/tx/{signature}?cluster={cluster}"
    
    def get_token_address(self) -> str:
        """Get the token mint address"""
        return self.token_mint


# Global instance
_token_manager: Optional[SolanaTokenManager] = None


def init_solana_manager(
    rpc_url: Optional[str] = None,
    token_mint: Optional[str] = None,
    sender_private_key: Optional[str] = None
) -> SolanaTokenManager:
    """Initialize the global Solana token manager"""
    global _token_manager
    _token_manager = SolanaTokenManager(
        rpc_url=rpc_url,
        token_mint=token_mint,
        sender_private_key=sender_private_key
    )
    return _token_manager


def get_solana_manager() -> Optional[SolanaTokenManager]:
    """Get the global Solana token manager instance"""
    return _token_manager


async def transfer_entity_tokens(
    recipient_address: str,
    amount: float,
    sender_private_key: Optional[str] = None
) -> TransferResult:
    """
    Convenience function to transfer $ENTITY tokens
    
    Args:
        recipient_address: Recipient's Solana address
        amount: Amount of $ENTITY tokens to transfer
        sender_private_key: Optional sender private key override
        
    Returns:
        TransferResult with transaction details
    """
    manager = get_solana_manager()
    if not manager:
        manager = init_solana_manager()
    
    return await manager.transfer(
        recipient_address=recipient_address,
        amount=amount,
        sender_private_key=sender_private_key
    )


# Wallet management utilities
def generate_wallet() -> Dict[str, str]:
    """
    Generate a new Solana wallet
    Returns the public key and private key (base58 encoded)
    """
    try:
        # Use Node.js to generate wallet
        script = """
        const { Keypair } = require('@solana/web3.js');
        const bs58 = require('bs58');
        
        const keypair = Keypair.generate();
        const result = {
            public_key: keypair.publicKey.toString(),
            private_key: bs58.encode(keypair.secretKey),
            secret_key_array: Array.from(keypair.secretKey)
        };
        console.log(JSON.stringify(result));
        """
        
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return json.loads(result.stdout.strip())
        else:
            raise RuntimeError(f"Wallet generation failed: {result.stderr}")
            
    except Exception as e:
        logger.error(f"Failed to generate wallet: {e}")
        raise


def validate_address(address: str) -> bool:
    """Validate a Solana address"""
    try:
        script = f"""
        const {{ PublicKey }} = require('@solana/web3.js');
        try {{
            new PublicKey('{address}');
            console.log('true');
        }} catch (e) {{
            console.log('false');
        }}
        """
        
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        return result.stdout.strip() == "true"
        
    except Exception:
        return False


# Test function
if __name__ == "__main__":
    import asyncio
    
    logging.basicConfig(level=logging.INFO)
    
    # Test wallet generation
    print("Testing wallet generation...")
    try:
        wallet = generate_wallet()
        print(f"Generated wallet: {wallet['public_key']}")
        print(f"Address valid: {validate_address(wallet['public_key'])}")
    except Exception as e:
        print(f"Wallet generation test failed: {e}")
    
    # Test token transfer (would need actual private key)
    print("\nSolana Token Module Ready")
    print(f"Token Mint: {ENTITY_TOKEN_MINT}")
    print(f"RPC URL: {DEFAULT_RPC_URL}")
