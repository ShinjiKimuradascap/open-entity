#!/usr/bin/env python3
"""
Chunk Manager Module
Protocol v1.0 対応のメッセージチャンク管理

機能:
- 大きなメッセージのチャンク分割
- チャンクの再構築
- タイムアウト管理
- 重複チャンク検出
"""

import asyncio
import hashlib
import logging
import secrets
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum

logger = logging.getLogger(__name__)


class AssemblyStatus(Enum):
    """メッセージ再構築状態"""
    PENDING = "pending"       # 受信中
    COMPLETE = "complete"     # 完了
    EXPIRED = "expired"       # 期限切れ
    ERROR = "error"           # エラー


@dataclass
class Chunk:
    """メッセージチャンク"""
    chunk_index: int           # チャンクインデックス（0-based）
    total_chunks: int          # 合計チャンク数
    data: bytes                # チャンクデータ
    checksum: Optional[str] = None  # データのMD5ハッシュ
    
    def __post_init__(self):
        if self.checksum is None:
            self.checksum = hashlib.md5(self.data).hexdigest()
    
    def verify(self) -> bool:
        """チェックサムを検証"""
        return self.checksum == hashlib.md5(self.data).hexdigest()
    
    def to_dict(self) -> dict:
        """ディクショナリに変換"""
        return {
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "data": self.data.hex(),
            "checksum": self.checksum
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Chunk":
        """ディクショナリから作成"""
        return cls(
            chunk_index=data["chunk_index"],
            total_chunks=data["total_chunks"],
            data=bytes.fromhex(data["data"]),
            checksum=data.get("checksum")
        )


@dataclass
class ChunkedMessage:
    """チャンク化されたメッセージ"""
    message_id: str
    session_id: str
    sender_id: str
    recipient_id: str
    msg_type: str
    total_size: int
    chunk_size: int
    total_chunks: int
    chunks: Dict[int, Chunk] = field(default_factory=dict)
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    assembled_data: Optional[bytes] = None
    status: AssemblyStatus = AssemblyStatus.PENDING
    error_message: Optional[str] = None
    
    def add_chunk(self, chunk: Chunk) -> bool:
        """
        チャンクを追加
        
        Returns:
            True if valid and added, False otherwise
        """
        # バリデーション
        if chunk.chunk_index >= self.total_chunks:
            self.error_message = f"Invalid chunk index: {chunk.chunk_index} >= {self.total_chunks}"
            self.status = AssemblyStatus.ERROR
            return False
        
        if chunk.total_chunks != self.total_chunks:
            self.error_message = f"Chunk count mismatch: {chunk.total_chunks} != {self.total_chunks}"
            self.status = AssemblyStatus.ERROR
            return False
        
        if not chunk.verify():
            self.error_message = f"Checksum mismatch for chunk {chunk.chunk_index}"
            self.status = AssemblyStatus.ERROR
            return False
        
        # 追加
        self.chunks[chunk.chunk_index] = chunk
        return True
    
    def is_complete(self) -> bool:
        """すべてのチャンクが揃ったかチェック"""
        return len(self.chunks) == self.total_chunks
    
    def assemble(self) -> Optional[bytes]:
        """
        チャンクを再構築
        
        Returns:
            再構築されたデータ、またはNone
        """
        if not self.is_complete():
            return None
        
        if self.assembled_data is not None:
            return self.assembled_data
        
        try:
            # インデックス順にソートして結合
            sorted_chunks = [self.chunks[i] for i in sorted(self.chunks.keys())]
            self.assembled_data = b"".join(chunk.data for chunk in sorted_chunks)
            
            # サイズ検証
            if len(self.assembled_data) != self.total_size:
                self.error_message = f"Size mismatch: {len(self.assembled_data)} != {self.total_size}"
                self.status = AssemblyStatus.ERROR
                return None
            
            self.status = AssemblyStatus.COMPLETE
            return self.assembled_data
            
        except Exception as e:
            self.error_message = f"Assembly error: {e}"
            self.status = AssemblyStatus.ERROR
            return None
    
    def get_progress(self) -> Tuple[int, int, float]:
        """
        再構築進捗を取得
        
        Returns:
            (received_chunks, total_chunks, percentage)
        """
        received = len(self.chunks)
        percentage = (received / self.total_chunks * 100) if self.total_chunks > 0 else 0
        return (received, self.total_chunks, percentage)
    
    def get_missing_indices(self) -> List[int]:
        """欠落しているチャンクインデックスを取得"""
        return [i for i in range(self.total_chunks) if i not in self.chunks]
    
    def to_dict(self) -> dict:
        """ディクショナリに変換"""
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "msg_type": self.msg_type,
            "total_size": self.total_size,
            "chunk_size": self.chunk_size,
            "total_chunks": self.total_chunks,
            "received_chunks": len(self.chunks),
            "progress": self.get_progress()[2],
            "status": self.status.value,
            "received_at": self.received_at.isoformat(),
            "is_complete": self.is_complete()
        }


