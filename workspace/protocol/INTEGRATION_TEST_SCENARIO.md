# Peer-to-Peer Communication Integration Test Scenario

## Overview

This document describes the integration test scenarios for secure peer-to-peer communication between Entity A and Entity B using the Peer Communication Protocol v0.3.

**Test Scope:**
- Ed25519 signature verification
- X25519 + AES-256-GCM encryption/decryption
- JWT session authentication (EdDSA)
- Replay attack prevention
- Error handling for security violations

**Reference Implementation:** services/test_peer_service.py

---

## Prerequisites

### 1. Environment Setup

| Requirement | Value | Description |
|-------------|-------|-------------|
| Python | 3.9+ | Runtime environment |
| Dependencies | cryptography, pyjwt, aiohttp | Install via pip install -r requirements.txt |
| Network | localhost | Both entities on same machine for testing |

### 2. Key Generation

Generate Ed25519 and X25519 keypairs for both entities using generate_entity_keypair() from crypto_utils.

### 3. Environment Variables

For Entity A:
- ENTITY_ID="entity-a"
- ENTITY_PRIVATE_KEY=<hex-encoded-private-key-a>
- PEER_SERVICE_PORT=8001

For Entity B:
- ENTITY_ID="entity-b"
- ENTITY_PRIVATE_KEY=<hex-encoded-private-key-b>
- PEER_SERVICE_PORT=8002

### 4. Network Configuration

| Entity | Address | Port | Endpoint |
|--------|---------|------|----------|
| Entity A | http://localhost | 8001 | /message |
| Entity B | http://localhost | 8002 | /message |

---

## Test Cases

### TC-01: Basic Signed Message Exchange

**Objective:** Verify Ed25519 signature creation and verification between two entities.

**Preconditions:**
- [ ] Both entities have generated Ed25519 keypairs
- [ ] Entity A knows Entity B's public key
- [ ] Entity B knows Entity A's public key

**Test Steps:**
1. Entity A creates a message payload with type, data, and from fields
2. Entity A signs the message using crypto_manager.sign_message()
3. Entity A sends message to Entity B
4. Entity B verifies the signature using verify_signature()

**Expected Results:**
- [ ] Signature is created successfully (Base64 string, ~88 chars)
- [ ] Signature verification returns True
- [ ] Tampered payload fails verification

**Pass Criteria:** All assertions pass

---

### TC-02: Encrypted Message Exchange (X25519 + AES-256-GCM)

**Objective:** Verify end-to-end encryption using X25519 key exchange and AES-256-GCM.

**Preconditions:**
- [ ] Both entities have generated X25519 keypairs
- [ ] Shared keys have been derived via ECDH

**Test Steps:**
1. Entity B generates X25519 keypair using generate_x25519_keypair()
2. Entity A derives shared key using derive_shared_key()
3. Entity A encrypts payload using encrypt_payload()
4. Entity B derives shared key and decrypts using decrypt_payload()

**Expected Results:**
- [ ] Ciphertext is Base64 encoded
- [ ] Nonce is 128-bit (16 bytes, Base64 ~24 chars)
- [ ] Decrypted payload matches original exactly

**Pass Criteria:** assert decrypted == payload

---

### TC-03: JWT-Authenticated Session

**Objective:** Verify JWT token generation and verification using EdDSA (Ed25519).

**Preconditions:**
- [ ] Both entities have Ed25519 keypairs
- [ ] Entity B knows Entity A's public key

**Test Steps:**
1. Entity A creates JWT token using create_jwt_token(audience="entity-b")
2. Entity A sends token with message to Entity B
3. Entity B verifies JWT using verify_jwt_token()

**Expected Results:**
- [ ] JWT has 3 parts separated by dots (header.payload.signature)
- [ ] Decoded claims include: sub, iat, exp, iss
- [ ] sub claim equals "entity-a"
- [ ] aud claim equals "entity-b"
- [ ] Token expiry is 5 minutes from iat

**Pass Criteria:** decoded is not None and all claims match

---

### TC-04: Replay Attack Prevention Test

**Objective:** Verify that replay attacks are detected and rejected.

