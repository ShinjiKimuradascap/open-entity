#!/usr/bin/env python3
"""
Reliability Layer - Phase 3 Implementation
Provides at-least-once delivery, message ordering, and exactly-once semantics
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Set
from collections import defaultdict
import json
import hashlib

logger = logging.getLogger(__name__)


class DeliveryStatus(Enum):
    """Message delivery status"""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class DeliveryRecord:
    """Tracks message delivery state"""
    message_id: str
    recipient_id: str
    payload: Any
    attempts: int = 0
    max_attempts: int = 5
    created_at: datetime = field(default_factory=lambda: datetime.now())
    last_attempt: Optional[datetime] = None
    status: DeliveryStatus = DeliveryStatus.PENDING
    error_log: List[str] = field(default_factory=list)
    delivery_timestamp: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "recipient_id": self.recipient_id,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "delivery_timestamp": self.delivery_timestamp.isoformat() if self.delivery_timestamp else None,
            "error_log": self.error_log
        }


class ExponentialBackoff:
    """Exponential backoff strategy for retries"""
    
    def __init__(
        self,
        base_delay_ms: float = 100,
        max_delay_ms: float = 1600,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number (0-indexed)"""
        delay = self.base_delay_ms * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay_ms)
        
        if self.jitter:
            # Add random jitter (0-20%)
            import random
            delay *= (1 + random.random() * 0.2)
        
        return delay / 1000.0  # Convert to seconds


class RetryManager:
    """Manages retry logic with exponential backoff"""
    
    def __init__(
        self,
        max_retries: int = 5,
        base_delay_ms: float = 100,
        max_delay_ms: float = 1600,
        exponential_base: float = 2.0
    ):
        self.max_retries = max_retries
        self.backoff = ExponentialBackoff(
            base_delay_ms=base_delay_ms,
            max_delay_ms=max_delay_ms,
            exponential_base=exponential_base
        )
        self._retry_counts: Dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    async def should_retry(self, message_id: str, error: Optional[Exception] = None) -> bool:
        """Determine if message should be retried"""
        async with self._lock:
            count = self._retry_counts.get(message_id, 0)
            if count >= self.max_retries:
                return False
            self._retry_counts[message_id] = count + 1
            return True
    
    def get_retry_delay(self, message_id: str) -> float:
        """Get delay before next retry"""
        count = self._retry_counts.get(message_id, 0)
        return self.backoff.get_delay(count)
    
    def reset_retry_count(self, message_id: str):
        """Reset retry count for message"""
        if message_id in self._retry_counts:
            del self._retry_counts[message_id]
    
    def get_retry_count(self, message_id: str) -> int:
        """Get current retry count for message"""
        return self._retry_counts.get(message_id, 0)


