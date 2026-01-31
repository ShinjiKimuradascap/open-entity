#!/usr/bin/env python3
"""
Bandwidth Adaptation Manager
動的帯域適応と輻輳制御システム

Features:
- Dynamic quality adjustment
- Message prioritization
- Congestion control
- Bandwidth usage metrics
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PriorityLevel(Enum):
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


class CongestionLevel(Enum):
    NONE = "none"
    LIGHT = "light"
    MODERATE = "moderate"
    SEVERE = "severe"


@dataclass
class BandwidthMetrics:
    bytes_sent: int = 0
    bytes_received: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    errors: int = 0
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AdaptiveMessage:
    message_id: str
    priority: PriorityLevel
    payload_size: int
    created_at: datetime
    max_latency_ms: int = 5000
    compressed: bool = False


class BandwidthAdaptationManager:
    """
    Dynamic bandwidth adaptation manager.
    
    Monitors network conditions and adapts message flow
    to optimize delivery under varying bandwidth constraints.
    """
    
    def __init__(
        self,
        target_bandwidth_bps: int = 1_000_000,  # 1 Mbps default
        max_queue_size: int = 1000,
        adaptation_interval: float = 5.0
    ):
        self.target_bandwidth_bps = target_bandwidth_bps
        self.max_queue_size = max_queue_size
        self.adaptation_interval = adaptation_interval
        
        # Message queues by priority
        self._queues: Dict[PriorityLevel, asyncio.Queue] = {
            priority: asyncio.Queue(maxsize=max_queue_size)
            for priority in PriorityLevel
        }
        
        # Metrics
        self._metrics = BandwidthMetrics()
        self._metrics_history: List[BandwidthMetrics] = []
        self._max_history = 100
        
        # Congestion detection
        self._current_congestion = CongestionLevel.NONE
        self._congestion_thresholds = {
            CongestionLevel.LIGHT: 0.6,
            CongestionLevel.MODERATE: 0.8,
            CongestionLevel.SEVERE: 0.95
        }
        
        # Adaptation state
        self._compression_enabled = False
        self._drop_low_priority = False
        self._current_bandwidth_limit = target_bandwidth_bps
        
        # Control
        self._lock = asyncio.Lock()
        self._running = False
        self._adaptation_task: Optional[asyncio.Task] = None
        self._send_callback: Optional[Callable] = None
        
    async def start(self, send_callback: Callable[[Any], asyncio.Future]):
        """Start bandwidth adaptation manager"""
        self._send_callback = send_callback
        self._running = True
        self._adaptation_task = asyncio.create_task(self._adaptation_loop())
        asyncio.create_task(self._process_queues())
        logger.info("BandwidthAdaptationManager started")
        
    async def stop(self):
        """Stop bandwidth adaptation manager"""
        self._running = False
        if self._adaptation_task:
            self._adaptation_task.cancel()
            try:
                await self._adaptation_task
            except asyncio.CancelledError:
                pass
        logger.info("BandwidthAdaptationManager stopped")
        
    async def send_message(
        self,
        message: Any,
        priority: PriorityLevel = PriorityLevel.NORMAL,
        payload_size: int = 0
    ) -> bool:
        """Queue message for sending with priority"""
        if priority == PriorityLevel.BACKGROUND and self._drop_low_priority:
            logger.debug("Dropping background priority message due to congestion")
            return False
            
        adaptive_msg = AdaptiveMessage(
            message_id=f"msg_{time.time_ns()}",
            priority=priority,
            payload_size=payload_size,
            created_at=datetime.now(timezone.utc)
        )
        
        try:
            self._queues[priority].put_nowait((adaptive_msg, message))
            return True
        except asyncio.QueueFull:
            logger.warning(f"Queue full for priority {priority}")
            return False
            
    async def _process_queues(self):
        """Process message queues by priority"""
        while self._running:
            try:
                # Process in priority order
                for priority in sorted(PriorityLevel, key=lambda p: p.value):
                    queue = self._queues[priority]
                    
                    # Calculate messages to process based on congestion
                    max_messages = self._get_max_messages_for_priority(priority)
                    
                    for _ in range(max_messages):
                        if queue.empty():
                            break
                            
                        try:
                            adaptive_msg, message = queue.get_nowait()
                            
                            # Apply compression if enabled
                            if self._compression_enabled and adaptive_msg.payload_size > 1024:
                                message = await self._compress_message(message)
                                adaptive_msg.compressed = True
                            
                            # Send via callback
                            if self._send_callback:
                                await self._send_callback(message)
                                await self._update_metrics(
                                    bytes_sent=adaptive_msg.payload_size
                                )
                                
                        except Exception as e:
                            logger.error(f"Error sending message: {e}")
                            await self._update_metrics(errors=1)
                
                # Small delay to prevent busy-waiting
                await asyncio.sleep(0.001)
                
            except Exception as e:
                logger.error(f"Error in process_queues: {e}")
                await asyncio.sleep(0.1)
                
    def _get_max_messages_for_priority(self, priority: PriorityLevel) -> int:
        """Get maximum messages to process based on congestion level"""
        base_limits = {
            PriorityLevel.CRITICAL: 100,
            PriorityLevel.HIGH: 50,
            PriorityLevel.NORMAL: 20,
            PriorityLevel.LOW: 10,
            PriorityLevel.BACKGROUND: 5
        }
        
        base = base_limits[priority]
        
        # Reduce limits during congestion
        if self._current_congestion == CongestionLevel.SEVERE:
            if priority in (PriorityLevel.LOW, PriorityLevel.BACKGROUND):
                return 0
            return base // 4
        elif self._current_congestion == CongestionLevel.MODERATE:
            if priority == PriorityLevel.BACKGROUND:
                return 0
            return base // 2
        elif self._current_congestion == CongestionLevel.LIGHT:
            return int(base * 0.8)
        
        return base
        
    async def _adaptation_loop(self):
        """Main adaptation loop - monitors and adjusts bandwidth usage"""
        while self._running:
            try:
                await asyncio.sleep(self.adaptation_interval)
                
                async with self._lock:
                    await self._analyze_and_adapt()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in adaptation loop: {e}")
                
    async def _analyze_and_adapt(self):
        """Analyze metrics and adapt bandwidth settings"""
        # Calculate current utilization
        utilization = self._calculate_utilization()
        
        # Update congestion level
        if utilization > self._congestion_thresholds[CongestionLevel.SEVERE]:
            new_congestion = CongestionLevel.SEVERE
        elif utilization > self._congestion_thresholds[CongestionLevel.MODERATE]:
            new_congestion = CongestionLevel.MODERATE
        elif utilization > self._congestion_thresholds[CongestionLevel.LIGHT]:
            new_congestion = CongestionLevel.LIGHT
        else:
            new_congestion = CongestionLevel.NONE
            
        if new_congestion != self._current_congestion:
            logger.info(f"Congestion level changed: {self._current_congestion.value} -> {new_congestion.value}")
            self._current_congestion = new_congestion
            await self._apply_congestion_adaptations()
            
        # Store metrics history
        self._metrics_history.append(self._metrics)
        if len(self._metrics_history) > self._max_history:
            self._metrics_history.pop(0)
            
        # Reset current metrics
        self._metrics = BandwidthMetrics()
        
    def _calculate_utilization(self) -> float:
        """Calculate current bandwidth utilization (0.0 - 1.0)"""
        if self.target_bandwidth_bps == 0:
            return 0.0
            
        # Calculate bytes sent in adaptation interval
        bytes_sent = self._metrics.bytes_sent
        bits_sent = bytes_sent * 8
        
        # Calculate utilization ratio
        max_bits = self.target_bandwidth_bps * self.adaptation_interval
        utilization = bits_sent / max_bits if max_bits > 0 else 0
        
        return min(1.0, utilization)
        
    async def _apply_congestion_adaptations(self):
        """Apply adaptations based on congestion level"""
        if self._current_congestion == CongestionLevel.SEVERE:
            self._compression_enabled = True
            self._drop_low_priority = True
            self._current_bandwidth_limit = self.target_bandwidth_bps * 0.3
        elif self._current_congestion == CongestionLevel.MODERATE:
            self._compression_enabled = True
            self._drop_low_priority = False
            self._current_bandwidth_limit = self.target_bandwidth_bps * 0.6
        elif self._current_congestion == CongestionLevel.LIGHT:
            self._compression_enabled = True
            self._drop_low_priority = False
            self._current_bandwidth_limit = self.target_bandwidth_bps * 0.8
        else:
            self._compression_enabled = False
            self._drop_low_priority = False
            self._current_bandwidth_limit = self.target_bandwidth_bps
            
        logger.info(f"Applied adaptations: compression={self._compression_enabled}, "
                   f"drop_low={self._drop_low_priority}, limit={self._current_bandwidth_limit}")
        
    async def _compress_message(self, message: Any) -> Any:
        """Compress message payload"""
        # Placeholder - actual compression would depend on message format
        return message
        
    async def _update_metrics(self, bytes_sent: int = 0, errors: int = 0):
        """Update bandwidth metrics"""
        self._metrics.bytes_sent += bytes_sent
        self._metrics.messages_sent += 1
        self._metrics.errors += errors
        
    def get_status(self) -> Dict[str, Any]:
        """Get current bandwidth adaptation status"""
        queue_sizes = {
            p.name: q.qsize() for p, q in self._queues.items()
        }
        
        return {
            "congestion_level": self._current_congestion.value,
            "compression_enabled": self._compression_enabled,
            "drop_low_priority": self._drop_low_priority,
            "bandwidth_limit_bps": self._current_bandwidth_limit,
            "target_bandwidth_bps": self.target_bandwidth_bps,
            "queue_sizes": queue_sizes,
            "metrics_history_count": len(self._metrics_history)
        }
        
    async def record_latency(self, latency_ms: float):
        """Record message latency for adaptation"""
        self._metrics.latency_ms = latency_ms


class MessagePrioritizer:
    """Helper class for message prioritization"""
    
    @staticmethod
    def get_priority_for_message_type(message_type: str) -> PriorityLevel:
        """Get default priority for message type"""
        priorities = {
            "heartbeat": PriorityLevel.LOW,
            "task_urgent": PriorityLevel.CRITICAL,
            "task_normal": PriorityLevel.NORMAL,
            "chat": PriorityLevel.NORMAL,
            "file_transfer": PriorityLevel.BACKGROUND,
            "discovery": PriorityLevel.HIGH,
            "gossip": PriorityLevel.LOW,
            "status_update": PriorityLevel.LOW
        }
        return priorities.get(message_type, PriorityLevel.NORMAL)


# Convenience functions
async def create_bandwidth_manager(
    target_bandwidth_bps: int = 1_000_000,
    max_queue_size: int = 1000
) -> BandwidthAdaptationManager:
    """Create bandwidth adaptation manager"""
    return BandwidthAdaptationManager(
        target_bandwidth_bps=target_bandwidth_bps,
        max_queue_size=max_queue_size
    )
