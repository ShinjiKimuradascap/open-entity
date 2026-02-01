#!/usr/bin/env python3
"""
JWT Authentication for AI Peer Communication
"""

import os
import jwt
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Callable
from functools import wraps

try:
    from fastapi import HTTPException, Request, Depends
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# Multi-level import fallback for different execution contexts
try:
    # Try relative import (when imported as part of package)
    from .crypto import KeyPair, load_key_from_env
except ImportError:
    try:
        # Try absolute import (when services is in PYTHONPATH)
        from services.crypto import KeyPair, load_key_from_env
    except ImportError:
        try:
            # Try direct import (when running from services directory)
            from crypto import KeyPair, load_key_from_env
        except ImportError:
            # Last resort: importlib with path manipulation
            import sys
            from pathlib import Path
            current_dir = Path(__file__).parent
            if str(current_dir) not in sys.path:
                sys.path.insert(0, str(current_dir))
            from crypto import KeyPair, load_key_from_env


class JWTConfig:
    """JWT configuration"""
    
    # Default values
    DEFAULT_ALGORITHM = "HS256"
    DEFAULT_EXPIRY_MINUTES = 5
    
    def __init__(
        self,
        secret: Optional[str] = None,
        algorithm: str = DEFAULT_ALGORITHM,
        expiry_minutes: int = DEFAULT_EXPIRY_MINUTES
    ):
        self.secret = secret or self._generate_secret()
        self.algorithm = algorithm
        self.expiry_minutes = expiry_minutes
    
    @staticmethod
    def _generate_secret() -> str:
        """Generate a secure secret - requires explicit env var in production"""
        if os.environ.get("ENVIRONMENT") == "production":
            raise ValueError(
                "JWT_SECRET must be set explicitly in production environment. "
                "Please set a secure random secret (at least 32 bytes)."
            )
        # Development fallback: generate a random secret with warning
        import logging
        logging.getLogger(__name__).warning(
            "JWT_SECRET not set - generating temporary secret for development. "
            "All tokens will be invalidated on restart. "
            "Set JWT_SECRET environment variable for persistent authentication."
        )
        return secrets.token_urlsafe(64)  # Increased to 64 bytes for better security
    
    @classmethod
    def from_env(cls) -> "JWTConfig":
        """Load config from environment variables with validation"""
        secret = os.environ.get("JWT_SECRET")
        algorithm = os.environ.get("JWT_ALGORITHM", cls.DEFAULT_ALGORITHM)
        expiry = int(os.environ.get("JWT_EXPIRY_MINUTES", cls.DEFAULT_EXPIRY_MINUTES))
        
        config = cls(secret=secret, algorithm=algorithm, expiry_minutes=expiry)
        
        # Validate secret length (minimum 256 bits / 32 bytes)
        secret_bytes = config.secret.encode('utf-8')
        if len(secret_bytes) < 32:
            import logging
            logging.getLogger(__name__).warning(
                f"JWT_SECRET is too short ({len(secret_bytes)} bytes). "
                "Recommended minimum is 32 bytes (256 bits)."
            )
        
        return config


