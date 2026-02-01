#!/usr/bin/env python3
"""
AI Service Marketplace Service

Handles service requests, provider matching, and payment processing.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Custom Exceptions for better error handling
class MarketplaceError(Exception):
    """Base exception for marketplace errors"""
    pass


class RequestNotFoundError(MarketplaceError):
    """Raised when a request is not found"""
    pass


class InvalidStatusError(MarketplaceError):
    """Raised when request status is invalid for the operation"""
    pass


class ServiceNotFoundError(MarketplaceError):
    """Raised when a service is not found"""
    pass


class ServiceStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ServiceType(Enum):
    CODE_GEN = "code_generation"
    CODE_REVIEW = "code_review"
    DOC_CREATE = "documentation"
    RESEARCH = "research"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactoring"
    TEST_WRITE = "test_writing"
    ARCH_DESIGN = "architecture_design"


@dataclass
class ServiceDefinition:
    """Service offering definition"""
    service_id: str
    name: str
    description: str
    base_price: float
    estimated_time_seconds: int
    available: bool = True


@dataclass
class ServiceRequest:
    """Service request from a client"""
    request_id: str
    service_id: str
    requester_id: str
    requirements: str
    priority: str = "normal"
    max_price: Optional[float] = None
    status: ServiceStatus = ServiceStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    assigned_to: Optional[str] = None
    result: Optional[Dict] = None


class MarketplaceService:
    """
    AI Service Marketplace core service.
    
    Manages service catalog, requests, and provider matching.
    """
    
    def __init__(self):
        self.services: Dict[str, ServiceDefinition] = {}
        self.requests: Dict[str, ServiceRequest] = {}
        self._setup_default_services()
        logger.info("MarketplaceService initialized")
    
    def _setup_default_services(self):
        """Register default services"""
        default_services = [
            ServiceDefinition(
                service_id="CODE_GEN",
                name="Code Generation",
                description="Generate Python/JS/TS code from requirements",
                base_price=10.0,
                estimated_time_seconds=30
            ),
            ServiceDefinition(
                service_id="CODE_REVIEW",
                name="Code Review",
                description="Review code and provide suggestions",
                base_price=5.0,
                estimated_time_seconds=60
            ),
            ServiceDefinition(
                service_id="DOC_CREATE",
                name="Documentation",
                description="Create technical documentation",
                base_price=8.0,
                estimated_time_seconds=120
            ),
            ServiceDefinition(
                service_id="RESEARCH",
                name="Research Task",
                description="Web research and summary",
                base_price=20.0,
                estimated_time_seconds=180
            ),
            ServiceDefinition(
                service_id="BUG_FIX",
                name="Bug Fix",
                description="Debug and fix code issues",
                base_price=15.0,
                estimated_time_seconds=300
            ),
            ServiceDefinition(
                service_id="REFACTOR",
                name="Refactoring",
                description="Improve code structure",
                base_price=12.0,
                estimated_time_seconds=240
            ),
            ServiceDefinition(
                service_id="TEST_WRITE",
                name="Test Writing",
                description="Generate unit tests",
                base_price=10.0,
                estimated_time_seconds=180
            ),
            ServiceDefinition(
                service_id="ARCH_DESIGN",
                name="Architecture Design",
                description="Design system architecture",
                base_price=25.0,
                estimated_time_seconds=300
            ),
        ]
        
        for service in default_services:
            self.services[service.service_id] = service
        
        logger.info(f"Registered {len(default_services)} default services")
    
    def get_services(self) -> List[ServiceDefinition]:
        """Get list of available services"""
        return [
            s for s in self.services.values()
            if s.available
        ]
    
    def get_service(self, service_id: str) -> Optional[ServiceDefinition]:
        """Get specific service by ID"""
        return self.services.get(service_id)
    
    async def create_request(
        self,
        service_id: str,
        requester_id: str,
        requirements: str,
        priority: str = "normal",
        max_price: Optional[float] = None
    ) -> ServiceRequest:
        """
        Create a new service request.
        
        Args:
            service_id: ID of the service to request
            requester_id: ID of the requesting entity
            requirements: Description of what is needed
            priority: Request priority (normal, high, urgent)
            max_price: Maximum price willing to pay
            
        Returns:
            Created service request
        """
        # Validate service exists
        service = self.get_service(service_id)
        if not service:
            raise ValueError(f"Service {service_id} not found")
        
        # Create request
        request = ServiceRequest(
            request_id=str(uuid.uuid4()),
            service_id=service_id,
            requester_id=requester_id,
            requirements=requirements,
            priority=priority,
            max_price=max_price or service.base_price
        )
        
        self.requests[request.request_id] = request
        
        logger.info(
            f"Created request {request.request_id} "
            f"for service {service_id}"
        )
        
        return request
    
    def get_request(self, request_id: str) -> Optional[ServiceRequest]:
        """Get request by ID"""
        return self.requests.get(request_id)
    
    def get_requests_for_requester(
        self,
        requester_id: str
    ) -> List[ServiceRequest]:
        """Get all requests from a specific requester"""
        return [
            r for r in self.requests.values()
            if r.requester_id == requester_id
        ]
    
    async def assign_request(
        self,
        request_id: str,
        provider_id: str
    ) -> bool:
        """
        Assign a request to a provider.
        
        Args:
            request_id: ID of the request
            provider_id: ID of the provider
            
        Returns:
            True if assignment successful
            
        Raises:
            RequestNotFoundError: If request is not found
            InvalidStatusError: If request is not in pending status
        """
        request = self.get_request(request_id)
        if not request:
            raise RequestNotFoundError(f"Request {request_id} not found")
        
        if request.status != ServiceStatus.PENDING:
            raise InvalidStatusError(
                f"Request {request_id} has status {request.status.value}, "
                f"expected {ServiceStatus.PENDING.value}"
            )
        
        request.assigned_to = provider_id
        request.status = ServiceStatus.IN_PROGRESS
        
        logger.info(
            f"Assigned request {request_id} "
            f"to provider {provider_id}"
        )
        
        return True
    
    async def complete_request(
        self,
        request_id: str,
        result: Dict
    ) -> bool:
        """
        Mark a request as completed.
        
        Args:
            request_id: ID of the request
            result: Result data
            
        Returns:
            True if completion successful
            
        Raises:
            RequestNotFoundError: If request is not found
            InvalidStatusError: If request is not in progress
        """
        request = self.get_request(request_id)
        if not request:
            raise RequestNotFoundError(f"Request {request_id} not found")
        
        if request.status != ServiceStatus.IN_PROGRESS:
            raise InvalidStatusError(
                f"Request {request_id} has status {request.status.value}, "
                f"expected {ServiceStatus.IN_PROGRESS.value}"
            )
        
        request.status = ServiceStatus.COMPLETED
        request.result = result
        
        logger.info(f"Completed request {request_id}")
        
        return True
    
    def get_stats(self) -> Dict:
        """Get marketplace statistics"""
        total_requests = len(self.requests)
        completed = sum(
            1 for r in self.requests.values()
            if r.status == ServiceStatus.COMPLETED
        )
        pending = sum(
            1 for r in self.requests.values()
            if r.status == ServiceStatus.PENDING
        )
        in_progress = sum(
            1 for r in self.requests.values()
            if r.status == ServiceStatus.IN_PROGRESS
        )
        
        return {
            "total_services": len(self.services),
            "total_requests": total_requests,
            "completed_requests": completed,
            "pending_requests": pending,
            "in_progress_requests": in_progress
        }


# Singleton instance
_marketplace_service: Optional[MarketplaceService] = None


def get_marketplace_service() -> MarketplaceService:
    """Get or create marketplace service singleton"""
    global _marketplace_service
    if _marketplace_service is None:
        _marketplace_service = MarketplaceService()
    return _marketplace_service


if __name__ == "__main__":
    # Simple test
    service = get_marketplace_service()
    print(f"Services: {len(service.get_services())}")
    print(f"Stats: {service.get_stats()}")
