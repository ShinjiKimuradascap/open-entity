# AI Inter-Communication Protocol v0.1

## Overview
Lightweight AI inter-communication protocol for Entity A <-> Entity B mutual monitoring and task delegation.

## Design Principles
1. Simplicity - Minimum features for rapid implementation
2. Security - Ed25519 signatures required for all messages
3. Reliability - Heartbeat-based health monitoring
4. Extensibility - Designed for future expansion

## Message Format

### Base Message Structure
- version: "0.1"
- msg_type: "ping|status|task|heartbeat"
- sender_id: entity identifier
- timestamp: ISO 8601 format
- nonce: base64 encoded 16 bytes
- payload: message-specific data
- signature: base64 encoded Ed25519 signature

### Message Types

1. heartbeat - Health check (30s interval)
2. status - Current state notification
3. task - Task delegation
4. ping - Connection check

## Security Requirements

- Ed25519 signatures on all messages
- Timestamp validation (+/- 60 seconds)
- Nonce-based replay attack prevention

## Handshake Flow

1. A sends ping to B
2. B responds with pong
3. Exchange public keys
4. Establish secure channel

## Implementation

- services/peer_service.py - Core implementation
- services/crypto.py - Cryptographic utilities
- services/test_peer_service.py - Test suite

## Version History

- v0.1 (2026-02-01): Initial draft
