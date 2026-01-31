# Peer Service Refactoring Plan

## Review Summary

| Severity | Count | Description |
|----------|-------|-------------|
| Major | 2 | Excessive responsibility, inefficient ClientSession usage |
| Minor | 2 | Duplicate error handling, chunk validation exception handling |
| Praise | 2 | Non-retryable status detection, exponential backoff |

## Major Issue 1: send_message Responsibility

Current send_message handles:
- Chunk split detection
- Stats initialization and update
- Message creation
- HTTP send delegation
- Success/failure stats branching
- Queue addition

Refactoring Plan:
1. Create SendResult dataclass
2. Extract _validate_peer method
3. Extract _should_chunk method
4. Inline _send_with_retry into _execute_send
5. Create _update_delivery_stats for centralized stats management

## Major Issue 2: ClientSession Inefficiency

Current: Creates new ClientSession per retry
Solution: Reuse session across class lifecycle

Implementation Priority:
1. High: SendResult dataclass + inline retry logic
2. High: Centralized stats update method
3. Medium: ClientSession reuse
4. Low: Chunk validation exception handling

## Module Split Plan

Current peer_service.py: ~4856 lines

Proposed structure under services/peer/:
- models.py - Data classes (~400 lines)
- queue.py - MessageQueue (~300 lines)
- heartbeat.py - HeartbeatManager (~250 lines)
- handlers.py - Message handlers (~800 lines)
- security.py - Security utilities (~400 lines)
- session.py - Session wrapper (~300 lines)
- service.py - Main PeerService (~1500 lines)

## Long-term Goals
1. Each module under 1000 lines
2. Independent testability
3. Better code organization
4. Multiple developer collaboration

Date: 2026-02-01 (updated)