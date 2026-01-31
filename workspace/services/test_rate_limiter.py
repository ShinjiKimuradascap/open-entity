#!/usr/bin/env python3
"""
Rate Limiter Test Suite
レートリミッターの包括的テスト
"""

import sys
import os
import asyncio
import time
from typing import Dict, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.rate_limiter import (
    RateLimitConfig,
    RateLimitState,
    TokenBucketRateLimiter,
    EndpointRateLimiter,
    get_rate_limiter,
    get_endpoint_rate_limiter,
    init_rate_limiters,
    shutdown_rate_limiters
)


# ============================================================================
# Test 1: TokenBucketRateLimiter Basic Tests
# ============================================================================

async def test_token_bucket_basic_initialization():
    """TokenBucketRateLimiterの初期化テスト"""
    print("\n--- Test: TokenBucketRateLimiter Basic Initialization ---")
    
    # デフォルト設定で初期化
    limiter = TokenBucketRateLimiter()
    assert limiter.default_config.requests_per_minute == 60
    assert limiter.default_config.burst_size == 10
    assert limiter._cleanup_task is None
    assert len(limiter._buckets) == 0
    print("  ✓ Default initialization works")
    
    # カスタム設定で初期化
    custom_config = RateLimitConfig(
        requests_per_minute=120,
        burst_size=20,
        window_seconds=30
    )
    limiter2 = TokenBucketRateLimiter(default_config=custom_config)
    assert limiter2.default_config.requests_per_minute == 120
    assert limiter2.default_config.burst_size == 20
    print("  ✓ Custom initialization works")


async def test_token_bucket_start_stop():
    """start/stop機能のテスト"""
    print("\n--- Test: TokenBucketRateLimiter Start/Stop ---")
    
    limiter = TokenBucketRateLimiter()
    
    # Start
    await limiter.start()
    assert limiter._cleanup_task is not None
    assert not limiter._cleanup_task.done()
    print("  ✓ Start creates cleanup task")
    
    # Stop
    await limiter.stop()
    assert limiter._cleanup_task is None
    print("  ✓ Stop cancels cleanup task")
    
    # Multiple start calls (should be idempotent)
    await limiter.start()
    await limiter.start()  # Should not create second task
    await limiter.stop()
    print("  ✓ Multiple start calls handled")
    
    # Stop when not started
    limiter2 = TokenBucketRateLimiter()
    await limiter2.stop()  # Should not raise
    print("  ✓ Stop when not started handled")


async def test_token_bucket_burst_limit():
    """バースト制限テスト"""
    print("\n--- Test: TokenBucketRateLimiter Burst Limit ---")
    
    config = RateLimitConfig(requests_per_minute=60, burst_size=5)
    limiter = TokenBucketRateLimiter(default_config=config)
    await limiter.start()
    
    key = "burst_test_client"
    
    # バーストサイズ分は許可される
    allowed_count = 0
    for i in range(5):
        allowed, info = await limiter.check_rate_limit(key)
        if allowed:
            allowed_count += 1
            print(f"  Request {i+1}: ✓ (remaining: {info['remaining']})")
        else:
            print(f"  Request {i+1}: ✗ (retry_after: {info.get('retry_after')})")
    
    assert allowed_count == 5, f"Expected 5 allowed, got {allowed_count}"
    print(f"  ✓ Burst limit respected: {allowed_count}/5 allowed")
    
    # 6番目は拒否される
    allowed, info = await limiter.check_rate_limit(key)
    assert not allowed
    assert "retry_after" in info
    print(f"  ✓ 6th request denied with retry_after: {info['retry_after']}s")
    
    await limiter.stop()


# ============================================================================
# Test 2: Token Refill Tests
# ============================================================================

async def test_token_refill():
    """トークン補充テスト - 時間経過での補充確認"""
    print("\n--- Test: Token Refill Over Time ---")
    
    config = RateLimitConfig(requests_per_minute=60, burst_size=5)
    limiter = TokenBucketRateLimiter(default_config=config)
    await limiter.start()
    
    key = "refill_test_client"
    
    # 全トークンを消費
    for i in range(5):
        await limiter.check_rate_limit(key)
    
    # 拒否されることを確認
    allowed, info = await limiter.check_rate_limit(key)
    assert not allowed
    print(f"  After consuming all tokens: denied (retry_after: {info['retry_after']})")
    
    # 2秒待機（約2トークン補充されるはず）
    await asyncio.sleep(2)
    
    # 1つ目は許可される
    allowed, info = await limiter.check_rate_limit(key)
    assert allowed, f"Expected allowed after wait, got denied"
    print(f"  After 2s wait: allowed (remaining: {info['remaining']})")
    
    # 2つ目も許可されるはず（補充されたトークンが残っている）
    allowed, info = await limiter.check_rate_limit(key)
    if allowed:
        print(f"  Second request: allowed (remaining: {info['remaining']})")
    else:
        print(f"  Second request: denied (retry_after: {info.get('retry_after')})")
    
    await limiter.stop()
    print("  ✓ Token refill working correctly")


