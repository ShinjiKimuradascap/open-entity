#!/usr/bin/env python3
"""
Distributed Service Registry with DHT Integration
v1.3 Multi-Agent Marketplace - Decentralized Service Discovery
"""

import asyncio
import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Callable, Any
from enum import Enum

# DHT imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from kademlia_dht import DHTRegistry, PeerInfo
    KADEMLIA_AVAILABLE = True
except ImportError:
    KADEMLIA_AVAILABLE = False
    DHTRegistry = None
    PeerInfo = None

from service_registry import ServiceRegistry, ServiceListing, ServiceType, PricingModel


@dataclass
class DistributedServiceListing(ServiceListing):
    """Extended service listing with DHT metadata"""
    dht_key: Optional[str] = None
    ttl_seconds: int = 3600  # 1 hour default TTL
    replication_factor: int = 3
    last_heartbeat: Optional[datetime] = None
    
    def is_expired(self) -> bool:
        """Check if listing has expired"""
        if not self.last_heartbeat:
            return True
        expiry = self.last_heartbeat + timedelta(seconds=self.ttl_seconds)
        return datetime.utcnow() > expiry
    
    def to_dht_value(self) -> str:
        """Convert to DHT storable value"""
        data = self.to_dict()
        data['dht_key'] = self.dht_key
        data['ttl_seconds'] = self.ttl_seconds
        return json.dumps(data)
    
    @classmethod
    def from_dht_value(cls, value: str) -> 'DistributedServiceListing':
        """Create from DHT stored value"""
        data = json.loads(value)
        listing = cls.from_dict(data)
        listing.dht_key = data.get('dht_key')
        listing.ttl_seconds = data.get('ttl_seconds', 3600)
        return listing


