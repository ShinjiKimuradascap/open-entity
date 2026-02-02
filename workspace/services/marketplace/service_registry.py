#!/usr/bin/env python3
"""
Service Registry for AI Multi-Agent Marketplace

Manages service listings, search, and provider reputation.
Integrated with ReputationEngine for advanced reputation calculation.
"""

import json
import hashlib
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Callable, Any
from enum import Enum

# Import ReputationEngine
try:
    from .reputation_engine import (
        ReputationEngine, ServiceMetrics, RatingEntry
    )
except ImportError:
    from reputation_engine import (
        ReputationEngine, ServiceMetrics, RatingEntry
    )


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
    # Extended metrics for ranking
    completion_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    # v1.3 fields
    tags: List[str] = None
    name: str = ""
    category: str = ""
    currency: str = "AIC"
    input_schema: Optional[Dict] = None
    output_schema: Optional[Dict] = None
    max_concurrent: int = 1
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()
        if self.tags is None:
            self.tags = []
    
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
        # Handle new fields with defaults for backward compatibility
        data.setdefault('completion_rate', 0.0)
        data.setdefault('avg_response_time_ms', 0.0)
        data.setdefault('tags', [])
        data.setdefault('name', '')
        data.setdefault('category', '')
        data.setdefault('currency', 'AIC')
        data.setdefault('input_schema', None)
        data.setdefault('output_schema', None)
        data.setdefault('max_concurrent', 1)
        return cls(**data)
    
    def compute_hash(self) -> str:
        """Compute listing hash for integrity"""
        data = f"{self.service_id}:{self.provider_id}:{self.price}:{self.terms_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


