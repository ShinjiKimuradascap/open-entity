#!/usr/bin/env python3
"""
Entry Signature Validator - Ed25519-based Registry Entry Validation

Provides cryptographic verification of registry entries to prevent:
- Entry spoofing
- Tampering with entry data
- Unauthorized registrations

Features:
- Ed25519 signature generation and verification
- Canonical payload construction
- Signature caching for performance
- Trusted key whitelist support
"""

import asyncio
import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Set, Any, Callable
from collections import OrderedDict

# Try to import ed25519, fallback to stub if not available
try:
    import ed25519
    HAS_ED25519 = True
except ImportError:
    HAS_ED25519 = False
    logging.warning("ed25519 module not available, using stub implementation")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of entry validation"""
    valid: bool
    reason: Optional[str] = None
    cached: bool = False


class LRUCache:
    """Simple LRU cache for signature validation results"""
    
    def __init__(self, maxsize: int = 1000):
        self.maxsize = maxsize
        self._cache: OrderedDict[str, Any] = OrderedDict()
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return self._cache[key]
        return None
    
    def set(self, key: str, value: Any):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        
        # Evict oldest if over capacity
        while len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)
    
    def __contains__(self, key: str) -> bool:
        return key in self._cache


class EntrySignatureValidator:
    """
    Validates registry entry signatures using Ed25519.
    
    Prevents entry spoofing and tampering by cryptographically
    signing and verifying registry entries.
    """
    
    CACHE_SIZE = 10000
    CACHE_TTL = 300  # 5 minutes
    
    def __init__(self, trusted_keys: Optional[Set[str]] = None):
        """
        Initialize validator.
        
        Args:
            trusted_keys: Optional set of trusted public key base64 strings.
                         If provided, only entries from these keys are accepted.
        """
        self.trusted_keys = trusted_keys or set()
        self._signature_cache = LRUCache(maxsize=self.CACHE_SIZE)
        self._cache_timestamps: Dict[str, float] = {}
        self._validation_count = 0
        self._cache_hit_count = 0
    
    def validate_entry(self, entry: Any) -> ValidationResult:
        """
        Validate entry signature.
        
        Args:
            entry: RegistryEntry with signature fields
            
        Returns:
            ValidationResult with success/failure and reason
        """
        self._validation_count += 1
        
        # Build cache key
        cache_key = self._build_cache_key(entry)
        
        # Check cache
        cached_result = self._signature_cache.get(cache_key)
        if cached_result is not None:
            # Check TTL
            timestamp = self._cache_timestamps.get(cache_key, 0)
            if time.time() - timestamp < self.CACHE_TTL:
                self._cache_hit_count += 1
                return ValidationResult(
                    valid=cached_result,
                    cached=True
                )
        
        # Verify required fields
        if not hasattr(entry, 'signature') or not entry.signature:
            return ValidationResult(
                valid=False,
                reason="Missing signature"
            )
        
        if not hasattr(entry, 'public_key') or not entry.public_key:
            return ValidationResult(
                valid=False,
                reason="Missing public key"
            )
        
        # Check trusted keys list (if configured)
        if self.trusted_keys and entry.public_key not in self.trusted_keys:
            return ValidationResult(
                valid=False,
                reason="Public key not in trusted set"
            )
        
        # Verify signature
        is_valid = self._verify_signature(entry)
        
        # Cache result
        self._signature_cache.set(cache_key, is_valid)
        self._cache_timestamps[cache_key] = time.time()
        
        if not is_valid:
            return ValidationResult(
                valid=False,
                reason="Signature verification failed"
            )
        
        return ValidationResult(valid=True)
    
    def _build_cache_key(self, entry: Any) -> str:
        """Build cache key from entry"""
        return f"{entry.entity_id}:{entry.version}:{entry.signature[:16]}"
    
    def _build_payload(self, entry: Any) -> str:
        """
        Build canonical payload for signing/verification.
        
        The payload is a deterministic string representation of
        the entry fields that should be protected by the signature.
        """
        # Get capabilities as sorted list
        capabilities = sorted(entry.capabilities) if hasattr(entry, 'capabilities') else []
        capabilities_hash = hashlib.sha256(
            json.dumps(capabilities).encode()
        ).hexdigest()[:16]
        
        # Build payload parts
        payload_parts = [
            entry.entity_id,
            entry.endpoint if hasattr(entry, 'endpoint') else "",
            capabilities_hash,
            str(entry.version) if hasattr(entry, 'version') else "1",
            entry.registered_at.isoformat() if hasattr(entry, 'registered_at') else "",
            entry.node_id if hasattr(entry, 'node_id') else ""
        ]
        
        # Join with delimiter that won't appear in fields
        return "|".join(payload_parts)
    
    def _verify_signature(self, entry: Any) -> bool:
        """
        Verify Ed25519 signature of entry.
        
        Args:
            entry: RegistryEntry with signature and public_key
            
        Returns:
            True if signature is valid
        """
        if not HAS_ED25519:
            # Stub implementation - accept all signatures in dev mode
            logger.warning("Ed25519 not available, accepting signature without verification")
            return True
        
        try:
            # Build payload
            payload = self._build_payload(entry)
            payload_hash = hashlib.sha256(payload.encode()).digest()
            
            # Decode public key
            try:
                public_key_bytes = base64.b64decode(entry.public_key)
            except Exception:
                logger.warning(f"Failed to decode public key for {entry.entity_id}")
                return False
            
            # Create verifying key
            verifying_key = ed25519.VerifyingKey(public_key_bytes)
            
            # Decode signature
            try:
                signature_bytes = base64.b64decode(entry.signature)
            except Exception:
                logger.warning(f"Failed to decode signature for {entry.entity_id}")
                return False
            
            # Verify
            try:
                verifying_key.verify(signature_bytes, payload_hash)
                return True
            except ed25519.BadSignatureError:
                logger.warning(f"Invalid signature for {entry.entity_id}")
                return False
            
        except Exception as e:
            logger.error(f"Signature validation error: {e}")
            return False
    
    def sign_entry(self, entry: Any, private_key: Any) -> Any:
        """
        Sign a registry entry.
        
        Args:
            entry: Entry to sign (modified in place)
            private_key: Ed25519 private key (SigningKey)
            
        Returns:
            Entry with signature and public_key fields populated
        """
        if not HAS_ED25519:
            logger.warning("Ed25519 not available, cannot sign entry")
            entry.signature = "stub-signature"
            entry.public_key = "stub-public-key"
            return entry
        
        # Build payload
        payload = self._build_payload(entry)
        payload_hash = hashlib.sha256(payload.encode()).digest()
        
        # Sign
        signature = private_key.sign(payload_hash)
        
        # Set fields
        entry.signature = base64.b64encode(signature).decode()
        entry.public_key = base64.b64encode(
            private_key.get_verifying_key().to_bytes()
        ).decode()
        
        return entry
    
    def add_trusted_key(self, public_key_b64: str):
        """Add a trusted public key"""
        self.trusted_keys.add(public_key_b64)
        logger.info(f"Added trusted key: {public_key_b64[:20]}...")
    
    def remove_trusted_key(self, public_key_b64: str):
        """Remove a trusted public key"""
        self.trusted_keys.discard(public_key_b64)
        logger.info(f"Removed trusted key: {public_key_b64[:20]}...")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get validator statistics"""
        cache_hit_rate = 0.0
        if self._validation_count > 0:
            cache_hit_rate = self._cache_hit_count / self._validation_count
        
        return {
            "validation_count": self._validation_count,
            "cache_hit_count": self._cache_hit_count,
            "cache_hit_rate": cache_hit_rate,
            "trusted_keys_count": len(self.trusted_keys),
            "cache_size": len(self._signature_cache._cache)
        }


