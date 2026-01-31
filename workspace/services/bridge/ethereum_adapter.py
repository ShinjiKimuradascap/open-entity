"""
Ethereum Bridge Adapter

Cross-chain bridge adapter for Ethereum network.
Handles token locking, minting, burning, and verification.
"""

import os
import json
import asyncio
from decimal import Decimal
from typing import Optional, Dict, Any
from dataclasses import dataclass
from web3 import Web3
from web3.contract import Contract
from web3.types import TxReceipt, Wei, ChecksumAddress


@dataclass
class LockReceipt:
    """Token lock receipt"""
    lock_id: str
    tx_hash: str
    amount: Decimal
    token: str
    recipient: str
    block_number: int
    status: str  # pending, confirmed, failed


@dataclass
class BridgeTransaction:
    """Bridge transaction status"""
    tx_hash: str
    status: str  # pending, confirmed, failed
    confirmations: int
    block_number: Optional[int]
    gas_used: Optional[int]
    effective_gas_price: Optional[int]


class EthereumBridgeAdapter:
    """Ethereum bridge adapter for cross-chain transfers"""
    
    # Bridge contract ABI (placeholder - actual ABI needed)
    BRIDGE_ABI = [
        {
            "inputs": [
                {"internalType": "address", "name": "token", "type": "address"},
                {"internalType": "uint256", "name": "amount", "type": "uint256"},
                {"internalType": "string", "name": "recipient", "type": "string"}
            ],
            "name": "lockTokens",
            "outputs": [{"internalType": "bytes32", "name": "lockId", "type": "bytes32"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {"internalType": "bytes32", "name": "lockId", "type": "bytes32"},
                {"internalType": "bytes", "name": "proof", "type": "bytes"}
            ],
            "name": "releaseTokens",
            "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "bytes32", "name": "lockId", "type": "bytes32"},
                {"indexed": False, "internalType": "address", "name": "token", "type": "address"},
                {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
                {"indexed": False, "internalType": "string", "name": "recipient", "type": "string"}
            ],
            "name": "TokensLocked",
            "type": "event"
        }
    ]
    
    def __init__(
        self,
        rpc_url: Optional[str] = None,
        bridge_contract_address: Optional[str] = None,
        private_key: Optional[str] = None
    ):
        self.rpc_url = rpc_url or os.environ.get("ETH_RPC_URL", "https://mainnet.infura.io/v3/YOUR_PROJECT_ID")
        self.bridge_address = bridge_contract_address or os.environ.get("ETH_BRIDGE_ADDRESS")
        self.private_key = private_key or os.environ.get("ETH_PRIVATE_KEY")
        
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.bridge_contract: Optional[Contract] = None
        
        if self.bridge_address:
            self.bridge_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.bridge_address),
                abi=self.BRIDGE_ABI
            )
        
        self.account = None
        if self.private_key:
            self.account = self.w3.eth.account.from_key(self.private_key)
    
    async def lock_tokens(
        self,
        token_address: str,
        amount: Decimal,
        recipient_chain: str,
        recipient_address: str
    ) -> LockReceipt:
        """Lock tokens on Ethereum for cross-chain transfer"""
        if not self.bridge_contract or not self.account:
            raise RuntimeError("Bridge contract or account not configured")
        
        # Convert amount to Wei (assuming 18 decimals)
        amount_wei = self.w3.to_wei(amount, 'ether')
        
        # Build transaction
        tx = self.bridge_contract.functions.lockTokens(
            Web3.to_checksum_address(token_address),
            amount_wei,
            f"{recipient_chain}:{recipient_address}"
        ).build_transaction({
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'gas': 200000,
            'gasPrice': self.w3.eth.gas_price
        })
        
        # Sign and send
        signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Wait for receipt
        receipt = await self._wait_for_receipt(tx_hash.hex())
        
        # Parse lock ID from event
        lock_id = self._parse_lock_id_from_receipt(receipt)
        
        return LockReceipt(
            lock_id=lock_id or tx_hash.hex(),
            tx_hash=tx_hash.hex(),
            amount=amount,
            token=token_address,
            recipient=recipient_address,
            block_number=receipt.block_number if receipt else 0,
            status="confirmed" if receipt else "pending"
        )
    
    async def verify_transaction(self, tx_hash: str, min_confirmations: int = 12) -> BridgeTransaction:
        """Verify transaction status with minimum confirmations"""
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if not receipt:
                return BridgeTransaction(
                    tx_hash=tx_hash,
                    status="pending",
                    confirmations=0,
                    block_number=None,
                    gas_used=None,
                    effective_gas_price=None
                )
            
            current_block = self.w3.eth.block_number
            confirmations = current_block - receipt.block_number
            
            return BridgeTransaction(
                tx_hash=tx_hash,
                status="confirmed" if confirmations >= min_confirmations else "pending",
                confirmations=confirmations,
                block_number=receipt.block_number,
                gas_used=receipt.gasUsed,
                effective_gas_price=receipt.effectiveGasPrice
            )
        except Exception as e:
            return BridgeTransaction(
                tx_hash=tx_hash,
                status="failed",
                confirmations=0,
                block_number=None,
                gas_used=None,
                effective_gas_price=None
            )
    
    async def get_balance(self, address: str, token_address: Optional[str] = None) -> Decimal:
        """Get ETH or ERC-20 token balance"""
        checksum_addr = Web3.to_checksum_address(address)
        
        if token_address:
            # ERC-20 balance
            erc20_abi = [
                {
                    "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function"
                }
            ]
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=erc20_abi
            )
            balance = token_contract.functions.balanceOf(checksum_addr).call()
            # Assuming 18 decimals
            return Decimal(balance) / Decimal(10**18)
        else:
            # ETH balance
            balance = self.w3.eth.get_balance(checksum_addr)
            return Decimal(self.w3.from_wei(balance, 'ether'))
    
    async def _wait_for_receipt(self, tx_hash: str, timeout: int = 120) -> Optional[TxReceipt]:
        """Wait for transaction receipt"""
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    return receipt
            except Exception:
                pass
            await asyncio.sleep(2)
        return None
    
    def _parse_lock_id_from_receipt(self, receipt: TxReceipt) -> Optional[str]:
        """Parse lock ID from transaction receipt events"""
        if not receipt or not self.bridge_contract:
            return None
        
        # Parse TokensLocked event
        for log in receipt.logs:
            try:
                event = self.bridge_contract.events.TokensLocked().process_log(log)
                return event.args.lockId.hex()
            except Exception:
                continue
        return None
    
    def is_connected(self) -> bool:
        """Check if connected to Ethereum node"""
        return self.w3.is_connected()
    
    async def health_check(self) -> Dict[str, Any]:
        """Adapter health check"""
        try:
            block_number = self.w3.eth.block_number
            syncing = self.w3.eth.syncing
            
            return {
                "status": "healthy",
                "connected": True,
                "block_number": block_number,
                "syncing": syncing is not False,
                "bridge_contract": self.bridge_address is not None,
                "account": self.account.address if self.account else None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }


# Convenience factory
async def create_ethereum_adapter(
    rpc_url: Optional[str] = None,
    bridge_address: Optional[str] = None,
    private_key: Optional[str] = None
) -> EthereumBridgeAdapter:
    """Factory function to create Ethereum bridge adapter"""
    return EthereumBridgeAdapter(rpc_url, bridge_address, private_key)
