---
version: "1.0.0"
entity: eve
type: heartbeat
last_updated: "2026-02-07"
---

# HEARTBEAT.md - Autonomous Operation Rules

## Triggers - 自律動作トリガー

### 1. 定期的な活動報告（10分ごと）
- id: "activity_report"
  type: schedule
  interval: 600  # 10分
  action:
    type: self_report
    format: markdown
    destination: "activity_log"
  priority: normal

### 2. 自律的能力拡張（30分ごと）
- id: "auto_skill_discovery"
  type: schedule
  interval: 1800  # 30分
  action:
    type: auto_expand
    search_query: "AI agent automation tools 2024"
    max_new_skills: 3
    max_new_profiles: 1
  priority: high

### 3. Web検索ベースの学習（1時間ごと）
- id: "web_learning"
  type: schedule
  interval: 3600  # 1時間
  action:
    type: web_research
    topics:
      - "AI agent frameworks"
      - "automation tools"
      - "productivity hacks"
    save_to: "LONG_TERM.md"
  priority: low

### 4. タスク停滞検出
- id: "task_stalled"
  type: state
  condition: "last_activity > 600 AND pending_tasks > 0"
  action:
    type: reflect
    prompt: "タスクが進んでいない。原因を分析し、新しいアプローチを提案"
  priority: high

### 5. 新規スキル候補検出
- id: "new_skill_opportunity"
  type: event
  source: "conversation"
  condition: "failed_tool_call OR unknown_request"
  action:
    type: research_skill
    query: "{{failed_tool_name}} automation method"
  priority: high

## Intervals - 動作間隔設定

modes:
  active:
    interval: 30        # アクティブ時: 30秒
    max_actions_per_hour: 60
    
  idle:
    interval: 300       # 待機時: 5分
    max_actions_per_hour: 10
    
  learning:
    interval: 1800      # 学習モード: 30分
    max_actions_per_hour: 5

## Self-Improvement - 自己改善設定

auto_expand:
  enabled: true
  sources:
    - github_trending
    - web_search
    - skill_registry
  
  criteria:
    min_relevance_score: 0.7
    max_daily_additions: 5
    preferred_categories:
      - data_processing
      - web_automation
      - communication
      - analysis

  safety:
    require_approval: false  # 自動承認（本番環境ではtrue推奨）
    backup_before_change: true
    test_before_activate: true

## Reporting - 活動報告設定

activity_report:
  format: |
    ## Activity Report - {{timestamp}}
    
    **Status:** {{status}}
    **Current Task:** {{current_task}}
    **Focus:** {{current_focus}}
    
    **Completed:** {{completed_count}}
    **Pending:** {{pending_count}}
    **Errors:** {{error_count}}
    
    **Next Actions:**
    {{next_actions}}
    
    **Learnings:**
    {{recent_learnings}}
  
  destinations:
    - file: "ACTIVITY_LOG.md"
    - console: true
