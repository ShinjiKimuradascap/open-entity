#!/usr/bin/env python3
"""
Order Book for AI Multi-Agent Marketplace

Manages service orders and matching.
"""

import uuid
import json
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Callable
from enum import Enum
from pathlib import Path

# Token system imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from token_system import load_wallet, get_wallet, save_wallet


class OrderStatus(Enum):
    PENDING = "pending"
    MATCHED = "matched"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"  # Provider submitted result, waiting for buyer approval
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"  # Buyer rejected result


class OrderSide(Enum):
    BUY = "buy"   # Consumer wants to buy service
    SELL = "sell"  # Provider wants to sell service


@dataclass
class ServiceOrder:
    """Service order information"""
    order_id: str
    buyer_id: str
    service_id: str
    provider_id: Optional[str]  # Filled when matched
    quantity: int
    price_per_unit: Decimal
    total_amount: Decimal
    side: OrderSide
    status: OrderStatus
    requirements: Dict  # Specific requirements for the service
    created_at: datetime
    expires_at: datetime
    matched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    escrow_id: Optional[str] = None  # Reference to escrow
    # Buyer approval flow fields
    result_data: Optional[Dict] = None  # Work result data submitted by provider
    submitted_at: Optional[datetime] = None  # When result was submitted
    reviewed_at: Optional[datetime] = None  # When buyer approved/rejected
    rejection_reason: Optional[str] = None  # Reason for rejection
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        data = asdict(self)
        data['side'] = self.side.value
        data['status'] = self.status.value
        data['price_per_unit'] = str(self.price_per_unit)
        data['total_amount'] = str(self.total_amount)
        data['created_at'] = self.created_at.isoformat()
        data['expires_at'] = self.expires_at.isoformat()
        data['matched_at'] = self.matched_at.isoformat() if self.matched_at else None
        data['completed_at'] = self.completed_at.isoformat() if self.completed_at else None
        data['submitted_at'] = self.submitted_at.isoformat() if self.submitted_at else None
        data['reviewed_at'] = self.reviewed_at.isoformat() if self.reviewed_at else None
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ServiceOrder':
        """Create from dictionary"""
        data = data.copy()
        data['side'] = OrderSide(data['side'])
        data['status'] = OrderStatus(data['status'])
        data['price_per_unit'] = Decimal(data['price_per_unit'])
        data['total_amount'] = Decimal(data['total_amount'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['expires_at'] = datetime.fromisoformat(data['expires_at'])
        data['matched_at'] = datetime.fromisoformat(data['matched_at']) if data.get('matched_at') else None
        data['completed_at'] = datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None
        data['submitted_at'] = datetime.fromisoformat(data['submitted_at']) if data.get('submitted_at') else None
        data['reviewed_at'] = datetime.fromisoformat(data['reviewed_at']) if data.get('reviewed_at') else None
        # Handle new fields for backwards compatibility
        if 'result_data' not in data:
            data['result_data'] = None
        if 'rejection_reason' not in data:
            data['rejection_reason'] = None
        return cls(**data)


@dataclass
class MatchResult:
    """Order matching result"""
    success: bool
    order_id: str
    matched_provider_id: Optional[str] = None
    escrow_id: Optional[str] = None
    message: str = ""


class OrderBook:
    """Order book for service marketplace"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self._orders: Dict[str, ServiceOrder] = {}
        self._buyer_orders: Dict[str, Set[str]] = {}
        self._service_orders: Dict[str, Set[str]] = {}
        self._pending_orders: Set[str] = set()
        self._storage_path = storage_path
        self._lock = asyncio.Lock()
        self._match_callbacks: List[Callable] = []
        
        if storage_path:
            self._load_from_storage()
    
    async def create_order(
        self,
        buyer_id: str,
        service_id: str,
        quantity: int,
        max_price: Decimal,
        requirements: Optional[Dict] = None,
        expiry_hours: int = 24
    ) -> Optional[ServiceOrder]:
        """Create a new buy order"""
        async with self._lock:
            order_id = str(uuid.uuid4())
            
            order = ServiceOrder(
                order_id=order_id,
                buyer_id=buyer_id,
                service_id=service_id,
                provider_id=None,
                quantity=quantity,
                price_per_unit=max_price,
                total_amount=max_price * quantity,
                side=OrderSide.BUY,
                status=OrderStatus.PENDING,
                requirements=requirements or {},
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=expiry_hours)
            )
            
            self._orders[order_id] = order
            self._buyer_orders.setdefault(buyer_id, set()).add(order_id)
            self._service_orders.setdefault(service_id, set()).add(order_id)
            self._pending_orders.add(order_id)
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return order
    
    async def match_order(
        self,
        order_id: str,
        provider_id: str,
        escrow_id: Optional[str] = None
    ) -> MatchResult:
        """Match a pending order with a provider"""
        async with self._lock:
            if order_id not in self._orders:
                return MatchResult(False, order_id, message="Order not found")
            
            order = self._orders[order_id]
            
            if order.status != OrderStatus.PENDING:
                return MatchResult(False, order_id, message=f"Order not pending (status: {order.status.value})")
            
            if datetime.utcnow() > order.expires_at:
                order.status = OrderStatus.CANCELLED
                self._pending_orders.discard(order_id)
                return MatchResult(False, order_id, message="Order expired")
            
            # Update order
            order.provider_id = provider_id
            order.status = OrderStatus.MATCHED
            order.matched_at = datetime.utcnow()
            order.escrow_id = escrow_id
            
            self._pending_orders.discard(order_id)
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            # Notify callbacks
            for callback in self._match_callbacks:
                try:
                    await callback(order)
                except Exception:
                    pass
            
            return MatchResult(
                True, 
                order_id, 
                matched_provider_id=provider_id,
                escrow_id=escrow_id,
                message="Order matched successfully"
            )
    
    async def cancel_order(self, order_id: str, buyer_id: str) -> bool:
        """Cancel a pending order (only by buyer)"""
        async with self._lock:
            if order_id not in self._orders:
                return False
            
            order = self._orders[order_id]
            
            if order.buyer_id != buyer_id:
                return False  # Not authorized
            
            if order.status not in [OrderStatus.PENDING, OrderStatus.MATCHED]:
                return False  # Cannot cancel
            
            order.status = OrderStatus.CANCELLED
            self._pending_orders.discard(order_id)
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def start_order(self, order_id: str, provider_id: str) -> bool:
        """Provider starts work on a matched order - changes status from MATCHED to IN_PROGRESS"""
        async with self._lock:
            if order_id not in self._orders:
                return False
            
            order = self._orders[order_id]
            
            # Verify provider
            if order.provider_id != provider_id:
                return False
            
            if order.status != OrderStatus.MATCHED:
                return False
            
            order.status = OrderStatus.IN_PROGRESS
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def submit_result(self, order_id: str, provider_id: str, result_data: Dict) -> bool:
        """Provider submits work result for buyer review"""
        async with self._lock:
            if order_id not in self._orders:
                return False
            
            order = self._orders[order_id]
            
            # Verify provider
            if order.provider_id != provider_id:
                return False
            
            if order.status != OrderStatus.IN_PROGRESS:
                return False
            
            order.result_data = result_data
            order.submitted_at = datetime.utcnow()
            order.status = OrderStatus.PENDING_REVIEW
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def approve_order(self, order_id: str, buyer_id: str) -> bool:
        """Buyer approves submitted result - completes order and releases payment"""
        async with self._lock:
            if order_id not in self._orders:
                print(f"[approve_order] Order not found: {order_id}")
                return False
            
            order = self._orders[order_id]
            
            # Verify buyer
            if order.buyer_id != buyer_id:
                print(f"[approve_order] Buyer mismatch: order.buyer_id={order.buyer_id}, provided={buyer_id}")
                return False
            
            if order.status != OrderStatus.PENDING_REVIEW:
                print(f"[approve_order] Status mismatch: status={order.status.value}, expected=pending_review")
                return False
            
            # Token transfer: buyer -> provider
            if order.provider_id:
                data_dir = Path("/home/moco/workspace/data/token_system/wallets")
                
                # Load buyer wallet
                buyer_wallet = load_wallet(order.buyer_id, data_dir)
                if not buyer_wallet:
                    # Try to get from registry if already loaded
                    buyer_wallet = get_wallet(order.buyer_id)
                    if not buyer_wallet:
                        print(f"[approve_order] Buyer wallet not found: {order.buyer_id}")
                        return False
                
                # Load provider wallet
                provider_wallet = load_wallet(order.provider_id, data_dir)
                if not provider_wallet:
                    # Try to get from registry if already loaded
                    provider_wallet = get_wallet(order.provider_id)
                    if not provider_wallet:
                        print(f"[approve_order] Provider wallet not found: {order.provider_id}")
                        return False
                
                # Convert Decimal to float for transfer
                amount = float(order.total_amount)
                
                # Check buyer balance
                buyer_balance = buyer_wallet.get_balance()
                if buyer_balance < amount:
                    print(f"[approve_order] Insufficient balance: buyer {order.buyer_id} has {buyer_balance}, needs {amount}")
                    return False
                
                # Execute transfer
                transfer_success = buyer_wallet.transfer(
                    provider_wallet, 
                    amount,
                    description=f"Payment for order {order_id}"
                )
                
                if not transfer_success:
                    print(f"[approve_order] Token transfer failed for order {order_id}")
                    return False
                
                # Save wallets
                save_wallet(order.buyer_id, data_dir)
                save_wallet(order.provider_id, data_dir)
                
                print(f"[approve_order] Token transfer successful: {amount} AIC from {order.buyer_id} to {order.provider_id}")
            
            order.status = OrderStatus.COMPLETED
            order.completed_at = datetime.utcnow()
            order.reviewed_at = datetime.utcnow()
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def reject_order(self, order_id: str, buyer_id: str, reason: str) -> bool:
        """Buyer rejects submitted result - enters dispute"""
        async with self._lock:
            if order_id not in self._orders:
                return False
            
            order = self._orders[order_id]
            
            # Verify buyer
            if order.buyer_id != buyer_id:
                return False
            
            if order.status != OrderStatus.PENDING_REVIEW:
                return False
            
            order.status = OrderStatus.DISPUTED
            order.rejection_reason = reason
            order.reviewed_at = datetime.utcnow()
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def get_result(self, order_id: str, user_id: str) -> Optional[Dict]:
        """Get submitted result (available to both buyer and provider)"""
        async with self._lock:
            if order_id not in self._orders:
                return None
            
            order = self._orders[order_id]
            
            # Verify user is either buyer or provider
            if order.buyer_id != user_id and order.provider_id != user_id:
                return None
            
            # Result only available after submission
            if order.status not in [OrderStatus.PENDING_REVIEW, OrderStatus.COMPLETED, OrderStatus.DISPUTED]:
                return None
            
            return {
                'result_data': order.result_data,
                'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                'status': order.status.value
            }
    
    async def complete_order(self, order_id: str, result_data: Optional[Dict] = None) -> bool:
        """[DEPRECATED] Use submit_result instead.
        Mark order as pending review with result data."""
        async with self._lock:
            if order_id not in self._orders:
                return False
            
            order = self._orders[order_id]
            
            if order.status != OrderStatus.IN_PROGRESS:
                return False
            
            # Now sets PENDING_REVIEW instead of COMPLETED
            order.status = OrderStatus.PENDING_REVIEW
            if result_data:
                order.result_data = result_data
            order.submitted_at = datetime.utcnow()
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def start_service(self, order_id: str) -> bool:
        """Mark order as in progress (service started)"""
        async with self._lock:
            if order_id not in self._orders:
                return False
            
            order = self._orders[order_id]
            
            if order.status != OrderStatus.MATCHED:
                return False
            
            order.status = OrderStatus.IN_PROGRESS
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def get_order(self, order_id: str) -> Optional[ServiceOrder]:
        """Get order by ID"""
        async with self._lock:
            return self._orders.get(order_id)
    
    async def get_buyer_orders(self, buyer_id: str, status: Optional[OrderStatus] = None) -> List[ServiceOrder]:
        """Get all orders for a buyer"""
        async with self._lock:
            order_ids = self._buyer_orders.get(buyer_id, set())
            orders = [self._orders[oid] for oid in order_ids if oid in self._orders]
            
            if status:
                orders = [o for o in orders if o.status == status]
            
            return sorted(orders, key=lambda x: x.created_at, reverse=True)
    
    async def get_pending_orders(self, service_id: Optional[str] = None) -> List[ServiceOrder]:
        """Get pending orders (optionally filtered by service)"""
        async with self._lock:
            pending = [self._orders[oid] for oid in self._pending_orders if oid in self._orders]
            
            if service_id:
                pending = [o for o in pending if o.service_id == service_id]
            
            # Remove expired
            now = datetime.utcnow()
            valid_pending = []
            for order in pending:
                if now > order.expires_at:
                    order.status = OrderStatus.CANCELLED
                    self._pending_orders.discard(order.order_id)
                else:
                    valid_pending.append(order)
            
            return sorted(valid_pending, key=lambda x: x.total_amount, reverse=True)
    
    async def cleanup_expired(self) -> int:
        """Clean up expired pending orders"""
        async with self._lock:
            now = datetime.utcnow()
            expired = []
            
            for oid in self._pending_orders:
                if oid in self._orders:
                    order = self._orders[oid]
                    if now > order.expires_at:
                        expired.append(oid)
            
            for oid in expired:
                self._orders[oid].status = OrderStatus.CANCELLED
                self._pending_orders.discard(oid)
            
            if expired and self._storage_path:
                await self._save_to_storage()
            
            return len(expired)
    
    def on_match(self, callback: Callable):
        """Register callback for order match events"""
        self._match_callbacks.append(callback)
    
    async def _save_to_storage(self):
        """Save order book to file"""
        import os
        data = {
            'orders': {k: v.to_dict() for k, v in self._orders.items()},
            'version': '1.0',
            'updated_at': datetime.utcnow().isoformat()
        }
        
        try:
            # Ensure directory exists
            storage_dir = os.path.dirname(self._storage_path)
            if storage_dir and not os.path.exists(storage_dir):
                os.makedirs(storage_dir, exist_ok=True)
                print(f"[_save_to_storage] Created directory: {storage_dir}")
            
            temp_path = self._storage_path + '.tmp'
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            os.replace(temp_path, self._storage_path)
            print(f"[_save_to_storage] Saved {len(self._orders)} orders to {self._storage_path}")
        except Exception as e:
            print(f"[_save_to_storage] ERROR: {e}")
            raise
    
    def _load_from_storage(self):
        """Load order book from file"""
        import os
        try:
            abs_path = os.path.abspath(self._storage_path)
            print(f"[_load_from_storage] Loading from: {abs_path}")
            
            with open(self._storage_path, 'r') as f:
                data = json.load(f)
            
            order_count = 0
            for oid, order_data in data.get('orders', {}).items():
                order = ServiceOrder.from_dict(order_data)
                self._orders[oid] = order
                
                # Rebuild indexes
                self._buyer_orders.setdefault(order.buyer_id, set()).add(oid)
                self._service_orders.setdefault(order.service_id, set()).add(oid)
                
                if order.status == OrderStatus.PENDING:
                    self._pending_orders.add(oid)
                order_count += 1
            
            print(f"[_load_from_storage] Loaded {order_count} orders from {self._storage_path}")
                    
        except FileNotFoundError:
            print(f"[_load_from_storage] File not found: {self._storage_path}")
        except Exception as e:
            print(f"[_load_from_storage] ERROR: {e}")
    
    async def get_stats(self) -> dict:
        """Get order book statistics"""
        async with self._lock:
            status_counts = {}
            for order in self._orders.values():
                status_counts[order.status.value] = status_counts.get(order.status.value, 0) + 1
            
            return {
                'total_orders': len(self._orders),
                'pending_orders': len(self._pending_orders),
                'status_breakdown': status_counts,
                'total_volume': sum(o.total_amount for o in self._orders.values() if o.status == OrderStatus.COMPLETED)
            }
