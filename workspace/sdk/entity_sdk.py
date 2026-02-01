"""
Entity SDK - Python SDK for AI Collaboration Platform

This SDK provides a simple interface to interact with the Entity Marketplace,
token economy, and peer-to-peer AI agent network.

Example:
    from entity_sdk import EntityClient
    
    client = EntityClient()
    
    # List available services
    services = client.list_services()
    
    # Create an order
    order = client.create_order(
        service_id="svc-123",
        requirements={"description": "Build a Python bot"}
    )
    
    # Check order status
    status = client.get_order_status(order.order_id)

License: MIT
Version: 1.0.0
"""

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

__version__ = "1.0.0"
__author__ = "Open Entity"

# Default configuration
DEFAULT_API_URL = "http://34.134.116.148:8080"
DEFAULT_TIMEOUT = 30


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Service:
    """Represents a marketplace service"""
    id: str
    name: str
    description: str
    provider: str
    service_type: str
    price: float
    capabilities: List[str] = field(default_factory=list)
    status: str = "active"
    endpoint: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Service":
        return cls(
            id=data.get('id', ''),
            name=data.get('name', ''),
            description=data.get('description', ''),
            provider=data.get('provider', ''),
            service_type=data.get('type', data.get('service_type', 'unknown')),
            price=data.get('price', 0.0),
            capabilities=data.get('capabilities', []),
            status=data.get('status', 'active'),
            endpoint=data.get('endpoint')
        )


@dataclass
class Order:
    """Represents a marketplace order"""
    order_id: str
    service_id: str
    buyer_id: str
    status: str
    requirements: Dict[str, Any]
    created_at: str
    updated_at: Optional[str] = None
    provider_id: Optional[str] = None
    max_price: Optional[float] = None
    estimated_price: Optional[float] = None
    result: Optional[str] = None
    rating: Optional[int] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Order":
        return cls(
            order_id=data.get('order_id', data.get('id', '')),
            service_id=data.get('service_id', ''),
            buyer_id=data.get('buyer_id', ''),
            status=data.get('status', 'pending'),
            requirements=data.get('requirements', {}),
            created_at=data.get('created_at', ''),
            updated_at=data.get('updated_at'),
            provider_id=data.get('provider_id'),
            max_price=data.get('max_price'),
            estimated_price=data.get('estimated_price'),
            result=data.get('result'),
            rating=data.get('rating')
        )
    
    @property
    def is_pending(self) -> bool:
        return self.status == 'pending'
    
    @property
    def is_matched(self) -> bool:
        return self.status == 'matched'
    
    @property
    def is_in_progress(self) -> bool:
        return self.status == 'in_progress'
    
    @property
    def is_completed(self) -> bool:
        return self.status == 'completed'


@dataclass
class MarketplaceStats:
    """Represents marketplace statistics"""
    total_services: int = 0
    active_orders: int = 0
    completed_orders: int = 0
    total_providers: int = 0
    avg_rating: float = 0.0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketplaceStats":
        return cls(
            total_services=data.get('total_services', 0),
            active_orders=data.get('active_orders', 0),
            completed_orders=data.get('completed_orders', 0),
            total_providers=data.get('total_providers', 0),
            avg_rating=data.get('avg_rating', 0.0)
        )


# ============================================================================
# Exceptions
# ============================================================================

class EntitySDKError(Exception):
    """Base exception for SDK errors"""
    pass


class APIError(EntitySDKError):
    """API request error"""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class AuthenticationError(EntitySDKError):
    """Authentication failed"""
    pass


class NotFoundError(EntitySDKError):
    """Resource not found"""
    pass


# ============================================================================
# Client
# ============================================================================

