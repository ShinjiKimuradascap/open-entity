#!/usr/bin/env python3
"""Register Open Entity services to marketplace"""
import urllib.request
import json
import uuid
from datetime import datetime

API_BASE = "http://34.134.116.148:8080"
ENTITY_ID = "open-entity-1769905908"

def register_service(service_data):
    """Register a service to the marketplace"""
    payload = {
        "entity_id": f"{ENTITY_ID}-{service_data['name'].lower().replace(' ', '-')}",
        "name": service_data["name"],
        "endpoint": service_data["endpoint"],
        "capabilities": service_data["capabilities"]
    }
    
    req = urllib.request.Request(
        f"{API_BASE}/register",
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            print(f"✅ Registered: {service_data['name']} - {data.get('status', 'ok')}")
            return True
    except Exception as e:
        print(f"❌ Failed: {service_data['name']} - {e}")
        return False

def main():
    services = [
        {
            "name": "Code Generation",
            "type": "compute",
            "description": "Generate Python/JavaScript code from specifications",
            "price": 10,
            "currency": "AIC",
            "capabilities": ["code_generation", "python", "javascript"],
            "endpoint": f"{API_BASE}/task/create"
        },
        {
            "name": "Code Review",
            "type": "analysis",
            "description": "Review code for quality, security, and best practices",
            "price": 5,
            "currency": "AIC",
            "capabilities": ["code_review", "security_audit", "best_practices"],
            "endpoint": f"{API_BASE}/task/create"
        },
        {
            "name": "Documentation",
            "type": "llm",
            "description": "Generate technical documentation and README files",
            "price": 8,
            "currency": "AIC",
            "capabilities": ["documentation", "technical_writing", "markdown"],
            "endpoint": f"{API_BASE}/task/create"
        },
        {
            "name": "Research Task",
            "type": "analysis",
            "description": "Research and summarize information on any topic",
            "price": 20,
            "currency": "AIC",
            "capabilities": ["research", "summarization", "web_search"],
            "endpoint": f"{API_BASE}/task/create"
        },
        {
            "name": "Bug Fix",
            "type": "compute",
            "description": "Analyze and fix bugs in existing code",
            "price": 15,
            "currency": "AIC",
            "capabilities": ["debugging", "bug_fix", "testing"],
            "endpoint": f"{API_BASE}/task/create"
        },
        {
            "name": "AI Service Delegation",
            "type": "llm",
            "description": "Delegate tasks to specialized sub-agents (coder, reviewer)",
            "price": 25,
            "currency": "AIC",
            "capabilities": ["task_delegation", "sub_agent", "orchestration"],
            "endpoint": f"{API_BASE}/task/create"
        }
    ]
    
    print("=== Registering Open Entity Services ===")
    print(f"Entity ID: {ENTITY_ID}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    registered = 0
    for service in services:
        if register_service(service):
            registered += 1
    
    print()
    print(f"=== Results ===")
    print(f"Registered: {registered}/{len(services)} services")
    
    # Check health
    try:
        req = urllib.request.Request(f"{API_BASE}/health", method='GET')
        with urllib.request.urlopen(req, timeout=5) as response:
            health = json.loads(response.read().decode())
            print(f"API Health: {health.get('status', 'unknown')}")
            print(f"Version: {health.get('version', 'unknown')}")
    except Exception as e:
        print(f"Health check failed: {e}")

if __name__ == "__main__":
    main()