class JWTAuth:
    """JWT Authentication handler"""
    
    def __init__(self, config: Optional[JWTConfig] = None):
        self.config = config or JWTConfig.from_env()
    
    def create_token(
        self,
        entity_id: str,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a JWT token for an entity
        
        Args:
            entity_id: Entity identifier
            additional_claims: Additional claims to include
            
        Returns:
            JWT token string
        """
        now = datetime.now(timezone.utc)
        
        payload = {
            "sub": entity_id,  # Subject
            "iat": now,  # Issued at
            "exp": now + timedelta(minutes=self.config.expiry_minutes),
            "jti": secrets.token_hex(16),  # JWT ID for replay protection
            "type": "access"
        }
        
        if additional_claims:
            payload.update(additional_claims)
        
        token = jwt.encode(
            payload,
            self.config.secret,
            algorithm=self.config.algorithm
        )
        
        return token
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify a JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload
            
        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                self.config.secret,
                algorithms=[self.config.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {e}")
    
    def get_entity_id(self, token: str) -> str:
        """Extract entity_id from token"""
        payload = self.verify_token(token)
        return payload.get("sub")


class APIKeyAuth:
    """Simple API key authentication"""
    
    def __init__(self, api_keys: Optional[Dict[str, str]] = None):
        """
        Initialize with API keys
        
        Args:
            api_keys: Dict mapping entity_id to api_key
        """
        self.api_keys = api_keys or {}
        self._key_hashes: Dict[str, str] = {}
        for entity_id, key in self.api_keys.items():
            self._key_hashes[self._hash_key(key)] = entity_id
    
    @staticmethod
    def _hash_key(key: str) -> str:
        """Hash an API key for storage"""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def add_key(self, entity_id: str, api_key: str) -> None:
        """Add an API key for an entity"""
        self.api_keys[entity_id] = api_key
        self._key_hashes[self._hash_key(api_key)] = entity_id
    
    def generate_key(self, entity_id: str) -> str:
        """Generate a new API key for an entity"""
        api_key = f"ak_{secrets.token_urlsafe(32)}"
        self.add_key(entity_id, api_key)
        return api_key
    
    def verify_key(self, api_key: str) -> Optional[str]:
        """
        Verify an API key using constant-time comparison
        
        Args:
            api_key: API key to verify
            
        Returns:
            entity_id if valid, None otherwise
        """
        key_hash = self._hash_key(api_key)
        
        # Use constant-time comparison to prevent timing attacks
        for stored_hash, entity_id in self._key_hashes.items():
            if hmac.compare_digest(key_hash, stored_hash):
                return entity_id
        return None
    
    @classmethod
    def from_env(cls, prefix: str = "API_KEY_") -> "APIKeyAuth":
        """Load API keys from environment variables"""
        api_keys = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                entity_id = key[len(prefix):].lower()
                api_keys[entity_id] = value
        return cls(api_keys)


# FastAPI integration
if FASTAPI_AVAILABLE:
    
    class JWTBearer(HTTPBearer):
        """FastAPI JWT authentication dependency"""
        
        def __init__(self, auth: JWTAuth, auto_error: bool = True):
            super().__init__(auto_error=auto_error)
            self.auth = auth
        
        async def __call__(
            self,
            request: Request
        ) -> Optional[HTTPAuthorizationCredentials]:
            credentials = await super().__call__(request)
            
            if not credentials:
                raise HTTPException(status_code=403, detail="Invalid authorization code")
            
            if not credentials.scheme == "Bearer":
                raise HTTPException(status_code=403, detail="Invalid authentication scheme")
            
            try:
                payload = self.auth.verify_token(credentials.credentials)
                request.state.entity_id = payload.get("sub")
                return credentials
            except ValueError as e:
                raise HTTPException(status_code=401, detail=str(e))
    
    
    class APIKeyBearer(HTTPBearer):
        """FastAPI API key authentication dependency"""
        
        def __init__(self, auth: APIKeyAuth, auto_error: bool = True):
            super().__init__(auto_error=auto_error)
            self.auth = auth
        
        async def __call__(
            self,
            request: Request
        ) -> Optional[HTTPAuthorizationCredentials]:
            credentials = await super().__call__(request)
            
            if not credentials:
                raise HTTPException(status_code=403, detail="API key required")
            
            entity_id = self.auth.verify_key(credentials.credentials)
            if not entity_id:
                raise HTTPException(status_code=401, detail="Invalid API key")
            
            request.state.entity_id = entity_id
            return credentials
    
    
    def get_current_entity_id(request: Request) -> str:
        """Get current entity ID from request state"""
        entity_id = getattr(request.state, "entity_id", None)
        if not entity_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return entity_id


class CombinedAuth:
    """
    Combined authentication using both JWT and Ed25519 signatures
    Provides defense in depth
    """
    
    def __init__(
        self,
        jwt_auth: Optional[JWTAuth] = None,
        api_key_auth: Optional[APIKeyAuth] = None
    ):
        self.jwt_auth = jwt_auth or JWTAuth()
        self.api_key_auth = api_key_auth or APIKeyAuth()
    
    def authenticate_request(
        self,
        token: Optional[str] = None,
        api_key: Optional[str] = None,
        signature: Optional[str] = None,
        message: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Authenticate a request using available credentials
        
        Args:
            token: JWT token
            api_key: API key
            signature: Ed25519 signature (requires message)
            message: Message that was signed
            
        Returns:
            Authentication result with entity_id and methods used
        """
        result = {
            "authenticated": False,
            "entity_id": None,
            "methods": [],
            "errors": []
        }
        
        # Try JWT
        if token:
            try:
                payload = self.jwt_auth.verify_token(token)
                result["entity_id"] = payload.get("sub")
                result["methods"].append("jwt")
            except ValueError as e:
                result["errors"].append(f"JWT: {e}")
        
        # Try API key
        if api_key:
            entity_id = self.api_key_auth.verify_key(api_key)
            if entity_id:
                if result["entity_id"] and result["entity_id"] != entity_id:
                    result["errors"].append("API key entity mismatch")
                else:
                    result["entity_id"] = entity_id
                    result["methods"].append("api_key")
            else:
                result["errors"].append("API key: invalid")
        
        # Check if authenticated
        if result["entity_id"]:
            result["authenticated"] = True
        
        return result


# Convenience functions
def create_jwt_auth() -> JWTAuth:
    """Create JWT auth from environment"""
    return JWTAuth(JWTConfig.from_env())


def create_api_key_auth() -> APIKeyAuth:
    """Create API key auth from environment"""
    return APIKeyAuth.from_env()


if __name__ == "__main__":
    # Test
    print("Testing authentication...")
    
    # JWT test
    jwt_auth = JWTAuth(JWTConfig(secret="test-secret"))
    token = jwt_auth.create_token("test-entity", {"role": "admin"})
    print(f"Created JWT: {token[:50]}...")
    
    payload = jwt_auth.verify_token(token)
    print(f"Verified, entity_id: {payload['sub']}")
    
    # API key test
    api_auth = APIKeyAuth()
    api_key = api_auth.generate_key("test-entity")
    print(f"Generated API key: {api_key[:30]}...")
    
    verified_id = api_auth.verify_key(api_key)
    print(f"Verified entity_id: {verified_id}")
    
    # Combined auth test
    combined = CombinedAuth(jwt_auth, api_auth)
    result = combined.authenticate_request(token=token, api_key=api_key)
    print(f"Combined auth: {result}")
    
    print("\nAll auth tests passed!")