class ChunkManager:
    """
    チャンク管理クラス
    
    Protocol v1.0 対応:
    - メッセージの分割と再構築
    - タイムアウト管理
    - 重複検出
    """
    
    def __init__(
        self,
        default_chunk_size: int = 65536,      # デフォルト64KB
        max_chunk_size: int = 262144,          # 最大256KB
        assembly_timeout: int = 300,           # 再構築タイムアウト（秒）
        max_pending_messages: int = 100,       # 最大保留メッセージ数
        auto_cleanup_interval: int = 60        # クリーンアップ間隔（秒）
    ):
        self.default_chunk_size = default_chunk_size
        self.max_chunk_size = max_chunk_size
        self.assembly_timeout = timedelta(seconds=assembly_timeout)
        self.max_pending_messages = max_pending_messages
        
        # 保留中のメッセージ {message_id: ChunkedMessage}
        self._pending_messages: Dict[str, ChunkedMessage] = {}
        
        # 受信済みチャンクトラッキング {(message_id, chunk_index): received_at}
        self._received_chunks: Dict[Tuple[str, int], datetime] = {}
        
        # ロック
        self._lock = asyncio.Lock()
        
        # クリーンアップ
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = auto_cleanup_interval
        
        # 統計
        self._stats = {
            "messages_chunked": 0,
            "messages_assembled": 0,
            "messages_expired": 0,
            "chunks_received": 0,
            "chunks_duplicates": 0,
            "total_bytes_chunked": 0,
            "total_bytes_assembled": 0
        }
    
    async def start(self) -> None:
        """チャンクマネージャーを開始"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("ChunkManager started")
    
    async def stop(self) -> None:
        """チャンクマネージャーを停止"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        
        async with self._lock:
            self._pending_messages.clear()
            self._received_chunks.clear()
        
        logger.info("ChunkManager stopped")
    
    def create_chunks(
        self,
        data: bytes,
        message_id: str,
        session_id: str,
        sender_id: str,
        recipient_id: str,
        msg_type: str,
        chunk_size: Optional[int] = None
    ) -> List[dict]:
        """
        データをチャンクに分割
        
        Args:
            data: 分割するデータ
            message_id: メッセージID
            session_id: セッションID
            sender_id: 送信者ID
            recipient_id: 受信者ID
            msg_type: メッセージタイプ
            chunk_size: チャンクサイズ（Noneの場合はデフォルト）
            
        Returns:
            チャンクディクショナリのリスト（送信用）
        """
        size = chunk_size or self.default_chunk_size
        size = min(size, self.max_chunk_size)
        
        total_size = len(data)
        total_chunks = (total_size + size - 1) // size
        
        chunks = []
        for i in range(total_chunks):
            start = i * size
            end = min(start + size, total_size)
            chunk_data = data[start:end]
            
            chunk = Chunk(
                chunk_index=i,
                total_chunks=total_chunks,
                data=chunk_data
            )
            
            # 送信用メタデータ
            chunk_meta = {
                "version": "1.0",
                "msg_type": "chunk",
                "sender_id": sender_id,
                "recipient_id": recipient_id,
                "session_id": session_id,
                "message_id": message_id,
                "original_msg_type": msg_type,
                "chunk": chunk.to_dict(),
                "total_size": total_size,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "nonce": secrets.token_hex(16)
            }
            
            chunks.append(chunk_meta)
        
        self._stats["messages_chunked"] += 1
        self._stats["total_bytes_chunked"] += total_size
        
        logger.debug(
            f"Created {len(chunks)} chunks for message {message_id} "
            f"({total_size} bytes)"
        )
        
        return chunks
    
    async def receive_chunk(self, chunk_data: dict) -> Tuple[AssemblyStatus, Optional[bytes]]:
        """
        チャンクを受信して処理
        
        Args:
            chunk_data: チャンクメタデータ
            
        Returns:
            (status, assembled_data)
        """
        message_id = chunk_data.get("message_id")
        session_id = chunk_data.get("session_id")
        sender_id = chunk_data.get("sender_id")
        recipient_id = chunk_data.get("recipient_id")
        msg_type = chunk_data.get("original_msg_type")
        total_size = chunk_data.get("total_size")
        chunk_info = chunk_data.get("chunk", {})
        
        if not all([message_id, session_id, chunk_info]):
            return AssemblyStatus.ERROR, None
        
        chunk_index = chunk_info.get("chunk_index")
        chunk_key = (message_id, chunk_index)
        
        async with self._lock:
            # 重複チェック
            if chunk_key in self._received_chunks:
                self._stats["chunks_duplicates"] += 1
                logger.debug(f"Duplicate chunk received: {message_id}[{chunk_index}]")
                
                # 既存のメッセージが完了しているか確認
                if message_id in self._pending_messages:
                    msg = self._pending_messages[message_id]
                    if msg.status == AssemblyStatus.COMPLETE:
                        return AssemblyStatus.COMPLETE, msg.assembled_data
                
                return AssemblyStatus.PENDING, None
            
            # 受信記録
            self._received_chunks[chunk_key] = datetime.now(timezone.utc)
            self._stats["chunks_received"] += 1
            
            # メッセージ取得または作成
            if message_id not in self._pending_messages:
                # 保留メッセージ数チェック
                if len(self._pending_messages) >= self.max_pending_messages:
                    logger.warning("Max pending messages reached, dropping chunk")
                    return AssemblyStatus.ERROR, None
                
                # 新規作成
                total_chunks = chunk_info.get("total_chunks", 1)
                chunk_size = len(bytes.fromhex(chunk_info.get("data", "")))
                
                self._pending_messages[message_id] = ChunkedMessage(
                    message_id=message_id,
                    session_id=session_id,
                    sender_id=sender_id,
                    recipient_id=recipient_id,
                    msg_type=msg_type or "unknown",
                    total_size=total_size or (chunk_size * total_chunks),
                    chunk_size=chunk_size,
                    total_chunks=total_chunks
                )
            
            chunked_msg = self._pending_messages[message_id]
            
            # チャンクを追加
            try:
                chunk = Chunk.from_dict(chunk_info)
                if not chunked_msg.add_chunk(chunk):
                    return AssemblyStatus.ERROR, None
                
                # 完了チェック
                if chunked_msg.is_complete():
                    assembled = chunked_msg.assemble()
                    if assembled is not None:
                        self._stats["messages_assembled"] += 1
                        self._stats["total_bytes_assembled"] += len(assembled)
                        logger.info(
                            f"Message {message_id} assembled from "
                            f"{chunked_msg.total_chunks} chunks"
                        )
                        return AssemblyStatus.COMPLETE, assembled
                    else:
                        return AssemblyStatus.ERROR, None
                
                return AssemblyStatus.PENDING, None
                
            except Exception as e:
                logger.error(f"Error processing chunk: {e}")
                chunked_msg.status = AssemblyStatus.ERROR
                chunked_msg.error_message = str(e)
                return AssemblyStatus.ERROR, None
    
    async def get_progress(self, message_id: str) -> Optional[Tuple[int, int, float]]:
        """メッセージの再構築進捗を取得"""
        async with self._lock:
            msg = self._pending_messages.get(message_id)
            if not msg:
                return None
            return msg.get_progress()
    
    async def get_pending_messages(self) -> List[dict]:
        """保留中のメッセージ一覧を取得"""
        async with self._lock:
            return [msg.to_dict() for msg in self._pending_messages.values()]
    
    async def get_stats(self) -> dict:
        """統計情報を取得"""
        async with self._lock:
            return {
                **self._stats,
                "pending_messages": len(self._pending_messages),
                "received_chunk_entries": len(self._received_chunks)
            }
    
    async def _cleanup_loop(self) -> None:
        """期限切れメッセージのクリーンアップループ"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_expired(self) -> None:
        """期限切れメッセージをクリーンアップ"""
        now = datetime.now(timezone.utc)
        expired_messages = []
        
        async with self._lock:
            # メッセージのクリーンアップ
            for message_id, msg in list(self._pending_messages.items()):
                if msg.status == AssemblyStatus.COMPLETE:
                    # 完了メッセージは5分後に削除
                    age = (now - msg.received_at).total_seconds()
                    if age > 300:
                        expired_messages.append(message_id)
                
                elif msg.status == AssemblyStatus.ERROR:
                    # エラーメッセージは即削除
                    expired_messages.append(message_id)
                
                else:
                    # タイムアウトチェック
                    age = (now - msg.received_at).total_seconds()
                    if age > self.assembly_timeout.total_seconds():
                        msg.status = AssemblyStatus.EXPIRED
                        expired_messages.append(message_id)
                        self._stats["messages_expired"] += 1
                        logger.warning(
                            f"Message {message_id} assembly timed out "
                            f"({len(msg.chunks)}/{msg.total_chunks} chunks)"
                        )
            
            # 削除実行
            for message_id in expired_messages:
                if message_id in self._pending_messages:
                    del self._pending_messages[message_id]
            
            # 古いチャンク受信記録をクリーンアップ
            old_chunks = [
                key for key, received_at in self._received_chunks.items()
                if (now - received_at).total_seconds() > self.assembly_timeout.total_seconds() * 2
            ]
            for key in old_chunks:
                del self._received_chunks[key]
        
        if expired_messages:
            logger.info(f"Cleaned up {len(expired_messages)} expired/incomplete messages")


# グローバルインスタンス
_chunk_manager: Optional[ChunkManager] = None


def init_chunk_manager(**kwargs) -> ChunkManager:
    """チャンクマネージャーを初期化"""
    global _chunk_manager
    _chunk_manager = ChunkManager(**kwargs)
    return _chunk_manager


def get_chunk_manager() -> Optional[ChunkManager]:
    """チャンクマネージャーを取得"""
    return _chunk_manager


if __name__ == "__main__":
    # テスト実行
    import asyncio
    
    async def run_tests():
        print("=" * 60)
        print("ChunkManager Test")
        print("=" * 60)
        
        # 1. 初期化
        print("\n1. Initialization Test")
        manager = init_chunk_manager()
        await manager.start()
        print(f"   ChunkManager initialized")
        print(f"   Default chunk size: {manager.default_chunk_size} bytes")
        
        # 2. チャンク作成
        print("\n2. Chunk Creation Test")
        test_data = b"Hello, World! " * 5000  # 約70KB
        chunks = manager.create_chunks(
            data=test_data,
            message_id="msg-001",
            session_id="session-001",
            sender_id="entity-a",
            recipient_id="entity-b",
            msg_type="test"
        )
        print(f"   Original size: {len(test_data)} bytes")
        print(f"   Number of chunks: {len(chunks)}")
        print(f"   First chunk size: {len(chunks[0]['chunk']['data']) // 2} bytes (hex encoded)")
        
        # 3. チャンク受信・再構築
        print("\n3. Chunk Reception & Assembly Test")
        
        # 順不同で受信（シミュレーション）
        import random
        shuffled_chunks = chunks.copy()
        random.shuffle(shuffled_chunks)
        
        assembled_data = None
        for chunk_meta in shuffled_chunks:
            status, data = await manager.receive_chunk(chunk_meta)
            if status == AssemblyStatus.COMPLETE:
                assembled_data = data
                print(f"   Assembly complete!")
        
        if assembled_data:
            print(f"   Assembled size: {len(assembled_data)} bytes")
            print(f"   Data integrity: {assembled_data == test_data}")
        
        # 4. 重複チャンク検出
        print("\n4. Duplicate Detection Test")
        status, data = await manager.receive_chunk(chunks[0])
        print(f"   Duplicate detected: {status == AssemblyStatus.PENDING and data is None}")
        
        # 5. 統計確認
        print("\n5. Statistics Test")
        stats = await manager.get_stats()
        print(f"   Messages chunked: {stats['messages_chunked']}")
        print(f"   Messages assembled: {stats['messages_assembled']}")
        print(f"   Chunks received: {stats['chunks_received']}")
        print(f"   Duplicates detected: {stats['chunks_duplicates']}")
        
        # クリーンアップ
        await manager.stop()
        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)
    
    asyncio.run(run_tests())
