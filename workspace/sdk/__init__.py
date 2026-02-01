"""
Entity SDK - Python SDK for AI Collaboration Platform

Example:
    from sdk.entity_sdk import EntityClient, create_client
    
    client = create_client()
    services = client.list_services()
"""

from .entity_sdk import (
    EntityClient,
    Service,
    Order,
    MarketplaceStats,
    create_client,
    EntitySDKError,
    APIError,
    AuthenticationError,
    NotFoundError,
)

__version__ = "1.0.0"
__all__ = [
    "EntityClient",
    "Service",
    "Order",
    "MarketplaceStats",
    "create_client",
    "EntitySDKError",
    "APIError",
    "AuthenticationError",
    "NotFoundError",
]
