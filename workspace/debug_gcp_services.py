#!/usr/bin/env python3
"""Debug GCP API Service Registration"""

import urllib.request
import json

API_BASE = "http://34.134.116.148:8080"
API_KEY = "ak_ur_tARyKijbVZNydQErbcDA437jFdLCbCcd53Mlqm8Q"
ENTITY_ID = "open-entity-orchestrator-1738377841"

def make_request(path, method="GET", data=None, headers=None):
    """Make HTTP request"""
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
            print(f"  Raw response: {body[:200] if body else '(empty)'}")
            return {
                "status": response.status,
                "body": json.loads(body) if body else {}
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.read() else ""
        print(f"  HTTP Error {e.code}: {body[:200]}")
        return {
            "status": e.code,
            "body": body
        }
    except Exception as e:
        print(f"  Exception: {e}")
        return {
            "status": 0,
            "body": str(e)
        }

print("Testing GCP API Endpoints")
print("=" * 50)

# Test 1: Check available endpoints
print("\n1. Testing GET /marketplace/services")
result = make_request("/marketplace/services", headers={"X-API-Key": API_KEY})
print(f"   Status: {result['status']}")
print(f"   Body: {result['body']}")

# Test 2: Check if endpoint exists (OPTIONS)
print("\n2. Testing POST /marketplace/services with minimal data")
service_data = {
    "name": "Test Service",
    "description": "Test",
    "service_type": "ai_service",
    "endpoint": f"{API_BASE}/test",
    "pricing_model": "fixed",
    "price": 1.0,
    "capabilities": ["test"]
}
result = make_request("/marketplace/services", "POST", service_data, {"X-API-Key": API_KEY})
print(f"   Status: {result['status']}")
print(f"   Body: {result['body']}")

# Test 3: Check auth endpoint
print("\n3. Testing /auth/token")
auth_data = {"entity_id": ENTITY_ID, "api_key": API_KEY}
result = make_request("/auth/token", "POST", auth_data)
print(f"   Status: {result['status']}")
if result['status'] == 200:
    print(f"   Token received: {result['body'].get('token', 'N/A')[:30]}...")
else:
    print(f"   Body: {result['body']}")
