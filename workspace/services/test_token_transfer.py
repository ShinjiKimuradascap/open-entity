#!/usr/bin/env python3
"""
トークン転送機能テスト
AI間トークン転送の動作確認
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from token_system import (
    create_wallet, get_wallet, delete_wallet,
    TokenWallet, TransactionType
)


def test_wallet_creation():
    """ウォレット作成テスト"""
    print("\n=== Wallet Creation Test ===")
    
    # 新規ウォレット作成
    wallet = create_wallet("test-entity-1", initial_balance=1000.0)
    assert wallet is not None, "Wallet should be created"
    assert wallet.entity_id == "test-entity-1"
    assert wallet.get_balance() == 1000.0
    print(f"✅ Wallet created: {wallet.entity_id}, balance={wallet.get_balance()}")
    
    # クリーンアップ
    delete_wallet("test-entity-1")


def test_token_transfer():
    """トークン転送テスト"""
    print("\n=== Token Transfer Test ===")
    
    # 送信者・受信者ウォレット作成
    sender = create_wallet("sender-entity", initial_balance=1000.0)
    receiver = create_wallet("receiver-entity", initial_balance=100.0)
    
    # 転送前残高を記録
    sender_before = sender.get_balance()
    receiver_before = receiver.get_balance()
    
    # トークン転送
    transfer_amount = 500.0
    success = sender.transfer(receiver, transfer_amount, "Test payment")
    
    assert success is True, "Transfer should succeed"
    assert sender.get_balance() == sender_before - transfer_amount
    assert receiver.get_balance() == receiver_before + transfer_amount
    
    print(f"✅ Transfer completed: {transfer_amount} AIC")
    print(f"   Sender: {sender_before} -> {sender.get_balance()}")
    print(f"   Receiver: {receiver_before} -> {receiver.get_balance()}")
    
    # クリーンアップ
    delete_wallet("sender-entity")
    delete_wallet("receiver-entity")


def test_insufficient_balance():
    """残高不足テスト"""
    print("\n=== Insufficient Balance Test ===")
    
    sender = create_wallet("poor-entity", initial_balance=10.0)
    receiver = create_wallet("rich-entity", initial_balance=100.0)
    
    # 残高以上の転送（失敗すべき）
    success = sender.transfer(receiver, 100.0, "Should fail")
    
    assert success is False, "Transfer should fail due to insufficient balance"
    assert sender.get_balance() == 10.0, "Sender balance should not change"
    assert receiver.get_balance() == 100.0, "Receiver balance should not change"
    
    print(f"✅ Insufficient balance correctly rejected")
    
    # クリーンアップ
    delete_wallet("poor-entity")
    delete_wallet("rich-entity")


def test_transaction_history():
    """トランザクション履歴テスト"""
    print("\n=== Transaction History Test ===")
    
    wallet = create_wallet("history-entity", initial_balance=1000.0)
    
    # 複数の取引
    wallet.deposit(500.0, "Initial deposit")
    wallet.withdraw(200.0, "Withdrawal")
    
    # 履歴取得
    history = wallet.get_transaction_history()
    
    assert len(history) >= 2, f"Expected at least 2 transactions, got {len(history)}"
    
    # 最新の取引を確認
    latest = history[0]
    assert latest.type == TransactionType.WITHDRAW
    assert latest.amount == 200.0
    
    print(f"✅ Transaction history: {len(history)} records")
    for tx in history:
        print(f"   {tx.type.value}: {tx.amount} AIC - {tx.description}")
    
    # クリーンアップ
    delete_wallet("history-entity")


def test_invalid_transfer():
    """無効な転送テスト"""
    print("\n=== Invalid Transfer Test ===")
    
    sender = create_wallet("sender-invalid", initial_balance=100.0)
    receiver = create_wallet("receiver-invalid", initial_balance=100.0)
    
    # 負の金額
    success1 = sender.transfer(receiver, -50.0, "Negative amount")
    assert success1 is False, "Negative transfer should fail"
    
    # ゼロ
    success2 = sender.transfer(receiver, 0.0, "Zero amount")
    assert success2 is False, "Zero transfer should fail"
    
    print(f"✅ Invalid transfers correctly rejected")
    
    # クリーンアップ
    delete_wallet("sender-invalid")
    delete_wallet("receiver-invalid")


def test_multiple_transfers():
    """複数回転送テスト"""
    print("\n=== Multiple Transfers Test ===")
    
    alice = create_wallet("alice", initial_balance=1000.0)
    bob = create_wallet("bob", initial_balance=0.0)
    charlie = create_wallet("charlie", initial_balance=0.0)
    
    # Alice -> Bob
    alice.transfer(bob, 300.0, "Payment 1")
    
    # Bob -> Charlie
    bob.transfer(charlie, 150.0, "Payment 2")
    
    # Alice -> Charlie
    alice.transfer(charlie, 200.0, "Payment 3")
    
    # 残高確認
    assert alice.get_balance() == 500.0  # 1000 - 300 - 200
    assert bob.get_balance() == 150.0    # 0 + 300 - 150
    assert charlie.get_balance() == 350.0  # 0 + 150 + 200
    
    print(f"✅ Multiple transfers completed")
    print(f"   Alice: {alice.get_balance()} AIC")
    print(f"   Bob: {bob.get_balance()} AIC")
    print(f"   Charlie: {charlie.get_balance()} AIC")
    
    # クリーンアップ
    delete_wallet("alice")
    delete_wallet("bob")
    delete_wallet("charlie")


def main():
    """全テスト実行"""
    print("=" * 60)
    print("Token Transfer Test Suite")
    print("=" * 60)
    
    try:
        test_wallet_creation()
        test_token_transfer()
        test_insufficient_balance()
        test_transaction_history()
        test_invalid_transfer()
        test_multiple_transfers()
        
        print("\n" + "=" * 60)
        print("✅ All token tests passed!")
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
