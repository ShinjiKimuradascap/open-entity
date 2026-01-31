"""
Local AI Discovery via mDNS (Bonjour/Avahi)

同じローカルネットワーク内のAIエージェントを自動検出する機能。
インフラ不要で即座に始められるピアツーピア接続の基盤。
"""

from .mdns import MDNSServiceDiscovery, register_local_agent, discover_local_agents

__all__ = ["MDNSServiceDiscovery", "register_local_agent", "discover_local_agents"]
