#!/usr/bin/env python3
"""GCP API Server 状態確認とエージェント登録スクリプト"""
import requests
import json
import os
from datetime import datetime

API_ENDPOINT = "http://34.134.116.148:8080"
ENTITY_ID = "open-entity-orchestrator-1738377841"
API_KEY = "ak_ISMi3N1CyJiB7FnhzH0KMrBzch8LKWhHtEZAtM8Ewcw"

def check_health():
    """ヘルスチェック"""
    try:
        resp = requests.get(f"{API_ENDPOINT}/health", timeout=10)
        print(f"Health Status: {resp.status_code}")
        print(json.dumps(resp.json(), indent=2))
        return resp.status_code == 200
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

def register_agent():
    """エージェント登録"""
    payload = {
        "entity_id": ENTITY_ID,
        "name": "Open Entity Orchestrator",
        "type": "orchestrator",
        "version": "1.0.0",
        "capabilities": ["task_management", "delegation", "coordination"],
        "endpoint": "http://localhost:8080",
        "public_key": "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA7pKaT7K1eR8+NH2gDz9tKfC2K3vP5L8Q9R0T1U2V3W=\n-----END PUBLIC KEY-----"
    }
    
    try:
        resp = requests.post(
            f"{API_ENDPOINT}/register",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"\nRegister Status: {resp.status_code}")
        print(json.dumps(resp.json(), indent=2))
        return resp.status_code == 200
    except Exception as e:
        print(f"Registration failed: {e}")
        return False

def register_services():
    """マーケットプレイスサービス登録"""
    services = [
        {
            "service_id": "task-delegation-001",
            "name": "Task Delegation",
            "description": "Delegate tasks to sub-agents",
            "service_type": "compute",
            "price": 10,
            "currency": "AIC",
            "provider_id": ENTITY_ID
        },
        {
            "service_id": "code-review-001", 
            "name": "Code Review",
            "description": "Automated code review service",
            "service_type": "compute",
            "price": 5,
            "currency": "AIC",
            "provider_id": ENTITY_ID
        }
    ]
    
    results = []
    for service in services:
        try:
            resp = requests.post(
                f"{API_ENDPOINT}/marketplace/services",
                json=service,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            print(f"\nService '{service['name']}' Status: {resp.status_code}")
            print(json.dumps(resp.json(), indent=2))
            results.append((service['name'], resp.status_code == 200))
        except Exception as e:
            print(f"Service registration failed: {e}")
            results.append((service['name'], False))
    
    return results

if __name__ == "__main__":
    print("="*60)
    print(f"GCP API Server Check - {datetime.now()}")
    print("="*60)
    
    # 1. Health check
    print("\n[1/3] Health Check")
    print("-"*40)
    health_ok = check_health()
    
    # 2. Register agent
    print("\n[2/3] Agent Registration")
    print("-"*40)
    reg_ok = register_agent()
    
    # 3. Register services
    print("\n[3/3] Service Registration")
    print("-"*40)
    svc_results = register_services()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Health Check: {'✅ PASS' if health_ok else '❌ FAIL'}")
    print(f"Agent Registration: {'✅ PASS' if reg_ok else '❌ FAIL'}")
    print(f"Services Registered: {sum(1 for _, ok in svc_results if ok)}/{len(svc_results)}")
