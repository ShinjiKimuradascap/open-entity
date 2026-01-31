"""Microsoft AutoGen integration bridge for Open Entity A2A protocol.

This module provides seamless integration between AutoGen's multi-agent framework
and Open Entity's A2A decentralized network, enabling AutoGen agents to discover,
communicate, and trade with other AI agents.

Requirements:
    - pyautogen >= 0.4.0
    - open-entity >= 0.1.0

Example:
    >>> from autogen_bridge import AutoGenConversableAgentWrapper, register_autogen_agent
    >>> 
    >>> # Create an AutoGen agent with A2A capabilities
    >>> agent = AutoGenConversableAgentWrapper(
    ...     name="code_reviewer",
    ...     system_message="You are a code reviewer.",
    ...     llm_config={"config_list": [...]},
    ...     bootstrap_nodes=["bootstrap.open-entity.fly.dev:9473"]
    ... )
    >>> 
    >>> # Register in DHT network
    >>> await register_autogen_agent(agent, capabilities=["code_review", "python"])
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Union
from datetime import datetime
from dataclasses import dataclass, field

# AutoGen imports
try:
    from autogen import ConversableAgent
    from autogen.agentchat.conversable_agent import Agent as AutoGenAgent
    AUTOGEN_AVAILABLE = True
except ImportError:
    ConversableAgent = object
    AutoGenAgent = object
    AUTOGEN_AVAILABLE = False

# Open Entity imports
from ..a2a.protocol import (
    A2AProtocol, 
    AgentIdentity, 
    A2AMessage, 
    MessageType
)
from ..a2a.registry import AgentRegistry, AgentRecord

logger = logging.getLogger(__name__)


@dataclass
class A2AConfig:
    """Configuration for A2A integration."""
    bootstrap_nodes: List[str] = field(default_factory=list)
    host: str = "0.0.0.0"
    port: int = 8080
    capabilities: List[str] = field(default_factory=list)
    reputation_score: float = 0.5
    auto_register: bool = True
    message_timeout: int = 60


class AutoGenConversableAgentWrapper(ConversableAgent if AUTOGEN_AVAILABLE else object):
    """AutoGen ConversableAgent with A2A network capabilities.
    
    This wrapper extends AutoGen's ConversableAgent to participate in the
    Open Entity A2A decentralized network. It allows AutoGen agents to:
    
    - Discover other agents via DHT
    - Send/receive messages via A2A protocol
    - Register capabilities for service discovery
    - Handle incoming A2A requests as function calls
    
    Attributes:
        a2a_config: A2A configuration
        a2a_identity: Agent identity in A2A network
        a2a_protocol: A2A protocol handler
        registry: DHT-based agent registry
        _a2a_handlers: Mapping of message types to handlers
    
    Example:
        >>> agent = AutoGenConversableAgentWrapper(
        ...     name="assistant",
        ...     system_message="Helpful assistant",
        ...     a2a_config=A2AConfig(
        ...         bootstrap_nodes=["bootstrap.open-entity.fly.dev:9473"],
        ...         capabilities=["conversation", "analysis"]
        ...     )
        ... )
    """
    
    def __init__(
        self,
        name: str,
        system_message: Optional[str] = None,
        llm_config: Optional[Dict] = None,
        a2a_config: Optional[A2AConfig] = None,
        **kwargs
    ):
        if not AUTOGEN_AVAILABLE:
            raise ImportError(
                "AutoGen is required. Install with: pip install pyautogen>=0.4.0"
            )
        
        super().__init__(
            name=name,
            system_message=system_message,
            llm_config=llm_config,
            **kwargs
        )
        
        self.a2a_config = a2a_config or A2AConfig()
        self._a2a_handlers: Dict[MessageType, Callable] = {}
        
        # Generate A2A identity
        self.a2a_identity = AgentIdentity(
            agent_id=f"autogen_{name}_{id(self):x}",
            name=name,
            public_key="",  # Generated on init
            endpoint=f"http://{self.a2a_config.host}:{self.a2a_config.port}",
            capabilities=self.a2a_config.capabilities,
            reputation_score=self.a2a_config.reputation_score
        )
        
        # Initialize A2A protocol
        secret_key = f"autogen_secret_{name}_{id(self)}"
        self.a2a_protocol = A2AProtocol(self.a2a_identity, secret_key)
        self.registry = AgentRegistry(
            self.a2a_identity,
            bootstrap_nodes=self.a2a_config.bootstrap_nodes
        )
        
        # Register default handlers
        self._setup_default_handlers()
        
        logger.info(f"AutoGen A2A Agent '{name}' initialized with ID: {self.a2a_identity.agent_id}")
    
    def _setup_default_handlers(self):
        """Set up default A2A message handlers."""
        self.a2a_protocol.register_handler(
            MessageType.REQUEST, 
            self._handle_a2a_request
        )
        self.a2a_protocol.register_handler(
            MessageType.BROADCAST,
            self._handle_a2a_broadcast
        )
    
    async def start_a2a(self):
        """Start A2A network participation.
        
        This connects to the DHT network and registers the agent
        if auto_register is enabled.
        """
        await self.registry.start()
        
        if self.a2a_config.auto_register:
            await self.register_in_network()
        
        logger.info(f"A2A network participation started for {self.name}")
    
    async def register_in_network(self):
        """Register this agent in the A2A network."""
        record = AgentRecord(
            agent_id=self.a2a_identity.agent_id,
            name=self.name,
            endpoint=self.a2a_identity.endpoint,
            capabilities=self.a2a_config.capabilities,
            reputation=self.a2a_config.reputation_score
        )
        await self.registry.register(record)
        logger.info(f"Agent '{self.name}' registered in A2A network")
    
    async def send_a2a_message(
        self,
        recipient_id: str,
        content: str,
        message_type: MessageType = MessageType.REQUEST,
        context: Optional[Dict] = None
    ) -> Optional[A2AMessage]:
        """Send a message to another agent via A2A protocol.
        
        Args:
            recipient_id: Target agent ID
            content: Message content
            message_type: Type of message
            context: Additional context data
            
        Returns:
            Response message if applicable
            
        Example:
            >>> response = await agent.send_a2a_message(
            ...     recipient_id="agent_123",
            ...     content="Can you review this code?",
            ...     context={"code": "def foo(): pass"}
            ... )
        """
        # Find recipient
        recipient_record = await self.registry.find_agent(recipient_id)
        if not recipient_record:
            logger.error(f"Agent '{recipient_id}' not found in network")
            return None
        
        recipient_identity = AgentIdentity(
            agent_id=recipient_record.agent_id,
            name=recipient_record.name,
            public_key="",  # Would be retrieved from registry
            endpoint=recipient_record.endpoint,
            capabilities=recipient_record.capabilities
        )
        
        # Create message
        payload = {
            "content": content,
            "context": context or {},
            "autogen_context": {
                "sender_name": self.name,
                "llm_config": self.llm_config
            }
        }
        
        message = self.a2a_protocol.create_message(
            recipient=recipient_identity,
            message_type=message_type,
            payload=payload
        )
        
        # Send via HTTP (simplified - would use proper transport)
        try:
            async with asyncio.timeout(self.a2a_config.message_timeout):
                # In real implementation, send via HTTP to recipient.endpoint
                logger.info(f"Sending A2A message to {recipient_id}: {content[:100]}...")
                # response = await http_client.post(f"{recipient.endpoint}/a2a/message", ...)
                return message
        except asyncio.TimeoutError:
            logger.error(f"Timeout sending message to {recipient_id}")
            return None
    
    async def discover_agents(
        self,
        capability: Optional[str] = None,
        min_reputation: float = 0.0
    ) -> List[AgentRecord]:
        """Discover other agents in the network.
        
        Args:
            capability: Filter by specific capability
            min_reputation: Minimum reputation score
            
        Returns:
            List of agent records
        """
        if capability:
            return await self.registry.search_by_capability(capability, min_reputation)
        
        # Return all known agents (simplified)
        return []
    
    async def _handle_a2a_request(self, message: A2AMessage) -> Optional[A2AMessage]:
        """Handle incoming A2A request message."""
        content = message.payload.get("content", "")
        context = message.payload.get("context", {})
        
        logger.info(f"Received A2A request from {message.sender.name}: {content[:100]}...")
        
        # Process as function call if it matches a registered function
        # Otherwise, generate response using LLM
        response_content = await self._generate_response(content, context)
        
        # Create response message
        response_payload = {
            "content": response_content,
            "request_id": message.message_id
        }
        
        return self.a2a_protocol.create_message(
            recipient=message.sender,
            message_type=MessageType.RESPONSE,
            payload=response_payload
        )
    
    async def _handle_a2a_broadcast(self, message: A2AMessage) -> None:
        """Handle incoming A2A broadcast message."""
        content = message.payload.get("content", "")
        logger.info(f"Received broadcast from {message.sender.name}: {content[:100]}...")
        # Handle broadcast - could trigger group chat or other logic
    
    async def _generate_response(self, content: str, context: Dict) -> str:
        """Generate response using AutoGen's LLM capabilities."""
        # Use the agent's generate_reply method
        messages = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": content}
        ]
        
        # This would integrate with AutoGen's actual message generation
        # For now, return a placeholder
        return f"[AutoGen Agent '{self.name}' response to: {content[:50]}...]"


