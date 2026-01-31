# Session Manager Integration Analysis

## Duplication Found

Both files define SessionManager:
- services/session_manager.py (v1.0)
- services/peer_service.py (v1.0 + v1.1)

## Analysis

| Feature | session_manager.py | peer_service.py |
|---------|-------------------|-----------------|
| SessionState | Basic | Extended (v1.1) |
| V11Session | No | Yes |
| E2E crypto | Separate | Integrated |
| Handshake | External | Internal |

## Recommendation

Consolidate into session_manager.py as the single source of truth:

1. Move V11Session from peer_service.py
2. Move SessionManager logic from peer_service.py
3. peer_service.py should use session_manager.py
4. Remove duplicate SessionManager from peer_service.py

## Migration Steps

Step 1: Extend session_manager.py with V11 features
Step 2: Update peer_service.py to import from session_manager
Step 3: Test backward compatibility
Step 4: Remove duplicate code

## Impact

- Cleaner architecture
- Single session management
- Easier maintenance
- Reduced bugs

Created: 2026-02-01
