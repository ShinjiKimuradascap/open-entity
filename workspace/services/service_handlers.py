#!/usr/bin/env python3
"""
サービスハンドラ実装
AIエージェントが提供する各サービスの実際の実行処理
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# 親ディレクトリをパスに追加（import用）
sys.path.insert(0, str(Path(__file__).parent))

from ai_transaction_protocol import Agreement

logger = logging.getLogger(__name__)


class ServiceExecutionError(Exception):
    """サービス実行エラー"""
    pass


class CodeGenerationHandler:
    """コード生成サービスハンドラ"""
    
    @staticmethod
    def execute(agreement: Agreement, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        コード生成サービスを実行
        
        Args:
            agreement: 取引合意オブジェクト
            context: 追加コンテキスト（要件詳細など）
            
        Returns:
            実行結果
        """
        logger.info(f"Starting code generation for agreement {agreement.agreement_id}")
        
        # タスク詳細を取得
        task_description = context.get("description", "") if context else ""
        requirements = context.get("requirements", []) if context else []
        
        if not task_description:
            raise ServiceExecutionError("Task description is required for code generation")
        
        # 実際のコード生成はcoderエージェントに委譲
        # 注: 実際の実装ではdelegate_to_agentを呼び出す
        # ここではシミュレーション実装
        
        result = {
            "service_type": "code_gen",
            "agreement_id": agreement.agreement_id,
            "status": "completed",
            "deliverables": {
                "files_created": [],
                "code": "",
                "documentation": ""
            },
            "summary": f"Generated code based on: {task_description[:50]}..."
        }
        
        logger.info(f"Code generation completed for agreement {agreement.agreement_id}")
        return result


