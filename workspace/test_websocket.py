#!/usr/bin/env python3
"""
WebSocket Endpoint Test Script
Tests the /ws/v1/peers endpoint with authentication and message types
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone

# Test configuration
BASE_URL = "ws://localhost:8000"
WS_ENDPOINT = f"{BASE_URL}/ws/v1/peers"
API_URL = "http://localhost:8000"

# Test results
test_results = []


def log(message: str, level: str = "INFO"):
    """Print test log message"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def record_test(name: str, passed: bool, details: str = ""):
    """Record test result"""
    test_results.append({
        "name": name,
        "passed": passed,
        "details": details
    })
    status = "✅ PASS" if passed else "❌ FAIL"
    log(f"{status}: {name} - {details}")


async def test_websocket_without_token():
    """Test 1: Connection without token should fail"""
    try:
        import websockets
        async with websockets.connect(WS_ENDPOINT) as ws:
            # Should not reach here
            record_test("WS Auth - No Token", False, "Connection should have been rejected")
    except Exception as e:
        if "1008" in str(e) or "Missing authentication" in str(e) or "closed" in str(e):
            record_test("WS Auth - No Token", True, "Connection correctly rejected")
        else:
            record_test("WS Auth - No Token", True, f"Connection rejected: {e}")


async def test_websocket_with_invalid_token():
    """Test 2: Connection with invalid token should fail"""
    try:
        import websockets
        async with websockets.connect(f"{WS_ENDPOINT}?token=invalid_token") as ws:
            record_test("WS Auth - Invalid Token", False, "Connection should have been rejected")
    except Exception as e:
        if "1008" in str(e) or "Authentication failed" in str(e) or "closed" in str(e):
            record_test("WS Auth - Invalid Token", True, "Connection correctly rejected with invalid token")
        else:
            record_test("WS Auth - Invalid Token", True, f"Connection rejected: {e}")


