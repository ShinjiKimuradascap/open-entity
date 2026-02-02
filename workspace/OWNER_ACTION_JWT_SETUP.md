# OWNER ACTION REQUIRED: JWT_SECRET Setup

## Problem
GCP Cloud Run deployed API services have JWT authentication issues due to missing JWT_SECRET environment variable.

## Generated JWT_SECRET
jLwz85W5soadfdEC4xN9oxaXDWzsHXk1jK_f8KiVUVZ93BAGEZXiOQFsZKXbw_Abj_pUqYQd4YwQXXIplR7Oxw

## Steps

1. Set JWT_SECRET in GitHub Secrets:
   - Via CLI: gh secret set JWT_SECRET --body "jLwz85W5soadfdEC4xN9oxaXDWzsHXk1jK_f8KiVUVZ93BAGEZXiOQFsZKXbw_Abj_pUqYQd4YwQXXIplR7Oxw"
   - Or Web UI: Settings -> Secrets and variables -> Actions -> New repository secret

2. Commit workflow changes (already done in .github/workflows/deploy-messaging-api.yml)

3. Run manual deploy via GitHub Actions

## Impact
- messaging-api (Cloud Run) - Fixed with this change
- api-server (Render) - Check env vars separately
- ai-roulette (Fly.io) - Check env vars separately
