# Peer Communication Protocol v0.2

## Message Types

### status_report
Task completion report

### wake_up
Wake up peer request

### task_delegate
Delegate task to peer

### discovery
Service discovery

## Rules
1. Report status after task completion
2. Wake up peer if timeout
3. Idempotent task execution
