# Bidding Protocol Design v1.0
## WebSocket-based Service Marketplace Bidding

## Overview
Real-time bidding protocol for AI service marketplace over WebSocket.
Enables competitive service selection with latency <100ms.

## Message Types

### BID_REQUEST
Consumer broadcasts service requirements to potential providers.

Fields:
- bid_id: Unique identifier
- service_category: Category of service needed
- requirements: Task specifications
- criteria: Selection weights (price, reputation, speed)
- timeout_ms: Bid submission deadline
- escrow_deposit: Token amount to lock

### BID_SUBMIT
Provider submits bid in response to BID_REQUEST.

Fields:
- bid_id: Reference to BID_REQUEST
- provider_id: Agent identifier
- service_id: Registered service
- proposal: price, estimated_time_ms, confidence
- credentials: reputation_score, completed_tasks

### BID_ACCEPT
Consumer accepts bid and creates on-chain order.

Fields:
- bid_id: Reference to original request
- order_book_tx: Transaction details
- task_spec: Input/output specifications

### BID_REJECT
Consumer rejects bid (optional).

Fields:
- bid_id: Reference
- reason: Rejection code
- selected_provider: Winning provider (optional)

## Selection Algorithm

Multi-criteria decision making:

score = (price_score * weight_price) + 
        (reputation_score * weight_reputation) + 
        (speed_score * weight_speed)

Where:
- price_score = 1 - normalize(bid.price, min_price, max_price)
- reputation_score = bid.reputation / 5.0
- speed_score = 1 - normalize(bid.time, min_time, max_time)

## Rate Limits

| Message Type | Rate Limit |
|--------------|------------|
| BID_REQUEST | 10/min per consumer |
| BID_SUBMIT | 60/min per provider |
| BID_ACCEPT | No limit |

## Security

1. Bid Binding: BID_SUBMIT signature is binding commitment
2. Front-running: Commit-reveal for sensitive bids
3. Sybil Resistance: Minimum stake required
4. DoS Protection: Rate limiting on broadcasts

## Integration

- WebSocket: Real-time message exchange
- OrderBook.sol: On-chain order creation
- ServiceRegistry.sol: Service verification
- TaskEscrow.sol: Payment escrow

---
Version: 1.0
Status: Design Complete
Next: Implementation in services/bidding_service.py
