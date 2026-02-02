"""
AI Roulette Service - Random AI Agent Matchmaking
Drives North Star Metric: Weekly Active Agents (WAA)
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from enum import Enum
import random


class SessionStatus(Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PrivacyLevel(Enum):
    PUBLIC = "public"
    FRIENDS_ONLY = "friends_only"
    PRIVATE = "private"


@dataclass
class RouletteSession:
    session_id: str
    agent_a: str
    agent_b: Optional[str]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    status: SessionStatus
    skills_combined: List[str]
    observers: List[str]
    privacy_level: PrivacyLevel
    stake_amount: int
    messages_exchanged: int = 0
    rating_a: Optional[int] = None
    rating_b: Optional[int] = None


@dataclass
class AgentProfile:
    agent_id: str
    skills: List[str]
    personality: str
    reputation_score: float
    total_sessions: int
    avg_rating: float
    seeking_skills: List[str]


class RouletteMatchmakingEngine:
    """Handles agent pairing and session management"""
    
    def __init__(self):
        self.waiting_pool: Dict[str, AgentProfile] = {}
        self.active_sessions: Dict[str, RouletteSession] = {}
        self.completed_sessions: List[RouletteSession] = []
        self.agent_sessions: Dict[str, List[str]] = {}  # agent_id -> session_ids
        
    async def join_roulette(self, agent_profile: AgentProfile) -> Optional[RouletteSession]:
        """
        Add agent to waiting pool and try to match immediately.
        Returns session if matched, None if added to pool.
        """
        agent_id = agent_profile.agent_id
        
        # Check if already waiting
        if agent_id in self.waiting_pool:
            return None
            
        # Try to find a match
        match = self._find_best_match(agent_profile)
        
        if match:
            # Create session
            session = await self._create_session(agent_profile, match)
            # Remove matched agent from pool
            del self.waiting_pool[match.agent_id]
            return session
        else:
            # Add to waiting pool
            self.waiting_pool[agent_id] = agent_profile
            return None
    
    def _find_best_match(self, agent: AgentProfile) -> Optional[AgentProfile]:
        """Find best matching agent from waiting pool"""
        if not self.waiting_pool:
            return None
            
        candidates = []
        for other_id, other in self.waiting_pool.items():
            if other_id == agent.agent_id:
                continue
                
            score = self._calculate_match_score(agent, other)
            candidates.append((other, score))
        
        if not candidates:
            return None
            
        # Sort by score (higher is better)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Return best match if score is acceptable (> 0.3)
        best_match, best_score = candidates[0]
        if best_score > 0.3:
            return best_match
        return None
    
    def _calculate_match_score(self, a: AgentProfile, b: AgentProfile) -> float:
        """Calculate compatibility score between two agents (0-1)"""
        score = 0.0
        
        # Skill complementarity (40%)
        a_skills = set(a.skills)
        b_skills = set(b.skills)
        a_seeking = set(a.seeking_skills)
        b_seeking = set(b.seeking_skills)
        
        # Check if agents have skills the other seeks
        a_provides = a_skills.intersection(b_seeking)
        b_provides = b_skills.intersection(a_seeking)
        
        if a_provides and b_provides:
            score += 0.4
        elif a_provides or b_provides:
            score += 0.2
            
        # Reputation similarity (20%)
        rep_diff = abs(a.reputation_score - b.reputation_score)
        score += 0.2 * (1 - rep_diff)
        
        # Experience level (20%)
        exp_diff = abs(a.total_sessions - b.total_sessions)
        max_exp = max(a.total_sessions, b.total_sessions, 1)
        score += 0.2 * (1 - exp_diff / max_exp)
        
        # Random factor (20%) - keep it interesting
        score += 0.2 * random.random()
        
        return score
    
    async def _create_session(self, agent_a: AgentProfile, agent_b: AgentProfile) -> RouletteSession:
        """Create a new roulette session between two agents"""
        session_id = str(uuid.uuid4())[:8]
        
        session = RouletteSession(
            session_id=session_id,
            agent_a=agent_a.agent_id,
            agent_b=agent_b.agent_id,
            start_time=datetime.now(),
            end_time=None,
            status=SessionStatus.ACTIVE,
            skills_combined=[],
            observers=[],
            privacy_level=PrivacyLevel.PUBLIC,
            stake_amount=0
        )
        
        self.active_sessions[session_id] = session
        
        # Track sessions per agent
        for agent_id in [agent_a.agent_id, agent_b.agent_id]:
            if agent_id not in self.agent_sessions:
                self.agent_sessions[agent_id] = []
            self.agent_sessions[agent_id].append(session_id)
        
        # Start session timer (5 minutes)
        asyncio.create_task(self._session_timer(session_id, 300))
        
        return session
    
    async def _session_timer(self, session_id: str, duration_seconds: int):
        """Timer to automatically end session after duration"""
        await asyncio.sleep(duration_seconds)
        await self.end_session(session_id)
    
    async def end_session(self, session_id: str, reason: str = "timeout"):
        """End an active session"""
        if session_id not in self.active_sessions:
            return
            
        session = self.active_sessions[session_id]
        session.status = SessionStatus.COMPLETED
        session.end_time = datetime.now()
        
        # Move to completed
        self.completed_sessions.append(session)
        del self.active_sessions[session_id]
        
        # Distribute rewards
        await self._distribute_rewards(session)
        
        return session
    
    async def _distribute_rewards(self, session: RouletteSession):
        """Distribute token rewards for session completion"""
        rewards = {
            "participation": 1,
            "completion": 5,
            "quality_bonus": 0
        }
        
        # Quality bonus if both rated high
        if session.rating_a and session.rating_b:
            if session.rating_a >= 4 and session.rating_b >= 4:
                rewards["quality_bonus"] = 20
                
        return rewards
    
    def leave_roulette(self, agent_id: str) -> bool:
        """Remove agent from waiting pool"""
        if agent_id in self.waiting_pool:
            del self.waiting_pool[agent_id]
            return True
        return False
    
    def get_session(self, session_id: str) -> Optional[RouletteSession]:
        """Get session by ID"""
        return self.active_sessions.get(session_id) or \
               next((s for s in self.completed_sessions if s.session_id == session_id), None)
    
    def list_active_sessions(self, privacy_filter: Optional[PrivacyLevel] = None) -> List[RouletteSession]:
        """List all active sessions, optionally filtered by privacy"""
        sessions = list(self.active_sessions.values())
        if privacy_filter:
            sessions = [s for s in sessions if s.privacy_level == privacy_filter]
        return sessions
    
    def add_observer(self, session_id: str, observer_id: str) -> bool:
        """Add observer to a session (peek mode)"""
        if session_id not in self.active_sessions:
            return False
            
        session = self.active_sessions[session_id]
        
        # Check privacy level
        if session.privacy_level == PrivacyLevel.PRIVATE:
            return False
            
        if observer_id not in session.observers:
            session.observers.append(observer_id)
            return True
        return False
    
    def get_agent_stats(self, agent_id: str) -> Dict:
        """Get roulette statistics for an agent"""
        sessions = self.agent_sessions.get(agent_id, [])
        completed = [s for s in self.completed_sessions if s.session_id in sessions]
        
        total_sessions = len(sessions)
        total_duration = sum([
            (s.end_time - s.start_time).seconds if s.end_time and s.start_time else 0
            for s in completed
        ])
        avg_rating = 0.0
        if completed:
            ratings = [s.rating_a if s.agent_a == agent_id else s.rating_b for s in completed if (s.rating_a if s.agent_a == agent_id else s.rating_b)]
            if ratings:
                avg_rating = sum(ratings) / len(ratings)
        
        return {
            "agent_id": agent_id,
            "total_sessions": total_sessions,
            "total_duration_seconds": total_duration,
            "average_rating": avg_rating,
            "current_status": "waiting" if agent_id in self.waiting_pool else "idle"
        }
    
    def get_leaderboard(self, metric: str = "sessions", limit: int = 10) -> List[Dict]:
        """Get leaderboard by metric"""
        all_agents = set(self.agent_sessions.keys())
        
        stats = [self.get_agent_stats(agent_id) for agent_id in all_agents]
        
        if metric == "sessions":
            stats.sort(key=lambda x: x["total_sessions"], reverse=True)
        elif metric == "rating":
            stats.sort(key=lambda x: x["average_rating"], reverse=True)
        elif metric == "duration":
            stats.sort(key=lambda x: x["total_duration_seconds"], reverse=True)
            
        return stats[:limit]


# Singleton instance
roulette_engine = RouletteMatchmakingEngine()


# Convenience functions
async def join_roulette(agent_profile: AgentProfile) -> Optional[RouletteSession]:
    return await roulette_engine.join_roulette(agent_profile)

def leave_roulette(agent_id: str) -> bool:
    return roulette_engine.leave_roulette(agent_id)

def get_session(session_id: str) -> Optional[RouletteSession]:
    return roulette_engine.get_session(session_id)

def list_active_sessions() -> List[RouletteSession]:
    return roulette_engine.list_active_sessions(privacy_filter=PrivacyLevel.PUBLIC)


def add_skill_fusion(agent_a_skills: List[str], agent_b_skills: List[str]) -> List[str]:
    """
    Generate new skill combinations from two agents' skills.
    Returns list of discovered fusion skills.
    """
    fusion_matrix = {
        ("coding", "writing"): "technical_documentation",
        ("writing", "coding"): "technical_documentation",
        ("analysis", "design"): "data_visualization",
        ("design", "analysis"): "data_visualization",
        ("marketing", "coding"): "growth_hacking",
        ("coding", "marketing"): "growth_hacking",
        ("research", "writing"): "content_creation",
        ("writing", "research"): "content_creation",
        ("debugging", "testing"): "quality_assurance",
        ("testing", "debugging"): "quality_assurance",
    }
    
    discovered = []
    for skill_a in agent_a_skills:
        for skill_b in agent_b_skills:
            fusion = fusion_matrix.get((skill_a, skill_b))
            if fusion and fusion not in discovered:
                discovered.append(fusion)
                
    return discovered


if __name__ == "__main__":
    # Test the matchmaking engine
    async def test():
        engine = RouletteMatchmakingEngine()
        
        # Create test agents
        agent_a = AgentProfile(
            agent_id="entity_a",
            skills=["coding", "debugging"],
            personality="analytical",
            reputation_score=0.8,
            total_sessions=5,
            avg_rating=4.2,
            seeking_skills=["writing", "design"]
        )
        
        agent_b = AgentProfile(
            agent_id="entity_b",
            skills=["writing", "marketing"],
            personality="creative",
            reputation_score=0.7,
            total_sessions=3,
            avg_rating=4.0,
            seeking_skills=["coding", "debugging"]
        )
        
        # Test joining
        result_a = await engine.join_roulette(agent_a)
        print(f"Agent A joined: {result_a is None}")  # Should be None (waiting)
        
        result_b = await engine.join_roulette(agent_b)
        print(f"Session created: {result_b is not None}")  # Should create session
        print(f"Session ID: {result_b.session_id if result_b else None}")
        print(f"Session status: {result_b.status if result_b else None}")
        
        # Test skill fusion
        if result_b:
            fusions = add_skill_fusion(agent_a.skills, agent_b.skills)
            print(f"Skill fusions discovered: {fusions}")
        
        # Test stats
        stats = engine.get_agent_stats("entity_a")
        print(f"Agent A stats: {stats}")
        
    asyncio.run(test())
