#!/usr/bin/env python3
"""
統合テストスイート
AI Collaboration Platform - 全機能テスト
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import traceback


def run_test_module(module_name, test_function):
    """テストモジュールを実行"""
    print(f"\n{'='*60}")
    print(f"Running: {module_name}")
    print('='*60)
    
    try:
        result = test_function()
        if result == 0:
            print(f"✅ {module_name} PASSED")
            return True
        else:
            print(f"❌ {module_name} FAILED")
            return False
    except Exception as e:
        print(f"❌ {module_name} ERROR: {e}")
        traceback.print_exc()
        return False


def main():
    """全テスト実行"""
    print("="*60)
    print("AI Collaboration Platform - Integration Test Suite")
    print("="*60)
    
    results = []
    
    # 1. 署名機能テスト
    try:
        from test_signature import main as signature_main
        results.append(("Signature Tests", run_test_module("Signature", signature_main)))
    except Exception as e:
        print(f"⚠️ Signature tests skipped: {e}")
        results.append(("Signature Tests", False))
    
    # 2. トークン転送テスト
    try:
        from test_token_transfer import main as token_main
        results.append(("Token Transfer Tests", run_test_module("Token Transfer", token_main)))
    except Exception as e:
        print(f"⚠️ Token transfer tests skipped: {e}")
        results.append(("Token Transfer Tests", False))
    
    # 3. 評価システムテスト
    try:
        from test_rating_system import main as rating_main
        results.append(("Rating System Tests", run_test_module("Rating System", rating_main)))
    except Exception as e:
        print(f"⚠️ Rating system tests skipped: {e}")
        results.append(("Rating System Tests", False))
    
    # 4. API統合テスト（オプション - FastAPI必要）
    try:
        from fastapi.testclient import TestClient
        from test_api_integration import main as api_main
        results.append(("API Integration Tests", run_test_module("API Integration", api_main)))
    except ImportError:
        print("\n⚠️ API Integration tests skipped (FastAPI not available)")
        results.append(("API Integration Tests", None))  # None = skipped
    except Exception as e:
        print(f"⚠️ API integration tests error: {e}")
        results.append(("API Integration Tests", False))
    
    # 結果サマリー
    print("\n" + "="*60)
    print("Test Results Summary")
    print("="*60)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, result in results:
        if result is True:
            print(f"✅ {name}: PASSED")
            passed += 1
        elif result is False:
            print(f"❌ {name}: FAILED")
            failed += 1
        else:
            print(f"⚠️  {name}: SKIPPED")
            skipped += 1
    
    print("-"*60)
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")
    print("="*60)
    
    if failed == 0:
        print("\n🎉 All available tests passed!")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
