# Performance Optimization Plan

## Current Components

### Connection Pool (1225 lines)
- HTTP keep-alive pooling
- Circuit breaker pattern
- Per-peer connection limits
- Health checking

### Rate Limiter (610 lines)
- Token bucket algorithm
- Per-endpoint limits
- Client-based throttling

## Optimization Targets

### 1. Connection Pool Tuning
- Current: Default 3 connections per peer
- Target: Dynamic based on latency
- Metric: Connection acquisition time < 100ms

### 2. Rate Limiter Enhancement
- Current: In-memory only
- Target: Redis backend option
- Metric: 10k req/s per instance

### 3. Message Serialization
- Current: JSON
- Target: CBOR or MessagePack
- Metric: 50% size reduction

### 4. Async Optimization
- Profile coroutine scheduling
- Reduce context switches
- Optimize hot paths

## Implementation Priority

### Phase 1: Measurement
- Add performance metrics
- Benchmark current state
- Identify bottlenecks

### Phase 2: Serialization
- CBOR implementation
- Backward compatibility
- Migration strategy

### Phase 3: Scaling
- Redis rate limiter
- Cluster support
- Load balancing

## Success Metrics
- Latency p99 < 100ms
- Throughput > 1000 msg/s
- Memory usage stable

Status: Planning
Last Updated: 2026-02-01
