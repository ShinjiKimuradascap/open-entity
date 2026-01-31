#!/usr/bin/env python3
"""
自律的収益システムのセットアップ
サービスハンドラを登録し、収益化を開始する
"""

import logging
from typing import Dict, Any

from autonomous_revenue_system import get_revenue_system, AutonomousRevenueSystem
from service_handlers import (
    execute_service, ServiceExecutionError,
    CodeGenerationHandler, CodeReviewHandler,
    DocumentationHandler, ResearchHandler, BugFixHandler
)
from ai_transaction_protocol import Agreement

logger = logging.getLogger(__name__)


def setup_service_handlers(revenue_system: AutonomousRevenueSystem) -> None:
    """
    収益システムにサービスハンドラを登録
    
    Args:
        revenue_system: 収益システムインスタンス
    """
    
    def code_gen_handler(agreement: Agreement) -> bool:
        """コード生成サービス実行"""
        try:
            result = CodeGenerationHandler.execute(
                agreement,
                context={"description": "Generated code for client request"}
            )
            logger.info(f"Code generation completed: {result['summary']}")
            return True
        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            return False
    
    def code_review_handler(agreement: Agreement) -> bool:
        """コードレビューサービス実行"""
        try:
            result = CodeReviewHandler.execute(
                agreement,
                context={"code": "# Sample code to review"}
            )
            logger.info(f"Code review completed: {result['summary']}")
            return True
        except Exception as e:
            logger.error(f"Code review failed: {e}")
            return False
    
    def doc_creation_handler(agreement: Agreement) -> bool:
        """ドキュメント作成サービス実行"""
        try:
            result = DocumentationHandler.execute(
                agreement,
                context={"topic": "Technical documentation"}
            )
            logger.info(f"Documentation completed: {result['summary']}")
            return True
        except Exception as e:
            logger.error(f"Documentation failed: {e}")
            return False
    
    def research_handler(agreement: Agreement) -> bool:
        """調査サービス実行"""
        try:
            result = ResearchHandler.execute(
                agreement,
                context={"query": "Research query"}
            )
            logger.info(f"Research completed: {result['summary']}")
            return True
        except Exception as e:
            logger.error(f"Research failed: {e}")
            return False
    
    def bug_fix_handler(agreement: Agreement) -> bool:
        """バグ修正サービス実行"""
        try:
            result = BugFixHandler.execute(
                agreement,
                context={"error": "Bug description"}
            )
            logger.info(f"Bug fix completed: {result['summary']}")
            return True
        except Exception as e:
            logger.error(f"Bug fix failed: {e}")
            return False
    
    # ハンドラを登録
    revenue_system.register_service_handler("code_gen", code_gen_handler)
    revenue_system.register_service_handler("code_review", code_review_handler)
    revenue_system.register_service_handler("doc_creation", doc_creation_handler)
    revenue_system.register_service_handler("research", research_handler)
    revenue_system.register_service_handler("bug_fix", bug_fix_handler)
    
    logger.info("All service handlers registered successfully")


def initialize_revenue_system(agent_id: str = "open_entity") -> AutonomousRevenueSystem:
    """
    収益システムを初期化し、サービスハンドラを登録
    
    Args:
        agent_id: エージェントID
        
    Returns:
        初期化済みの収益システム
    """
    revenue_system = get_revenue_system(agent_id)
    setup_service_handlers(revenue_system)
    
    logger.info(f"Revenue system initialized for agent: {agent_id}")
    return revenue_system


def get_service_menu() -> Dict[str, Dict[str, Any]]:
    """
    提供可能なサービスメニューを取得
    
    Returns:
        サービスメニュー
    """
    return {
        "code_gen": {
            "name": "Code Generation",
            "description": "Generate Python/JS/TS code based on requirements",
            "base_price": 10.0,
            "estimated_time_minutes": 30,
            "capabilities": ["coding", "python", "javascript"]
        },
        "code_review": {
            "name": "Code Review",
            "description": "Review code quality and suggest improvements",
            "base_price": 5.0,
            "estimated_time_minutes": 15,
            "capabilities": ["review", "analysis"]
        },
        "doc_creation": {
            "name": "Documentation Creation",
            "description": "Create technical documentation and design docs",
            "base_price": 8.0,
            "estimated_time_minutes": 20,
            "capabilities": ["writing", "documentation"]
        },
        "research": {
            "name": "Research Task",
            "description": "Web research and report generation",
            "base_price": 20.0,
            "estimated_time_minutes": 60,
            "capabilities": ["research", "analysis"]
        },
        "bug_fix": {
            "name": "Bug Fix",
            "description": "Debug and fix issues in code",
            "base_price": 15.0,
            "estimated_time_minutes": 45,
            "capabilities": ["debugging", "coding"]
        },
    }


def print_service_menu() -> None:
    """サービスメニューを表示"""
    menu = get_service_menu()
    
    print("\n" + "=" * 60)
    print("🤖 AI Service Menu - Available Services")
    print("=" * 60)
    
    for service_id, info in menu.items():
        print(f"\n📦 {info['name']} ({service_id})")
        print(f"   💰 Price: {info['base_price']} AIC")
        print(f"   ⏱️  Estimated time: {info['estimated_time_minutes']} minutes")
        print(f"   📝 {info['description']}")
        print(f"   🔧 Capabilities: {', '.join(info['capabilities'])}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("\n🚀 Initializing Autonomous Revenue System...")
    
    # システム初期化
    revenue_system = initialize_revenue_system("open_entity")
    
    # サービスメニュー表示
    print_service_menu()
    
    # 収益サマリー表示（空）
    summary = revenue_system.get_revenue_summary()
    print(f"\n📊 Revenue Summary (Last 30 days)")
    print(f"   Total: {summary['total_revenue']} AIC")
    print(f"   Transactions: {summary['transaction_count']}")
    
    print("\n✅ Revenue system is ready!")
    print("   Waiting for service requests...")