class DistributedServiceRegistry(ServiceRegistry):
    """
    Distributed service registry with DHT integration.
    
    Enables decentralized service discovery across the AI network.
    Services are registered both locally and in the DHT for global discovery.
    """
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        dht_registry: Optional[Any] = None,
        entity_id: Optional[str] = None,
        enable_dht: bool = True
    ):
        super().__init__(storage_path)
        self._dht_registry = dht_registry
        self._entity_id = entity_id
        self._enable_dht = enable_dht and KADEMLIA_AVAILABLE
        self._dht_listings: Dict[str, DistributedServiceListing] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._dht_index_prefix = "service:"
    
    async def start(self) -> bool:
        """Start the distributed registry with DHT"""
        if not self._enable_dht:
            return True
        
        if not self._dht_registry:
            return False
        
        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        return True
    
    async def stop(self):
        """Stop the distributed registry"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
    
    async def register_distributed_service(
        self,
        listing: DistributedServiceListing
    ) -> bool:
        """
        Register a service both locally and in DHT.
        
        Args:
            listing: Service listing to register
            
        Returns:
            True if registration successful
        """
        # Register locally first
        base_listing = ServiceListing(
            service_id=listing.service_id,
            provider_id=listing.provider_id,
            service_type=listing.service_type,
            description=listing.description,
            pricing_model=listing.pricing_model,
            price=listing.price,
            capabilities=listing.capabilities,
            endpoint=listing.endpoint,
            terms_hash=listing.terms_hash,
            reputation_score=listing.reputation_score,
            total_reviews=listing.total_reviews,
            successful_transactions=listing.successful_transactions
        )
        
        success = await self.register_service(base_listing)
        if not success:
            return False
        
        # Register in DHT
        if self._enable_dht and self._dht_registry:
            try:
                dht_key = self._compute_dht_key(listing)
                listing.dht_key = dht_key
                listing.last_heartbeat = datetime.utcnow()
                
                await self._dht_registry.set(
                    dht_key,
                    listing.to_dht_value(),
                    ttl=listing.ttl_seconds
                )
                
                # Also index by capability for capability-based search
                for cap in listing.capabilities:
                    cap_key = f"{self._dht_index_prefix}cap:{cap}"
                    await self._dht_registry.append(cap_key, listing.service_id)
                
                self._dht_listings[listing.service_id] = listing
                
            except Exception as e:
                print(f"DHT registration failed: {e}")
                # Continue with local registration only
        
        return True
    
    async def discover_services_dht(
        self,
        capability: Optional[str] = None,
        service_type: Optional[ServiceType] = None,
        max_results: int = 10
    ) -> List[DistributedServiceListing]:
        """
        Discover services from DHT.
        
        Args:
            capability: Filter by capability
            service_type: Filter by service type
            max_results: Maximum number of results
            
        Returns:
            List of discovered service listings
        """
        if not self._enable_dht or not self._dht_registry:
            return []
        
        discovered = []
        
        try:
            if capability:
                # Search by capability index
                cap_key = f"{self._dht_index_prefix}cap:{capability}"
                service_ids = await self._dht_registry.get(cap_key)
                
                if service_ids:
                    ids = json.loads(service_ids) if isinstance(service_ids, str) else service_ids
                    for sid in ids[:max_results]:
                        listing = await self._get_service_from_dht(sid)
                        if listing and not listing.is_expired():
                            discovered.append(listing)
            else:
                # Iterate through DHT keys (inefficient but functional for prototype)
                # In production, would use more sophisticated DHT queries
                for sid, local_listing in self._listings.items():
                    dht_key = self._compute_dht_key_from_id(sid)
                    value = await self._dht_registry.get(dht_key)
                    
                    if value:
                        try:
                            listing = DistributedServiceListing.from_dht_value(value)
                            if not listing.is_expired():
                                if service_type and listing.service_type != service_type:
                                    continue
                                discovered.append(listing)
                        except:
                            pass
        
        except Exception as e:
            print(f"DHT discovery failed: {e}")
        
        return discovered[:max_results]
    
    async def _get_service_from_dht(
        self,
        service_id: str
    ) -> Optional[DistributedServiceListing]:
        """Retrieve a service listing from DHT"""
        if not self._dht_registry:
            return None
        
        dht_key = self._compute_dht_key_from_id(service_id)
        
        try:
            value = await self._dht_registry.get(dht_key)
            if value:
                return DistributedServiceListing.from_dht_value(value)
        except Exception as e:
            print(f"Failed to get service from DHT: {e}")
        
        return None
    
    def _compute_dht_key(self, listing: DistributedServiceListing) -> str:
        """Compute DHT key for a listing"""
        return f"{self._dht_index_prefix}{listing.service_id}"
    
    def _compute_dht_key_from_id(self, service_id: str) -> str:
        """Compute DHT key from service ID"""
        return f"{self._dht_index_prefix}{service_id}"
    
    async def _heartbeat_loop(self):
        """Background task to refresh DHT listings"""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                await self._refresh_dht_listings()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Heartbeat error: {e}")
    
    async def _refresh_dht_listings(self):
        """Refresh all DHT listings to prevent expiration"""
        if not self._dht_registry:
            return
        
        for listing in self._dht_listings.values():
            try:
                listing.last_heartbeat = datetime.utcnow()
                await self._dht_registry.set(
                    listing.dht_key,
                    listing.to_dht_value(),
                    ttl=listing.ttl_seconds
                )
            except Exception as e:
                print(f"Failed to refresh listing {listing.service_id}: {e}")
    
    async def hybrid_search(
        self,
        capability: Optional[str] = None,
        service_type: Optional[ServiceType] = None,
        min_reputation: float = 0.0,
        max_price: Optional[Decimal] = None,
        limit: int = 100,
        prefer_local: bool = True
    ) -> List[DistributedServiceListing]:
        """
        Hybrid search combining local and DHT results.
        
        Args:
            capability: Required capability
            service_type: Service type filter
            min_reputation: Minimum reputation score
            max_price: Maximum price
            limit: Maximum results
            prefer_local: Prefer local listings over DHT
            
        Returns:
            Merged and filtered results
        """
        # Get local results
        local_results = await self.search_services(
            service_type=service_type,
            capabilities=[capability] if capability else None,
            min_reputation=min_reputation,
            max_price=max_price,
            limit=limit
        )
        
        # Get DHT results
        dht_results = await self.discover_services_dht(
            capability=capability,
            service_type=service_type,
            max_results=limit
        )
        
        # Convert local results to distributed format
        distributed_locals = []
        for local in local_results:
            dist = DistributedServiceListing(
                service_id=local.service_id,
                provider_id=local.provider_id,
                service_type=local.service_type,
                description=local.description,
                pricing_model=local.pricing_model,
                price=local.price,
                capabilities=local.capabilities,
                endpoint=local.endpoint,
                terms_hash=local.terms_hash,
                reputation_score=local.reputation_score,
                total_reviews=local.total_reviews,
                successful_transactions=local.successful_transactions,
                is_active=local.is_active
            )
            distributed_locals.append(dist)
        
        # Merge results (deduplicate by service_id)
        seen_ids = set()
        merged = []
        
        if prefer_local:
            sources = [distributed_locals, dht_results]
        else:
            sources = [dht_results, distributed_locals]
        
        for source in sources:
            for listing in source:
                if listing.service_id not in seen_ids:
                    # Apply filters
                    if listing.reputation_score >= min_reputation:
                        if max_price is None or listing.price <= max_price:
                            seen_ids.add(listing.service_id)
                            merged.append(listing)
        
        # Sort by reputation, then price
        merged.sort(key=lambda x: (-x.reputation_score, x.price))
        
        return merged[:limit]


# Factory function
async def create_distributed_registry(
    storage_path: Optional[str] = None,
    dht_registry: Optional[Any] = None,
    entity_id: Optional[str] = None,
    enable_dht: bool = True
) -> DistributedServiceRegistry:
    """Create and initialize a distributed service registry"""
    registry = DistributedServiceRegistry(
        storage_path=storage_path,
        dht_registry=dht_registry,
        entity_id=entity_id,
        enable_dht=enable_dht
    )
    
    if enable_dht:
        await registry.start()
    
    return registry


if __name__ == "__main__":
    # Test the distributed registry
    async def test():
        registry = await create_distributed_registry(
            storage_path="data/test_distributed_registry.json",
            enable_dht=False  # Test without DHT for now
        )
        
        # Create a test listing
        from decimal import Decimal
        
        listing = DistributedServiceListing(
            service_id="test-service-1",
            provider_id="provider-1",
            service_type=ServiceType.COMPUTE,
            description="Test compute service",
            pricing_model=PricingModel.PER_REQUEST,
            price=Decimal("10.00"),
            capabilities=["compute", "ai"],
            endpoint="http://localhost:8080",
            terms_hash="abc123"
        )
        
        # Register
        success = await registry.register_distributed_service(listing)
        print(f"Registration success: {success}")
        
        # Search
        results = await registry.hybrid_search(
            capability="compute",
            limit=10
        )
        print(f"Found {len(results)} services")
        
        # Stats
        stats = await registry.get_stats()
        print(f"Stats: {stats}")
        
        await registry.stop()
    
    asyncio.run(test())