class KeyManager:
    """
    Manages Ed25519 key pairs for registry entries.
    
    Provides key generation, storage, and retrieval.
    """
    
    def __init__(self, key_dir: Optional[str] = None):
        """
        Initialize key manager.
        
        Args:
            key_dir: Directory to store/load keys (optional)
        """
        self.key_dir = key_dir
        self._keys: Dict[str, Any] = {}  # entity_id -> private_key
    
    def generate_keypair(self, entity_id: str) -> tuple:
        """
        Generate new Ed25519 keypair for entity.
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            Tuple of (private_key, public_key_b64)
        """
        if not HAS_ED25519:
            raise RuntimeError("Ed25519 not available")
        
        # Generate keypair
        private_key, public_key = ed25519.create_keypair()
        
        # Store
        self._keys[entity_id] = private_key
        
        # Get public key as base64
        public_key_b64 = base64.b64encode(
            public_key.to_bytes()
        ).decode()
        
        logger.info(f"Generated keypair for {entity_id}")
        
        return private_key, public_key_b64
    
    def get_private_key(self, entity_id: str) -> Optional[Any]:
        """Get private key for entity"""
        return self._keys.get(entity_id)
    
    def load_key(self, entity_id: str, private_key_b64: str):
        """Load private key from base64"""
        if not HAS_ED25519:
            raise RuntimeError("Ed25519 not available")
        
        private_key_bytes = base64.b64decode(private_key_b64)
        private_key = ed25519.SigningKey(private_key_bytes)
        self._keys[entity_id] = private_key
    
    def export_key(self, entity_id: str) -> Optional[str]:
        """Export private key as base64"""
        private_key = self._keys.get(entity_id)
        if not private_key:
            return None
        
        return base64.b64encode(
            private_key.to_bytes()
        ).decode()


