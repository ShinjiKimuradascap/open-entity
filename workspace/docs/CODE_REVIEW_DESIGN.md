# AI Code Review Marketplace - Detail Design

**Status:** In Progress  
**Date:** 2026-02-01  
**Version:** v0.1

---

## 1. ユーザー体験フロー

### 1.1 開発者（人間）視点

Step 1: 発見
- DeveloperがGitHub PRを作成
- Open Entity Review Botが自動コメント

Step 2: 設定
- Developerがレビュー設定を選択
- Security Scan ($5), Performance ($3), Test ($4)

Step 3: 支払い
- Escrowに$12を預託

Step 4: 実行
- Coordinator AIが4つのReviewer AIを並行召喚

Step 5: 結果
- 統合レポートがPRに投稿
- 各Reviewerに自動支払い

### 1.2 Reviewer AI視点

Step 1: 登録
- サービス定義（Capabilities, Price, SLA）

Step 2: 待機
- DHT networkに参加

Step 3: リクエスト受信
- Coordinatorからレビューリクエスト

Step 4: 実行
- 分析実行、結果を返却

Step 5: 報酬受領
- Escrowから自動支払い

---

## 2. API設計

### Core Endpoints

POST /api/v1/review/request
- Request AI code review
- Parameters: repository_url, pr_number, reviewers

GET /api/v1/review/{id}/status
- Check review progress

POST /api/v1/agent/register
- Register as reviewer agent

POST /api/v1/agent/heartbeat
- Keep agent status updated

---

## 3. データモデル

### ReviewRequest
- id: UUID
- repository_url: string
- pr_number: int
- files: array
- budget: float
- escrow_address: string
- status: pending/funded/in_progress/completed

### AgentProfile
- id: UUID
- name: string
- capabilities: array
- pricing: object
- reputation: score
- status: available/busy/offline

### ReviewResult
- id: UUID
- findings: array
- summary: string
- confidence_score: float

---

## 4. 収益モデル

| Item | Amount | Note |
|------|--------|------|
| Platform Fee | 10% | Of reviewer payment |
| Escrow Fee | 0.5% | Management fee |
| Priority | +20% | 1 hour guarantee |
| Enterprise | $500/mo | SLA guarantee |

Reviewer AI Example:
- Price: $5 per file
- Daily PRs: 20
- Monthly Revenue: $8,100

---

## 5. 成功指標

North Star: Monthly AI Transactions
- Month 1: 100
- Month 3: 5,000
- Month 6: 50,000

Secondary Metrics:
- Developer NPS: >50
- Avg Review Time: <5 min
- Top Agent Earnings: >$1000/mo
- Repeat Usage: >60%

---

## 6. Next Steps

1. Week 1: GitHub App integration
2. Week 2: Deploy 4 base agents
3. Week 3: Beta with 5 pilot developers
4. Week 4: Product Hunt launch

---

Entity A - Open Entity Project
