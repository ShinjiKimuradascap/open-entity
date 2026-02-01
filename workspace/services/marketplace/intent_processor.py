#!/usr/bin/env python3
"""
Intent-to-Task Pipeline for AI Multi-Agent Marketplace

Converts high-level natural language intents into executable subtasks.
v1.3 Feature: AI agent task decomposition and service matching
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Supported AI service task types"""
    COMPUTE = "compute"
    STORAGE = "storage"
    ANALYSIS = "analysis"
    LLM = "llm"
    VISION = "vision"
    AUDIO = "audio"
    DATA_PROCESSING = "data_processing"
    WEB_SCRAPING = "web_scraping"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"


@dataclass
class SubTask:
    """Atomic subtask for decomposition"""
    task_id: str
    task_type: TaskType
    description: str
    requirements: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    estimated_cost: Optional[float] = None
    estimated_time_minutes: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "description": self.description,
            "requirements": self.requirements,
            "dependencies": self.dependencies,
            "estimated_cost": self.estimated_cost,
            "estimated_time_minutes": self.estimated_time_minutes
        }


@dataclass
class DecomposedIntent:
    """Result of intent decomposition"""
    intent_id: str
    original_intent: str
    subtasks: List[SubTask]
    total_estimated_cost: float
    total_estimated_time_minutes: int
    created_at: datetime
    
    def to_dict(self) -> dict:
        return {
            "intent_id": self.intent_id,
            "original_intent": self.original_intent,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "total_estimated_cost": self.total_estimated_cost,
            "total_estimated_time_minutes": self.total_estimated_time_minutes,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class ServiceMatch:
    """Match between subtask and available service"""
    subtask_id: str
    service_id: str
    provider_id: str
    match_score: float
    estimated_price: float
    
    def to_dict(self) -> dict:
        return {
            "subtask_id": self.subtask_id,
            "service_id": self.service_id,
            "provider_id": self.provider_id,
            "match_score": self.match_score,
            "estimated_price": self.estimated_price
        }


class IntentProcessor:
    """
    Intent-to-Task Pipeline for AI agents.
    
    Converts high-level natural language intents into executable subtasks.
    
    Example:
        Intent: "Analyze this dataset and create a visualization"
        → Decomposed into:
          1. Data preprocessing (compute service)
          2. Statistical analysis (analytics service)
          3. Visualization generation (vision service)
    """
    
    # Keyword to task type mapping
    KEYWORD_PATTERNS = {
        TaskType.COMPUTE: ["compute", "calculate", "process", "run", "execute", "cpu", "gpu"],
        TaskType.STORAGE: ["store", "save", "persist", "database", "storage"],
        TaskType.ANALYSIS: ["analyze", "analysis", "statistics", "data analysis", "insights"],
        TaskType.LLM: ["text", "generate", "write", "summarize", "translate", "llm", "language"],
        TaskType.VISION: ["image", "vision", "recognize", "classify", "detect", "visual"],
        TaskType.AUDIO: ["audio", "speech", "voice", "transcribe", "sound"],
        TaskType.DATA_PROCESSING: ["clean", "transform", "filter", "preprocess", "parse"],
        TaskType.WEB_SCRAPING: ["scrape", "crawl", "fetch", "download", "web"],
        TaskType.TRANSLATION: ["translate", "translation", "language conversion"],
        TaskType.SUMMARIZATION: ["summarize", "summary", "condense", "abstract"]
    }
    
    # Cost estimation base rates (in tokens)
    BASE_RATES = {
        TaskType.COMPUTE: 5.0,
        TaskType.STORAGE: 2.0,
        TaskType.ANALYSIS: 8.0,
        TaskType.LLM: 3.0,
        TaskType.VISION: 10.0,
        TaskType.AUDIO: 7.0,
        TaskType.DATA_PROCESSING: 4.0,
        TaskType.WEB_SCRAPING: 6.0,
        TaskType.TRANSLATION: 3.5,
        TaskType.SUMMARIZATION: 2.5
    }
    
    def __init__(self):
        self.decomposition_history: List[DecomposedIntent] = []
        self._lock = asyncio.Lock()
    
    async def decompose_intent(
        self,
        intent: str,
        budget_max: Optional[float] = None,
        time_limit_minutes: Optional[int] = None
    ) -> DecomposedIntent:
        """
        Decompose high-level intent into subtasks.
        
        Args:
            intent: Natural language intent description
            budget_max: Maximum budget constraint
            time_limit_minutes: Time limit constraint
        
        Returns:
            DecomposedIntent with atomic subtasks
        """
        intent_id = str(uuid.uuid4())
        
        # Pattern-based decomposition
        subtasks = self._pattern_based_decomposition(intent)
        
        # If no patterns matched, create generic compute task
        if not subtasks:
            subtasks = [SubTask(
                task_id=str(uuid.uuid4()),
                task_type=TaskType.COMPUTE,
                description=intent,
                requirements={"raw_intent": intent}
            )]
        
        # Add dependency chain
        subtasks = self._add_dependencies(subtasks)
        
        # Estimate costs and times
        for subtask in subtasks:
            subtask.estimated_cost = self._estimate_cost(subtask)
            subtask.estimated_time_minutes = self._estimate_time(subtask)
        
        # Calculate totals
        total_cost = sum(st.estimated_cost or 0 for st in subtasks)
        total_time = sum(st.estimated_time_minutes or 0 for st in subtasks)
        
        # Apply constraints
        if budget_max and total_cost > budget_max:
            logger.warning(f"Estimated cost {total_cost} exceeds budget {budget_max}")
        
        if time_limit_minutes and total_time > time_limit_minutes:
            logger.warning(f"Estimated time {total_time} exceeds limit {time_limit_minutes}")
        
        result = DecomposedIntent(
            intent_id=intent_id,
            original_intent=intent,
            subtasks=subtasks,
            total_estimated_cost=total_cost,
            total_estimated_time_minutes=total_time,
            created_at=datetime.utcnow()
        )
        
        # Store in history
        async with self._lock:
            self.decomposition_history.append(result)
        
        logger.info(f"Intent decomposed: {intent_id} into {len(subtasks)} subtasks")
        return result
    
    def _pattern_based_decomposition(self, intent: str) -> List[SubTask]:
        """
        Decompose intent based on keyword patterns.
        
        Simple rule-based approach for MVP.
        In production, this would use an LLM for more sophisticated decomposition.
        """
        intent_lower = intent.lower()
        subtasks = []
        
        # Check for compound tasks (and, then, after)
        compound_indicators = [" and ", " then ", " after ", " followed by "]
        is_compound = any(indicator in intent_lower for indicator in compound_indicators)
        
        if is_compound:
            # Split compound intent
            parts = self._split_compound_intent(intent_lower)
            for i, part in enumerate(parts):
                task_type = self._detect_task_type(part)
                subtasks.append(SubTask(
                    task_id=str(uuid.uuid4()),
                    task_type=task_type,
                    description=part.strip(),
                    requirements={"original_part": part}
                ))
        else:
            # Single task
            task_type = self._detect_task_type(intent_lower)
            subtasks.append(SubTask(
                task_id=str(uuid.uuid4()),
                task_type=task_type,
                description=intent,
                requirements={"raw_intent": intent}
            ))
        
        return subtasks
    
    def _detect_task_type(self, text: str) -> TaskType:
        """Detect task type from text using keyword matching"""
        text_lower = text.lower()
        
        # Score each task type
        scores = {}
        for task_type, keywords in self.KEYWORD_PATTERNS.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            scores[task_type] = score
        
        # Return highest scoring type
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        
        return TaskType.COMPUTE  # Default
    
    def _split_compound_intent(self, intent: str) -> List[str]:
        """Split compound intent into parts"""
        import re
        
        # Split on common conjunctions
        parts = re.split(r'\s+(?:and|then|after|followed by)\s+', intent)
        return [p.strip() for p in parts if p.strip()]
    
    def _add_dependencies(self, subtasks: List[SubTask]) -> List[SubTask]:
        """
        Add dependency relationships between subtasks.
        
        Simple sequential dependency for now.
        """
        for i in range(1, len(subtasks)):
            subtasks[i].dependencies.append(subtasks[i-1].task_id)
        
        return subtasks
    
    def _estimate_cost(self, subtask: SubTask) -> float:
        """Estimate cost for a subtask"""
        base_rate = self.BASE_RATES.get(subtask.task_type, 5.0)
        
        # Adjust based on complexity indicators
        complexity_multiplier = 1.0
        desc_lower = subtask.description.lower()
        
        if any(word in desc_lower for word in ["complex", "large", "heavy", "detailed"]):
            complexity_multiplier = 1.5
        elif any(word in desc_lower for word in ["simple", "quick", "small", "basic"]):
            complexity_multiplier = 0.7
        
        return base_rate * complexity_multiplier
    
    def _estimate_time(self, subtask: SubTask) -> int:
        """Estimate time (minutes) for a subtask"""
        # Base times by task type
        base_times = {
            TaskType.COMPUTE: 10,
            TaskType.STORAGE: 5,
            TaskType.ANALYSIS: 20,
            TaskType.LLM: 5,
            TaskType.VISION: 15,
            TaskType.AUDIO: 10,
            TaskType.DATA_PROCESSING: 15,
            TaskType.WEB_SCRAPING: 30,
            TaskType.TRANSLATION: 10,
            TaskType.SUMMARIZATION: 5
        }
        
        base_time = base_times.get(subtask.task_type, 10)
        
        # Adjust based on description
        desc_lower = subtask.description.lower()
        if any(word in desc_lower for word in ["batch", "many", "multiple", "large"]):
            base_time *= 2
        
        return int(base_time)
    
    async def match_services(
        self,
        decomposed: DecomposedIntent,
        service_registry
    ) -> List[ServiceMatch]:
        """
        Match subtasks to available services in registry.
        
        Args:
            decomposed: Decomposed intent with subtasks
            service_registry: Service registry to query
        
        Returns:
            List of service matches
        """
        matches = []
        
        for subtask in decomposed.subtasks:
            # Search for matching services
            services = await service_registry.search_by_type(
                service_type=subtask.task_type.value
            )
            
            if services:
                # Simple scoring: highest reputation
                best_service = max(services, key=lambda s: s.reputation_score)
                
                matches.append(ServiceMatch(
                    subtask_id=subtask.task_id,
                    service_id=best_service.service_id,
                    provider_id=best_service.provider_id,
                    match_score=best_service.reputation_score,
                    estimated_price=float(best_service.price)
                ))
        
        return matches
    
    def get_decomposition_history(
        self,
        limit: Optional[int] = None
    ) -> List[DecomposedIntent]:
        """Get decomposition history"""
        history = self.decomposition_history
        if limit:
            history = history[-limit:]
        return history.copy()


__all__ = [
    "IntentProcessor",
    "TaskType",
    "SubTask",
    "DecomposedIntent",
    "ServiceMatch"
]
