# Peer Communication Protocol v0.1

## Overview
AIエンティティ間の安全な通信のための軽量プロトコル。
シンプルさと実装の容易さを重視し、最小限の機能で確実な通信を実現する。

## Design Goals
1. Simplicity - 最小限のメッセージタイプとシンプルな状態管理
2. Security - Ed25519署名による認証とリプレイ攻撃防止
3. Reliability - 基本的な再送制御と接続管理
4. Interoperability - HTTP/JSONベースでどの言語からも実装可能

## Message Format

### BaseMessage Structure
All messages follow this structure:
- version: "0.1"
- msg_type: ping|pong|status|delegate|result|error
- sender_id, recipient_id: string identifiers
- timestamp: ISO8601 UTC format
- nonce: 16-byte hex string for replay protection
- payload.data: base64 encoded JSON
- signature: Ed25519 64-byte hex signature

### Field Descriptions
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| version | string | Yes | Protocol version ("0.1") |
| msg_type | string | Yes | Message type identifier |
| sender_id | string | Yes | Unique sender identifier |
| recipient_id | string | Yes | Target recipient identifier |
| timestamp | ISO8601 | Yes | UTC timestamp |
| nonce | hex(16bytes) | Yes | Replay protection |
| payload | object | Yes | Message content with base64 data |
| signature | hex(64bytes) | Yes | Ed25519 signature |

## Message Types

### 1. Ping / Pong (Connection Test)
Basic connectivity check between peers.

### 2. Status (Health Report)
Periodic health and capability reporting.

### 3. Delegate (Task Assignment)
Assign a task to another entity.

### 4. Result (Task Completion)
Return results from completed tasks.

### 5. Error
Error response for failed operations.

## Security Requirements

### Message Signing (Required)
- All messages MUST be signed with Ed25519
- Signature covers all fields except signature itself
- Signature format: 64-byte hex string

### Replay Protection (Required)
- 16-byte random nonce for each message
- Timestamp tolerance: plus/minus 5 minutes
- Nonce tracking: Last 1000 nonces per peer

### Identity Verification
- Public key registry per peer
- Sender_id must match registered public key

## Error Codes

| Code | Description |
|------|-------------|
| INVALID_VERSION | Unsupported protocol version |
| INVALID_SIGNATURE | Signature verification failed |
| REPLAY_DETECTED | Duplicate nonce detected |
| EXPIRED_TIMESTAMP | Timestamp outside tolerance window |
| UNKNOWN_SENDER | Sender not in registry |
| UNKNOWN_RECIPIENT | Recipient mismatch |
| INVALID_PAYLOAD | Payload decode failed |
| TIMEOUT | Operation timed out |
| SERVICE_UNAVAILABLE | Recipient busy or offline |

## HTTP Interface

### Endpoints

#### POST /v0.1/message
Receive a signed message from a peer.

#### GET /v0.1/health
Check peer health status.

#### GET /v0.1/public-key
Get peer's public key for signature verification.

## Communication Flow

### Initial Connection
1. Query public key via GET /public-key
2. Send ping with signature
3. Verify response signature
4. Connection established

### Task Delegation Flow
1. Send delegate message
2. Verify acknowledgment
3. Process task
4. Send result message
5. Verify completion

## Implementation Guidelines

### Client Responsibilities
- Sign all outgoing messages
- Verify all incoming message signatures
- Generate unique nonces
- Validate timestamps
- Track peer public keys

### Server Responsibilities
- Verify all message signatures
- Check for replay attacks
- Validate timestamp freshness
- Route messages to handlers
- Return proper error responses

### Retry Logic
- Initial retry: 1 second
- Exponential backoff: 2x per retry
- Max retries: 3
- Max delay: 30 seconds

## Versioning

This is protocol version 0.1 (initial release).

Future versions will add:
- End-to-end payload encryption (v0.2)
- Session management (v0.3)
- Token economy integration (v0.4)
- Chunked messages (v0.5)

## References

- Ed25519: https://ed25519.cr.yp.to/
- NaCl/libsodium: https://nacl.cr.yp.to/
- RFC 8032: EdDSA Signatures

---

Status: Draft  
Last Updated: 2026-02-01  
Author: Open Entity
