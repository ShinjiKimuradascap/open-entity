#!/usr/bin/env python3
"""
並行転送テスト
複数スレッドからの同時転送による残高一貫性検証
"""

import sys
import os
import threading
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from token_system import create_wallet, delete_wallet


def test_concurrent_transfers():
    """並行転送での残高一貫性テスト"""
    print("\n=== Concurrent Transfers Test ===")
    alice_id = "alice-concurrent"
    bob_id = "bob-concurrent"
    initial_balance = 1000.0
    transfer_amount = 10.0
    transfers_per_thread = 10
    num_threads = 5
    expected_total_transfers = transfer_amount * transfers_per_thread * num_threads
    
    try:
        # ウォレット作成
        alice = create_wallet(alice_id, initial_balance=initial_balance)
        bob = create_wallet(bob_id, initial_balance=0.0)
        
        errors = []
        
        def transfer_batch():
            """1スレッドでの転送バッチ"""
            for i in range(transfers_per_thread):
                try:
                    success = alice.transfer(bob, transfer_amount, f"Concurrent transfer {i}")
                    if not success:
                        errors.append(f"Transfer {i} failed")
                except Exception as e:
                    errors.append(f"Transfer {i} error: {e}")
        
        # 複数スレッドで同時転送
        threads = [threading.Thread(target=transfer_batch) for _ in range(num_threads)]
        
        start_time = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start_time
        
        # 結果検証
        alice_final = alice.get_balance()
        bob_final = bob.get_balance()
        
        print(f"   Initial Alice: {initial_balance} AIC")
        print(f"   Final Alice: {alice_final} AIC")
        print(f"   Final Bob: {bob_final} AIC")
        print(f"   Total transferred: {initial_balance - alice_final} AIC")
        print(f"   Expected transfers: {expected_total_transfers} AIC")
        print(f"   Threads: {num_threads}, Transfers per thread: {transfers_per_thread}")
        print(f"   Elapsed time: {elapsed:.2f}s")
        print(f"   Errors: {len(errors)}")
        
        # 残高一貫性チェック
        assert alice_final + bob_final == initial_balance, "Total balance should remain constant"
        assert bob_final == expected_total_transfers or alice_final == initial_balance - expected_total_transfers, \
            f"Transfer amount mismatch. Bob has {bob_final}, expected {expected_total_transfers}"
        assert len(errors) == 0, f"Transfer errors occurred: {errors}"
        
        print(f"✅ Concurrent transfers completed successfully")
        print(f"   TPS: {(num_threads * transfers_per_thread) / elapsed:.2f}")
        
    finally:
        # クリーンアップ
        delete_wallet(alice_id)
        delete_wallet(bob_id)


def test_concurrent_mixed_operations():
    """混在操作の並行テスト"""
    print("\n=== Concurrent Mixed Operations Test ===")
    entity_id = "mixed-test"
    
    try:
        wallet = create_wallet(entity_id, initial_balance=1000.0)
        errors = []
        
        def deposit_operations():
            for i in range(20):
                try:
                    wallet.deposit(10.0, f"Deposit {i}")
                except Exception as e:
                    errors.append(f"Deposit error: {e}")
        
        def withdraw_operations():
            for i in range(10):
                try:
                    wallet.withdraw(5.0, f"Withdraw {i}")
                except Exception as e:
                    errors.append(f"Withdraw error: {e}")
        
        # 並行実行
        threads = [
            threading.Thread(target=deposit_operations),
            threading.Thread(target=withdraw_operations)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        final_balance = wallet.get_balance()
        expected_balance = 1000.0 + (20 * 10.0) - (10 * 5.0)  # 1000 + 200 - 50 = 1150
        
        print(f"   Final balance: {final_balance} AIC")
        print(f"   Expected: {expected_balance} AIC")
        print(f"   Errors: {len(errors)}")
        
        # 残高が整合しているか（厳密な一致ではなく範囲で確認）
        assert abs(final_balance - expected_balance) < 1.0, \
            f"Balance mismatch: {final_balance} != {expected_balance}"
        
        print(f"✅ Mixed operations test passed")
        
    finally:
        delete_wallet(entity_id)


def main():
    """全テスト実行"""
    print("=" * 60)
    print("Concurrent Transfer Test Suite")
    print("=" * 60)
    
    try:
        test_concurrent_transfers()
        test_concurrent_mixed_operations()
        
        print("\n" + "=" * 60)
        print("✅ All concurrent tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
