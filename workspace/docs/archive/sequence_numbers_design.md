# Sequence Numbers Design

## Overview
Per-session message ordering and deduplication mechanism.

## Current State
- SessionInfo.sequence_num field exists (line 1473)
- Not used in message flow

## Design Goals
1. Message ordering guarantee
2. Duplicate detection
3. Missing message detection
4. Out-of-order handling

## Sequence Number Rules
- Monotonically increasing per session
- Start from 1 after handshake
- Increment for each message sent
- Included in all message headers

## Gap Handling
- Buffer out-of-order messages
- Request missing sequences
- Timeout-based retry

## Integration Points
1. PeerService.send_message()
2. MessageRouter.route_message()
3. SessionManager

## Tasks
- Add sequence_num to headers
- Implement sender increment
- Implement receiver validation
- Add gap detection
- Unit tests

Last Updated: 2026-02-01
Status: Design Draft