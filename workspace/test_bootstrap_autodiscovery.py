#!/usr/bin/env python3
"""Test script for Bootstrap Auto-Discovery (S1)

Tests:
1. _parse_dht_endpoint() - Parse endpoint strings
2. load_bootstrap_nodes() - Load and merge bootstrap nodes
3. __init__ with bootstrap_config_path - Auto-discovery on initialization
4. Error handling - Missing files, invalid formats
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# Add services directory to path
sys.path.insert(0, str(Path(__file__).parent / "services"))

from dht_registry import DHTRegistry


def test_parse_dht_endpoint():
    """Test _parse_dht_endpoint helper method"""
    print("\n=== Test: _parse_dht_endpoint() ===")
    
    # Create minimal registry for testing
    registry = DHTRegistry(
        entity_id="test-entity",
        entity_name="Test Entity",
        endpoint="http://localhost:8000",
        public_key="test-public-key",
        capabilities=["test"]
    )
    
    # Valid endpoints
    test_cases = [
        ("127.0.0.1:8468", ("127.0.0.1", 8468)),
        ("bootstrap1.ai-network.local:8468", ("bootstrap1.ai-network.local", 8468)),
        ("192.168.1.100:9000", ("192.168.1.100", 9000)),
        ("[::1]:8080", ("[::1", 8080)),  # IPv6 (partial)
    ]
    
    for endpoint, expected in test_cases:
        result = registry._parse_dht_endpoint(endpoint)
        assert result == expected, f"Failed for {endpoint}: got {result}, expected {expected}"
        print(f"  ✓ {endpoint} -> {result}")
    
    # Invalid endpoints
    invalid_cases = [
        "invalid-endpoint",
        "missing-port",
        ":8080",
        "",
    ]
    
    for endpoint in invalid_cases:
        try:
            registry._parse_dht_endpoint(endpoint)
            assert False, f"Should have raised ValueError for {endpoint}"
        except ValueError:
            print(f"  ✓ {endpoint} correctly raised ValueError")
    
    print("  All tests passed!")


def test_load_bootstrap_nodes():
    """Test load_bootstrap_nodes method"""
    print("\n=== Test: load_bootstrap_nodes() ===")
    
    # Create test config file
    test_config = {
        "bootstrap_servers": [
            {
                "node_id": "bootstrap-001",
                "endpoint": "https://bootstrap1.ai-network.local",
                "dht_endpoint": "bootstrap1.ai-network.local:8468",
                "priority": 1,
                "capabilities": ["discovery", "relay", "registry", "dht"]
            },
            {
                "node_id": "bootstrap-002",
                "endpoint": "https://bootstrap2.ai-network.local",
                "dht_endpoint": "bootstrap2.ai-network.local:8468",
                "priority": 2,
                "capabilities": ["discovery", "relay", "dht"]
            }
        ],
        "local_bootstrap": [
            {
                "node_id": "local-bootstrap-1",
                "endpoint": "http://localhost:9000",
                "dht_endpoint": "127.0.0.1:8468",
                "priority": 0,
                "capabilities": ["discovery", "relay", "registry", "dht"]
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_config, f)
        temp_path = f.name
    
    try:
        # Create registry and load nodes
        registry = DHTRegistry(
            entity_id="test-entity",
            entity_name="Test Entity",
            endpoint="http://localhost:8000",
            public_key="test-public-key",
            capabilities=["test"]
        )
        
        nodes = registry.load_bootstrap_nodes(temp_path)
        
        # Verify results
        assert len(nodes) == 3, f"Expected 3 nodes, got {len(nodes)}"
        
        # Check priority sorting (lower priority = first)
        expected_order = [
            ("127.0.0.1", 8468),      # priority 0 (local)
            ("bootstrap1.ai-network.local", 8468),  # priority 1
            ("bootstrap2.ai-network.local", 8468),  # priority 2
        ]
        
        for i, (expected, actual) in enumerate(zip(expected_order, nodes)):
            assert actual == expected, f"Node {i}: expected {expected}, got {actual}"
            print(f"  ✓ Node {i}: {actual[0]}:{actual[1]}")
        
        print("  All tests passed!")
        
    finally:
        os.unlink(temp_path)


def test_auto_load_on_init():
    """Test auto-loading bootstrap nodes on __init__"""
    print("\n=== Test: __init__ with bootstrap_config_path ===")
    
    # Create test config file
    test_config = {
        "bootstrap_servers": [
            {
                "node_id": "bootstrap-001",
                "dht_endpoint": "192.168.1.10:8468",
                "priority": 1
            }
        ],
        "local_bootstrap": [
            {
                "node_id": "local-001",
                "dht_endpoint": "127.0.0.1:8468",
                "priority": 0
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_config, f)
        temp_path = f.name
    
    try:
        # Create registry with auto-discovery
        registry = DHTRegistry(
            entity_id="test-entity",
            entity_name="Test Entity",
            endpoint="http://localhost:8000",
            public_key="test-public-key",
            capabilities=["test"],
            bootstrap_config_path=temp_path
        )
        
        # Verify nodes were loaded
        assert len(registry.bootstrap_nodes) == 2, f"Expected 2 nodes, got {len(registry.bootstrap_nodes)}"
        assert registry.bootstrap_nodes[0] == ("127.0.0.1", 8468), "First node should be local (priority 0)"
        assert registry.bootstrap_nodes[1] == ("192.168.1.10", 8468), "Second node should be bootstrap (priority 1)"
        
        print(f"  ✓ Auto-loaded {len(registry.bootstrap_nodes)} nodes")
        for host, port in registry.bootstrap_nodes:
            print(f"    - {host}:{port}")
        
        print("  All tests passed!")
        
    finally:
        os.unlink(temp_path)


def test_explicit_bootstrap_nodes_override():
    """Test that explicit bootstrap_nodes overrides auto-discovery"""
    print("\n=== Test: Explicit bootstrap_nodes overrides config ===")
    
    test_config = {
        "bootstrap_servers": [
            {"node_id": "bs-001", "dht_endpoint": "10.0.0.1:8468", "priority": 1}
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_config, f)
        temp_path = f.name
    
    try:
        explicit_nodes = [("192.168.1.1", 9000), ("192.168.1.2", 9000)]
        
        # Create registry with both explicit nodes and config path
        registry = DHTRegistry(
            entity_id="test-entity",
            entity_name="Test Entity",
            endpoint="http://localhost:8000",
            public_key="test-public-key",
            capabilities=["test"],
            bootstrap_nodes=explicit_nodes,
            bootstrap_config_path=temp_path
        )
        
        # Explicit nodes should take precedence
        assert registry.bootstrap_nodes == explicit_nodes, "Explicit nodes should override config"
        
        print(f"  ✓ Explicit nodes used: {registry.bootstrap_nodes}")
        print("  All tests passed!")
        
    finally:
        os.unlink(temp_path)


def test_error_handling():
    """Test error handling for edge cases"""
    print("\n=== Test: Error Handling ===")
    
    registry = DHTRegistry(
        entity_id="test-entity",
        entity_name="Test Entity",
        endpoint="http://localhost:8000",
        public_key="test-public-key",
        capabilities=["test"]
    )
    
    # Non-existent file
    nodes = registry.load_bootstrap_nodes("/nonexistent/path/config.json")
    assert nodes == [], f"Expected empty list for missing file, got {nodes}"
    print("  ✓ Missing file handled gracefully")
    
    # Invalid JSON
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("invalid json {{{")
        temp_path = f.name
    
    try:
        nodes = registry.load_bootstrap_nodes(temp_path)
        assert nodes == [], f"Expected empty list for invalid JSON, got {nodes}"
        print("  ✓ Invalid JSON handled gracefully")
    finally:
        os.unlink(temp_path)
    
    # Empty config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({}, f)
        temp_path = f.name
    
    try:
        nodes = registry.load_bootstrap_nodes(temp_path)
        assert nodes == [], f"Expected empty list for empty config, got {nodes}"
        print("  ✓ Empty config handled gracefully")
    finally:
        os.unlink(temp_path)
    
    print("  All tests passed!")


def test_with_real_config():
    """Test with actual config/bootstrap_nodes.json"""
    print("\n=== Test: Real Config File ===")
    
    config_path = Path(__file__).parent / "config" / "bootstrap_nodes.json"
    
    if not config_path.exists():
        print(f"  ⚠ Skipping: Real config not found at {config_path}")
        return
    
    registry = DHTRegistry(
        entity_id="test-entity",
        entity_name="Test Entity",
        endpoint="http://localhost:8000",
        public_key="test-public-key",
        capabilities=["test"]
    )
    
    nodes = registry.load_bootstrap_nodes(str(config_path))
    
    # Should have 4 nodes (3 bootstrap + 1 local)
    assert len(nodes) == 4, f"Expected 4 nodes from real config, got {len(nodes)}"
    
    # First should be local (priority 0)
    assert nodes[0] == ("127.0.0.1", 8468), f"First node should be local, got {nodes[0]}"
    
    print(f"  ✓ Loaded {len(nodes)} nodes from real config")
    for host, port in nodes:
        print(f"    - {host}:{port}")
    
    print("  All tests passed!")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Bootstrap Auto-Discovery (S1) Test Suite")
    print("=" * 60)
    
    try:
        test_parse_dht_endpoint()
        test_load_bootstrap_nodes()
        test_auto_load_on_init()
        test_explicit_bootstrap_nodes_override()
        test_error_handling()
        test_with_real_config()
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