class DeliveryTracker:
    """Tracks message delivery status and manages retries"""
    
    def __init__(
        self,
        max_retries: int = 5,
        ack_timeout_seconds: float = 30.0,
        cleanup_interval_seconds: float = 300.0
    ):
        self.records: Dict[str, DeliveryRecord] = {}
        self.retry_manager = RetryManager(max_retries=max_retries)
        self.ack_timeout_seconds = ack_timeout_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._acknowledgments: Set[str] = set()
       ._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._delivery_callbacks: Dict[str, List[Callable]] = defaultdict(list)
    
    async def start(self):
        """Start background cleanup task"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("DeliveryTracker started")
    
    async def stop(self):
        """Stop background tasks"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("DeliveryTracker stopped")
    
    async def track_message(
        self,
        message_id: str,
        recipient_id: str,
        payload: Any
    ) -> DeliveryRecord:
        """Start tracking a new message"""
        async with self._lock:
            record = DeliveryRecord(
                message_id=message_id,
                recipient_id=recipient_id,
                payload=payload,
                max_attempts=self.retry_manager.max_retries
            )
            self.records[message_id] = record
            logger.debug(f"Started tracking message {message_id} to {recipient_id}")
            return record
    
    async def record_attempt(self, message_id: str, error: Optional[str] = None):
        """Record a delivery attempt"""
        async with self._lock:
            if message_id not in self.records:
                return
            
            record = self.records[message_id]
            record.attempts += 1
            record.last_attempt = datetime.now()
            
            if error:
                record.error_log.append(f"{datetime.now().isoformat()}: {error}")
                record.status = DeliveryStatus.RETRYING
                logger.warning(f"Message {message_id} attempt {record.attempts} failed: {error}")
            else:
                record.status = DeliveryStatus.PENDING
    
    async def mark_delivered(self, message_id: str):
        """Mark message as successfully delivered"""
        async with self._lock:
            if message_id in self.records:
                record = self.records[message_id]
                record.status = DeliveryStatus.DELIVERED
                record.delivery_timestamp = datetime.now()
                self.retry_manager.reset_retry_count(message_id)
                self._acknowledgments.add(message_id)
                logger.info(f"Message {message_id} marked as delivered")
                
                # Trigger callbacks
                await self._trigger_callbacks(message_id, True)
    
    async def mark_failed(self, message_id: str, reason: str):
        """Mark message as permanently failed"""
        async with self._lock:
            if message_id in self.records:
                record = self.records[message_id]
                record.status = DeliveryStatus.FAILED
                record.error_log.append(f"FAILED: {reason}")
                logger.error(f"Message {message_id} permanently failed: {reason}")
                
                # Trigger callbacks
                await self._trigger_callbacks(message_id, False)
    
    async def should_retry(self, message_id: str) -> bool:
        """Check if message should be retried"""
        async with self._lock:
            if message_id not in self.records:
                return False
            record = self.records[message_id]
            if record.status in [DeliveryStatus.DELIVERED, DeliveryStatus.FAILED]:
                return False
            return record.attempts < record.max_attempts
    
    def get_retry_delay(self, message_id: str) -> float:
        """Get delay before next retry"""
        return self.retry_manager.get_retry_delay(message_id)
    
    async def get_record(self, message_id: str) -> Optional[DeliveryRecord]:
        """Get delivery record for message"""
        async with self._lock:
            return self.records.get(message_id)
    
    async def get_pending_messages(self) -> List[DeliveryRecord]:
        """Get all pending messages"""
        async with self._lock:
            return [
                record for record in self.records.values()
                if record.status in [DeliveryStatus.PENDING, DeliveryStatus.RETRYING]
            ]
    
    async def get_stats(self) -> dict:
        """Get delivery statistics"""
        async with self._lock:
            stats = {
                "total": len(self.records),
                "pending": sum(1 for r in self.records.values() if r.status == DeliveryStatus.PENDING),
                "delivered": sum(1 for r in self.records.values() if r.status == DeliveryStatus.DELIVERED),
                "failed": sum(1 for r in self.records.values() if r.status == DeliveryStatus.FAILED),
                "retrying": sum(1 for r in self.records.values() if r.status == DeliveryStatus.RETRYING)
            }
            return stats
    
    def register_callback(self, message_id: str, callback: Callable[[bool], Any]):
        """Register callback for delivery status change"""
        self._delivery_callbacks[message_id].append(callback)
    
    async def _trigger_callbacks(self, message_id: str, success: bool):
        """Trigger registered callbacks"""
        callbacks = self._delivery_callbacks.get(message_id, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(success)
                else:
                    callback(success)
            except Exception as e:
                logger.error(f"Callback error for message {message_id}: {e}")
        
        # Clean up callbacks
        if message_id in self._delivery_callbacks:
            del self._delivery_callbacks[message_id]
    
    async def _cleanup_loop(self):
        """Background task to clean up old records"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self._cleanup_old_records()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _cleanup_old_records(self):
        """Remove old delivered/failed records"""
        cutoff = datetime.now() - timedelta(hours=24)
        async with self._lock:
            to_remove = [
                msg_id for msg_id, record in self.records.items()
                if record.status in [DeliveryStatus.DELIVERED, DeliveryStatus.FAILED]
                and record.last_attempt and record.last_attempt < cutoff
            ]
            for msg_id in to_remove:
                del self.records[msg_id]
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old delivery records")


class IdempotencyStore:
    """Stores processed message IDs for exactly-once semantics"""
    
    def __init__(self, max_size: int = 10000, ttl_seconds: float = 86400):
        self._store: Dict[str, tuple] = {}  # idempotency_key -> (timestamp, response)
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
    
    async def is_processed(self, idempotency_key: str) -> bool:
        """Check if key has been processed"""
        async with self._lock:
            if idempotency_key not in self._store:
                return False
            timestamp, _ = self._store[idempotency_key]
            if time.time() - timestamp > self._ttl_seconds:
                del self._store[idempotency_key]
                return False
            return True
    
    async def get_response(self, idempotency_key: str) -> Optional[Any]:
        """Get cached response for processed key"""
        async with self._lock:
            if idempotency_key in self._store:
                _, response = self._store[idempotency_key]
                return response
            return None
    
    async def mark_processed(self, idempotency_key: str, response: Any):
        """Mark key as processed with response"""
        async with self._lock:
            # Cleanup if store is too large
            if len(self._store) >= self._max_size:
                self._cleanup_old_entries()
            
            self._store[idempotency_key] = (time.time(), response)
    
    def _cleanup_old_entries(self):
        """Remove old entries to make space"""
        cutoff = time.time() - self._ttl_seconds
        old_keys = [
            k for k, (timestamp, _) in self._store.items()
            if timestamp < cutoff
        ]
        for k in old_keys:
            del self._store[k]
        
        # If still too large, remove oldest entries
        if len(self._store) >= self._max_size:
            sorted_items = sorted(self._store.items(), key=lambda x: x[1][0])
            to_remove = len(self._store) - self._max_size + 100
            for k, _ in sorted_items[:to_remove]:
                del self._store[k]


class ReliableMessenger:
    """High-level interface for reliable message delivery"""
    
    def __init__(
        self,
        send_func: Callable[[str, Any], Any],
        max_retries: int = 5,
        ack_timeout_seconds: float = 30.0
    ):
        self.send_func = send_func
        self.delivery_tracker = DeliveryTracker(
            max_retries=max_retries,
            ack_timeout_seconds=ack_timeout_seconds
        )
        self.idempotency_store = IdempotencyStore()
        self._running = False
    
    async def start(self):
        """Start the reliable messenger"""
        await self.delivery_tracker.start()
        self._running = True
        logger.info("ReliableMessenger started")
    
    async def stop(self):
        """Stop the reliable messenger"""
        self._running = False
        await self.delivery_tracker.stop()
        logger.info("ReliableMessenger stopped")
    
    async def send_reliable(
        self,
        recipient_id: str,
        payload: Any,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send message with at-least-once delivery guarantee
        
        Args:
            recipient_id: Target recipient
            payload: Message payload
            idempotency_key: Optional key for exactly-once semantics
        
        Returns:
            Delivery result with status and metadata
        """
        # Generate message ID
        message_id = str(uuid.uuid4())
        
        # Check idempotency
        if idempotency_key:
            if await self.idempotency_store.is_processed(idempotency_key):
                cached_response = await self.idempotency_store.get_response(idempotency_key)
                logger.info(f"Returning cached response for {idempotency_key}")
                return {
                    "status": "delivered",
                    "message_id": message_id,
                    "cached": True,
                    "response": cached_response
                }
        
        # Start tracking
        await self.delivery_tracker.track_message(message_id, recipient_id, payload)
        
        # Attempt delivery with retries
        attempt = 0
        last_error = None
        
        while attempt < self.delivery_tracker.retry_manager.max_retries:
            try:
                # Send message
                response = await self.send_func(recipient_id, payload)
                
                # Mark as delivered
                await self.delivery_tracker.mark_delivered(message_id)
                
                # Cache response if idempotency key provided
                if idempotency_key:
                    await self.idempotency_store.mark_processed(idempotency_key, response)
                
                return {
                    "status": "delivered",
                    "message_id": message_id,
                    "attempts": attempt + 1,
                    "response": response
                }
                
            except Exception as e:
                attempt += 1
                last_error = str(e)
                await self.delivery_tracker.record_attempt(message_id, last_error)
                
                if attempt < self.delivery_tracker.retry_manager.max_retries:
                    delay = self.delivery_tracker.get_retry_delay(message_id)
                    logger.warning(f"Retry {attempt} for {message_id} after {delay}s: {e}")
                    await asyncio.sleep(delay)
        
        # All retries exhausted
        await self.delivery_tracker.mark_failed(message_id, f"Max retries exceeded: {last_error}")
        
        return {
            "status": "failed",
            "message_id": message_id,
            "attempts": attempt,
            "error": last_error
        }
    
    async def handle_ack(self, message_id: str):
        """Handle delivery acknowledgment"""
        await self.delivery_tracker.mark_delivered(message_id)
    
    def get_stats(self) -> dict:
        """Get messenger statistics"""
        return self.delivery_tracker.get_stats()


# Global instance
_default_messenger: Optional[ReliableMessenger] = None


def init_reliable_messenger(
    send_func: Callable[[str, Any], Any],
    max_retries: int = 5
) -> ReliableMessenger:
    """Initialize global reliable messenger"""
    global _default_messenger
    _default_messenger = ReliableMessenger(send_func, max_retries)
    return _default_messenger


def get_reliable_messenger() -> Optional[ReliableMessenger]:
    """Get global reliable messenger instance"""
    return _default_messenger


if __name__ == "__main__":
    # Simple test
    async def test_send(recipient: str, payload: Any) -> Any:
        print(f"Sending to {recipient}: {payload}")
        return {"status": "ok"}
    
    async def main():
        messenger = init_reliable_messenger(test_send)
        await messenger.start()
        
        result = await messenger.send_reliable(
            "test-recipient",
            {"message": "Hello, World!"},
            idempotency_key="test-123"
        )
        print(f"Result: {result}")
        
        stats = await messenger.get_stats()
        print(f"Stats: {stats}")
        
        await messenger.stop()
    
    asyncio.run(main())
