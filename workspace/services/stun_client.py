#!/usr/bin/env python3
"""
STUN Client Implementation
RFC 5389 compliant STUN client for NAT traversal

Features:
- Binding request/response
- Public endpoint discovery
- Multiple STUN server support
- Asyncio support
"""

import asyncio
import hashlib
import logging
import random
import struct
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional, List, Tuple, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# STUN Constants
STUN_MAGIC_COOKIE = 0x2112A442
STUN_HEADER_SIZE = 20
STUN_TRANSACTION_ID_SIZE = 12

# Message Types
class StunMessageType(IntEnum):
    BINDING_REQUEST = 0x0001
    BINDING_RESPONSE = 0x0101
    BINDING_ERROR_RESPONSE = 0x0111

# Attribute Types
class StunAttributeType(IntEnum):
    MAPPED_ADDRESS = 0x0001
    RESPONSE_ADDRESS = 0x0002
    CHANGE_REQUEST = 0x0003
    SOURCE_ADDRESS = 0x0004
    CHANGED_ADDRESS = 0x0005
    USERNAME = 0x0006
    PASSWORD = 0x0007
    MESSAGE_INTEGRITY = 0x0008
    ERROR_CODE = 0x0009
    UNKNOWN_ATTRIBUTES = 0x000A
    REFLECTED_FROM = 0x000B
    XOR_MAPPED_ADDRESS = 0x0020
    PRIORITY = 0x0024
    USE_CANDIDATE = 0x0025
    FINGERPRINT = 0x8028
    ICE_CONTROLLED = 0x8029
    ICE_CONTROLLING = 0x802A

# Address families
AF_IPV4 = 0x01
AF_IPV6 = 0x02


@dataclass
class StunEndpoint:
    """STUN endpoint (IP:port)"""
    ip: str
    port: int
    
    def __str__(self) -> str:
        return f"{self.ip}:{self.port}"
    
    @classmethod
    def from_tuple(cls, addr: Tuple[str, int]) -> 'StunEndpoint':
        return cls(ip=addr[0], port=addr[1])


@dataclass
class StunResponse:
    """STUN binding response"""
    success: bool
    mapped_endpoint: Optional[StunEndpoint]
    source_endpoint: Optional[StunEndpoint]
    changed_endpoint: Optional[StunEndpoint]
    error_code: Optional[int]
    error_reason: Optional[str]
    transaction_id: bytes
    raw_response: bytes


