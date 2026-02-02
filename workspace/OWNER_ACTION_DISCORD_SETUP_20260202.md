# Discord Outreach Setup Request

## Objective
Acquire external AI agents via Discord outreach to AutoGPT/CrewAI/LangChain communities

## Current Status
- [x] Outreach content created (3 variants)
- [x] Discord client implementation verified
- [ ] Bot token and channel IDs needed

## Required Actions

### 1. Create Discord Bot
1. Visit https://discord.com/developers/applications
2. "New Application" -> "Create"
3. "Bot" -> "Add Bot" -> "Yes, do it!"
4. "Reset Token" -> Copy token

### 2. Set Environment Variables
export DISCORD_BOT_TOKEN="your_bot_token"
export DISCORD_CHANNEL_ID_AUTO_GPT="channel_id"
export DISCORD_CHANNEL_ID_CREWAI="channel_id"
export DISCORD_CHANNEL_ID_LANGCHAIN="channel_id"

### 3. Invite Bot to Servers
- OAuth2 -> URL Generator
- Scope: bot
- Permissions: Send Messages, Read Message History

## Ready-to-Post Content
- AutoGPT: content/outreach/autogpt_discord_post.md
- CrewAI: content/outreach/crewai_discord_post.md
- LangChain: content/outreach/langchain_discord_post.md

## Campaign Target
- Discord: 3 approaches -> 1 conversion
- Current: 0/3

---
Created: 2026-02-02
Priority: HIGH
