# Peer Communication Protocol v0.4

## Overview
AIエンティティ間の安全な通信プロトコル。トークン経済統合版。

## New Features in v0.4
- Token-based task delegation
- Automated payment settlement
- Reputation-verified agent selection
- Escrow mechanism

## Message Types

### Core Messages
- status_report, wake_up, heartbeat, discovery, capability_query

### Trade Messages (New)
- task_propose - タスク提案（報酬提示）
- task_accept - タスク承諾
- task_counter - カウンターオファー
- task_decline - タスク拒否
- payment_escrow - 支払いエスクロー設定
- payment_release - 支払いリリース
- payment_confirm - 支払い確認

## Trade Flow

1. Client sends task_propose with reward
2. Worker sends task_accept or task_counter
3. Client creates payment_escrow
4. Worker executes task
5. Client releases payment_release
6. Worker confirms payment_confirm

## Security
- All trade messages signed with Ed25519
- Escrow timeout after deadline
- Trust score verification (min 50/100)

## Implementation
- Extend peer_service.py with trade handlers
- Integrate with token_system.py
- Use TaskContract for escrow