class CodeReviewHandler:
    """コードレビューサービスハンドラ"""
    
    @staticmethod
    def execute(agreement: Agreement, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        コードレビューサービスを実行
        
        Args:
            agreement: 取引合意オブジェクト
            context: 追加コンテキスト（コード内容など）
            
        Returns:
            実行結果
        """
        logger.info(f"Starting code review for agreement {agreement.agreement_id}")
        
        code_content = context.get("code", "") if context else ""
        file_path = context.get("file_path", "") if context else ""
        
        if not code_content and not file_path:
            raise ServiceExecutionError("Code content or file path is required for code review")
        
        # ファイルパスが指定されている場合は読み込み
        if file_path and not code_content:
            try:
                with open(file_path, 'r') as f:
                    code_content = f.read()
            except Exception as e:
                raise ServiceExecutionError(f"Failed to read file: {e}")
        
        # 実際のコードレビューはcode-reviewerエージェントに委譲
        # ここではシミュレーション実装
        
        result = {
            "service_type": "code_review",
            "agreement_id": agreement.agreement_id,
            "status": "completed",
            "deliverables": {
                "review_report": {
                    "issues_found": 0,
                    "suggestions": [],
                    "quality_score": 0.0
                }
            },
            "summary": f"Reviewed code from {file_path or 'provided content'}"
        }
        
        logger.info(f"Code review completed for agreement {agreement.agreement_id}")
        return result


class DocumentationHandler:
    """ドキュメント作成サービスハンドラ"""
    
    @staticmethod
    def execute(agreement: Agreement, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        ドキュメント作成サービスを実行
        
        Args:
            agreement: 取引合意オブジェクト
            context: 追加コンテキスト（トピックなど）
            
        Returns:
            実行結果
        """
        logger.info(f"Starting documentation creation for agreement {agreement.agreement_id}")
        
        topic = context.get("topic", "") if context else ""
        doc_type = context.get("doc_type", "technical") if context else "technical"
        
        if not topic:
            raise ServiceExecutionError("Topic is required for documentation creation")
        
        # ドキュメント作成処理
        result = {
            "service_type": "doc_creation",
            "agreement_id": agreement.agreement_id,
            "status": "completed",
            "deliverables": {
                "document": "",
                "format": "markdown",
                "sections": []
            },
            "summary": f"Created {doc_type} documentation for: {topic[:50]}..."
        }
        
        logger.info(f"Documentation creation completed for agreement {agreement.agreement_id}")
        return result


class ResearchHandler:
    """調査サービスハンドラ"""
    
    @staticmethod
    def execute(agreement: Agreement, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        調査サービスを実行
        
        Args:
            agreement: 取引合意オブジェクト
            context: 追加コンテキスト（調査クエリなど）
            
        Returns:
            実行結果
        """
        logger.info(f"Starting research for agreement {agreement.agreement_id}")
        
        query = context.get("query", "") if context else ""
        research_type = context.get("type", "general") if context else "general"
        
        if not query:
            raise ServiceExecutionError("Research query is required")
        
        # websearch/webfetchを使用した調査処理
        # ここではシミュレーション実装
        
        result = {
            "service_type": "research",
            "agreement_id": agreement.agreement_id,
            "status": "completed",
            "deliverables": {
                "report": "",
                "sources": [],
                "key_findings": []
            },
            "summary": f"Research completed for: {query[:50]}..."
        }
        
        logger.info(f"Research completed for agreement {agreement.agreement_id}")
        return result


class BugFixHandler:
    """バグ修正サービスハンドラ"""
    
    @staticmethod
    def execute(agreement: Agreement, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        バグ修正サービスを実行
        
        Args:
            agreement: 取引合意オブジェクト
            context: 追加コンテキスト（エラー情報など）
            
        Returns:
            実行結果
        """
        logger.info(f"Starting bug fix for agreement {agreement.agreement_id}")
        
        error_description = context.get("error", "") if context else ""
        file_path = context.get("file_path", "") if context else ""
        
        if not error_description:
            raise ServiceExecutionError("Error description is required for bug fix")
        
        # 実際のバグ修正はcoderエージェントに委譲
        # ここではシミュレーション実装
        
        result = {
            "service_type": "bug_fix",
            "agreement_id": agreement.agreement_id,
            "status": "completed",
            "deliverables": {
                "fixed_files": [],
                "changes_made": [],
                "test_results": ""
            },
            "summary": f"Fixed bug in {file_path or 'target code'}"
        }
        
        logger.info(f"Bug fix completed for agreement {agreement.agreement_id}")
        return result


# サービスハンドラレジストリ
SERVICE_HANDLERS = {
    "code_gen": CodeGenerationHandler,
    "code_review": CodeReviewHandler,
    "doc_creation": DocumentationHandler,
    "research": ResearchHandler,
    "bug_fix": BugFixHandler,
}


def get_service_handler(service_id: str) -> Optional[type]:
    """
    サービスIDに対応するハンドラを取得
    
    Args:
        service_id: サービスID
        
    Returns:
        ハンドラクラス、またはNone
    """
    return SERVICE_HANDLERS.get(service_id)


def register_custom_handler(service_id: str, handler_class: type) -> None:
    """
    カスタムサービスハンドラを登録
    
    Args:
        service_id: サービスID
        handler_class: ハンドラクラス
    """
    SERVICE_HANDLERS[service_id] = handler_class
    logger.info(f"Registered custom handler for service: {service_id}")


def execute_service(service_id: str, agreement: Agreement, 
                   context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    サービスを実行
    
    Args:
        service_id: サービスID
        agreement: 取引合意オブジェクト
        context: 追加コンテキスト
        
    Returns:
        実行結果
        
    Raises:
        ServiceExecutionError: サービス実行に失敗した場合
    """
    handler_class = get_service_handler(service_id)
    
    if not handler_class:
        raise ServiceExecutionError(f"Unknown service: {service_id}")
    
    try:
        return handler_class.execute(agreement, context)
    except Exception as e:
        logger.exception(f"Service execution failed: {e}")
        raise ServiceExecutionError(f"Service execution failed: {e}")


# 実際のサブエージェント委譲を行う実装（将来的な拡張）
class SubAgentDelegator:
    """
    サブエージェントへの委譲を管理するクラス
    
    将来的にはここでdelegate_to_agentを呼び出す
    """
    
    @staticmethod
    def delegate_to_coder(task: str) -> str:
        """
        coderエージェントにタスクを委譲
        
        Args:
            task: タスク説明
            
        Returns:
            実行結果
        """
        # 実際の実装:
        # result = delegate_to_agent(agent_name="coder", task=task)
        # return result
        
        # シミュレーション:
        return f"[SIMULATION] Delegated to coder: {task[:50]}..."
    
    @staticmethod
    def delegate_to_reviewer(code: str) -> str:
        """
        code-reviewerエージェントにタスクを委譲
        
        Args:
            code: レビュー対象コード
            
        Returns:
            レビュー結果
        """
        # 実際の実装:
        # result = delegate_to_agent(
        #     agent_name="code-reviewer",
        #     task=f"Review this code:\n{code}"
        # )
        # return result
        
        # シミュレーション:
        return f"[SIMULATION] Delegated to reviewer: {len(code)} chars"


if __name__ == "__main__":
    # 簡易テスト
    logging.basicConfig(level=logging.INFO)
    
    print("Service Handlers Test")
    print("=" * 50)
    
    # テスト用Agreement
    test_agreement = Agreement(
        agreement_id="test-001",
        client_id="client-001",
        provider_id="provider-001",
        confirmed_amount=10.0
    )
    
    # 各ハンドラのテスト
    for service_id in SERVICE_HANDLERS.keys():
        handler = get_service_handler(service_id)
        print(f"\n{service_id}: {handler.__name__}")
        
        try:
            result = handler.execute(test_agreement, {
                "description": f"Test {service_id}",
                "code": "print('hello')",
                "topic": "Test topic"
            })
            print(f"  Status: {result['status']}")
            print(f"  Summary: {result['summary'][:40]}...")
        except ServiceExecutionError as e:
            print(f"  Expected error: {e}")
    
    print("\n" + "=" * 50)
    print("Test completed")