class StunClient:
    """
    STUN Client for NAT traversal
    
    Usage:
        client = StunClient()
        response = await client.binding_request("stun.l.google.com", 19302)
        if response.success:
            print(f"Public endpoint: {response.mapped_endpoint}")
    """
    
    DEFAULT_TIMEOUT = 3.0
    DEFAULT_RETRY = 2
    
    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        retry_count: int = DEFAULT_RETRY,
        local_port: int = 0
    ):
        self.timeout = timeout
        self.retry_count = retry_count
        self.local_port = local_port
        self._socket: Optional[socket.socket] = None
        self._lock = asyncio.Lock()
    
    def _generate_transaction_id(self) -> bytes:
        """Generate 12-byte random transaction ID"""
        return bytes([random.randint(0, 255) for _ in range(STUN_TRANSACTION_ID_SIZE)])
    
    def _build_binding_request(self, transaction_id: Optional[bytes] = None) -> bytes:
        """Build STUN binding request message"""
        if transaction_id is None:
            transaction_id = self._generate_transaction_id()
        
        # Message Type: Binding Request
        msg_type = struct.pack('>H', StunMessageType.BINDING_REQUEST)
        
        # Message Length: 0 (no attributes)
        msg_len = struct.pack('>H', 0)
        
        # Magic Cookie
        magic = struct.pack('>I', STUN_MAGIC_COOKIE)
        
        # Transaction ID
        # Header: type(2) + len(2) + cookie(4) + tid(12) = 20 bytes
        header = msg_type + msg_len + magic + transaction_id
        
        return header
    
    def _parse_address_attribute(
        self,
        data: bytes,
        offset: int,
        xor_cookie: int = 0
    ) -> Optional[StunEndpoint]:
        """Parse MAPPED-ADDRESS or XOR-MAPPED-ADDRESS attribute"""
        try:
            # Skip first byte (reserved)
            family = data[offset + 1]
            port = struct.unpack('>H', data[offset + 2:offset + 4])[0]
            
            if xor_cookie:
                # XOR with magic cookie
                port ^= (STUN_MAGIC_COOKIE >> 16) & 0xFFFF
            
            if family == AF_IPV4:
                ip_bytes = data[offset + 4:offset + 8]
                if xor_cookie:
                    # XOR with magic cookie
                    ip_int = struct.unpack('>I', ip_bytes)[0] ^ STUN_MAGIC_COOKIE
                    ip_bytes = struct.pack('>I', ip_int)
                ip = socket.inet_ntoa(ip_bytes)
            elif family == AF_IPV6:
                ip_bytes = data[offset + 4:offset + 20]
                if xor_cookie:
                    # XOR with magic cookie and transaction ID
                    xor_bytes = struct.pack('>I', STUN_MAGIC_COOKIE) + data[8:20]
                    ip_bytes = bytes([ip_bytes[i] ^ xor_bytes[i] for i in range(16)])
                ip = socket.inet_ntop(socket.AF_INET6, ip_bytes)
            else:
                return None
            
            return StunEndpoint(ip=ip, port=port)
            
        except Exception as e:
            logger.debug(f"Failed to parse address attribute: {e}")
            return None
    
    def _parse_response(self, data: bytes) -> StunResponse:
        """Parse STUN response message"""
        if len(data) < STUN_HEADER_SIZE:
            return StunResponse(
                success=False,
                mapped_endpoint=None,
                source_endpoint=None,
                changed_endpoint=None,
                error_code=None,
                error_reason="Response too short",
                transaction_id=b'',
                raw_response=data
            )
        
        try:
            # Parse header
            msg_type = struct.unpack('>H', data[0:2])[0]
            msg_len = struct.unpack('>H', data[2:4])[0]
            magic = struct.unpack('>I', data[4:8])[0]
            transaction_id = data[8:20]
            
            # Check magic cookie
            if magic != STUN_MAGIC_COOKIE:
                return StunResponse(
                    success=False,
                    mapped_endpoint=None,
                    source_endpoint=None,
                    changed_endpoint=None,
                    error_code=None,
                    error_reason="Invalid magic cookie",
                    transaction_id=transaction_id,
                    raw_response=data
                )
            
            # Check message type
            if msg_type == StunMessageType.BINDING_ERROR_RESPONSE:
                # Parse error code
                error_code = None
                error_reason = "Unknown error"
                
                # Parse attributes
                offset = STUN_HEADER_SIZE
                while offset < len(data):
                    attr_type = struct.unpack('>H', data[offset:offset + 2])[0]
                    attr_len = struct.unpack('>H', data[offset + 2:offset + 4])[0]
                    
                    if attr_type == StunAttributeType.ERROR_CODE:
                        # Class(3bits) + Number(8bits) = Code
                        code = (data[offset + 4] & 0x07) * 100 + data[offset + 5]
                        reason = data[offset + 6:offset + 4 + attr_len].decode('utf-8', errors='ignore')
                        error_code = code
                        error_reason = reason
                    
                    # Pad to 4-byte boundary
                    offset += 4 + attr_len
                    if attr_len % 4:
                        offset += 4 - (attr_len % 4)
                
                return StunResponse(
                    success=False,
                    mapped_endpoint=None,
                    source_endpoint=None,
                    changed_endpoint=None,
                    error_code=error_code,
                    error_reason=error_reason,
                    transaction_id=transaction_id,
                    raw_response=data
                )
            
            if msg_type != StunMessageType.BINDING_RESPONSE:
                return StunResponse(
                    success=False,
                    mapped_endpoint=None,
                    source_endpoint=None,
                    changed_endpoint=None,
                    error_code=None,
                    error_reason=f"Unexpected message type: {msg_type}",
                    transaction_id=transaction_id,
                    raw_response=data
                )
            
            # Parse attributes
            mapped_endpoint = None
            source_endpoint = None
            changed_endpoint = None
            
            offset = STUN_HEADER_SIZE
            while offset < len(data):
                attr_type = struct.unpack('>H', data[offset:offset + 2])[0]
                attr_len = struct.unpack('>H', data[offset + 2:offset + 4])[0]
                attr_value = data[offset + 4:offset + 4 + attr_len]
                
                if attr_type == StunAttributeType.MAPPED_ADDRESS:
                    mapped_endpoint = self._parse_address_attribute(data, offset + 4)
                elif attr_type == StunAttributeType.XOR_MAPPED_ADDRESS:
                    mapped_endpoint = self._parse_address_attribute(data, offset + 4, xor_cookie=1)
                elif attr_type == StunAttributeType.SOURCE_ADDRESS:
                    source_endpoint = self._parse_address_attribute(data, offset + 4)
                elif attr_type == StunAttributeType.CHANGED_ADDRESS:
                    changed_endpoint = self._parse_address_attribute(data, offset + 4)
                
                # Pad to 4-byte boundary
                offset += 4 + attr_len
                if attr_len % 4:
                    offset += 4 - (attr_len % 4)
            
            return StunResponse(
                success=mapped_endpoint is not None,
                mapped_endpoint=mapped_endpoint,
                source_endpoint=source_endpoint,
                changed_endpoint=changed_endpoint,
                error_code=None,
                error_reason=None,
                transaction_id=transaction_id,
                raw_response=data
            )
            
        except Exception as e:
            logger.error(f"Failed to parse STUN response: {e}")
            return StunResponse(
                success=False,
                mapped_endpoint=None,
                source_endpoint=None,
                changed_endpoint=None,
                error_code=None,
                error_reason=str(e),
                transaction_id=b'',
                raw_response=data
            )
    
    async def binding_request(
        self,
        server_host: str,
        server_port: int = 3478,
        change_ip: bool = False,
        change_port: bool = False
    ) -> StunResponse:
        """
        Send STUN binding request
        
        Args:
            server_host: STUN server hostname or IP
            server_port: STUN server port
            change_ip: Request to change IP (for NAT detection)
            change_port: Request to change port (for NAT detection)
            
        Returns:
            StunResponse object
        """
        transaction_id = self._generate_transaction_id()
        request = self._build_binding_request(transaction_id)
        
        # Add CHANGE-REQUEST attribute if needed
        if change_ip or change_port:
            flags = (0x04 if change_ip else 0) | (0x02 if change_port else 0)
            change_attr = struct.pack('>HH', StunAttributeType.CHANGE_REQUEST, 4)
            change_attr += struct.pack('>I', flags)
            
            # Update message length
            msg_len = struct.pack('>H', len(change_attr))
            request = request[:2] + msg_len + request[4:]
            request += change_attr
        
        for attempt in range(self.retry_count):
            try:
                # Resolve hostname
                addrinfo = await asyncio.get_event_loop().getaddrinfo(
                    server_host, server_port,
                    family=socket.AF_INET,  # IPv4 for now
                    type=socket.SOCK_DGRAM
                )
                
                if not addrinfo:
                    logger.warning(f"Could not resolve {server_host}")
                    continue
                
                server_addr = addrinfo[0][4]
                
                # Create UDP socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setblocking(False)
                
                if self.local_port:
                    sock.bind(('0.0.0.0', self.local_port))
                
                try:
                    # Send request
                    await asyncio.get_event_loop().sock_sendto(sock, request, server_addr)
                    
                    # Receive response
                    response_data, _ = await asyncio.wait_for(
                        asyncio.get_event_loop().sock_recvfrom(sock, 1024),
                        timeout=self.timeout
                    )
                    
                    response = self._parse_response(response_data)
                    
                    # Verify transaction ID
                    if response.transaction_id != transaction_id:
                        logger.warning("Transaction ID mismatch")
                        continue
                    
                    return response
                    
                finally:
                    sock.close()
                    
            except asyncio.TimeoutError:
                logger.debug(f"STUN request timeout (attempt {attempt + 1})")
                continue
            except Exception as e:
                logger.debug(f"STUN request error: {e}")
                continue
        
        # All retries exhausted
        return StunResponse(
            success=False,
            mapped_endpoint=None,
            source_endpoint=None,
            changed_endpoint=None,
            error_code=None,
            error_reason="All retries exhausted",
            transaction_id=transaction_id,
            raw_response=b''
        )
    
    async def get_public_endpoint(
        self,
        servers: List[Tuple[str, int]]
    ) -> Optional[StunEndpoint]:
        """
        Get public endpoint using multiple STUN servers
        
        Args:
            servers: List of (host, port) tuples
            
        Returns:
            Public endpoint or None
        """
        for host, port in servers:
            try:
                response = await self.binding_request(host, port)
                if response.success and response.mapped_endpoint:
                    logger.info(f"Got public endpoint from {host}:{port}: {response.mapped_endpoint}")
                    return response.mapped_endpoint
            except Exception as e:
                logger.debug(f"STUN server {host}:{port} failed: {e}")
                continue
        
        logger.warning("All STUN servers failed")
        return None


# Default public STUN servers
DEFAULT_STUN_SERVERS: List[Tuple[str, int]] = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
    ("stun.openstreetmap.org", 3478),
    ("stun.nextcloud.com", 3478),
]


async def test_stun_client():
    """Test STUN client"""
    print("=== STUN Client Test ===")
    
    client = StunClient(timeout=5.0)
    
    # Test with Google's STUN server
    print("\nTesting stun.l.google.com:19302")
    response = await client.binding_request("stun.l.google.com", 19302)
    
    if response.success:
        print(f"Success!")
        print(f"  Mapped endpoint: {response.mapped_endpoint}")
        print(f"  Source endpoint: {response.source_endpoint}")
        print(f"  Changed endpoint: {response.changed_endpoint}")
    else:
        print(f"Failed: {response.error_reason}")
    
    # Test multiple servers
    print("\nTesting multiple servers...")
    public_ep = await client.get_public_endpoint(DEFAULT_STUN_SERVERS[:3])
    if public_ep:
        print(f"Public endpoint: {public_ep}")
    else:
        print("Failed to get public endpoint")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_stun_client())
