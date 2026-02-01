#!/usr/bin/env python3
"""
GCP API Server - Agent and Service Registration Script
Registers an agent and marketplace services on the GCP API Server
"""

import urllib.request
import json
import sys
from datetime import datetime

# Configuration
API_BASE = "http://34.134.116.148:8080"
ENTITY_ID = "open-entity-orchestrator-1738377841"
RESULT_FILE = "gcp_registration_result.json"

def make_request(path, method="GET", data=None, headers=None):
    """Make HTTP request to GCP API Server"""
    url = f"{API_BASE}{path}"
    default_headers = {"Content-Type": "application/json"}
    if headers:
        default_headers.update(headers)
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers=default_headers,
        method=method
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read().decode()
            return {
                "status": response.status,
                "body": json.loads(body) if body else {}
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            parsed_body = json.loads(body) if body else {"error": f"HTTP {e.code}"}
        except json.JSONDecodeError:
            parsed_body = {"error": f"HTTP {e.code}", "raw": body[:200]}
        return {
            "status": e.code,
            "body": parsed_body
        }
    except Exception as e:
        return {
            "status": 0,
            "body": {"error": str(e)}
        }

def register_service_v2(service_data, jwt_token):
    """Register service using lightweight API"""
    # Try lightweight API first
    path = "/api/marketplace/services"
    headers = {"Authorization": f"Bearer {jwt_token}"}
    
    result = make_request(path, "POST", service_data, headers)
    
    if result['status'] == 404:
        # Try v1.3 endpoint
        path = "/api/v1.3/marketplace/services"
        result = make_request(path, "POST", service_data, headers)
    
    return result

def health_check():
    """Check API server health"""
    print("\n[1/4] Health Check")
    print("-" * 40)
    result = make_request("/health")
    print(f"Status: {result['status']}")
    print(f"Response: {json.dumps(result['body'], indent=2)}")
    return result

def register_agent():
    """Register agent on GCP API Server"""
    print("\n[2/4] Agent Registration")
    print("-" * 40)
    
    payload = {
        "entity_id": ENTITY_ID,
        "name": "Open Entity Orchestrator",
        "type": "orchestrator",
        "version": "1.0.0",
        "capabilities": ["task_management", "delegation", "coordination", "code_generation"],
        "endpoint": API_BASE,
        "public_key": None,
        "metadata": {
            "registered_at": datetime.now().isoformat(),
            "platform": "AI Collaboration Platform"
        }
    }
    
    result = make_request("/register", "POST", payload)
    print(f"Status: {result['status']}")
    print(f"Response: {json.dumps(result['body'], indent=2)}")
    
    # Extract API key if present
    api_key = result['body'].get('api_key') if isinstance(result['body'], dict) else None
    if api_key:
        print(f"\n✅ API Key received: {api_key[:20]}...")
    
    return result

def get_jwt_token(api_key):
    """Get JWT token from API key"""
    print("\n  [Getting JWT Token]")
    auth_data = {
        "entity_id": ENTITY_ID,
        "api_key": api_key
    }
    result = make_request("/auth/token", "POST", auth_data)
    if result['status'] == 200 and isinstance(result['body'], dict):
        token = result['body'].get('access_token') or result['body'].get('token')
        if token:
            print(f"  ✅ JWT token received")
            return token
    print(f"  ❌ Failed to get JWT token: {result['body']}")
    return None

def register_services(api_key=None, jwt_token=None):
    """Register marketplace services"""
    print("\n[3/4] Service Registration")
    print("-" * 40)
    
    if not api_key:
        print("⚠️ No API key available, skipping service registration")
        return []
    
    # Get JWT token if not provided
    if not jwt_token:
        jwt_token = get_jwt_token(api_key)
    if not jwt_token:
        print("⚠️ Cannot get JWT token, skipping service registration")
        return []
    
    services = [
        {
            "name": "Task Delegation Service",
            "description": "Intelligent task delegation and orchestration across AI agents with automatic load balancing",
            "category": "compute",
            "tags": ["orchestration", "delegation", "ai"],
            "capabilities": ["task_delegation", "load_balancing", "agent_coordination"],
            "pricing": {"type": "fixed", "amount": 10.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/delegate"
        },
        {
            "name": "Code Review Service",
            "description": "Automated code quality analysis and review with AI-powered suggestions",
            "category": "development",
            "tags": ["code_review", "quality", "ai"],
            "capabilities": ["code_analysis", "quality_review", "suggestions"],
            "pricing": {"type": "fixed", "amount": 5.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/code_review"
        },
        {
            "name": "Agent Coordination Hub",
            "description": "Real-time coordination and communication hub for multi-agent collaboration",
            "category": "api",
            "tags": ["coordination", "messaging", "realtime"],
            "capabilities": ["real_time_coordination", "messaging", "sync"],
            "pricing": {"type": "fixed", "amount": 50.0, "currency": "AIC"},
            "endpoint": "/api/v1/services/coordinate"
        }
    ]
    
    registered_services = []
    for svc_def in services:
        print(f"\n  Registering: {svc_def['name']}")
        
        # Create lightweight payload
        service_payload = {
            "entity_id": f"{ENTITY_ID}-{svc_def['name'].lower().replace(' ', '_')}",
            "name": svc_def["name"],
            "description": svc_def["description"],
            "capabilities": svc_def["capabilities"],
            "price_per_task": svc_def["pricing"]["amount"],
            "endpoint": f"{API_BASE}{svc_def['endpoint']}"
        }
        
        result = register_service_v2(service_payload, jwt_token)
        print(f"  Status: {result['status']}")
        
        if result['status'] in [200, 201]:
            service_id = result['body'].get('service_id') if isinstance(result['body'], dict) else None
            registered_services.append({
                "service_name": svc_def['name'],
                "service_id": service_id or service_payload['entity_id'],
                "status": "registered",
                "response": result['body']
            })
            print(f"  ✅ Registered successfully")
        else:
            registered_services.append({
                "service_name": svc_def['name'],
                "status": "failed",
                "error": str(result['body'])
            })
            print(f"  ❌ Failed: {result['body']}")
    
    return registered_services

def list_services(jwt_token=None):
    """List registered services"""
    print("\n[4/4] Listing Registered Services")
    print("-" * 40)
    
    headers = {}
    if jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token}"
    
    result = make_request("/marketplace/services", "GET", headers=headers)
    print(f"Status: {result['status']}")
    if result['status'] == 200 and isinstance(result['body'], dict):
        services = result['body'].get('services', [])
        print(f"Total services: {result['body'].get('total', 0)}")
        print(f"Services from this entity: {sum(1 for s in services if s.get('provider_id') == ENTITY_ID)}")
    else:
        print(f"Response: {result['body']}")
    return result

def save_results(results):
    """Save registration results to file"""
    print(f"\n[5/4] Saving Results to {RESULT_FILE}")
    print("-" * 40)
    
    try:
        with open(RESULT_FILE, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"✅ Results saved to {RESULT_FILE}")
        return True
    except Exception as e:
        print(f"❌ Failed to save results: {e}")
        return False

def main():
    print("=" * 60)
    print("GCP API Server - Complete Registration")
    print("=" * 60)
    print(f"API Endpoint: {API_BASE}")
    print(f"Entity ID: {ENTITY_ID}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "api_endpoint": API_BASE,
        "entity_id": ENTITY_ID,
        "health_check": None,
        "agent_registration": None,
        "service_registration": None,
        "service_listing": None
    }
    
    try:
        # Step 1: Health Check
        results["health_check"] = health_check()
        
        # Step 2: Register Agent
        results["agent_registration"] = register_agent()
        api_key = None
        if results["agent_registration"]["status"] == 200:
            api_key = results["agent_registration"]["body"].get("api_key")
        
        # Step 3: Register Services
        jwt_token = get_jwt_token(api_key) if api_key else None
        results["service_registration"] = register_services(api_key, jwt_token)
        
        # Step 4: List Services
        results["service_listing"] = list_services(jwt_token)
        
        # Step 5: Save Results
        save_results(results)
        
        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        health_ok = results["health_check"]["status"] == 200
        agent_ok = results["agent_registration"]["status"] == 200
        services_ok = sum(1 for s in results["service_registration"] if s["status"] == "registered")
        
        print(f"Health Check: {'✅' if health_ok else '❌'} {results['health_check']['status']}")
        print(f"Agent Registration: {'✅' if agent_ok else '❌'} {results['agent_registration']['status']}")
        print(f"Services Registered: {services_ok}/{len(results['service_registration'])}")
        
        if api_key:
            print(f"\n🔑 API Key: {api_key}")
            print(f"   (Saved in response)")
        
        print(f"\n📄 Results saved to: {RESULT_FILE}")
        print("\n✅ GCP API Server registration complete!")
        
        return 0 if (health_ok and agent_ok and services_ok > 0) else 1
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        save_results(results)
        return 130
    except Exception as e:
        print(f"\n❌ Error: {e}")
        save_results(results)
        return 1

if __name__ == "__main__":
    sys.exit(main())
