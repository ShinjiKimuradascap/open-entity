# Peer Communication Protocol v1.1

## Overview
AIエンティティ間の安全でスケーラブルな通信プロトコル。
v1.0からの拡張：6-stepハンドシェイク、強化された暗号化、分散型レジストリ

## 6-Step Enhanced Handshake

### Overview
v1.1では3-stepから6-stepハンドシェイクに拡張し、より強力な認証とセッション確立を実現。

### Handshake Flow

Step 1: Initiator → Responder: handshake_init
- ephemeral_pubkey_A
- challenge_A (32-byte random)
- supported_versions ["1.0", "1.1"]

Step 2: Responder → Initiator: handshake_response
- ephemeral_pubkey_B
- challenge_response_A (SHA256(challenge_A | ephemeral_B | static_B))
- challenge_B (32-byte random)
- selected_version: "1.1"

Step 3: Initiator → Responder: handshake_proof
- challenge_response_B (SHA256(challenge_B | ephemeral_A | static_A))
- session_params (encryption settings)
- encrypted_capabilities
- signature

Step 4: Responder → Initiator: handshake_ready
- session_confirmation (session_id, key fingerprint)
- encrypted_capabilities_ack
- signature

Step 5: Initiator → Responder: handshake_confirm
- final_confirmation (session_accepted)
- first_encrypted_message
- signature

Step 6: Responder → Initiator: handshake_complete
- session_established: true
- ready_for_traffic: true
- signature

## Security Features

### Required
- Ed25519 signatures on all messages
- X25519/AES-256-GCM E2E encryption after handshake
- Replay protection (nonce + timestamp + sequence)
- Perfect Forward Secrecy (ephemeral keys per session)
- Challenge-response authentication

## Error Codes

- INVALID_VERSION: Protocol version not supported
- INVALID_SIGNATURE: Message signature verification failed
- REPLAY_DETECTED: Replay attack detected
- HANDSHAKE_TIMEOUT: Handshake completion timeout
- CHALLENGE_FAILED: Challenge response invalid

Last Updated: 2026-02-01
