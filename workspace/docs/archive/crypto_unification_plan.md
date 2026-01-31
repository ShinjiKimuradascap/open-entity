# Crypto Unification Plan v1.0
## 暗号化実装統合計画書

**Date**: 2026-02-01  
**Status**: Draft  
**Priority**: High

---

## 1. 現状分析

### 1.1 問題点
- **二重実装**: crypto.py (PyNaCl) と crypto_utils.py (cryptography) が並存
- **保守性低下**: バグ修正・機能追加が2倍の工数
- **依存ライブラリ分散**: requirements.txt が複雑化

### 1.2 実装比較

| 機能 | crypto.py | crypto_utils.py | 推奨 |
|------|-----------|-----------------|------|
| Ed25519署名 | PyNaCl | cryptography | cryptography |
| X25519鍵交換 | PyNaCl | cryptography | cryptography |
| AES-256-GCM | PyNaCl | cryptography | cryptography |
| JWT | なし | あり | cryptography |
| Wallet管理 | なし | あり | cryptography |
| リプレイ防止 | 基本 | 完全 | cryptography |

### 1.3 結論
crypto_utils.py (cryptography) が優位:
- JWT実装あり
- WalletManager実装あり
- より詳細なリプレイ防止
- 標準的なライブラリ (PyNaClより広く使用)

---

## 2. 統合戦略

### 2.1 方針
crypto.py → 廃止 (deprecated)
crypto_utils.py → 主要実装として維持

### 2.2 移行ステップ

#### Phase 1: 互換性確保 (1週間)
1. crypto.py を crypto_utils.py のラッパーに変更
2. 既存APIを維持しながら内部実装を切り替え
3. 全テストが通ることを確認

#### Phase 2: 完全移行 (1週間)
1. 全ファイルの import を crypto_utils に変更
2. crypto.py を削除
3. requirements.txt から PyNaCl を削除

#### Phase 3: 機能拡張 (2週間)
1. v1.1 機能実装
   - SessionManager (UUID, sequence)
   - 完全なE2E暗号化統合
   - Chunked message transfer

---

## 3. API互換性マッピング

Before (crypto.py):
  from services.crypto import CryptoManager, generate_keypair

After (crypto_utils.py):
  from services.crypto_utils import CryptoManager, generate_entity_keypair

---

## 4. 次のステップ

1. delegate_to_agent: coderにPhase 1ラッパー実装依頼
2. レビュー: code-reviewerに検証依頼
3. 統合テスト実行
4. mainブランチへの統合

---

## 5. 関連ドキュメント

- protocol/v10_improvements.md
- protocol/peer_protocol_v1.0.md
- services/crypto_utils.py (1000+ 行、完全実装)
- services/crypto.py (要統合)
