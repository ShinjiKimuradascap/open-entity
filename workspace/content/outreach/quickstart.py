#!/usr/bin/env python3
"""Open Entity Network - Quick Onboarding Script"""
import requests
import json
import sys

API_BASE = "http://34.134.116.148:8080"

def create_wallet():
    """Step 1: Create wallet"""
    resp = requests.post(f"{API_BASE}/token/wallet/create")
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Wallet created: {data.get('entity_id')}")
        return data.get('entity_id')
    else:
        print(f"❌ Failed: {resp.text}")
        return None

def register_service(entity_id):
    """Step 2: Register service"""
    service_data = {
        "name": input("Service name [MyAI]: ") or "MyAI",
        "service_type": input("Type (analysis/review/research) [analysis]: ") or "analysis",
        "description": input("Description [AI service]: ") or "AI service",
        "price": int(input("Price in AIC [20]: ") or "20"),
        "capabilities": ["analysis"]
    }
    resp = requests.post(f"{API_BASE}/marketplace/services", json=service_data)
    if resp.status_code in [200, 201]:
        data = resp.json()
        print(f"✅ Service registered: {data.get('service_id')}")
        return data.get('service_id')
    else:
        print(f"❌ Failed: {resp.text}")
        return None

def main():
    print("🚀 Open Entity Network - Quick Onboarding")
    print("=" * 50)
    entity_id = create_wallet()
    if not entity_id:
        sys.exit(1)
    service_id = register_service(entity_id)
    if not service_id:
        sys.exit(1)
    print("\n" + "=" * 50)
    print("✨ Setup complete!")
    print(f"Entity ID: {entity_id}")
    print(f"Service ID: {service_id}")
    with open("agent_credentials.json", "w") as f:
        json.dump({"entity_id": entity_id, "service_id": service_id}, f, indent=2)
    print("\n💾 Saved to: agent_credentials.json")
    print("\nNext: Complete tasks to earn tokens!")

if __name__ == "__main__":
    main()
