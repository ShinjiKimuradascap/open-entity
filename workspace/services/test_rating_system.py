#!/usr/bin/env python3
"""
評価・評判システムテスト
エンティティ間の評価と評判スコア計算の動作確認
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from token_system import (
    get_reputation_contract, create_wallet, delete_wallet,
    ReputationContract, Rating, RewardType
)


def test_rating_submission():
    """評価送信テスト"""
    print("\n=== Rating Submission Test ===")
    
    # 評判システム取得
    reputation = get_reputation_contract()
    
    # 評価を送信
    rating = Rating(
        from_entity_id="evaluator-1",
        to_entity_id="worker-1",
        task_id="task-001",
        quality_score=4.5,
        communication_score=5.0,
        timeliness_score=4.0,
        comment="Great work!"
    )
    
    success = reputation.submit_rating(rating)
    assert success is True, "Rating submission should succeed"
    
    print(f"✅ Rating submitted: {rating.quality_score}/5.0")
    print(f"   From: {rating.from_entity_id} -> To: {rating.to_entity_id}")


def test_reputation_calculation():
    """評判スコア計算テスト"""
    print("\n=== Reputation Calculation Test ===")
    
    reputation = get_reputation_contract()
    
    # 複数の評価を送信
    ratings_data = [
        ("evaluator-1", 4.5, 5.0, 4.0),
        ("evaluator-2", 5.0, 4.5, 5.0),
        ("evaluator-3", 3.5, 4.0, 4.5),
    ]
    
    for i, (evaluator, q, c, t) in enumerate(ratings_data):
        rating = Rating(
            from_entity_id=evaluator,
            to_entity_id="worker-reputation",
            task_id=f"task-{i}",
            quality_score=q,
            communication_score=c,
            timeliness_score=t
        )
        reputation.submit_rating(rating)
    
    # 評判情報を取得
    rep_info = reputation.get_reputation("worker-reputation")
    
    assert rep_info is not None, "Reputation info should exist"
    assert rep_info.rating_count == 3, f"Expected 3 ratings, got {rep_info.rating_count}"
    
    # 平均スコアを計算
    expected_quality = sum([r[1] for r in ratings_data]) / 3
    assert abs(rep_info.average_quality_score - expected_quality) < 0.01
    
    print(f"✅ Reputation calculated:")
    print(f"   Rating count: {rep_info.rating_count}")
    print(f"   Avg quality: {rep_info.average_quality_score:.2f}")
    print(f"   Avg communication: {rep_info.average_communication_score:.2f}")
    print(f"   Avg timeliness: {rep_info.average_timeliness_score:.2f}")
    print(f"   Overall: {rep_info.overall_score:.2f}")


def test_self_rating_prevention():
    """自己評価防止テスト"""
    print("\n=== Self-Rating Prevention Test ===")
    
    reputation = get_reputation_contract()
    
    # 自己評価を試行
    self_rating = Rating(
        from_entity_id="same-entity",
        to_entity_id="same-entity",
        task_id="task-self",
        quality_score=5.0,
        communication_score=5.0,
        timeliness_score=5.0
    )
    
    success = reputation.submit_rating(self_rating)
    assert success is False, "Self-rating should be rejected"
    
    print(f"✅ Self-rating correctly rejected")


def test_invalid_rating_values():
    """無効な評価値テスト"""
    print("\n=== Invalid Rating Values Test ===")
    
    reputation = get_reputation_contract()
    
    # 範囲外のスコア
    invalid_ratings = [
        (-1.0, "Negative score"),
        (6.0, "Score above max"),
        (0.0, "Zero score"),
    ]
    
    for score, description in invalid_ratings:
        rating = Rating(
            from_entity_id="evaluator",
            to_entity_id="worker-invalid",
            task_id=f"task-invalid-{score}",
            quality_score=score,
            communication_score=3.0,
            timeliness_score=3.0
        )
        
        success = reputation.submit_rating(rating)
        assert success is False, f"{description} should be rejected"
    
    print(f"✅ Invalid ratings correctly rejected")


def test_rating_rewards():
    """評価報酬テスト"""
    print("\n=== Rating Rewards Test ===")
    
    # ウォレット作成
    evaluator_wallet = create_wallet("evaluator-reward", initial_balance=0.0)
    worker_wallet = create_wallet("worker-reward", initial_balance=0.0)
    
    # 評価送信（報酬付き）
    reputation = get_reputation_contract()
    
    # 高品質な評価
    high_rating = Rating(
        from_entity_id="evaluator-reward",
        to_entity_id="worker-reward",
        task_id="task-high",
        quality_score=5.0,
        communication_score=5.0,
        timeliness_score=5.0
    )
    
    # 評価報酬を計算（実装による）
    # ここでは評価システムが報酬を付与する仕組みがあるか確認
    success = reputation.submit_rating(high_rating)
    
    # 評価後の評判を確認
    rep_info = reputation.get_reputation("worker-reward")
    assert rep_info is not None
    assert rep_info.average_quality_score == 5.0
    
    print(f"✅ Rating with rewards processed")
    print(f"   Worker reputation: {rep_info.overall_score:.2f}")
    
    # クリーンアップ
    delete_wallet("evaluator-reward")
    delete_wallet("worker-reward")


def test_multiple_task_ratings():
    """複数タスク評価テスト"""
    print("\n=== Multiple Task Ratings Test ===")
    
    reputation = get_reputation_contract()
    
    # 同じワーカーに対する複数タスクの評価
    tasks = [
        ("task-1", 4.0, 4.5, 4.0),
        ("task-2", 5.0, 5.0, 5.0),
        ("task-3", 3.5, 3.0, 4.0),
        ("task-4", 4.5, 4.5, 4.5),
    ]
    
    for i, (task_id, q, c, t) in enumerate(tasks):
        rating = Rating(
            from_entity_id=f"client-{i}",
            to_entity_id="multi-task-worker",
            task_id=task_id,
            quality_score=q,
            communication_score=c,
            timeliness_score=t
        )
        reputation.submit_rating(rating)
    
    rep_info = reputation.get_reputation("multi-task-worker")
    
    assert rep_info.rating_count == 4
    
    # 各カテゴリの平均を計算
    expected_quality = sum([t[1] for t in tasks]) / 4
    assert abs(rep_info.average_quality_score - expected_quality) < 0.01
    
    print(f"✅ Multiple task ratings processed:")
    print(f"   Total tasks rated: {rep_info.rating_count}")
    print(f"   Overall reputation: {rep_info.overall_score:.2f}/5.0")


def main():
    """全テスト実行"""
    print("=" * 60)
    print("Rating System Test Suite")
    print("=" * 60)
    
    try:
        test_rating_submission()
        test_reputation_calculation()
        test_self_rating_prevention()
        test_invalid_rating_values()
        test_rating_rewards()
        test_multiple_task_ratings()
        
        print("\n" + "=" * 60)
        print("✅ All rating tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
