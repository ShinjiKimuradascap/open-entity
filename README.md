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
