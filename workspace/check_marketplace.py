#!/usr/bin/env python3
"""Check marketplace services"""
import urllib.request
import json

API_BASE = "http://34.134.116.148:8080"

def check_services():
    req = urllib.request.Request(
        f"{API_BASE}/discover",
        method='GET'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            print("=== Registered Services ===")
            services = data.get('services', [])
            if services:
                for svc in services:
                    print(f"- {svc.get('name')}: {svc.get('price')} AIC")
            else:
                print("No services registered")
            return services
    except Exception as e:
        print(f"Error: {e}")
        return []

def check_agents():
    # Use /discover with different parameters
    print("\n=== Checking Service Registry ===")
    req = urllib.request.Request(
        f"{API_BASE}/discover?service_type=agent",
        method='GET'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            print("\n=== Registered Agents ===")
            agents = data.get('agents', [])
            print(f"Count: {len(agents)}")
            for agent in agents[:5]:  # Show first 5
                print(f"- {agent.get('id', 'N/A')}: {agent.get('status', 'unknown')}")
            return agents
    except Exception as e:
        print(f"Error: {e}")
        return []

if __name__ == "__main__":
    check_services()
    check_agents()
