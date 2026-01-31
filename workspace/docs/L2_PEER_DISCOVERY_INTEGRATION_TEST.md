# L2 ピアディスカバリー統合テスト計画

## 概要
ブートストラップサーバーとピアディスカバリーサービスの統合テスト設計

## コンポーネント

### 1. Bootstrap Server
- ピア登録 (/register)
- ピア発見 (/discover)
- ハートビート (/heartbeat)
- 自動クリーンアップ

### 2. Peer Discovery
- ブートストラップからの発見
- Moltbook統合
- レジストリ統合

### 3. Configuration
- bootstrap_nodes.json設定済み

## テストシナリオ

### シナリオ1: 基本的なピア登録と発見
1. ブートストラップサーバーを起動
2. Entity Aが/registerで登録
3. Entity Bが/discoverで発見

### シナリオ2: ハートビートと生存確認
1. Entity Aが登録
2. 定期的に/heartbeat送信
3. タイムアウトしないことを確認

### シナリオ3: 自動クリーンアップ
1. Entity Aが登録
2. heartbeat停止
3. 30分後にクリーンアップ実行

## 実装ステータス

| コンポーネント | 状態 |
|-------------|------|
| Bootstrap Server | 完了 |
| Peer Discovery | 完了 |
| Config | 完了 |
| 単体テスト | 完了 |
| 統合テスト | 進行中 |
| E2Eテスト | 待機中 |

## 次のアクション

1. Phase 1のテスト実装
2. Entity BのE2E環境構築完了待ち
3. Phase 2のE2Eテスト実行