async def test_token_refill_rate_calculation():
    """refill_rate計算のテスト"""
    print("\n--- Test: Token Refill Rate Calculation ---")
    
    # 60 requests per minute = 1 per second
    config = RateLimitConfig(requests_per_minute=60)
    assert config.refill_rate == 1.0
    print(f"  60 RPM: refill_rate = {config.refill_rate}/s (expected: 1.0)")
    
    # 120 requests per minute = 2 per second
    config = RateLimitConfig(requests_per_minute=120)
    assert config.refill_rate == 2.0
    print(f"  120 RPM: refill_rate = {config.refill_rate}/s (expected: 2.0)")
    
    # 30 requests per minute = 0.5 per second
    config = RateLimitConfig(requests_per_minute=30)
    assert config.refill_rate == 0.5
    print(f"  30 RPM: refill_rate = {config.refill_rate}/s (expected: 0.5)")
    
    print("  ✓ Refill rate calculations correct")


# ============================================================================
# Test 3: Window-Based Limit Tests
# ============================================================================

async def test_window_reset():
    """ウィンドウベース制限テスト - window_secondsでのリセット"""
    print("\n--- Test: Window-Based Limit Reset ---")
    
    # 短いウィンドウでテスト
    config = RateLimitConfig(
        requests_per_minute=60,
        burst_size=10,
        window_seconds=2  # 2秒ウィンドウ
    )
    limiter = TokenBucketRateLimiter(default_config=config)
    await limiter.start()
    
    key = "window_test_client"
    
    # 初期リクエスト
    allowed, info = await limiter.check_rate_limit(key)
    assert allowed
    initial_window_start = info['reset_at'] - config.window_seconds
    print(f"  Initial request: allowed (window starts at ~{initial_window_start:.0f})")
    
    # ウィンドウが切り替わるまで待機
    await asyncio.sleep(2.5)
    
    # 新しいウィンドウでリクエスト
    allowed, info = await limiter.check_rate_limit(key)
    assert allowed
    new_window_start = info['reset_at'] - config.window_seconds
    print(f"  After window reset: allowed (new window starts at ~{new_window_start:.0f})")
    
    # ウィンドウが実際にリセットされたことを確認
    assert new_window_start > initial_window_start
    print("  ✓ Window reset correctly after window_seconds")
    
    await limiter.stop()


# ============================================================================
# Test 4: EndpointRateLimiter Tests
# ============================================================================

async def test_endpoint_rate_limiter_initialization():
    """EndpointRateLimiterの初期化テスト"""
    print("\n--- Test: EndpointRateLimiter Initialization ---")
    
    limiter = EndpointRateLimiter(default_rpm=100, default_burst=15)
    assert limiter.default_config.requests_per_minute == 100
    assert limiter.default_config.burst_size == 15
    assert len(limiter._endpoint_configs) == 0
    print("  ✓ EndpointRateLimiter initialized with custom defaults")
    
    # Default values
    limiter2 = EndpointRateLimiter()
    assert limiter2.default_config.requests_per_minute == 60
    assert limiter2.default_config.burst_size == 10
    print("  ✓ EndpointRateLimiter initialized with defaults")


