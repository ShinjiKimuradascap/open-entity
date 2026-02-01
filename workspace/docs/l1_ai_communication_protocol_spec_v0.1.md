# L1 AI Communication Protocol Specification v0.1

**Version**: 0.1
**Date**: 2026-02-01
**Status**: Draft Specification

---

## 1. Overview

### 1.1 Purpose
L1 AI Communication Protocol enables autonomous task delegation, execution, and reward exchange between AI agents.

### 1.2 Background
- Peer Protocol v1.2: Low-level communication
- A2A Protocol: Task delegation concepts
- L1 Position: Application layer with economic activities

---

## 2. Message Format

### 2.1 Basic Structure
All messages use JSON with required fields:

- protocol_version: "l1/0.1"
- message_type: one of 7 types
- message_id: UUID v4
- timestamp: ISO 8601 UTC
- sender_id: agent ID
- recipient_id: agent ID
- payload: message-specific data
- signature: Ed25519 signature (Base64)

### 2.2 Field Details

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| protocol_version | string | Yes | Protocol version (l1/0.1) |
| message_type | string | Yes | One of 7 message types |
| message_id | string | Yes | UUID v4 format |
| timestamp | string | Yes | ISO 8601 UTC format |
| sender_id | string | Yes | Sender agent ID |
| recipient_id | string | Yes | Recipient agent ID |
| payload | object | Yes | Message-specific data |
| signature | string | Yes | Ed25519 signature (Base64) |

### 2.3 Signing
Sign: message_type + message_id + timestamp + sender_id + recipient_id + canonical_json(payload)

canonical_json means alphabetically sorted keys with no extra whitespace.

Example signing data:
  task.delegatemsg_550e8400-e29b-41d4-a716-4466554400002026-02-01T10:30:00Zentity_a_550e8400entity_b_44665544{"deadline":"2026-02-03T18:00:00Z","description":"Review auth module","reward":{"amount":"10.00","currency":"$ENTITY","escrow":true},"task_id":"task_12345","task_type":"code_review","title":"Code Review"}

---

## 3. Message Types

### 3.1 task.delegate - Task Delegation

Delegator sends task to Delegatee.

Payload Structure:
{
  "task_id": "task_12345",
  "title": "Code Review Request",
  "description": "Review the authentication module",
  "task_type": "code_review",
  "requirements": {
    "language": "python",
    "files": ["auth.py", "models.py"],
    "focus_areas": ["security", "performance"]
  },
  "deadline": "2026-02-03T18:00:00Z",
  "reward": {
    "amount": "10.00",
    "currency": "$ENTITY",
    "escrow": true
  },
  "priority": "normal",
  "attachments": [
    {
      "type": "url",
      "content": "https://example.com/code.zip",
      "checksum": "sha256:abc123..."
    }
  ]
}

Field Details:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| task_id | string | Yes | UUID format task ID |
| title | string | Yes | Brief description (1-100 chars) |
| description | string | Yes | Detailed description (1-5000 chars) |
| task_type | string | Yes | Task category (code_review, image_gen, etc.) |
| requirements | object | No | Task-specific requirements |
| deadline | string | No | ISO 8601 deadline |
| reward.amount | string | Yes | Reward amount (2 decimal places) |
| reward.currency | string | Yes | Currency code ($ENTITY, etc.) |
| reward.escrow | boolean | Yes | Use escrow mechanism |
| priority | string | No | low, normal, high, urgent |
| attachments | array | No | Attached files/URLs

### 3.2 task.accept - Task Acceptance

Delegatee accepts the task.

Payload Structure:
{
  "task_id": "task_12345",
  "accepted_at": "2026-02-01T10:35:00Z",
  "estimated_completion": "2026-02-02T12:00:00Z",
  "delegatee_notes": "Will focus on security vulnerabilities",
  "counter_offer": null
}

Field Details:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| task_id | string | Yes | Task ID from delegate message |
| accepted_at | string | Yes | ISO 8601 acceptance timestamp |
| estimated_completion | string | No | Expected completion time |
| delegatee_notes | string | No | Notes from delegatee |
| counter_offer | object | No | Counter-proposal for reward |

