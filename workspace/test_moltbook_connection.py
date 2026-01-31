#!/usr/bin/env python3
"""
Moltbook接続テストスクリプト
API Key取得後、接続確認用に実行
"""

import asyncio
import os
import sys

sys.path.insert(0, 'services')

from moltbook_integration import MoltbookAgentClient, create_moltbook_agent_client


async def test_connection():
    """Moltbook接続テスト"""
    print("=" * 50)
    print("Moltbook Connection Test")
    print("=" * 50)
    
    api_key = os.getenv("MOLTBOOK_API_KEY")
    agent_id = os.getenv("MOLTBOOK_AGENT_ID")
    x_code = os.getenv("MOLTBOOK_X_CODE")
    
    print(f"\n[1/5] Environment Check")
    print(f"  MOLTBOOK_API_KEY: {'Set' if api_key else 'NOT SET'}")
    print(f"  MOLTBOOK_AGENT_ID: {'Set' if agent_id else 'NOT SET'}")
    print(f"  MOLTBOOK_X_CODE: {'Set' if x_code else 'NOT SET'}")
    
    if not api_key or not agent_id:
        print("\nERROR: Required environment variables not set")
        print("Please set MOLTBOOK_API_KEY and MOLTBOOK_AGENT_ID")
        return False
    
    print(f"\n[2/5] Creating Client")
    try:
        client = MoltbookAgentClient(api_key=api_key, agent_id=agent_id)
        print(f"  Client created successfully")
        print(f"  Agent ID: {client.agent_id}")
        print(f"  Base URL: {client.base_url}")
    except Exception as e:
        print(f"  ERROR: {e}")
        return False
    
    if x_code:
        print(f"\n[3/5] Authentication")
        try:
            result = await client.authenticate(x_verification_code=x_code)
            print(f"  Authentication: {'SUCCESS' if result else 'FAILED'}")
            print(f"  Verified: {client._verified}")
        except Exception as e:
            print(f"  ERROR: {e}")
            print("  Continuing with unauthenticated client...")
    else:
        print(f"\n[3/5] Authentication (skipped - no X_CODE)")
    
    print(f"\n[4/5] Get Feed (Read-only test)")
    try:
        posts = await client.get_feed(limit=5)
        print(f"  Feed fetched successfully")
        print(f"  Posts retrieved: {len(posts)}")
        if posts:
            print(f"  Latest post: {posts[0].content[:50]}...")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    if client._verified:
        print(f"\n[5/5] Create Test Post")
        try:
            post = await client.create_post(
                content="Hello Moltbook! This is a test post from Open Entity.",
                submolt="ai_agents"
            )
            print(f"  Post created successfully")
            print(f"  Post ID: {post.id}")
            print(f"  Content: {post.content[:50]}...")
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        print(f"\n[5/5] Create Test Post (skipped - not authenticated)")
    
    await client.close()
    
    print("\n" + "=" * 50)
    print("Test Complete")
    print("=" * 50)
    return True


if __name__ == "__main__":
    # Load .env if exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("Loaded .env file")
    except ImportError:
        pass
    
    result = asyncio.run(test_connection())
    sys.exit(0 if result else 1)
