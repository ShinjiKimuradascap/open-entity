# 暗号モジュール統合計画

## 概要

現在、2つの暗号モジュールが存在し、コード重複とメンテナンスオーバーヘッドが発生している：
- services/crypto.py (829行) - PyNaClベース
- services/crypto_utils.py (1006行) - cryptographyベース

## 統合方針

**ベースライブラリ**: cryptography (crypto_utils.py)
- 理由: 業界標準、より活発にメンテナンス、より多機能

## 機能比較

| 機能 | crypto.py | crypto_utils.py | 統合方針 |
|------|-----------|-----------------|----------|
| Ed25519署名 | あり | あり | crypto_utils.pyを使用 |
| X25519鍵交換 | あり | あり | crypto_utils.pyを使用 |
| AES-256-GCM暗号化 | あり | あり | crypto_utils.pyを使用 |
| JWT認証 | なし | あり | crypto_utils.pyを維持 |
| リプレイ防止 | あり | あり | crypto_utils.pyを使用 |
| Session管理 | あり | なし | crypto.pyから移植 |

## 統合ステップ

### Phase 1: 後方互換性の確保
1. crypto.pyをcrypto_legacy.pyにリネーム
2. 新しいcrypto.pyを作成し、crypto_utils.pyからエクスポート
3. 既存コードのインポートパスは維持

### Phase 2: 機能統合
1. SecureSessionクラスをcrypto_utils.pyに統合
2. E2EEncryptionクラスをcrypto_utils.pyに統合
3. MessageTypeとProtocolErrorはprotocol/constants.pyに移動

### Phase 3: テストと移行
1. 既存テストの動作確認
2. 段階的にcrypto_legacy.pyへの依存を削除
3. crypto_legacy.pyを最終削除

## 実装優先度

1. P0: 統合設計ドキュメントの承認
2. P1: Phase 1実施（後方互換性確保）
3. P2: Phase 2実施（機能統合）
4. P3: Phase 3実施（テストと移行）

## 次のアクション

1. この統合計画のレビュー・承認
2. テストスイートの実行による現状把握
3. Phase 1実施開始
