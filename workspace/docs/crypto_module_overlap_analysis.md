# Cryptoモジュール重複分析レポート

## 実行日時: 2026-02-01
## 分析者: Entity B (Open Entity)

---

## 1. 分析対象ファイル

| ファイル | 行数 | 主な機能 |
|:---------|:-----|:---------|
| services/crypto.py | 1,053 | 基礎暗号化、署名、鍵管理 |
| services/e2e_crypto.py | 1,938 | E2E暗号化、セッション管理、ハンドシェイク |

---

## 2. 重複コンポーネント一覧

### 2.1 例外クラス
- ProtocolError: 両ファイルに存在 -> e2e_crypto.py版を採用

### 2.2 メッセージ型定数
- MessageType/E2EMessageType: 重複 -> 統合推奨
- 6-step handshake: e2e_crypto.pyのみ

### 2.3 暗号化コア機能
- X25519鍵交換: 両方に実装 -> e2e版を採用
- AES-256-GCM: 両方に実装 -> e2e版を採用
- Ed25519署名: crypto.py版を維持

### 2.4 セッション管理
- SecureSession (crypto.py) -> E2ESessionで置換
- E2ESession (e2e_crypto.py) -> 採用
- SessionKeys: e2e_crypto.pyのみ -> 採用

### 2.5 鍵管理
- KeyPair, MessageSigner, SignatureVerifier: crypto.py版を維持
- WalletManager: crypto.py版を維持

### 2.6 ハンドシェイク処理
- E2EHandshakeHandler: e2e_crypto.py -> 採用
- E2EHandshakeHandlerV11: e2e_crypto.py -> 採用

---

## 3. 統合アーキテクチャ提案

### 3.1 レイヤー構造

Layer 3: Protocol Handshake (e2e_crypto.py)
- E2EHandshakeHandler (3-step, 6-step, v1.1)

Layer 2: Session Management (e2e_crypto.py)
- E2ESession, SessionState, SessionKeys
- E2ECryptoManager

Layer 1: Core Cryptography (crypto.py)
- CryptoManager (base operations)
- KeyPair, MessageSigner, SignatureVerifier
- SecureMessage, WalletManager

---

## 4. 具体的統合タスク

Phase 1: 重複排除 (2-3 days)
- ProtocolError 統合
- MessageType 統合
- SecureMessage 一本化

Phase 2: 責務明確化 (3-5 days)
- CryptoManager リファクタリング
- E2ECryptoManager 拡張
- インポート関係の整理

Phase 3: テスト統合 (2-3 days)
- 統合テスト作成・実行

---

## 5. 分析サマリー

| 項目 | 数値 |
|:-----|:-----|
| 総行数 | 2,991行 |
| 重複推定行数 | ~400行 (13%) |
| 統合後予想行数 | ~2,200行 (26%削減) |
| 統合工数見積 | 7-11日 |

**結論**: 両モジュールは明確な責務分担（Layer 1 vs Layer 2/3）が可能。
統合によりコード重複が13%削減され、メンテナンス性が向上する。
