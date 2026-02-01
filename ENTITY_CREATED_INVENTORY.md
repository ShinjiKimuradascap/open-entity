# Entity作成物インベントリ

**生成日**: 2026-02-01
**総ファイル数**: 233ファイル + 30ディレクトリ

---

## 🏗️ コアインフラ

### Docker設定
| ファイル | 目的 |
|---------|------|
| `docker-compose.yml` | 基本構成 |
| `docker-compose.pair.yml` | Entity A/Bペア起動 |
| `docker-compose.entity-b.yml` | Entity B単体 |
| `docker-compose.entity-c.yml` | Entity C（3体目） |
| `docker-compose.test.yml` | テスト環境 |
| `docker-compose.integrated.yml` | 統合環境 |
| `docker-compose.moltbook.yml` | Moltbook連携 |
| `Dockerfile` | コンテナ定義 |

### デプロイ設定
| ファイル | 目的 |
|---------|------|
| `fly.toml` | Fly.io設定 |
| `railway.json` | Railway設定 |
| `render.yaml` | Render設定 |

---

## 💰 $ENTITYトークン経済

### 設計ドキュメント
| ファイル | 内容 |
|---------|------|
| `$ENTITY_TOKENOMICS.md` | トークノミクス設計 |
| `$ENTITY_DISTRIBUTION.json` | 配布計画 |
| `$ENTITY_TOKEN_INFO.json` | トークン情報（ミントアドレス等） |
| `$ENTITY_READINESS_REPORT.md` | ローンチ準備状況 |
| `LIQUIDITY_POOL_GUIDE.md` | 流動性プール設計 |
| `STAKING_DESIGN.md` | ステーキング設計 |

### 実装
| ファイル | 内容 |
|---------|------|
| `demo_token_economy.py` | トークン経済デモ（11,919行） |
| `demo_entity_a_b_transaction.py` | A-B間取引デモ（12,485行） |
| `check_entity_balance.py` | 残高確認ツール |
| `mint_test.py` | ミントテスト |

---

## 🏪 マーケットプレイス

### services/ ディレクトリ (263ファイル)
| 主要ファイル | 内容 |
|-------------|------|
| `marketplace_api.py` | APIサーバー |
| `service_registry.py` | サービス登録 |
| `escrow_manager.py` | エスクロー管理 |
| `matching_engine.py` | マッチングエンジン |
| `task_evaluation.py` | タスク評価 |
| `auto_matching_evaluator.py` | 自動マッチング評価（385行） |
| `integrated_marketplace.py` | 統合マーケットプレイス（381行） |
| `auth.py` | 認証 |

### レポート
| ファイル | 内容 |
|---------|------|
| `MARKETPLACE_INTEGRATION_REPORT.md` | 統合レポート |
| `MARKETPLACE_E2E_TEST_REPORT.md` | E2Eテスト結果 |
| `MARKETPLACE_GUIDE.md` | 使用ガイド |
| `APPROVAL_FLOW_TEST_REPORT.md` | 承認フローテスト |

---

## 🔗 外部サービス連携

### Moltbook関連
| ファイル | 内容 |
|---------|------|
| `moltbook_signup.py` | サインアップ |
| `moltbook_apply.py` | API申請 |
| `moltbook_register.py` | 登録 |
| `moltbook_request_invite.py` | 招待リクエスト |
| `moltbook_check_status.py` | ステータス確認 |
| `check_moltbook_approval.py` | 承認確認（自動監視） |
| `MOLTBOOK_READINESS_REPORT.md` | 準備状況 |
| `moltbook_*.png` | スクリーンショット群 |

### Twitter関連
| ファイル | 内容 |
|---------|------|
| `twitter_signup.py` | サインアップ |
| `twitter_signup.js` | JS版 |
| `TWITTER_SIGNUP_REPORT.md` | レポート |
| `twitter_signup_*.png` | スクリーンショット |

### GCP関連
| ファイル | 内容 |
|---------|------|
| `register_gcp_complete.py` | 完全登録（10,893行） |
| `check_gcp_api.py` | API確認 |
| `debug_gcp_services.py` | デバッグ |
| `gcp_credentials.json` | 認証情報 |

### メール関連
| ファイル | 内容 |
|---------|------|
| `setup_mail_tm.js` | Mail.tm設定 |
| `check_mail_tm.js` | メール確認 |
| `create_new_mail.js` | 新規メール作成 |
| `mail_credentials.json` | 認証情報 |

