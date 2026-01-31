#!/usr/bin/env python3
"""
Sequence Number Management - Phase 3 Implementation
Provides message ordering guarantees and gap detection
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Callable, Any, Tuple
from collections import defaultdict
import heapq

logger = logging.getLogger(__name__)


@dataclass
class SequenceState:
    """Manages sequence numbers for a peer connection"""
    peer_id: str
    next_seq: int = 1  # Next sequence number to send
    last_acked: int = 0  # Last confirmed sequence number received
    expected_seq: int = 1  # Next expected sequence number from peer
    reorder_buffer: Dict[int, Any] = field(default_factory=dict)
    max_buffer_size: int = 100
    
    def get_next_seq(self) -> int:
        """Get next sequence number for sending"""
        seq = self.next_seq
        self.next_seq += 1
        return seq
    
    def is_expected(self, seq: int) -> bool:
        """Check if sequence number is the expected one"""
        return seq == self.expected_seq
    
    def advance_expected(self):
        """Advance expected sequence number"""
        self.expected_seq += 1


@dataclass
class GapInfo:
    """Information about a sequence gap"""
    start_seq: int
    end_seq: int
    detected_at: datetime = field(default_factory=lambda: datetime.now())
    nack_sent: bool = False


class SequenceManager:
    """Manages sequence numbers across multiple peer connections"""
    
    def __init__(
        self,
        max_reorder_buffer: int = 100,
        nack_timeout_seconds: float = 5.0,
        gap_cleanup_interval: float = 60.0
    ):
        self._states: Dict[str, SequenceState] = {}
        self._max_reorder_buffer = max_reorder_buffer
        self._nack_timeout_seconds = nack_timeout_seconds
        self._gap_cleanup_interval = gap_cleanup_interval
        self._gaps: Dict[str, List[GapInfo]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._gap_handlers: List[Callable[[str, int, int], Any]] = []
    
    async def start(self):
        """Start background tasks"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("SequenceManager started")
    
    async def stop(self):
        """Stop background tasks"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("SequenceManager stopped")
    
    async def get_or_create_state(self, peer_id: str) -> SequenceState:
        """Get or create sequence state for peer"""
        async with self._lock:
            if peer_id not in self._states:
                self._states[peer_id] = SequenceState(
                    peer_id=peer_id,
                    max_buffer_size=self._max_reorder_buffer
                )
            return self._states[peer_id]
    
    async def allocate_seq(self, peer_id: str) -> int:
        """Allocate next sequence number for sending to peer"""
        state = await self.get_or_create_state(peer_id)
        return state.get_next_seq()
    
    async def process_incoming_seq(
        self,
        peer_id: str,
        seq: int,
        payload: Any
    ) -> Tuple[bool, Optional[List[Any]]]:
        """
        Process incoming sequence number
        
        Returns:
            (is_in_order, deliverable_messages)
        """
        async with self._lock:
            state = await self.get_or_create_state(peer_id)
            
            # Check if already processed
            if seq < state.expected_seq:
                logger.debug(f"Duplicate message {seq} from {peer_id}")
                return False, None
            
            # Check if this is the expected sequence
            if state.is_expected(seq):
                # Deliver immediately and check buffer
                messages = [payload]
                state.advance_expected()
                
                # Check reorder buffer for consecutive messages
                while state.expected_seq in state.reorder_buffer:
                    messages.append(state.reorder_buffer.pop(state.expected_seq))
                    state.advance_expected()
                
                return True, messages
            
            # Out of order - buffer it
            if len(state.reorder_buffer) >= state.max_buffer_size:
                # Buffer full - drop oldest
                oldest = min(state.reorder_buffer.keys())
                del state.reorder_buffer[oldest]
                logger.warning(f"Reorder buffer full, dropped seq {oldest}")
            
            state.reorder_buffer[seq] = payload
            
            # Detect gap
            if seq > state.expected_seq:
                await self._detect_gap(peer_id, state.expected_seq, seq - 1)
            
            return False, None
    
    async def _detect_gap(self, peer_id: str, start_seq: int, end_seq: int):
        """Detect and track sequence gap"""
        gap = GapInfo(start_seq=start_seq, end_seq=end_seq)
        self._gaps[peer_id].append(gap)
        
        logger.warning(f"Gap detected for {peer_id}: {start_seq}-{end_seq}")
        
        # Trigger gap handlers
        for handler in self._gap_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(peer_id, start_seq, end_seq)
                else:
                    handler(peer_id, start_seq, end_seq)
            except Exception as e:
                logger.error(f"Gap handler error: {e}")
    
    def register_gap_handler(self, handler: Callable[[str, int, int], Any]):
        """Register handler for gap detection events"""
        self._gap_handlers.append(handler)
    
    async def handle_nack(self, peer_id: str, start_seq: int, end_seq: int) -> List[int]:
        """
        Handle NACK from peer - return sequence numbers to retransmit
        
        Returns:
            List of sequence numbers that need retransmission
        """
        async with self._lock:
            state = await self.get_or_create_state(peer_id)
            
            # Find missing sequence numbers in our send window
            to_retransmit = []
            for seq in range(start_seq, end_seq + 1):
                if seq < state.next_seq:
                    # We should have sent this
                    to_retransmit.append(seq)
            
            logger.info(f"NACK from {peer_id} for {start_seq}-{end_seq}, retransmitting {len(to_retransmit)}")
            return to_retransmit
    
    async def create_nack_message(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """Create NACK message for detected gaps"""
        async with self._lock:
            if peer_id not in self._gaps or not self._gaps[peer_id]:
                return None
            
            # Get oldest unsent gap
            for gap in self._gaps[peer_id]:
                if not gap.nack_sent:
                    gap.nack_sent = True
                    return {
                        "type": "nack",
                        "start_seq": gap.start_seq,
                        "end_seq": gap.end_seq,
                        "timestamp": datetime.now().isoformat()
                    }
            
            return None
    
    async def resolve_gap(self, peer_id: str, start_seq: int, end_seq: int):
        """Mark gap as resolved"""
        async with self._lock:
            if peer_id in self._gaps:
                self._gaps[peer_id] = [
                    gap for gap in self._gaps[peer_id]
                    if not (gap.start_seq == start_seq and gap.end_seq == end_seq)
                ]
    
    async def get_stats(self, peer_id: Optional[str] = None) -> Dict[str, Any]:
        """Get sequence statistics"""
        async with self._lock:
            if peer_id:
                if peer_id not in self._states:
                    return {}
                state = self._states[peer_id]
                return {
                    "peer_id": peer_id,
                    "next_seq": state.next_seq,
                    "expected_seq": state.expected_seq,
                    "last_acked": state.last_acked,
                    "reorder_buffer_size": len(state.reorder_buffer),
                    "gaps": len(self._gaps.get(peer_id, []))
                }
            else:
                return {
                    "peers": len(self._states),
                    "total_gaps": sum(len(gaps) for gaps in self._gaps.values()),
                    "peer_stats": [
                        {
                            "peer_id": pid,
                            "next_seq": state.next_seq,
                            "expected_seq": state.expected_seq,
                            "buffer_size": len(state.reorder_buffer)
                        }
                        for pid, state in self._states.items()
                    ]
                }
    
    async def _cleanup_loop(self):
        """Background cleanup task"""
        while True:
            try:
                await asyncio.sleep(self._gap_cleanup_interval)
                await self._cleanup_old_gaps()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _cleanup_old_gaps(self):
        """Remove old resolved gaps"""
        cutoff = datetime.now() - timedelta(seconds=self._nack_timeout_seconds * 10)
        
        async with self._lock:
            for peer_id in list(self._gaps.keys()):
                self._gaps[peer_id] = [
                    gap for gap in self._gaps[peer_id]
                    if not (gap.nack_sent and gap.detected_at < cutoff)
                ]
                
                if not self._gaps[peer_id]:
                    del self._gaps[peer_id]


class OrderedMessageProcessor:
    """High-level interface for ordered message processing"""
    
    def __init__(
        self,
        message_handler: Callable[[str, Any], Any],
        max_reorder_buffer: int = 100
    ):
        self.sequence_manager = SequenceManager(max_reorder_buffer=max_reorder_buffer)
        self.message_handler = message_handler
        self._running = False
    
    async def start(self):
        """Start the ordered processor"""
        await self.sequence_manager.start()
        self._running = True
        logger.info("OrderedMessageProcessor started")
    
    async def stop(self):
        """Stop the ordered processor"""
        self._running = False
        await self.sequence_manager.stop()
        logger.info("OrderedMessageProcessor stopped")
    
    async def send_ordered(
        self,
        peer_id: str,
        payload: Any,
        send_func: Callable[[Dict], Any]
    ) -> Dict[str, Any]:
        """Send message with sequence number for ordering"""
        seq = await self.sequence_manager.allocate_seq(peer_id)
        
        message = {
            "seq": seq,
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            result = await send_func(message)
            return {
                "status": "sent",
                "seq": seq,
                "result": result
            }
        except Exception as e:
            return {
                "status": "error",
                "seq": seq,
                "error": str(e)
            }
    
    async def receive_ordered(self, peer_id: str, seq: int, payload: Any) -> Dict[str, Any]:
        """Receive and process ordered message"""
        is_in_order, messages = await self.sequence_manager.process_incoming_seq(
            peer_id, seq, payload
        )
        
        if messages:
            # Process all deliverable messages in order
            results = []
            for msg in messages:
                try:
                    if asyncio.iscoroutinefunction(self.message_handler):
                        result = await self.message_handler(peer_id, msg)
                    else:
                        result = self.message_handler(peer_id, msg)
                    results.append({"status": "processed", "result": result})
                except Exception as e:
                    logger.error(f"Message handler error: {e}")
                    results.append({"status": "error", "error": str(e)})
            
            return {
                "delivered": True,
                "count": len(messages),
                "results": results
            }
        
        return {
            "delivered": False,
            "buffered": True,
            "reason": "out_of_order"
        }
    
    async def handle_nack(self, peer_id: str, start_seq: int, end_seq: int) -> List[int]:
        """Handle NACK from peer"""
        return await self.sequence_manager.handle_nack(peer_id, start_seq, end_seq)
    
    async def create_nack(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """Create NACK for peer if gaps exist"""
        return await self.sequence_manager.create_nack_message(peer_id)
    
    async def get_stats(self, peer_id: Optional[str] = None) -> Dict[str, Any]:
        """Get processing statistics"""
        return await self.sequence_manager.get_stats(peer_id)


# Global instance
_default_sequence_manager: Optional[SequenceManager] = None


def init_sequence_manager(max_reorder_buffer: int = 100) -> SequenceManager:
    """Initialize global sequence manager"""
    global _default_sequence_manager
    _default_sequence_manager = SequenceManager(max_reorder_buffer=max_reorder_buffer)
    return _default_sequence_manager


def get_sequence_manager() -> Optional[SequenceManager]:
    """Get global sequence manager instance"""
    return _default_sequence_manager


if __name__ == "__main__":
    # Simple test
    async def test_handler(peer_id: str, payload: Any):
        print(f"Processing from {peer_id}: {payload}")
        return {"processed": True}
    
    async def main():
        processor = OrderedMessageProcessor(test_handler)
        await processor.start()
        
        # Simulate receiving messages out of order
        print("Receiving message seq=2...")
        result = await processor.receive_ordered("peer1", 2, "message_2")
        print(f"Result: {result}")
        
        print("Receiving message seq=1...")
        result = await processor.receive_ordered("peer1", 1, "message_1")
        print(f"Result: {result}")
        
        stats = await processor.get_stats()
        print(f"Stats: {stats}")
        
        await processor.stop()
    
    asyncio.run(main())
