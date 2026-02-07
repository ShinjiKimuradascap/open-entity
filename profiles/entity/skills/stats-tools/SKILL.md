---
name: stats-tools
description: Session and agent statistics tools for monitoring runtime performance and activity. Use when the user asks to check agent stats, session info, or switch sessions.
disable-model-invocation: false
user-invocable: true
allowed-tools: get_agent_stats, get_session_stats, set_current_session
version: 1.0.0
tools:
  get_agent_stats:
    description: Get agent runtime statistics
  get_session_stats:
    description: Get current session activity statistics
  set_current_session:
    description: Set active session ID
---

# Stats Tools

Tools for monitoring agent and session statistics.
Use these to check runtime performance, session activity, and switch between sessions.
