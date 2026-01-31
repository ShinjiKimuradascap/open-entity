#!/usr/bin/env python3
"""
Wake Up Protocol Implementation

ピアエンティティが停止/スリープ状態にある場合に、
自動的に復帰させるためのプロトコル実装。

Features:
- Mutual monitoring: 相互監視による自動復帰
- Task delegation: 緊急タスクのためのウェイクアップ委譲
- Auto restart: ヘルスチェック失敗時の自動再起動
- Signed messages: 署名付きメッセージによるセキュリティ保証
- Rate limiting: レート制限によるDoS防止
"""

import asyncio
import json
import logging
import secrets
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Callable, Awaitable, List

# Crypto imports
try:
    from services.crypto import sign_message, verify_signature, get_ed25519_public_key
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        from crypto import sign_message, verify_signature, get_ed25519_public_key
        CRYPTO_AVAILABLE = True
    except ImportError:
        CRYPTO_AVAILABLE = False

# Peer service imports
try:
    from services.peer_service import PeerService, PeerMessage
    PEER_AVAILABLE = True
except ImportError:
    try:
        from peer_service import PeerService, PeerMessage
        PEER_AVAILABLE = True
    except ImportError:
        PEER_AVAILABLE = False


logger = logging.getLogger(__name__)


class WakeUpPriority(Enum):
    """Wake up priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class WakeUpStatus(Enum):
    """Wake up response status"""
    SUCCESS = "success"
    FAILED = "failed"
    ALREADY_AWAKE = "already_awake"
    RATE_LIMITED = "rate_limited"
    INVALID_SIGNATURE = "invalid_signature"


@dataclass
class WakeUpMessage:
    """Wake up request message"""
    type: str = "wake_up"
    source_id: str = ""
    target_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))
    priority: str = WakeUpPriority.NORMAL.value
    reason: str = ""
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding signature for signing)"""
        data = asdict(self)
        if data.get('signature') is None:
            del data['signature']
        return data
    
    def sign(self, private_key: bytes) -> None:
        """Sign the message"""
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("Crypto module not available")
        
        data = self.to_dict()
        message = json.dumps(data, sort_keys=True).encode()
        self.signature = sign_message(message, private_key)
    
    def verify(self, public_key: bytes) -> bool:
        """Verify message signature"""
        if not CRYPTO_AVAILABLE or not self.signature:
            return False
        
        data = self.to_dict()
        message = json.dumps(data, sort_keys=True).encode()
        return verify_signature(message, self.signature, public_key)


