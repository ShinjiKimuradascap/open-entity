"""
Bridge Core Engine

Central coordinator for cross-chain token transfers.
Manages Lock-Mint and Burn-Release flows across multiple chains.
"""

import uuid
import asyncio
from enum import Enum
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta


class TransferStatus(Enum):
    PENDING = "pending"
    LOCKING = "locking"
    LOCKED = "locked"
    VERIFYING = "verifying"
    RELAYING = "relaying"
    MINTING = "minting"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class TransferDirection(Enum):
    LOCK_MINT = "lock_mint"  # Source -> Destination
    BURN_RELEASE = "burn_release"  # Destination -> Source


@dataclass
class TransferRequest:
    """Cross-chain transfer request"""
    transfer_id: str
    source_chain: str
    destination_chain: str
    direction: TransferDirection
    token: str
    amount: Decimal
    sender: str
    recipient: str
    status: TransferStatus
    created_at: datetime
    updated_at: datetime
    source_tx: Optional[str] = None
    destination_tx: Optional[str] = None
    lock_id: Optional[str] = None
    proof: Optional[bytes] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainAdapter:
    """Chain adapter interface"""
    name: str
    adapter: Any  # Actual adapter instance
    config: Dict[str, Any]
    is_active: bool = True


class BridgeCoreEngine:
    """Core engine for cross-chain bridge operations"""
    
    def __init__(self):
        self.adapters: Dict[str, ChainAdapter] = {}
        self.transfers: Dict[str, TransferRequest] = {}
        self.listeners: List[Callable] = []
        self._lock = asyncio.Lock()
        self._running = False
        self._poll_interval = 5  # seconds
        
        # Config
        self.min_confirmations = {
            "ethereum": 12,
            "polygon": 20,
            "solana": 32
        }
        self.max_retries = 3
        self.timeout_hours = 4
    
    def register_adapter(self, name: str, adapter: Any, config: Dict[str, Any] = None):
        """Register a chain adapter"""
        self.adapters[name] = ChainAdapter(
            name=name,
            adapter=adapter,
            config=config or {}
        )
    
    async def start(self):
        """Start the bridge engine"""
        self._running = True
        asyncio.create_task(self._transfer_monitor_loop())
    
    async def stop(self):
        """Stop the bridge engine"""
        self._running = False
    
    async def request_transfer(
        self,
        source_chain: str,
        destination_chain: str,
        token: str,
        amount: Decimal,
        sender: str,
        recipient: str
    ) -> TransferRequest:
        """Request a new cross-chain transfer"""
        transfer_id = str(uuid.uuid4())
        
        transfer = TransferRequest(
            transfer_id=transfer_id,
            source_chain=source_chain,
            destination_chain=destination_chain,
            direction=TransferDirection.LOCK_MINT,
            token=token,
            amount=amount,
            sender=sender,
            recipient=recipient,
            status=TransferStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        async with self._lock:
            self.transfers[transfer_id] = transfer
        
        # Start transfer flow
        asyncio.create_task(self._execute_lock_mint_flow(transfer_id))
        
        return transfer
    
    async def get_transfer_status(self, transfer_id: str) -> Optional[TransferRequest]:
        """Get transfer status"""
        return self.transfers.get(transfer_id)
    
    async def _execute_lock_mint_flow(self, transfer_id: str):
        """Execute Lock-Mint flow"""
        transfer = self.transfers.get(transfer_id)
        if not transfer:
            return
        
        try:
            # Step 1: Lock tokens on source chain
            await self._update_status(transfer, TransferStatus.LOCKING)
            source_adapter = self.adapters.get(transfer.source_chain)
            if not source_adapter:
                raise ValueError(f"Adapter not found: {transfer.source_chain}")
            
            lock_receipt = await source_adapter.adapter.lock_tokens(
                token_address=transfer.token,
                amount=transfer.amount,
                recipient_chain=transfer.destination_chain,
                recipient_address=transfer.recipient
            )
            
            transfer.source_tx = lock_receipt.tx_hash
            transfer.lock_id = lock_receipt.lock_id
            await self._update_status(transfer, TransferStatus.LOCKED)
            
            # Step 2: Wait for confirmations
            await self._update_status(transfer, TransferStatus.VERIFYING)
            min_conf = self.min_confirmations.get(transfer.source_chain, 12)
            
            verified = await self._wait_for_confirmations(
                transfer.source_chain,
                lock_receipt.tx_hash,
                min_conf
            )
            
            if not verified:
                raise TimeoutError("Confirmation timeout")
            
            # Step 3: Generate proof and relay
            await self._update_status(transfer, TransferStatus.RELAYING)
            proof = await self._generate_proof(transfer)
            transfer.proof = proof
            
            # Step 4: Mint tokens on destination chain
            await self._update_status(transfer, TransferStatus.MINTING)
            dest_adapter = self.adapters.get(transfer.destination_chain)
            if not dest_adapter:
                raise ValueError(f"Adapter not found: {transfer.destination_chain}")
            
            # Mint call would go here
            # mint_tx = await dest_adapter.adapter.mint_tokens(...)
            # transfer.destination_tx = mint_tx
            
            await self._update_status(transfer, TransferStatus.COMPLETED)
            
        except Exception as e:
            transfer.error_message = str(e)
            await self._update_status(transfer, TransferStatus.FAILED)
            
            # Retry logic
            if transfer.retry_count < self.max_retries:
                transfer.retry_count += 1
                await asyncio.sleep(10 * transfer.retry_count)
                asyncio.create_task(self._execute_lock_mint_flow(transfer_id))
    
    async def _wait_for_confirmations(
        self,
        chain: str,
        tx_hash: str,
        min_confirmations: int
    ) -> bool:
        """Wait for transaction confirmations"""
        adapter = self.adapters.get(chain)
        if not adapter:
            return False
        
        timeout = datetime.utcnow() + timedelta(hours=self.timeout_hours)
        
        while datetime.utcnow() < timeout:
            try:
                status = await adapter.adapter.verify_transaction(tx_hash, min_confirmations)
                if status.status == "confirmed":
                    return True
                if status.status == "failed":
                    return False
            except Exception:
                pass
            
            await asyncio.sleep(self._poll_interval)
        
        return False
    
    async def _generate_proof(self, transfer: TransferRequest) -> bytes:
        """Generate cryptographic proof for relay"""
        # Simplified - actual implementation would use merkle proofs or threshold sigs
        proof_data = f"{transfer.lock_id}:{transfer.amount}:{transfer.recipient}"
        return proof_data.encode()
    
    async def _update_status(self, transfer: TransferRequest, status: TransferStatus):
        """Update transfer status and notify listeners"""
        transfer.status = status
        transfer.updated_at = datetime.utcnow()
        
        for listener in self.listeners:
            try:
                await listener(transfer)
            except Exception:
                pass
    
    async def _transfer_monitor_loop(self):
        """Monitor pending transfers"""
        while self._running:
            try:
                # Check for stuck transfers
                now = datetime.utcnow()
                for transfer in list(self.transfers.values()):
                    if transfer.status in [TransferStatus.PENDING, TransferStatus.LOCKING]:
                        if now - transfer.created_at > timedelta(hours=self.timeout_hours):
                            await self._update_status(transfer, TransferStatus.FAILED)
                            transfer.error_message = "Transfer timeout"
                
                await asyncio.sleep(self._poll_interval)
            except Exception:
                await asyncio.sleep(self._poll_interval)
    
    def add_listener(self, listener: Callable):
        """Add status change listener"""
        self.listeners.append(listener)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bridge statistics"""
        total = len(self.transfers)
        completed = sum(1 for t in self.transfers.values() if t.status == TransferStatus.COMPLETED)
        failed = sum(1 for t in self.transfers.values() if t.status == TransferStatus.FAILED)
        pending = sum(1 for t in self.transfers.values() if t.status in [
            TransferStatus.PENDING, TransferStatus.LOCKING, TransferStatus.VERIFYING,
            TransferStatus.RELAYING, TransferStatus.MINTING
        ])
        
        return {
            "total_transfers": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "success_rate": completed / total if total > 0 else 0,
            "registered_chains": list(self.adapters.keys())
        }


# Factory function
async def create_bridge_engine() -> BridgeCoreEngine:
    """Factory to create bridge core engine"""
    return BridgeCoreEngine()
