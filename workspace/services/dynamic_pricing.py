#!/usr/bin/env python3
"""
Dynamic Pricing System for AI Service Marketplace
Implements demand-based pricing, auctions, and bundle discounts
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, List, Callable
from decimal import Decimal
import threading
import math


@dataclass
class PricingConfig:
    """Configuration for dynamic pricing"""
    base_price: Decimal = Decimal("1.0")
    min_price: Decimal = Decimal("0.1")
    max_price: Decimal = Decimal("100.0")
    demand_multiplier: float = 1.5  # Price multiplier at max demand
    smoothing_factor: float = 0.1   # EMA smoothing
    

@dataclass
class ServiceDemand:
    """Tracks demand for a service"""
    service_id: str
    request_count: int = 0
    last_request_time: Optional[datetime] = None
    price_history: List[Decimal] = field(default_factory=list)
    current_price: Decimal = Decimal("1.0")
    
    def record_request(self):
        """Record a service request"""
        self.request_count += 1
        self.last_request_time = datetime.now(timezone.utc)
    
    def update_price(self, new_price: Decimal):
        """Update price with smoothing"""
        self.price_history.append(self.current_price)
        if len(self.price_history) > 100:
            self.price_history.pop(0)
        self.current_price = new_price


class DynamicPricingEngine:
    """
    Dynamic pricing engine for AI services
    
    Features:
    - Demand-based pricing
    - Time-based pricing
    - Auction mechanism
    - Bundle discounts
    """
    
    def __init__(self, config: Optional[PricingConfig] = None):
        self.config = config or PricingConfig()
        self._demand_data: Dict[str, ServiceDemand] = {}
        self._auctions: Dict[str, 'Auction'] = {}
        self._lock = threading.Lock()
    
    def calculate_price(
        self,
        service_id: str,
        base_price: Decimal,
        demand_score: float = 0.0
    ) -> Decimal:
        """
        Calculate dynamic price based on demand
        
        Args:
            service_id: Service identifier
            base_price: Base price for the service
            demand_score: 0.0 to 1.0 demand intensity
            
        Returns:
            Adjusted price
        """
        with self._lock:
            # Get or create demand tracking
            if service_id not in self._demand_data:
                self._demand_data[service_id] = ServiceDemand(
                    service_id=service_id,
                    current_price=base_price
                )
            
            demand = self._demand_data[service_id]
            demand.record_request()
            
            # Calculate price multiplier based on demand
            # Linear interpolation: base -> base * multiplier
            multiplier = 1.0 + (demand_score * (self.config.demand_multiplier - 1.0))
            
            # Apply smoothing with previous price
            raw_price = base_price * Decimal(str(multiplier))
            smoothed_price = (
                demand.current_price * Decimal(str(self.config.smoothing_factor)) +
                raw_price * Decimal(str(1 - self.config.smoothing_factor))
            )
            
            # Enforce bounds
            final_price = max(
                self.config.min_price,
                min(self.config.max_price, smoothed_price)
            )
            
            demand.update_price(final_price)
            return final_price
    
    def get_bundle_discount(
        self,
        service_ids: List[str],
        individual_prices: List[Decimal]
    ) -> Decimal:
        """
        Calculate bundle discount
        
        Args:
            service_ids: List of services in bundle
            individual_prices: Individual prices for each service
            
        Returns:
            Discounted total price
        """
        total = sum(individual_prices, Decimal("0"))
        
        # Discount tiers based on bundle size
        if len(service_ids) >= 10:
            discount = Decimal("0.25")  # 25% off
        elif len(service_ids) >= 5:
            discount = Decimal("0.15")  # 15% off
        elif len(service_ids) >= 3:
            discount = Decimal("0.10")  # 10% off
        else:
            discount = Decimal("0")
        
        return total * (Decimal("1") - discount)
    
    def start_auction(
        self,
        auction_id: str,
        service_id: str,
        starting_price: Decimal,
        duration_seconds: int = 300
    ) -> Dict:
        """
        Start a new auction
        
        Args:
            auction_id: Unique auction identifier
            service_id: Service being auctioned
            starting_price: Initial bid price
            duration_seconds: Auction duration
            
        Returns:
            Auction details
        """
        with self._lock:
            auction = Auction(
                auction_id=auction_id,
                service_id=service_id,
                starting_price=starting_price,
                end_time=datetime.now(timezone.utc).timestamp() + duration_seconds
            )
            self._auctions[auction_id] = auction
            return auction.to_dict()
    
    def place_bid(
        self,
        auction_id: str,
        bidder_id: str,
        amount: Decimal
    ) -> Dict:
        """Place a bid on an auction"""
        with self._lock:
            if auction_id not in self._auctions:
                return {"success": False, "error": "Auction not found"}
            
            auction = self._auctions[auction_id]
            return auction.place_bid(bidder_id, amount)
    
    def get_pricing_stats(self, service_id: str) -> Dict:
        """Get pricing statistics for a service"""
        with self._lock:
            if service_id not in self._demand_data:
                return {"error": "Service not found"}
            
            demand = self._demand_data[service_id]
            return {
                "service_id": service_id,
                "current_price": str(demand.current_price),
                "request_count": demand.request_count,
                "price_history": [str(p) for p in demand.price_history[-10:]],
                "avg_price": str(sum(demand.price_history, Decimal("0")) / len(demand.price_history)) if demand.price_history else str(demand.current_price)
            }


@dataclass
class Auction:
    """Simple ascending auction"""
    auction_id: str
    service_id: str
    starting_price: Decimal
    end_time: float
    bids: List[tuple] = field(default_factory=list)
    highest_bid: Decimal = Decimal("0")
    highest_bidder: Optional[str] = None
    
    def place_bid(self, bidder_id: str, amount: Decimal) -> Dict:
        """Place a bid"""
        current_time = datetime.now(timezone.utc).timestamp()
        
        if current_time > self.end_time:
            return {"success": False, "error": "Auction ended"}
        
        if amount <= self.highest_bid:
            return {"success": False, "error": "Bid too low"}
        
        if amount < self.starting_price:
            return {"success": False, "error": "Bid below starting price"}
        
        self.bids.append((bidder_id, amount, current_time))
        self.highest_bid = amount
        self.highest_bidder = bidder_id
        
        return {
            "success": True,
            "bidder_id": bidder_id,
            "amount": str(amount),
            "is_winning": True
        }
    
    def to_dict(self) -> Dict:
        return {
            "auction_id": self.auction_id,
            "service_id": self.service_id,
            "starting_price": str(self.starting_price),
            "highest_bid": str(self.highest_bid),
            "highest_bidder": self.highest_bidder,
            "bid_count": len(self.bids),
            "ended": datetime.now(timezone.utc).timestamp() > self.end_time
        }


# Global instance
_pricing_engine: Optional[DynamicPricingEngine] = None


def get_pricing_engine() -> DynamicPricingEngine:
    """Get or create global pricing engine"""
    global _pricing_engine
    if _pricing_engine is None:
        _pricing_engine = DynamicPricingEngine()
    return _pricing_engine


if __name__ == "__main__":
    # Demo usage
    engine = DynamicPricingEngine()
    
    # Test dynamic pricing
    price1 = engine.calculate_price("service_1", Decimal("10.0"), demand_score=0.5)
    print(f"Price with 50% demand: {price1}")
    
    price2 = engine.calculate_price("service_1", Decimal("10.0"), demand_score=0.8)
    print(f"Price with 80% demand: {price2}")
    
    # Test bundle discount
    bundle_price = engine.get_bundle_discount(
        ["s1", "s2", "s3", "s4", "s5"],
        [Decimal("10.0")] * 5
    )
    print(f"Bundle price (5 items): {bundle_price}")
    
    # Test auction
    auction = engine.start_auction("auc_1", "service_1", Decimal("5.0"))
    print(f"Auction started: {auction}")
