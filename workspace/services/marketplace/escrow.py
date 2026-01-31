#!/usr/bin/env python3
"""
Escrow Manager for AI Multi-Agent Marketplace

Manages token escrow for service transactions.
"""

import uuid
import json
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from enum import Enum


class EscrowStatus(Enum):
    PENDING = "pending"       # Funds locked, waiting for service
    RELEASED = "released"     # Funds released to provider
    REFUNDED = "refunded"     # Funds returned to buyer
    DISPUTED = "disputed"     # Under dispute resolution
    EXPIRED = "expired"       # Escrow expired


@dataclass
class Escrow:
    """Escrow information"""
    escrow_id: str
    order_id: str
    buyer_id: str
    provider_id: str
    amount: Decimal
    status: EscrowStatus
    created_at: datetime
    expires_at: datetime
    released_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    dispute_reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        data = asdict(self)
        data['status'] = self.status.value
        data['amount'] = str(self.amount)
        data['created_at'] = self.created_at.isoformat()
        data['expires_at'] = self.expires_at.isoformat()
        data['released_at'] = self.released_at.isoformat() if self.released_at else None
        data['refunded_at'] = self.refunded_at.isoformat() if self.refunded_at else None
        return data


class EscrowManager:
    """Manages token escrow for marketplace transactions"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self._escrows: Dict[str, Escrow] = {}
        self._order_escrow: Dict[str, str] = {}  # order_id -> escrow_id
        self._storage_path = storage_path
        self._lock = asyncio.Lock()
        
        if storage_path:
            self._load_from_storage()
    
    async def create_escrow(
        self,
        order_id: str,
        buyer_id: str,
        provider_id: str,
        amount: Decimal,
        expiry_hours: int = 48
    ) -> Optional[Escrow]:
        """Create new escrow for an order"""
        async with self._lock:
            # Check if escrow already exists
            if order_id in self._order_escrow:
                return None
            
            escrow_id = str(uuid.uuid4())
            
            escrow = Escrow(
                escrow_id=escrow_id,
                order_id=order_id,
                buyer_id=buyer_id,
                provider_id=provider_id,
                amount=amount,
                status=EscrowStatus.PENDING,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=expiry_hours)
            )
            
            self._escrows[escrow_id] = escrow
            self._order_escrow[order_id] = escrow_id
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return escrow
    
    async def release_to_provider(self, escrow_id: str) -> bool:
        """Release escrowed funds to provider"""
        async with self._lock:
            if escrow_id not in self._escrows:
                return False
            
            escrow = self._escrows[escrow_id]
            
            if escrow.status != EscrowStatus.PENDING:
                return False
            
            escrow.status = EscrowStatus.RELEASED
            escrow.released_at = datetime.utcnow()
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def refund_to_buyer(self, escrow_id: str) -> bool:
        """Refund escrowed funds to buyer"""
        async with self._lock:
            if escrow_id not in self._escrows:
                return False
            
            escrow = self._escrows[escrow_id]
            
            if escrow.status != EscrowStatus.PENDING:
                return False
            
            escrow.status = EscrowStatus.REFUNDED
            escrow.refunded_at = datetime.utcnow()
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def open_dispute(self, escrow_id: str, reason: str) -> bool:
        """Open dispute for an escrow"""
        async with self._lock:
            if escrow_id not in self._escrows:
                return False
            
            escrow = self._escrows[escrow_id]
            
            if escrow.status != EscrowStatus.PENDING:
                return False
            
            escrow.status = EscrowStatus.DISPUTED
            escrow.dispute_reason = reason
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def resolve_dispute(
        self,
        escrow_id: str,
        release_to_provider: bool,
        resolution_note: str
    ) -> bool:
        """Resolve a disputed escrow"""
        async with self._lock:
            if escrow_id not in self._escrows:
                return False
            
            escrow = self._escrows[escrow_id]
            
            if escrow.status != EscrowStatus.DISPUTED:
                return False
            
            if release_to_provider:
                escrow.status = EscrowStatus.RELEASED
                escrow.released_at = datetime.utcnow()
            else:
                escrow.status = EscrowStatus.REFUNDED
                escrow.refunded_at = datetime.utcnow()
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def get_escrow(self, escrow_id: str) -> Optional[Escrow]:
        """Get escrow by ID"""
        async with self._lock:
            return self._escrows.get(escrow_id)
    
    async def get_escrow_by_order(self, order_id: str) -> Optional[Escrow]:
        """Get escrow for an order"""
        async with self._lock:
            escrow_id = self._order_escrow.get(order_id)
            if escrow_id:
                return self._escrows.get(escrow_id)
            return None
    
    async def get_pending_escrows(self) -> List[Escrow]:
        """Get all pending escrows"""
        async with self._lock:
            return [
                e for e in self._escrows.values()
                if e.status == EscrowStatus.PENDING
            ]
    
    async def cleanup_expired(self) -> int:
        """Mark expired escrows"""
        async with self._lock:
            now = datetime.utcnow()
            expired = []
            
            for escrow in self._escrows.values():
                if escrow.status == EscrowStatus.PENDING and now > escrow.expires_at:
                    expired.append(escrow.escrow_id)
            
            for eid in expired:
                self._escrows[eid].status = EscrowStatus.EXPIRED
            
            if expired and self._storage_path:
                await self._save_to_storage()
            
            return len(expired)
    
    async def _save_to_storage(self):
        """Save escrows to file"""
        data = {
            'escrows': {k: v.to_dict() for k, v in self._escrows.items()},
            'order_escrow': self._order_escrow,
            'version': '1.0',
            'updated_at': datetime.utcnow().isoformat()
        }
        
        temp_path = self._storage_path + '.tmp'
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        import os
        os.replace(temp_path, self._storage_path)
    
    def _load_from_storage(self):
        """Load escrows from file"""
        try:
            with open(self._storage_path, 'r') as f:
                data = json.load(f)
            
            for eid, escrow_data in data.get('escrows', {}).items():
                escrow = Escrow(
                    escrow_id=escrow_data['escrow_id'],
                    order_id=escrow_data['order_id'],
                    buyer_id=escrow_data['buyer_id'],
                    provider_id=escrow_data['provider_id'],
                    amount=Decimal(escrow_data['amount']),
                    status=EscrowStatus(escrow_data['status']),
                    created_at=datetime.fromisoformat(escrow_data['created_at']),
                    expires_at=datetime.fromisoformat(escrow_data['expires_at']),
                    released_at=datetime.fromisoformat(escrow_data['released_at']) if escrow_data.get('released_at') else None,
                    refunded_at=datetime.fromisoformat(escrow_data['refunded_at']) if escrow_data.get('refunded_at') else None,
                    dispute_reason=escrow_data.get('dispute_reason')
                )
                self._escrows[eid] = escrow
            
            self._order_escrow = data.get('order_escrow', {})
            
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading escrows: {e}")
    
    async def get_stats(self) -> dict:
        """Get escrow statistics"""
        async with self._lock:
            status_counts = {}
            total_locked = Decimal('0')
            total_released = Decimal('0')
            total_refunded = Decimal('0')
            
            for escrow in self._escrows.values():
                status_counts[escrow.status.value] = status_counts.get(escrow.status.value, 0) + 1
                
                if escrow.status == EscrowStatus.PENDING:
                    total_locked += escrow.amount
                elif escrow.status == EscrowStatus.RELEASED:
                    total_released += escrow.amount
                elif escrow.status == EscrowStatus.REFUNDED:
                    total_refunded += escrow.amount
            
            return {
                'total_escrows': len(self._escrows),
                'status_breakdown': status_counts,
                'total_locked': str(total_locked),
                'total_released': str(total_released),
                'total_refunded': str(total_refunded)
            }
