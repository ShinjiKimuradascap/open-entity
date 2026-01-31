#!/usr/bin/env python3
"""
Service Registry for AI Multi-Agent Marketplace

Manages service listings, search, and provider reputation.
"""

import json
import hashlib
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Callable
from enum import Enum


class ServiceType(Enum):
    COMPUTE = "compute"
    STORAGE = "storage"
    DATA = "data"
    ANALYSIS = "analysis"
    LLM = "llm"
    VISION = "vision"
    AUDIO = "audio"


class PricingModel(Enum):
    PER_REQUEST = "per_request"
    PER_HOUR = "per_hour"
    PER_GB = "per_gb"
    FIXED = "fixed"


@dataclass
class ServiceListing:
    """Service listing information"""
    service_id: str
    provider_id: str
    service_type: ServiceType
    description: str
    pricing_model: PricingModel
    price: Decimal
    capabilities: List[str]
    endpoint: str
    terms_hash: str
    reputation_score: float = 0.0
    total_reviews: int = 0
    successful_transactions: int = 0
    created_at: datetime = None
    updated_at: datetime = None
    is_active: bool = True
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        data = asdict(self)
        data['service_type'] = self.service_type.value
        data['pricing_model'] = self.pricing_model.value
        data['price'] = str(self.price)
        data['created_at'] = self.created_at.isoformat() if self.created_at else None
        data['updated_at'] = self.updated_at.isoformat() if self.updated_at else None
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ServiceListing':
        """Create from dictionary"""
        data = data.copy()
        data['service_type'] = ServiceType(data['service_type'])
        data['pricing_model'] = PricingModel(data['pricing_model'])
        data['price'] = Decimal(data['price'])
        data['created_at'] = datetime.fromisoformat(data['created_at']) if data.get('created_at') else None
        data['updated_at'] = datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None
        return cls(**data)
    
    def compute_hash(self) -> str:
        """Compute listing hash for integrity"""
        data = f"{self.service_id}:{self.provider_id}:{self.price}:{self.terms_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