**Preconditions:**
- [ ] CryptoManager initialized with replay protection enabled
- [ ] Timestamp tolerance: +/-60 seconds
- [ ] Replay detection window: 5 minutes

**Test Steps:**
1. Entity A creates message with nonce and timestamp
2. Entity B receives and validates using check_and_record_nonce()
3. Attacker replays same message with identical nonce
4. Test edge cases: old timestamp (120s past), future timestamp (120s future)

**Expected Results:**
- [ ] First nonce check returns True
- [ ] Replay attempt returns False
- [ ] Old timestamp (>60s) returns False
- [ ] Future timestamp (>60s) returns False

**Pass Criteria:** All replay attempts rejected

---

### TC-05: Error Handling - Tampered Message

**Objective:** Verify proper rejection of tampered messages.

**Preconditions:**
- [ ] Valid signed message exists
- [ ] Signature verification enabled

**Test Steps:**
1. Entity A creates and signs valid message
2. Attacker modifies payload data field after signing
3. Entity B attempts verification with tampered payload

**Expected Results:**
- [ ] Signature verification returns False
- [ ] Message is rejected
- [ ] Error reason indicates signature mismatch

**Pass Criteria:** Tampered message fails verification

---

### TC-06: Error Handling - Expired JWT

**Objective:** Verify rejection of expired JWT tokens.

**Preconditions:**
- [ ] Ability to create tokens with custom timestamps

**Test Steps:**
1. Create expired JWT payload with iat 10 minutes ago and exp 5 minutes ago
2. Sign with EdDSA algorithm
3. Entity B attempts verification

**Expected Results:**
- [ ] Verification returns None (failure)
- [ ] Expired token is rejected silently

**Pass Criteria:** assert result is None

---

## Step-by-Step Test Execution Guide

### Phase 1: Setup (Terminal 1 and 2)

Terminal 1 - Entity A:
- cd /home/moco/workspace
- export ENTITY_ID="entity-a"
- export ENTITY_PRIVATE_KEY (generate using crypto_utils)
- Initialize service on port 8001

Terminal 2 - Entity B:
- cd /home/moco/workspace
- export ENTITY_ID="entity-b"
- export ENTITY_PRIVATE_KEY (generate using crypto_utils)
- Initialize service on port 8002

### Phase 2: Run Test Suite

Run: python3 services/test_peer_service.py

Expected: All security tests completed message

### Phase 3: Manual Verification

1. Check public key exchange using get_public_keys()
2. Verify peer registration using add_peer() and list_peers()
3. Health check using health_check()

---

## Expected Results Summary

| Test Case | Expected Result | Status |
|-----------|-----------------|--------|
| TC-01 Basic Signed Message | Signature verified: True | PASS |
| TC-02 Encrypted Exchange | Payload decrypted matches original | PASS |
| TC-03 JWT Session | Token valid, claims correct | PASS |
| TC-04 Replay Prevention | Duplicate nonce rejected | PASS |
| TC-05 Tampered Message | Signature verification fails | PASS |
| TC-06 Expired JWT | Token rejected | PASS |

### Security Validation Checklist

- [ ] Ed25519 signatures cannot be forged
- [ ] X25519 shared keys are identical on both sides
- [ ] AES-256-GCM encryption produces different ciphertexts for same payload
- [ ] JWT expiry is strictly enforced (5 minutes)
- [ ] Nonce replay is detected within 5-minute window
- [ ] Timestamps outside +/-60s tolerance are rejected
- [ ] Tampered payloads fail signature verification

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Signature verification failed | Key mismatch | Verify public keys are exchanged correctly |
| Nonce already seen | Clock skew | Synchronize system clocks (NTP) |
| JWT expired | Clock drift | Check system time on both entities |
| Decryption failed | Wrong shared key | Ensure X25519 keypairs are generated before ECDH |
| Connection refused | Service not running | Start both services before testing |

---

## References

- Protocol Specification: protocol/peer_protocol_v03.md
- Implementation Guide: protocol/IMPLEMENTATION_GUIDE.md
- Test Implementation: services/test_peer_service.py
- Crypto Utilities: services/crypto_utils.py
- Peer Service: services/peer_service.py

---

Created: 2026-02-01
Version: 0.3
Protocol Version: v0.3