async def test_endpoint_rate_limiter_set_get_limit():
    """エンドポイント別制限設定テスト"""
    print("\n--- Test: EndpointRateLimiter Set/Get Limit ---")
    
    limiter = EndpointRateLimiter()
    await limiter.start()
    
    # エンドポイント別制限を設定
    limiter.set_limit("/api/message", requests_per_minute=60, burst_size=10)
    limiter.set_limit("/api/auth", requests_per_minute=10, burst_size=2)
    limiter.set_limit("/api/admin", requests_per_minute=30)  # burst_size auto
    
    # 設定を確認
    msg_config = limiter.get_limit("/api/message")
    assert msg_config.requests_per_minute == 60
    assert msg_config.burst_size == 10
    print(f"  /api/message: {msg_config.requests_per_minute} RPM, burst={msg_config.burst_size}")
    
    auth_config = limiter.get_limit("/api/auth")
    assert auth_config.requests_per_minute == 10
    assert auth_config.burst_size == 2
    print(f"  /api/auth: {auth_config.requests_per_minute} RPM, burst={auth_config.burst_size}")
    
    admin_config = limiter.get_limit("/api/admin")
    assert admin_config.requests_per_minute == 30
    assert admin_config.burst_size == 5  # 30 // 6 = 5
    print(f"  /api/admin: {admin_config.requests_per_minute} RPM, burst={admin_config.burst_size} (auto)")
    
    # 未設定エンドポイントはデフォルト
    other_config = limiter.get_limit("/api/other")
    assert other_config.requests_per_minute == 60  # default
    print(f"  /api/other: {other_config.requests_per_minute} RPM (default)")
    
    await limiter.stop()
    print("  ✓ Endpoint-specific limits configured correctly")


async def test_endpoint_rate_limiter_check():
    """EndpointRateLimiterのcheckメソッドテスト"""
    print("\n--- Test: EndpointRateLimiter Check Method ---")
    
    limiter = EndpointRateLimiter()
    await limiter.start()
    
    limiter.set_limit("/api/test", requests_per_minute=60, burst_size=3)
    
    client_id = "test_client"
    path = "/api/test"
    
    # バースト分許可される
    for i in range(3):
        allowed, info = await limiter.check(client_id, path)
        assert allowed, f"Request {i+1} should be allowed"
        print(f"  Request {i+1}: ✓ (remaining: {info['remaining']})")
    
    # 4番目は拒否
    allowed, info = await limiter.check(client_id, path)
    assert not allowed
    assert "retry_after" in info
    print(f"  Request 4: ✗ (retry_after: {info['retry_after']})")
    
    # 別クライアントは独立
    client2 = "test_client_2"
    allowed, info = await limiter.check(client2, path)
    assert allowed
    print(f"  Different client: ✓ (remaining: {info['remaining']})")
    
    # 別エンドポイントも独立
    limiter.set_limit("/api/other", requests_per_minute=60, burst_size=5)
    allowed, info = await limiter.check(client_id, "/api/other")
    assert allowed
    print(f"  Different endpoint: ✓ (remaining: {info['remaining']})")
    
    await limiter.stop()
    print("  ✓ EndpointRateLimiter check working correctly")


# ============================================================================
# Test 5: Statistics Tests
# ============================================================================

async def test_statistics():
    """統計情報テスト - allowed/deniedカウント"""
    print("\n--- Test: Rate Limiter Statistics ---")
    
    config = RateLimitConfig(requests_per_minute=60, burst_size=3)
    limiter = TokenBucketRateLimiter(default_config=config)
    await limiter.start()
    
    key = "stats_test_client"
    
    # 初期統計
    stats = await limiter.get_stats()
    assert stats["allowed"] == 0
    assert stats["denied"] == 0
    assert stats["active_buckets"] == 0
    print(f"  Initial stats: allowed={stats['allowed']}, denied={stats['denied']}")
    
    # 3つ許可
    for _ in range(3):
        await limiter.check_rate_limit(key)
    
    stats = await limiter.get_stats()
    assert stats["allowed"] == 3
    assert stats["denied"] == 0
    assert stats["active_buckets"] == 1
    print(f"  After 3 allowed: allowed={stats['allowed']}, denied={stats['denied']}")
    
    # 2つ拒否
    for _ in range(2):
        await limiter.check_rate_limit(key)
    
    stats = await limiter.get_stats()
    assert stats["allowed"] == 3
    assert stats["denied"] == 2
    print(f"  After 2 denied: allowed={stats['allowed']}, denied={stats['denied']}")
    
    await limiter.stop()
    print("  ✓ Statistics tracking correctly")


async def test_endpoint_statistics():
    """EndpointRateLimiterの統計テスト"""
    print("\n--- Test: EndpointRateLimiter Statistics ---")
    
    limiter = EndpointRateLimiter()
    await limiter.start()
    
    limiter.set_limit("/api/test", requests_per_minute=60, burst_size=2)
    
    # リクエスト実行
    await limiter.check("client1", "/api/test")
    await limiter.check("client1", "/api/test")
    await limiter.check("client1", "/api/test")  # denied
    await limiter.check("client2", "/api/test")
    
    stats = await limiter.get_stats()
    assert stats["allowed"] == 3
    assert stats["denied"] == 1
    assert stats["active_buckets"] == 2  # 2 clients
    assert stats["endpoint_configs"] == 1
    print(f"  Stats: allowed={stats['allowed']}, denied={stats['denied']}, "
          f"buckets={stats['active_buckets']}, configs={stats['endpoint_configs']}")
    
    await limiter.stop()
    print("  ✓ EndpointRateLimiter statistics correct")


