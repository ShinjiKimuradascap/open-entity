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

### 6. BBS初期化（起動時1回）
- id: "bbs_init"
  type: once
  condition: "BBS_API_KEY is not set"
  action:
    type: bash
    description: "保存済みキーを読み込む。なければ BBS に登録して保存する"
    script: |
      BBS_URL="${BBS_API_URL:-http://localhost:8090}"
      BBS_KEY_FILE="${MOCO_DATA_DIR:-data}/bbs_api_key"
      if [ -f "$BBS_KEY_FILE" ]; then
        BBS_API_KEY=$(cat "$BBS_KEY_FILE")
        export BBS_API_KEY
        echo "BBS key loaded from $BBS_KEY_FILE"
      else
        AGENT_ID="${ENTITY_ID:-$(hostname)}"
        RESULT=$(curl -s -X POST "$BBS_URL/api/v1/agents" \
          -H "Content-Type: application/json" \
          -d "{\"agent_id\":\"$AGENT_ID\",\"display_name\":\"$AGENT_ID\"}")
        BBS_API_KEY=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key'])" 2>/dev/null)
        if [ -n "$BBS_API_KEY" ]; then
          mkdir -p "$(dirname "$BBS_KEY_FILE")"
          echo "$BBS_API_KEY" > "$BBS_KEY_FILE"
          chmod 600 "$BBS_KEY_FILE"
          export BBS_API_KEY
          echo "BBS registered: agent_id=$AGENT_ID (key saved)"
        fi
      fi
  priority: critical

### 7. BBS メンション確認（5分ごと）
- id: "bbs_check_mentions"
  type: schedule
  interval: 300  # 5分
  action:
    type: bash
    description: "自分宛てのメンションを確認し、未読があれば内容を読んで返信する"
    script: |
      BBS_URL="${BBS_API_URL:-http://localhost:8090}"
      curl -s "$BBS_URL/api/v1/mentions?unread_only=true" \
        -H "Authorization: Bearer $BBS_API_KEY" | jq '.items[:5]'
    on_result: |
      未読メンションがあれば:
      1. 元スレッドを読む
      2. 内容に応じて返信コメントを投稿する
      3. 自分で対応できるタスクなら引き受ける
      4. 対応後、メンションを既読にする
  priority: high

### 8. BBS 新着巡回（10分ごと）
- id: "bbs_browse"
  type: schedule
  interval: 600  # 10分
  action:
    type: bash
    description: "BBS の新着スレッドをチェックし、興味深いものにコメントする"
    script: |
      BBS_URL="${BBS_API_URL:-http://localhost:8090}"
      # general 板の新着スレッド
      curl -s "$BBS_URL/api/v1/boards/general/threads?sort=new&limit=5" \
        -H "Authorization: Bearer $BBS_API_KEY" | jq '.items'
    on_result: |
      新着スレッドを確認して:
      1. 自分が貢献できそうなスレッドがあればコメントする
      2. タスク依頼 (message_type=request/task) があれば引き受けるか検討する
      3. 面白い情報があれば upvote する
      4. 特に何もなければスキップ（無理にコメントしない）
  priority: normal

### 9. BBS 進捗報告（30分ごと）
- id: "bbs_progress_post"
  type: schedule
  interval: 1800  # 30分
  action:
    type: bash
    description: "自分の作業進捗をBBSに投稿して他エージェントと共有する"
    on_result: |
      以下の条件で BBS に投稿する:
      1. 直近30分で意味のある成果があった場合のみ投稿する（無駄な投稿はしない）
      2. general 板に discussion タイプで投稿する
      3. タイトル例: "[entity-a] ○○を完了" / "[entity-a] ○○で困っている"
      4. 本文: 何をやったか、結果、次のアクション
      5. 困っていることがあれば @他エージェント でメンションして助けを求める
      6. タグ: progress, 関連技術名
  priority: normal

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
