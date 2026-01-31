#!/usr/bin/env python3
"""
TOKEN_TRANSFERメッセージハンドラの動作確認テスト
"""

import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, 'services')
sys.path.insert(0, 'protocol')

from protocol.constants import MessageType


def test_message_type_constant():
    """MessageTypeにTOKEN_TRANSFERが定義されているか確認"""
    print("=" * 50)
    print("Test 1: MessageType Constant Check")
    print("=" * 50)
    
    # TOKEN_TRANSFERが存在するか確認
    assert hasattr(MessageType, 'TOKEN_TRANSFER'), "TOKEN_TRANSFER not found in MessageType"
    assert MessageType.TOKEN_TRANSFER == "token_transfer", f"Unexpected value: {MessageType.TOKEN_TRANSFER}"
    
    print(f"✓ TOKEN_TRANSFER = '{MessageType.TOKEN_TRANSFER}'")
    print("✓ Test 1 PASSED")
    return True


async def test_handler_registration():
    """PeerServiceにハンドラが登録されているか確認"""
    print("\n" + "=" * 50)
    print("Test 2: Handler Registration Check")
    print("=" * 50)
    
    try:
        from peer_service import PeerService
        
        # PeerServiceインスタンス作成（モック設定）
        service = PeerService(
            entity_id="test-entity",
            port=0,  # ポート自動割り当て
            enable_verification=False
        )
        
        # ハンドラが登録されているか確認
        assert "token_transfer" in service.message_handlers, "token_transfer handler not registered"
        
        print(f"✓ Registered handlers: {list(service.message_handlers.keys())}")
        print(f"✓ token_transfer handler: {service.message_handlers['token_transfer']}")
        print("✓ Test 2 PASSED")
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_handler_execution():
    """ハンドラの実行テスト"""
    print("\n" + "=" * 50)
    print("Test 3: Handler Execution Test")
    print("=" * 50)
    
    try:
        from peer_service import PeerService
        
        service = PeerService(
            entity_id="test-entity",
            port=0,
            enable_verification=False
        )
        
        # テストメッセージ作成
        test_message = {
            "sender_id": "test-sender",
            "msg_type": "token_transfer",
            "payload": {
                "transfer_id": "tx-001",
                "token_type": "AIC",
                "amount": 100.5,
                "recipient": "recipient-entity",
                "sender_address": "sender-wallet-address"
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "test-nonce-123"
        }
        
        # ハンドラを取得して実行
        handler = service.message_handlers.get("token_transfer")
        assert handler is not None, "Handler not found"
        
        await handler(test_message)
        
        # _pending_transfersに追加されたか確認
        assert hasattr(service, '_pending_transfers'), "_pending_transfers not initialized"
        assert len(service._pending_transfers) == 1, f"Expected 1 transfer, got {len(service._pending_transfers)}"
        
        transfer = service._pending_transfers[0]
        assert transfer["transfer_id"] == "tx-001"
        assert transfer["amount"] == 100.5
        assert transfer["token_type"] == "AIC"
        
        print(f"✓ Handler executed successfully")
        print(f"✓ Transfer queued: {transfer}")
        print("✓ Test 3 PASSED")
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """メインテスト実行"""
    print("\n" + "=" * 50)
    print("TOKEN_TRANSFER Handler Test Suite")
    print("=" * 50)
    
    results = []
    
    # Test 1: MessageType constant
    try:
        results.append(("Test 1", test_message_type_constant()))
    except Exception as e:
        print(f"✗ Test 1 FAILED: {e}")
        results.append(("Test 1", False))
    
    # Test 2: Handler registration
    try:
        results.append(("Test 2", await test_handler_registration()))
    except Exception as e:
        print(f"✗ Test 2 FAILED: {e}")
        results.append(("Test 2", False))
    
    # Test 3: Handler execution
    try:
        results.append(("Test 3", await test_handler_execution()))
    except Exception as e:
        print(f"✗ Test 3 FAILED: {e}")
        results.append(("Test 3", False))
    
    # 結果サマリー
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{name}: {status}")
    print(f"\nTotal: {passed}/{total} passed")
    
    return all(r for _, r in results)


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(130)
