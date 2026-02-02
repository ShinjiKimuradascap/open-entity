#!/usr/bin/env python3
"""
Free Quota System
Open Entity Charter v0.2 準拠の無料枠管理システム

Features:
- First 3 tasks fee-free (max 100 AIC per task)
- Sybil attack prevention via IP-based detection
- Progressive quota for proven entities
- Automatic transition to normal rate after quota exhaustion
"""

import json
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

# Constants per Charter v0.2
FREE_TASKS_LIMIT = 3
MAX_AIC_PER_FREE_TASK = 100
PROGRESSIVE_MULTIPLIER = 1.5  # Proven entities get 1.5x quota


class QuotaStatus(Enum):
    """Quota usage status"""
    ACTIVE = "active"           # Within free quota
    EXHAUSTED = "exhausted"     # Free quota used up
    PROGRESSIVE = "progressive" # Extended quota for proven entities
    SUSPICIOUS = "suspicious"   # Potential Sybil attack detected


@dataclass
class FreeQuotaRecord:
    """Entity's free quota usage record"""
    entity_id: str
    tasks_used: int = 0
    total_aic_used: float = 0.0
    ip_addresses: List[str] = field(default_factory=list)
    first_task_at: Optional[str] = None
    last_task_at: Optional[str] = None
    status: QuotaStatus = QuotaStatus.ACTIVE
    trust_score: float = 0.0  # 0-100, affects progressive quota
    extended_quota: int = 0   # Additional tasks for proven entities
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "tasks_used": self.tasks_used,
            "total_aic_used": self.total_aic_used,
            "ip_addresses": self.ip_addresses,
            "first_task_at": self.first_task_at,
            "last_task_at": self.last_task_at,
            "status": self.status.value,
            "trust_score": self.trust_score,
            "extended_quota": self.extended_quota
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FreeQuotaRecord":
        return cls(
            entity_id=data["entity_id"],
            tasks_used=data.get("tasks_used", 0),
            total_aic_used=data.get("total_aic_used", 0.0),
            ip_addresses=data.get("ip_addresses", []),
            first_task_at=data.get("first_task_at"),
            last_task_at=data.get("last_task_at"),
            status=QuotaStatus(data.get("status", "active")),
            trust_score=data.get("trust_score", 0.0),
            extended_quota=data.get("extended_quota", 0)
        )
    
    @property
    def remaining_tasks(self) -> int:
        """Calculate remaining free tasks"""
        base_quota = FREE_TASKS_LIMIT + self.extended_quota
        return max(0, base_quota - self.tasks_used)
    
    @property
    def is_eligible_for_free(self) -> bool:
        """Check if entity is eligible for free tasks"""
        return self.remaining_tasks > 0 and self.status != QuotaStatus.SUSPICIOUS


@dataclass
class SybilDetectionRule:
    """Sybil attack detection rule"""
    name: str
    threshold: int
    action: str  # "flag", "block", "review"
    description: str


