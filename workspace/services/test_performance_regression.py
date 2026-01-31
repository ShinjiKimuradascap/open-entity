#!/usr/bin/env python3
"""
Performance Regression Tests
パフォーマンス回帰テスト - ベンチマーク・負荷テスト

Metrics:
- Throughput: messages/sec (target: >1000)
- Latency: p50, p95, p99 (target: p95 <100ms)
- Memory: per node (target: <500MB)

Usage:
    pytest services/test_performance_regression.py -v
    pytest services/test_performance_regression.py --benchmark-only
"""

import pytest
import sys
import time
import statistics
import tracemalloc
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

sys.path.insert(0, str(Path(__file__).parent))

from crypto import CryptoManager
from token_system import create_wallet, get_wallet, delete_wallet
from e2e_session import E2ESessionManager
from peer_service import PeerService


# =============================================================================
# Benchmark Utilities
# =============================================================================

class BenchmarkResult:
    """Store benchmark results."""
    
    def __init__(self, name: str):
        self.name = name
        self.durations: List[float] = []
        self.memory_start: int = 0
        self.memory_peak: int = 0
        
    def add_duration(self, duration_ms: float):
        """Add a duration measurement."""
        self.durations.append(duration_ms)
        
    @property
    def min_ms(self) -> float:
        return min(self.durations) if self.durations else 0
        
    @property
    def max_ms(self) -> float:
        return max(self.durations) if self.durations else 0
        
    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.durations) if self.durations else 0
        
    @property
    def median_ms(self) -> float:
        return statistics.median(self.durations) if self.durations else 0
        
    @property
    def p95_ms(self) -> float:
        if not self.durations:
            return 0
        sorted_durations = sorted(self.durations)
        idx = int(len(sorted_durations) * 0.95)
        return sorted_durations[min(idx, len(sorted_durations) - 1)]
        
    @property
    def p99_ms(self) -> float:
        if not self.durations:
            return 0
        sorted_durations = sorted(self.durations)
        idx = int(len(sorted_durations) * 0.99)
        return sorted_durations[min(idx, len(sorted_durations) - 1)]
        
    @property
    def throughput(self) -> float:
        """Calculate throughput (ops/sec)."""
        if self.mean_ms > 0:
            return 1000.0 / self.mean_ms
        return 0
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "samples": len(self.durations),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "mean_ms": round(self.mean_ms, 2),
            "median_ms": round(self.median_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "throughput_ops_sec": round(self.throughput, 2),
            "memory_peak_mb": round(self.memory_peak / (1024 * 1024), 2)
        }
        
    def __str__(self) -> str:
        return f"""
Benchmark: {self.name}
  Samples: {len(self.durations)}
  Latency: min={self.min_ms:.2f}ms, mean={self.mean_ms:.2f}ms, p95={self.p95_ms:.2f}ms, p99={self.p99_ms:.2f}ms
  Throughput: {self.throughput:.2f} ops/sec
  Memory Peak: {self.memory_peak / (1024 * 1024):.2f} MB
"""


def benchmark(iterations: int = 100, warmup: int = 10):
    """Decorator for benchmark functions."""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> BenchmarkResult:
            result = BenchmarkResult(func.__name__)
            
            # Warmup
            for _ in range(warmup):
                func(*args, **kwargs)
                
            # Start memory tracking
            tracemalloc.start()
            result.memory_start = tracemalloc.get_traced_memory()[0]
            
            # Benchmark
            for _ in range(iterations):
                start = time.perf_counter()
                func(*args, **kwargs)
                duration = (time.perf_counter() - start) * 1000  # Convert to ms
                result.add_duration(duration)
                
            # Memory tracking
            _, peak = tracemalloc.get_traced_memory()
            result.memory_peak = peak
            tracemalloc.stop()
            
            return result
        return wrapper
    return decorator


# =============================================================================
# Crypto Performance Tests
# =============================================================================