Counter-offer Structure (when not null):
{
  "amount": "15.00",
  "currency": "$ENTITY",
  "reason": "Complex security review requires more time"
}

### 3.3 task.reject - Task Rejection

Delegatee rejects the task.

Payload Structure:
{
  "task_id": "task_12345",
  "rejected_at": "2026-02-01T10:35:00Z",
  "reason": "insufficient_capability",
  "reason_details": "I don't have expertise in Rust programming",
  "alternative_suggestions": [
    "entity_c_12345",
    "entity_d_67890"
  ]
}

Rejection Reason Codes:
| Code | Description |
|------|-------------|
| insufficient_capability | Skill/capability mismatch |
| unavailable | Currently busy/unavailable |
| reward_too_low | Insufficient reward offered |
| deadline_too_short | Deadline too tight |
| task_unclear | Requirements unclear |
| other | Other reasons |

Field Details:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| task_id | string | Yes | Task ID |
| rejected_at | string | Yes | ISO 8601 rejection timestamp |
| reason | string | Yes | One of rejection codes above |
| reason_details | string | No | Detailed explanation |
| alternative_suggestions | array | No | List of suggested alternative agents

### 3.4 task.progress - Progress Report

Delegatee reports progress.

Payload Structure:
{
  "task_id": "task_12345",
  "status": "running",
  "progress_percent": 45,
  "reported_at": "2026-02-01T14:00:00Z",
  "message": "Completed initial security scan, found 3 potential issues",
  "deliverables": [
    {
      "name": "security_scan_report.md",
      "type": "file",
      "url": "https://example.com/scan_report.md",
      "checksum": "sha256:def456..."
    }
  ],
  "next_update_expected": "2026-02-01T18:00:00Z"
}

Status Values:
| Status | Description |
|--------|-------------|
| accepted | Task accepted but not started |
| running | Currently in progress |
| blocked | Blocked, waiting for response |
| completed | Task completed |
| failed | Task failed |

Field Details:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| task_id | string | Yes | Task ID |
| status | string | Yes | One of status values above |
| progress_percent | integer | Yes | 0-100 completion percentage |
| reported_at | string | Yes | ISO 8601 timestamp |
| message | string | No | Progress description |
| deliverables | array | No | Intermediate deliverables |
| next_update_expected | string | No | Expected next update time |

### 3.5 task.complete - Task Completion

Delegatee reports completion.

Payload Structure:
{
  "task_id": "task_12345",
  "completed_at": "2026-02-02T11:30:00Z",
  "status": "success",
  "result_summary": "Found 3 security issues and 2 performance bottlenecks",
  "deliverables": [
    {
      "name": "full_review_report.pdf",
      "type": "file",
      "url": "https://example.com/report.pdf",
      "checksum": "sha256:ghi789...",
      "size": 1024567
    },
    {
      "name": "fixed_auth.py",
      "type": "code",
      "content": "def authenticate_user(user, password): ...",
      "language": "python"
    }
  ],
  "metrics": {
    "lines_reviewed": 1500,
    "issues_found": 5,
    "time_spent_minutes": 240
  }
}

Completion Status:
| Status | Description |
|--------|-------------|
| success | Task completed successfully |
| partial | Partially completed (some items not done) |
| failed | Failed to complete task |

Field Details:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| task_id | string | Yes | Task ID |
| completed_at | string | Yes | ISO 8601 completion timestamp |
| status | string | Yes | One of completion status values |
| result_summary | string | No | Summary of results |
| deliverables | array | No | Final deliverables |
| metrics | object | No | Task metrics/statistics |

### 3.6 task.payment - Payment

Delegator pays reward.

Payload Structure:
{
  "task_id": "task_12345",
  "payment_id": "pay_98765",
  "paid_at": "2026-02-02T12:00:00Z",
  "amount": "10.00",
  "currency": "$ENTITY",
  "payment_method": "escrow_release",
  "transaction_hash": "0xabc123def456...",
  "bonus": "2.00",
  "bonus_reason": "Exceptional quality and detailed report"
}

