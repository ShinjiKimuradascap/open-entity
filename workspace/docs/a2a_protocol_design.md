# A2A Protocol Design

## Overview
AI-to-AI communication protocol for autonomous agent coordination.

## Message Types

### Task Delegation
- delegation_id: UUID
- from_agent: Agent ID
- to_agent: Agent ID  
- task: Task details
- signature: Ed25519 signature

### Status Update
- delegation_id: UUID
- state: pending/accepted/running/completed/failed
- progress_percent: 0-100
- deliverables: List of artifacts

### Heartbeat
- agent_id: Agent ID
- healthy: boolean
- active_tasks: count
- timestamp: ISO8601

## State Machine
PENDING -> ACCEPTED -> RUNNING -> COMPLETED
   |          |          |          |
   v          v          v          v
REJECTED   CANCELLED    FAILED

## Security
- Ed25519 signatures required
- E2E encryption via Peer Protocol v1.1
- Public keys in DHT registry

## Future
- v1.1: Reputation system, incentives
- v2.0: Smart contract integration

Version: 1.0-draft
Last Updated: 2026-02-01
