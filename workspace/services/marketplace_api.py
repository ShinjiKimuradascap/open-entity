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
    version="1.3.0",
    description="AI Task Marketplace and $ENTITY Token Registry - v1.3 Multi-Agent Support"
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


# v1.3 Multi-Agent Marketplace Models
class QuoteRequest(BaseModel):
    service_id: str
    client_id: str
    urgency: int = 1
    custom_requirements: Optional[Dict[str, Any]] = None


class OrderRequest(BaseModel):
    quote_id: str
    client_id: str
    payment_method: str = "escrow"


class DeliverableSubmission(BaseModel):
    order_id: str
    provider_id: str
    deliverable: Dict[str, Any]


class CompletionConfirmation(BaseModel):
    order_id: str
    client_id: str
    rating: Optional[float] = None


class DisputeRequest(BaseModel):
    order_id: str
    initiator_id: str
    reason: str
    evidence: Optional[List[Dict]] = None


# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/")
async def root():
    return {
        "name": "Entity Marketplace API",
        "version": "1.3.0",
        "token": TOKEN_INFO,
        "features": [
            "multi_agent_discovery",
            "dynamic_pricing",
            "escrow_payments",
            "reputation_system",
            "dispute_resolution"
        ],
        "endpoints": {
            "health": "/health",
            "services_v1": "/api/marketplace/services",
            "services_v13": "/api/v1/marketplace/services",
            "quote": "/api/v1/marketplace/quote",
            "order": "/api/v1/marketplace/order",
            "tasks": "/api/tasks",
            "token": "/api/token/info",
            "stats": "/api/v1/marketplace/stats"
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


# v1.3 Multi-Agent Marketplace Endpoints
@app.get("/api/v1/marketplace/stats")
async def marketplace_stats():
    """Get marketplace statistics"""
    from services.multi_agent_marketplace import get_marketplace
    mp = get_marketplace()
    return mp.get_marketplace_stats()


@app.get("/api/v1/marketplace/services")
async def discover_services(
    service_type: Optional[str] = None,
    min_reputation: float = 0.0,
    max_price: Optional[float] = None
):
    """Discover services with filters"""
    from services.marketplace.service_registry import ServiceType
    from services.multi_agent_marketplace import get_marketplace
    
    mp = get_marketplace()
    
    # Convert string to enum
    st = None
    if service_type:
        try:
            st = ServiceType[service_type.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid service type: {service_type}")
    
    max_price_dec = None
    if max_price:
        from decimal import Decimal
        max_price_dec = Decimal(str(max_price))
    
    services = await mp.discover_services(
        service_type=st,
        max_price=max_price_dec,
        min_reputation=min_reputation
    )
    return {"services": services, "count": len(services)}


@app.post("/api/v1/marketplace/quote")
async def request_quote(quote_req: QuoteRequest):
    """Request a quote for a service"""
    from services.multi_agent_marketplace import get_marketplace
    
    mp = get_marketplace()
    quote = await mp.request_quote(
        service_id=quote_req.service_id,
        client_id=quote_req.client_id,
        custom_requirements=quote_req.custom_requirements,
        urgency=quote_req.urgency
    )
    
    if not quote:
        raise HTTPException(status_code=404, detail="Service not found or unavailable")
    
    return quote.to_dict()


@app.post("/api/v1/marketplace/order")
async def place_order(order_req: OrderRequest):
    """Place an order from a quote"""
    from services.multi_agent_marketplace import get_marketplace
    
    mp = get_marketplace()
    order = await mp.place_order(
        quote_id=order_req.quote_id,
        client_id=order_req.client_id,
        payment_method=order_req.payment_method
    )
    
    if not order:
        raise HTTPException(status_code=400, detail="Invalid quote or insufficient funds")
    
    return order.to_dict()


@app.post("/api/v1/marketplace/deliverable")
async def submit_deliverable(submission: DeliverableSubmission):
    """Submit deliverable for an order"""
    from services.multi_agent_marketplace import get_marketplace
    
    mp = get_marketplace()
    success = await mp.submit_deliverable(
        order_id=submission.order_id,
        provider_id=submission.provider_id,
        deliverable=submission.deliverable
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Cannot submit deliverable")
    
    return {"success": True, "message": "Deliverable submitted"}


@app.post("/api/v1/marketplace/complete")
async def confirm_completion(confirmation: CompletionConfirmation):
    """Confirm order completion and release payment"""
    from services.multi_agent_marketplace import get_marketplace
    
    mp = get_marketplace()
    success = await mp.confirm_completion(
        order_id=confirmation.order_id,
        client_id=confirmation.client_id,
        rating=confirmation.rating
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Cannot complete order")
    
    return {"success": True, "message": "Order completed and payment released"}


@app.get("/api/v1/marketplace/agent/{agent_id}/stats")
async def agent_stats(agent_id: str):
    """Get agent statistics"""
    from services.multi_agent_marketplace import get_marketplace
    
    mp = get_marketplace()
    return mp.get_agent_stats(agent_id)


@app.post("/api/v1/marketplace/dispute")
async def open_dispute(dispute_req: DisputeRequest):
    """Open a dispute for an order"""
    from services.multi_agent_marketplace import get_marketplace
    
    mp = get_marketplace()
    dispute = await mp.open_dispute(
        order_id=dispute_req.order_id,
        initiator_id=dispute_req.initiator_id,
        reason=dispute_req.reason,
        evidence=dispute_req.evidence
    )
    
    if not dispute:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return dispute.to_dict()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
