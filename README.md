# 🤖 Open Entity

**Lightweight AI agent orchestration with profiles, tools, skills, and memory.**

Open Entity is a modular framework for running AI agents with a consistent runtime, unified LLM providers, and a rich tool system. It supports CLI and Web UI workflows, profile-based agent setups, and persistent session logs.

---

## ✅ Highlights

- **Unified LLM providers**: OpenAI, OpenRouter, Gemini, Moonshot, Z.ai, Ollama
- **Profiles & agents**: orchestrator, coder, code-reviewer (customizable)
- **Tool system**: filesystem, web, browser automation, shell, scheduler, mobile, etc.
- **Skills**: SKILL.md-based knowledge + logic tools
- **Memory**: session history, rolling summaries, tool memos, transcripts
- **CLI + Web UI**: `oe chat` or Docker compose

---

## 🚀 Quick Start (Local)

### 1) Install

```bash
pip install -e .
```

### 2) Configure

```bash
cp .env.example .env
```

Edit `.env` with at least one provider key. Example:

```bash
LLM_PROVIDER=moonshot
MOONSHOT_API_KEY=your_key
MOONSHOT_MODEL=kimi-k2.5

# Optional
GEMINI_API_KEY=your_key
OPENAI_API_KEY=your_key
OPENROUTER_API_KEY=your_key

# Embeddings (memory/search)
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-001
```

### 3) Start Chat

```bash
oe chat
```

Default profile is **`entity`**. You can override:

```bash
oe chat -p entity
```

---

## 🐳 Quick Start (Docker)

```bash
docker compose up -d
```

- Web UI: `http://localhost:8001` (entity-a)
- Web UI: `http://localhost:8002` (entity-b)

Logs:
```bash
docker compose logs -f entity-a
```

Stop:
```bash
docker compose down
```

---

## 🧠 Profiles & Skills

Profiles live in:
```
profiles/<profile>/
```

Skills live in:
```
profiles/<profile>/skills/<skill-name>/SKILL.md
```

List skills:
```bash
oe skills list --profile entity
```

---

## 💓 Heartbeat (Proactive Monitoring)

Heartbeat is a built-in proactive monitoring system. The agent periodically wakes up, evaluates a `HEARTBEAT.md` checklist, and notifies you only when something needs attention.

### Configuration

In `profiles/<profile>/profile.yaml`:

```yaml
heartbeat:
  enabled: true          # Enable/disable
  interval: 30m          # Check interval (30m, 1h, 300s)
  active_hours: "09:00-22:00"  # Only run during these hours
  timezone: "Asia/Tokyo"
  ack_token: "HEARTBEAT_OK"    # Silent response token
  ack_max_chars: 300
  evolve_every: 5        # Self-evolve checklist every N beats
```

Environment variable overrides:
```bash
MOCO_HEARTBEAT_ENABLED=true
MOCO_HEARTBEAT_INTERVAL=15m
```

### HEARTBEAT.md

Place `HEARTBEAT.md` in `profiles/<profile>/HEARTBEAT.md`. This is the checklist the agent evaluates on each heartbeat:

```markdown
# Heartbeat Checklist

Check the following items periodically.
If all is well, respond with `HEARTBEAT_OK`.

## Check Items

- [ ] Important emails/notifications
- [ ] Upcoming calendar events
- [ ] Running task progress
```

### Self-Evolution

Every `evolve_every` beats, the agent reflects on past results and rewrites `HEARTBEAT.md` to improve the checklist — removing items that are always OK, refining noisy alerts, and adding new checks based on observed patterns.

### CLI Commands

```bash
oe heartbeat status    # Show heartbeat config and state
oe heartbeat trigger   # Manually run one heartbeat
oe heartbeat edit      # Open HEARTBEAT.md in editor
```

Or in chat mode:
```
/heartbeat             # Show status
/heartbeat trigger     # Run once
```

### How It Works

1. `oe ui` starts the heartbeat loop in the background
2. Every `interval`, the agent reads `HEARTBEAT.md`
3. Evaluates the checklist (using tools to check real state)
4. If all OK → responds `HEARTBEAT_OK` (silent, no notification)
5. If attention needed → sends alert via configured adapters (LINE, Telegram, etc.)
6. Every N beats → reflects and rewrites `HEARTBEAT.md`

---

## 🌐 Browser Tool (agent-browser)

The `browser_*` tools wrap the `agent-browser` CLI.

Install it locally:
```bash
npm install
```

If needed, set a direct path:
```bash
export MOCO_AGENT_BROWSER_BIN=/path/to/agent-browser
```

---

## 📁 Project Structure

```
open-entity/
├── src/open_entity/          # Framework core
│   ├── core/                 # Runtime, context management
│   ├── tools/                # Tool implementations
│   ├── memory/               # Memory service integration
│   └── storage/              # Sessions & transcripts
├── profiles/                 # Agent profiles
├── docs/                     # Documentation
├── examples/                 # Example scripts
└── tests/                    # Tests
```

---

## 📜 License

MIT