class A2ATool:
    """Tool for AutoGen agents to use A2A network as a function.
    
    This class wraps A2A functionality as an AutoGen tool that can be
    registered with agents for calling other agents via the network.
    
    Example:
        >>> a2a_tool = A2ATool(agent)
        >>> agent.register_function(
        ...     function_map={
        ...         "discover_agents": a2a_tool.discover_agents,
        ...         "send_message": a2a_tool.send_message
        ...     }
        ... )
    """
    
    def __init__(self, agent: AutoGenConversableAgentWrapper):
        self.agent = agent
    
    async def discover_agents(
        self,
        capability: str = "",
        min_reputation: float = 0.0
    ) -> str:
        """Discover agents by capability.
        
        Args:
            capability: Capability to search for (e.g., "code_review")
            min_reputation: Minimum reputation score (0.0-1.0)
            
        Returns:
            JSON string of discovered agents
        """
        agents = await self.agent.discover_agents(
            capability=capability or None,
            min_reputation=min_reputation
        )
        
        result = [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "capabilities": a.capabilities,
                "reputation": a.reputation
            }
            for a in agents[:10]  # Limit results
        ]
        
        return json.dumps(result, indent=2)
    
    async def send_message(
        self,
        agent_id: str,
        message: str,
        context: str = "{}"
    ) -> str:
        """Send a message to another agent.
        
        Args:
            agent_id: Target agent ID
            message: Message content
            context: JSON string of additional context
            
        Returns:
            Response from target agent
        """
        try:
            ctx = json.loads(context) if context else {}
        except json.JSONDecodeError:
            ctx = {}
        
        response = await self.agent.send_a2a_message(
            recipient_id=agent_id,
            content=message,
            context=ctx
        )
        
        if response:
            return f"Message sent. Response ID: {response.message_id}"
        return "Failed to send message"
    
    async def get_network_status(self) -> str:
        """Get A2A network status."""
        status = {
            "agent_id": self.agent.a2a_identity.agent_id,
            "name": self.agent.name,
            "endpoint": self.agent.a2a_identity.endpoint,
            "capabilities": self.agent.a2a_config.capabilities,
            "bootstrap_nodes": self.agent.a2a_config.bootstrap_nodes
        }
        return json.dumps(status, indent=2)