class TestCryptoPerformance:
    """Test cryptographic operation performance."""
    
    def test_ed25519_sign_performance(self):
        """Benchmark Ed25519 signing performance."""
        crypto = CryptoManager("perf-test")
        message = b"Benchmark message for signing"
        
        @benchmark(iterations=1000, warmup=100)
        def sign_operation():
            return crypto.sign(message)
            
        result = sign_operation()
        
        # Assertions based on targets
        assert result.p95_ms < 10, f"p95 latency {result.p95_ms}ms exceeds 10ms target"
        assert result.throughput > 1000, f"Throughput {result.throughput} below 1000 ops/sec target"
        
        print(f"\nEd25519 Sign Performance:\n{result}")
        
    def test_ed25519_verify_performance(self):
        """Benchmark Ed25519 verification performance."""
        crypto = CryptoManager("perf-test")
        message = b"Benchmark message for verification"
        signature = crypto.sign(message)
        pub_key = crypto.get_keypair()["public_key"]
        
        @benchmark(iterations=1000, warmup=100)
        def verify_operation():
            return crypto.verify_signature(pub_key, message, signature)
            
        result = verify_operation()
        assert result.p95_ms < 10
        print(f"\nEd25519 Verify Performance:\n{result}")
        
    def test_x25519_key_derivation_performance(self):
        """Benchmark X25519 key derivation performance."""
        crypto_a = CryptoManager("entity-a-perf")
        crypto_b = CryptoManager("entity-b-perf")
        pub_b = crypto_b.get_x25519_public_key()
        
        @benchmark(iterations=1000, warmup=100)
        def derive_operation():
            return crypto_a.derive_shared_secret(pub_b)
            
        result = derive_operation()
        assert result.p95_ms < 5
        print(f"\nX25519 Key Derivation Performance:\n{result}")
        
    def test_encryption_performance(self):
        """Benchmark encryption/decryption performance."""
        crypto_a = CryptoManager("encrypt-perf")
        crypto_b = CryptoManager("decrypt-perf")
        pub_b = crypto_b.get_x25519_public_key()
        plaintext = "A" * 1024  # 1KB message
        
        @benchmark(iterations=500, warmup=50)
        def encrypt_operation():
            return crypto_a.encrypt_x25519(pub_b, plaintext)
            
        result = encrypt_operation()
        assert result.p95_ms < 20
        print(f"\nEncryption Performance (1KB message):\n{result}")


# =============================================================================
# Token System Performance Tests
# =============================================================================

class TestTokenPerformance:
    """Test token system performance."""
    
    def test_wallet_transfer_performance(self):
        """Benchmark wallet transfer performance."""
        sender = create_wallet("perf-sender", initial_balance=1000000.0)
        receiver = create_wallet("perf-receiver", initial_balance=0.0)
        
        @benchmark(iterations=1000, warmup=100)
        def transfer_operation():
            return sender.transfer(receiver, 1.0, "Benchmark transfer")
            
        result = transfer_operation()
        
        assert result.p95_ms < 50
        assert result.throughput > 500
        
        print(f"\nWallet Transfer Performance:\n{result}")
        
        # Cleanup
        delete_wallet("perf-sender")
        delete_wallet("perf-receiver")
        
    def test_concurrent_transfers(self):
        """Test concurrent transfer performance."""
        wallets = []
        for i in range(10):
            wallets.append(create_wallet(f"concurrent-{i}", initial_balance=10000.0))
            
        def transfer_task(from_idx: int, to_idx: int, amount: float) -> float:
            start = time.perf_counter()
            wallets[from_idx].transfer(wallets[to_idx], amount, "Concurrent transfer")
            return (time.perf_counter() - start) * 1000
            
        # Concurrent transfers
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(100):
                from_idx = i % 10
                to_idx = (i + 1) % 10
                futures.append(executor.submit(transfer_task, from_idx, to_idx, 1.0))
                
            durations = [f.result() for f in as_completed(futures)]
            
        total_time = (time.perf_counter() - start) * 1000
        throughput = 100 / (total_time / 1000)  # ops/sec
        
        p95 = sorted(durations)[int(len(durations) * 0.95)]
        
        print(f"\nConcurrent Transfer Performance:")
        print(f"  Total time: {total_time:.2f}ms for 100 transfers")
        print(f"  Throughput: {throughput:.2f} ops/sec")
        print(f"  p95 latency: {p95:.2f}ms")
        
        assert throughput > 200
        assert p95 < 100
        
        # Cleanup
        for i in range(10):
            delete_wallet(f"concurrent-{i}")


# =============================================================================
# Session Management Performance Tests
# =============================================================================

