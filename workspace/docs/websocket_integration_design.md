# WebSocket Phase 2: peer_service.py Client Integration Design

## Overview

This design document defines the integration of WebSocket client functionality into PeerService.

- Current State: PeerService is implemented as an HTTP client using aiohttp
- Goal: Make WebSocket the preferred transport with HTTP as fallback

## 1. Current State Analysis

### 1.1 HTTP Communication Implementation (peer_service.py)

Key Methods and Line Ranges:

| Method | Lines | Description |
|--------|-------|-------------|
| send_message() | 3003-3090 | Main send method with auto-chunking support |
| _send_with_retry() | 2825-2891 | HTTP POST with retry logic |
| _send_message_direct() | 3402-3421 | Direct send for queue |
| send_chunked_message() | 3218-3298 | Chunked transfer for large messages |
| _ping_peer() | 3423-3443 | Heartbeat ping |

HTTP Send Flow:
- send_message() calls _should_use_chunking() for check
- Then _prepare_payload() for E2E encryption
- Then _get_session_info() to get session
- Then _create_message_dict() to create message
- Finally _send_with_retry() for HTTP POST via aiohttp.ClientSession.post()

### 1.2 Existing WebSocket Implementation

websocket_client.py (Client-side):
- WebSocketPeerClient class at line 109
- WebSocketClientRegistry class at line 582
- Auto-reconnect, heartbeat, message signing support
- Built-in HTTP fallback

websocket_manager.py (Server-side):
- WebSocketManager class at line 114
- FastAPI integration, session management, rate limiting
- Protocol v1.1 support

## 2. Integration Design

### 2.1 Architecture Overview

PeerService has:
- HTTP Client (existing)
- WebSocket Client (new)
- Transport Selector (WebSocket preferred)
  - WebSocket Server as primary
  - HTTP Server as fallback

### 2.2 New Components

TransportLayer Class:
- Unified transport layer with WebSocket preferred, HTTP fallback
- Uses WebSocketClientRegistry from websocket_client.py
- Integrates aiohttp session management

TransportPreference Enum values:
- WEBSOCKET_ONLY
- WEBSOCKET_FIRST (default)
- HTTP_FIRST
- HTTP_ONLY

### 2.3 PeerService Modifications

Constructor Changes at line ~1686:
- Add enable_websocket parameter
- Add transport_preference parameter
- Initialize TransportLayer

send_message() Changes at line ~3003:
- Add prefer_websocket parameter with default True
- Try WebSocket first if enabled
- Fallback to HTTP on failure

New Methods to add:
- _get_websocket_url(): Derive WS URL from HTTP URL
- init_websocket_connection(): Explicit WS connect
- close_websocket_connection(): Close WS connection

## 3. Implementation Steps

Phase 2.1: TransportLayer Implementation
- Create services/transport_layer.py
- Implement TransportLayer class
- Define TransportPreference enum

Phase 2.2: PeerService Integration
- Modify constructor at line ~1686
- Modify send_message() at line ~3003
- Add new helper methods

Phase 2.3: Configuration
- Create config/peer_service.yaml
- Define transport preferences

Phase 2.4: Testing
- Create tests/test_transport_layer.py
- Create tests/test_peer_service_websocket.py

## 4. API Compatibility

### 4.1 Backward Compatibility
- Existing send_message() calls work unchanged
- HTTP fallback always available
- http_only mode for pure legacy behavior

### 4.2 New API Usage Examples:

Explicit WebSocket connection:
    await peer_service.init_websocket_connection("peer-123")

Force WebSocket usage:
    await peer_service.send_message(
        target_id="peer-123",
        message_type="task",
        payload={"action": "execute"},
        prefer_websocket=True
    )

Force HTTP usage:
    await peer_service.send_message(
        target_id="peer-123",
        message_type="task",
        payload={"action": "execute"},
        prefer_websocket=False
    )

## 5. Error Handling

| Scenario | Behavior |
|----------|----------|
| WebSocket not connected | Fallback to HTTP |
| WebSocket disconnect detected | Try auto-reconnect, fallback to HTTP |
| WebSocket send failure | Fallback to HTTP |
| HTTP 4xx error | No retry, return error |
| HTTP 5xx error | Retry, then return error |

## 6. Timeline

| Phase | Effort | Description |
|-------|--------|-------------|
| 2.1 | 1 day | TransportLayer implementation |
| 2.2 | 1 day | PeerService integration |
| 2.3 | 0.5 day | Configuration |
| 2.4 | 1 day | Testing |
| Total | 3.5 days | |

## 7. Implementation Files

| File | Type | Description |
|------|------|-------------|
| services/transport_layer.py | New | TransportLayer class |
| services/peer_service.py | Modify | WebSocket integration |
| config/peer_service.yaml | New | Configuration file |
| tests/test_transport_layer.py | New | Unit tests |
| tests/test_peer_service_websocket.py | New | Integration tests |

## 8. Key Design Decisions

### 8.1 Transport Selection Strategy
- Default: Try WebSocket first, fallback to HTTP
- Configurable per-message via prefer_websocket parameter
- Global setting via transport_preference constructor parameter

### 8.2 Connection Management
- Use existing WebSocketClientRegistry for connection pooling
- Lazy connection establishment on first send
- Explicit connection management available via init/close methods

### 8.3 Message Format Compatibility
- Use existing message format (_create_message_dict)
- Both WebSocket and HTTP use same message structure
- Protocol versioning maintained

## 9. References

- services/websocket_client.py - Existing WebSocket client (lines 109-724)
- services/websocket_manager.py - Server-side WebSocket manager (lines 114-655)
- services/peer_service.py - HTTP implementation:
  - Lines 2825-2891: _send_with_retry()
  - Lines 3003-3090: send_message()
- docs/websocket_design_v2.md - WebSocket design document
