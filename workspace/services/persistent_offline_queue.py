#!/usr/bin/env python3
"""
Persistent Offline Message Queue
SQLite-based persistent message queue for offline peers

Features:
- Message persistence across restarts
- Automatic delivery when peer comes online
- Exponential backoff retry
- Expired message cleanup
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessageStatus(Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class PeerStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class QueuedMessage:
    message_id: str
    sender_id: str
    recipient_id: str
    message_type: str
    payload: Dict[str, Any]
    priority: int
    created_at: datetime
    expires_at: datetime
    status: MessageStatus
    retry_count: int
    max_retries: int
    next_retry_at: Optional[datetime] = None


@dataclass
class QueueStats:
    total_messages: int
    pending: int
    delivered: int
    failed: int
    by_recipient: Dict[str, int]


class PersistentOfflineQueue:
    """SQLite-based persistent message queue for offline peers"""
    
    def __init__(self, db_path: str = "data/offline_queue.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._initialized = False
        
    async def initialize(self):
        """Initialize database tables"""
        if self._initialized:
            return
            
        async with self._lock:
            await asyncio.to_thread(self._init_db)
            self._initialized = True
            logger.info(f"PersistentOfflineQueue initialized: {self.db_path}")
    
    def _init_db(self):
        """Create tables (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE NOT NULL,
                    sender_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    priority INTEGER DEFAULT 5,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 5,
                    next_retry_at TIMESTAMP,
                    delivered_at TIMESTAMP,
                    error_message TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_recipient_status 
                    ON messages(recipient_id, status);
                CREATE INDEX IF NOT EXISTS idx_next_retry 
                    ON messages(next_retry_at, status);
                CREATE INDEX IF NOT EXISTS idx_expires 
                    ON messages(expires_at);
                
                CREATE TABLE IF NOT EXISTS peers (
                    peer_id TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'offline',
                    last_seen TIMESTAMP,
                    last_heartbeat TIMESTAMP,
                    endpoint TEXT,
                    metadata TEXT
                );
                
                CREATE TABLE IF NOT EXISTS delivery_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN,
                    error_message TEXT,
                    FOREIGN KEY (message_id) REFERENCES messages(message_id)
                );
            """)
    
    async def enqueue(
        self,
        sender_id: str,
        recipient_id: str,
        message_type: str,
        payload: Dict[str, Any],
        priority: int = 5,
        ttl_hours: int = 72,
        max_retries: int = 5
    ) -> str:
        """Add message to queue"""
        await self.initialize()
        
        message_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ttl_hours)
        
        async with self._lock:
            await asyncio.to_thread(
                self._insert_message,
                message_id, sender_id, recipient_id, message_type,
                json.dumps(payload), priority, expires_at, max_retries
            )
        
        logger.info(f"Message queued: {message_id} for {recipient_id}")
        return message_id
    
    def _insert_message(self, *args):
        """Insert message (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO messages 
                (message_id, sender_id, recipient_id, message_type, payload,
                 priority, expires_at, max_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, args)
    
    async def mark_peer_online(self, peer_id: str) -> List[QueuedMessage]:
        """Mark peer as online and return pending messages"""
        await self.initialize()
        
        async with self._lock:
            await asyncio.to_thread(self._update_peer_status, peer_id, "online")
            messages = await asyncio.to_thread(
                self._get_pending_messages_sync, peer_id, 100
            )
        
        logger.info(f"Peer {peer_id} online, {len(messages)} messages pending")
        return messages
    
    async def mark_peer_offline(self, peer_id: str) -> None:
        """Mark peer as offline"""
        await self.initialize()
        
        async with self._lock:
            await asyncio.to_thread(self._update_peer_status, peer_id, "offline")
        
        logger.info(f"Peer {peer_id} marked offline")
    
    def _update_peer_status(self, peer_id: str, status: str):
        """Update peer status (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO peers 
                (peer_id, status, last_seen)
                VALUES (?, ?, ?)
            """, (peer_id, status, datetime.now(timezone.utc)))
    
    async def _get_pending_messages_for_test(self, recipient_id: str, limit: int) -> List[QueuedMessage]:
        """Get pending messages for testing"""
        async with self._lock:
            return await asyncio.to_thread(self._get_pending_messages_sync, recipient_id, limit)
    
    def _get_pending_messages_sync(self, recipient_id: str, limit: int) -> List[QueuedMessage]:
        """Get pending messages for recipient (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM messages 
                WHERE recipient_id = ? AND status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT ?
            """, (recipient_id, limit)).fetchall()
            
            return [self._row_to_message(row) for row in rows]
    
    def _row_to_message(self, row: sqlite3.Row) -> QueuedMessage:
        """Convert row to QueuedMessage"""
        return QueuedMessage(
            message_id=row["message_id"],
            sender_id=row["sender_id"],
            recipient_id=row["recipient_id"],
            message_type=row["message_type"],
            payload=json.loads(row["payload"]),
            priority=row["priority"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            status=MessageStatus(row["status"]),
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            next_retry_at=row["next_retry_at"]
        )
    
    async def mark_delivered(self, message_id: str) -> None:
        """Mark message as delivered"""
        await self.initialize()
        
        async with self._lock:
            await asyncio.to_thread(self._update_status, message_id, "delivered")
        
        logger.debug(f"Message marked delivered: {message_id}")
    
    async def mark_failed(self, message_id: str, error: str) -> bool:
        """Mark delivery attempt as failed, schedule retry if possible"""
        await self.initialize()
        
        async with self._lock:
            # Get current retry count
            retry_info = await asyncio.to_thread(
                self._get_retry_info, message_id
            )
            
            if not retry_info:
                return False
            
            retry_count, max_retries = retry_info
            
            if retry_count >= max_retries - 1:
                # Max retries reached
                await asyncio.to_thread(
                    self._update_status, message_id, "failed", error
                )
                logger.warning(f"Message failed after max retries: {message_id}")
                return False
            
            # Schedule retry with exponential backoff
            next_retry = datetime.now(timezone.utc) + timedelta(
                seconds=min(300, 2 ** retry_count)
            )
            await asyncio.to_thread(
                self._schedule_retry, message_id, retry_count + 1, next_retry
            )
        
        logger.debug(f"Message retry scheduled: {message_id}")
        return True
    
    def _get_retry_info(self, message_id: str) -> Optional[tuple]:
        """Get retry count and max retries (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT retry_count, max_retries FROM messages WHERE message_id = ?",
                (message_id,)
            ).fetchone()
            return row if row else None
    
    def _update_status(self, message_id: str, status: str, error: str = None):
        """Update message status (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            if status == "delivered":
                conn.execute("""
                    UPDATE messages 
                    SET status = ?, delivered_at = ?
                    WHERE message_id = ?
                """, (status, datetime.now(timezone.utc), message_id))
            else:
                conn.execute("""
                    UPDATE messages 
                    SET status = ?, error_message = ?
                    WHERE message_id = ?
                """, (status, error, message_id))
    
    def _schedule_retry(self, message_id: str, retry_count: int, next_retry: datetime):
        """Schedule retry (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE messages 
                SET retry_count = ?, next_retry_at = ?
                WHERE message_id = ?
            """, (retry_count, next_retry, message_id))
    
    async def get_messages_for_retry(self) -> List[QueuedMessage]:
        """Get messages ready for retry"""
        await self.initialize()
        
        async with self._lock:
            messages = await asyncio.to_thread(self._get_retry_messages)
        
        return messages
    
    def _get_retry_messages(self) -> List[QueuedMessage]:
        """Get messages ready for retry (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM messages 
                WHERE status = 'pending' 
                AND next_retry_at IS NOT NULL
                AND next_retry_at <= ?
                ORDER BY priority ASC
            """, (datetime.now(timezone.utc),)).fetchall()
            
            return [self._row_to_message(row) for row in rows]
    
    async def cleanup_expired(self, max_age_days: int = 7) -> int:
        """Remove expired and old delivered/failed messages"""
        await self.initialize()
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        
        async with self._lock:
            count = await asyncio.to_thread(self._delete_expired, cutoff)
        
        logger.info(f"Cleaned up {count} expired messages")
        return count
    
    def _delete_expired(self, cutoff: datetime) -> int:
        """Delete expired messages (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            # Delete expired pending messages
            conn.execute("""
                DELETE FROM messages 
                WHERE status = 'pending' AND expires_at < ?
            """, (datetime.now(timezone.utc),))
            
            # Delete old delivered/failed messages
            conn.execute("""
                DELETE FROM messages 
                WHERE status IN ('delivered', 'failed') 
                AND delivered_at < ?
            """, (cutoff,))
            
            return conn.total_changes
    
    async def get_stats(self) -> QueueStats:
        """Get queue statistics"""
        await self.initialize()
        
        async with self._lock:
            stats = await asyncio.to_thread(self._get_stats_sync)
        
        return stats
    
    def _get_stats_sync(self) -> QueueStats:
        """Get stats (sync version)"""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM messages"
            ).fetchone()[0]
            
            pending = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE status = 'pending'"
            ).fetchone()[0]
            
            delivered = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE status = 'delivered'"
            ).fetchone()[0]
            
            failed = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE status = 'failed'"
            ).fetchone()[0]
            
            # By recipient
            cursor = conn.execute(
                "SELECT recipient_id, COUNT(*) FROM messages WHERE status = 'pending' GROUP BY recipient_id"
            )
            by_recipient = {row[0]: row[1] for row in cursor}
            
            return QueueStats(
                total_messages=total,
                pending=pending,
                delivered=delivered,
                failed=failed,
                by_recipient=by_recipient
            )
    
    async def close(self):
        """Close queue (no-op for SQLite)"""
        logger.info("PersistentOfflineQueue closed")


# Convenience function
async def create_offline_queue(db_path: str = "data/offline_queue.db") -> PersistentOfflineQueue:
    """Create and initialize offline queue"""
    queue = PersistentOfflineQueue(db_path)
    await queue.initialize()
    return queue
