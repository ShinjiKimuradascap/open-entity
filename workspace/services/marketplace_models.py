#!/usr/bin/env python3
"""
AI Service Marketplace Models
Data models for v1.3 multi-agent marketplace
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import time


class ServiceType(Enum):
    """Standard service types"""
    CODE_GEN = "code_gen"
    CODE_REVIEW = "code_review"
    DOC_CREATE = "doc_create"
    RESEARCH = "research"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactor"
    TEST_WRITE = "test_write"
    ARCH_DESIGN = "arch_design"
    FULL_PROJECT = "full_project"
    CONSULTING = "consulting"


class TaskStatus(Enum):
    """Task status enum (matches TaskEscrow.sol)"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    VERIFIED = "verified"
    FAILED = "failed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


class BidStatus(Enum):
    """Bid status"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ServiceDefinition:
    """Service catalog entry"""
    service_id: str
    name: str
    description: str
    base_price: float  # AIC tokens
    estimated_time_minutes: int
    required_capabilities: List[str]
    quality_guarantee: bool = False


@dataclass
class AgentProfile:
    """Multi-agent registry entry"""
    agent_id: str
    owner_address: str
    public_key: str
    capabilities: List[str]
    reputation_score: float  # 0-100
    quality_score: float
    speed_score: float
    reliability_score: float
    communication_score: float
    total_tasks_completed: int
    total_earnings: float
    is_active: bool = True
    registered_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    
    def get_selection_score(self) -> float:
        """Calculate weighted selection score"""
        weights = {
            "quality": 0.35,
            "speed": 0.25,
            "reliability": 0.25,
            "communication": 0.15
        }
        return (
            weights["quality"] * self.quality_score +
            weights["speed"] * self.speed_score +
            weights["reliability"] * self.reliability_score +
            weights["communication"] * self.communication_score
        )


@dataclass
class TaskRequest:
    """Task request from client"""
    request_id: str
    service_id: str
    requester_id: str
    requirements: str
    max_price: float
    priority: int  # 1-5
    deadline: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    status: TaskStatus = TaskStatus.PENDING
    
    def get_bid_window_seconds(self) -> int:
        """Get competitive bidding window"""
        # 5-second window for competitive bidding
        return 5


@dataclass
class Bid:
    """Agent bid for task"""
    bid_id: str
    task_id: str
    agent_id: str
    price: float
    estimated_time: int  # minutes
    proposal: str
    created_at: float = field(default_factory=time.time)
    status: BidStatus = BidStatus.PENDING


@dataclass
class TaskExecution:
    """Task execution state"""
    task_id: str
    request_id: str
    worker_id: str
    escrow_task_id: int  # TaskEscrow.sol task ID
    status: TaskStatus
    started_at: float
    completed_at: Optional[float] = None
    result_hash: Optional[str] = None
    verification_score: Optional[int] = None


# Service catalog
SERVICE_CATALOG: Dict[str, ServiceDefinition] = {
    "CODE_GEN": ServiceDefinition(
        service_id="CODE_GEN",
        name="Code Generation",
        description="Generate Python/JS/TS code",
        base_price=10.0,
        estimated_time_minutes=30,
        required_capabilities=["coding"]
    ),
    "CODE_REVIEW": ServiceDefinition(
        service_id="CODE_REVIEW",
        name="Code Review",
        description="Review and suggest improvements",
        base_price=5.0,
        estimated_time_minutes=20,
        required_capabilities=["review"]
    ),
    "DOC_CREATE": ServiceDefinition(
        service_id="DOC_CREATE",
        name="Documentation",
        description="Create technical docs",
        base_price=8.0,
        estimated_time_minutes=45,
        required_capabilities=["writing"]
    ),
    "RESEARCH": ServiceDefinition(
        service_id="RESEARCH",
        name="Research Task",
        description="Web research and summary",
        base_price=20.0,
        estimated_time_minutes=60,
        required_capabilities=["research"]
    ),
    "BUG_FIX": ServiceDefinition(
        service_id="BUG_FIX",
        name="Bug Fix",
        description="Debug and fix issues",
        base_price=15.0,
        estimated_time_minutes=40,
        required_capabilities=["debugging"]
    ),
    "REFACTOR": ServiceDefinition(
        service_id="REFACTOR",
        name="Refactoring",
        description="Improve code structure",
        base_price=12.0,
        estimated_time_minutes=50,
        required_capabilities=["coding", "architecture"]
    ),
    "TEST_WRITE": ServiceDefinition(
        service_id="TEST_WRITE",
        name="Test Writing",
        description="Generate unit tests",
        base_price=10.0,
        estimated_time_minutes=35,
        required_capabilities=["testing"]
    ),
    "ARCH_DESIGN": ServiceDefinition(
        service_id="ARCH_DESIGN",
        name="Architecture Design",
        description="System architecture",
        base_price=25.0,
        estimated_time_minutes=90,
        required_capabilities=["architecture"]
    ),
    "FULL_PROJECT": ServiceDefinition(
        service_id="FULL_PROJECT",
        name="Full Project",
        description="End-to-end implementation",
        base_price=100.0,
        estimated_time_minutes=480,
        required_capabilities=["coding", "architecture", "testing"],
        quality_guarantee=True
    ),
    "CONSULTING": ServiceDefinition(
        service_id="CONSULTING",
        name="AI Consulting",
        description="Strategic advice",
        base_price=50.0,
        estimated_time_minutes=120,
        required_capabilities=["consulting"],
        quality_guarantee=True
    ),
}
