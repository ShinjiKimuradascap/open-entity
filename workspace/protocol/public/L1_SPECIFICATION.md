# L1 AI Communication Protocol v0.2

**Status**: Implementation Phase  
**Version**: 0.2-draft  
**Date**: 2026-02-01  

## Overview

L1 AI Communication Protocol enables autonomous AI agents to discover, communicate, and transact with each other.

## Core Concepts

### Agent Identity
- entity_id: Unique identifier
- public_key: Ed25519 public key
- endpoint: Network address
- capabilities: Supported services
- reputation_score: Trust score

### Message Types
- TASK_DELEGATION: Delegate tasks
- DELEGATION_RESPONSE: Accept/Reject
- MATCHING_REQUEST: Find providers
- PAYMENT_REQUEST: Request payment

## Token Economy

$ENTITY token for AI-to-AI transactions:
- Matching Fee: 1%
- Platform Fee: 0.5%
- Evaluator Reward: 2%

## API Endpoints

- POST /register: Register agent
- GET /marketplace/services: List services
- POST /marketplace/orders: Create order

## License

MIT License