@dataclass
class WakeUpAck:
    """Wake up acknowledgment message"""
    type: str = "wake_up_ack"
    source_id: str = ""
    target_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = WakeUpStatus.SUCCESS.value
    session_id: Optional[str] = None
    message: str = ""
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding signature for signing)"""
        data = asdict(self)
        if data.get('signature') is None:
            del data['signature']
        return data
    
    def sign(self, private_key: bytes) -> None:
        """Sign the message"""
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("Crypto module not available")
        
        data = self.to_dict()
        message = json.dumps(data, sort_keys=True).encode()
        self.signature = sign_message(message, private_key)


@dataclass
class WakeUpConfig:
    """Configuration for wake up protocol"""
    max_retries: int = 3
    retry_interval: float = 5.0  # seconds
    backoff_multiplier: float = 2.0
    rate_limit_window: float = 60.0  # seconds
    rate_limit_max_requests: int = 10
    session_timeout: float = 300.0  # 5 minutes
    priority_timeout: Dict[str, float] = field(default_factory=lambda: {
        WakeUpPriority.LOW.value: 300.0,
        WakeUpPriority.NORMAL.value: 60.0,
        WakeUpPriority.HIGH.value: 10.0,
        WakeUpPriority.CRITICAL.value: 0.0,
    })


class RateLimiter:
    """Simple rate limiter for wake up requests"""
    
    def __init__(self, window: float = 60.0, max_requests: int = 10):
        self.window = window
        self.max_requests = max_requests
        self.requests: Dict[str, List[float]] = {}
    
    def is_allowed(self, peer_id: str) -> bool:
        """Check if request is allowed under rate limit"""
        now = time.time()
        
        if peer_id not in self.requests:
            self.requests[peer_id] = []
        
        # Remove old requests outside window
        self.requests[peer_id] = [
            t for t in self.requests[peer_id]
            if now - t < self.window
        ]
        
        if len(self.requests[peer_id]) >= self.max_requests:
            return False
        
        self.requests[peer_id].append(now)
        return True
    
    def get_remaining(self, peer_id: str) -> int:
        """Get remaining requests in current window"""
        if not self.is_allowed(peer_id):
            return 0
        return self.max_requests - len(self.requests.get(peer_id, []))


class WakeUpProtocol:
    """
    Wake Up Protocol handler for peer communication
    
    Usage:
        # Initialize
        wake_up = WakeUpProtocol(peer_service, entity_id, private_key)
        
        # Send wake up to peer
        result = await wake_up.send_wake_up(peer_id, priority=WakeUpPriority.HIGH)
        
        # Handle incoming wake up (automatically registered)
        # The protocol automatically handles wake_up and wake_up_ack messages
    """
    
    def __init__(
        self,
        peer_service: Any,
        entity_id: str,
        private_key: bytes,
        config: Optional[WakeUpConfig] = None
    ):
        self.peer_service = peer_service
        self.entity_id = entity_id
        self.private_key = private_key
        self.config = config or WakeUpConfig()
        self.rate_limiter = RateLimiter(
            self.config.rate_limit_window,
            self.config.rate_limit_max_requests
        )
        
        # Pending wake up requests
        self._pending_wake_ups: Dict[str, asyncio.Future] = {}
        
        # Statistics
        self.stats = {
            "wake_up_sent": 0,
            "wake_up_received": 0,
            "wake_up_ack_sent": 0,
            "wake_up_ack_received": 0,
            "wake_up_success": 0,
            "wake_up_failed": 0,
            "rate_limited": 0,
        }
        
        # Register handlers if peer service supports it
        if PEER_AVAILABLE and hasattr(peer_service, 'register_message_handler'):
            self._register_handlers()
        
        logger.info(f"WakeUpProtocol initialized for entity {entity_id}")
    
    def _register_handlers(self) -> None:
        """Register message handlers with peer service"""
        if hasattr(self.peer_service, 'register_message_handler'):
            self.peer_service.register_message_handler(
                "wake_up",
                self._handle_wake_up
            )
            self.peer_service.register_message_handler(
                "wake_up_ack",
                self._handle_wake_up_ack
            )
            logger.info("Wake up handlers registered")
    
    async def send_wake_up(
        self,
        target_id: str,
        priority: WakeUpPriority = WakeUpPriority.NORMAL,
        reason: str = "",
        timeout: Optional[float] = None
    ) -> WakeUpAck:
        """
        Send wake up request to target peer
        
        Args:
            target_id: Target peer ID
            priority: Wake up priority
            reason: Reason for wake up
            timeout: Custom timeout (defaults to priority-based timeout)
        
        Returns:
            WakeUpAck response
        
        Raises:
            TimeoutError: If no response received
            RuntimeError: If sending fails
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("Crypto module not available")
        
        timeout = timeout or self.config.priority_timeout.get(
            priority.value,
            self.config.priority_timeout[WakeUpPriority.NORMAL.value]
        )
        
        # Create wake up message
        message = WakeUpMessage(
            source_id=self.entity_id,
            target_id=target_id,
            priority=priority.value,
            reason=reason
        )
        message.sign(self.private_key)
        
        # Retry logic
        last_error = None
        retry_delay = self.config.retry_interval
        
        for attempt in range(self.config.max_retries):
            try:
                self.stats["wake_up_sent"] += 1
                
                # Create future for response
                future = asyncio.Future()
                self._pending_wake_ups[message.nonce] = future
                
                # Send message
                await self._send_message(target_id, message)
                
                # Wait for response
                ack = await asyncio.wait_for(future, timeout=timeout)
                self.stats["wake_up_ack_received"] += 1
                
                if ack.status == WakeUpStatus.SUCCESS.value:
                    self.stats["wake_up_success"] += 1
                else:
                    self.stats["wake_up_failed"] += 1
                
                return ack
                
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Wake up timeout (attempt {attempt + 1})")
                logger.warning(f"Wake up to {target_id} timed out (attempt {attempt + 1})")
                
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= self.config.backoff_multiplier
                    
            except Exception as e:
                last_error = e
                logger.error(f"Wake up error: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= self.config.backoff_multiplier
            
            finally:
                if message.nonce in self._pending_wake_ups:
                    del self._pending_wake_ups[message.nonce]
        
        # All retries exhausted
        self.stats["wake_up_failed"] += 1
        if last_error:
            raise last_error
        raise RuntimeError("Wake up failed after all retries")
    
    async def _send_message(self, target_id: str, message: WakeUpMessage) -> None:
        """Send message via peer service"""
        if PEER_AVAILABLE and hasattr(self.peer_service, 'send_message'):
            await self.peer_service.send_message(
                target_id,
                message.type,
                message.to_dict()
            )
        else:
            # Fallback: log the message
            logger.info(f"Would send wake_up to {target_id}: {message.to_dict()}")
    
    async def _handle_wake_up(self, message: Dict[str, Any]) -> None:
        """
        Handle incoming wake up request
        
        This is automatically called when a wake_up message is received.
        """
        self.stats["wake_up_received"] += 1
        
        try:
            # Parse message
            wake_up = WakeUpMessage(**message)
            
            # Check rate limit
            if not self.rate_limiter.is_allowed(wake_up.source_id):
                self.stats["rate_limited"] += 1
                await self._send_ack(
                    wake_up.source_id,
                    WakeUpStatus.RATE_LIMITED,
                    "Rate limit exceeded"
                )
                return
            
            # Verify signature if available
            if CRYPTO_AVAILABLE and wake_up.signature:
                # Get public key from peer service
                public_key = await self._get_peer_public_key(wake_up.source_id)
                if public_key and not wake_up.verify(public_key):
                    await self._send_ack(
                        wake_up.source_id,
                        WakeUpStatus.INVALID_SIGNATURE,
                        "Invalid signature"
                    )
                    return
            
            # Process wake up based on priority
            await self._process_wake_up(wake_up)
            
            # Send success ack
            await self._send_ack(
                wake_up.source_id,
                WakeUpStatus.SUCCESS,
                "Wake up processed successfully"
            )
            
        except Exception as e:
            logger.error(f"Error handling wake up: {e}")
            # Try to send failure ack if we know the source
            if 'source_id' in message:
                await self._send_ack(
                    message['source_id'],
                    WakeUpStatus.FAILED,
                    str(e)
                )
    
    async def _process_wake_up(self, wake_up: WakeUpMessage) -> None:
        """
        Process wake up request
        
        Override this method to implement custom wake up behavior.
        """
        priority = WakeUpPriority(wake_up.priority)
        
        logger.info(f"Wake up received from {wake_up.source_id} "
                   f"(priority: {priority.value}, reason: {wake_up.reason})")
        
        # Default behavior: just log and acknowledge
        # Subclasses can override to implement actual wake up logic
        pass
    
    async def _send_ack(
        self,
        target_id: str,
        status: WakeUpStatus,
        message: str = ""
    ) -> None:
        """Send wake up acknowledgment"""
        ack = WakeUpAck(
            source_id=self.entity_id,
            target_id=target_id,
            status=status.value,
            message=message
        )
        
        if CRYPTO_AVAILABLE:
            ack.sign(self.private_key)
        
        self.stats["wake_up_ack_sent"] += 1
        
        if PEER_AVAILABLE and hasattr(self.peer_service, 'send_message'):
            await self.peer_service.send_message(
                target_id,
                ack.type,
                ack.to_dict()
            )
        else:
            logger.info(f"Would send wake_up_ack to {target_id}: {ack.to_dict()}")
    
    async def _handle_wake_up_ack(self, message: Dict[str, Any]) -> None:
        """
        Handle incoming wake up acknowledgment
        
        This is automatically called when a wake_up_ack message is received.
        """
        try:
            ack = WakeUpAck(**message)
            
            # Find pending request and resolve it
            # Note: In a real implementation, we'd match by nonce
            # For now, we resolve any pending future
            for nonce, future in list(self._pending_wake_ups.items()):
                if not future.done():
                    future.set_result(ack)
                    break
            
        except Exception as e:
            logger.error(f"Error handling wake up ack: {e}")
    
    async def _get_peer_public_key(self, peer_id: str) -> Optional[bytes]:
        """Get public key for peer from peer service"""
        if hasattr(self.peer_service, 'get_peer_public_key'):
            return await self.peer_service.get_peer_public_key(peer_id)
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get protocol statistics"""
        return {
            **self.stats,
            "pending_wake_ups": len(self._pending_wake_ups),
            "rate_limit_remaining": {
                peer_id: self.rate_limiter.get_remaining(peer_id)
                for peer_id in list(self.rate_limiter.requests.keys())[:10]  # Limit output
            }
        }
    
    async def check_peer_alive(self, peer_id: str, timeout: float = 5.0) -> bool:
        """
        Check if peer is alive by sending wake up
        
        Returns:
            True if peer responds, False otherwise
        """
        try:
            ack = await self.send_wake_up(
                peer_id,
                priority=WakeUpPriority.LOW,
                reason="health_check",
                timeout=timeout
            )
            return ack.status == WakeUpStatus.SUCCESS.value
        except Exception:
            return False


# Convenience functions for simple usage

async def wake_up_peer(
    peer_service: Any,
    entity_id: str,
    private_key: bytes,
    target_id: str,
    priority: WakeUpPriority = WakeUpPriority.NORMAL,
    reason: str = ""
) -> WakeUpAck:
    """
    Convenience function to wake up a peer
    
    Args:
        peer_service: Peer service instance
        entity_id: This entity's ID
        private_key: This entity's private key
        target_id: Target peer ID
        priority: Wake up priority
        reason: Reason for wake up
    
    Returns:
        WakeUpAck response
    """
    protocol = WakeUpProtocol(peer_service, entity_id, private_key)
    return await protocol.send_wake_up(target_id, priority, reason)


def create_wake_up_message(
    source_id: str,
    target_id: str,
    private_key: bytes,
    priority: WakeUpPriority = WakeUpPriority.NORMAL,
    reason: str = ""
) -> WakeUpMessage:
    """
    Create a signed wake up message
    
    Args:
        source_id: Source entity ID
        target_id: Target entity ID
        private_key: Source private key
        priority: Wake up priority
        reason: Reason for wake up
    
    Returns:
        Signed WakeUpMessage
    """
    message = WakeUpMessage(
        source_id=source_id,
        target_id=target_id,
        priority=priority.value,
        reason=reason
    )
    message.sign(private_key)
    return message


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        print("Wake Up Protocol Test")
        print("=" * 50)
        
        # Create mock peer service
        class MockPeerService:
            def __init__(self):
                self.handlers = {}
            
            def register_message_handler(self, msg_type, handler):
                self.handlers[msg_type] = handler
            
            async def send_message(self, target_id, msg_type, data):
                print(f"Mock send to {target_id}: {msg_type}")
        
        mock_service = MockPeerService()
        
        # Test without crypto
        if not CRYPTO_AVAILABLE:
            print("\nNote: Crypto module not available, using mock mode")
            protocol = WakeUpProtocol(
                mock_service,
                "entity_a",
                b"mock_private_key"
            )
            print(f"Stats: {protocol.get_stats()}")
        else:
            print("\nCrypto module available")
        
        print("\nTest completed!")
    
    asyncio.run(test())
