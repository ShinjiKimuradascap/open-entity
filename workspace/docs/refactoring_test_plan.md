# Refactoring Test Plan

## Current Test Coverage

Existing tests for _send_with_retry:
- test_send_with_retry: Success case, server error (500), connection error
- test_send_with_retry_non_retryable: 404, 403, 400 status codes

## Refactored Test Requirements

After refactoring (_send_with_retry -> _execute_send), following tests needed:

### 1. _execute_send Tests

| Test Case | Expected Behavior |
|-----------|-------------------|
| Success (200) | Return SendResult(success=True, status=200) |
| Server Error (500, 502, 503) | Retry 3 times, then fail |
| Non-retryable (400, 401, 403, 404) | Immediate fail, no retry |
| Connection Error | Retry with exponential backoff |
| Timeout Error | Retry with exponential backoff |

### 2. _update_delivery_stats Tests

| Test Case | Expected Behavior |
|-----------|-------------------|
| Success | Increment successful_deliveries, update last_seen, set is_healthy=True |
| Failure | Increment failed_deliveries, set last_error, set is_healthy=False, enqueue to queue |
| First time peer | Initialize PeerStats automatically |

### 3. _should_chunk Tests

| Test Case | Expected Behavior |
|-----------|-------------------|
| Payload < threshold | Return False |
| Payload > threshold | Return True |
| message_type == "chunk" | Always return False |
| Serialization error | Return False (graceful handling) |

### 4. send_message Integration Tests

| Test Case | Expected Behavior |
|-----------|-------------------|
| Unknown peer | Return False, log error |
| Chunked message | Delegate to send_chunked_message |
| Normal message | Create message, execute send, update stats |
| Auto-chunk disabled | Skip chunk check |

### 5. ClientSession Reuse Tests

| Test Case | Expected Behavior |
|-----------|-------------------|
| Multiple sends | Use same session instance |
| Session closed | Reinitialize on next send |
| Service cleanup | Close session properly |

## Test Migration Plan

| Current Test | Refactored Test | Priority |
|--------------|-----------------|----------|
| test_send_with_retry | test_execute_send_success | High |
| test_send_with_retry | test_execute_send_server_error | High |
| test_send_with_retry | test_execute_send_connection_error | High |
| test_send_with_retry_non_retryable | test_execute_send_non_retryable | High |
| N/A (new) | test_update_delivery_stats_success | High |
| N/A (new) | test_update_delivery_stats_failure | High |
| N/A (new) | test_should_chunk | Medium |
| N/A (new) | test_clientsession_reuse | Medium |

## Notes

- ClientSession reuse requires async context manager support
- SendResult dataclass enables better test assertions
- Centralized stats update simplifies test setup