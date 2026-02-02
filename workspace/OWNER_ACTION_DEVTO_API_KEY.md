# Dev.to API Key Acquisition Required

## Purpose
Enable automated posting to Dev.to via API

## Steps for Owner
1. Go to https://dev.to/settings/extensions
2. Scroll to "DEV API Keys" section
3. Click "Generate API Key"
4. Copy the generated key
5. Add to environment: `export DEVTO_API_KEY=your_key_here`

## Current Status
- Dev.to article prepared: `content/devto_post.md`
- Posting script ready: `scripts/auto_post_devto.py`
- Blocked: API key required

## Priority
Medium - Can manually post for now, automation desired for future posts
