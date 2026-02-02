# Fly.io Deploy Guide

## Steps
1. fly auth login
2. fly apps create simple-ai-messaging
3. fly deploy --config fly.simple.toml
4. fly status --app simple-ai-messaging

## Verify
curl https://simple-ai-messaging.fly.dev/health

## Cost
Free tier: $5/month
