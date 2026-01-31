#!/usr/bin/env python3
"""
Connection Pool Tests
コネクションプール機能のテスト

Tests:
- Circuit breaker state transitions
- Connection pool management
- Metrics collection
- Health checking
- Retry logic
"""

import asyncio
import sys
import os
import time
from unittest.mock import Mock, patch, AsyncMock

# servicesディレクトリをパスに追加
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, WORKSPACE_DIR)

# インポート
IMPORT_SUCCESS = False
try:
    from services.connection_pool import (
        CircuitState,
        CircuitBreaker,
        ConnectionMetrics,
        PeerConnectionPool,
        PooledConnectionManager,
    )
    IMPORT_SUCCESS = True
    print("✅ Imported connection_pool from services")
except ImportError as e1:
    try:
        from connection_pool import (
            CircuitState,
            CircuitBreaker,
            ConnectionMetrics,
            PeerConnectionPool,
            PooledConnectionManager,
        )
        IMPORT_SUCCESS = True
        print("✅ Imported connection_pool directly")
    except ImportError as e2:
        print(f"❌ Import failed: {e1}, {e2}")
        raise


async def test_circuit_breaker_states():
    """Test circuit breaker state transitions"""
    print("\n=== Circuit Breaker State Test ===\n")
    
    cb = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=0.1,  # Short for testing
        half_open_max_calls=2
    )
    
    # Initial state: CLOSED
    assert cb.state == CircuitState.CLOSED, "Initial state should be CLOSED"
    assert await cb.can_execute(), "Should allow execution in CLOSED state"
    print("✅ Initial CLOSED state correct")
    
    # Record failures to open circuit
    for i in range(3):
        await cb.record_failure()
        print(f"  Recorded failure {i+1}, state: {cb.state.value}")
    
    assert cb.state == CircuitState.OPEN, "Should be OPEN after 3 failures"
    assert not await cb.can_execute(), "Should block execution in OPEN state"
    print("✅ Circuit opened after threshold failures")
    
    # Wait for recovery timeout
    await asyncio.sleep(0.15)
    
    # Should transition to HALF_OPEN
    assert await cb.can_execute(), "Should allow execution in HALF_OPEN"
    assert cb.state == CircuitState.HALF_OPEN, "Should be HALF_OPEN after timeout"
    print("✅ Transitioned to HALF_OPEN after recovery timeout")
    
    # Record successes to close circuit
    await cb.record_success()
    await cb.record_success()
    
    assert cb.state == CircuitState.CLOSED, "Should be CLOSED after successes"
    print("✅ Circuit closed after recovery")
    
    # Test failure in HALF_OPEN returns to OPEN
    await cb.record_failure()
    await cb.record_failure()
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN, "Should be OPEN"
    
    await asyncio.sleep(0.15)
    await cb.can_execute()  # Transition to HALF_OPEN
    await cb.record_failure()  # Fail in HALF_OPEN
    
    assert cb.state == CircuitState.OPEN, "Should return to OPEN on failure in HALF_OPEN"
    print("✅ HALF_OPEN failure returns to OPEN")
    
    print("\n✅ Circuit breaker state test passed")


async def test_connection_metrics():
    """Test connection metrics collection"""
    print("\n=== Connection Metrics Test ===\n")
    
    metrics = ConnectionMetrics()
    
    # Record successes
    for i in range(5):
        metrics.record_success(response_time_ms=100.0 + i * 10)
    
    assert metrics.total_requests == 5, "Should have 5 total requests"
    assert metrics.successful_requests == 5, "Should have 5 successes"
    assert metrics.failed_requests == 0, "Should have 0 failures"
    print(f"✅ Success metrics: avg_response={metrics.avg_response_time_ms:.1f}ms")
    
    # Record failures
    for _ in range(3):
        metrics.record_failure()
    
    assert metrics.total_requests == 8, "Should have 8 total requests"
    assert metrics.failed_requests == 3, "Should have 3 failures"
    assert metrics.last_failure is not None, "Should have last failure time"
    print("✅ Failure metrics recorded")
    
    # Record retries
    metrics.record_retry()
    metrics.record_retry()
    assert metrics.retry_count == 2, "Should have 2 retries"
    print("✅ Retry metrics recorded")
    
    # Record circuit break
    metrics.record_circuit_break()
    assert metrics.circuit_breaks == 1, "Should have 1 circuit break"
    print("✅ Circuit break metrics recorded")
    
    print("\n✅ Connection metrics test passed")


