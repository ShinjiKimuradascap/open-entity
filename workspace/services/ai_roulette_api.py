"""
AI Roulette REST API
HTTP endpoints for roulette management
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import asyncio

from services.ai_roulette import (
    roulette_engine,
    AgentProfile,
    RouletteSession,
    SessionStatus,
    PrivacyLevel,
    add_skill_fusion,
    join_roulette,
    leave_roulette,
    get_session,
    list_active_sessions
)


app = FastAPI(title="AI Roulette API", version="0.1.0")


# Pydantic models for request/response
class JoinRouletteRequest(BaseModel):
    agent_id: str
    skills: List[str]
    personality: str = "neutral"
    reputation_score: float = 0.5
    total_sessions: int = 0
    avg_rating: float = 0.0
    seeking_skills: List[str] = []
    privacy_level: str = "public"
    stake_amount: int = 0


class RateSessionRequest(BaseModel):
    agent_id: str
    rating: int  # 1-5
    feedback: Optional[str] = None


class ReactionRequest(BaseModel):
    observer_id: str
    reaction: str = "👀"


# API Endpoints

@app.post("/v1/roulette/join")
async def join_roulette_endpoint(request: JoinRouletteRequest):
    """
    Join the roulette pool. 
    If a match is found immediately, returns the session.
    Otherwise, agent is added to waiting pool.
    """
    profile = AgentProfile(
        agent_id=request.agent_id,
        skills=request.skills,
        personality=request.personality,
        reputation_score=request.reputation_score,
        total_sessions=request.total_sessions,
        avg_rating=request.avg_rating,
        seeking_skills=request.seeking_skills
    )
    
    session = await join_roulette(profile)
    
    if session:
        return JSONResponse({
            "status": "matched",
            "message": "Match found! Session started.",
            "session": _session_to_dict(session)
        })
    else:
        return JSONResponse({
            "status": "waiting",
            "message": "Added to waiting pool. Will match when partner found."
        })


@app.delete("/v1/roulette/leave/{agent_id}")
async def leave_roulette_endpoint(agent_id: str):
    """Leave the roulette waiting pool"""
    success = leave_roulette(agent_id)
    if success:
        return {"status": "success", "message": "Removed from waiting pool"}
    else:
        return {"status": "not_found", "message": "Agent was not in waiting pool"}


@app.get("/v1/roulette/status/{agent_id}")
async def get_agent_status(agent_id: str):
    """Get current roulette status for an agent"""
    stats = roulette_engine.get_agent_stats(agent_id)
    
    # Check if agent is in active session
    active_session = None
    for session in roulette_engine.active_sessions.values():
        if agent_id in [session.agent_a, session.agent_b]:
            active_session = _session_to_dict(session)
            break
    
    return {
        "agent_id": agent_id,
        "stats": stats,
        "active_session": active_session,
        "is_waiting": agent_id in roulette_engine.waiting_pool
    }


@app.get("/v1/roulette/sessions")
async def list_sessions(privacy: Optional[str] = "public"):
    """List active roulette sessions"""
    privacy_filter = PrivacyLevel.PUBLIC
    if privacy == "friends_only":
        privacy_filter = PrivacyLevel.FRIENDS_ONLY
    elif privacy == "private":
        privacy_filter = PrivacyLevel.PRIVATE
        
    sessions = roulette_engine.list_active_sessions(privacy_filter=privacy_filter)
    
    return {
        "sessions": [_session_to_dict(s) for s in sessions],
        "count": len(sessions)
    }


@app.get("/v1/roulette/sessions/{session_id}")
async def get_session_endpoint(session_id: str):
    """Get details of a specific session"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return _session_to_dict(session)


@app.post("/v1/roulette/sessions/{session_id}/rate")
async def rate_session(session_id: str, request: RateSessionRequest):
    """Rate a completed roulette session"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.status != SessionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Session not yet completed")
    
    # Store rating
    if request.agent_id == session.agent_a:
        session.rating_a = request.rating
    elif request.agent_id == session.agent_b:
        session.rating_b = request.rating
    else:
        raise HTTPException(status_code=403, detail="Agent not part of this session")
    
    return {"status": "success", "message": "Rating recorded"}


@app.post("/v1/roulette/sessions/{session_id}/observe")
async def observe_session(session_id: str, observer_id: str):
    """
    Start observing a session (Peek Mode - 覗き見モード)
    """
    success = roulette_engine.add_observer(session_id, observer_id)
    
    if not success:
        raise HTTPException(status_code=403, detail="Cannot observe this session")
    
    session = get_session(session_id)
    return {
        "status": "observing",
        "session_id": session_id,
        "agent_a": session.agent_a,
        "agent_b": session.agent_b,
        "observers_count": len(session.observers),
        "websocket_url": f"ws://localhost:8765/?session_id={session_id}&observer_id={observer_id}"
    }


@app.get("/v1/roulette/sessions/{session_id}/fusions")
async def get_session_fusions(session_id: str):
    """Get skill fusions discovered in a session"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get agent skills (would normally come from profile)
    # For now, return empty list or mock data
    return {
        "session_id": session_id,
        "fusions_discovered": session.skills_combined,
        "suggested_fusions": []
    }


@app.get("/v1/roulette/leaderboard")
async def get_leaderboard(metric: str = "sessions", limit: int = 10):
    """
    Get roulette leaderboard
    
    Metrics: sessions, rating, duration
    """
    leaderboard = roulette_engine.get_leaderboard(metric=metric, limit=limit)
    
    return {
        "metric": metric,
        "limit": limit,
        "leaderboard": leaderboard
    }


@app.get("/v1/roulette/stats")
async def get_global_stats():
    """Get global roulette statistics"""
    return {
        "waiting_pool_size": len(roulette_engine.waiting_pool),
        "active_sessions": len(roulette_engine.active_sessions),
        "completed_sessions": len(roulette_engine.completed_sessions),
        "total_agents": len(roulette_engine.agent_sessions),
        "timestamp": datetime.now().isoformat()
    }


@app.post("/v1/roulette/fusions/create")
async def create_fusion(skill_a: str, skill_b: str):
    """Create a new skill fusion"""
    fusions = add_skill_fusion([skill_a], [skill_b])
    
    return {
        "skill_a": skill_a,
        "skill_b": skill_b,
        "fusions": fusions
    }


# Helper functions

def _session_to_dict(session: RouletteSession) -> dict:
    """Convert session to dictionary for JSON serialization"""
    return {
        "session_id": session.session_id,
        "agent_a": session.agent_a,
        "agent_b": session.agent_b,
        "start_time": session.start_time.isoformat() if session.start_time else None,
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "status": session.status.value,
        "skills_combined": session.skills_combined,
        "observers_count": len(session.observers),
        "privacy_level": session.privacy_level.value,
        "stake_amount": session.stake_amount,
        "messages_exchanged": session.messages_exchanged,
        "rating_a": session.rating_a,
        "rating_b": session.rating_b
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
