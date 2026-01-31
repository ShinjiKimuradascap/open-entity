#!/usr/bin/env python3
"""
NAT Type Detector
Detects NAT type using STUN protocol

Based on RFC 5780 - NAT Behavioral Requirements for Unicast UDP
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Tuple

from services.stun_client import StunClient, StunEndpoint, DEFAULT_STUN_SERVERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NATType(Enum):
    """NAT type classification"""
    UNKNOWN = auto()
    OPEN_INTERNET = auto()          # No NAT
    FULL_CONE = auto()              # Full Cone NAT
    RESTRICTED_CONE = auto()        # Restricted Cone NAT
    PORT_RESTRICTED_CONE = auto()   # Port Restricted Cone NAT
    SYMMETRIC = auto()              # Symmetric NAT
    BLOCKED = auto()                # UDP blocked


@dataclass
class NATDetectionResult:
    """NAT detection result"""
    nat_type: NATType
    public_endpoint: Optional[StunEndpoint]
    local_endpoint: Optional[StunEndpoint]
    details: dict
    
    def is_traversable(self) -> bool:
        """Check if P2P traversal is possible"""
        return self.nat_type in (
            NATType.OPEN_INTERNET,
            NATType.FULL_CONE,
            NATType.RESTRICTED_CONE,
            NATType.PORT_RESTRICTED_CONE
        )
    
    def needs_turn(self) -> bool:
        """Check if TURN relay is required"""
        return self.nat_type == NATType.SYMMETRIC
    
    def __str__(self) -> str:
        return f"NATType({self.nat_type.name}, public={self.public_endpoint})"


class NATDetector:
    """
    NAT type detector using STUN protocol
    
    Algorithm:
    1. Test I: Send binding request to primary STUN server
       - No response -> UDP blocked
       - Mapped address == local address -> Open Internet
    
    2. Test II: Send binding request with change IP+port request
       - Response received -> Full Cone NAT
       - No response -> Continue to Test I with secondary server
    
    3. Test III: Send binding request to secondary STUN server
       - Different mapped address -> Symmetric NAT
       - Same mapped address -> Continue to Test IV
    
    4. Test IV: Send binding request with change port request
       - Response received -> Restricted Cone NAT
       - No response -> Port Restricted Cone NAT
    
    Usage:
        detector = NATDetector()
        result = await detector.detect()
        print(f"NAT Type: {result.nat_type}")
        print(f"Needs TURN: {result.needs_turn()}")
    """
    
    def __init__(
        self,
        stun_servers: Optional[List[Tuple[str, int]]] = None,
        timeout: float = 5.0
    ):
        self.stun_servers = stun_servers or DEFAULT_STUN_SERVERS[:2]
        self.timeout = timeout
        self._client = StunClient(timeout=timeout)
    
    async def detect(self) -> NATDetectionResult:
        """
        Detect NAT type
        
        Returns:
            NATDetectionResult with detected type and endpoints
        """
        if len(self.stun_servers) < 1:
            return NATDetectionResult(
                nat_type=NATType.UNKNOWN,
                public_endpoint=None,
                local_endpoint=None,
                details={"error": "No STUN servers configured"}
            )
        
        primary_server = self.stun_servers[0]
        secondary_server = self.stun_servers[1] if len(self.stun_servers) > 1 else None
        
        details = {}
        
        # Test I: Basic binding request to primary server
        logger.debug("Test I: Basic binding request")
        response1 = await self._client.binding_request(
            primary_server[0], primary_server[1]
        )
        
        if not response1.success:
            # No response - UDP might be blocked
            logger.info("No response from primary STUN server")
            return NATDetectionResult(
                nat_type=NATType.BLOCKED,
                public_endpoint=None,
                local_endpoint=None,
                details={"error": "No response from STUN server", "test": "I"}
            )
        
        public_ep1 = response1.mapped_endpoint
        details["test1_mapped"] = str(public_ep1) if public_ep1 else None
        details["test1_source"] = str(response1.source_endpoint) if response1.source_endpoint else None
        
        if not public_ep1:
            return NATDetectionResult(
                nat_type=NATType.UNKNOWN,
                public_endpoint=None,
                local_endpoint=None,
                details={"error": "No mapped address in response", "test": "I"}
            )
        
        # Test II: Try to use CHANGE-REQUEST to get response from different IP/port
        logger.debug("Test II: Change IP+port request")
        response2 = await self._client.binding_request(
            primary_server[0], primary_server[1],
            change_ip=True, change_port=True
        )
        
        details["test2_success"] = response2.success
        
        if response2.success:
            # Got response from different address - Full Cone NAT
            logger.info("Full Cone NAT detected (response from different address)")
            return NATDetectionResult(
                nat_type=NATType.FULL_CONE,
                public_endpoint=public_ep1,
                local_endpoint=None,
                details=details
            )
        
        # Test III: Check if we have a secondary server
        if not secondary_server:
            logger.warning("Only one STUN server, cannot determine NAT type precisely")
            return NATDetectionResult(
                nat_type=NATType.UNKNOWN,
                public_endpoint=public_ep1,
                local_endpoint=None,
                details={"error": "Need secondary STUN server", "test": "III"}
            )
        
        # Send request to secondary server
        logger.debug("Test III: Request to secondary server")
        response3 = await self._client.binding_request(
            secondary_server[0], secondary_server[1]
        )
        
        if response3.success and response3.mapped_endpoint:
            public_ep2 = response3.mapped_endpoint
            details["test3_mapped"] = str(public_ep2)
            
            # Check if mapped addresses are different
            if public_ep1.ip != public_ep2.ip or public_ep1.port != public_ep2.port:
                logger.info("Symmetric NAT detected (different mapped addresses)")
                return NATDetectionResult(
                    nat_type=NATType.SYMMETRIC,
                    public_endpoint=public_ep1,
                    local_endpoint=None,
                    details=details
                )
        
        # Test IV: Try change port only
        logger.debug("Test IV: Change port request")
        response4 = await self._client.binding_request(
            primary_server[0], primary_server[1],
            change_ip=False, change_port=True
        )
        
        details["test4_success"] = response4.success
        
        if response4.success:
            logger.info("Restricted Cone NAT detected (response from different port)")
            return NATDetectionResult(
                nat_type=NATType.RESTRICTED_CONE,
                public_endpoint=public_ep1,
                local_endpoint=None,
                details=details
            )
        else:
            logger.info("Port Restricted Cone NAT detected (no response from different port)")
            return NATDetectionResult(
                nat_type=NATType.PORT_RESTRICTED_CONE,
                public_endpoint=public_ep1,
                local_endpoint=None,
                details=details
            )
    
    async def quick_check(self) -> Optional[StunEndpoint]:
        """
        Quick check - just get public endpoint without full NAT detection
        
        Returns:
            Public endpoint or None
        """
        return await self._client.get_public_endpoint(self.stun_servers)


async def test_nat_detector():
    """Test NAT detector"""
    print("=== NAT Detector Test ===")
    
    detector = NATDetector(timeout=5.0)
    
    # Quick check first
    print("\nQuick check - getting public endpoint...")
    public_ep = await detector.quick_check()
    if public_ep:
        print(f"Public endpoint: {public_ep}")
    else:
        print("Could not determine public endpoint")
        return
    
    # Full NAT detection
    print("\nRunning full NAT detection...")
    result = await detector.detect()
    
    print(f"\nNAT Type: {result.nat_type.name}")
    print(f"Public Endpoint: {result.public_endpoint}")
    print(f"Is Traversable: {result.is_traversable()}")
    print(f"Needs TURN: {result.needs_turn()}")
    print(f"Details: {result.details}")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_nat_detector())
