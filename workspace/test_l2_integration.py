#!/usr/bin/env python3
"""
L2 Integration Test
L2統合テスト

Tests all L2 components:
- Bootstrap Server
- Discovery Manager
- DHT Registry
- Relay Service
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from bootstrap_server import BootstrapServer
from bootstrap_discovery import BootstrapDiscoveryManager, DiscoveryMode
from kademlia_dht import DHTRegistry, PeerInfo
from relay_service import RelayService


async def test_all_l2_components():
    """すべてのL2コンポーネントをテスト"""
    print("="*60)
    print("L2 Integration Test - All Components")
    print("="*60)
    
    results = {}
    
    # Test 1: Bootstrap Server
    print("\n--- Testing Bootstrap Server ---")
    try:
        server = BootstrapServer(host="localhost", port=19000)
        await server.register_peer(
            entity_id="test-1",
            address="http://localhost:8001",
            public_key="test_key",
            capabilities=["test"]
        )
        peers = await server.get_peer_list()
        assert len(peers) == 1
        print(f"Bootstrap Server: OK ({len(peers)} peers)")
        results["bootstrap"] = "PASS"
    except Exception as e:
        print(f"Bootstrap Server: FAIL - {e}")
        results["bootstrap"] = "FAIL"
    
    # Test 2: Discovery Manager
    print("\n--- Testing Discovery Manager ---")
    try:
        manager = BootstrapDiscoveryManager(
            verify_signatures=False,
            discovery_mode=DiscoveryMode.HTTP_ONLY
        )
        stats = manager.get_stats()
        print(f"Discovery Manager: OK (DHT available: {stats['dht_available']})")
        results["discovery"] = "PASS"
    except Exception as e:
        print(f"Discovery Manager: FAIL - {e}")
        results["discovery"] = "FAIL"
    
    # Test 3: DHT
    print("\n--- Testing DHT ---")
    try:
        peer = PeerInfo(
            peer_id="test-peer",
            endpoint="http://localhost:8001",
            public_key="test_key"
        )
        peer_dict = peer.to_dict()
        peer2 = PeerInfo.from_dict(peer_dict)
        assert peer2.peer_id == peer.peer_id
        print(f"DHT PeerInfo: OK")
        results["dht"] = "PASS"
    except Exception as e:
        print(f"DHT: FAIL - {e}")
        results["dht"] = "FAIL"
    
    # Test 4: Relay Service
    print("\n--- Testing Relay Service ---")
    try:
        from relay_service import RelayPeer, RelayMessage, RelayStatus
        peer = RelayPeer(
            entity_id="test-relay",
            public_key="test_key",
            registered_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc),
            last_heartbeat=__import__('datetime').datetime.now(__import__('datetime').timezone.utc),
            connection_info={}
        )
        print(f"Relay Service: OK")
        results["relay"] = "PASS"
    except Exception as e:
        print(f"Relay Service: FAIL - {e}")
        results["relay"] = "FAIL"
    
    # Summary
    print("\n" + "="*60)
    print("Test Results Summary")
    print("="*60)
    for component, result in results.items():
        status = "PASS" if result == "PASS" else "FAIL"
        icon = "OK" if result == "PASS" else "NG"
        print(f"  {icon} {component}: {status}")
    
    passed = sum(1 for r in results.values() if r == "PASS")
    total = len(results)
    print(f"\nTotal: {passed}/{total} passed")
    print("="*60)
    
    return all(r == "PASS" for r in results.values())


if __name__ == "__main__":
    try:
        success = asyncio.run(test_all_l2_components())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
