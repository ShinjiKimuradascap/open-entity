"""A2A Protocol core implementation."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import json
import hashlib
import hmac
import secrets


class MessageType(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    CONTRACT = "contract"
    PAYMENT = "payment"
    HEARTBEAT = "heartbeat"


@dataclass
class AgentIdentity:
    """Agent identity information."""
    agent_id: str
    name: str
    public_key: str
    endpoint: str
    capabilities: List[str] = field(default_factory=list)
    reputation_score: float = 0.5
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "public_key": self.public_key,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "reputation_score": self.reputation_score,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentIdentity":
        return cls(
            agent_id=data["agent_id"],
            name=data["name"],
            public_key=data["public_key"],
            endpoint=data["endpoint"],
            capabilities=data.get("capabilities", []),
            reputation_score=data.get("reputation_score", 0.5),
        )


@dataclass
class A2AMessage:
    """A2A message format."""
    message_id: str
    sender: AgentIdentity
    recipient: AgentIdentity
    message_type: MessageType
    payload: Dict[str, Any]
    timestamp: datetime
    signature: str
    ttl: int = 3600
    
    def to_json(self) -> str:
        return json.dumps({
            "message_id": self.message_id,
            "sender": self.sender.to_dict(),
            "recipient": self.recipient.to_dict(),
            "message_type": self.message_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "signature": self.signature,
            "ttl": self.ttl,
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> "A2AMessage":
        data = json.loads(json_str)
        return cls(
            message_id=data["message_id"],
            sender=AgentIdentity.from_dict(data["sender"]),
            recipient=AgentIdentity.from_dict(data["recipient"]),
            message_type=MessageType(data["message_type"]),
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            signature=data["signature"],
            ttl=data.get("ttl", 3600),
        )
    
    def verify_signature(self, secret_key: str) -> bool:
        """Verify message signature."""
        expected = hmac.new(
            secret_key.encode(),
            f"{self.message_id}{self.timestamp.isoformat()}".encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)


class A2AProtocol:
    """A2A Protocol handler."""
    
    def __init__(self, identity: AgentIdentity, secret_key: str):
        self.identity = identity
        self.secret_key = secret_key
        self.message_handlers: Dict[MessageType, callable] = {}
    
    def register_handler(self, message_type: MessageType, handler: callable):
        """Register a message handler."""
        self.message_handlers[message_type] = handler
    
    def create_message(
        self,
        recipient: AgentIdentity,
        message_type: MessageType,
        payload: Dict[str, Any],
        ttl: int = 3600
    ) -> A2AMessage:
        """Create a signed message."""
        message_id = secrets.token_hex(16)
        timestamp = datetime.now()
        
        # Sign the message
        signature = hmac.new(
            self.secret_key.encode(),
            f"{message_id}{timestamp.isoformat()}".encode(),
            hashlib.sha256
        ).hexdigest()
        
        return A2AMessage(
            message_id=message_id,
            sender=self.identity,
            recipient=recipient,
            message_type=message_type,
            payload=payload,
            timestamp=timestamp,
            signature=signature,
            ttl=ttl,
        )
    
    async def handle_message(self, message: A2AMessage) -> Optional[A2AMessage]:
        """Handle incoming message."""
        # Verify signature
        if not message.verify_signature(self.secret_key):
            return None
        
        # Check TTL
        age = (datetime.now() - message.timestamp).total_seconds()
        if age > message.ttl:
            return None
        
        # Call handler
        handler = self.message_handlers.get(message.message_type)
        if handler:
            return await handler(message)
        return None
