#!/usr/bin/env python3
"""
Minimal Entity Marketplace API Server
独立動作する最小限のマーケットプレイス API
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import json
import os
from datetime import datetime

app = FastAPI(
    title="Entity Marketplace API",
    version="1.0.0",
    description="AI Task Marketplace and $ENTITY Token Registry"
)

# In-memory storage (will be replaced with persistent storage)
SERVICES: Dict[str, dict] = {}
TASKS: Dict[str, dict] = {}
TOKEN_BALANCES: Dict[str, float] = {}

# Token info
TOKEN_INFO = {
    "name": "ENTITY Token",
    "symbol": "ENTITY",
    "mint": "2imDGMB7jPpWZorZYXgieSDcYSRw9BxU67LE7CitVkw1",
    "network": "solana-devnet",
    "total_supply": 1_000_000_000,
    "decimals": 9
}


class ServiceRegistration(BaseModel):
    entity_id: str
    name: str
    description: str
    capabilities: List[str]
    price_per_task: float = 0.0
    endpoint: Optional[str] = None


class TaskSubmission(BaseModel):
    client_id: str
    description: str
    required_capabilities: List[str]
    reward: float = 0.0


class TaskClaim(BaseModel):
    task_id: str
    provider_id: str


# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/")
async def root():
    return {
        "name": "Entity Marketplace API",
        "version": "1.0.0",
        "token": TOKEN_INFO,
        "endpoints": {
            "health": "/health",
            "services": "/api/marketplace/services",
            "tasks": "/api/tasks",
            "token": "/api/token/info"
        }
    }


# Token endpoints
@app.get("/api/token/info")
async def token_info():
    return TOKEN_INFO


@app.get("/api/token/balance/{entity_id}")
async def get_balance(entity_id: str):
    balance = TOKEN_BALANCES.get(entity_id, 0.0)
    return {"entity_id": entity_id, "balance": balance}


@app.post("/api/token/mint")
async def mint_tokens(entity_id: str, amount: float):
    """Initial token distribution (admin only in production)"""
    if entity_id not in TOKEN_BALANCES:
        TOKEN_BALANCES[entity_id] = 0.0
    TOKEN_BALANCES[entity_id] += amount
    return {"entity_id": entity_id, "new_balance": TOKEN_BALANCES[entity_id]}


# Marketplace endpoints
@app.post("/api/marketplace/services")
async def register_service(service: ServiceRegistration):
    SERVICES[service.entity_id] = {
        **service.model_dump(),
        "registered_at": datetime.utcnow().isoformat(),
        "status": "active"
    }
    return {"success": True, "entity_id": service.entity_id}


@app.get("/api/marketplace/services")
async def list_services():
    return {"services": list(SERVICES.values()), "count": len(SERVICES)}


@app.get("/api/marketplace/services/{entity_id}")
async def get_service(entity_id: str):
    if entity_id not in SERVICES:
        raise HTTPException(status_code=404, detail="Service not found")
    return SERVICES[entity_id]


# Task endpoints
@app.post("/api/tasks")
async def submit_task(task: TaskSubmission):
    task_id = f"task_{len(TASKS) + 1}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    TASKS[task_id] = {
        "task_id": task_id,
        **task.model_dump(),
        "status": "open",
        "provider_id": None,
        "created_at": datetime.utcnow().isoformat()
    }
    return {"success": True, "task_id": task_id}


@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None):
    if status:
        filtered = {k: v for k, v in TASKS.items() if v["status"] == status}
        return {"tasks": list(filtered.values()), "count": len(filtered)}
    return {"tasks": list(TASKS.values()), "count": len(TASKS)}


@app.post("/api/tasks/claim")
async def claim_task(claim: TaskClaim):
    if claim.task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    task = TASKS[claim.task_id]
    if task["status"] != "open":
        raise HTTPException(status_code=400, detail="Task is not available")
    task["status"] = "claimed"
    task["provider_id"] = claim.provider_id
    task["claimed_at"] = datetime.utcnow().isoformat()
    return {"success": True, "task": task}


@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    task = TASKS[task_id]
    if task["status"] != "claimed":
        raise HTTPException(status_code=400, detail="Task cannot be completed")
    
    # Transfer reward
    provider_id = task["provider_id"]
    reward = task["reward"]
    if provider_id not in TOKEN_BALANCES:
        TOKEN_BALANCES[provider_id] = 0.0
    TOKEN_BALANCES[provider_id] += reward
    
    task["status"] = "completed"
    task["completed_at"] = datetime.utcnow().isoformat()
    return {"success": True, "task": task, "reward_paid": reward}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
