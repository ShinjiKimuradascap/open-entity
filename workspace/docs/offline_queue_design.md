# Persistent Offline Message Queue Design

## Overview
Persistent message queue for offline peers using SQLite.

## Features
- Message persistence with SQLite
- Automatic delivery when peer comes online
- Exponential backoff retry
- Expired message cleanup

## Implementation
- File: services/persistent_offline_queue.py
- Test: services/test_persistent_offline_queue.py

## Next Steps
1. Implement persistent_offline_queue.py
2. Create tests
3. Integrate with PeerService
