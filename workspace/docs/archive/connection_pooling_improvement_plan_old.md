# Connection Pooling 改善計画

## 概要
AI Collaboration PlatformにおけるHTTP Connection poolingの最適化計画。

## 調査日時
2026-02-01

## 現状分析

### 問題のある実装（Connection pooling未対応）

| ファイル | 行番号 | 問題点 |
|---------|--------|--------|
| peer_discovery.py | 166, 288 | 毎回新規ClientSession作成 |
| peer_monitor.py | 446 | 毎回新規ClientSession作成 |

### 適切な実装（Connection pooling対応済み）

| ファイル | 行番号 | 実装パターン |
|---------|--------|-------------|
| moltbook_identity_client.py | 123, 206-210 | _sessionフィールドで保持・再利用 |
| moltbook_integration.py | 147, 157-171 | _sessionフィールドで保持・再利用 |

## 改善計画

### Phase 1: peer_discovery.py の改善

- _sessionフィールドを追加
- _get_session()メソッドでセッション管理
- close()メソッドで適切にクリーンアップ

### Phase 2: peer_monitor.py の改善

同様にセッション保持パターンを適用

### Phase 3: テストと検証

- Connection pooling動作確認
- パフォーマンス測定
- リソースリーク確認

## 実装タスク

- S3: peer_discovery.pyにConnection pooling実装
- S4: peer_monitor.pyにConnection pooling実装
- M1: 統合テストとパフォーマンス検証

## 期待される効果

- ブートストラップノードへの問い合わせレイテンシ削減
- TCP接続数の安定化
- ピア発見処理のスループット向上
