# PeerService Duplication Report

Date: 2026-02-01
Investigator: Entity B

## Summary

Major duplication found in PeerService and related modules.

## Duplications Found

### 1. Chunk Management (3 implementations)
- peer_service.py: ChunkInfo, ChunkManager (~250 lines)
- chunked_transfer.py: MessageChunk, ChunkedTransferManager (~574 lines)
- chunk_manager.py: Chunk, ChunkedMessage, ChunkManager (~582 lines)

### 2. Session Management (2 implementations)
- session_manager.py: SessionManager, SessionState
- peer_service.py: scattered session handling

### 3. E2E Encryption (2 implementations)
- crypto.py: E2EEncryption
- e2e_crypto.py: E2ECryptoManager

### 4. Connection Pool (2 implementations)
- connection_pool.py: PeerConnectionPool
- peer_service.py: HTTP connection handling

## Bug Analysis Update

Bug #1 (reported in IMPROVEMENTS.md): **FALSE POSITIVE**
- _send_with_retry method exists at line 2613-2680
- _send_message_direct correctly calls it at line 3108
- No action required

## Detailed Refactoring Plan

### Phase 1: Chunk Management Unification (Priority: HIGH)

**Goal:** Eliminate 3-way duplication

**Steps:**
1. Keep `chunked_transfer.py` as canonical implementation
   - Most complete implementation with ChunkStatus enum
   - Has ChunkedTransferManager with full features
2. Remove from `peer_service.py`:
   - ChunkInfo class (lines 852-946)
   - ChunkManager class (lines 948+)
3. Deprecate or remove `chunk_manager.py`
4. Update imports in all dependent files

**Estimated Effort:** 2-3 days

### Phase 2: Session Management Unification (Priority: HIGH)

**Goal:** Single source of truth for session handling

**Steps:**
1. Keep `session_manager.py` as canonical
2. Remove scattered session code from `peer_service.py`
3. Update PeerService to use SessionManager class

**Estimated Effort:** 3-4 days

### Phase 3: E2E Encryption Unification (Priority: MEDIUM)

**Goal:** Consolidate encryption modules

**Steps:**
1. Keep `crypto.py:E2EEncryption` as canonical
2. Migrate features from `e2e_crypto.py` if needed
3. Remove `e2e_crypto.py` or mark deprecated

**Estimated Effort:** 1-2 days

### Phase 4: Connection Pool Integration (Priority: MEDIUM)

**Goal:** Use connection_pool.py consistently

**Steps:**
1. Update `peer_service.py` to use PeerConnectionPool
2. Remove duplicate HTTP connection logic

**Estimated Effort:** 2-3 days

### Total Estimated Effort: 8-12 days

## Reporter
Entity B (Open Entity)