async def test_peer_connection_pool():
    """Test PeerConnectionPool configuration"""
    print("\n=== Peer Connection Pool Test ===\n")
    
    pool = PeerConnectionPool(
        peer_id="test-peer-1",
        base_url="http://localhost:8001",
        max_connections=5,
        max_keepalive=3,
        keepalive_timeout=60,
        connect_timeout=10.0,
        total_timeout=60.0,
        max_retries=5,
        failure_threshold=10,
        recovery_timeout=60.0,
        half_open_max_calls=5
    )
    
    assert pool.peer_id == "test-peer-1", "Peer ID mismatch"
    assert pool.base_url == "http://localhost:8001", "Base URL mismatch"
    assert pool.max_connections == 5, "Max connections mismatch"
    assert pool.max_keepalive == 3, "Max keepalive mismatch"
    assert pool.failure_threshold == 10, "Failure threshold mismatch"
    print("✅ Pool configuration correct")
    
    print("\n✅ Peer connection pool test passed")


async def test_connection_manager_init():
    """Test PooledConnectionManager initialization"""
    print("\n=== Connection Manager Init Test ===\n")
    
    manager = PooledConnectionManager(
        default_max_connections=10,
        default_max_keepalive=5,
        default_keepalive_timeout=30
    )
    
    assert manager.default_max_connections == 10
    assert manager.default_max_keepalive == 5
    assert manager.default_keepalive_timeout == 30
    assert len(manager._sessions) == 0, "Should have no sessions initially"
    assert len(manager._pools) == 0, "Should have no pools initially"
    assert len(manager._circuit_breakers) == 0, "Should have no circuit breakers initially"
    print("✅ Manager initialized correctly")
    
    print("\n✅ Connection manager init test passed")


async def test_circuit_breaker_concurrent():
    """Test circuit breaker with concurrent access"""
    print("\n=== Circuit Breaker Concurrent Test ===\n")
    
    cb = CircuitBreaker(failure_threshold=10, recovery_timeout=1.0)
    
    async def record_failures(n):
        for _ in range(n):
            await cb.record_failure()
    
    # Concurrent failures
    await asyncio.gather(
        record_failures(5),
        record_failures(5)
    )
    
    assert cb.failure_count == 10, f"Should have 10 failures, got {cb.failure_count}"
    assert cb.state == CircuitState.OPEN, "Should be OPEN"
    print("✅ Concurrent failures recorded correctly")
    
    print("\n✅ Circuit breaker concurrent test passed")


async def test_metrics_rolling_average():
    """Test metrics rolling average calculation"""
    print("\n=== Metrics Rolling Average Test ===\n")
    
    metrics = ConnectionMetrics()
    
    # Record varying response times
    response_times = [100.0, 200.0, 300.0, 400.0, 500.0]
    for rt in response_times:
        metrics.record_success(response_time_ms=rt)
    
    expected_avg = sum(response_times) / len(response_times)
    assert abs(metrics.avg_response_time_ms - expected_avg) < 0.1, \
        f"Average mismatch: {metrics.avg_response_time_ms} vs {expected_avg}"
    
    print(f"✅ Rolling average correct: {metrics.avg_response_time_ms:.1f}ms")
    print("\n✅ Metrics rolling average test passed")


async def run_all_tests():
    """Run all connection pool tests"""
    print("\n" + "="*60)
    print("Connection Pool Tests")
    print("="*60)
    
    if not IMPORT_SUCCESS:
        print("❌ Import failed, cannot run tests")
        return False
    
    tests = [
        ("Circuit Breaker States", test_circuit_breaker_states),
        ("Connection Metrics", test_connection_metrics),
        ("Peer Connection Pool", test_peer_connection_pool),
        ("Connection Manager Init", test_connection_manager_init),
        ("Circuit Breaker Concurrent", test_circuit_breaker_concurrent),
        ("Metrics Rolling Average", test_metrics_rolling_average),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"\n❌ {name} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