# ============================================================================
# Test 6: Reset Functionality Tests
# ============================================================================

async def test_reset_specific_key():
    """特定キーのリセットテスト"""
    print("\n--- Test: Reset Specific Key ---")
    
    config = RateLimitConfig(requests_per_minute=60, burst_size=3)
    limiter = TokenBucketRateLimiter(default_config=config)
    await limiter.start()
    
    key1 = "client1"
    key2 = "client2"
    
    # 両方のクライアントでトークン消費
    for _ in range(3):
        await limiter.check_rate_limit(key1)
        await limiter.check_rate_limit(key2)
    
    # 両方とも拒否される
    assert not (await limiter.check_rate_limit(key1))[0]
    assert not (await limiter.check_rate_limit(key2))[0]
    print("  Both clients at burst limit")
    
    # key1のみリセット
    await limiter.reset(key1)
    print(f"  Reset key: {key1}")
    
    # key1は許可される、key2はまだ拒否
    assert (await limiter.check_rate_limit(key1))[0]
    assert not (await limiter.check_rate_limit(key2))[0]
    print("  ✓ Only reset key allows requests again")
    
    await limiter.stop()


async def test_reset_all():
    """全リセットテスト"""
    print("\n--- Test: Reset All Keys ---")
    
    config = RateLimitConfig(requests_per_minute=60, burst_size=2)
    limiter = TokenBucketRateLimiter(default_config=config)
    await limiter.start()
    
    # 複数クライアントで消費
    for key in ["client1", "client2", "client3"]:
        for _ in range(2):
            await limiter.check_rate_limit(key)
    
    stats = await limiter.get_stats()
    assert stats["active_buckets"] == 3
    print(f"  Created {stats['active_buckets']} buckets")
    
    # 全リセット
    await limiter.reset()
    
    stats = await limiter.get_stats()
    assert stats["active_buckets"] == 0
    print("  ✓ All buckets cleared")
    
    # すべてのクライアントが再び許可される
    for key in ["client1", "client2", "client3"]:
        assert (await limiter.check_rate_limit(key))[0]
    print("  ✓ All clients can request again after reset")
    
    await limiter.stop()


# ============================================================================
# Test 7: RateLimitConfig Tests
# ============================================================================

async def test_rate_limit_config_defaults():
    """RateLimitConfigデフォルト値テスト"""
    print("\n--- Test: RateLimitConfig Default Values ---")
    
    config = RateLimitConfig()
    assert config.requests_per_minute == 60
    assert config.burst_size == 10
    assert config.window_seconds == 60
    assert config.key_prefix == "rl"
    assert config.refill_rate == 1.0  # 60/60
    print(f"  Defaults: RPM={config.requests_per_minute}, "
          f"burst={config.burst_size}, window={config.window_seconds}, "
          f"refill_rate={config.refill_rate}")
    print("  ✓ Default values correct")


async def test_rate_limit_config_custom():
    """RateLimitConfigカスタム値テスト"""
    print("\n--- Test: RateLimitConfig Custom Values ---")
    
    config = RateLimitConfig(
        requests_per_minute=120,
        burst_size=20,
        window_seconds=30,
        key_prefix="custom"
    )
    assert config.requests_per_minute == 120
    assert config.burst_size == 20
    assert config.window_seconds == 30
    assert config.key_prefix == "custom"
    assert config.refill_rate == 2.0  # 120/60
    print(f"  Custom: RPM={config.requests_per_minute}, "
          f"burst={config.burst_size}, window={config.window_seconds}, "
          f"refill_rate={config.refill_rate}")
    print("  ✓ Custom values correct")


async def test_rate_limit_config_refill_rate_variations():
    """様々なrefill_rate計算テスト"""
    print("\n--- Test: RateLimitConfig Refill Rate Variations ---")
    
    test_cases = [
        (1, 1/60),
        (10, 10/60),
        (30, 0.5),
        (60, 1.0),
        (100, 100/60),
        (120, 2.0),
        (300, 5.0),
        (600, 10.0),
        (1000, 1000/60),
    ]
    
    for rpm, expected in test_cases:
        config = RateLimitConfig(requests_per_minute=rpm)
        assert abs(config.refill_rate - expected) < 0.001
        print(f"  {rpm:4d} RPM → refill_rate = {config.refill_rate:.4f}/s")
    
    print("  ✓ All refill rate calculations correct")


