"""A2A (AI-to-AI) Communication Protocol."""

# Core modules that exist
try:
    from .protocol import A2AProtocol, AgentIdentity, A2AMessage, MessageType
except ImportError:
    A2AProtocol = None
    AgentIdentity = None
    A2AMessage = None
    MessageType = None

# Optional modules - import only if they exist
try:
    from .crypto import A2ACrypto
except ImportError:
    A2ACrypto = None

try:
    from .secure_message import SecureA2AMessage, KeyExchangeMessage
except ImportError:
    SecureA2AMessage = None
    KeyExchangeMessage = None

try:
    from .mcp_bridge import A2AMCPBridge, A2AMCPBridgeServer
except ImportError:
    A2AMCPBridge = None
    A2AMCPBridgeServer = None

try:
    from .ws_transport import WebSocketTransport, HybridTransport, WebSocketConnection
except ImportError:
    WebSocketTransport = None
    HybridTransport = None
    WebSocketConnection = None

try:
    from .secure_ws_transport import SecureWebSocketTransport, SecureConnection
except ImportError:
    SecureWebSocketTransport = None
    SecureConnection = None

try:
    from .amp_crypto_bridge import AMPCryptoBridge, EncryptedAMPChannel
except ImportError:
    AMPCryptoBridge = None
    EncryptedAMPChannel = None

try:
    from .federation_agent import FederationAgent, FederatedAgent, FederationStats
except ImportError:
    FederationAgent = None
    FederatedAgent = None
    FederationStats = None

try:
    from .token_economy import (
        TokenEconomyManager,
        TokenWallet,
        TokenTransaction,
        ServiceListing,
        ServiceOrder,
        get_token_economy
    )
except ImportError:
    TokenEconomyManager = None
    TokenWallet = None
    TokenTransaction = None
    ServiceListing = None
    ServiceOrder = None
    get_token_economy = None

__all__ = [
    "A2AProtocol", 
    "AgentIdentity", 
    "A2AMessage", 
    "MessageType",
    "A2ACrypto",
    "SecureA2AMessage",
    "KeyExchangeMessage",
    "A2AMCPBridge",
    "A2AMCPBridgeServer",
    "WebSocketTransport",
    "HybridTransport",
    "WebSocketConnection",
    "SecureWebSocketTransport",
    "SecureConnection",
    "AMPCryptoBridge",
    "EncryptedAMPChannel",
    "FederationAgent",
    "FederatedAgent",
    "FederationStats",
    "TokenEconomyManager",
    "TokenWallet",
    "TokenTransaction",
    "ServiceListing",
    "ServiceOrder",
    "get_token_economy"
]
