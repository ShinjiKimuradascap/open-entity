#!/usr/bin/env python3
"""Marketplace Service - v1.3 Multi-Agent Service Marketplace"""

from typing import Dict, List, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json


@dataclass
class PricingModel:
    type: Literal["fixed", "per_token", "auction", "dynamic"]
    amount: float
    currency: str = "AIC"
    min_bid: Optional[float] = None
    max_bid: Optional[float] = None


@dataclass
class AvailabilityInfo:
    status: Literal["available", "busy", "offline"]
    max_concurrent: int = 1
    current_load: int = 0
    avg_response_time_ms: int = 0


@dataclass
class RatingStats:
    average: float = 0.0
    count: int = 0
    distribution: Dict[int, int] = field(default_factory=dict)


@dataclass
class ServiceRecord:
    service_id: str
    provider_id: str
    name: str
    description: str
    category: str
    tags: List[str]
    capabilities: List[str]
    pricing: PricingModel
    endpoint: str
    availability: AvailabilityInfo
    rating_stats: RatingStats
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    verification_status: Literal["pending", "verified", "rejected"] = "pending"
    input_schema: Optional[Dict] = None
    output_schema: Optional[Dict] = None


@dataclass
class ServiceInvocation:
    invocation_id: str
    service_id: str
    requester_id: str
    provider_id: str
    input_data: Dict
    status: Literal["pending", "in_progress", "completed", "failed", "disputed"]
    escrow_amount: float
    created_at: datetime
    output_data: Optional[Dict] = None
    completed_at: Optional[datetime] = None


class MarketplaceRegistry:
    """Registry for marketplace services"""
    
    def __init__(self):
        self._services: Dict[str, ServiceRecord] = {}
        self._invocations: Dict[str, ServiceInvocation] = {}
        self._provider_services: Dict[str, List[str]] = {}
        
    def register_service(self, record: ServiceRecord) -> bool:
        """Register a new service"""
        self._services[record.service_id] = record
        
        # Track provider services
        if record.provider_id not in self._provider_services:
            self._provider_services[record.provider_id] = []
        if record.service_id not in self._provider_services[record.provider_id]:
            self._provider_services[record.provider_id].append(record.service_id)
        
        return True
    
    def get_service(self, service_id: str) -> Optional[ServiceRecord]:
        """Get service by ID"""
        return self._services.get(service_id)
    
    def search_services(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_rating: Optional[float] = None,
        max_price: Optional[float] = None,
        available_only: bool = True,
        limit: int = 20,
        offset: int = 0
    ) -> List[ServiceRecord]:
        """Search services with filters"""
        results = []
        
        for service in self._services.values():
            # Filter by category
            if category and service.category != category:
                continue
            
            # Filter by tags
            if tags and not any(tag in service.tags for tag in tags):
                continue
            
            # Filter by rating
            if min_rating and service.rating_stats.average < min_rating:
                continue
            
            # Filter by price
            if max_price and service.pricing.amount > max_price:
                continue
            
            # Filter by availability
            if available_only and service.availability.status != "available":
                continue
            
            results.append(service)
        
        # Sort by rating
        results.sort(key=lambda s: s.rating_stats.average, reverse=True)
        
        # Pagination
        return results[offset:offset + limit]
    
    def get_provider_services(self, provider_id: str) -> List[ServiceRecord]:
        """Get all services by provider"""
        service_ids = self._provider_services.get(provider_id, [])
        return [self._services[sid] for sid in service_ids if sid in self._services]
    
    def update_availability(
        self,
        service_id: str,
        status: Literal["available", "busy", "offline"]
    ) -> bool:
        """Update service availability"""
        if service_id in self._services:
            self._services[service_id].availability.status = status
            self._services[service_id].updated_at = datetime.now(timezone.utc)
            return True
        return False
    
    def create_invocation(self, invocation: ServiceInvocation) -> bool:
        """Create a service invocation"""
        self._invocations[invocation.invocation_id] = invocation
        return True
    
    def get_invocation(self, invocation_id: str) -> Optional[ServiceInvocation]:
        """Get invocation by ID"""
        return self._invocations.get(invocation_id)
    
    def list_all(self) -> List[ServiceRecord]:
        """List all services"""
        return list(self._services.values())


# Backwards compatibility aliases
ServiceRegistry = MarketplaceRegistry
ServiceListing = ServiceRecord
ServiceType = str

# Singleton instance
_marketplace = MarketplaceRegistry()


def get_marketplace() -> MarketplaceRegistry:
    return _marketplace


# Backwards compatibility
def get_registry():
    return _marketplace


if __name__ == "__main__":
    mp = get_marketplace()
    
    # Create sample service
    service = ServiceRecord(
        service_id="code-review-001",
        provider_id="agent-1",
        name="Python Code Review",
        description="AI-powered Python code review",
        category="development",
        tags=["code_review", "python"],
        capabilities=["static_analysis"],
        pricing=PricingModel(type="fixed", amount=50),
        endpoint="http://localhost:8001/review",
        availability=AvailabilityInfo(status="available", max_concurrent=5),
        rating_stats=RatingStats(average=4.8, count=127)
    )
    
    mp.register_service(service)
    print(f"Registered {len(mp.list_all())} services")
    
    # Search
    results = mp.search_services(category="development")
    print(f"Found {len(results)} development services")
