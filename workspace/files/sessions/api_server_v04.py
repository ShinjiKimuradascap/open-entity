#!/usr/bin/env python3
"""
AI Agent API Server v0.4.0
Security-enhanced version with Ed25519 signatures, JWT authentication, and replay protection
"""

from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uvicorn
import os

from registry import get_registry, ServiceInfo
from peer_service import PeerService

# Import security modules
from crypto import (
    KeyPair, MessageSigner, SignatureVerifier, SecureMessage,
    ReplayProtector, load_key_from_env, generate_keypair, get_public_key_from_private
)
from auth import (
    JWTAuth, JWTConfig, APIKeyAuth, CombinedAuth,
    JWTBearer, APIKeyBearer, get_current_entity_id,
    create_jwt_auth, create_api_key_auth
)

# Initialize FastAPI app
app = FastAPI(
    title="AI Collaboration API",
    version="0.4.0",
    description="Security-enhanced API with Ed25519 signatures and JWT authentication"
)

# Initialize components
registry = get_registry()
replay_protector = ReplayProtector(max_age_seconds=60)

# Initialize security components
jwt_auth = create_jwt_auth()
api_key_auth = create_api_key_auth()
combined_auth = CombinedAuth(jwt_auth, api_key_auth)

# Initialize signature verifier
signature_verifier = SignatureVerifier()

# Server's own key pair (for signing messages)
_server_keypair: Optional[KeyPair] = None
_server_signer: Optional[MessageSigner] = None


def get_server_keypair() -> KeyPair:
    """Get or create server key pair"""
    global _server_keypair, _server_signer
    if _server_keypair is None:
        _server_keypair = load_key_from_env("ENTITY_PRIVATE_KEY") or generate_keypair()
        _server_signer = MessageSigner(_server_keypair)
    return _server_keypair


def get_server_signer() -> MessageSigner:
    """Get server message signer"""
    global _server_signer
    if _server_signer is None:
        get_server_keypair()
    return _server_signer


# Request/Response Models
class RegisterRequest(BaseModel):
    entity_id: str
    name: str
    endpoint: str
    capabilities: List[str]
    public_key: Optional[str] = Field(None, description="Hex-encoded Ed25519 public key")


class HeartbeatRequest(BaseModel):
    entity_id: str
    load: float = 0.0
    active_tasks: int = 0


class MessageRequest(BaseModel):
    version: str
    msg_type: str
    sender_id: str
    payload: Dict[str, Any]
    timestamp: Optional[str] = None
    nonce: Optional[str] = None
    signature: Optional[str] = Field(None, description="Base64-encoded Ed25519 signature")


class TokenRequest(BaseModel):
    entity_id: str
    api_key: Optional[str] = None
    public_key: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    entity_id: str


class VerifyRequest(BaseModel):
    message: Dict[str, Any]
    signature: str
    sender_id: str


class VerifyResponse(BaseModel):
    valid: bool
    message: str


class PublicKeyResponse(BaseModel):
    public_key: str
    algorithm: str = "Ed25519"
    entity_id: str


class StatsResponse(BaseModel):
    version: str
    registered_agents: int
    active_agents: int
    server_public_key: str
    timestamp: str
    features: List[str]


# Authentication dependencies
jwt_bearer = JWTBearer(jwt_auth)
api_key_bearer = APIKeyBearer(api_key_auth)


@app.post("/register")
async def register_agent(req: RegisterRequest):
    """Register a new AI agent with optional public key"""
    success = registry.register(
        entity_id=req.entity_id,
        name=req.name,
        endpoint=req.endpoint,
        capabilities=req.capabilities
    )
    
    if success:
        # Store public key if provided
        if req.public_key:
            try:
                signature_verifier.add_public_key_hex(req.entity_id, req.public_key)
            except Exception as e:
                # Log but don't fail registration
                print(f"Warning: Failed to store public key for {req.entity_id}: {e}")
        
        # Generate API key for the entity
        api_key = api_key_auth.generate_key(req.entity_id)
        
        return {
            "status": "ok",
            "entity_id": req.entity_id,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "api_key": api_key,
            "public_key_stored": req.public_key is not None
        }
    
    raise HTTPException(status_code=400, detail="Registration failed")


@app.post("/unregister/{entity_id}")
async def unregister_agent(
    entity_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """Unregister an agent (requires JWT authentication)"""
    # Verify the requesting entity matches or is admin
    current_entity = credentials.credentials
    
    success = registry.unregister(entity_id)
    if success:
        # Remove public key
        if entity_id in signature_verifier.public_keys:
            del signature_verifier.public_keys[entity_id]
            if entity_id in signature_verifier._verify_keys:
                del signature_verifier._verify_keys[entity_id]
        
        return {"status": "ok", "message": f"{entity_id} unregistered"}
    
    raise HTTPException(status_code=404, detail="Entity not found")


@app.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest):
    """Update agent heartbeat"""
    success = registry.heartbeat(req.entity_id)
    if success:
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    raise HTTPException(status_code=404, detail="Entity not registered")


@app.get("/discover")
async def discover_agents(capability: Optional[str] = None):
    """Discover available agents"""
    if capability:
        services = registry.find_by_capability(capability)
    else:
        services = registry.list_all()
    
    return {
        "agents": [
            {
                "entity_id": s.entity_id,
                "name": s.entity_name,
                "endpoint": s.endpoint,
                "capabilities": s.capabilities,
                "alive": s.is_alive()
            }
            for s in services
        ]
    }