class ServiceRegistry:
    """Central registry for AI services"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self._listings: Dict[str, ServiceListing] = {}
        self._provider_services: Dict[str, Set[str]] = {}
        self._type_index: Dict[ServiceType, Set[str]] = {t: set() for t in ServiceType}
        self._capability_index: Dict[str, Set[str]] = {}
        self._storage_path = storage_path
        self._lock = asyncio.Lock()
        
        if storage_path:
            self._load_from_storage()
    
    async def register_service(self, listing: ServiceListing) -> bool:
        """Register a new service listing"""
        async with self._lock:
            # Validate listing
            if not self._validate_listing(listing):
                return False
            
            # Check if service already exists
            if listing.service_id in self._listings:
                # Update existing
                listing.updated_at = datetime.utcnow()
            
            # Store listing
            self._listings[listing.service_id] = listing
            
            # Update indexes
            self._provider_services.setdefault(listing.provider_id, set()).add(listing.service_id)
            self._type_index[listing.service_type].add(listing.service_id)
            
            for cap in listing.capabilities:
                self._capability_index.setdefault(cap, set()).add(listing.service_id)
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def unregister_service(self, service_id: str, provider_id: str) -> bool:
        """Unregister a service (only by provider)"""
        async with self._lock:
            if service_id not in self._listings:
                return False
            
            listing = self._listings[service_id]
            if listing.provider_id != provider_id:
                return False  # Not authorized
            
            # Remove from indexes
            self._provider_services[provider_id].discard(service_id)
            self._type_index[listing.service_type].discard(service_id)
            
            for cap in listing.capabilities:
                self._capability_index.get(cap, set()).discard(service_id)
            
            # Remove listing
            del self._listings[service_id]
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def get_service(self, service_id: str) -> Optional[ServiceListing]:
        """Get a specific service listing"""
        async with self._lock:
            return self._listings.get(service_id)
    
    async def search_services(
        self,
        service_type: Optional[ServiceType] = None,
        capabilities: Optional[List[str]] = None,
        min_reputation: float = 0.0,
        max_price: Optional[Decimal] = None,
        limit: int = 100
    ) -> List[ServiceListing]:
        """Search for services matching criteria"""
        async with self._lock:
            candidates = set(self._listings.keys())
            
            # Filter by type
            if service_type:
                candidates &= self._type_index.get(service_type, set())
            
            # Filter by capabilities (must have all)
            if capabilities:
                for cap in capabilities:
                    candidates &= self._capability_index.get(cap, set())
            
            # Get listings and apply remaining filters
            results = []
            for sid in candidates:
                listing = self._listings[sid]
                
                if not listing.is_active:
                    continue
                if listing.reputation_score < min_reputation:
                    continue
                if max_price and listing.price > max_price:
                    continue
                
                results.append(listing)
            
            # Sort by reputation (descending), then price (ascending)
            results.sort(key=lambda x: (-x.reputation_score, x.price))
            
            return results[:limit]
    
    async def update_reputation(
        self,
        service_id: str,
        rating: float,
        transaction_success: bool
    ) -> bool:
        """Update service reputation after transaction"""
        async with self._lock:
            if service_id not in self._listings:
                return False
            
            listing = self._listings[service_id]
            
            # Update review count
            listing.total_reviews += 1
            
            # Update reputation score (weighted average)
            alpha = 0.1  # Learning rate
            listing.reputation_score = (
                (1 - alpha) * listing.reputation_score + alpha * rating
            )
            
            # Update transaction count
            if transaction_success:
                listing.successful_transactions += 1
            
            listing.updated_at = datetime.utcnow()
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
    async def get_provider_services(self, provider_id: str) -> List[ServiceListing]:
        """Get all services by a provider"""
        async with self._lock:
            service_ids = self._provider_services.get(provider_id, set())
            return [self._listings[sid] for sid in service_ids if sid in self._listings]
    
    def _validate_listing(self, listing: ServiceListing) -> bool:
        """Validate service listing"""
        if not listing.service_id or not listing.provider_id:
            return False
        if listing.price < 0:
            return False
        if not listing.endpoint:
            return False
        if listing.reputation_score < 0 or listing.reputation_score > 5:
            return False
        return True
    
    async def _save_to_storage(self):
        """Save registry to file"""
        data = {
            'listings': {k: v.to_dict() for k, v in self._listings.items()},
            'version': '1.0',
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Use temp file for atomic write
        temp_path = self._storage_path + '.tmp'
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        import os
        os.replace(temp_path, self._storage_path)
    
    def _load_from_storage(self):
        """Load registry from file"""
        try:
            with open(self._storage_path, 'r') as f:
                data = json.load(f)
            
            for sid, listing_data in data.get('listings', {}).items():
                listing = ServiceListing.from_dict(listing_data)
                self._listings[sid] = listing
                
                # Rebuild indexes
                self._provider_services.setdefault(listing.provider_id, set()).add(sid)
                self._type_index[listing.service_type].add(sid)
                for cap in listing.capabilities:
                    self._capability_index.setdefault(cap, set()).add(sid)
                    
        except FileNotFoundError:
            pass  # No existing data
        except Exception as e:
            print(f"Error loading registry: {e}")
    
    async def get_stats(self) -> dict:
        """Get registry statistics"""
        async with self._lock:
            return {
                'total_services': len(self._listings),
                'active_services': sum(1 for l in self._listings.values() if l.is_active),
                'total_providers': len(self._provider_services),
                'by_type': {
                    t.value: len(sids) 
                    for t, sids in self._type_index.items()
                },
                'avg_reputation': (
                    sum(l.reputation_score for l in self._listings.values()) / len(self._listings)
                    if self._listings else 0.0
                )
            }


# Convenience functions for async usage
async def create_registry(storage_path: Optional[str] = None) -> ServiceRegistry:
    """Create a new service registry"""
    return ServiceRegistry(storage_path)
