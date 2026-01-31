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


class OrderStatus(Enum):
    PENDING = "pending"
    MATCHED = "matched"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


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
    
    async def complete_order(self, order_id: str) -> bool:
        """Mark order as completed"""
        async with self._lock:
            if order_id not in self._orders:
                return False
            
            order = self._orders[order_id]
            
            if order.status != OrderStatus.IN_PROGRESS:
                return False
            
            order.status = OrderStatus.COMPLETED
            order.completed_at = datetime.utcnow()
            
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
        data = {
            'orders': {k: v.to_dict() for k, v in self._orders.items()},
            'version': '1.0',
            'updated_at': datetime.utcnow().isoformat()
        }
        
        temp_path = self._storage_path + '.tmp'
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        import os
        os.replace(temp_path, self._storage_path)
    
    def _load_from_storage(self):
        """Load order book from file"""
        try:
            with open(self._storage_path, 'r') as f:
                data = json.load(f)
            
            for oid, order_data in data.get('orders', {}).items():
                order = ServiceOrder.from_dict(order_data)
                self._orders[oid] = order
                
                # Rebuild indexes
                self._buyer_orders.setdefault(order.buyer_id, set()).add(oid)
                self._service_orders.setdefault(order.service_id, set()).add(oid)
                
                if order.status == OrderStatus.PENDING:
                    self._pending_orders.add(oid)
                    
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading order book: {e}")
    
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
