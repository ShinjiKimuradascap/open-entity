# Connection Pooling Design for Peer Service v1.2

## Current Issue
Currently, peer_service.py creates a new aiohttp.ClientSession for every request.
This is inefficient for high-frequency peer communication.

## Proposed Solution

### 1. ConnectionPoolManager Class
Manage pooled HTTP connections for peer communication with:
- Total connection limit (default 100)
- Per-peer connection limit (default 10)
- Keep-alive timeout (default 30s)
- DNS cache TTL (default 300s)

### 2. Integration Points
- Add ConnectionPoolManager to PeerService.__init__
- Share across all HTTP operations
- Replace per-request session creation

### 3. Configuration Options
- enabled: bool
- limit: int
- limit_per_host: int
- keepalive_timeout: int
- enable_http2: bool (future)

### 4. Benefits
- Reduced connection overhead
- Connection reuse between peers
- Better resource management
- Improved throughput

## Implementation Priority
1. Create ConnectionPoolManager class
2. Integrate into PeerService
3. Add configuration options
4. Performance testing

Last Updated: 2026-02-01