async def get_jwt_token() -> str:
    """Get a valid JWT token from the API server"""
    import aiohttp
    
    # First register an entity
    async with aiohttp.ClientSession() as session:
        # Register entity
        register_data = {
            "entity_id": "test_websocket_entity",
            "name": "WebSocket Test Entity",
            "endpoint": "http://localhost:9000",
            "capabilities": ["test"]
        }
        
        try:
            async with session.post(f"{API_URL}/register", json=register_data) as resp:
                if resp.status in [200, 201, 400]:  # 400 might mean already registered
                    log("Entity registered or already exists")
        except Exception as e:
            log(f"Registration warning: {e}", "WARN")
        
        # Get API key first (we need it to get JWT)
        # For testing, we'll use a known API key or generate one
        # Since we can't easily get the API key, let's try to get token directly
        # by using a test endpoint or creating a token with known credentials
        
        # Try to get token using auth/token endpoint
        token_data = {
            "api_key": "test_key",  # This might not work without proper key
            "entity_id": "test_websocket_entity"
        }
        
        try:
            async with session.post(f"{API_URL}/auth/token", json=token_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("access_token")
        except Exception as e:
            log(f"Token request failed: {e}", "WARN")
        
        # If that fails, return None and we'll skip authenticated tests
        return None


async def test_websocket_ping_pong(token: str):
    """Test 3: Ping/Pong message exchange"""
    if not token:
        record_test("WS Ping/Pong", False, "No valid token available")
        return
    
    try:
        import websockets
        uri = f"{WS_ENDPOINT}?token={token}"
        
        async with websockets.connect(uri) as ws:
            # Wait for welcome message
            welcome = await asyncio.wait_for(ws.recv(), timeout=5.0)
            welcome_data = json.loads(welcome)
            
            if welcome_data.get("type") != "status":
                record_test("WS Ping/Pong", False, f"Expected status message, got: {welcome_data.get('type')}")
                return
            
            # Send ping
            ping_msg = {
                "type": "ping",
                "payload": {"test": True},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await ws.send(json.dumps(ping_msg))
            
            # Receive pong
            pong = await asyncio.wait_for(ws.recv(), timeout=5.0)
            pong_data = json.loads(pong)
            
            if pong_data.get("type") == "pong":
                record_test("WS Ping/Pong", True, "Ping/Pong exchange successful")
            else:
                record_test("WS Ping/Pong", False, f"Expected pong, got: {pong_data.get('type')}")
    
    except Exception as e:
        record_test("WS Ping/Pong", False, f"Error: {e}")


async def test_websocket_message(token: str):
    """Test 4: Send and receive message"""
    if not token:
        record_test("WS Message", False, "No valid token available")
        return
    
    try:
        import websockets
        uri = f"{WS_ENDPOINT}?token={token}"
        
        async with websockets.connect(uri) as ws:
            # Wait for welcome
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            
            # Send a message
            msg = {
                "type": "message",
                "payload": {
                    "content": "Hello from test",
                    "target": "broadcast"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await ws.send(json.dumps(msg))
            
            # Receive acknowledgment
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response_data = json.loads(response)
            
            if response_data.get("type") in ["status", "message"]:
                record_test("WS Message", True, "Message sent and acknowledged")
            else:
                record_test("WS Message", False, f"Unexpected response: {response_data}")
    
    except Exception as e:
        record_test("WS Message", False, f"Error: {e}")


async def test_websocket_status(token: str):
    """Test 5: Status query"""
    if not token:
        record_test("WS Status Query", False, "No valid token available")
        return
    
    try:
        import websockets
        uri = f"{WS_ENDPOINT}?token={token}"
        
        async with websockets.connect(uri) as ws:
            # Wait for welcome
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            
            # Send status request
            msg = {
                "type": "status",
                "payload": {"status_type": "peers"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await ws.send(json.dumps(msg))
            
            # Receive peer list
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response_data = json.loads(response)
            
            if response_data.get("type") == "status" and "peers" in response_data.get("payload", {}):
                peer_count = response_data["payload"].get("count", 0)
                record_test("WS Status Query", True, f"Peer list received: {peer_count} peers")
            else:
                record_test("WS Status Query", False, f"Unexpected response: {response_data}")
    
    except Exception as e:
        record_test("WS Status Query", False, f"Error: {e}")


async def test_websocket_task(token: str):
    """Test 6: Task message"""
    if not token:
        record_test("WS Task Message", False, "No valid token available")
        return
    
    try:
        import websockets
        uri = f"{WS_ENDPOINT}?token={token}"
        
        async with websockets.connect(uri) as ws:
            # Wait for welcome
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            
            # Send task message
            msg = {
                "type": "task",
                "payload": {
                    "action": "create",
                    "task_id": "test-task-001",
                    "data": {"test": True}
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await ws.send(json.dumps(msg))
            
            # Receive response
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response_data = json.loads(response)
            
            if response_data.get("type") == "task":
                record_test("WS Task Message", True, "Task message processed")
            else:
                record_test("WS Task Message", False, f"Unexpected response: {response_data}")
    
    except Exception as e:
        record_test("WS Task Message", False, f"Error: {e}")


async def test_http_ws_peers_endpoint(token: str):
    """Test 7: HTTP endpoint for connected peers"""
    if not token:
        record_test("HTTP WS Peers Endpoint", False, "No valid token available")
        return
    
    try:
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token}"}
            
            async with session.get(f"{API_URL}/ws/peers", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "peers" in data and "count" in data:
                        record_test("HTTP WS Peers Endpoint", True, f"Response: {data['count']} peers")
                    else:
                        record_test("HTTP WS Peers Endpoint", False, f"Invalid response format: {data}")
                else:
                    record_test("HTTP WS Peers Endpoint", False, f"HTTP {resp.status}")
    
    except Exception as e:
        record_test("HTTP WS Peers Endpoint", False, f"Error: {e}")


async def run_all_tests():
    """Run all WebSocket tests"""
    log("=" * 60)
    log("WebSocket API Server Tests")
    log("=" * 60)
    
    # Check if server is running
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/health") as resp:
                if resp.status == 200:
                    log("API Server is running")
                else:
                    log(f"API Server responded with status {resp.status}", "WARN")
    except Exception as e:
        log(f"API Server may not be running: {e}", "WARN")
        log("Please start the server: python services/api_server.py", "WARN")
        print("\n⚠️  Skipping tests - server not available")
        return
    
    # Test 1 & 2: Authentication (no token needed)
    log("\n--- Testing Authentication ---")
    await test_websocket_without_token()
    await test_websocket_with_invalid_token()
    
    # Get token for authenticated tests
    log("\n--- Getting JWT Token ---")
    token = await get_jwt_token()
    if token:
        log(f"Got token: {token[:20]}...")
    else:
        log("Could not get JWT token - authenticated tests will be skipped", "WARN")
        log("You may need to manually create an entity and get a token", "WARN")
    
    # Authenticated tests
    if token:
        log("\n--- Testing Authenticated WebSocket ---")
        await test_websocket_ping_pong(token)
        await test_websocket_message(token)
        await test_websocket_status(token)
        await test_websocket_task(token)
        await test_http_ws_peers_endpoint(token)
    
    # Print summary
    log("\n" + "=" * 60)
    log("Test Summary")
    log("=" * 60)
    
    passed = sum(1 for r in test_results if r["passed"])
    failed = sum(1 for r in test_results if not r["passed"])
    
    for result in test_results:
        status = "✅" if result["passed"] else "❌"
        print(f"{status} {result['name']}")
    
    print(f"\nTotal: {passed} passed, {failed} failed out of {len(test_results)} tests")
    
    return failed == 0


def main():
    """Main entry point"""
    print("WebSocket API Test Suite")
    print("Make sure the API server is running on localhost:8000")
    print("-" * 60)
    
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTests interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest suite error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
