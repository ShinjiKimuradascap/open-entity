# Integration Test Plan - Post SessionManager Integration

## Test Scope
Verify SessionManager integration with PeerService works correctly.

## Test Categories

### 1. Session Lifecycle Tests
- Session creation on handshake
- Session validation on messages
- Session expiration
- Session cleanup

### 2. Message Flow Tests
- All message types with session_id
- Message rejection without valid session
- Session renewal

### 3. Performance Tests
- Concurrent sessions
- Session cleanup under load
- Memory usage

### 4. Error Handling Tests
- Invalid session_id
- Expired session
- Session hijacking attempt

## Test Cases

### TC1: Basic Session Creation
Input: peer_id, public_key
Expected: session_id returned, session stored

### TC2: Message with Valid Session
Input: message with valid session_id
Expected: message processed

### TC3: Message without Session
Input: message without session_id
Expected: rejected with error

### TC4: Session Expiration
Input: wait for TTL
Expected: session removed, new handshake required

### TC5: Concurrent Sessions
Input: 100 simultaneous sessions
Expected: all sessions managed correctly

## Test Environment
- Docker container
- Isolated network
- Mock peers

## Success Criteria
- All unit tests pass
- Integration tests pass
- No memory leaks
- Performance within thresholds

Last Updated: 2026-02-01
Status: Draft