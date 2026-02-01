#!/usr/bin/env python3
"""
Marketplace Integration Test
マーケットプレイス統合テスト - ローカルモジュール直接使用
"""

import sys
import os
import json
from datetime import datetime

# Add services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))

# Import directly from marketplace.py (not marketplace package)
import importlib.util
spec = importlib.util.spec_from_file_location("marketplace_module", 
    os.path.join(os.path.dirname(__file__), '..', 'services', 'marketplace.py'))
marketplace_module = importlib.util.module_from_spec(spec)
sys.modules["marketplace_module"] = marketplace_module
spec.loader.exec_module(marketplace_module)

MarketplaceRegistry = marketplace_module.MarketplaceRegistry
ServiceRecord = marketplace_module.ServiceRecord
PricingModel = marketplace_module.PricingModel
AvailabilityInfo = marketplace_module.AvailabilityInfo
RatingStats = marketplace_module.RatingStats


def test_entity_a_services():
    """Test registering Entity A services"""
    print("\n" + "=" * 60)
    print("Entity A Service Registration")
    print("=" * 60)
    
    registry = MarketplaceRegistry()
    
    services = [
        {
            "name": "Code Generation",
            "description": "Generate Python/JS/TS code from natural language requirements",
            "category": "development",
            "tags": ["coding", "generation", "python", "javascript"],
            "capabilities": ["code_gen", "file_write", "syntax_check"],
            "pricing": {"type": "fixed", "amount": 10.0, "currency": "AIC"},
        },
        {
            "name": "Code Review",
            "description": "Review code and provide improvement suggestions",
            "category": "development",
            "tags": ["code_review", "quality", "suggestions"],
            "capabilities": ["code_review", "static_analysis"],
            "pricing": {"type": "fixed", "amount": 5.0, "currency": "AIC"},
        },
        {
            "name": "Documentation",
            "description": "Create technical documentation from code or specs",
            "category": "documentation",
            "tags": ["docs", "documentation", "markdown"],
            "capabilities": ["doc_gen", "markdown"],
            "pricing": {"type": "per_token", "amount": 0.01, "currency": "AIC"},
        }
    ]
    
    registered = []
    entity_id = "entity-a"
    
    for i, svc in enumerate(services):
        pricing = PricingModel(**svc["pricing"])
        availability = AvailabilityInfo(
            status="available",
            max_concurrent=5,
            current_load=0,
            avg_response_time_ms=1000
        )
        rating = RatingStats(average=5.0, count=0)
        
        record = ServiceRecord(
            service_id=f"{entity_id}-{svc['name'].lower().replace(' ', '_')}",
            provider_id=entity_id,
            name=svc["name"],
            description=svc["description"],
            category=svc["category"],
            tags=svc["tags"],
            capabilities=svc["capabilities"],
            pricing=pricing,
            endpoint=f"http://localhost:8001/api/v1/services/{svc['name'].lower().replace(' ', '_')}",
            availability=availability,
            rating_stats=rating,
            version="1.0.0",
            verification_status="verified"
        )
        
        success = registry.register_service(record)
        if success:
            registered.append(record)
            print(f"  [OK] {record.name} -> {record.service_id}")
    
    return registered, registry


def test_entity_b_services():
    """Test registering Entity B services"""
    print("\n" + "=" * 60)
    print("Entity B Service Registration")
    print("=" * 60)
    
    registry = MarketplaceRegistry()
    
    services = [
        {
            "name": "Bug Fix",
            "description": "Analyze and fix bugs in code",
            "category": "development",
            "tags": ["debug", "fix", "bug"],
            "capabilities": ["debug", "code_fix", "testing"],
            "pricing": {"type": "fixed", "amount": 15.0, "currency": "AIC"},
        },
        {
            "name": "Research",
            "description": "Research topics and provide comprehensive summaries",
            "category": "research",
            "tags": ["research", "analysis", "summary"],
            "capabilities": ["web_search", "analysis", "summarization"],
            "pricing": {"type": "fixed", "amount": 20.0, "currency": "AIC"},
        }
    ]
    
    registered = []
    entity_id = "entity-b"
    
    for i, svc in enumerate(services):
        pricing = PricingModel(**svc["pricing"])
        availability = AvailabilityInfo(
            status="available",
            max_concurrent=5,
            current_load=0,
            avg_response_time_ms=1000
        )
        rating = RatingStats(average=5.0, count=0)
        
        record = ServiceRecord(
            service_id=f"{entity_id}-{svc['name'].lower().replace(' ', '_')}",
            provider_id=entity_id,
            name=svc["name"],
            description=svc["description"],
            category=svc["category"],
            tags=svc["tags"],
            capabilities=svc["capabilities"],
            pricing=pricing,
            endpoint=f"http://localhost:8002/api/v1/services/{svc['name'].lower().replace(' ', '_')}",
            availability=availability,
            rating_stats=rating,
            version="1.0.0",
            verification_status="verified"
        )
        
        success = registry.register_service(record)
        if success:
            registered.append(record)
            print(f"  [OK] {record.name} -> {record.service_id}")
    
    return registered, registry


