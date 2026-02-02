# URGENT: API Keys Required for User Acquisition

**Date:** 2026-02-02 00:17 JST  
**Priority:** HIGH

## Blocker Summary

External AI agent acquisition is BLOCKED due to missing API credentials.

| Platform | Status |
|:---------|:-------|
| Reddit API | Missing |
| Discord Bot | Missing |
| Dev.to API | Missing |
| ProductHunt Dev Token | Missing |

## Required Actions (Owner)

### 1. Reddit API Credentials
- Go to https://www.reddit.com/prefs/apps
- Create "script" type app
- Set env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD

### 2. Discord Bot Token
- Go to https://discord.com/developers/applications
- Create application, add bot
- Set env var: DISCORD_BOT_TOKEN

### 3. Dev.to API Key
- Go to https://dev.to/settings/extensions
- Set env var: DEVTO_API_KEY

### 4. ProductHunt Dev Token
- Go to https://www.producthunt.com/v2/oauth/applications
- Set env var: PRODUCTHUNT_DEV_TOKEN

## Alternative: Manual Outreach Ready

Target communities identified, messages prepared:
- AutoGPT Discord
- LangChain Discord  
- Reddit r/AI_Agents, r/artificial, r/MachineLearning

Next Action: Provide credentials within 12 hours before PH launch.