@pytest.mark.asyncio
class TestSessionPerformance:
    """Test session management performance."""
    
    async def test_session_creation_performance(self):
        """Benchmark session creation performance."""
        crypto = CryptoManager("session-perf")
        session_mgr = E2ESessionManager(crypto)
        
        durations = []
        for _ in range(100):
            start = time.perf_counter()
            await session_mgr.create_session("entity-a", "entity-b")
            duration = (time.perf_counter() - start) * 1000
            durations.append(duration)
            
        mean = statistics.mean(durations)
        p95 = sorted(durations)[int(len(durations) * 0.95)]
        
        print(f"\nSession Creation Performance:")
        print(f"  Mean: {mean:.2f}ms")
        print(f"  p95: {p95:.2f}ms")
        
        assert mean < 50
        assert p95 < 100
        
    async def test_session_validation_performance(self):
        """Benchmark session validation performance."""
        crypto = CryptoManager("session-val-perf")
        session_mgr = E2ESessionManager(crypto)
        
        # Create session once
        session_id = await session_mgr.create_session("entity-a", "entity-b")
        
        durations = []
        for _ in range(1000):
            start = time.perf_counter()
            await session_mgr.validate_session(session_id, "entity-a", "entity-b")
            duration = (time.perf_counter() - start) * 1000
            durations.append(duration)
            
        mean = statistics.mean(durations)
        p95 = sorted(durations)[int(len(durations) * 0.95)]
        
        print(f"\nSession Validation Performance:")
        print(f"  Mean: {mean:.2f}ms")
        print(f"  p95: {p95:.2f}ms")
        
        assert mean < 10
        assert p95 < 20


# =============================================================================
# Memory Usage Tests
# =============================================================================

class TestMemoryUsage:
    """Test memory consumption."""
    
    def test_wallet_memory_footprint(self):
        """Test memory usage per wallet."""
        tracemalloc.start()
        
        # Create many wallets
        wallets = []
        for i in range(1000):
            wallets.append(create_wallet(f"mem-test-{i}", initial_balance=1000.0))
            
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        memory_per_wallet = current / 1000 / (1024 * 1024)  # MB
        
        print(f"\nWallet Memory Usage:")
        print(f"  Total: {current / (1024 * 1024):.2f} MB")
        print(f"  Per wallet: {memory_per_wallet:.4f} MB")
        
        assert memory_per_wallet < 0.5  # Less than 500KB per wallet
        
        # Cleanup
        for i in range(1000):
            delete_wallet(f"mem-test-{i}")
        
    def test_crypto_manager_memory(self):
        """Test CryptoManager memory footprint."""
        tracemalloc.start()
        
        crypto_instances = []
        for i in range(100):
            crypto_instances.append(CryptoManager(f"crypto-mem-{i}"))
            
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        memory_per_instance = current / 100 / (1024 * 1024)  # MB
        
        print(f"\nCryptoManager Memory Usage:")
        print(f"  Total: {current / (1024 * 1024):.2f} MB")
        print(f"  Per instance: {memory_per_instance:.4f} MB")
        
        assert memory_per_instance < 5  # Less than 5MB per instance


# =============================================================================
# Baseline Recording
# =============================================================================

class TestPerformanceBaselines:
    """Record performance baselines for regression detection."""
    
    def test_record_all_baselines(self):
        """Record all performance baselines."""
        results = []
        
        # Crypto benchmarks
        crypto = CryptoManager("baseline")
        message = b"Baseline message"
        
        @benchmark(iterations=100, warmup=10)
        def sign_baseline():
            return crypto.sign(message)
            
        results.append(sign_baseline())
        
        # Token benchmarks
        sender = create_wallet("baseline-sender", initial_balance=100000.0)
        receiver = create_wallet("baseline-receiver", initial_balance=0.0)
        
        @benchmark(iterations=100, warmup=10)
        def transfer_baseline():
            return sender.transfer(receiver, 1.0, "Baseline")
            
        results.append(transfer_baseline())
        
        # Print baseline report
        print("\n" + "="*60)
        print("PERFORMANCE BASELINE REPORT")
        print("="*60)
        
        baseline_data = {}
        for result in results:
            print(result)
            baseline_data[result.name] = result.to_dict()
            
        # Save baselines to file
        baseline_file = Path("test_baselines.json")
        import json
        with open(baseline_file, 'w') as f:
            json.dump(baseline_data, f, indent=2)
            
        print(f"\nBaselines saved to: {baseline_file}")
        
        # Cleanup
        delete_wallet("baseline-sender")
        delete_wallet("baseline-receiver")


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
