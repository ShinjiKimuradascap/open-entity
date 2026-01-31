#!/usr/bin/env python3
"""
NAT Traversal Module
Main module for NAT traversal operations

Integrates:
- STUN client for public endpoint discovery
- NAT type detection
- UDP hole punching (future)
- TURN client (future)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable

from services.stun_client import StunClient, StunEndpoint, DEFAULT_STUN_SERVERS
from services.nat_detector import NATDetector, NATType, NATDetectionResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TraversalConfig:
    """NAT traversal configuration"""
    stun_servers: List[tuple] = field(default_factory=lambda: DEFAULT_STUN_SERVERS)
    turn_servers: List[dict] = field(default_factory=list)
    timeout: float = 5.0
    retry_count: int = 3
    enable_hole_punching: bool = True
    enable_turn: bool = False


class NATTraversalManager:
    """
    NAT Traversal Manager
    
    Manages NAT traversal operations including:
    - Public endpoint discovery
    - NAT type detection
    - Connection strategy selection
    
    Usage:
        config = TraversalConfig()
        manager = NATTraversalManager(config)
        
        # Detect NAT type
        result = await manager.detect_nat_type()
        
        # Get public endpoint
        endpoint = await manager.get_public_endpoint()
        
        # Check if P2P is possible
        if manager.can_do_p2p():
            # Attempt P2P connection
            pass
        else:
            # Use relay
            pass
    """
    
    def __init__(self, config: Optional[TraversalConfig] = None):
        self.config = config or TraversalConfig()
        
        self._stun_client = StunClient(
            timeout=self.config.timeout,
            retry_count=self.config.retry_count
        )
        self._nat_detector = NATDetector(
            stun_servers=self.config.stun_servers,
            timeout=self.config.timeout
        )
        
        # Cached results
        self._nat_result: Optional[NATDetectionResult] = None
        self._detected_at: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 minutes
        
        # Callbacks
        self._on_nat_detected: List[Callable[[NATDetectionResult], None]] = []
    
    async def detect_nat_type(self, force: bool = False) -> NATDetectionResult:
        """
        Detect NAT type
        
        Args:
            force: Force re-detection even if cached
            
        Returns:
            NATDetectionResult
        """
        # Check cache
        if not force and self._nat_result and self._detected_at:
            age = (datetime.now(timezone.utc) - self._detected_at).total_seconds()
            if age < self._cache_ttl_seconds:
                logger.debug(f"Using cached NAT result (age={age:.0f}s)")
                return self._nat_result
        
        # Perform detection
        logger.info("Detecting NAT type...")
        self._nat_result = await self._nat_detector.detect()
        self._detected_at = datetime.now(timezone.utc)
        
        # Notify callbacks
        for callback in self._on_nat_detected:
            try:
                callback(self._nat_result)
            except Exception as e:
                logger.error(f"NAT detection callback error: {e}")
        
        logger.info(f"NAT type detected: {self._nat_result.nat_type.name}")
        return self._nat_result
    
    async def get_public_endpoint(self) -> Optional[StunEndpoint]:
        """
        Get public endpoint (external IP:port)
        
        Returns:
            Public endpoint or None if undiscoverable
        """
        # Try quick check first
        endpoint = await self._nat_detector.quick_check()
        if endpoint:
            return endpoint
        
        # Fall back to detection
        result = await self.detect_nat_type()
        return result.public_endpoint
    
    def get_nat_type(self) -> Optional[NATType]:
        """Get cached NAT type (None if not detected)"""
        if self._nat_result:
            return self._nat_result.nat_type
        return None
    
    def can_do_p2p(self) -> bool:
        """
        Check if P2P connection is possible
        
        Returns:
            True if P2P is possible
        """
        if not self._nat_result:
            return False
        return self._nat_result.is_traversable()
    
    def needs_turn(self) -> bool:
        """
        Check if TURN relay is required
        
        Returns:
            True if TURN is needed
        """
        if not self._nat_result:
            return True  # Assume worst case
        return self._nat_result.needs_turn()
    
    def on_nat_detected(self, callback: Callable[[NATDetectionResult], None]) -> None:
        """Register callback for NAT detection events"""
        self._on_nat_detected.append(callback)
    
    def get_connection_strategy(self) -> Dict[str, Any]:
        """
        Get recommended connection strategy
        
        Returns:
            Strategy dictionary
        """
        nat_type = self.get_nat_type()
        
        if nat_type == NATType.UNKNOWN:
            return {
                "primary": "unknown",
                "fallback": ["stun_discovery"],
                "p2p_possible": False
            }
        
        if nat_type == NATType.BLOCKED:
            return {
                "primary": "relay",
                "fallback": [],
                "p2p_possible": False,
                "reason": "UDP blocked"
            }
        
        if nat_type == NATType.SYMMETRIC:
            return {
                "primary": "relay",
                "fallback": ["reverse_connection"],
                "p2p_possible": False,
                "reason": "Symmetric NAT"
            }
        
        if nat_type == NATType.FULL_CONE:
            return {
                "primary": "direct_p2p",
                "fallback": ["hole_punching", "relay"],
                "p2p_possible": True,
                "preferred": "direct"
            }
        
        if nat_type in (NATType.RESTRICTED_CONE, NATType.PORT_RESTRICTED_CONE):
            return {
                "primary": "hole_punching",
                "fallback": ["relay"],
                "p2p_possible": True,
                "preferred": "udp_hole_punching"
            }
        
        return {
            "primary": "unknown",
            "fallback": ["relay"],
            "p2p_possible": False
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return {
            "nat_type": self._nat_result.nat_type.name if self._nat_result else None,
            "public_endpoint": str(self._nat_result.public_endpoint) if self._nat_result and self._nat_result.public_endpoint else None,
            "detected_at": self._detected_at.isoformat() if self._detected_at else None,
            "can_p2p": self.can_do_p2p(),
            "needs_turn": self.needs_turn()
        }
    
    async def close(self):
        """Clean up resources"""
        logger.info("NAT Traversal Manager closed")


# Global instance
_default_manager: Optional[NATTraversalManager] = None


def get_nat_traversal_manager(config: Optional[TraversalConfig] = None) -> NATTraversalManager:
    """Get default NAT traversal manager instance"""
    global _default_manager
    if _default_manager is None:
        _default_manager = NATTraversalManager(config)
    return _default_manager


async def test_nat_traversal():
    """Test NAT traversal module"""
    print("=== NAT Traversal Test ===")
    
    config = TraversalConfig(timeout=5.0)
    manager = NATTraversalManager(config)
    
    # Get public endpoint
    print("\nGetting public endpoint...")
    public_ep = await manager.get_public_endpoint()
    if public_ep:
        print(f"Public endpoint: {public_ep}")
    else:
        print("Could not determine public endpoint")
    
    # Detect NAT type
    print("\nDetecting NAT type...")
    result = await manager.detect_nat_type()
    
    print(f"\nNAT Type: {result.nat_type.name}")
    print(f"Is Traversable: {result.is_traversable()}")
    print(f"Needs TURN: {result.needs_turn()}")
    
    # Get strategy
    strategy = manager.get_connection_strategy()
    print(f"\nConnection Strategy:")
    print(f"  Primary: {strategy['primary']}")
    print(f"  Fallback: {strategy.get('fallback', [])}")
    print(f"  P2P Possible: {strategy.get('p2p_possible', False)}")
    
    # Get stats
    print(f"\nStats: {manager.get_stats()}")
    
    await manager.close()
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_nat_traversal())
