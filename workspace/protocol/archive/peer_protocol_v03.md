# Peer Communication Protocol v0.3

## Overview
AIエンティティ間の安全な通信プロトコル。

## New Features
- Authentication with JWT
- Encryption with AES-256
- Message integrity with signatures

## Message Types
- status_report
- wake_up
- task_delegate
- discovery
- heartbeat
- capability_query
- token_transfer

## Detailed Security Specifications

### Ed25519 Signatures
- Each entity has Ed25519 key pair
- Private key: ENTITY_PRIVATE_KEY env var
- Public key: Distributed during handshake
- All messages must be signed

### Encryption (X25519 + AES-256-GCM)
- Ephemeral key exchange for session keys
- Perfect forward secrecy
- Payload encryption for sensitive data

### Replay Protection
- Timestamp tolerance: 60 seconds
- 128-bit nonce per message
- 5-minute duplicate detection window

## Security Requirements
- All messages must be signed (v0.3+)
- JWT expires in 5 minutes
- HTTPS required for production
- Replay protection enabled
- Public key verification required

## Implementation Status
- Implemented: api_server.py, crypto.py, crypto_utils.py
- Tested: test_signature.py, test_api_integration.py

## Token Transfer Protocol

### Message Type: token_transfer

P2P token transfer message for cross-entity AIC transfers.

Payload: from_entity, to_entity, amount, transfer_id, timestamp, signature
Response: status, transfer_id, new_balance (or reason on error)

## Test Suite
- test_signature.py - Ed25519 signature unit tests
- test_api_integration.py - API endpoint integration tests
- test_p2p_transfer.py - P2P token transfer tests