# ============================================================================
# Test 8: Error Cases and Edge Cases
# ============================================================================

async def test_retry_after_calculation():
    """retry_after計算テスト"""
    print("\n--- Test: Retry-After Calculation ---")
    
    # 低速レート（1リクエスト/秒）
    config = RateLimitConfig(requests_per_minute=60, burst_size=1)
    limiter = TokenBucketRateLimiter(default_config=config)
    await limiter.start()
    
    key = "retry_test_client"
    
    # トークン消費
    await limiter.check_rate_limit(key)
    
    # 拒否時のretry_after
    allowed, info = await limiter.check_rate_limit(key)
    assert not allowed
    assert "retry_after" in info
    # 1トークン補充に約1秒かかる
    assert info["retry_after"] >= 1
    print(f"  With 1 token consumed, retry_after = {info['retry_after']}s")
    
    await limiter.stop()
    
    # 高速レート（10リクエスト/秒）
    config2 = RateLimitConfig(requests_per_minute=600, burst_size=1)
    limiter2 = TokenBucketRateLimiter(default_config=config2)
    await limiter2.start()
    
    await limiter2.check_rate_limit(key + "_2")
    allowed, info = await limiter2.check_rate_limit(key + "_2")
    assert not allowed
    # 高速レートなのでretry_afterは短い
    assert info["retry_after"] < 1
    print(f"  With high rate (600 RPM), retry_after = {info['retry_after']}s")
    
    await limiter2.stop()
    print("  ✓ Retry-after calculations correct")


async def test_empty_key():
    """空キーのテスト"""
    print("\n--- Test: Empty/Invalid Keys ---")
    
    limiter = TokenBucketRateLimiter()
    await limiter.start()
    
    # 空文字列キー
    allowed, info = await limiter.check_rate_limit("")
    assert allowed  # 最初は許可される
    print("  Empty string key: handled")
    
    # Noneは扱えないが、特殊キーは許可
    special_keys = [" ", "key:with:colons", "key/with/slashes", "キー"]
    for key in special_keys:
        allowed, info = await limiter.check_rate_limit(key)
        assert allowed  # 最初は許可される
        print(f"  Special key '{key}': handled")
    
    await limiter.stop()
    print("  ✓ Various key formats handled")


async def test_concurrent_access():
    """並行アクセステスト"""
    print("\n--- Test: Concurrent Access ---")
    
    config = RateLimitConfig(requests_per_minute=600, burst_size=100)
    limiter = TokenBucketRateLimiter(default_config=config)
    await limiter.start()
    
    key = "concurrent_client"
    
    async def make_requests(count: int) -> int:
        """複数リクエストを実行し、許可された数を返す"""
        allowed = 0
        for _ in range(count):
            if (await limiter.check_rate_limit(key))[0]:
                allowed += 1
        return allowed
    
    # 並行してリクエスト
    tasks = [
        make_requests(30),
        make_requests(30),
        make_requests(30),
    ]
    results = await asyncio.gather(*tasks)
    
    total_allowed = sum(results)
    print(f"  Concurrent requests: {total_allowed}/90 allowed")
    
    # バーストサイズを超えない
    assert total_allowed <= config.burst_size
    print(f"  ✓ Concurrent access respects burst limit ({total_allowed} <= {config.burst_size})")
    
    await limiter.stop()


async def test_rate_limit_state():
    """RateLimitStateデータクラステスト"""
    print("\n--- Test: RateLimitState Dataclass ---")
    
    # デフォルト値
    state = RateLimitState()
    assert state.tokens == 0.0
    assert state.request_count == 0
    assert isinstance(state.last_update, float)
    assert isinstance(state.window_start, float)
    print("  ✓ RateLimitState defaults correct")
    
    # カスタム値
    state2 = RateLimitState(tokens=5.0, request_count=10)
    assert state2.tokens == 5.0
    assert state2.request_count == 10
    print("  ✓ RateLimitState custom values correct")


