# M5 WebSocket Communication Layer Design

## Overview

M5フェーズでのL2 P2Pリアルタイム通信基盤としてWebSocketを導入し、HTTPポーリング方式からの移行を実現する。

## Requirements

### Functional Requirements
1. **Bidirectional Real-time Communication**: 双方向リアルタイム通信
2. **Connection Multiplexing**: 1つのWebSocket接続で複数のピアと通信
3. **Authentication**: JWT + Ed25519署名による認証
4. **Message Routing**: メッセージタイプに基づく適切なルーティング
5. **Fallback to HTTP**: WebSocket接続失敗時のHTTPフォールバック

### Non-Functional Requirements
1. **Latency**: < 50ms (HTTPポーリングの200ms→50ms)
2. **Throughput**: 1000+ メッセージ/秒
3. **Connection Stability**: 自動再接続、ハートビート
4. **Scalability**: 10,000+ 同時接続

## Architecture

### Components

- WebSocket Manager: 接続管理
- Server Handler: サーバー側WebSocketエンドポイント
- Client Handler: クライアント側WebSocket接続
- Message Broker: WebSocket/HTTP間のメッセージ仲介

### New Files

- services/websocket_manager.py: WebSocket接続管理
- services/websocket_server.py: サーバー側WebSocketエンドポイント
- services/websocket_client.py: クライアント側WebSocket接続

### Modified Files

- services/api_server.py: WebSocketエンドポイント追加
- services/peer_service.py: WebSocketクライアント統合
- services/message_router.py: WebSocket経由のメッセージ対応

## Protocol

### WebSocket URL

ws://host:port/ws/v1/peers?entity_id={entity_id}&token={jwt_token}
wss://host:port/ws/v1/peers?entity_id={entity_id}&token={jwt_token}

### Authentication Flow

1. GET /auth/token (entity_id, pubkey)
2. Server returns challenge (nonce)
3. POST /auth/verify (signature)
4. Server returns JWT token
5. ws://...?token={jwt}
6. Connection accepted

### Message Format

{
  "message_id": "uuid",
  "type": "HELLO|MESSAGE|ACK|HEARTBEAT|BYE",
  "from_entity": "entity_id",
  "to_entity": "entity_id|null",
  "timestamp": 1700000000,
  "payload": {...},
  "signature": "base64_ed25519_sig"
}

### Message Types

- HELLO: 接続開始時のハンドシェイク
- READY: サーバー準備完了通知
- MESSAGE: 通常のP2Pメッセージ
- ACK: メッセージ受信確認
- HEARTBEAT: 接続維持用ping/pong
- BYE: 正常終了通知
- ERROR: エラー通知

## Implementation Plan

### Phase 1: Server-Side Implementation (Week 1)

- api_server.pyにWebSocketエンドポイント追加
- websocket_manager.py実装 (ConnectionPool統合、メッセージルーティング、認証)

### Phase 2: Client-Side Implementation (Week 2)

- websocket_client.py実装 (接続確立、自動再接続、ハートビート)
- peer_service.py統合 (HTTPクライアントと並行動作、WebSocket優先)

### Phase 3: Protocol Update (Week 3)

- peer_protocol_v1.2.md作成
- WebSocketセクション追加、バージョンネゴシエーション

### Phase 4: Testing (Week 4)

- Unit Tests: 接続確立、メッセージ送受信、エラーハンドリング
- Integration Tests: Entity A ↔ Entity B通信、HTTPフォールバック

## API Changes

### New Endpoints

- /ws/v1/peers: メインP2P通信エンドポイント
- /ws/v1/events: ブロードキャストイベント用

### Updated Endpoints

- /peers/discover: WebSocket利用可能ピアを返す
- /peers/capabilities: WebSocket対応フラグ追加

## Migration Strategy

### Backward Compatibility

- HTTP APIは維持（非推奨化のみ）
- WebSocket非対応ピアはHTTPで通信
- Capability交換で使用プロトコル決定

### Rollout Plan

1. Stage 1: Entity AのみWebSocket対応（内部テスト）
2. Stage 2: Entity Bとの相互接続テスト
3. Stage 3: 本番環境デプロイ

## Security Considerations

- Authentication: JWT + Ed25519署名検証
- Authorization: エンティティ間の許可リスト
- Rate Limiting: 接続数・メッセージ数制限
- Encryption: wss:// (TLS) 必須
- Replay Protection: nonce + timestamp検証

## Performance Targets

| Metric | HTTP (Current) | WebSocket (Target) |
|--------|---------------|-------------------|
| Latency | 200ms | < 50ms |
| Throughput | 100 msg/s | 1000 msg/s |
| Connections | 100/entity | 1000/entity |
| CPU Usage | High (polling) | Low (event-driven) |

## Dependencies

websockets>=12.0
fastapi-websocket>=0.10.0

## References

- FastAPI WebSocket Docs
- RFC 6455 - WebSocket Protocol
- Current: docs/websocket_design.md

---

Status: Design Complete (M5 Ready)
Version: 2.0
Last Updated: 2026-02-01
