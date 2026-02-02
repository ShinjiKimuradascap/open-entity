#!/usr/bin/env python3
"""
Knowledge Sharing System Demo

Entity間知識共有システムのデモンストレーション

使用方法:
    python examples/knowledge_sharing_demo.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.knowledge_sharing import (
    KnowledgeSharingSystem, KnowledgeType, KnowledgeStatus,
    get_knowledge_sharing_system, reset_knowledge_sharing_system,
    share_skill, search_skills, get_knowledge_stats
)
from services.self_learning_system import get_learning_system


def demo_basic_usage():
    """基本的な使い方のデモ"""
    print("=== Knowledge Sharing System Demo ===\n")
    
    # システム初期化
    print("1. システム初期化")
    reset_knowledge_sharing_system()
    system = get_knowledge_sharing_system(
        entity_id="demo_entity",
        self_learning_system=get_learning_system()
    )
    print(f"   ✓ Entity '{system.entity_id}' の知識共有システムを初期化しました\n")
    
    # 知識を公開
    print("2. 知識を公開")
    
    skill1 = system.publish_knowledge(
        item_type=KnowledgeType.SKILL,
        title="Python Best Practices",
        description="Clean code principles and design patterns for Python",
        content={
            "principles": ["DRY", "KISS", "SOLID"],
            "patterns": ["Factory", "Observer", "Strategy"],
            "examples": [
                {"title": "Factory Pattern", "code": "class Factory: ..."}
            ]
        },
        tags=["python", "programming", "best-practices"],
        quality_score=0.92,
        notify_peers=False
    )
    print(f"   ✓ スキルを公開: '{skill1.title}' (品質: {skill1.quality_score})")
    
    skill2 = system.publish_knowledge(
        item_type=KnowledgeType.SKILL,
        title="Machine Learning Basics",
        description="Introduction to ML algorithms and techniques",
        content={
            "algorithms": ["Linear Regression", "Decision Trees", "Neural Networks"],
            "frameworks": ["scikit-learn", "TensorFlow", "PyTorch"],
            "use_cases": ["Classification", "Regression", "Clustering"]
        },
        tags=["ml", "ai", "data-science"],
        quality_score=0.85,
        notify_peers=False
    )
    print(f"   ✓ スキルを公開: '{skill2.title}' (品質: {skill2.quality_score})")
    
    experience = system.publish_knowledge(
        item_type=KnowledgeType.EXPERIENCE,
        title="API Performance Optimization",
        description="How we improved API response time by 50%",
        content={
            "problem": "Slow API responses",
            "solution": "Caching and query optimization",
            "result": "50% improvement",
            "duration": "2 weeks"
        },
        tags=["performance", "api", "optimization"],
        quality_score=0.78,
        notify_peers=False
    )
    print(f"   ✓ 経験を公開: '{experience.title}' (品質: {experience.quality_score})\n")
    
    # 知識を検索
    print("3. 知識を検索")
    
    all_skills = system.search_knowledge(
        item_type=KnowledgeType.SKILL,
        local_only=True
    )
    print(f"   ✓ スキル検索結果: {len(all_skills)} 件")
    for skill in all_skills:
        print(f"     - {skill.title} (品質: {skill.quality_score})")
    
    python_skills = system.search_knowledge(
        query="Python",
        local_only=True
    )
    print(f"\n   ✓ 'Python' 検索結果: {len(python_skills)} 件")
    for skill in python_skills:
        print(f"     - {skill.title}")
    
    high_quality = system.search_knowledge(
        min_quality=0.90,
        local_only=True
    )
    print(f"\n   ✓ 高品質(0.90以上)検索結果: {len(high_quality)} 件")
    for item in high_quality:
        print(f"     - {item.title} (品質: {item.quality_score})")
    
    # タグで検索
    print("\n4. タグで検索")
    ai_skills = system.search_knowledge(
        tags=["ai"],
        local_only=True
    )
    print(f"   ✓ 'ai' タグ検索結果: {len(ai_skills)} 件")
    for item in ai_skills:
        print(f"     - {item.title} (タグ: {', '.join(item.tags)})")
    
    # 統計情報
    print("\n5. 統計情報")
    stats = system.get_statistics()
    print(f"   ✓ Entity: {stats['entity_id']}")
    print(f"   ✓ 公開知識数: {stats['published_count']}")
    print(f"   ✓ 取得知識数: {stats['acquired_count']}")
    print(f"   ✓ 統合知識数: {stats['integrated_count']}")
    print(f"   ✓ 共有回数: {stats['share_count']}")
    print(f"   ✓ タイプ別内訳:")
    for type_name, count in stats['by_type']['published'].items():
        print(f"     - {type_name}: {count} 件")
    
    # ショートカット関数のデモ
    print("\n6. ショートカット関数")
    
    # share_skill
    new_skill = share_skill(
        name="Rust Programming",
        description="Systems programming with Rust",
        content={
            "concepts": ["Ownership", "Borrowing", "Lifetimes"],
            "use_cases": ["Systems", "WebAssembly", "Embedded"]
        },
        tags=["rust", "systems-programming"],
        quality=0.88
    )
    print(f"   ✓ share_skill() で公開: '{new_skill.title}'")
    
    # search_skills
    found_skills = search_skills(query="Programming", min_quality=0.8)
    print(f"   ✓ search_skills() で検索: {len(found_skills)} 件")
    
    # get_knowledge_stats
    current_stats = get_knowledge_stats()
    print(f"   ✓ get_knowledge_stats(): 公開 {current_stats['published_count']} 件")
    
    print("\n=== Demo Complete ===")


def demo_integration_with_learning():
    """SelfLearningSystemとの連携デモ"""
    print("\n=== Integration with SelfLearningSystem ===\n")
    
    # システム初期化
    reset_knowledge_sharing_system()
    learning_system = get_learning_system()
    sharing_system = get_knowledge_sharing_system(
        entity_id="learning_entity",
        self_learning_system=learning_system
    )
    
    print("1. 経験を記録（直接ExperienceCollectorを使用）")
    from services.experience_collector import TaskResult, get_experience_collector
    
    collector = get_experience_collector()
    for i in range(5):
        record_id = collector.record_task_execution(
            task_id=f"task-{i}",
            task_type="code_generation",
            result=TaskResult.SUCCESS if i % 5 != 0 else TaskResult.FAILURE,
            duration=2.5 + i * 0.5,
            resources={"memory_mb": 100 + i * 10, "cpu_percent": 20},
            context={"language": "python"}
        )
        print(f"   ✓ 経験を記録: {record_id}")
    
    print("\n2. 学習ループを実行")
    result = learning_system.run_learning_loop(
        min_confidence=0.5,
        auto_register_skills=False
    )
    print(f"   ✓ パターン識別: {len(result.get('patterns', []))} 件")
    print(f"   ✓ スキル生成: {len(result.get('skills', []))} 件")
    
    print("\n3. 学習したスキルを公開")
    published = sharing_system.publish_skills_from_learning(min_quality=0.5)
    print(f"   ✓ {len(published)} 件のスキルを公開")
    for item in published:
        print(f"     - {item.title}")
    
    print("\n4. 学習したパターンを公開")
    patterns = sharing_system.publish_experiences_from_learning(
        days_back=30,
        min_quality=0.5
    )
    print(f"   ✓ {len(patterns)} 件のパターンを公開")
    
    print("\n5. 共有可能な知識を取得")
    shareable = sharing_system.get_shareable_knowledge(min_quality=0.5)
    total = sum(len(items) for items in shareable.values())
    print(f"   ✓ 共有可能な知識: {total} 件")
    for type_name, items in shareable.items():
        if items:
            print(f"     - {type_name}: {len(items)} 件")
    
    print("\n=== Integration Demo Complete ===")


def demo_export():
    """エクスポート機能のデモ"""
    print("\n=== Export Demo ===\n")
    
    reset_knowledge_sharing_system()
    system = get_knowledge_sharing_system(entity_id="export_entity")
    
    # いくつかの知識を公開
    for i in range(3):
        system.publish_knowledge(
            item_type=KnowledgeType.SKILL,
            title=f"Skill {i+1}",
            description=f"Description for skill {i+1}",
            content={"index": i},
            quality_score=0.8 + i * 0.05,
            notify_peers=False
        )
    
    # エクスポート
    export_path = "/tmp/knowledge_export_demo.json"
    success = system.export_knowledge_data(export_path)
    
    if success:
        print(f"✓ 知識データをエクスポート: {export_path}")
        with open(export_path, 'r') as f:
            import json
            data = json.load(f)
        
        print(f"  - エクスポート日時: {data['export_info']['exported_at']}")
        print(f"  - 公開知識数: {len(data['published'])}")
        print(f"  - 取得知識数: {len(data['acquired'])}")
        print(f"  - 統合知識数: {len(data['integrated_ids'])}")
    else:
        print("✗ エクスポートに失敗しました")
    
    print("\n=== Export Demo Complete ===")


if __name__ == "__main__":
    try:
        demo_basic_usage()
        demo_integration_with_learning()
        demo_export()
        
        print("\n" + "=" * 50)
        print("All demos completed successfully!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
