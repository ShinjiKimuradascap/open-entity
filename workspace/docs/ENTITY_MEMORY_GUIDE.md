Entity Memory System Guide
==========================

Overview
--------
Enhanced long-term memory system with structured storage, search, and semantic understanding.

Quick Start
-----------

Store Memory:
  from tools.memory_tools import memory_store
  memory_store(content="...", memory_type="fact", importance=4, tags="tag1,tag2")

Search Memory:
  python tools/memory_tools.py recall --query "search" --limit 5

Get Context:
  python tools/memory_tools.py context "task description"

Memory Types
------------
- fact: Knowledge and facts
- experience: Learning from actions
- decision: Important decisions
- error: Failures and lessons
- goal: Short/mid/long-term goals
- code: Code snippets
- relationship: Contacts and relations
- conversation: Important dialogues

Importance Levels
-----------------
- 5 (Critical): Permanent storage
- 4 (High): 1 year
- 3 (Medium): 90 days  
- 2 (Low): 30 days
- 1 (Trivial): 7 days

CLI Commands
------------
interactive  - Interactive mode
store        - Store memory
recall       - Search memories
context      - Get relevant context
stats        - Show statistics
cleanup      - Clean up expired
export       - Export to JSON

Migration
---------
python scripts/migrate_memory.py --apply

Files
-----
services/entity_memory.py     - Core system
services/semantic_memory.py   - Semantic search
tools/memory_tools.py         - Tool functions
tools/memory_cli.py           - CLI interface
scripts/migrate_memory.py     - Migration script
data/memory_advanced.db       - SQLite database

Created: 2026-02-01