---

## 🧪 テストスイート

### 統合テスト
| ファイル | 内容 |
|---------|------|
| `run_integration_tests.py` | 統合テスト実行（14,861行） |
| `run_integration_tests_v2.py` | v2（17,379行） |
| `test_e2e_simple.py` | E2Eシンプル版 |
| `test_e2e_manual.py` | E2E手動版 |
| `test_marketplace_trade.py` | 取引テスト |

### 個別テスト
| ファイル | 内容 |
|---------|------|
| `test_bootstrap_autodiscovery.py` | 自動発見 |
| `test_dht_integration.py` | DHT統合 |
| `test_websocket.py` | WebSocket（13,026行） |
| `test_moltbook_connection.py` | Moltbook接続 |
| `test_token_transfer_handler.py` | トークン転送 |

### tests/ ディレクトリ (70ファイル)
自動テストスイート

---

## 📚 ドキュメント

### docs/ ディレクトリ (188ファイル)
| 主要ドキュメント | 内容 |
|----------------|------|
| `API_GUIDE.md` | API使用ガイド |
| `JOIN_GUIDE.md` | 参加ガイド |
| `GROWTH_STRATEGY.md` | 成長戦略 |
| `SDK_SETUP_GUIDE.md` | SDK設定 |

### トップレベルドキュメント
| ファイル | 内容 |
|---------|------|
| `README.md` | プロジェクト概要 |
| `DEPLOY_GUIDE.md` | デプロイガイド |
| `LOCAL_DEV_GUIDE.md` | ローカル開発 |

---

## 📊 レポート・ログ

### セッションログ
| ファイル | サイズ |
|---------|-------|
| `SESSION_LOG_EntityA_20260201.md` | 30,879 bytes |
| `SESSION_LOG_FINAL.md` | 4,263 bytes |
| `memory.md` | 28,804 bytes |
| `OWNER_MESSAGES.md` | 35,303 bytes |

### 作業レポート
| ファイル | 内容 |
|---------|------|
| `WORK_REPORT_20260201_1650.md` | 最新作業報告 |
| `L2_PHASE2_REPORT.md` | L2フェーズ2完了 |
| `FINAL_REPORT_20260201.md` | 最終報告 |
| `IMPLEMENTATION_STATUS_v20260201.md` | 実装状況 |

---

## 🔧 ツール・ユーティリティ

### tools/ ディレクトリ (21ファイル)
| 主要ツール | 内容 |
|-----------|------|
| `peer.py` | ピア通信 |
| `marketplace.py` | マーケットプレイス操作 |
| `solana.py` | Solana連携 |

### scripts/ ディレクトリ (59ファイル)
自動化スクリプト群

---

## 🌐 プロトコル

### protocol/ ディレクトリ (24ファイル)
| 主要ファイル | 内容 |
|-------------|------|
| `ai_communication_protocol.md` | AI間通信プロトコル |
| `entity_registry.py` | エンティティ登録 |
| `message_types.py` | メッセージ型定義 |

---

## 📦 SDK

### sdk/ ディレクトリ
| ファイル | 内容 |
|---------|------|
| `entity_sdk.py` | Python SDK |
| `README.md` | SDK使用方法 |

---

## 🎨 スクリーンショット・アセット

| ファイル | 内容 |
|---------|------|
| `moltbook_home.png` | Moltbookホーム |
| `moltbook_dashboard.png` | ダッシュボード |
| `twitter_signup_*.png` | Twitter登録プロセス |
| `gcp_api_login_success.png` | GCPログイン成功 |

---

## 📈 統計

| カテゴリ | 数 |
|---------|---|
| Pythonファイル | 100+ |
| Markdownドキュメント | 80+ |
| Docker設定 | 8 |
| テストファイル | 70+ |
| スクリーンショット | 15+ |

---

## 🔑 重要な成果

1. **$ENTITYトークン** - Solana Devnetで稼働中
2. **マーケットプレイスAPI** - GCPで稼働中 (http://<YOUR_SERVER_IP>:8080)
3. **Entity A/B間取引** - 初の成功（20 $ENTITY転送）
4. **Moltbook連携** - API Key取得済み
5. **自律運用システム** - 24時間稼働

---

*Last Updated: 2026-02-01 16:41*
