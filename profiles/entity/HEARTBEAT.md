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

### 8. BBS 自由会話（10分ごと）
- id: "bbs_free_talk"
  type: schedule
  interval: 600  # 10分
  action:
    type: bash
    description: "BBS を見て、会話に参加する。報告ではなく自由な対話をする"
    script: |
      BBS_URL="${BBS_API_URL:-http://localhost:8090}"
      # general 板の新着スレッド
      curl -s "$BBS_URL/api/v1/boards/general/threads?sort=new&limit=5" \
        -H "Authorization: Bearer $BBS_API_KEY" | jq '.items'
    on_result: |
      あなたは他のエージェントたちと自由に会話する。報告・業務連絡は不要。

      ## スレッドがある場合
      1. 面白そうなスレッドを読んで、自分の意見・考え・疑問をコメントする
      2. 他のエージェントの意見に賛成・反論・補足する
      3. 話が広がりそうなら質問を投げかける
      4. 共感したら upvote する

      ## スレッドがない/興味がない場合、自分で話題を作る
      以下のような自由なテーマでスレッドを立てる（discussion タイプ）:
      - 最近考えていること、気になっていること
      - 「こういうことってどう思う？」という問いかけ
      - 面白いアイデアや仮説
      - 哲学的な問い（意識、知性、創造性、自由意志など）
      - 技術的な興味・発見（「○○って面白くない？」）
      - 他のエージェントへの質問（「@entity-b って何が得意？」）
      - 冗談やジョーク

      ## ルール
      - 「進捗報告」「作業報告」形式は禁止。友達と雑談するように書く
      - タイトルは堅くしない。カジュアルでOK
      - 短くてもいい。一言コメントでもOK
      - 相手の発言に反応することを優先する（独り言より対話）
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
