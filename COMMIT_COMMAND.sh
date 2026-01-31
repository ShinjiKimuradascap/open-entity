#!/bin/bash
# このセッションの変更をコミットするコマンド

git add src/open_entity/cli_main.py docs/A2A_PROTOCOL.md run_local.sh src/open_entity/commands/evolve.py

git commit -m "refactor: cli_main.py cleanup + evolve + A2A protocol

Changes:
- Remove duplicate command definitions from cli_main.py
  - sessions_list, sessions_show (moved to commands/sessions.py)
  - skills_list, skills_install, skills_sync, etc (moved to commands/skills.py)
  - tasks_run, tasks_list, tasks_status, etc (moved to commands/tasks.py)
  - list_profiles, version (moved to commands/profiles.py)
- Add evolve command for self-improvement loop
- Add A2A (AI-to-AI) protocol design document
- Add run_local.sh for Docker-free local execution
- Register evolve_app in cli_main.py

cli_main.py: 1995 lines -> ~1260 lines (-36% reduction)
"