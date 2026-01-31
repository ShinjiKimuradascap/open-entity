#!/usr/bin/env python3
"""
Autonomous Revenue System Tests
自律的収益生成システムのテスト
"""

import sys
import shutil
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from autonomous_revenue_system import (
    ServiceOffering, RevenueRecord, AutonomousRevenueSystem,
    get_revenue_system
)


def test_service_offering():
    """Test 1: ServiceOfferingデータクラスのシリアライゼーション"""
    print("Test 1: ServiceOffering dataclass serialization")
    
    service = ServiceOffering(
        service_id="test_service",
        name="Test Service",
        description="A test service offering",
        base_price=25.0,
        estimated_time_minutes=30,
        required_capabilities=["test", "demo"]
    )
    
    # to_dict test
    data = service.to_dict()
    assert data["service_id"] == "test_service"
    assert data["name"] == "Test Service"
    assert data["description"] == "A test service offering"
    assert data["base_price"] == 25.0
    assert data["estimated_time_minutes"] == 30
    assert data["required_capabilities"] == ["test", "demo"]
    
    print("  ✓ ServiceOffering serialization passed")


def test_revenue_system_init():
    """Test 2: AutonomousRevenueSystemの初期化"""
    print("\nTest 2: Revenue system initialization")
    
    # Create temporary directory for test data
    temp_dir = tempfile.mkdtemp()
    
    try:
        system = AutonomousRevenueSystem(
            agent_id="test-agent-001",
            data_dir=temp_dir
        )
        
        assert system.agent_id == "test-agent-001"
        assert system.data_dir == Path(temp_dir)
        assert system.data_dir.exists()
        assert hasattr(system, 'economy')
        assert hasattr(system, 'tx_manager')
        assert isinstance(system.revenue_history, list)
        assert isinstance(system.active_agreements, dict)
        assert isinstance(system._service_handlers, dict)
        
        print(f"  ✓ System initialized with agent_id: {system.agent_id}")
        print(f"  ✓ Data directory created: {system.data_dir}")
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_get_available_services():
    """Test 3: デフォルトサービス一覧取得"""
    print("\nTest 3: Get available services")
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        system = AutonomousRevenueSystem(
            agent_id="test-agent-002",
            data_dir=temp_dir
        )
        
        services = system.get_available_services()
        
        assert isinstance(services, list)
        assert len(services) == 5  # 5 default services
        
        # Check expected services exist
        service_ids = [s.service_id for s in services]
        expected = ["code_gen", "code_review", "doc_creation", "research", "bug_fix"]
        for sid in expected:
            assert sid in service_ids, f"Missing service: {sid}"
        
        # Check service properties
        code_gen = next(s for s in services if s.service_id == "code_gen")
        assert code_gen.name == "Code Generation"
        assert code_gen.base_price == 10.0
        assert code_gen.estimated_time_minutes == 30
        
        print(f"  ✓ Found {len(services)} default services")
        print(f"  ✓ Services: {', '.join(service_ids)}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_register_service_handler():
    """Test 4: サービスハンドラ登録"""
    print("\nTest 4: Register service handler")
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        system = AutonomousRevenueSystem(
            agent_id="test-agent-003",
            data_dir=temp_dir
        )
        
        # Define a mock handler
        def mock_handler(agreement):
            return True
        
        # Register handler
        system.register_service_handler("code_gen", mock_handler)
        
        # Verify registration
        assert "code_gen" in system._service_handlers
        assert system._service_handlers["code_gen"] == mock_handler
        
        # Register another handler
        def another_handler(agreement):
            return False
        
        system.register_service_handler("bug_fix", another_handler)
        assert len(system._service_handlers) == 2
        
        print("  ✓ Handler registered for 'code_gen'")
        print("  ✓ Handler registered for 'bug_fix'")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_handle_incoming_proposal():
    """Test 5: 提案処理と見積もり作成"""
    print("\nTest 5: Handle incoming proposal")
    
    # Create mock TaskProposal
    class MockTaskProposal:
        def __init__(self, task_type, budget_max):
            self.proposal_id = "prop-001"
            self.task_type = task_type
            self.budget_max = budget_max
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        system = AutonomousRevenueSystem(
            agent_id="test-agent-004",
            data_dir=temp_dir
        )
        
        # Test 1: Valid proposal with matching service and sufficient budget
        proposal1 = MockTaskProposal(task_type="code_gen", budget_max=15.0)
        quote1 = system.handle_incoming_proposal(proposal1)
        
        assert quote1 is not None
        assert quote1.proposal_id == "prop-001"
        assert quote1.provider_id == "test-agent-004"
        assert quote1.estimated_amount == 10.0  # code_gen base price
        assert quote1.estimated_time_seconds == 1800  # 30 minutes in seconds
        print("  ✓ Valid proposal accepted, quote created")
        
        # Test 2: Proposal with insufficient budget
        proposal2 = MockTaskProposal(task_type="code_gen", budget_max=5.0)
        quote2 = system.handle_incoming_proposal(proposal2)
        
        assert quote2 is None
        print("  ✓ Low budget proposal rejected")
        
        # Test 3: Proposal with unknown service type
        proposal3 = MockTaskProposal(task_type="unknown_service", budget_max=100.0)
        quote3 = system.handle_incoming_proposal(proposal3)
        
        assert quote3 is None
        print("  ✓ Unknown service type rejected")
        
        # Test 4: Valid proposal for different service
        proposal4 = MockTaskProposal(task_type="research", budget_max=25.0)
        quote4 = system.handle_incoming_proposal(proposal4)
        
        assert quote4 is not None
        assert quote4.estimated_amount == 20.0  # research base price
        print("  ✓ Different service type handled correctly")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_revenue_summary():
    """Test 6: 収益サマリー計算"""
    print("\nTest 6: Revenue summary calculation")
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        system = AutonomousRevenueSystem(
            agent_id="test-agent-005",
            data_dir=temp_dir
        )
        
        # Add mock revenue records
        from datetime import datetime, timezone, timedelta
        
        # Recent records (within 30 days)
        now = datetime.now(timezone.utc)
        system.revenue_history = [
            RevenueRecord(
                date=now.isoformat(),
                service_id="code_gen",
                amount=10.0,
                client_id="client-1",
                status="completed"
            ),
            RevenueRecord(
                date=(now - timedelta(days=5)).isoformat(),
                service_id="code_review",
                amount=5.0,
                client_id="client-2",
                status="completed"
            ),
            RevenueRecord(
                date=(now - timedelta(days=10)).isoformat(),
                service_id="code_gen",
                amount=10.0,
                client_id="client-3",
                status="completed"
            ),
            # Old record (outside 30 days)
            RevenueRecord(
                date=(now - timedelta(days=60)).isoformat(),
                service_id="research",
                amount=20.0,
                client_id="client-4",
                status="completed"
            )
        ]
        
        # Get summary for last 30 days
        summary = system.get_revenue_summary(days=30)
        
        assert summary["period_days"] == 30
        assert summary["total_revenue"] == 25.0  # 10 + 5 + 10
        assert summary["transaction_count"] == 3
        assert summary["average_per_transaction"] == 25.0 / 3
        
        # Check by_service breakdown
        assert "by_service" in summary
        assert summary["by_service"]["code_gen"] == 20.0  # Two code_gen records
        assert summary["by_service"]["code_review"] == 5.0
        assert "research" not in summary["by_service"]  # Too old
        
        print(f"  ✓ Total revenue (30 days): {summary['total_revenue']} AIC")
        print(f"  ✓ Transaction count: {summary['transaction_count']}")
        print(f"  ✓ Average per transaction: {summary['average_per_transaction']:.2f} AIC")
        
        # Test with longer period to include old record
        summary_all = system.get_revenue_summary(days=90)
        assert summary_all["total_revenue"] == 45.0  # All 4 records
        assert summary_all["transaction_count"] == 4
        assert summary_all["by_service"]["research"] == 20.0
        
        print(f"  ✓ Total revenue (90 days): {summary_all['total_revenue']} AIC")
        
        # Test empty history
        system.revenue_history = []
        summary_empty = system.get_revenue_summary(days=30)
        assert summary_empty["total_revenue"] == 0.0
        assert summary_empty["transaction_count"] == 0
        assert summary_empty["average_per_transaction"] == 0.0
        
        print("  ✓ Empty history handled correctly")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_all_tests():
    """全テスト実行"""
    print("=== Autonomous Revenue System Tests ===\n")
    
    try:
        test_service_offering()
        test_revenue_system_init()
        test_get_available_services()
        test_register_service_handler()
        test_handle_incoming_proposal()
        test_revenue_summary()
        
        print("\n" + "=" * 40)
        print("All 6 tests passed! ✓")
        print("=" * 40)
        return True
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