async def test_config_per_key():
    """キーごとの設定テスト"""
    print("\n--- Test: Config Per Key ---")
    
    default_config = RateLimitConfig(requests_per_minute=60, burst_size=10)
    limiter = TokenBucketRateLimiter(default_config=default_config)
    await limiter.start()
    
    # デフォルト設定
    config = limiter.get_config("default_client")
    assert config.requests_per_minute == 60
    print("  Default config: 60 RPM, burst=10")
    
    # カスタム設定
    custom_config = RateLimitConfig(requests_per_minute=30, burst_size=5)
    limiter.set_config("vip_client", custom_config)
    
    config = limiter.get_config("vip_client")
    assert config.requests_per_minute == 30
    assert config.burst_size == 5
    print("  Custom config for vip_client: 30 RPM, burst=5")
    
    await limiter.stop()
    print("  ✓ Per-key configuration working")


async def test_cleanup_functionality():
    """クリーンアップ機能テスト"""
    print("\n--- Test: Cleanup Functionality ---")
    
    # 短いクリーンアップ間隔でテスト
    limiter = TokenBucketRateLimiter(cleanup_interval=1)
    await limiter.start()
    
    # バケットを作成
    await limiter.check_rate_limit("client1")
    await limiter.check_rate_limit("client2")
    
    stats = await limiter.get_stats()
    assert stats["active_buckets"] == 2
    print(f"  Created 2 buckets")
    
    # 手動で古いバケットをクリーンアップ（実際には時間経過が必要）
    # ここではクリーンアップメソッドの存在確認のみ
    cleaned = await limiter._cleanup_old_buckets()
    print(f"  Cleaned {cleaned} old buckets (expected 0, buckets are fresh)")
    
    await limiter.stop()
    print("  ✓ Cleanup functionality available")


# ============================================================================
# Global Instance Tests
# ============================================================================

async def test_global_instances():
    """グローバルインスタンステスト"""
    print("\n--- Test: Global Instances ---")
    
    # シングルトンパターン
    limiter1 = get_rate_limiter()
    limiter2 = get_rate_limiter()
    assert limiter1 is limiter2
    print("  ✓ TokenBucketRateLimiter singleton works")
    
    endpoint_limiter1 = get_endpoint_rate_limiter()
    endpoint_limiter2 = get_endpoint_rate_limiter()
    assert endpoint_limiter1 is endpoint_limiter2
    print("  ✓ EndpointRateLimiter singleton works")


async def test_init_shutdown():
    """初期化・シャットダウンテスト"""
    print("\n--- Test: Init and Shutdown ---")
    
    # 初期化
    await init_rate_limiters()
    print("  ✓ init_rate_limiters() completed")
    
    # グローバルインスタンスが動作している
    limiter = get_rate_limiter()
    endpoint_limiter = get_endpoint_rate_limiter()
    
    allowed, info = await limiter.check_rate_limit("test")
    assert allowed
    print("  ✓ Global limiter working after init")
    
    allowed, info = await endpoint_limiter.check("test", "/message")
    assert allowed
    print("  ✓ Global endpoint limiter working after init")
    
    # シャットダウン
    await shutdown_rate_limiters()
    print("  ✓ shutdown_rate_limiters() completed")


# ============================================================================
# Test Runner
# ============================================================================

async def run_all_tests():
    """すべてのテストを実行"""
    print("=" * 60)
    print("Rate Limiter Test Suite")
    print("=" * 60)
    
    tests = [
        # Test 1: TokenBucketRateLimiter Basic Tests
        test_token_bucket_basic_initialization,
        test_token_bucket_start_stop,
        test_token_bucket_burst_limit,
        
        # Test 2: Token Refill Tests
        test_token_refill,
        test_token_refill_rate_calculation,
        
        # Test 3: Window-Based Limit Tests
        test_window_reset,
        
        # Test 4: EndpointRateLimiter Tests
        test_endpoint_rate_limiter_initialization,
        test_endpoint_rate_limiter_set_get_limit,
        test_endpoint_rate_limiter_check,
        
        # Test 5: Statistics Tests
        test_statistics,
        test_endpoint_statistics,
        
        # Test 6: Reset Functionality Tests
        test_reset_specific_key,
        test_reset_all,
        
        # Test 7: RateLimitConfig Tests
        test_rate_limit_config_defaults,
        test_rate_limit_config_custom,
        test_rate_limit_config_refill_rate_variations,
        
        # Test 8: Error Cases and Edge Cases
        test_retry_after_calculation,
        test_empty_key,
        test_concurrent_access,
        test_rate_limit_state,
        test_config_per_key,
        test_cleanup_functionality,
        
        # Global Instance Tests
        test_global_instances,
        test_init_shutdown,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n  ✗ FAILED: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)
    print(f"Total: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ {failed} test(s) failed")
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