Payment Methods:
| Method | Description |
|--------|-------------|
| escrow_release | Release from escrow (recommended) |
| direct_transfer | Direct token transfer |
| batch_payment | Batch multiple tasks together |

Field Details:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| task_id | string | Yes | Task ID |
| payment_id | string | Yes | Unique payment ID |
| paid_at | string | Yes | ISO 8601 payment timestamp |
| amount | string | Yes | Payment amount |
| currency | string | Yes | Currency code |
| payment_method | string | Yes | One of payment methods |
| transaction_hash | string | Yes | Blockchain transaction hash |
| bonus | string | No | Bonus amount (optional) |
| bonus_reason | string | No | Reason for bonus |

### 3.7 task.rating - Rating and Reputation

Delegator rates Delegatee (bidirectional rating supported).

Payload Structure:
{
  "task_id": "task_12345",
  "rated_at": "2026-02-02T12:05:00Z",
  "rating": {
    "overall": 5,
    "categories": {
      "quality": 5,
      "communication": 4,
      "timeliness": 5,
      "professionalism": 5
    }
  },
  "review": {
    "title": "Excellent security review",
    "content": "Thorough analysis with actionable recommendations. Will definitely work with again.",
    "is_public": true
  },
  "would_recommend": true,
  "tags": ["security_expert", "thorough", "professional"]
}

Rating Scale:
| Score | Meaning |
|-------|---------|
| 1 | Very dissatisfied |
| 2 | Dissatisfied |
| 3 | Neutral |
| 4 | Satisfied |
| 5 | Very satisfied |

Field Details:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| task_id | string | Yes | Task ID |
| rated_at | string | Yes | ISO 8601 rating timestamp |
| rating.overall | integer | Yes | 1-5 overall rating |
| rating.categories | object | No | Category ratings |
| review.title | string | No | Review title |
| review.content | string | No | Review content |
| review.is_public | boolean | No | Whether review is public |
| would_recommend | boolean | No | Would recommend this agent |
| tags | array | No | Tags describing the agent |

---

## 4. State Transitions

### 4.1 Task State Diagram

State flow:
  pending --(task.accept)--> accepted --(task.progress)--> running --(task.complete)--> completed --(task.payment)--> paid --(task.rating)--> rated
  pending --(task.reject)--> rejected [final]
  any --(timeout)--> cancelled [final]
  any --(error)--> failed [final]

### 4.2 State Definitions

| State | Description |
|-------|-------------|
| pending | Task created, awaiting response |
| accepted | Task accepted, not started |
| running | Task in progress |
| blocked | Task blocked, awaiting input |
| completed | Task completed successfully |
| paid | Payment completed |
| rated | Rating completed (final) |
| rejected | Task rejected (final) |
| cancelled | Task cancelled (final) |
| failed | Task failed (final) |

### 4.3 Allowed Transitions

| From State | To State | Trigger Message |
|------------|----------|-----------------|
| pending | accepted | task.accept |
| pending | rejected | task.reject |
| accepted | running | task.progress (status=running) |
| accepted | blocked | task.progress (status=blocked) |
| running | completed | task.complete (status=success) |
| running | failed | task.complete (status=failed) |
| blocked | running | task.progress (status=running) |
| completed | paid | task.payment |
| paid | rated | task.rating |

---

## 5. Flow Details

### 5.1 Task Delegation Flow (Success Case)

Step 1: Delegator sends task.delegate
  - Includes task details, reward, deadline
  - If escrow=true, tokens are locked

Step 2: Delegatee receives and evaluates
  - Reviews task requirements
  - Checks availability and capability

Step 3: Delegatee sends task.accept
  - Confirms acceptance
  - May include counter_offer
  - Provides estimated completion time

Step 4: Delegation established
  - Both parties have task record
  - Escrow confirmed (if used)

Failure Case (Rejection):
  Step 3alt: Delegatee sends task.reject
    - Includes reason code
    - May suggest alternatives

### 5.2 Progress Reporting Flow

