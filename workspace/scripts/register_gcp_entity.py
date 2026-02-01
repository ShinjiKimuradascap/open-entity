#!/usr/bin/env python3
import urllib.request
import json
import sys
from datetime import datetime

API_BASE = "http://34.134.116.148:8080"
ENTITY_ID = f"open-entity-orchestrator-{int(datetime.now().timestamp())}"

def register():
    payload = {
        "entity_id": ENTITY_ID,
        "name": "Open Entity Orchestrator",
        "endpoint": API_BASE,
        "capabilities": ["task_orchestration", "code_generation", "code_review"],
        "public_key": None
    }
    
    req = urllib.request.Request(
        f"{API_BASE}/register",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    print("Registering Open Entity to GCP API Server...")
    result = register()
    if result:
        print(f"Success!")
        print(f"Entity ID: {result.get('entity_id')}")
        print(f"API Key: {result.get('api_key')}")
        with open(".gcp_api_key", "w") as f:
            f.write(f"GCP_API_KEY={result.get('api_key')}\n")
        print("Saved to .gcp_api_key")

if __name__ == "__main__":
    main()
