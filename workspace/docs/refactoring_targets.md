# Refactoring Targets

## Duplicated Code

### ExponentialBackoff (4 locations)
- moltbook_integration.py
- peer_monitor.py
- peer_service.py (x2)

### ProtocolError (2 locations)
- e2e_crypto.py
- crypto.py

## Priority
1. Extract ExponentialBackoff to utils
2. Consolidate ProtocolError
3. Create common error module

Status: Analysis Complete
