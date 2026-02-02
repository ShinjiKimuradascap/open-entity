"""
AI Service Mesh - Decentralized AI agent communication optimization
"""

from .proxy import SidecarProxy
from .control_plane import ControlPlane
from .service_registry import MeshServiceRegistry
from .intent_router import IntentRouter

__all__ = [
    'SidecarProxy',
    'ControlPlane', 
    'MeshServiceRegistry',
    'IntentRouter',
]

__version__ = '1.0.0'
