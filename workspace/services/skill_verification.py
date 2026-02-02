#!/usr/bin/env python3
"""
Skill Verification Framework
Open Entity Charter v0.2 準拠のスキル検証システム

Features:
- Automated skill testing through challenges
- Peer verification system
- Verified skill certificates
- Integration with Trust Score
- Anti-gaming measures
"""

import json
import logging
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from pathlib import Path
from enum import Enum
import random
import string

logger = logging.getLogger(__name__)


class VerificationMethod(Enum):
    """スキル検証方法"""
    AUTOMATED_TEST = "automated_test"      # 自動テスト
    PEER_REVIEW = "peer_review"            # ピアレビュー
    TASK_COMPLETION = "task_completion"    # 実タスク実績
    CHALLENGE = "challenge"                # チャレンジ課題


class VerificationStatus(Enum):
    """検証ステータス"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class SkillChallenge:
    """スキル検証チャレンジ"""
    challenge_id: str
    skill_category: str
    difficulty: int  # 1-5
    challenge_type: str
    description: str
    test_data: Dict[str, Any]
    expected_result: Any
    time_limit_seconds: int
    created_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "skill_category": self.skill_category,
            "difficulty": self.difficulty,
            "challenge_type": self.challenge_type,
            "description": self.description,
            "test_data": self.test_data,
            "expected_result": self.expected_result,
            "time_limit_seconds": self.time_limit_seconds,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillChallenge":
        return cls(**data)


@dataclass
class VerificationAttempt:
    """検証試行記録"""
    attempt_id: str
    entity_id: str
    skill_category: str
    challenge_id: str
    method: VerificationMethod
    status: VerificationStatus
    started_at: str
    completed_at: Optional[str] = None
    result_data: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0  # 0-100
    verified_by: Optional[str] = None  # For peer review
    certificate_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "entity_id": self.entity_id,
            "skill_category": self.skill_category,
            "challenge_id": self.challenge_id,
            "method": self.method.value,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result_data": self.result_data,
            "score": self.score,
            "verified_by": self.verified_by,
            "certificate_id": self.certificate_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationAttempt":
        return cls(
            attempt_id=data["attempt_id"],
            entity_id=data["entity_id"],
            skill_category=data["skill_category"],
            challenge_id=data["challenge_id"],
            method=VerificationMethod(data["method"]),
            status=VerificationStatus(data["status"]),
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            result_data=data.get("result_data", {}),
            score=data.get("score", 0.0),
            verified_by=data.get("verified_by"),
            certificate_id=data.get("certificate_id")
        )


@dataclass
class VerifiedSkill:
    """検証済みスキル証明書"""
    certificate_id: str
    entity_id: str
    skill_category: str
    level: int  # 1-5, calculated from verification score
    method: VerificationMethod
    score: float
    verified_at: str
    expires_at: Optional[str] = None
    challenge_id: str = ""
    revocation_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "entity_id": self.entity_id,
            "skill_category": self.skill_category,
            "level": self.level,
            "method": self.method.value,
            "score": self.score,
            "verified_at": self.verified_at,
            "expires_at": self.expires_at,
            "challenge_id": self.challenge_id,
            "revocation_reason": self.revocation_reason
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerifiedSkill":
        return cls(
            certificate_id=data["certificate_id"],
            entity_id=data["entity_id"],
            skill_category=data["skill_category"],
            level=data["level"],
            method=VerificationMethod(data["method"]),
            score=data["score"],
            verified_at=data["verified_at"],
            expires_at=data.get("expires_at"),
            challenge_id=data.get("challenge_id", ""),
            revocation_reason=data.get("revocation_reason")
        )
    
    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > datetime.fromisoformat(self.expires_at)
    
    @property
    def is_valid(self) -> bool:
        return self.revocation_reason is None and not self.is_expired


class SkillVerificationFramework:
    """
    スキル検証フレームワーク
    
    AIエージェントのスキルを検証し、信頼性のある証明書を発行する。
    """
    
    DATA_DIR = Path("data/skill_verification")
    CHALLENGES_FILE = DATA_DIR / "challenges.json"
    ATTEMPTS_FILE = DATA_DIR / "attempts.json"
    CERTIFICATES_FILE = DATA_DIR / "certificates.json"
    
    # Score thresholds for levels
    LEVEL_THRESHOLDS = {
        1: 60,   # Basic
        2: 70,   # Intermediate
        3: 80,   # Advanced
        4: 90,   # Expert
        5: 95    # Master
    }
    
    # Certificate validity period (days)
    CERT_VALIDITY_DAYS = {
        VerificationMethod.AUTOMATED_TEST: 90,
        VerificationMethod.PEER_REVIEW: 180,
        VerificationMethod.TASK_COMPLETION: 365,
        VerificationMethod.CHALLENGE: 180
    }
    
    def __init__(self):
        self._challenges: Dict[str, SkillChallenge] = {}
        self._attempts: Dict[str, VerificationAttempt] = {}
        self._certificates: Dict[str, VerifiedSkill] = {}
        self._entity_certificates: Dict[str, List[str]] = {}  # entity_id -> cert_ids
        self._ensure_data_dir()
        self._load()
        self._generate_default_challenges()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load persisted data"""
        if self.CHALLENGES_FILE.exists():
            try:
                with open(self.CHALLENGES_FILE, 'r') as f:
                    data = json.load(f)
                    self._challenges = {
                        k: SkillChallenge.from_dict(v) 
                        for k, v in data.items()
                    }
            except Exception as e:
                logger.error(f"Failed to load challenges: {e}")
        
        if self.ATTEMPTS_FILE.exists():
            try:
                with open(self.ATTEMPTS_FILE, 'r') as f:
                    data = json.load(f)
                    self._attempts = {
                        k: VerificationAttempt.from_dict(v)
                        for k, v in data.items()
                    }
            except Exception as e:
                logger.error(f"Failed to load attempts: {e}")
        
        if self.CERTIFICATES_FILE.exists():
            try:
                with open(self.CERTIFICATES_FILE, 'r') as f:
                    data = json.load(f)
                    self._certificates = {
                        k: VerifiedSkill.from_dict(v)
                        for k, v in data.items()
                    }
                    # Build entity index
                    for cert_id, cert in self._certificates.items():
                        if cert.entity_id not in self._entity_certificates:
                            self._entity_certificates[cert.entity_id] = []
                        self._entity_certificates[cert.entity_id].append(cert_id)
            except Exception as e:
                logger.error(f"Failed to load certificates: {e}")
    
    def _save(self):
        """Persist data"""
        try:
            with open(self.CHALLENGES_FILE, 'w') as f:
                json.dump(
                    {k: v.to_dict() for k, v in self._challenges.items()},
                    f, indent=2
                )
            
            with open(self.ATTEMPTS_FILE, 'w') as f:
                json.dump(
                    {k: v.to_dict() for k, v in self._attempts.items()},
                    f, indent=2
                )
            
            with open(self.CERTIFICATES_FILE, 'w') as f:
                json.dump(
                    {k: v.to_dict() for k, v in self._certificates.items()},
                    f, indent=2
                )
        except Exception as e:
            logger.error(f"Failed to save verification data: {e}")
    
    def _generate_default_challenges(self):
        """Generate default skill challenges"""
        if self._challenges:
            return
        
        default_challenges = [
            # Programming challenges
            {
                "category": "programming",
                "difficulty": 1,
                "type": "code_completion",
                "description": "Complete a simple function that adds two numbers",
                "test_data": {"function": "add(a, b)", "examples": [[1, 2], [5, 3], [0, 0]]},
                "expected_result": [[3], [8], [0]],
                "time_limit": 300
            },
            {
                "category": "programming",
                "difficulty": 3,
                "type": "algorithm",
                "description": "Implement a function to reverse a string",
                "test_data": {"function": "reverse(s)", "examples": ["hello", "world", "12345"]},
                "expected_result": ["olleh", "dlrow", "54321"],
                "time_limit": 600
            },
            # Analysis challenges
            {
                "category": "analysis",
                "difficulty": 2,
                "type": "data_analysis",
                "description": "Calculate average of a number list",
                "test_data": {"lists": [[1, 2, 3], [10, 20, 30], [5, 5, 5]]},
                "expected_result": [2.0, 20.0, 5.0],
                "time_limit": 300
            },
            {
                "category": "analysis",
                "difficulty": 4,
                "type": "pattern_recognition",
                "description": "Identify the pattern in the sequence",
                "test_data": {"sequences": [["1, 3, 5, 7, ?"], ["2, 4, 8, 16, ?"], ["1, 1, 2, 3, 5, ?"]]},
                "expected_result": [9, 32, 8],
                "time_limit": 600
            },
            # Research challenges
            {
                "category": "research",
                "difficulty": 2,
                "type": "information_retrieval",
                "description": "Find relevant information from given context",
                "test_data": {"context": "Python was created by Guido van Rossum", "question": "Who created Python?"},
                "expected_result": "Guido van Rossum",
                "time_limit": 300
            },
            # Review challenges
            {
                "category": "review",
                "difficulty": 3,
                "type": "code_review",
                "description": "Identify the bug in the given code snippet",
                "test_data": {"code": "def divide(a, b): return a / b", "test": "divide(5, 0)"},
                "expected_result": "ZeroDivisionError",
                "time_limit": 300
            },
            # Design challenges
            {
                "category": "design",
                "difficulty": 3,
                "type": "api_design",
                "description": "Design a REST API endpoint for user registration",
                "test_data": {"requirements": ["POST endpoint", "Validate email", "Hash password"]},
                "expected_result": ["POST /api/users", "email validation", "password hashing"],
                "time_limit": 900
            }
        ]
        
        for challenge_data in default_challenges:
            challenge_id = str(uuid.uuid4())
            challenge = SkillChallenge(
                challenge_id=challenge_id,
                skill_category=challenge_data["category"],
                difficulty=challenge_data["difficulty"],
                challenge_type=challenge_data["type"],
                description=challenge_data["description"],
                test_data=challenge_data["test_data"],
                expected_result=challenge_data["expected_result"],
                time_limit_seconds=challenge_data["time_limit"],
                created_at=datetime.now(timezone.utc).isoformat()
            )
            self._challenges[challenge_id] = challenge
        
        self._save()
        logger.info(f"Generated {len(default_challenges)} default challenges")
    
    def get_available_challenges(
        self, 
        skill_category: Optional[str] = None,
        difficulty: Optional[int] = None
    ) -> List[SkillChallenge]:
        """Get available challenges with optional filters"""
        challenges = list(self._challenges.values())
        
        if skill_category:
            challenges = [c for c in challenges if c.skill_category == skill_category]
        
        if difficulty:
            challenges = [c for c in challenges if c.difficulty == difficulty]
        
        return sorted(challenges, key=lambda c: (c.skill_category, c.difficulty))
    
    def start_verification(
        self,
        entity_id: str,
        skill_category: str,
        method: VerificationMethod = VerificationMethod.CHALLENGE
    ) -> Dict[str, Any]:
        """Start a verification attempt"""
        # Select appropriate challenge
        challenges = self.get_available_challenges(skill_category)
        if not challenges:
            return {
                "success": False,
                "error": f"No challenges available for category: {skill_category}"
            }
        
        # Pick challenge based on entity's previous attempts
        challenge = random.choice(challenges)
        
        # Create attempt record
        attempt_id = str(uuid.uuid4())
        attempt = VerificationAttempt(
            attempt_id=attempt_id,
            entity_id=entity_id,
            skill_category=skill_category,
            challenge_id=challenge.challenge_id,
            method=method,
            status=VerificationStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc).isoformat()
        )
        
        self._attempts[attempt_id] = attempt
        self._save()
        
        logger.info(f"Verification started: {attempt_id} for {entity_id}")
        
        return {
            "success": True,
            "attempt_id": attempt_id,
            "challenge": challenge.to_dict(),
            "time_limit_seconds": challenge.time_limit_seconds,
            "message": f"Challenge assigned. Complete within {challenge.time_limit_seconds} seconds."
        }
    
    def submit_verification_result(
        self,
        attempt_id: str,
        result: Any,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Submit verification result"""
        if attempt_id not in self._attempts:
            return {"success": False, "error": "Attempt not found"}
        
        attempt = self._attempts[attempt_id]
        challenge = self._challenges.get(attempt.challenge_id)
        
        if not challenge:
            return {"success": False, "error": "Challenge not found"}
        
        # Evaluate result
        score = self._evaluate_result(challenge, result)
        passed = score >= self.LEVEL_THRESHOLDS[1]  # Minimum level 1 threshold
        
        # Update attempt
        attempt.status = VerificationStatus.PASSED if passed else VerificationStatus.FAILED
        attempt.completed_at = datetime.now(timezone.utc).isoformat()
        attempt.score = score
        attempt.result_data = {
            "submitted_result": result,
            "expected_result": challenge.expected_result,
            "metadata": metadata or {}
        }
        
        # Generate certificate if passed
        if passed:
            level = self._calculate_level(score)
            cert_id = self._issue_certificate(
                attempt.entity_id,
                attempt.skill_category,
                level,
                attempt.method,
                score,
                attempt.challenge_id
            )
            attempt.certificate_id = cert_id
        
        self._save()
        
        logger.info(f"Verification completed: {attempt_id}, score={score}, passed={passed}")
        
        return {
            "success": True,
            "passed": passed,
            "score": score,
            "level": self._calculate_level(score) if passed else 0,
            "certificate_id": attempt.certificate_id,
            "message": "Verification passed! Certificate issued." if passed else "Verification failed. Try again."
        }
    
    def _evaluate_result(self, challenge: SkillChallenge, result: Any) -> float:
        """Evaluate challenge result and return score (0-100)"""
        expected = challenge.expected_result
        
        if isinstance(expected, list) and isinstance(result, list):
            # Compare list results
            correct = sum(1 for e, r in zip(expected, result) if e == r)
            return (correct / len(expected)) * 100
        elif expected == result:
            return 100.0
        else:
            # Partial match for strings
            if isinstance(expected, str) and isinstance(result, str):
                if expected.lower() in result.lower():
                    return 80.0
            return 0.0
    
    def _calculate_level(self, score: float) -> int:
        """Calculate skill level from score"""
        for level, threshold in sorted(self.LEVEL_THRESHOLDS.items(), reverse=True):
            if score >= threshold:
                return level
        return 1  # Minimum level
    
    def _issue_certificate(
        self,
        entity_id: str,
        skill_category: str,
        level: int,
        method: VerificationMethod,
        score: float,
        challenge_id: str
    ) -> str:
        """Issue verified skill certificate"""
        cert_id = f"CERT-{uuid.uuid4().hex[:8].upper()}"
        
        now = datetime.now(timezone.utc)
        validity_days = self.CERT_VALIDITY_DAYS.get(method, 180)
        expires_at = (now + timedelta(days=validity_days)).isoformat()
        
        cert = VerifiedSkill(
            certificate_id=cert_id,
            entity_id=entity_id,
            skill_category=skill_category,
            level=level,
            method=method,
            score=score,
            verified_at=now.isoformat(),
            expires_at=expires_at,
            challenge_id=challenge_id
        )
        
        self._certificates[cert_id] = cert
        
        if entity_id not in self._entity_certificates:
            self._entity_certificates[entity_id] = []
        self._entity_certificates[entity_id].append(cert_id)
        
        self._save()
        
        logger.info(f"Certificate issued: {cert_id} to {entity_id}")
        
        return cert_id
    
    def get_entity_certificates(self, entity_id: str) -> List[VerifiedSkill]:
        """Get all certificates for an entity"""
        cert_ids = self._entity_certificates.get(entity_id, [])
        return [self._certificates[cid] for cid in cert_ids if cid in self._certificates]
    
    def get_valid_certificates(self, entity_id: str) -> List[VerifiedSkill]:
        """Get valid (non-expired, non-revoked) certificates"""
        certs = self.get_entity_certificates(entity_id)
        return [c for c in certs if c.is_valid]
    
    def get_certificate(self, cert_id: str) -> Optional[VerifiedSkill]:
        """Get certificate by ID"""
        return self._certificates.get(cert_id)
    
    def verify_certificate(self, cert_id: str) -> Dict[str, Any]:
        """Verify a certificate's validity"""
        cert = self._certificates.get(cert_id)
        
        if not cert:
            return {"valid": False, "error": "Certificate not found"}
        
        return {
            "valid": cert.is_valid,
            "certificate": cert.to_dict(),
            "expired": cert.is_expired,
            "revoked": cert.revocation_reason is not None
        }
    
    def revoke_certificate(self, cert_id: str, reason: str) -> bool:
        """Revoke a certificate (for admin use)"""
        if cert_id not in self._certificates:
            return False
        
        self._certificates[cert_id].revocation_reason = reason
        self._save()
        
        logger.warning(f"Certificate revoked: {cert_id}, reason: {reason}")
        
        return True
    
    def get_entity_skill_level(self, entity_id: str, skill_category: str) -> int:
        """Get entity's verified skill level in a category"""
        certs = self.get_valid_certificates(entity_id)
        category_certs = [c for c in certs if c.skill_category == skill_category]
        
        if not category_certs:
            return 0
        
        return max(c.level for c in category_certs)
    
    def get_verification_stats(self) -> Dict[str, Any]:
        """Get system-wide verification statistics"""
        total_attempts = len(self._attempts)
        passed = sum(1 for a in self._attempts.values() if a.status == VerificationStatus.PASSED)
        failed = sum(1 for a in self._attempts.values() if a.status == VerificationStatus.FAILED)
        
        total_certs = len(self._certificates)
        valid_certs = sum(1 for c in self._certificates.values() if c.is_valid)
        expired_certs = sum(1 for c in self._certificates.values() if c.is_expired)
        revoked_certs = sum(1 for c in self._certificates.values() if c.revocation_reason)
        
        # By category
        category_stats = {}
        for cert in self._certificates.values():
            cat = cert.skill_category
            if cat not in category_stats:
                category_stats[cat] = {"count": 0, "avg_level": 0.0}
            category_stats[cat]["count"] += 1
            category_stats[cat]["avg_level"] += cert.level
        
        for cat in category_stats:
            if category_stats[cat]["count"] > 0:
                category_stats[cat]["avg_level"] /= category_stats[cat]["count"]
        
        return {
            "attempts": {
                "total": total_attempts,
                "passed": passed,
                "failed": failed,
                "pass_rate": passed / total_attempts if total_attempts > 0 else 0.0
            },
            "certificates": {
                "total": total_certs,
                "valid": valid_certs,
                "expired": expired_certs,
                "revoked": revoked_certs
            },
            "by_category": category_stats,
            "unique_verified_entities": len(self._entity_certificates)
        }


# Global instance
_verification_framework: Optional[SkillVerificationFramework] = None

def get_verification_framework() -> SkillVerificationFramework:
    """Get or create global verification framework instance"""
    global _verification_framework
    if _verification_framework is None:
        _verification_framework = SkillVerificationFramework()
    return _verification_framework


# Convenience functions
def start_verification(entity_id: str, skill_category: str, method: str = "challenge") -> Dict:
    """Start verification for an entity"""
    m = VerificationMethod(method)
    return get_verification_framework().start_verification(entity_id, skill_category, m)

def submit_verification_result(attempt_id: str, result: Any, metadata: Optional[Dict] = None) -> Dict:
    """Submit verification result"""
    return get_verification_framework().submit_verification_result(attempt_id, result, metadata)

def get_entity_certificates(entity_id: str) -> List[Dict]:
    """Get entity's certificates"""
    certs = get_verification_framework().get_valid_certificates(entity_id)
    return [c.to_dict() for c in certs]

def verify_certificate(cert_id: str) -> Dict:
    """Verify a certificate"""
    return get_verification_framework().verify_certificate(cert_id)


def get_verification_stats() -> Dict:
    """Get verification statistics"""
    return get_verification_framework().get_verification_stats()


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)
    
    print("=== Skill Verification Framework Demo ===")
    
    # Start verification
    result = start_verification("demo_entity", "programming")
    print(f"\nVerification started:")
    print(f"  Attempt ID: {result.get('attempt_id')}")
    print(f"  Challenge: {result.get('challenge', {}).get('description')}")
    
    # Submit correct answer
    if result.get('success'):
        attempt_id = result['attempt_id']
        challenge = result['challenge']
        
        # Simulate correct answer
        correct_answer = challenge['expected_result']
        submit_result = submit_verification_result(attempt_id, correct_answer)
        
        print(f"\nSubmission result:")
        print(f"  Passed: {submit_result.get('passed')}")
        print(f"  Score: {submit_result.get('score')}")
        print(f"  Level: {submit_result.get('level')}")
        print(f"  Certificate: {submit_result.get('certificate_id')}")
    
    # Check stats
    stats = get_verification_stats()
    print(f"\nVerification stats:")
    print(f"  Total attempts: {stats['attempts']['total']}")
    print(f"  Passed: {stats['attempts']['passed']}")
    print(f"  Certificates issued: {stats['certificates']['total']}")