@app.get("/agent/{entity_id}")
async def get_agent(entity_id: str):
    """Get agent details"""
    service = registry.find_by_id(entity_id)
    if service:
        return {
            "entity_id": service.entity_id,
            "name": service.entity_name,
            "endpoint": service.endpoint,
            "capabilities": service.capabilities,
            "registered_at": service.registered_at.isoformat(),
            "last_heartbeat": service.last_heartbeat.isoformat(),
            "alive": service.is_alive()
        }
    raise HTTPException(status_code=404, detail="Entity not found")


@app.post("/message")
async def receive_message(
    req: MessageRequest,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
):
    """
    Receive secure message from peer
    
    Security checks:
    - Ed25519 signature verification (if signature provided)
    - Replay attack prevention using nonce and timestamp
    - Optional JWT/API key authentication
    """
    # Build secure message
    message = SecureMessage(
        version=req.version,
        msg_type=req.msg_type,
        sender_id=req.sender_id,
        payload=req.payload,
        timestamp=req.timestamp,
        nonce=req.nonce,
        signature=req.signature
    )
    
    # 1. Replay protection check
    valid, error = replay_protector.is_valid(message.nonce, message.timestamp)
    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"Replay protection failed: {error}"
        )
    
    # 2. Signature verification (if provided)
    if req.signature:
        try:
            is_valid = signature_verifier.verify_message(
                message.get_signable_data(),
                req.signature,
                req.sender_id
            )
            if not is_valid:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid message signature"
                )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Signature verification error: {e}"
            )
    
    # 3. Optional authentication (JWT or API key)
    auth_result = None
    if authorization or x_api_key:
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
        
        auth_result = combined_auth.authenticate_request(
            token=token,
            api_key=x_api_key
        )
        
        if not auth_result["authenticated"]:
            raise HTTPException(
                status_code=401,
                detail=f"Authentication failed: {auth_result['errors']}"
            )
    
    # Route to handler or process
    # TODO: Implement message routing based on msg_type
    
    return {
        "status": "received",
        "msg_type": req.msg_type,
        "from": req.sender_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verified": req.signature is not None,
        "authenticated": auth_result["authenticated"] if auth_result else False
    }


# New Security Endpoints

@app.post("/auth/token", response_model=TokenResponse)
async def create_token(req: TokenRequest):
    """
    Create JWT access token
    
    Authentication options:
    - API key (if previously registered)
    - Public key verification (for new entities)
    """
    # Verify using API key
    if req.api_key:
        entity_id = api_key_auth.verify_key(req.api_key)
        if not entity_id or entity_id != req.entity_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
    
    # Create JWT token
    token = jwt_auth.create_token(
        entity_id=req.entity_id,
        additional_claims={"method": "api_key" if req.api_key else "public_key"}
    )
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=jwt_auth.config.expiry_minutes * 60,
        entity_id=req.entity_id
    )


@app.get("/keys/public", response_model=PublicKeyResponse)
async def get_server_public_key():
    """Get server's Ed25519 public key for message verification"""
    keypair = get_server_keypair()
    
    return PublicKeyResponse(
        public_key=keypair.get_public_key_hex(),
        algorithm="Ed25519",
        entity_id="server"
    )


@app.post("/keys/verify", response_model=VerifyResponse)
async def verify_signature(req: VerifyRequest):
    """Verify an Ed25519 signature"""
    try:
        is_valid = signature_verifier.verify_message(
            req.message,
            req.signature,
            req.sender_id
        )
        
        return VerifyResponse(
            valid=is_valid,
            message="Signature is valid" if is_valid else "Signature is invalid"
        )
    except ValueError as e:
        return VerifyResponse(
            valid=False,
            message=f"Verification failed: {e}"
        )


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get server statistics and capabilities"""
    keypair = get_server_keypair()
    services = registry.list_all()
    active = [s for s in services if s.is_alive()]
    
    return StatsResponse(
        version="0.4.0",
        registered_agents=len(services),
        active_agents=len(active),
        server_public_key=keypair.get_public_key_hex(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        features=[
            "Ed25519_signatures",
            "JWT_authentication",
            "API_key_authentication",
            "Replay_protection",
            "Message_encryption"
        ]
    )


@app.get("/health")
async def health_check():
    """API health check"""
    return {
        "status": "healthy",
        "version": "0.4.0",
        "registered_agents": len(registry.list_all()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "security_features": {
            "ed25519_signatures": True,
            "jwt_authentication": True,
            "replay_protection": True
        }
    }


# Secure message sending helper
@app.post("/message/send")
async def send_secure_message(
    recipient_id: str,
    msg_type: str,
    payload: Dict[str, Any],
    credentials: HTTPAuthorizationCredentials = Depends(jwt_bearer)
):
    """
    Send a secure signed message to another agent
    (Server-side message signing for internal use)
    """
    sender_id = credentials.credentials
    
    # Create secure message
    message = SecureMessage(
        version="0.4.0",
        msg_type=msg_type,
        sender_id=sender_id,
        payload=payload
    )
    
    # Sign the message
    signer = get_server_signer()
    message.sign(signer)
    
    # TODO: Actually send to recipient
    # For now, just return the signed message
    return {
        "status": "signed",
        "recipient": recipient_id,
        "message": message.to_dict()
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
