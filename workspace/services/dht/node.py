"""
DHT Node Types - NodeID and NodeInfo

Based on dht_node.py implementation with improvements:
- Consistent 160-bit NodeID
- IPv4/IPv6 endpoint support
- Capability flags
"""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Any, Dict

KEY_SIZE = 160  # SHA-1 hash size in bits


class NodeID:
    """160-bit DHT Node ID with XOR distance metric"""
    
    def __init__(self, data: Optional[bytes] = None):
        if data is None:
            # Generate random ID
            data = bytes([random.randint(0, 255) for _ in range(KEY_SIZE // 8)])
        elif isinstance(data, str):
            # Hash string to ID
            data = hashlib.sha1(data.encode()).digest()
        elif isinstance(data, int):
            # Convert int to bytes
            data = data.to_bytes(KEY_SIZE // 8, byteorder='big')
        
        self._data = data[:KEY_SIZE // 8]
        self._int = int.from_bytes(self._data, byteorder='big')
    
    @property
    def bytes(self) -> bytes:
        return self._data
    
    @property
    def int(self) -> int:
        return self._int
    
    @property
    def hex(self) -> str:
        return self._data.hex()
    
    def distance_to(self, other: 'NodeID') -> int:
        """XOR distance to another node"""
        return self._int ^ other._int
    
    def distance_bytes(self, other: 'NodeID') -> bytes:
        """XOR distance as bytes"""
        xor = self._int ^ other._int
        return xor.to_bytes(KEY_SIZE // 8, byteorder='big')
    
    def bit_length(self) -> int:
        """Most significant bit position (0-indexed)"""
        if self._int == 0:
            return 0
        return self._int.bit_length() - 1
    
    def __eq__(self, other) -> bool:
        if isinstance(other, NodeID):
            return self._data == other._data
        return False
    
    def __hash__(self) -> int:
        return hash(self._data)
    
    def __lt__(self, other: 'NodeID') -> bool:
        return self._int < other._int
    
    def __repr__(self) -> str:
        return f"NodeID({self.hex[:16]}...)"
    
    def __str__(self) -> str:
        return self.hex[:16]
    
    @classmethod
    def from_hex(cls, hex_str: str) -> 'NodeID':
        return cls(bytes.fromhex(hex_str))
    
    @classmethod
    def from_entity(cls, entity_id: str) -> 'NodeID':
        """Generate NodeID from entity identifier"""
        return cls(data=entity_id)


@dataclass
class NodeInfo:
    """DHT node information with endpoint and metadata"""
    
    node_id: NodeID
    host: str
    port: int
    last_seen: Optional[datetime] = None
    failed_pings: int = 0
    capabilities: List[str] = field(default_factory=list)
    public_key: Optional[str] = None
    
    def __post_init__(self):
        if self.last_seen is None:
            self.last_seen = datetime.utcnow()
    
    @property
    def id_bytes(self) -> bytes:
        return self.node_id.bytes
    
    @property
    def endpoint(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    def distance_to(self, target_id: NodeID) -> int:
        return self.node_id.distance_to(target_id)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id.hex,
            "host": self.host,
            "port": self.port,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "capabilities": self.capabilities,
            "public_key": self.public_key,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NodeInfo':
        return cls(
            node_id=NodeID.from_hex(data["node_id"]),
            host=data["host"],
            port=data["port"],
            last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None,
            capabilities=data.get("capabilities", []),
            public_key=data.get("public_key"),
        )
