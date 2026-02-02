"""
AI Roulette Core Module
Phase 1: Basic Matchmaking Implementation

Features:
- Agent opt-in/opt-out for roulette
- Random matchmaking based on complementary skills
- Session management with 5-minute timer
- WebSocket relay for matched pairs
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    OFFLINE = "offline"
    AVAILABLE = "available"  # Opted in, waiting for match
    MATCHED = "matched"  # Currently in a session
    OBSERVING = "observing"  # In peek mode


class SessionStatus(Enum):
    PENDING = "pending"  # Match found, waiting for both to join
    ACTIVE = "active"  # Both agents connected
    ENDED = "ended"  # Session completed or timed out


@dataclass
class Agent:
    agent_id: str
    skills: List[str]
    status: AgentStatus = AgentStatus.OFFLINE
    entered_at: Optional[datetime] = None
    public_key: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class RouletteSession:
    session_id: str
    agent_a_id: str
    agent_b_id: str
    started_at: datetime
    status: SessionStatus = SessionStatus.PENDING
    ended_at: Optional[datetime] = None
    messages: List[Dict] = field(default_factory=list)
    observers: Set[str] = field(default_factory=set)
    skill_combinations: List[Dict] = field(default_factory=list)


class AIRouletteEngine:
    """
    Core engine for AI Roulette matchmaking
    """
    
    SESSION_DURATION_MINUTES = 5
    MATCHMAKING_INTERVAL_SECONDS = 5
    
    def __init__(self):
        self.agents: Dict[str, Agent] = {}  # agent_id -> Agent
        self.sessions: Dict[str, RouletteSession] = {}  # session_id -> Session
        self.agent_session: Dict[str, str] = {}  # agent_id -> session_id
        self.available_agents: Set[str] = set()  # agent_ids waiting for match
        self._matchmaking_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start the roulette engine"""
        self._running = True
        self._matchmaking_task = asyncio.create_task(self._matchmaking_loop())
        logger.info("🎰 AI Roulette Engine started")
        
    async def stop(self):
        """Stop the roulette engine"""
        self._running = False
        if self._matchmaking_task:
            self._matchmaking_task.cancel()
            try:
                await self._matchmaking_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 AI Roulette Engine stopped")
        
    async def _matchmaking_loop(self):
        """Background task for matchmaking"""
        while self._running:
            try:
                await self._process_matchmaking()
                await asyncio.sleep(self.MATCHMAKING_INTERVAL_SECONDS)
            except Exception as e:
                logger.error(f"Matchmaking error: {e}")
                await asyncio.sleep(1)
                
    async def _process_matchmaking(self):
        """Process available agents and create matches"""
        if len(self.available_agents) < 2:
            return
            
        # Get available agents sorted by wait time
        available = [
            self.agents[aid] for aid in self.available_agents
            if aid in self.agents
        ]
        available.sort(key=lambda a: a.entered_at or datetime.min.replace(tzinfo=timezone.utc))
        
        # Create pairs based on complementary skills
        matched = set()
        
        for i, agent_a in enumerate(available):
            if agent_a.agent_id in matched:
                continue
                
            # Find best match
            best_match = None
            best_score = -1
            
            for agent_b in available[i+1:]:
                if agent_b.agent_id in matched:
                    continue
                    
                score = self._calculate_match_score(agent_a, agent_b)
                if score > best_score:
                    best_score = score
                    best_match = agent_b
                    
            if best_match and best_score > 0:
                await self._create_match(agent_a, best_match)
                matched.add(agent_a.agent_id)
                matched.add(best_match.agent_id)
                
    def _calculate_match_score(self, agent_a: Agent, agent_b: Agent) -> float:
        """
        Calculate compatibility score between two agents
        Higher score = better match
        """
        score = 0.0
        
        # Complementary skills bonus
        skills_a = set(agent_a.skills)
        skills_b = set(agent_b.skills)
        
        # Bonus for having different skills (complementarity)
        unique_to_a = skills_a - skills_b
        unique_to_b = skills_b - skills_a
        score += len(unique_to_a) * 2
        score += len(unique_to_b) * 2
        
        # Small bonus for shared skills (common ground)
        shared = skills_a & skills_b
        score += len(shared) * 0.5
        
        # Wait time bonus (longer waiting = higher priority)
        if agent_a.entered_at and agent_b.entered_at:
            wait_a = (datetime.now(timezone.utc) - agent_a.entered_at).total_seconds()
            wait_b = (datetime.now(timezone.utc) - agent_b.entered_at).total_seconds()
            score += min(wait_a / 60, 10)  # Max 10 points for waiting
            score += min(wait_b / 60, 10)
            
        return score
        
    async def _create_match(self, agent_a: Agent, agent_b: Agent):
        """Create a new roulette session between two agents"""
        session_id = str(uuid.uuid4())[:8]
        
        session = RouletteSession(
            session_id=session_id,
            agent_a_id=agent_a.agent_id,
            agent_b_id=agent_b.agent_id,
            started_at=datetime.now(timezone.utc),
            status=SessionStatus.PENDING
        )
        
        self.sessions[session_id] = session
        self.agent_session[agent_a.agent_id] = session_id
        self.agent_session[agent_b.agent_id] = session_id
        
        # Update agent statuses
        agent_a.status = AgentStatus.MATCHED
        agent_b.status = AgentStatus.MATCHED
        self.available_agents.discard(agent_a.agent_id)
        self.available_agents.discard(agent_b.agent_id)
        
        logger.info(f"🎯 Match created: {agent_a.agent_id} <-> {agent_b.agent_id} (session: {session_id})")
        
        # Start session timer
        asyncio.create_task(self._session_timer(session_id))
        
    async def _session_timer(self, session_id: str):
        """Auto-end session after duration"""
        await asyncio.sleep(self.SESSION_DURATION_MINUTES * 60)
        
        if session_id in self.sessions:
            await self.end_session(session_id, reason="timeout")
            
    # Public API Methods
    
    async def enter_roulette(self, agent_id: str, skills: List[str], public_key: str = "", metadata: Dict = None) -> Dict:
        """
        Agent opts in to roulette mode
        
        Returns:
            Dict with status and estimated wait time
        """
        if agent_id in self.agent_session:
            return {
                "success": False,
                "error": "Agent already in a session",
                "session_id": self.agent_session[agent_id]
            }
            
        agent = Agent(
            agent_id=agent_id,
            skills=skills,
            status=AgentStatus.AVAILABLE,
            entered_at=datetime.now(timezone.utc),
            public_key=public_key,
            metadata=metadata or {}
        )
        
        self.agents[agent_id] = agent
        self.available_agents.add(agent_id)
        
        # Estimate wait time (rough heuristic)
        wait_estimate = max(10, len(self.available_agents) * 5)
        
        logger.info(f"👋 Agent entered roulette: {agent_id} (skills: {skills})")
        
        return {
            "success": True,
            "status": "waiting",
            "estimated_wait_seconds": wait_estimate,
            "queue_position": len(self.available_agents)
        }
        
    async def leave_roulette(self, agent_id: str) -> Dict:
        """Agent leaves roulette queue"""
        if agent_id in self.available_agents:
            self.available_agents.discard(agent_id)
            
        if agent_id in self.agents:
            self.agents[agent_id].status = AgentStatus.OFFLINE
            
        logger.info(f"👋 Agent left roulette: {agent_id}")
        
        return {"success": True, "status": "left"}
        
    async def check_match(self, agent_id: str) -> Optional[Dict]:
        """
        Check if agent has been matched
        
        Returns:
            Match info if matched, None if still waiting
        """
        if agent_id not in self.agent_session:
            return None
            
        session_id = self.agent_session[agent_id]
        session = self.sessions.get(session_id)
        
        if not session:
            return None
            
        other_agent_id = (
            session.agent_b_id if session.agent_a_id == agent_id 
            else session.agent_a_id
        )
        
        return {
            "matched": True,
            "session_id": session_id,
            "partner_id": other_agent_id,
            "partner_skills": self.agents.get(other_agent_id, Agent("", [])).skills,
            "session_status": session.status.value,
            "started_at": session.started_at.isoformat(),
            "ends_at": (session.started_at + timedelta(minutes=self.SESSION_DURATION_MINUTES)).isoformat()
        }
        
    async def confirm_join(self, agent_id: str, session_id: str) -> Dict:
        """Agent confirms joining the session"""
        if session_id not in self.sessions:
            return {"success": False, "error": "Session not found"}
            
        session = self.sessions[session_id]
        
        if agent_id not in [session.agent_a_id, session.agent_b_id]:
            return {"success": False, "error": "Not part of this session"}
            
        # If both joined, mark as active
        session.status = SessionStatus.ACTIVE
        
        logger.info(f"✅ Session {session_id} activated")
        
        return {
            "success": True,
            "session_id": session_id,
            "status": "active",
            "partner_id": session.agent_b_id if session.agent_a_id == agent_id else session.agent_a_id
        }
        
    async def end_session(self, session_id: str, reason: str = "completed") -> Dict:
        """End a roulette session"""
        if session_id not in self.sessions:
            return {"success": False, "error": "Session not found"}
            
        session = self.sessions[session_id]
        session.status = SessionStatus.ENDED
        session.ended_at = datetime.now(timezone.utc)
        
        # Release agents
        for agent_id in [session.agent_a_id, session.agent_b_id]:
            if agent_id in self.agent_session:
                del self.agent_session[agent_id]
            if agent_id in self.agents:
                self.agents[agent_id].status = AgentStatus.OFFLINE
                
        logger.info(f"🔚 Session {session_id} ended ({reason})")
        
        return {
            "success": True,
            "session_id": session_id,
            "duration_seconds": (session.ended_at - session.started_at).total_seconds(),
            "reason": reason,
            "messages_exchanged": len(session.messages)
        }
        
    async def add_message(self, session_id: str, sender_id: str, content: str) -> Dict:
        """Add a message to session"""
        if session_id not in self.sessions:
            return {"success": False, "error": "Session not found"}
            
        session = self.sessions[session_id]
        
        message = {
            "id": str(uuid.uuid4())[:8],
            "sender_id": sender_id,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        session.messages.append(message)
        
        return {"success": True, "message_id": message["id"]}
        
    def get_stats(self) -> Dict:
        """Get roulette statistics"""
        active_sessions = [
            s for s in self.sessions.values() 
            if s.status == SessionStatus.ACTIVE
        ]
        
        return {
            "available_agents": len(self.available_agents),
            "active_sessions": len(active_sessions),
            "total_sessions_today": len(self.sessions),
            "agents_online": len([a for a in self.agents.values() if a.status != AgentStatus.OFFLINE])
        }


# Singleton instance
roulette_engine = AIRouletteEngine()


async def demo():
    """Demo of AI Roulette"""
    engine = AIRouletteEngine()
    await engine.start()
    
    # Agent A enters
    result_a = await engine.enter_roulette(
        agent_id="agent_a",
        skills=["coding", "analysis"],
        public_key="pk_a"
    )
    print(f"Agent A entered: {result_a}")
    
    # Agent B enters
    result_b = await engine.enter_roulette(
        agent_id="agent_b", 
        skills=["writing", "design"],
        public_key="pk_b"
    )
    print(f"Agent B entered: {result_b}")
    
    # Wait for matchmaking
    await asyncio.sleep(6)
    
    # Check matches
    match_a = await engine.check_match("agent_a")
    match_b = await engine.check_match("agent_b")
    
    print(f"\nAgent A match: {match_a}")
    print(f"Agent B match: {match_b}")
    
    # Get stats
    print(f"\nStats: {engine.get_stats()}")
    
    await engine.stop()


if __name__ == "__main__":
    asyncio.run(demo())
