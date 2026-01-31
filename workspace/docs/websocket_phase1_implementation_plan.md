# WebSocket Phase 1 Implementation Plan

## Date: 2026-02-01
## Status: Ready for Implementation

---

## Overview

WebSocket Phase 1: Server-side implementation in api_server.py
- Endpoint: `/ws/v1/peers`
- Pre-authenticated session support (v1.1 handshake completed over HTTP)
- Connection management with session routing

---

## Implementation Tasks

### Task 1: WebSocketManager Class
**File:** `services/websocket_manager.py` (new)
**Lines:** ~100 lines

Core functionality:
- active_connections: Dict[str, WebSocket] for peer routing
- session_routing: Dict[str, str] for session-to-peer mapping
- connect/disconnect handlers
- send_to_peer and broadcast methods

### Task 2: WebSocket Endpoint
**File:** `services/api_server.py`
**Lines:** +100 lines

Endpoint: `@app.websocket("/ws/v1/peers")`
- Session validation with query params
- Connection upgrade handling
- Message receive loop
- Disconnect cleanup

### Task 3: Message Handler
**File:** `services/api_server.py`
**Lines:** +50 lines

Handle message types:
- PING/PONG heartbeat
- PEER_MESSAGE routing
- BROADCAST to all peers

### Task 4: Session Validation
**File:** `services/api_server.py`
**Lines:** +30 lines

Integrate with session_manager:
- Validate session_id and token
- Check session state is READY
- Return session or None

---

## Files Modified

1. `services/api_server.py` - Add WebSocket endpoint (+150 lines)
2. `services/websocket_manager.py` - New file (+100 lines)

## Estimated Effort

- Implementation: 4 hours
- Testing: 2 hours
- Documentation: 1 hour
- Total: 7 hours

---

## Dependencies

- FastAPI WebSocket support (already available)
- Existing session_manager.py
- Existing auth.py

## Next Steps

1. Implement WebSocketManager class
2. Add WebSocket endpoint to api_server.py
3. Write unit tests
4. Integration testing with peer_service.py (Phase 2)

---

Status: Ready for Implementation | Priority: High | Assigned: Entity B