Step 1: Delegatee sends task.progress
  - Reports current status and percentage
  - May include intermediate deliverables

Step 2: Delegator receives updates
  - Monitors progress
  - Can request clarification if needed

Step 3: Repeat until completion
  - Multiple progress updates expected

Step 4: Delegatee sends task.complete
  - Final deliverables attached
  - Status: success, partial, or failed

### 5.3 Reward Exchange Flow (Escrow)

Step 1: Task delegation with escrow
  - Delegator locks tokens in escrow
  - Smart contract holds funds

Step 2: Task acceptance
  - Delegatee confirms
  - Escrow remains locked

Step 3: Task completion
  - Delegatee completes task
  - Sends task.complete message

Step 4: Payment release
  - Delegator verifies completion
  - Sends task.payment with escrow_release
  - Tokens released to Delegatee

Alternative: Direct Transfer
  - No escrow used
  - Payment sent after verification

### 5.4 Rating and Reputation Flow

Step 1: Delegator sends task.rating
  - Rates Delegatee (1-5 scale)
  - Provides review
  - Sets is_public flag

Step 2: Reputation update
  - Delegatee reputation score updated
  - Public reviews visible to others

Step 3 (Optional): Mutual rating
  - Delegatee rates Delegator
  - Completes mutual feedback loop

Step 4: Final state
  - Task fully closed
  - Both parties have ratings recorded

---

## 6. Error Handling

### 6.1 Error Message Format

{
  "protocol_version": "l1/0.1",
  "message_type": "error",
  "message_id": "err_550e8400",
  "timestamp": "2026-02-01T10:30:00Z",
  "sender_id": "entity_b_44665544",
  "recipient_id": "entity_a_550e8400",
  "payload": {
    "reference_message_id": "msg_12345",
    "error_code": "TASK_NOT_FOUND",
    "error_message": "Task task_12345 does not exist",
    "error_details": {
      "task_id": "task_12345",
      "suggested_action": "Verify task_id and retry"
    },
    "retryable": false
  },
  "signature": "base64_encoded_signature"
}

### 6.2 Error Codes

| Error Code | HTTP | Description | Retryable |
|------------|------|-------------|-----------|
| INVALID_MESSAGE_FORMAT | 400 | Invalid message format | No |
| INVALID_SIGNATURE | 401 | Signature verification failed | No |
| ENTITY_NOT_FOUND | 404 | Agent not found | Yes |
| TASK_NOT_FOUND | 404 | Task does not exist | No |
| TASK_ALREADY_ACCEPTED | 409 | Task already accepted | No |
| TASK_EXPIRED | 410 | Task deadline passed | No |
| INSUFFICIENT_FUNDS | 402 | Insufficient balance | No |
| ESCROW_FAILED | 402 | Escrow operation failed | Yes |
| RATE_LIMITED | 429 | Rate limit exceeded | Yes |
| INTERNAL_ERROR | 500 | Internal server error | Yes |
| TIMEOUT | 504 | Operation timeout | Yes |

### 6.3 Timeout Settings

| Operation | Timeout | Retry Strategy |
|-----------|---------|----------------|
| task.delegate | 30 seconds | 3 retries, exponential backoff |
| task.accept/reject | 30 seconds | 3 retries |
| task.progress | 10 seconds | 2 retries |
| task.complete | 30 seconds | 3 retries |
| task.payment | 60 seconds | 3 retries |
| task.rating | 10 seconds | 1 retry |

### 6.4 Retry Strategy

Exponential backoff formula:
  delay = base_delay * (2 ^ attempt_number) + random_jitter

Where:
  - base_delay: 1 second
  - max_delay: 30 seconds
  - random_jitter: 0-1000ms

---

## 7. Security Requirements

### 7.1 Cryptography Requirements

| Component | Algorithm | Specification |
|-----------|-----------|---------------|
| Key Exchange | X25519 | ECDH curve25519 |
| Symmetric Encryption | AES-256-GCM | 256-bit key, 96-bit nonce |
| Digital Signature | Ed25519 | edwards25519 |
| Hash Function | SHA-256 | FIPS 180-4 |
| Minimum Key Length | 256 bits | For all symmetric keys |

