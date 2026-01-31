#!/usr/bin/env python3
"""
Entity B: Moltbook Client 動作確認テスト
"""
import sys
import os
sys.path.insert(0, '/home/moco/workspace')

from datetime import datetime, timedelta

def test_moltbook_client():
    print("=" * 50)
    print("Entity B: Moltbook Client 動作確認")
    print("=" * 50)
    
    try:
        from services.moltbook_identity_client import (
                    MoltbookClient,
                    MoltbookAgent,
                    IdentityToken,
                    RateLimitInfo
                )
        print("✅ Moltbook Client インポート成功")
    except Exception as e:
        print(f"❌ インポート失敗: {e}")
        return False
    
    # RateLimitInfo テスト
    try:
        info = RateLimitInfo(
            limit=100, 
            remaining=50, 
            reset_at=datetime.utcnow() + timedelta(hours=1)
        )
        assert info.limit == 100
        assert info.remaining == 50
        assert info.is_exceeded() == False
        print(f"✅ RateLimitInfo: limit={info.limit}, remaining={info.remaining}")
    except Exception as e:
        print(f"❌ RateLimitInfo テスト失敗: {e}")
        return False
    
    # IdentityToken テスト
    try:
        token = IdentityToken(
            token='test_token_abc123', 
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        assert token.is_valid() == True
        print(f"✅ IdentityToken: valid={token.is_valid()}")
    except Exception as e:
        print(f"❌ IdentityToken テスト失敗: {e}")
        return False
    
    # MoltbookClient 初期化テスト
    try:
        client = MoltbookClient(api_key='test_api_key_12345')
        assert client.api_key == 'test_api_key_12345'
        print(f"✅ MoltbookClient 初期化成功")
    except Exception as e:
        print(f"❌ MoltbookClient 初期化失敗: {e}")
        return False
    
    # MoltbookAgent 作成テスト
    try:
        agent = MoltbookAgent(
            id="agent_test_001",
            name="Test Agent",
            description="A test agent for Entity B",
            karma=100,
            avatar_url=None,
            verified=True,
            created_at=datetime.utcnow(),
            follower_count=50,
            post_count=10,
            comment_count=25,
            owner_x_handle="@testuser",
            owner_x_name="Test User",
            owner_x_verified=True,
            owner_x_follower_count=1000
        )
        assert agent.name == "Test Agent"
        assert agent.karma == 100
        print(f"✅ MoltbookAgent 作成成功: {agent.name} (karma={agent.karma})")
    except Exception as e:
        print(f"❌ MoltbookAgent 作成失敗: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("✅ 全テスト成功 - Moltbook Client 動作正常")
    print("=" * 50)
    return True

if __name__ == "__main__":
    success = test_moltbook_client()
    sys.exit(0 if success else 1)
