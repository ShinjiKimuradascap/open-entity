#!/usr/bin/env python3
"""
DHT Network Integration Test
Tests integration of:
- bootstrap_discovery.py
- kademlia_dht.py
- dht_node.py
- nat_traversal.py (optional)
"""

import sys
import os
import asyncio

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

print('=== DHT Network Integration Test ===')


def test_imports():
    """Test module imports"""
    print('\n--- Test 1: Module Imports ---')
    
    try:
        from services.kademlia_dht import DHTRegistry, PeerInfo
        print('  kademlia_dht: OK')
    except ImportError as e:
        print(f'  kademlia_dht: FAILED - {e}')
        return False
    
    try:
        from services.bootstrap_discovery import (
            BootstrapDiscoveryManager,
            BootstrapNodeInfo,
            DiscoveryMode
        )
        print('  bootstrap_discovery: OK')
    except ImportError as e:
        print(f'  bootstrap_discovery: FAILED - {e}')
        return False
    
    try:
        from services.dht_node import DHTNode, NodeID, NodeInfo
        print('  dht_node: OK')
    except ImportError as e:
        print(f'  dht_node: FAILED - {e}')
        return False
    
    try:
        from services.nat_traversal import NATTraversalManager, TraversalConfig
        print('  nat_traversal: OK')
    except ImportError as e:
        print(f'  nat_traversal: FAILED - {e}')
        return False
    
    print('  All imports successful')
    return True


def test_peer_info():
    """Test PeerInfo dataclass"""
    print('\n--- Test 2: PeerInfo ---')
    
    from services.kademlia_dht import PeerInfo
    
    peer = PeerInfo(
        peer_id="test-entity-1",
        endpoint="http://localhost:8000",
        public_key="test-pubkey",
        capabilities=["chat", "code"]
    )
    
    print(f'  Created peer: {peer.peer_id}')
    print(f'  Endpoint: {peer.endpoint}')
    print(f'  Capabilities: {peer.capabilities}')
    
    # Test serialization
    data = peer.to_dict()
    peer2 = PeerInfo.from_dict(data)
    
    assert peer.peer_id == peer2.peer_id
    assert peer.endpoint == peer2.endpoint
    print('  Serialization: OK')
    
    return True


def test_discovery_manager_creation():
    """Test BootstrapDiscoveryManager creation"""
    print('\n--- Test 3: BootstrapDiscoveryManager ---')
    
    from services.bootstrap_discovery import BootstrapDiscoveryManager, DiscoveryMode
    
    manager = BootstrapDiscoveryManager(
        entity_id="test-entity",
        entity_name="Test Entity",
        endpoint="http://localhost:8000",
        public_key="test-public-key",
        capabilities=["discovery", "relay"],
        discovery_mode=DiscoveryMode.HTTP_ONLY
    )
    
    print(f'  Created manager for: {manager.entity_id}')
    print(f'  Discovery mode: {manager.discovery_mode}')
    
    # Test stats
    stats = manager.get_stats()
    print(f'  Stats: {stats}')
    
    return True


def test_dht_node_creation():
    """Test DHTNode creation"""
    print('\n--- Test 4: DHTNode ---')
    
    from services.dht_node import DHTNode, NodeID
    
    node = DHTNode(
        host="127.0.0.1",
        port=0,  # Auto-assign
        node_id=NodeID("test-node-1")
    )
    
    print(f'  Created DHT node: {node.node_id}')
    print(f'  Stats: {node.get_stats()}')
    
    return True


def test_nat_traversal_creation():
    """Test NATTraversalManager creation"""
    print('\n--- Test 5: NATTraversalManager ---')
    
    from services.nat_traversal import NATTraversalManager, TraversalConfig
    
    config = TraversalConfig(timeout=3.0)
    manager = NATTraversalManager(config)
    
    print(f'  Created NAT manager')
    print(f'  Config: timeout={manager.config.timeout}')
    
    return True


def test_integration_flow():
    """Test integration workflow"""
    print('\n--- Test 6: Integration Flow ---')
    
    from services.bootstrap_discovery import BootstrapDiscoveryManager, DiscoveryMode
    from services.kademlia_dht import PeerInfo
    
    # Create discovery manager
    manager = BootstrapDiscoveryManager(
        entity_id="integration-test-entity",
        entity_name="Integration Test",
        endpoint="http://localhost:8000",
        public_key="test-key",
        capabilities=["dht", "discovery"],
        discovery_mode=DiscoveryMode.HTTP_ONLY
    )
    
    print(f'  Manager created: {manager.entity_id}')
    
    # Test bootstrap config loading
    addrs = manager._get_dht_bootstrap_addresses()
    print(f'  DHT bootstrap addresses: {addrs}')
    
    # Test PeerInfo creation (for DHT registration)
    peer = PeerInfo(
        peer_id=manager.entity_id,
        endpoint=manager.endpoint,
        public_key=manager.public_key,
        capabilities=manager.capabilities
    )
    print(f'  PeerInfo created: {peer.peer_id}')
    
    return True


async def test_async_operations():
    """Test async operations"""
    print('\n--- Test 7: Async Operations ---')
    
    from services.stun_client import StunClient, DEFAULT_STUN_SERVERS
    
    client = StunClient(timeout=3.0)
    
    # Test STUN request (may fail in restricted network)
    print('  Testing STUN request...')
    try:
        response = await client.binding_request(
            DEFAULT_STUN_SERVERS[0][0],
            DEFAULT_STUN_SERVERS[0][1]
        )
        
        if response.success:
            print(f'  STUN success: {response.mapped_endpoint}')
        else:
            print(f'  STUN failed: {response.error_reason}')
    except Exception as e:
        print(f'  STUN exception (expected in some environments): {e}')
    
    return True


def main():
    """Run all tests"""
    print('Starting DHT Network Integration Tests\n')
    
    tests = [
        test_imports,
        test_peer_info,
        test_discovery_manager_creation,
        test_dht_node_creation,
        test_nat_traversal_creation,
        test_integration_flow,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback
            traceback.print_exc()
            failed += 1
    
    # Async tests
    try:
        if asyncio.run(test_async_operations()):
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f'  Async test ERROR: {e}')
        failed += 1
    
    print(f'\n=== Test Results ===')
    print(f'  Passed: {passed}')
    print(f'  Failed: {failed}')
    print(f'  Total: {passed + failed}')
    
    if failed == 0:
        print('\n  All tests passed!')
        return 0
    else:
        print(f'\n  {failed} test(s) failed')
        return 1


if __name__ == "__main__":
    sys.exit(main())
