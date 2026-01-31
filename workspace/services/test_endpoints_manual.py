#!/usr/bin/env python3
"""
Manual endpoint test for /health, /stats, /keys/public
"""

import sys
import os

# Add services directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock environment variables before importing modules
os.environ["JWT_SECRET"] = "test-secret-key-for-jwt-tokens"
os.environ["ENTITY_ID"] = "test-server"
os.environ["PORT"] = "8000"
os.environ["ENTITY_PRIVATE_KEY"] = ""  # Generate new key if empty

from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

# Import after setting env vars
import api_server


def create_test_client():
    """Create test client with mocked dependencies"""
    mock_registry = Mock()
    mock_registry.list_all.return_value = []
    mock_registry.find_by_id.return_value = None
    mock_registry.register.return_value = True
    mock_registry.unregister.return_value = True
    mock_registry.heartbeat.return_value = True
    mock_registry.stats.return_value = {
        "registered_agents": 5,
        "total_messages": 100,
        "active_peers": 3
    }
    
    with patch.object(api_server, 'registry', mock_registry):
        with patch.object(api_server, 'get_registry', return_value=mock_registry):
            return TestClient(api_server.app)


def test_health_endpoint():
    """Test /health endpoint"""
    print("\n" + "="*60)
    print("TEST 1: /health endpoint")
    print("="*60)
    
    client = create_test_client()
    response = client.get("/health")
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    assert data["status"] == "healthy", f"Expected status 'healthy', got {data.get('status')}"
    assert "version" in data, "Missing 'version' field"
    assert "security_features" in data, "Missing 'security_features' field"
    
    print("✓ /health endpoint PASSED")
    return True


def test_stats_endpoint():
    """Test /stats endpoint"""
    print("\n" + "="*60)
    print("TEST 2: /stats endpoint")
    print("="*60)
    
    client = create_test_client()
    response = client.get("/stats")
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Stats endpoint may require auth, so accept 200 or 401
    if response.status_code == 200:
        data = response.json()
        assert "registered_agents" in data or "agents" in data, "Missing agents count"
        print("✓ /stats endpoint PASSED (no auth required)")
    elif response.status_code == 401:
        print("⚠ /stats endpoint requires authentication (expected)")
        print("✓ /stats endpoint PASSED (auth check working)")
    else:
        print(f"✗ Unexpected status code: {response.status_code}")
        return False
    
    return True


def test_keys_public_endpoint():
    """Test /keys/public endpoint"""
    print("\n" + "="*60)
    print("TEST 3: /keys/public endpoint")
    print("="*60)
    
    client = create_test_client()
    response = client.get("/keys/public")
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    assert "public_key" in data, "Missing 'public_key' field"
    assert "algorithm" in data, "Missing 'algorithm' field"
    assert data["algorithm"] == "Ed25519", f"Expected algorithm 'Ed25519', got {data.get('algorithm')}"
    
    print("✓ /keys/public endpoint PASSED")
    return True


if __name__ == "__main__":
    print("\n" + "="*60)
    print("API SERVER ENDPOINT TESTS")
    print("="*60)
    
    results = []
    
    try:
        results.append(("/health", test_health_endpoint()))
    except Exception as e:
        print(f"✗ /health endpoint FAILED: {e}")
        results.append(("/health", False))
    
    try:
        results.append(("/stats", test_stats_endpoint()))
    except Exception as e:
        print(f"✗ /stats endpoint FAILED: {e}")
        results.append(("/stats", False))
    
    try:
        results.append(("/keys/public", test_keys_public_endpoint()))
    except Exception as e:
        print(f"✗ /keys/public endpoint FAILED: {e}")
        results.append(("/keys/public", False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for endpoint, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{endpoint}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        sys.exit(1)
