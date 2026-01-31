# WebSocket Implementation Plan
**Created:** 2026-02-01 01:20 JST
**Status:** Ready for Implementation
**Assigned to:** coder

## Overview
Implementation plan for WebSocket real-time communication (M1).

## Phase 1: Server-Side WebSocket (api_server.py)

### Tasks
1. Add WebSocket endpoint `/ws/v1/peers`
2. Implement WebSocketManager class
3. Integrate with existing session management
4. Support dual-stack (HTTP + WebSocket)

### Files to Modify
- services/api_server.py (+200 lines)
- services/websocket_manager.py (new file, +100 lines)

### Implementation Details
See docs/websocket_design_v2.md for full specification.

## Next Steps
1. Implement Phase 1
2. Phase 2: Client integration (peer_service.py)
3. Phase 3: Protocol v1.2 documentation
4. Phase 4: Testing

## Blockers
- Rate limit reached for coder agent
- Retry after cooldown