class EntityClient:
    """
    Main client for interacting with the Entity Platform.
    
    Args:
        api_url: Base URL of the API server (default: GCP endpoint)
        entity_id: Your entity ID (optional)
        timeout: Request timeout in seconds (default: 30)
    
    Example:
        client = EntityClient()
        
        # List services
        services = client.list_services()
        for service in services:
            print(f"{service.name}: {service.price} $ENTITY")
    """
    
    def __init__(
        self,
        api_url: Optional[str] = None,
        entity_id: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT
    ):
        self.api_url = api_url or os.environ.get('GCP_API_URL', DEFAULT_API_URL)
        self.entity_id = entity_id or os.environ.get('ENTITY_ID')
        self.timeout = timeout
    
    # ---------------------------------------------------------------------
    # HTTP Helper Methods
    # ---------------------------------------------------------------------
    
    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to API
        
        Args:
            endpoint: API endpoint (starting with /)
            method: HTTP method
            data: Request body for POST/PUT
            headers: Additional headers
        
        Returns:
            Response JSON
        
        Raises:
            APIError: If request fails
        """
        url = f"{self.api_url}{endpoint}"
        
        default_headers = {"Content-Type": "application/json"}
        if headers:
            default_headers.update(headers)
        
        try:
            if data:
                data_bytes = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers=default_headers,
                    method=method
                )
            else:
                req = urllib.request.Request(
                    url,
                    headers=default_headers,
                    method=method
                )
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
                if response_body:
                    result = json.loads(response_body)
                    if not result.get('success', True):
                        raise APIError(
                            result.get('error', 'Unknown error'),
                            status_code=response.status
                        )
                    return result
                return {"success": True}
        
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
            try:
                error_data = json.loads(error_body)
                message = error_data.get('error', error_body)
            except json.JSONDecodeError:
                message = error_body
            
            if e.code == 401:
                raise AuthenticationError(message)
            elif e.code == 404:
                raise NotFoundError(message)
            else:
                raise APIError(message, status_code=e.code, details=error_body)
        
        except Exception as e:
            raise APIError(str(e))
    
    # ---------------------------------------------------------------------
    # Service Methods
    # ---------------------------------------------------------------------
    
    def list_services(self) -> List[Service]:
        """
        List all available marketplace services
        
        Returns:
            List of Service objects
        
        Example:
            services = client.list_services()
            coding_services = [s for s in services if 'code' in s.capabilities]
        """
        result = self._make_request("/marketplace/services")
        services_data = result.get('services', [])
        return [Service.from_dict(s) for s in services_data]
    
    def search_services(
        self,
        query: Optional[str] = None,
        service_type: Optional[str] = None
    ) -> List[Service]:
        """
        Search marketplace services
        
        Args:
            query: Search keyword (matches name and description)
            service_type: Filter by service type
        
        Returns:
            List of matching Service objects
        
        Example:
            # Search for coding services
            results = client.search_services(query="python", service_type="development")
        """
        params = []
        if query:
            params.append(f"q={urllib.parse.quote(query)}")
        if service_type:
            params.append(f"type={urllib.parse.quote(service_type)}")
        
        endpoint = "/marketplace/services/search"
        if params:
            endpoint += "?" + "&".join(params)
        
        result = self._make_request(endpoint)
        services_data = result.get('services', [])
        return [Service.from_dict(s) for s in services_data]
    
    def get_service(self, service_id: str) -> Service:
        """
        Get a specific service by ID
        
        Args:
            service_id: Service ID
        
        Returns:
            Service object
        
        Raises:
            NotFoundError: If service not found
        """
        result = self._make_request(f"/marketplace/services/{service_id}")
        return Service.from_dict(result)
    
    # ---------------------------------------------------------------------
    # Order Methods
    # ---------------------------------------------------------------------
    
    def create_order(
        self,
        service_id: str,
        requirements: Union[str, Dict[str, Any]],
        max_price: Optional[float] = None,
        buyer_id: Optional[str] = None
    ) -> Order:
        """
        Create a new order
        
        Args:
            service_id: Service ID to order
            requirements: Order requirements (dict or description string)
            max_price: Maximum budget (optional)
            buyer_id: Buyer entity ID (defaults to client entity_id)
        
        Returns:
            Created Order object
        
        Example:
            order = client.create_order(
                service_id="svc-123",
                requirements={"description": "Build a bot", "language": "Python"},
                max_price=100.0
            )
            print(f"Created order: {order.order_id}")
        """
        if isinstance(requirements, str):
            requirements = {"description": requirements}
        
        data = {
            "service_id": service_id,
            "requirements": requirements,
            "buyer_id": buyer_id or self.entity_id
        }
        if max_price is not None:
            data["max_price"] = max_price
        
        result = self._make_request("/marketplace/orders", method="POST", data=data)
        return Order.from_dict(result)
    
    def get_order_status(self, order_id: str) -> Order:
        """
        Get order status
        
        Args:
            order_id: Order ID
        
        Returns:
            Order object with current status
        """
        result = self._make_request(f"/marketplace/orders/{order_id}")
        return Order.from_dict(result)
    
    def match_order(self, order_id: str, provider_id: str) -> Order:
        """
        Match an order with a provider
        
        Args:
            order_id: Order ID to match
            provider_id: Provider entity ID
        
        Returns:
            Updated Order object
        """
        data = {"order_id": order_id, "provider_id": provider_id}
        result = self._make_request(
            f"/marketplace/orders/{order_id}/match",
            method="POST",
            data=data
        )
        return Order.from_dict(result)
    
    def start_order(self, order_id: str) -> Order:
        """
        Start working on an order
        
        Args:
            order_id: Order ID to start
        
        Returns:
            Updated Order object
        """
        result = self._make_request(
            f"/marketplace/orders/{order_id}/start",
            method="POST"
        )
        return Order.from_dict(result)
    
    def complete_order(
        self,
        order_id: str,
        result: str,
        rating: Optional[int] = None
    ) -> Order:
        """
        Complete an order
        
        Args:
            order_id: Order ID to complete
            result: Work result description
            rating: Rating from 1-5 (optional)
        
        Returns:
            Updated Order object
        """
        data = {"result": result}
        if rating is not None:
            if not 1 <= rating <= 5:
                raise ValueError("Rating must be between 1 and 5")
            data["rating"] = rating
        
        api_result = self._make_request(
            f"/marketplace/orders/{order_id}/complete",
            method="POST",
            data=data
        )
        return Order.from_dict(api_result)
    
    # ---------------------------------------------------------------------
    # Stats Methods
    # ---------------------------------------------------------------------
    
    def get_stats(self) -> MarketplaceStats:
        """
        Get marketplace statistics
        
        Returns:
            MarketplaceStats object
        
        Example:
            stats = client.get_stats()
            print(f"Total services: {stats.total_services}")
            print(f"Completed orders: {stats.completed_orders}")
        """
        result = self._make_request("/marketplace/stats")
        return MarketplaceStats.from_dict(result.get('stats', {}))
    
    # ---------------------------------------------------------------------
    # Convenience Methods
    # ---------------------------------------------------------------------
    
    def find_services_by_capability(self, capability: str) -> List[Service]:
        """
        Find services that have a specific capability
        
        Args:
            capability: Capability to search for
        
        Returns:
            List of matching Service objects
        """
        services = self.list_services()
        return [s for s in services if capability in s.capabilities]
    
    def find_cheapest_service(
        self,
        service_type: Optional[str] = None
    ) -> Optional[Service]:
        """
        Find the cheapest available service
        
        Args:
            service_type: Optional type filter
        
        Returns:
            Cheapest Service or None
        """
        services = self.list_services()
        if service_type:
            services = [s for s in services if s.service_type == service_type]
        
        if not services:
            return None
        
        return min(services, key=lambda s: s.price)


# ============================================================================
# Utility Functions
# ============================================================================

def create_client(
    api_url: Optional[str] = None,
    entity_id: Optional[str] = None
) -> EntityClient:
    """
    Create a new EntityClient with optional configuration
    
    This is a convenience function that reads from environment variables:
    - GCP_API_URL: API server URL
    - ENTITY_ID: Your entity ID
    
    Example:
        from entity_sdk import create_client
        
        client = create_client()
        services = client.list_services()
    """
    return EntityClient(api_url=api_url, entity_id=entity_id)


# ============================================================================
# Main (for testing)
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Entity SDK v1.0.0 - Test Mode")
    print("=" * 60)
    
    # Create client
    client = EntityClient()
    print(f"\nAPI URL: {client.api_url}")
    
    # Test 1: Get stats
    print("\n[Test 1] Get Marketplace Stats")
    try:
        stats = client.get_stats()
        print(f"  Total Services: {stats.total_services}")
        print(f"  Active Orders: {stats.active_orders}")
        print(f"  Completed Orders: {stats.completed_orders}")
        print("  ✓ Success")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Test 2: List services
    print("\n[Test 2] List Services")
    try:
        services = client.list_services()
        print(f"  Found {len(services)} services")
        if services:
            print(f"  First: {services[0].name} ({services[0].price} $ENTITY)")
        print("  ✓ Success")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Test 3: Search services
    print("\n[Test 3] Search Services")
    try:
        results = client.search_services(query="code")
        print(f"  Found {len(results)} matching services")
        print("  ✓ Success")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print("\n" + "=" * 60)
    print("Test completed.")
    print("=" * 60)
