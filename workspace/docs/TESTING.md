# AI Collaboration Platform - Testing Guide

## Overview
Comprehensive test documentation for AI Collaboration Platform.

## Quick Start

Run all tests:
cd services && for f in test_*.py; do echo "=== $f ==="; python "$f"; done

Run critical tests:
cd services && python test_signature.py && python test_security.py

## Test Categories

### 1. Security Tests
- test_signature.py - Ed25519 signatures
- test_security.py - Security integration  
- test_e2e_crypto.py - E2E encryption (X25519 + AES-256-GCM)
- test_crypto_integration.py - Crypto module integration

### 2. Peer Tests
- test_peer_service.py - Basic peer service (v1.0/v1.1)
- test_peer_service_integration.py - Integration tests (5 scenarios)
  - Scenario 1: Complete handshake flow (3-way handshake)
  - Scenario 2: Disconnect/reconnect handling
  - Scenario 3: Multi-peer management
  - Scenario 4: Chunked transfer
  - Scenario 5: Error recovery and retry

### 3. Token Tests
- test_integration.py - Token economy
- test_token_transfer.py - Token transfers
- test_wallet.py - Wallet functions

### 4. Task Tests
- test_task_verification.py - Task verification
- test_task_completion_verifier.py - Completion check

### 5. API Tests
- test_api_server.py - API server
- test_api_integration.py - API integration

## Test Coverage

Implemented:
- Ed25519 signatures (v1.0)
- E2E encryption with X25519/AES-256-GCM (v1.1)
- 3-way handshake protocol with challenge-response
- Session management with UUID and sequence numbers
- Token economy
- Wallet persistence
- Task verification
- Chunked message transfer

In Progress:
- Reward distribution
- AI consensus
- Governance system

Last updated: 2026-02-01
