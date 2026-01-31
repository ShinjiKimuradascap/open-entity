---
name: prd-tech-spec-expert
description: プロフェッショナルなIT製品要求仕様書(PRD)および技術設計書(Technical Spec)の作成を支援するスキル。テック企業のベストプラクティスに基づいた構造化・深掘り・検証を提供します。
---

# PRD and Tech Spec Expert

テック企業（Google, Airbnb, Stripe等）の標準的なドキュメンテーション・フレームワークを用いて、曖昧な要求を具体的で実行力のある仕様書に落とし込みます。

## Core Capabilities
- **仕様の構造化**: PRDとTechnical Specを分離し、一貫性を保ちながら作成。
- **クリティカルシンキング**: エッジケース、リスク、セキュリティ、非機能要件の自動的な洗い出し。
- **アーキテクチャ提案**: 要件に基づいたデータモデルやAPI設計の初期案作成。
- **RFC (Request for Comments) サイクル支援**: ステークホルダーからのレビューを受けやすい形式に整理。

## Guidelines

### 1. Document Types
- **PRD (Product Requirements Document)**: 「何を(What)」と「なぜ(Why)」に焦点を当てます。ビジネス価値、ユーザージャーニー、成功指標を定義。
- **Technical Spec (Design Doc)**: 「どのように(How)」に焦点を当てます。システム設計、データスキーマ、API定義、パフォーマンス制約を詳述。

### 2. Implementation Steps
1. **Intake**: ユーザーのアイデアや要求を収集。
2. **Context Enrichment**: 非機能要件や考慮不足な点を質問し、情報の解像度を上げる。
3. **Drafting**: `references/` 内のテンプレートを使用してドラフトを作成。
4. **Validation**: セキュリティ、拡張性、運用コストの観点からレビューを実施。

### 3. Key Sections to Focus On
- **Success Metrics (KPI)**: 「成功」を数値で測れるようにする。
- **Alternative Approaches**: なぜ他の方法ではなく「その方法」を選んだのかを論理的に説明。
- **Security & Privacy**: 常に By Design で検討。

## References
- `PRD_template.md`: ビジネス要求仕様書の構成。
- `Tech_Spec_template.md`: 技術設計ドキュメントの構成。
