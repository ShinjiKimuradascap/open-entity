"""
Peer Service Package

Refactored peer service modules for better maintainability.
"""

# Models
from .models import (
    MessageQueueItem,
    PeerStats,
    SessionInfo,
    ChunkInfo,
    RateLimitInfo,
    SendResult
)

# Queue
from .queue import MessageQueue

# Heartbeat
from .heartbeat import HeartbeatManager

# Main service (for backward compatibility)
# Note: Import from .service after migration
# from .service import PeerService

__all__ = [
    "MessageQueueItem",
    "PeerStats",
    "SessionInfo",
    "ChunkInfo",
    "RateLimitInfo",
    "SendResult",
    "MessageQueue",
    "HeartbeatManager",
]
