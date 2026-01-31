#!/usr/bin/env python3
"""
Chunked Transfer Tests
Phase1テスト実装 - chunked_transfer.py

機能テスト:
- メッセージチャンクの作成と検証
- チャンク転送の組み立て
- チェックサム検証
- プロトコルメッセージ作成
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chunked_transfer import (
    ChunkStatus,
    MessageChunk,
    ChunkedTransfer,
    ChunkedTransferManager,
    ChunkedMessageProtocol,
    chunk_message
)


class TestChunkStatus:
    """チャンク状態のテスト"""
    
    def test_status_values(self):
        """状態値の確認"""
        assert ChunkStatus.PENDING.value == "pending"
        assert ChunkStatus.IN_PROGRESS.value == "in_progress"
        assert ChunkStatus.COMPLETED.value == "completed"
        assert ChunkStatus.FAILED.value == "failed"
        assert ChunkStatus.EXPIRED.value == "expired"
        print("✅ ChunkStatus values test passed")


class TestMessageChunk:
    """メッセージチャンクのテスト"""
    
    def test_create_chunk(self):
        """チャンクの作成"""
        chunk = MessageChunk(
            transfer_id="test-transfer-123",
            chunk_index=0,
            total_chunks=3,
            data=b"test data",
            checksum="abc123"
        )
        
        assert chunk.transfer_id == "test-transfer-123"
        assert chunk.chunk_index == 0
        assert chunk.total_chunks == 3
        assert chunk.data == b"test data"
        assert chunk.checksum == "abc123"
        print("✅ MessageChunk creation test passed")
    
    def test_chunk_to_dict(self):
        """チャンクの辞書変換"""
        chunk = MessageChunk(
            transfer_id="transfer-456",
            chunk_index=1,
            total_chunks=5,
            data=b"chunk data content",
            checksum="def789"
        )
        
        result = chunk.to_dict()
        
        assert result["transfer_id"] == "transfer-456"
        assert result["chunk_index"] == 1
        assert result["total_chunks"] == 5
        assert "data" in result  # base64 encoded
        assert result["checksum"] == "def789"
        print("✅ MessageChunk to_dict test passed")
    
    def test_chunk_from_dict(self):
        """辞書からチャンク復元"""
        import base64
        
        original_data = b"test payload data"
        data_encoded = base64.b64encode(original_data).decode('utf-8')
        
        data = {
            "transfer_id": "transfer-789",
            "chunk_index": 2,
            "total_chunks": 4,
            "data": data_encoded,
            "checksum": "xyz789"
        }
        
        chunk = MessageChunk.from_dict(data)
        
        assert chunk.transfer_id == "transfer-789"
        assert chunk.chunk_index == 2
        assert chunk.data == original_data
        print("✅ MessageChunk from_dict test passed")
    
    def test_verify_checksum_valid(self):
        """有効なチェックサム検証"""
        import hashlib
        
        data = b"valid checksum data"
        checksum = hashlib.sha256(data).hexdigest()[:32]
        
        chunk = MessageChunk(
            transfer_id="test",
            chunk_index=0,
            total_chunks=1,
            data=data,
            checksum=checksum
        )
        
        assert chunk.verify_checksum() is True
        print("✅ Valid checksum verification test passed")
    
    def test_verify_checksum_invalid(self):
        """無効なチェックサム検証"""
        chunk = MessageChunk(
            transfer_id="test",
            chunk_index=0,
            total_chunks=1,
            data=b"some data",
            checksum="invalid_checksum"
        )
        
        assert chunk.verify_checksum() is False
        print("✅ Invalid checksum verification test passed")


class TestChunkedTransfer:
    """チャンク転送状態のテスト"""
    
    def test_create_transfer(self):
        """転送状態の作成"""
        transfer = ChunkedTransfer(
            transfer_id="transfer-001",
            sender_id="entity-a",
            recipient_id="entity-b",
            msg_type="test_message",
            total_chunks=10
        )
        
        assert transfer.transfer_id == "transfer-001"
        assert transfer.sender_id == "entity-a"
        assert transfer.recipient_id == "entity-b"
        assert transfer.total_chunks == 10
        assert transfer.status == ChunkStatus.PENDING
        assert transfer.chunks == {}
        print("✅ ChunkedTransfer creation test passed")
    
    def test_is_complete_true(self):
        """転送完了判定（完了）"""
        transfer = ChunkedTransfer(
            transfer_id="transfer-002",
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            total_chunks=2
        )
        
        # 全チャンク追加
        transfer.chunks[0] = MessageChunk("transfer-002", 0, 2, b"part1", "cs1")
        transfer.chunks[1] = MessageChunk("transfer-002", 1, 2, b"part2", "cs2")
        
        assert transfer.is_complete() is True
        print("✅ Transfer complete test passed")
    
    def test_is_complete_false(self):
        """転送完了判定（未完了）"""
        transfer = ChunkedTransfer(
            transfer_id="transfer-003",
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            total_chunks=3
        )
        
        # 一部のチャンクのみ
        transfer.chunks[0] = MessageChunk("transfer-003", 0, 3, b"part1", "cs1")
        
        assert transfer.is_complete() is False
        print("✅ Transfer incomplete test passed")
    
    def test_get_progress(self):
        """転送進捗の計算"""
        transfer = ChunkedTransfer(
            transfer_id="transfer-004",
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            total_chunks=4
        )
        
        # 進捗0%
        assert transfer.get_progress() == 0.0
        
        # 進捗25%
        transfer.chunks[0] = MessageChunk("transfer-004", 0, 4, b"p1", "c1")
        assert transfer.get_progress() == 0.25
        
        # 進捗50%
        transfer.chunks[1] = MessageChunk("transfer-004", 1, 4, b"p2", "c2")
        assert transfer.get_progress() == 0.5
        
        # 進捗100%
        transfer.chunks[2] = MessageChunk("transfer-004", 2, 4, b"p3", "c3")
        transfer.chunks[3] = MessageChunk("transfer-004", 3, 4, b"p4", "c4")
        assert transfer.get_progress() == 1.0
        
        print("✅ Transfer progress test passed")
    
    def test_assemble_message_success(self):
        """メッセージの組み立て成功"""
        test_message = {"key": "value", "number": 123}
        message_json = json.dumps(test_message).encode('utf-8')
        
        # チャンク分割
        chunk1 = MessageChunk("t1", 0, 2, message_json[:10], "cs1")
        chunk2 = MessageChunk("t1", 1, 2, message_json[10:], "cs2")
        
        transfer = ChunkedTransfer(
            transfer_id="t1",
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            total_chunks=2
        )
        transfer.chunks[0] = chunk1
        transfer.chunks[1] = chunk2
        
        result = transfer.assemble_message()
        
        assert result == test_message
        print("✅ Message assembly test passed")
    
    def test_assemble_message_incomplete(self):
        """不完全な転送の組み立て"""
        transfer = ChunkedTransfer(
            transfer_id="t2",
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            total_chunks=3
        )
        transfer.chunks[0] = MessageChunk("t2", 0, 3, b"p1", "c1")
        
        result = transfer.assemble_message()
        
        assert result is None
        print("✅ Incomplete assembly test passed")
    
    def test_assemble_message_size_limit(self):
        """サイズ制限超過の組み立て"""
        transfer = ChunkedTransfer(
            transfer_id="t3",
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            total_chunks=1
        )
        # 50MB超のデータ
        transfer.chunks[0] = MessageChunk("t3", 0, 1, b"x" * (51 * 1024 * 1024), "c1")
        
        result = transfer.assemble_message()
        
        assert result is None
        print("✅ Size limit assembly test passed")


class TestChunkedTransferManager:
    """転送マネージャーのテスト"""
    
    def test_init_default(self):
        """デフォルト初期化"""
        manager = ChunkedTransferManager()
        
        assert manager.chunk_size == 32768  # 32KB
        assert manager.max_transfer_size == 10485760  # 10MB
        assert manager.expiry_minutes == 30
        assert manager._transfers == {}
        print("✅ Manager default init test passed")
    
    def test_init_custom(self):
        """カスタム初期化"""
        manager = ChunkedTransferManager(
            chunk_size=1024,
            max_transfer_size=1024 * 1024,
            expiry_minutes=60
        )
        
        assert manager.chunk_size == 1024
        assert manager.max_transfer_size == 1024 * 1024
        assert manager.expiry_minutes == 60
        print("✅ Manager custom init test passed")
    
    def test_create_transfer_simple(self):
        """シンプルな転送作成"""
        manager = ChunkedTransferManager()
        
        message = {"test": "data"}
        chunks = manager.create_transfer(
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            message=message
        )
        
        # 小さなメッセージは1チャンク
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1
        print("✅ Simple transfer creation test passed")
    
    def test_create_transfer_large(self):
        """大きなメッセージの転送作成"""
        manager = ChunkedTransferManager(chunk_size=100)  # 100バイトチャンク
        
        # 約300バイトのメッセージ
        message = {"data": "x" * 250}
        chunks = manager.create_transfer(
            sender_id="a",
            recipient_id="b",
            msg_type="large",
            message=message
        )
        
        # 複数チャンクに分割される
        assert len(chunks) > 1
        print(f"✅ Large transfer creation test passed ({len(chunks)} chunks)")
    
    def test_create_transfer_too_large(self):
        """サイズ制限超過の転送作成"""
        manager = ChunkedTransferManager(max_transfer_size=100)
        
        # 制限を超えるメッセージ
        message = {"data": "x" * 200}
        
        try:
            manager.create_transfer(
                sender_id="a",
                recipient_id="b",
                msg_type="test",
                message=message
            )
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "exceeds maximum" in str(e)
        print("✅ Size limit transfer creation test passed")
    
    def test_initialize_transfer(self):
        """受信転送の初期化"""
        manager = ChunkedTransferManager()
        
        transfer = manager.initialize_transfer(
            transfer_id="recv-001",
            sender_id="entity-a",
            recipient_id="entity-b",
            msg_type="document",
            total_chunks=5,
            metadata={"filename": "test.pdf"}
        )
        
        assert transfer.transfer_id == "recv-001"
        assert transfer.total_chunks == 5
        assert transfer.metadata["filename"] == "test.pdf"
        assert "recv-001" in manager._transfers
        print("✅ Initialize transfer test passed")
    
    def test_receive_chunk_success(self):
        """チャンク受信成功"""
        manager = ChunkedTransferManager()
        
        # 転送を初期化
        manager.initialize_transfer(
            transfer_id="recv-002",
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            total_chunks=2
        )
        
        import hashlib
        data = b"chunk data"
        checksum = hashlib.sha256(data).hexdigest()[:32]
        
        chunk = MessageChunk("recv-002", 0, 2, data, checksum)
        result = manager.receive_chunk(chunk)
        
        assert result is not None
        assert result.status == ChunkStatus.IN_PROGRESS
        print("✅ Receive chunk test passed")
    
    def test_receive_chunk_invalid_checksum(self):
        """無効なチェックサムのチャンク受信"""
        manager = ChunkedTransferManager()
        
        manager.initialize_transfer(
            transfer_id="recv-003",
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            total_chunks=1
        )
        
        chunk = MessageChunk("recv-003", 0, 1, b"data", "invalid")
        result = manager.receive_chunk(chunk)
        
        assert result is None
        print("✅ Invalid checksum chunk test passed")
    
    def test_receive_chunk_unknown_transfer(self):
        """未知の転送のチャンク受信"""
        manager = ChunkedTransferManager()
        
        import hashlib
        data = b"data"
        checksum = hashlib.sha256(data).hexdigest()[:32]
        
        chunk = MessageChunk("unknown", 0, 1, data, checksum)
        result = manager.receive_chunk(chunk)
        
        assert result is None
        print("✅ Unknown transfer chunk test passed")
    
    def test_get_transfer(self):
        """転送の取得"""
        manager = ChunkedTransferManager()
        
        manager.initialize_transfer(
            transfer_id="get-test",
            sender_id="a",
            recipient_id="b",
            msg_type="test",
            total_chunks=1
        )
        
        transfer = manager.get_transfer("get-test")
        assert transfer is not None
        assert transfer.transfer_id == "get-test"
        
        # 存在しない転送
        assert manager.get_transfer("nonexistent") is None
        print("✅ Get transfer test passed")
    
    def test_get_stats(self):
        """統計情報取得"""
        manager = ChunkedTransferManager()
        
        stats = manager.get_stats()
        
        assert stats["active_transfers"] == 0
        assert stats["chunk_size"] == 32768
        assert stats["max_transfer_size"] == 10485760
        assert stats["expiry_minutes"] == 30
        assert "by_status" in stats
        print("✅ Manager stats test passed")


class TestChunkedMessageProtocol:
    """プロトコルハンドラのテスト"""
    
    def test_create_chunk_message(self):
        """チャンクメッセージ作成"""
        manager = ChunkedTransferManager()
        protocol = ChunkedMessageProtocol(manager)
        
        chunk = MessageChunk("t-001", 0, 2, b"data", "cs")
        message = protocol.create_chunk_message(chunk, "entity-a", "session-123")
        
        assert message["version"] == "1.1"
        assert message["msg_type"] == "chunk"
        assert message["sender_id"] == "entity-a"
        assert message["session_id"] == "session-123"
        assert "payload" in message
        assert "timestamp" in message
        print("✅ Create chunk message test passed")
    
    def test_parse_chunk_message(self):
        """チャンクメッセージ解析"""
        manager = ChunkedTransferManager()
        protocol = ChunkedMessageProtocol(manager)
        
        # 有効なメッセージ
        import base64
        data = b"test chunk data"
        chunk = MessageChunk("t-002", 1, 3, data, "cs123")
        message = protocol.create_chunk_message(chunk, "entity-b")
        
        parsed = protocol.parse_chunk_message(message)
        
        assert parsed is not None
        assert parsed.transfer_id == "t-002"
        assert parsed.chunk_index == 1
        assert parsed.total_chunks == 3
        print("✅ Parse chunk message test passed")
    
    def test_parse_invalid_chunk_message(self):
        """無効なチャンクメッセージ解析"""
        manager = ChunkedTransferManager()
        protocol = ChunkedMessageProtocol(manager)
        
        # 無効なメッセージ
        invalid_message = {
            "version": "1.1",
            "payload": {}  # chunkがない
        }
        
        result = protocol.parse_chunk_message(invalid_message)
        assert result is None
        print("✅ Parse invalid chunk message test passed")
    
    def test_create_transfer_init_message(self):
        """転送初期化メッセージ作成"""
        manager = ChunkedTransferManager()
        protocol = ChunkedMessageProtocol(manager)
        
        message = protocol.create_transfer_init_message(
            transfer_id="init-001",
            sender_id="entity-a",
            recipient_id="entity-b",
            msg_type="large_file",
            total_chunks=10,
            total_size=102400,
            metadata={"filename": "data.bin"}
        )
        
        assert message["version"] == "1.1"
        assert message["msg_type"] == "chunk_init"
        assert message["payload"]["transfer_id"] == "init-001"
        assert message["payload"]["total_chunks"] == 10
        assert message["payload"]["total_size"] == 102400
        print("✅ Create transfer init message test passed")


class TestChunkMessageConvenience:
    """便利関数のテスト"""
    
    def test_chunk_message(self):
        """メッセージチャンク分割便利関数"""
        message = {
            "type": "test",
            "content": "Hello, World! " * 100  # 約1500バイト
        }
        
        chunks = chunk_message(
            message=message,
            sender_id="entity-a",
            recipient_id="entity-b",
            msg_type="test_msg",
            chunk_size=500
        )
        
        assert len(chunks) > 0
        assert all(c["version"] == "1.1" for c in chunks)
        assert all(c["msg_type"] == "chunk" for c in chunks)
        print(f"✅ Chunk message convenience test passed ({len(chunks)} chunks)")


async def run_async_tests():
    """非同期テスト"""
    # 現在は非同期テストがないが、将来の拡張のために用意
    print("\n✅ Async tests placeholder (no async tests yet)")


def run_all_tests():
    """全テスト実行"""
    print("\n" + "=" * 60)
    print("Chunked Transfer Tests - Phase1")
    print("=" * 60)
    
    # ChunkStatus tests
    TestChunkStatus().test_status_values()
    
    # MessageChunk tests
    chunk_tests = TestMessageChunk()
    chunk_tests.test_create_chunk()
    chunk_tests.test_chunk_to_dict()
    chunk_tests.test_chunk_from_dict()
    chunk_tests.test_verify_checksum_valid()
    chunk_tests.test_verify_checksum_invalid()
    
    # ChunkedTransfer tests
    transfer_tests = TestChunkedTransfer()
    transfer_tests.test_create_transfer()
    transfer_tests.test_is_complete_true()
    transfer_tests.test_is_complete_false()
    transfer_tests.test_get_progress()
    transfer_tests.test_assemble_message_success()
    transfer_tests.test_assemble_message_incomplete()
    transfer_tests.test_assemble_message_size_limit()
    
    # ChunkedTransferManager tests
    manager_tests = TestChunkedTransferManager()
    manager_tests.test_init_default()
    manager_tests.test_init_custom()
    manager_tests.test_create_transfer_simple()
    manager_tests.test_create_transfer_large()
    manager_tests.test_create_transfer_too_large()
    manager_tests.test_initialize_transfer()
    manager_tests.test_receive_chunk_success()
    manager_tests.test_receive_chunk_invalid_checksum()
    manager_tests.test_receive_chunk_unknown_transfer()
    manager_tests.test_get_transfer()
    manager_tests.test_get_stats()
    
    # ChunkedMessageProtocol tests
    protocol_tests = TestChunkedMessageProtocol()
    protocol_tests.test_create_chunk_message()
    protocol_tests.test_parse_chunk_message()
    protocol_tests.test_parse_invalid_chunk_message()
    protocol_tests.test_create_transfer_init_message()
    
    # Convenience function tests
    TestChunkMessageConvenience().test_chunk_message()
    
    print("\n" + "=" * 60)
    print("✅ All Phase1 chunked_transfer tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
    
    # 非同期テスト実行
    asyncio.run(run_async_tests())