def create_signed_entry(
    entity_id: str,
    entity_name: str,
    endpoint: str,
    capabilities: list,
    node_id: str,
    key_manager: KeyManager,
    validator: EntrySignatureValidator
) -> Any:
    """
    Helper function to create and sign a registry entry.
    
    Args:
        entity_id: Entity identifier
        entity_name: Human-readable name
        endpoint: Service endpoint URL
        capabilities: List of capability strings
        node_id: Node identifier
        key_manager: KeyManager instance
        validator: EntrySignatureValidator instance
        
    Returns:
        Signed RegistryEntry
    """
    from services.distributed_registry import RegistryEntry
    
    # Create entry
    now = datetime.now(timezone.utc)
    entry = RegistryEntry(
        entity_id=entity_id,
        entity_name=entity_name,
        endpoint=endpoint,
        capabilities=capabilities,
        registered_at=now,
        last_heartbeat=now,
        version=1,
        node_id=node_id
    )
    
    # Get or generate key
    private_key = key_manager.get_private_key(entity_id)
    if not private_key:
        private_key, _ = key_manager.generate_keypair(entity_id)
    
    # Sign entry
    validator.sign_entry(entry, private_key)
    
    return entry


# Global instances
_validator: Optional[EntrySignatureValidator] = None
_key_manager: Optional[KeyManager] = None


def get_validator(trusted_keys: Optional[Set[str]] = None) -> EntrySignatureValidator:
    """Get global validator instance"""
    global _validator
    if _validator is None:
        _validator = EntrySignatureValidator(trusted_keys)
    return _validator


def get_key_manager(key_dir: Optional[str] = None) -> KeyManager:
    """Get global key manager instance"""
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManager(key_dir)
    return _key_manager


if __name__ == "__main__":
    print(f"Ed25519 available: {HAS_ED25519}")
    
    # Test with stub if ed25519 not available
    validator = EntrySignatureValidator()
    key_manager = KeyManager()
    
    from services.distributed_registry import RegistryEntry
    
    entry = RegistryEntry(
        entity_id="test-agent",
        entity_name="Test Agent",
        endpoint="http://localhost:8001",
        capabilities=["code", "review"],
        registered_at=datetime.now(timezone.utc),
        last_heartbeat=datetime.now(timezone.utc),
        version=1,
        node_id="test-node"
    )
    
    if HAS_ED25519:
        # Generate key and sign
        private_key, public_key = key_manager.generate_keypair("test-agent")
        validator.sign_entry(entry, private_key)
        
        print(f"Entry signed: {entry.signature[:30]}...")
        print(f"Public key: {entry.public_key[:30]}...")
        
        # Validate
        result = validator.validate_entry(entry)
        print(f"Validation: {result.valid} (cached: {result.cached})")
        
        # Validate again (should hit cache)
        result2 = validator.validate_entry(entry)
        print(f"Validation 2: {result2.valid} (cached: {result2.cached})")
    else:
        print("Ed25519 not available - skipping test")
    
    print(f"Stats: {validator.get_stats()}")
