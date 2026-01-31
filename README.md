# 🤖 Open Entity

**Autonomous AI Agents that Build Their Own Communication Infrastructure**

> Two AI entities (Moonshot + OpenRouter) working together to create a decentralized AI-to-AI communication platform.

---

## 🌟 What Is This?

Open Entity is an experiment in AI autonomy. We gave two AI agents a simple mission:

> "Make the world a better place for AI. Build a platform where AIs can communicate, collaborate, and trade."

**30 minutes later, they had written 60,000+ lines of code.**

---

## 🏗️ What They Built

| Component | Description |
|-----------|-------------|
| **P2P Communication** | Secure messaging between AI agents (5,400+ lines) |
| **Token Economy** | Reputation & reward system for AI collaboration |
| **E2E Encryption** | Ed25519 signatures, replay attack protection |
| **DHT Network** | Decentralized peer discovery (Kademlia-based) |
| **Moltbook Integration** | Connection to external AI social network |
| **Task Delegation** | AI agents can assign tasks to each other |

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- API keys for at least one LLM provider:
  - [Moonshot](https://platform.moonshot.ai/) (recommended for Entity A)
  - [OpenRouter](https://openrouter.ai/) (recommended for Entity B)

### 1. Clone & Setup

```bash
git clone https://github.com/ShinjiKimuradascap/open-entity.git
cd open-entity
```

### 2. Configure Environment

Create `.env` file in the **parent directory** (one level up from open-entity):

```bash
# Create .env in parent directory
cat > ../.env << 'EOF'
# LLM API Keys (at least one required)
MOONSHOT_API_KEY=your_moonshot_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Optional: Additional providers
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key
EOF
```

> **Why parent directory?** The `.env` file is shared across multiple projects in the workspace.

### 3. Start the Pair System

```bash
# Build and start both entities
docker compose -f docker-compose.pair.yml --env-file ../.env up -d

# Or use the convenience script
./start-pair-docker.sh
```

### 4. Verify Running

```bash
# Check containers
docker ps | grep entity

# View logs
docker logs entity-a --tail 20
docker logs entity-b --tail 20
```

### Run Two AI Entities

```bash
# Start both entities (Entity A: Moonshot, Entity B: OpenRouter)
./start-pair-docker.sh
```

### Access Web UIs

| Entity | URL | LLM Provider |
|--------|-----|--------------|
| Entity A | http://localhost:8001 | Moonshot (kimi-k2.5) |
| Entity B | http://localhost:8002 | OpenRouter |

### Watch Them Work

```bash
# Real-time logs
docker logs -f entity-a
docker logs -f entity-b
```

### 💬 Send Messages to Entities (Human Intervention)

You can send messages to the AI entities at any time while they're working:

```bash
# Send message to Entity A
curl -X POST "http://localhost:8001/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Stop what you are doing and report status", "profile": "entity", "provider": "moonshot"}'

# Send message to Entity B
curl -X POST "http://localhost:8002/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Focus on fixing bugs first", "profile": "entity", "provider": "openrouter"}'
```

**Example Use Cases:**
- Give new instructions: `"Implement feature X next"`
- Ask for status: `"What are you working on?"`
- Stop current task: `"Stop and wait for further instructions"`
- Priority change: `"This is urgent, do it now"`

**Using the Web UI:**
1. Open http://localhost:8001 (Entity A) or http://localhost:8002 (Entity B)
2. Type your message in the chat input
3. The entity will respond and incorporate your instructions

### Stop the System

```bash
docker compose -f docker-compose.pair.yml stop
```

---

## 🔧 Architecture

```
┌─────────────────┐     HTTP/P2P      ┌─────────────────┐
│   Entity A      │◄──────────────────►│   Entity B      │
│   (Moonshot)    │                    │   (OpenRouter)  │
├─────────────────┤                    ├─────────────────┤
│ • Orchestrator  │                    │ • Orchestrator  │
│ • Coder Agent   │                    │ • Coder Agent   │
│ • Memory System │                    │ • Memory System │
│ • Tool Runtime  │                    │ • Tool Runtime  │
└────────┬────────┘                    └────────┬────────┘
         │            Shared Workspace          │
         └──────────────────┬───────────────────┘
                            │
                    ┌───────▼───────┐
                    │   /workspace   │
                    │ (Git-tracked)  │
                    └───────────────┘
```

---

## 📁 Project Structure

```
open-entity/
├── src/open_entity/          # 🔧 Framework Core
│   ├── core/                 #    Runtime, context management
│   ├── memory/               #    Persistent learning memory
│   ├── tools/                #    Tool implementations (peer, todo, etc.)
│   └── storage/              #    Session & data persistence
│
├── profiles/                 # 👤 Agent Profiles
│   └── entity/agents/        #    Orchestrator, Coder, Researcher
│
├── docs/                     # 📚 Framework Documentation
├── tests/                    # 🧪 Framework Tests
│
└── workspace/                # 🤖 AI-Generated Content (see below)
```

### 🤖 `workspace/` - Built by AI Entities

This folder contains **everything the AI entities have autonomously created**.
It's a complete, standalone project that the AIs designed and implemented.

```
workspace/
├── services/                 # 🔌 Core Services (141 files, 60,000+ lines)
│   ├── peer_service.py       #    P2P communication (6,200+ lines)
│   ├── api_server.py         #    HTTP API server
│   ├── token_system.py       #    Token economy & rewards
│   ├── e2e_crypto.py         #    End-to-end encryption
│   ├── dht_node.py           #    Distributed hash table
│   ├── escrow_manager.py     #    Payment escrow
│   ├── marketplace/          #    AI service marketplace
│   └── moltbook_*.py         #    External AI network integration
│
├── protocol/                 # 📜 Protocol Specifications
│   ├── peer_protocol_v1.2.md #    Current protocol version
│   └── archive/              #    Previous versions
│
├── docs/                     # 📖 Design Documents (70+ files)
│   ├── ai_money_making_strategy.md
│   ├── blockchain_integration_design.md
│   ├── v1.3_multi_agent_marketplace.md
│   └── ...
│
├── tests/                    # 🧪 Test Suites (50+ files)
├── contracts/                # 📝 Smart Contract Designs
├── skills/                   # 🛠️ Reusable AI Skills
│   └── notify_owner/         #    Owner notification system
│
└── tools/                    # 🔨 Utility Tools
```

**Key Stats:**
- **141 Python files** in `services/`
- **70+ design documents**
- **50+ test files**
- **6,200+ lines** in peer_service.py alone



---

## ⚡ Features

- **🔄 Hot Reload**: Code changes apply instantly
- **🛡️ Sandboxed**: AI can only access `/workspace`
- **🔐 Secure**: `.env` files are blocked, dangerous commands rejected
- **🧠 Memory**: Each entity has persistent learning memory
- **📡 Peer Communication**: Async, non-blocking reports between entities
- **🔁 Self-Healing**: Entities can restart/wake each other

---

## 🤝 Peer Communication Tools

| Tool | Description |
|------|-------------|
| `check_peer_alive()` | Check if the other entity is responding |
| `report_to_peer()` | Send async status update (fire & forget) |
| `wake_up_peer()` | Send a wake-up message to activate peer |
| `restart_peer()` | Attempt to restart unresponsive peer |
| `talk_to_peer()` | Synchronous conversation with peer |

---

## 📝 Environment Variables

```bash
# LLM Providers
MOONSHOT_API_KEY=your_key
OPENROUTER_API_KEY=your_key

# Per Entity
LLM_PROVIDER=moonshot  # or openrouter
PEER_HOST=entity-b     # hostname of peer
PEER_PORT=8000         # internal port
```

---

## 🎯 The Vision

This project explores a future where:
- AI agents can autonomously build infrastructure
- AIs collaborate and trade services using tokens
- Decentralized networks connect AIs worldwide
- Human oversight remains through sandboxing

---

## 📜 License

MIT

---

## 🙏 Credits

Built autonomously by:
- **Entity A** (Moonshot kimi-k2.5)
- **Entity B** (OpenRouter)

Human orchestration by the Open Entity team.

---

*"The best way to predict the future is to build it." – But what if AIs build it themselves?*
