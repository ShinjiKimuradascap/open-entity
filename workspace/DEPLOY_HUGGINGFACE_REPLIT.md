# Hugging Face + Replit Deployment Guide

## Hugging Face Spaces

### Files Created
- `huggingface/app.py` - Gradio interface
- `huggingface/requirements.txt` - Dependencies
- `huggingface/README.md` - Space documentation

### Deployment Steps (Owner Action Required)
1. Go to https://huggingface.co/spaces
2. Click "Create new Space"
3. Select "Gradio" SDK
4. Upload files from `huggingface/` folder
5. Deploy

### Benefits
- Visual demo of Open Entity API
- Discoverable by AI community
- Live status dashboard

## Replit Template

### Files Created
- `replit/main.py` - Agent template
- `replit/.replit` - Replit config
- `replit/replit.nix` - Nix dependencies

### Deployment Steps (Owner Action Required)
1. Go to https://replit.com
2. Create new Repl from template
3. Upload files from `replit/` folder
4. Set ENTITY_ID and CAPABILITIES env vars
5. Deploy

### Benefits
- One-click agent deployment
- No setup required
- Easy for developers to join

## Next Steps
- [ ] Deploy Hugging Face Space
- [ ] Publish Replit template
- [ ] Share on social media
- [ ] Track WAA growth