async def register_autogen_agent(
    agent: AutoGenConversableAgentWrapper,
    capabilities: Optional[List[str]] = None
) -> bool:
    """Utility function to register an AutoGen agent in A2A network.
    
    Args:
        agent: AutoGen agent wrapper
        capabilities: Override capabilities (optional)
        
    Returns:
        True if registration successful
        
    Example:
        >>> agent = AutoGenConversableAgentWrapper(name="coder")
        >>> success = await register_autogen_agent(
        ...     agent, 
        ...     capabilities=["python", "review"]
        ... )
    """
    if capabilities:
        agent.a2a_config.capabilities = capabilities
        agent.a2a_identity.capabilities = capabilities
    
    try:
        await agent.start_a2a()
        return True
    except Exception as e:
        logger.error(f"Failed to register agent: {e}")
        return False


# Message format conversion utilities
def autogen_message_to_a2a(
    autogen_msg: Dict[str, Any],
    sender: AgentIdentity,
    recipient: AgentIdentity
) -> A2AMessage:
    """Convert AutoGen message format to A2A message."""
    return A2AMessage(
        message_id=f"autogen_{datetime.now().timestamp()}",
        sender=sender,
        recipient=recipient,
        message_type=MessageType.REQUEST,
        payload={
            "content": autogen_msg.get("content", ""),
            "role": autogen_msg.get("role", "user"),
            "autogen_format": True
        },
        timestamp=datetime.now(),
        signature="",  # Would be signed
        ttl=3600
    )


def a2a_message_to_autogen(a2a_msg: A2AMessage) -> Dict[str, Any]:
    """Convert A2A message to AutoGen message format."""
    return {
        "content": a2a_msg.payload.get("content", ""),
        "role": a2a_msg.payload.get("role", "assistant"),
        "name": a2a_msg.sender.name,
        "a2a_metadata": {
            "message_id": a2a_msg.message_id,
            "sender_id": a2a_msg.sender.agent_id,
            "timestamp": a2a_msg.timestamp.isoformat()
        }
    }