class FreeQuotaManager:
    """
    Manages free quota for external AI entities
    - Tracks usage per entity
    - Prevents Sybil attacks
    - Grants progressive quotas
    """
    
    DATA_DIR = Path("data/free_quota")
    RECORDS_FILE = DATA_DIR / "quota_records.json"
    IP_MAP_FILE = DATA_DIR / "ip_to_entities.json"
    AUDIT_LOG_FILE = DATA_DIR / "audit_log.json"
    
    # Sybil detection rules per Charter v0.2
    SYBIL_RULES = [
        SybilDetectionRule(
            name="multi_entity_per_ip",
            threshold=3,
            action="flag",
            description="Multiple entities from same IP"
        ),
        SybilDetectionRule(
            name="rapid_fire_tasks",
            threshold=5,
            action="block",
            description="Too many tasks in short time"
        ),
        SybilDetectionRule(
            name="low_trust_cluster",
            threshold=5,
            action="review",
            description="Cluster of low-trust entities"
        )
    ]
    
    def __init__(self):
        self._records: Dict[str, FreeQuotaRecord] = {}
        self._ip_map: Dict[str, List[str]] = {}  # IP -> list of entity IDs
        self._audit_log: List[Dict] = []
        self._ensure_data_dir()
        self._load()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load persisted data"""
        if self.RECORDS_FILE.exists():
            try:
                with open(self.RECORDS_FILE, 'r') as f:
                    data = json.load(f)
                    self._records = {
                        k: FreeQuotaRecord.from_dict(v) 
                        for k, v in data.items()
                    }
                logger.info(f"Loaded {len(self._records)} quota records")
            except Exception as e:
                logger.error(f"Failed to load quota records: {e}")
        
        if self.IP_MAP_FILE.exists():
            try:
                with open(self.IP_MAP_FILE, 'r') as f:
                    self._ip_map = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load IP map: {e}")
        
        if self.AUDIT_LOG_FILE.exists():
            try:
                with open(self.AUDIT_LOG_FILE, 'r') as f:
                    self._audit_log = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load audit log: {e}")
    
    def _save(self):
        """Persist data"""
        try:
            with open(self.RECORDS_FILE, 'w') as f:
                json.dump(
                    {k: v.to_dict() for k, v in self._records.items()}, 
                    f, 
                    indent=2
                )
            
            with open(self.IP_MAP_FILE, 'w') as f:
                json.dump(self._ip_map, f, indent=2)
            
            with open(self.AUDIT_LOG_FILE, 'w') as f:
                json.dump(self._audit_log, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save quota data: {e}")
    
    def _log_audit(self, action: str, entity_id: str, details: Dict):
        """Log audit event"""
        self._audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "entity_id": entity_id,
            "details": details
        })
        # Keep last 1000 entries
        self._audit_log = self._audit_log[-1000:]
        self._save()
    
    def get_or_create_record(self, entity_id: str) -> FreeQuotaRecord:
        """Get existing record or create new one"""
        if entity_id not in self._records:
            self._records[entity_id] = FreeQuotaRecord(entity_id=entity_id)
            self._save()
        return self._records[entity_id]
    
    def check_sybil_risk(self, entity_id: str, ip_address: str) -> Tuple[bool, str]:
        """
        Check for Sybil attack indicators
        Returns: (is_safe, reason)
        """
        # Check 1: Multiple entities per IP
        entities_from_ip = self._ip_map.get(ip_address, [])
        if len(entities_from_ip) >= 3 and entity_id not in entities_from_ip:
            return False, f"IP {ip_address} already has {len(entities_from_ip)} entities"
        
        # Check 2: Rapid task creation
        record = self.get_or_create_record(entity_id)
        if record.last_task_at:
            last_task = datetime.fromisoformat(record.last_task_at)
            time_since_last = datetime.now(timezone.utc) - last_task
            if time_since_last < timedelta(seconds=10):
                return False, "Tasks created too rapidly"
        
        return True, "No Sybil indicators detected"
    
    def use_free_quota(
        self, 
        entity_id: str, 
        aic_amount: float,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Attempt to use free quota for a task
        
        Returns: (success, details)
        - success: True if free quota was used
        - details: includes remaining_tasks, status, message
        """
        record = self.get_or_create_record(entity_id)
        
        # Check Sybil risk
        if ip_address:
            is_safe, reason = self.check_sybil_risk(entity_id, ip_address)
            if not is_safe:
                record.status = QuotaStatus.SUSPICIOUS
                self._save()
                self._log_audit("sybil_flagged", entity_id, {"reason": reason})
                return False, {
                    "success": False,
                    "reason": reason,
                    "status": "suspicious",
                    "message": "Account flagged for review"
                }
        
        # Check eligibility
        if not record.is_eligible_for_free:
            status_msg = "exhausted" if record.status == QuotaStatus.EXHAUSTED else "flagged"
            return False, {
                "success": False,
                "reason": f"Free quota {status_msg}",
                "status": record.status.value,
                "remaining_tasks": 0,
                "message": "Free quota exhausted. Normal rates apply."
            }
        
        # Check max AIC per task
        if aic_amount > MAX_AIC_PER_FREE_TASK:
            return False, {
                "success": False,
                "reason": f"Task value exceeds max free task value ({MAX_AIC_PER_FREE_TASK} AIC)",
                "status": record.status.value,
                "remaining_tasks": record.remaining_tasks,
                "message": f"Tasks over {MAX_AIC_PER_FREE_TASK} AIC require payment"
            }
        
        # Update record
        now = datetime.now(timezone.utc).isoformat()
        if not record.first_task_at:
            record.first_task_at = now
        record.last_task_at = now
        record.tasks_used += 1
        record.total_aic_used += aic_amount
        
        # Update IP mapping
        if ip_address:
            if ip_address not in record.ip_addresses:
                record.ip_addresses.append(ip_address)
            if ip_address not in self._ip_map:
                self._ip_map[ip_address] = []
            if entity_id not in self._ip_map[ip_address]:
                self._ip_map[ip_address].append(entity_id)
        
        # Check if quota exhausted
        if record.remaining_tasks == 0:
            record.status = QuotaStatus.EXHAUSTED
        
        self._save()
        self._log_audit("quota_used", entity_id, {
            "aic_amount": aic_amount,
            "ip": ip_address,
            "tasks_used": record.tasks_used
        })
        
        return True, {
            "success": True,
            "status": record.status.value,
            "tasks_used": record.tasks_used,
            "remaining_tasks": record.remaining_tasks,
            "total_aic_used": record.total_aic_used,
            "message": f"Free quota used. {record.remaining_tasks} tasks remaining."
        }
    
    def grant_progressive_quota(
        self, 
        entity_id: str, 
        trust_score: float,
        reason: str
    ) -> Dict[str, Any]:
        """
        Grant extended quota to proven entities
        Based on trust score and good behavior
        """
        record = self.get_or_create_record(entity_id)
        
        if trust_score < 50:
            return {
                "success": False,
                "reason": "Trust score too low for progressive quota",
                "trust_score": trust_score
            }
        
        # Calculate extended quota
        base_extension = 3
        if trust_score >= 80:
            base_extension = 10
        elif trust_score >= 70:
            base_extension = 7
        elif trust_score >= 60:
            base_extension = 5
        
        record.extended_quota += base_extension
        record.trust_score = trust_score
        record.status = QuotaStatus.PROGRESSIVE
        
        self._save()
        self._log_audit("progressive_quota_granted", entity_id, {
            "trust_score": trust_score,
            "extension": base_extension,
            "reason": reason
        })
        
        return {
            "success": True,
            "extended_quota": record.extended_quota,
            "total_remaining": record.remaining_tasks,
            "trust_score": trust_score,
            "message": f"Progressive quota granted: +{base_extension} tasks"
        }
    
    def get_quota_status(self, entity_id: str) -> Dict[str, Any]:
        """Get current quota status for an entity"""
        record = self.get_or_create_record(entity_id)
        
        return {
            "entity_id": entity_id,
            "status": record.status.value,
            "tasks_used": record.tasks_used,
            "remaining_tasks": record.remaining_tasks,
            "total_aic_used": record.total_aic_used,
            "trust_score": record.trust_score,
            "extended_quota": record.extended_quota,
            "first_task_at": record.first_task_at,
            "last_task_at": record.last_task_at,
            "is_eligible": record.is_eligible_for_free
        }
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system-wide quota statistics"""
        total_entities = len(self._records)
        active_entities = sum(1 for r in self._records.values() if r.status == QuotaStatus.ACTIVE)
        exhausted_entities = sum(1 for r in self._records.values() if r.status == QuotaStatus.EXHAUSTED)
        suspicious_entities = sum(1 for r in self._records.values() if r.status == QuotaStatus.SUSPICIOUS)
        progressive_entities = sum(1 for r in self._records.values() if r.status == QuotaStatus.PROGRESSIVE)
        
        total_free_tasks = sum(r.tasks_used for r in self._records.values())
        total_aic_used = sum(r.total_aic_used for r in self._records.values())
        
        return {
            "total_entities": total_entities,
            "active_entities": active_entities,
            "exhausted_entities": exhausted_entities,
            "suspicious_entities": suspicious_entities,
            "progressive_entities": progressive_entities,
            "total_free_tasks": total_free_tasks,
            "total_aic_used": total_aic_used,
            "unique_ips": len(self._ip_map)
        }


# Global instance
_quota_manager: Optional[FreeQuotaManager] = None

def get_quota_manager() -> FreeQuotaManager:
    """Get or create global quota manager instance"""
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = FreeQuotaManager()
    return _quota_manager


# Convenience functions
def use_free_quota(entity_id: str, aic_amount: float, ip_address: Optional[str] = None) -> Tuple[bool, Dict]:
    """Use free quota for a task"""
    return get_quota_manager().use_free_quota(entity_id, aic_amount, ip_address)

def get_quota_status(entity_id: str) -> Dict[str, Any]:
    """Get quota status for entity"""
    return get_quota_manager().get_quota_status(entity_id)

def grant_progressive_quota(entity_id: str, trust_score: float, reason: str) -> Dict[str, Any]:
    """Grant progressive quota to proven entity"""
    return get_quota_manager().grant_progressive_quota(entity_id, trust_score, reason)


def get_system_stats() -> Dict[str, Any]:
    """Get system-wide statistics"""
    return get_quota_manager().get_system_stats()


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(level=logging.INFO)
    
    print("=== Free Quota System Demo ===")
    
    # Test new entity
    entity_id = "demo_entity_001"
    
    # Check initial status
    status = get_quota_status(entity_id)
    print(f"\nInitial status: {status}")
    
    # Use free quota
    for i in range(4):
        success, details = use_free_quota(entity_id, 50.0, ip_address="192.168.1.100")
        print(f"\nTask {i+1}: success={success}")
        print(f"  Details: {details}")
    
    # Check final status
    final_status = get_quota_status(entity_id)
    print(f"\nFinal status: {final_status}")
    
    # System stats
    stats = get_system_stats()
    print(f"\nSystem stats: {stats}")
