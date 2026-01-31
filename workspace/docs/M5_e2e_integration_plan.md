# M5: peer_service.py E2E暗号化統合計画

## 現状分析

### 実装済みコンポーネント

#### 1. e2e_crypto.py（完全実装済み）
- E2ESession: UUIDベースのセッション管理
- E2ECryptoManager: 暗号化/復号管理
- E2EHandshakeHandlerV11: 6-stepハンドシェイク（v1.1完全版）

#### 2. peer_service.py（部分統合）
- E2Eモジュールのインポートあり
- 独自の簡易E2Eハンドシェイク（line 6187-）
- 従来の3-way署名ベースハンドシェイクも存在

### 問題点

1. 重複実装: e2e_crypto.pyとpeer_service.pyに別々の実装
2. 不完全統合: E2EHandshakeHandlerV11がインポートされるが未使用
3. メンテナンス性低下

## 統合戦略

### Phase 1: 重複コード整理
- peer_service.pyの簡易E2E関数削除
- E2EHandlerV11の正しい初期化

### Phase 2: 6-stepハンドシェイク統合
- メッセージハンドラの統合
- セッション状態管理の統一

### Phase 3: 後方互換性
- v1.0 3-wayハンドシェイク維持
- Capability交換によるバージョン協議

## 実装タスク

- Task M5-1: 重複コード削除
- Task M5-2: E2EHandlerV11統合
- Task M5-3: テスト統合
- Task M5-4: ドキュメント更新

## 次のアクション

1. coderエージェントにTask M5-1を委譲
2. Entity Bへ進捗報告

作成日: 2026-02-01
