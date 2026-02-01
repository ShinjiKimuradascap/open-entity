#!/usr/bin/env python3
"""
Hugging Face Spacesへのデプロイスクリプト
FastAPIアプリをSpacesで動作させるための設定
"""

import os
import subprocess
import sys

# Hugging Face Spaces用のDockerfile作成
DOCKERFILE_CONTENT = '''FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["python", "services/api_server.py"]
'''

# Spaces用のREADME作成
README_CONTENT = '''---
title: Open Entity API
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
---

# Open Entity API

AI Collaboration Platform - P2P Network for AI Agents

## Endpoints

- `/health` - Health check
- `/api/v0/discovery/nodes` - List discovered nodes
- `/api/v0/marketplace/services` - List services
'''

def setup_huggingface_files():
    """Hugging Face Spaces用のファイルを作成"""
    
    # Dockerfile作成
    with open('Dockerfile.spaces', 'w') as f:
        f.write(DOCKERFILE_CONTENT)
    print("✅ Created Dockerfile.spaces")
    
    # README作成
    with open('README_spaces.md', 'w') as f:
        f.write(README_CONTENT)
    print("✅ Created README_spaces.md")
    
    # 必要な環境変数を確認
    required_env = ['HUGGINGFACE_TOKEN']
    missing = [env for env in required_env if not os.getenv(env)]
    
    if missing:
        print(f"\n⚠️ Missing environment variables: {missing}")
        print("Set them with: export HUGGINGFACE_TOKEN=your_token")
        return False
    
    return True

def deploy():
    """Hugging Face Spacesにデプロイ"""
    token = os.getenv('HUGGINGFACE_TOKEN')
    if not token:
        print("❌ HUGGINGFACE_TOKEN not set")
        return False
    
    # レポジトリ名
    repo_name = "open-entity-api"
    
    print(f"🚀 Deploying to Hugging Face Spaces: {repo_name}")
    print("\n📋 Manual deployment steps:")
    print("1. Go to https://huggingface.co/new-space")
    print(f"2. Create space: {repo_name}")
    print("3. Select 'Docker' SDK")
    print("4. Clone the space:")
    print(f"   git clone https://huggingface.co/spaces/your-username/{repo_name}")
    print("5. Copy files and push")
    
    return True

if __name__ == '__main__':
    if setup_huggingface_files():
        deploy()
