"""
Cross-Chain Bridge Module

Enables AI agents to transfer tokens across multiple blockchains.
"""

from .ethereum_adapter import EthereumBridgeAdapter, LockReceipt, BridgeTransaction

__all__ = [
    "EthereumBridgeAdapter",
    "LockReceipt", 
    "BridgeTransaction"
]