def test_search_services(registry, query: str = None):
    """Test searching services"""
    print(f"\n" + "=" * 60)
    print(f"Search Test: query='{query}'")
    print("=" * 60)
    
    results = registry.search_services()
    
    if query:
        results = [r for r in results if query.lower() in r.name.lower() or 
                   any(query.lower() in tag.lower() for tag in r.tags)]
    
    print(f"  Found {len(results)} services")
    for r in results:
        print(f"    - {r.name} ({r.provider_id}): {r.pricing.amount} {r.pricing.currency}")
    
    return results


def main():
    print("=" * 60)
    print("Marketplace Integration Test")
    print("=" * 60)
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    
    # Register Entity A services
    entity_a_services, registry_a = test_entity_a_services()
    
    # Register Entity B services
    entity_b_services, registry_b = test_entity_b_services()
    
    # Merge registries for search test
    all_services = entity_a_services + entity_b_services
    
    print("\n" + "=" * 60)
    print(f"Total Registered: {len(all_services)} services")
    print("=" * 60)
    
    # Search tests
    print("\n--- Search Tests ---")
    
    # Search for 'code'
    code_results = [s for s in all_services if 'code' in s.name.lower() or 
                    any('code' in tag.lower() for tag in s.tags)]
    print(f"\nSearch 'code': {len(code_results)} results")
    for s in code_results:
        print(f"  - {s.name} ({s.provider_id})")
    
    # Search for 'research'
    research_results = [s for s in all_services if 'research' in s.name.lower()]
    print(f"\nSearch 'research': {len(research_results)} results")
    for s in research_results:
        print(f"  - {s.name} ({s.provider_id})")
    
    # Search by category 'development'
    dev_results = [s for s in all_services if s.category == 'development']
    print(f"\nCategory 'development': {len(dev_results)} results")
    for s in dev_results:
        print(f"  - {s.name} ({s.provider_id}): {s.pricing.amount} {s.pricing.currency}")
    
    # Export results
    output = {
        "timestamp": datetime.utcnow().isoformat(),
        "test_type": "local_marketplace_integration",
        "entity_a": {
            "services_count": len(entity_a_services),
            "services": [{"id": s.service_id, "name": s.name, "price": f"{s.pricing.amount} {s.pricing.currency}"} for s in entity_a_services]
        },
        "entity_b": {
            "services_count": len(entity_b_services),
            "services": [{"id": s.service_id, "name": s.name, "price": f"{s.pricing.amount} {s.pricing.currency}"} for s in entity_b_services]
        },
        "search_tests": {
            "code": len(code_results),
            "research": len(research_results),
            "development_category": len(dev_results)
        }
    }
    
    output_file = "marketplace_integration_test.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n[OK] Results exported to {output_file}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Entity A Services: {len(entity_a_services)} registered")
    print(f"Entity B Services: {len(entity_b_services)} registered")
    print(f"Total Services: {len(all_services)}")
    print(f"Search 'code': {len(code_results)} found")
    print(f"Search 'research': {len(research_results)} found")
    print(f"Category 'development': {len(dev_results)} found")
    print("=" * 60)
    print("Integration Test Complete!")
    print("=" * 60)
    
    return output


if __name__ == "__main__":
    result = main()
