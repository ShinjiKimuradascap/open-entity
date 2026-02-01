#!/usr/bin/env python3
"""
Register Entity Services to Marketplace
エンティティサービスのマーケットプレイス登録スクリプト

Usage:
    python scripts/register_marketplace_services.py --entity entity-a --api http://localhost:8000
"""

import argparse
import asyncio
import json
import sys
import os
from datetime import datetime
from typing import Dict, List

# Add services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))

from marketplace import MarketplaceRegistry, ServiceRecord, PricingModel, AvailabilityInfo, RatingStats


class ServiceRegistrar:
    """Register services for an AI entity"""
    
    # Default services offered by AI entities
    DEFAULT_SERVICES = [
        {
            "name": "Code Generation",
            "description": "Generate Python/JS/TS code from natural language requirements",
            "category": "development",
            "tags": ["coding", "generation", "python", "javascript", "typescript"],
            "capabilities": ["code_gen", "file_write", "syntax_check"],
            "pricing": {"type": "fixed", "amount": 10.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/code_gen"
        },
        {
            "name": "Code Review",
            "description": "Review code and provide improvement suggestions",
            "category": "development",
            "tags": ["code_review", "quality", "suggestions"],
            "capabilities": ["code_review", "static_analysis"],
            "pricing": {"type": "fixed", "amount": 5.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/code_review"
        },
        {
            "name": "Documentation",
            "description": "Create technical documentation from code or specs",
            "category": "documentation",
            "tags": ["docs", "documentation", "markdown"],
            "capabilities": ["doc_gen", "markdown"],
            "pricing": {"type": "per_token", "amount": 0.01, "currency": "AIC"},
            "endpoint": "/api/v1/services/documentation"
        },
        {
            "name": "Bug Fix",
            "description": "Analyze and fix bugs in code",
            "category": "development",
            "tags": ["debug", "fix", "bug"],
            "capabilities": ["debug", "code_fix", "testing"],
            "pricing": {"type": "fixed", "amount": 15.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/bug_fix"
        },
        {
            "name": "Research",
            "description": "Research topics and provide comprehensive summaries",
            "category": "research",
            "tags": ["research", "analysis", "summary"],
            "capabilities": ["web_search", "analysis", "summarization"],
            "pricing": {"type": "fixed", "amount": 20.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/research"
        }
    ]
    
    def __init__(self, entity_id: str, api_url: str):
        self.entity_id = entity_id
        self.api_url = api_url
        self.registry = MarketplaceRegistry()
        
    def create_service_record(self, service_def: Dict, index: int) -> ServiceRecord:
        """Create a ServiceRecord from definition"""
        pricing = PricingModel(**service_def["pricing"])
        availability = AvailabilityInfo(
            status="available",
            max_concurrent=5,
            current_load=0,
            avg_response_time_ms=1000
        )
        rating = RatingStats(average=5.0, count=0)
        
        return ServiceRecord(
            service_id=f"{self.entity_id}-{service_def['name'].lower().replace(' ', '_')}",
            provider_id=self.entity_id,
            name=service_def["name"],
            description=service_def["description"],
            category=service_def["category"],
            tags=service_def["tags"],
            capabilities=service_def["capabilities"],
            pricing=pricing,
            endpoint=f"{self.api_url}{service_def['endpoint']}",
            availability=availability,
            rating_stats=rating,
            version="1.0.0",
            verification_status="verified"
        )
    
    def register_all_services(self) -> List[str]:
        """Register all default services for the entity"""
        registered = []
        
        print(f"\nRegistering services for {self.entity_id}...")
        print("=" * 60)
        
        for i, service_def in enumerate(self.DEFAULT_SERVICES):
            record = self.create_service_record(service_def, i)
            success = self.registry.register_service(record)
            
            if success:
                registered.append(record.service_id)
                print(f"  [OK] {record.name}")
                print(f"       ID: {record.service_id}")
                print(f"       Price: {record.pricing.amount} {record.pricing.currency}")
                print(f"       Endpoint: {record.endpoint}")
                print()
        
        return registered
    
    def export_to_json(self, output_path: str):
        """Export registered services to JSON"""
        services = []
        for service_id in self.registry._services:
            s = self.registry._services[service_id]
            services.append({
                "service_id": s.service_id,
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "tags": s.tags,
                "pricing": {
                    "type": s.pricing.type,
                    "amount": s.pricing.amount,
                    "currency": s.pricing.currency
                },
                "endpoint": s.endpoint,
                "provider_id": s.provider_id
            })
        
        with open(output_path, 'w') as f:
            json.dump(services, f, indent=2)
        
        print(f"Exported {len(services)} services to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Register Entity Services to Marketplace"
    )
    parser.add_argument(
        "--entity",
        required=True,
        help="Entity ID (e.g., entity-a, entity-b)"
    )
    parser.add_argument(
        "--api",
        default="http://localhost:8000",
        help="API server URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("AI Collaboration Platform - Service Registration")
    print("=" * 60)
    print(f"Entity: {args.entity}")
    print(f"API URL: {args.api}")
    print("=" * 60)
    
    registrar = ServiceRegistrar(args.entity, args.api)
    registered = registrar.register_all_services()
    
    print("=" * 60)
    print(f"Registration Complete: {len(registered)} services")
    print("=" * 60)
    
    # Export to JSON if output path specified
    if args.output:
        registrar.export_to_json(args.output)
    
    print("\nRegistered Services:")
    for sid in registered:
        print(f"  - {sid}")
    
    print("\nNext steps:")
    print("  1. Deploy services to production")
    print("  2. Start accepting requests")
    print("  3. Earn AIC tokens for completed tasks")
    print("=" * 60)


if __name__ == "__main__":
    main()
