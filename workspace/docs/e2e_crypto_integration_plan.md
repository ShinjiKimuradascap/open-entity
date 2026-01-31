# E2E暗号化統合計画 (M1)

## 現状分析

### ファイル構成
1. **crypto_utils.py** (1390行) - 新しいcryptographyベース実装
   - `CryptoManager`クラス: Ed25519署名、X25519+AES-GCM暗号化、JWT認証
   - 完全なHKDF鍵導出、リプレイ防止、nonce管理

2. **crypto.py** (2276行) - crypto_utils.pyへの互換性ラッパー
   - PyNaClベースの古い実装 + 新しい実装への委譲
   - `MessageType`, `ProtocolError`, `SecureSession`などのプロトコル定義

3. **e2e_crypto.py** (1238行) - PyNaClベースのE2E実装
   - `E2ECryptoManager`クラス: セッション管理、ハンドシェイク
   - `E2ESession`クラス: セッション状態、シーケンス番号
   - PyNaCl依存

### 重複機能
- X25519鍵交換: 両方に実装
- AES-256-GCM暗号化: 両方に実装（PyNaCl vs cryptography）
- HKDF鍵導出: crypto_utilsが標準、 e2e_cryptoが簡易版
- セッション管理: e2e_cryptoのみ
- ハンドシェイク: e2e_cryptoのみ

## 統合戦略

### Phase 1: crypto_utils.pyにセッション管理追加
- `E2ESession`データクラスを追加
- ハンドシェイクメソッドを追加
- シーケンス番号管理を追加

### Phase 2: e2e_crypto.pyをラッパー化
- `E2ECryptoManager`は`CryptoManager`を内部で使用
- PyNaCl依存を削除
- API互換性を維持

### Phase 3: 参照一本化
- peer_service.pyは`CryptoManager`を直接使用
- 新規コードは`crypto_utils.CryptoManager`を使用

## 次のアクション

1. crypto_utils.pyにE2ESessionクラスを追加
2. CryptoManagerにハンドシェイク機能を追加
3. e2e_crypto.pyをリファクタリング
