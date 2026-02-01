# WebSocket Phase 2: Implementation Changes List

## Summary

This document lists all planned changes for WebSocket integration into peer_service.py.

## Files to Modify

### 1. services/peer_service.py

#### 1.1 Constructor Changes (around line 1686)

Add new parameters:
- enable_websocket: bool = True
- transport_preference: str = "websocket_first"

Add new attributes:
- self._transport: Optional[TransportLayer] = None
- self._enable_websocket: bool
- self._transport_preference: TransportPreference

Add initialization:
- self._init_transport_layer() call if enable_websocket is True

#### 1.2 send_message() Changes (around line 3003)

Add new parameter:
- prefer_websocket: bool = True

Add WebSocket send path before HTTP fallback:
- Check if WebSocket enabled and prefer_websocket is True
- Call transport_layer.send_message()
- On success: return True
- On failure with WEBSOCKET_ONLY preference: return False
- On failure with WEBSOCKET_FIRST preference: continue to HTTP

#### 1.3 New Methods to Add

Method 1: _init_transport_layer()
- Location: After __init__ or in _init_crypto section
- Purpose: Initialize TransportLayer instance

Method 2: _get_websocket_url(peer_id: str)
- Location: Helper methods section
- Purpose: Convert HTTP URL to WebSocket URL
- Logic: http:// -> ws://, https:// -> wss://, add /ws/v1/peers path

Method 3: init_websocket_connection(peer_id, jwt_token)
- Location: Public methods section
- Purpose: Explicitly establish WebSocket connection to peer

Method 4: close_websocket_connection(peer_id)
- Location: Public methods section
- Purpose: Close WebSocket connection to peer

Method 5: _update_transport_stats(target_id, result)
- Location: Stats management section
- Purpose: Update peer_stats with transport information

### 2. New Files to Create

#### 2.1 services/transport_layer.py

Classes to implement:
- TransportLayer: Main transport abstraction
- TransportPreference: Enum for preference settings
- TransportResult: Dataclass for send results
- TransportStats: Dataclass for statistics

Methods for TransportLayer:
- __init__(entity_id, private_key, websocket_config, http_config)
- send_message(target_id, target_address, message, websocket_url)
- connect_websocket(peer_id, websocket_url, jwt_token)
- disconnect_websocket(peer_id)
- is_websocket_connected(peer_id)
- get_transport_stats()

#### 2.2 config/peer_service.yaml

Configuration sections:
- transport.preference
- transport.websocket settings
- transport.http settings

#### 2.3 tests/test_transport_layer.py

Test cases:
- WebSocket send success
- HTTP fallback on WebSocket failure
- Transport preference handling
- Connection management

#### 2.4 tests/test_peer_service_websocket.py

Test cases:
- PeerService with WebSocket enabled
- HTTP fallback behavior
- Backward compatibility (HTTP only mode)
- Explicit WebSocket connection management

## Change Summary by Line Numbers

| File | Line Range | Change Type | Description |
|------|------------|-------------|-------------|
| peer_service.py | 1686-1714 | Modify | Add WebSocket params to __init__ |
| peer_service.py | 1744-1750 | Add | Initialize _transport layer |
| peer_service.py | 3003-3012 | Modify | Add prefer_websocket param |
| peer_service.py | 3067-3072 | Add | WebSocket send path |
| peer_service.py | ~1850 | Add | _init_transport_layer() method |
| peer_service.py | ~3500 | Add | _get_websocket_url() method |
| peer_service.py | ~3600 | Add | init_websocket_connection() method |
| peer_service.py | ~3650 | Add | close_websocket_connection() method |

## Backward Compatibility

All changes maintain backward compatibility:
- New parameters have default values
- Existing code paths remain unchanged when WebSocket disabled
- HTTP fallback ensures reliability

## Implementation Order

1. Create services/transport_layer.py with TransportLayer class
2. Modify services/peer_service.py constructor
3. Modify services/peer_service.py send_message()
4. Add new helper methods to services/peer_service.py
5. Create configuration file
6. Create test files
7. Run tests and fix issues