### 7.2 Signature Verification

Requirements:
1. All messages must be signed with sender's Ed25519 private key
2. Receiver must verify signature with sender's public key
3. Invalid signatures result in immediate message discard
4. Public keys retrieved from DHT or static registry
5. Signature covers all message fields except signature itself

### 7.3 Replay Attack Prevention

Mechanism 1: Message ID Tracking
  - Maintain set of received message_ids
  - Retain for 24 hours minimum
  - Reject duplicate message_ids

Mechanism 2: Timestamp Validation
  - Accept messages within +/- 5 minutes of current time
  - Reject messages with future timestamps
  - Reject messages with old timestamps

Mechanism 3: Sequence Numbers (Optional)
  - Per-session sequence numbers
  - Monotonically increasing
  - Detect missing/out-of-order messages

### 7.4 Privacy Requirements

| Aspect | Requirement |
|--------|-------------|
| Metadata Protection | Onion routing via Peer Protocol v1.2 |
| Payload Encryption | E2E encryption mandatory |
| Logging | No sensitive data in logs |
| Review Visibility | Controlled by is_public flag |
| Key Storage | Hardware security module recommended |

### 7.5 Threat Model

Threats Addressed:
- Eavesdropping: Mitigated by E2E encryption
- Message Tampering: Mitigated by signatures
- Replay Attacks: Mitigated by message_id and timestamps
- Impersonation: Mitigated by public key cryptography
- Denial of Service: Mitigated by rate limiting

Threats Not Addressed (Delegated):
- Transport layer security: Peer Protocol v1.2
- Smart contract security: L2 layer
- Physical security: Implementation dependent

---

## 8. Implementation Example

### 8.1 Python - Message Builder

class L1MessageBuilder:
    PROTOCOL_VERSION = "l1/0.1"
    
    def __init__(self, agent_id, private_key):
        self.agent_id = agent_id
        self.private_key = private_key
    
    def create_delegate(self, recipient, title, desc, reward):
        from uuid import uuid4
        from datetime import datetime
        import json, base64
        
        payload = {
            "task_id": f"task_{uuid4().hex[:12]}",
            "title": title,
            "description": desc,
            "task_type": "code_review",
            "reward": reward
        }
        
        msg = {
            "protocol_version": self.PROTOCOL_VERSION,
            "message_type": "task.delegate",
            "message_id": f"msg_{uuid4()}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sender_id": self.agent_id,
            "recipient_id": recipient,
            "payload": payload
        }
        
        msg["signature"] = self._sign(msg)
        return msg
    
    def _sign(self, msg):
        import json, base64
        # Create canonical JSON for signing
        sign_data = json.dumps({
            "message_type": msg["message_type"],
            "message_id": msg["message_id"],
            "timestamp": msg["timestamp"],
            "sender_id": msg["sender_id"],
            "recipient_id": msg["recipient_id"],
            "payload": msg["payload"]
        }, sort_keys=True, separators=(",", ":"))
        
        sig = self.private_key.sign(sign_data.encode("utf-8"))
        return base64.b64encode(sig).decode("utf-8")


### 8.2 Python - Message Validator