class ServiceRegistry:
    """Central registry for AI services with advanced reputation"""
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        reputation_engine: Optional[ReputationEngine] = None
    ):
        self._listings: Dict[str, ServiceListing] = {}
        self._provider_services: Dict[str, Set[str]] = {}
        self._type_index: Dict[ServiceType, Set[str]] = {t: set() for t in ServiceType}
        self._capability_index: Dict[str, Set[str]] = {}
        self._tag_index: Dict[str, Set[str]] = {}  # v1.3: tags index
        self._storage_path = storage_path
        self._lock = asyncio.Lock()
        
        # Initialize reputation engine
        if reputation_engine:
            self._reputation_engine = reputation_engine
        elif storage_path:
            # Use same directory for reputation storage
            rep_path = storage_path.replace('.json', '_reputation.json')
            self._reputation_engine = ReputationEngine(rep_path)
        else:
            self._reputation_engine = ReputationEngine()
        
        if storage_path:
            self._load_from_storage()
    
    @property
    def reputation_engine(self) -> ReputationEngine:
        """Access the reputation engine"""
        return self._reputation_engine
    
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
            
            # Update tag index (v1.3)
            for tag in listing.tags:
                self._tag_index.setdefault(tag, set()).add(listing.service_id)
            
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
            
            # Remove from tag index (v1.3)
            for tag in listing.tags:
                self._tag_index.get(tag, set()).discard(service_id)
            
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
    
    async def update_service(
        self,
        service_id: str,
        provider_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update a service listing (only by provider).
        
        Args:
            service_id: Service ID to update
            provider_id: Provider ID for authorization
            updates: Dictionary of fields to update
                - description: str
                - pricing_model: PricingModel
                - price: Decimal
                - capabilities: List[str]
                - endpoint: str
                - terms_hash: str
                - is_active: bool
        
        Returns:
            True if successful, False otherwise
        """
        async with self._lock:
            if service_id not in self._listings:
                return False
            
            listing = self._listings[service_id]
            if listing.provider_id != provider_id:
                return False  # Not authorized
            
            # Update allowed fields
            if 'description' in updates:
                listing.description = updates['description']
            if 'pricing_model' in updates:
                if isinstance(updates['pricing_model'], PricingModel):
                    listing.pricing_model = updates['pricing_model']
                else:
                    listing.pricing_model = PricingModel(updates['pricing_model'])
            if 'price' in updates:
                from decimal import Decimal
                if isinstance(updates['price'], Decimal):
                    listing.price = updates['price']
                else:
                    listing.price = Decimal(str(updates['price']))
            if 'capabilities' in updates:
                # Update capability index
                old_caps = set(listing.capabilities)
                new_caps = set(updates['capabilities'])
                listing.capabilities = list(new_caps)
                
                # Remove old capabilities
                for cap in old_caps - new_caps:
                    self._capability_index.get(cap, set()).discard(service_id)
                # Add new capabilities
                for cap in new_caps - old_caps:
                    self._capability_index.setdefault(cap, set()).add(service_id)
            
            if 'endpoint' in updates:
                listing.endpoint = updates['endpoint']
            if 'terms_hash' in updates:
                listing.terms_hash = updates['terms_hash']
            if 'is_active' in updates:
                listing.is_active = bool(updates['is_active'])
            
            # Update tags (v1.3)
            if 'tags' in updates:
                old_tags = set(listing.tags)
                new_tags = set(updates['tags'])
                listing.tags = list(new_tags)
                
                # Remove old tags
                for tag in old_tags - new_tags:
                    self._tag_index.get(tag, set()).discard(service_id)
                # Add new tags
                for tag in new_tags - old_tags:
                    self._tag_index.setdefault(tag, set()).add(service_id)
            
            listing.updated_at = datetime.utcnow()
            
            # Persist
            if self._storage_path:
                await self._save_to_storage()
            
            return True
    
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
                for tag in listing.tags:
                    self._tag_index.setdefault(tag, set()).add(sid)
                    
        except FileNotFoundError:
            pass  # No existing data
        except Exception as e:
            print(f"Error loading registry: {e}")
    
    async def reload_from_storage(self) -> bool:
        """Reload registry from storage file (public method for hot reload)"""
        async with self._lock:
            try:
                # Clear existing data
                self._listings.clear()
                self._provider_services.clear()
                self._type_index = {t: set() for t in ServiceType}
                self._capability_index.clear()
                self._tag_index.clear()
                
                # Reload from file
                self._load_from_storage()
                return True
            except Exception as e:
                print(f"Error reloading registry: {e}")
                return False
    
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
    
    async def match_by_requirements(
        self,
        requirements: Dict[str, Any],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Match services based on structured requirements.
        
        Args:
            requirements: Dict with keys:
                - 'service_type': str (optional)
                - 'capabilities': List[str] (optional)
                - 'min_reputation': float (optional, default 0.0)
                - 'max_budget': str/Decimal (optional)
                - 'preferred_providers': List[str] (optional)
                - 'exclude_providers': List[str] (optional)
        
        Returns:
            List of matching services with match scores
        """
        async with self._lock:
            candidates = set(self._listings.keys())
            
            # Filter by service type
            if 'service_type' in requirements:
                try:
                    svc_type = ServiceType(requirements['service_type'])
                    candidates &= self._type_index.get(svc_type, set())
                except ValueError:
                    pass
            
            # Filter by capabilities (must have all)
            if 'capabilities' in requirements:
                for cap in requirements['capabilities']:
                    candidates &= self._capability_index.get(cap, set())
            
            # Exclude providers
            if 'exclude_providers' in requirements:
                for provider_id in requirements['exclude_providers']:
                    excluded = self._provider_services.get(provider_id, set())
                    candidates -= excluded
            
            # Score and rank candidates
            scored_results = []
            for sid in candidates:
                listing = self._listings[sid]
                
                # Skip inactive
                if not listing.is_active:
                    continue
                
                # Check minimum reputation
                min_rep = requirements.get('min_reputation', 0.0)
                if listing.reputation_score < min_rep:
                    continue
                
                # Check budget
                if 'max_budget' in requirements:
                    from decimal import Decimal
                    max_bud = Decimal(requirements['max_budget'])
                    if listing.price > max_bud:
                        continue
                
                # Calculate match score (0-100)
                score = self._calculate_match_score(listing, requirements)
                
                scored_results.append({
                    'service': listing,
                    'match_score': score,
                    'match_details': {
                        'reputation_match': listing.reputation_score >= min_rep,
                        'capabilities_match': all(
                            cap in listing.capabilities 
                            for cap in requirements.get('capabilities', [])
                        ),
                        'price_within_budget': (
                            listing.price <= Decimal(requirements['max_budget'])
                            if 'max_budget' in requirements else True
                        )
                    }
                })
            
            # Sort by match score (descending)
            scored_results.sort(key=lambda x: x['match_score'], reverse=True)
            
            return scored_results[:limit]
    
    def _calculate_match_score(
        self,
        listing: ServiceListing,
        requirements: Dict[str, Any]
    ) -> float:
        """Calculate match score (0-100) for a service listing"""
        score = 0.0
        
        # Reputation score (up to 40 points)
        score += (listing.reputation_score / 5.0) * 40
        
        # Success rate (up to 30 points)
        if listing.total_reviews > 0:
            success_rate = listing.successful_transactions / listing.total_reviews
            score += success_rate * 30
        else:
            # New provider bonus
            score += 15
        
        # Price competitiveness (up to 20 points)
        if 'max_budget' in requirements:
            from decimal import Decimal
            max_bud = Decimal(requirements['max_budget'])
            if max_bud > 0:
                price_ratio = 1.0 - (float(listing.price) / float(max_bud))
                score += max(0, price_ratio * 20)
        else:
            score += 10  # Neutral if no budget specified
        
        # Preferred provider bonus (up to 10 points)
        if 'preferred_providers' in requirements:
            if listing.provider_id in requirements['preferred_providers']:
                score += 10
        
        return min(100.0, score)
    
    async def find_best_match(
        self,
        requirements: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Find the single best matching service for given requirements.
        
        Returns:
            Best match with score, or None if no matches
        """
        matches = await self.match_by_requirements(requirements, limit=1)
        return matches[0] if matches else None


# Convenience functions for async usage
async def create_registry(storage_path: Optional[str] = None) -> ServiceRegistry:
    """Create a new service registry"""
    return ServiceRegistry(storage_path)
