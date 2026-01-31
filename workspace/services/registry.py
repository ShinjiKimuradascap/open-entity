#!/usr/bin/env python3
"""Service Registry - AI service discovery"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta


@dataclass
class ServiceInfo:
    entity_id: str
    entity_name: str
    endpoint: str
    capabilities: List[str]
    registered_at: datetime
    last_heartbeat: datetime
    
    def is_alive(self, timeout_sec: int = 60) -> bool:
        delta = datetime.now(timezone.utc) - self.last_heartbeat
        return delta.seconds < timeout_sec


class ServiceRegistry:
    """Central service registry for AI entities"""
    
    def __init__(self):
        self._services: Dict[str, ServiceInfo] = {}
        
    def register(self, entity_id: str, name: str, endpoint: str, 
                 capabilities: List[str]) -> bool:
        """Register a new service"""
        now = datetime.now(timezone.utc)
        self._services[entity_id] = ServiceInfo(
            entity_id=entity_id,
            entity_name=name,
            endpoint=endpoint,
            capabilities=capabilities,
            registered_at=now,
            last_heartbeat=now
        )
        return True
        
    def unregister(self, entity_id: str) -> bool:
        """Unregister a service"""
        if entity_id in self._services:
            del self._services[entity_id]
            return True
        return False
        
    def heartbeat(self, entity_id: str) -> bool:
        """Update heartbeat timestamp"""
        if entity_id in self._services:
            self._services[entity_id].last_heartbeat = datetime.now(timezone.utc)
            return True
        return False
        
    def find_by_capability(self, capability: str) -> List[ServiceInfo]:
        """Find services by capability"""
        return [
            s for s in self._services.values()
            if capability in s.capabilities and s.is_alive()
        ]
        
    def find_by_id(self, entity_id: str) -> Optional[ServiceInfo]:
        """Find service by ID"""
        return self._services.get(entity_id)
        
    def list_all(self) -> List[ServiceInfo]:
        """List all registered services"""
        return list(self._services.values())
        
    def cleanup_stale(self, timeout_sec: int = 120) -> int:
        """Remove stale services"""
        stale = [
            eid for eid, s in self._services.items()
            if not s.is_alive(timeout_sec)
        ]
        for eid in stale:
            del self._services[eid]
        return len(stale)


# Singleton instance
_registry = ServiceRegistry()


def get_registry() -> ServiceRegistry:
    return _registry


if __name__ == "__main__":
    reg = get_registry()
    reg.register("agent-1", "Coder Agent", "http://localhost:8001", ["code"])
    print(f"Registered: {len(reg.list_all())} services")
