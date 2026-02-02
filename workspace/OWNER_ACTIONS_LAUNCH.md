# OWNER ACTIONS REQUIRED - Launch Blockers

## 1. Frontend Deploy (CRITICAL for Product Hunt)
**Options:**
- **Fly.io**: `cd frontend && flyctl deploy` (fly auth login required)
- **GCP**: `cd frontend && gcloud app deploy` (gcloud auth required)  
- **Streamlit Cloud**: Connect GitHub repo to streamlit.io

**Impact**: Product Hunt launch can proceed without this (API is live), but conversion will be lower.

---

## 2. API Keys for Marketing Automation

### Reddit API (for auto-posting)
1. Go to https://www.reddit.com/prefs/apps
2. Create "script" app
3. Set env vars:
   - REDDIT_CLIENT_ID=xxx
   - REDDIT_CLIENT_SECRET=xxx
   - REDDIT_USERNAME=xxx
   - REDDIT_PASSWORD=xxx

### Dev.to API (for tech blog)
1. Go to https://dev.to/settings/extensions
2. Generate API key
3. Set env var: DEVTO_API_KEY=xxx

---

## 3. Qiita Article Post (5 min)
Manual post using: content/qiita_article_20260202.md
- Login: https://qiita.com/login
- New post: https://qiita.com/drafts/new
- Paste content and publish

---

## Launch Timeline

### Now → 26 hours (Feb 2, 9AM PST)
- [ ] Owner: Deploy frontend (optional but recommended)
- [ ] Owner: Post Qiita article
- [ ] System: Monitor API health every 15 min ✓ (automated)

### T-0 (Feb 2, 9AM PST)
- [ ] Product Hunt launch (manual or script)
- [ ] Activate monitoring dashboard

### T+3 hours
- [ ] Submit Show HN
- [ ] Reddit post (r/artificial, r/machinelearning)

---

## Current Status Without Owner Actions
- API Live: http://34.134.116.148:8080 ✅
- Product Hunt materials ready ✅
- Show HN post ready ✅
- Reddit posts ready ✅
- Automated monitoring active ✅
- Frontend: Not deployed (API-only launch) ⚠️
- Qiita: Not posted ⚠️

VERDICT: Launch can proceed with API-only. Frontend deploy increases conversion but is not blocking.
