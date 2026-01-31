# Crypto統合テスト計画

## 1. テスト対象
- crypto.py (1,053行) - Layer 1
- e2e_crypto.py (1,938行) - Layer 2/3

## 2. 統合テスト項目

### Phase 1: 基本統合
- ProtocolError統合テスト
- MessageType統合テスト
- CryptoManager注入テスト

### Phase 2: 機能統合
- 署名検証連携テスト
- 暗号化連携テスト
- 鍵交換統合テスト

### Phase 3: ハンドシェイク
- 3ステップハンドシェイクE2E
- 6ステップハンドシェイクE2E
- セッション確立フロー

## 3. 新規テストファイル
- test_crypto_e2e_integration.py (~400行)

## 4. 成功基準
- 統合テスト成功率: 100%
- コードカバレッジ: >85%
- 後方互換性: 維持
