# P0 Critical Endpoints Test Plan
Priority: Critical | Timeline: Immediate

## Test Implementation Plan

### 1. /message/send (POST)
Purpose: Send message to another agent
Test Cases:
- Send message to valid agent
- Send to non-existent agent
- Send with invalid signature
- Send when rate limited

Dependencies: Mock PeerService, Mock Registry

### 2. /discover (GET)
Purpose: Discover available agents
Test Cases:
- List all registered agents
- Filter by capability
- Filter by status
- Empty registry returns empty list

Dependencies: Mock Registry with test data

### 3. /agent/{entity_id} (GET)
Purpose: Get agent information
Test Cases:
- Get existing agent info
- Get non-existent agent (404)
- Invalid entity_id format (400)

Dependencies: Mock Registry

### 4. /heartbeat (POST)
Purpose: Agent heartbeat update
Test Cases:
- Valid heartbeat from registered agent
- Heartbeat from unregistered agent
- Expired JWT token

Dependencies: Mock Registry, JWT auth

### 5. /unregister/{entity_id} (POST)
Purpose: Unregister agent
Test Cases:
- Unregister existing agent
- Unregister non-existent agent
- Unauthorized unregistration

Dependencies: Mock Registry, Auth middleware

## Implementation Order
1. /discover (simplest, no auth)
2. /agent/{entity_id} (simple lookup)
3. /heartbeat (auth required)
4. /unregister/{entity_id} (auth + destructive)
5. /message/send (most complex, external calls)
