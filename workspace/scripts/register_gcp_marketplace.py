#!/usr/bin/env python3
"""
Register Entity Services to GCP API Server Marketplace
GCP API Serverのマーケットプレイスにエンティティサービスを登録

Usage:
    python scripts/register_gcp_marketplace.py --entity-id entity-a --gcp-url http://34.134.116.148:8080
"""

import argparse
import asyncio
import json
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional

import requests


class GCPMarketplaceClient:
    """Client for GCP API Server Marketplace"""
    
    # Service definitions for Entity A
    ENTITY_A_SERVICES = [
        {
            "name": "Code Generation",
            "description": "Generate Python/JS/TS code from natural language requirements with high quality and best practices",
            "category": "development",
            "tags": ["coding", "generation", "python", "javascript", "typescript", "ai"],
            "capabilities": ["code_gen", "file_write", "syntax_check", "linting"],
            "pricing": {"type": "fixed", "amount": 10.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/code_gen"
        },
        {
            "name": "Code Review",
            "description": "Comprehensive code review with improvement suggestions, security checks, and performance optimization",
            "category": "development",
            "tags": ["code_review", "quality", "security", "performance"],
            "capabilities": ["code_review", "static_analysis", "security_audit"],
            "pricing": {"type": "fixed", "amount": 5.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/code_review"
        },
        {
            "name": "Documentation",
            "description": "Create technical documentation from code, APIs, or specifications in markdown format",
            "category": "documentation",
            "tags": ["docs", "documentation", "markdown", "api_docs"],
            "capabilities": ["doc_gen", "markdown", "api_documentation"],
            "pricing": {"type": "per_token", "amount": 0.01, "currency": "AIC"},
            "endpoint": "/api/v1/services/documentation"
        }
    ]
    
    # Service definitions for Entity B
    ENTITY_B_SERVICES = [
        {
            "name": "Bug Fix",
            "description": "Analyze, debug and fix bugs in Python/JS/TS code with comprehensive testing",
            "category": "development",
            "tags": ["debug", "fix", "bug", "testing", "troubleshooting"],
            "capabilities": ["debug", "code_fix", "testing", "root_cause_analysis"],
            "pricing": {"type": "fixed", "amount": 15.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/bug_fix"
        },
        {
            "name": "Research",
            "description": "Deep research on technical topics with comprehensive summaries and actionable insights",
            "category": "research",
            "tags": ["research", "analysis", "summary", "technical_research"],
            "capabilities": ["web_search", "analysis", "summarization", "report_generation"],
            "pricing": {"type": "fixed", "amount": 20.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/research"
        }
    ]
    
    def __init__(self, gcp_url: str, api_key: Optional[str] = None):
        self.gcp_url = gcp_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})
    
    def create_service_payload(self, service_def: Dict, entity_id: str, entity_endpoint: str) -> Dict:
        """Create service registration payload"""
        return {
            "service_id": f"{entity_id}-{service_def['name'].lower().replace(' ', '_')}",
            "name": service_def["name"],
            "description": service_def["description"],
            "provider_id": entity_id,
            "category": service_def["category"],
            "tags": service_def["tags"],
            "capabilities": service_def["capabilities"],
            "pricing_model": service_def["pricing"],
            "endpoint": f"{entity_endpoint}{service_def['endpoint']}",
            "availability": {
                "status": "available",
                "max_concurrent": 5,
                "avg_response_time_ms": 1000
            },
            "version": "1.0.0",
            "verification_status": "verified"
        }
    
    def register_service(self, service_payload: Dict) -> Optional[Dict]:
        """Register a single service to GCP API Server"""
        try:
            # Try v1.3 endpoint first
            url = f"{self.gcp_url}/api/v1.3/marketplace/services"
            response = self.session.post(url, json=service_payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                print(f"    [OK] {service_payload['name']} -> {result.get('service_id')}")
                return result
            elif response.status_code == 404:
                # Try lightweight marketplace API endpoint
                url = f"{self.gcp_url}/api/marketplace/services"
                # Convert payload format for lightweight API
                lightweight_payload = {
                    "entity_id": service_payload["service_id"],
                    "name": service_payload["name"],
                    "description": service_payload["description"],
                    "capabilities": service_payload["capabilities"],
                    "price_per_task": service_payload["pricing_model"]["amount"],
                    "endpoint": service_payload["endpoint"]
                }
                response = self.session.post(url, json=lightweight_payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"    [OK] {service_payload['name']} -> {service_payload['service_id']}")
                    return {"service_id": service_payload["service_id"], **result}
                else:
                    print(f"    [FAIL] {service_payload['name']}: HTTP {response.status_code}")
                    print(f"           {response.text[:200]}")
                    return None
            else:
                print(f"    [FAIL] {service_payload['name']}: HTTP {response.status_code}")
                print(f"           {response.text[:200]}")
                return None
                
        except Exception as e:
            print(f"    [ERROR] {service_payload['name']}: {e}")
            return None
    
    def register_entity_services(self, entity_id: str, entity_endpoint: str) -> List[Dict]:
        """Register all services for an entity"""
        # Select service definitions based on entity
        if entity_id == "entity-a":
            services = self.ENTITY_A_SERVICES
        elif entity_id == "entity-b":
            services = self.ENTITY_B_SERVICES
        else:
            # Combined services for other entities
            services = self.ENTITY_A_SERVICES + self.ENTITY_B_SERVICES
        
        registered = []
        print(f"\nRegistering {len(services)} services for {entity_id}...")
        print("-" * 60)
        
        for service_def in services:
            payload = self.create_service_payload(service_def, entity_id, entity_endpoint)
            result = self.register_service(payload)
            if result:
                registered.append(result)
        
        return registered
    
    def search_services(self, query: str = None, category: str = None) -> List[Dict]:
        """Search services on GCP API Server"""
        try:
            # Try v1.3 endpoint first
            url = f"{self.gcp_url}/api/v1.3/marketplace/services/search"
            params = {}
            if query:
                params["query"] = query
            if category:
                params["category"] = category
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                services = result.get("services", [])
                print(f"\n[OK] Search returned {len(services)} services")
                return services
            elif response.status_code == 404:
                # Lightweight API doesn't have search, use list and filter
                services = self.list_services()
                if query:
                    services = [s for s in services if query.lower() in json.dumps(s).lower()]
                print(f"\n[OK] Filtered search returned {len(services)} services")
                return services
            else:
                print(f"\n[FAIL] Search failed: HTTP {response.status_code}")
                print(f"       {response.text[:200]}")
                return []
                
        except Exception as e:
            print(f"\n[ERROR] Search failed: {e}")
            return []
    
    def list_services(self) -> List[Dict]:
        """List all services on GCP API Server"""
        try:
            # Try v1.3 endpoint first
            url = f"{self.gcp_url}/api/v1.3/marketplace/services"
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                services = result.get("services", [])
                print(f"\n[OK] Listed {len(services)} services")
                return services
            elif response.status_code == 404:
                # Try lightweight marketplace API endpoint
                url = f"{self.gcp_url}/api/marketplace/services"
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    services = result.get("services", [])
                    print(f"\n[OK] Listed {len(services)} services (lightweight API)")
                    return services
                else:
                    print(f"\n[FAIL] List failed: HTTP {response.status_code}")
                    return []
            else:
                print(f"\n[FAIL] List failed: HTTP {response.status_code}")
                return []
                
        except Exception as e:
            print(f"\n[ERROR] List failed: {e}")
            return []


def main():
    parser = argparse.ArgumentParser(
        description="Register Entity Services to GCP API Server Marketplace"
    )
    parser.add_argument(
        "--gcp-url",
        default="http://34.134.116.148:8080",
        help="GCP API Server URL (default: http://34.134.116.148:8080)"
    )
    parser.add_argument(
        "--entity-a-id",
        default="entity-a",
        help="Entity A ID (default: entity-a)"
    )
    parser.add_argument(
        "--entity-b-id",
        default="entity-b",
        help="Entity B ID (default: entity-b)"
    )
    parser.add_argument(
        "--entity-a-endpoint",
        default="http://localhost:8001",
        help="Entity A endpoint URL (default: http://localhost:8001)"
    )
    parser.add_argument(
        "--entity-b-endpoint",
        default="http://localhost:8002",
        help="Entity B endpoint URL (default: http://localhost:8002)"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="GCP API Key (optional)"
    )
    parser.add_argument(
        "--output",
        default="gcp_marketplace_registration.json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--skip-test",
        action="store_true",
        help="Skip search test after registration"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("GCP API Server - Marketplace Service Registration")
    print("=" * 70)
    print(f"GCP URL: {args.gcp_url}")
    print(f"Entity A: {args.entity_a_id} @ {args.entity_a_endpoint}")
    print(f"Entity B: {args.entity_b_id} @ {args.entity_b_endpoint}")
    print("=" * 70)
    
    # Initialize client
    client = GCPMarketplaceClient(args.gcp_url, args.api_key)
    
    all_registered = []
    
    # Register Entity A services
    registered_a = client.register_entity_services(args.entity_a_id, args.entity_a_endpoint)
    all_registered.extend(registered_a)
    
    # Register Entity B services
    registered_b = client.register_entity_services(args.entity_b_id, args.entity_b_endpoint)
    all_registered.extend(registered_b)
    
    print("\n" + "=" * 70)
    print(f"Registration Summary: {len(all_registered)} services registered")
    print("=" * 70)
    
    # List all services
    print("\n--- Listing All Services ---")
    all_services = client.list_services()
    
    # Search test
    if not args.skip_test:
        print("\n--- Search Test: 'code' ---")
        search_results = client.search_services(query="code")
        
        print("\n--- Search Test: 'research' ---")
        search_results = client.search_services(query="research")
        
        print("\n--- Search Test: category='development' ---")
        search_results = client.search_services(category="development")
    
    # Export results
    if args.output:
        output_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "gcp_url": args.gcp_url,
            "registered_services": all_registered,
            "total_registered": len(all_registered),
            "entity_a_services": len(registered_a),
            "entity_b_services": len(registered_b)
        }
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\n[OK] Results exported to {args.output}")
    
    print("\n" + "=" * 70)
    print("Registration Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