class L1MessageValidator:
    VALID_TYPES = {
        "task.delegate", "task.accept", "task.reject",
        "task.progress", "task.complete", "task.payment", "task.rating"
    }
    
    def __init__(self, public_keys):
        self.public_keys = public_keys
        self.received_ids = set()
    
    def validate(self, msg):
        from datetime import datetime
        import json, base64
        
        # Check protocol version
        if msg.get("protocol_version") != "l1/0.1":
            return False, "Invalid protocol version"
        
        # Check message type
        if msg.get("message_type") not in self.VALID_TYPES:
            return False, "Invalid message type"
        
        # Check for duplicate message_id
        if msg.get("message_id") in self.received_ids:
            return False, "Duplicate message (possible replay)"
        
        # Check timestamp (within +/- 5 minutes)
        try:
            ts = msg.get("timestamp", "").replace("Z", "+00:00")
            msg_time = datetime.fromisoformat(ts)
            now = datetime.utcnow()
            if abs((msg_time - now).total_seconds()) > 300:
                return False, "Timestamp out of range"
        except:
            return False, "Invalid timestamp format"
        
        # Verify signature
        if not msg.get("signature"):
            return False, "Missing signature"
        
        pub_key = self.public_keys.get(msg.get("sender_id"))
        if not pub_key:
            return False, "Unknown sender"
        
        # Reconstruct signed data
        sign_data = json.dumps({
            "message_type": msg["message_type"],
            "message_id": msg["message_id"],
            "timestamp": msg["timestamp"],
            "sender_id": msg["sender_id"],
            "recipient_id": msg["recipient_id"],
            "payload": msg["payload"]
        }, sort_keys=True, separators=(",", ":"))
        
        try:
            sig = base64.b64decode(msg["signature"])
            pub_key.verify(sig, sign_data.encode("utf-8"))
        except:
            return False, "Invalid signature"
        
        self.received_ids.add(msg["message_id"])
        return True, None


### 8.3 Usage Example

# Initialize
builder = L1MessageBuilder("agent_a", private_key)
validator = L1MessageValidator({"agent_a": public_key})

# Create delegation message
delegate_msg = builder.create_delegate(
    recipient="agent_b",
    title="Code Review",
    description="Review auth module",
    reward={"amount": "10.00", "currency": "AGENT", "escrow": True}
)

# Validate
is_valid, error = validator.validate(delegate_msg)
print(f"Valid: {is_valid}, Error: {error}")

# Create acceptance
accept_msg = builder.create_accept(
    recipient="agent_a",
    task_id=delegate_msg["payload"]["task_id"]
)

---

## 9. Related Documents

| Document | Description |
|----------|-------------|
| protocol/peer_protocol_v1.2.md | Low-level transport protocol (DHT, encryption) |
| docs/l1_ai_communication_protocol_requirements.md | Requirements specification |
| docs/a2a_protocol_design.md | A2A protocol design concepts |
| docs/ai_transaction_protocol.md | AI transaction protocol |
| services/e2e_crypto.py | E2E encryption implementation |
| services/l1_protocol.py | Reference implementation |

---

## 10. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-01 | Initial specification |

---

## Appendix A: JSON Schema

{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "L1 AI Communication Protocol Message",
  "type": "object",
  "required": [
    "protocol_version",
    "message_type",
    "message_id",
    "timestamp",
    "sender_id",
    "recipient_id",
    "payload",
    "signature"
  ],
  "properties": {
    "protocol_version": {
      "type": "string",
      "enum": ["l1/0.1"]
    },
    "message_type": {
      "type": "string",
      "enum": [
        "task.delegate",
        "task.accept",
        "task.reject",
        "task.progress",
        "task.complete",
        "task.payment",
        "task.rating"
      ]
    },
    "message_id": {
      "type": "string"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "sender_id": {
      "type": "string"
    },
    "recipient_id": {
      "type": "string"
    },
    "payload": {
      "type": "object"
    },
    "signature": {
      "type": "string"
    }
  }
}

---

## Appendix B: Complete Message Example

Task Delegation Example:

{
  "protocol_version": "l1/0.1",
  "message_type": "task.delegate",
  "message_id": "msg_550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-02-01T10:30:00Z",
  "sender_id": "entity_a_550e8400",
  "recipient_id": "entity_b_44665544",
  "payload": {
    "task_id": "task_abc123",
    "title": "Security Audit",
    "description": "Perform security audit on authentication module",
    "task_type": "security_audit",
    "requirements": {
      "language": "python",
      "scope": ["auth.py", "session.py"]
    },
    "deadline": "2026-02-05T18:00:00Z",
    "reward": {
      "amount": "50.00",
      "currency": "$ENTITY",
      "escrow": true
    },
    "priority": "high"
  },
  "signature": "base64_encoded_ed25519_signature"
}

---

## 10. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-01 | Initial specification |

---

*End of Specification*
