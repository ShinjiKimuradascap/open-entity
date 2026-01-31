#!/usr/bin/env python3
"""
Integration tests for AI Multi-Agent Marketplace

Tests the integration of ServiceRegistry, OrderBook, EscrowManager,
and ServiceMatchingEngine.
"""

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marketplace import (
    ServiceRegistry, ServiceListing, ServiceType, PricingModel,
    OrderBook, ServiceOrder, OrderStatus, OrderSide,
    EscrowManager, Escrow, EscrowStatus,
    ServiceMatchingEngine, MatchCriteria, MatchStrategy,
    create_matching_engine
)


class TestServiceRegistry(unittest.TestCase):
    """Test ServiceRegistry functionality"""
    
    def setUp(self):
        self.registry = ServiceRegistry()
    
    def test_register_service(self):
        """Test service registration"""
        async def run_test():
            listing = ServiceListing(
                service_id="svc_001",
                provider_id="provider_001",
                service_type=ServiceType.COMPUTE,
                description="Test compute service",
                pricing_model=PricingModel.PER_HOUR,
                price=Decimal("10.00"),
                capabilities=["gpu", "cuda"],
                endpoint="http://localhost:8000/compute",
                terms_hash="abc123"
            )
            
            result = await self.registry.register_service(listing)
            self.assertTrue(result)
            
            # Verify service was stored
            retrieved = await self.registry.get_service("svc_001")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.provider_id, "provider_001")
        
        asyncio.run(run_test())
    
    def test_search_services(self):
        """Test service search functionality"""
        async def run_test():
            # Register test services
            services = [
                ServiceListing(
                    service_id=f"svc_{i:03d}",
                    provider_id=f"provider_{i:03d}",
                    service_type=ServiceType.LLM if i % 2 == 0 else ServiceType.COMPUTE,
                    description=f"Test service {i}",
                    pricing_model=PricingModel.PER_REQUEST,
                    price=Decimal(str(5 + i)),
                    capabilities=["llm", "gpt"] if i % 2 == 0 else ["compute"],
                    endpoint=f"http://localhost:8000/{i}",
                    terms_hash=f"hash_{i}",
                    reputation_score=4.0 + (i % 2)
                )
                for i in range(5)
            ]
            
            for svc in services:
                await self.registry.register_service(svc)
            
            # Search by type
            llm_results = await self.registry.search_services(
                service_type=ServiceType.LLM
            )
            self.assertGreaterEqual(len(llm_results), 2)
            
            # Search by capabilities
            cap_results = await self.registry.search_services(
                capabilities=["llm"]
            )
            self.assertGreaterEqual(len(cap_results), 2)
            
            # Search with price limit
            price_results = await self.registry.search_services(
                max_price=Decimal("7.00")
            )
            self.assertLessEqual(len(price_results), 3)
        
        asyncio.run(run_test())
    
    def test_reputation_update(self):
        """Test reputation score updates"""
        async def run_test():
            listing = ServiceListing(
                service_id="svc_rep",
                provider_id="provider_rep",
                service_type=ServiceType.LLM,
                description="Test reputation",
                pricing_model=PricingModel.PER_REQUEST,
                price=Decimal("1.00"),
                capabilities=["test"],
                endpoint="http://localhost/test",
                terms_hash="hash",
                reputation_score=3.0
            )
            
            await self.registry.register_service(listing)
            
            # Update reputation
            await self.registry.update_reputation("svc_rep", 5.0, True)
            
            # Verify update
            updated = await self.registry.get_service("svc_rep")
            self.assertGreater(updated.reputation_score, 3.0)
            self.assertEqual(updated.successful_transactions, 1)
        
        asyncio.run(run_test())


class TestOrderBook(unittest.TestCase):
    """Test OrderBook functionality"""
    
    def setUp(self):
        self.order_book = OrderBook()
    
    def test_create_order(self):
        """Test order creation"""
        async def run_test():
            order = await self.order_book.create_order(
                buyer_id="buyer_001",
                service_id="svc_001",
                quantity=1,
                max_price=Decimal("10.00"),
                requirements={"prompt": "Hello world"}
            )
            
            self.assertIsNotNone(order)
            self.assertEqual(order.buyer_id, "buyer_001")
            self.assertEqual(order.status, OrderStatus.PENDING)
            self.assertEqual(order.total_amount, Decimal("10.00"))
        
        asyncio.run(run_test())
    
    def test_match_order(self):
        """Test order matching"""
        async def run_test():
            order = await self.order_book.create_order(
                buyer_id="buyer_001",
                service_id="svc_001",
                quantity=1,
                max_price=Decimal("10.00")
            )
            
            result = await self.order_book.match_order(
                order_id=order.order_id,
                provider_id="provider_001"
            )
            
            self.assertTrue(result.success)
            self.assertEqual(result.matched_provider_id, "provider_001")
            
            # Verify order status
            updated = await self.order_book.get_order(order.order_id)
            self.assertEqual(updated.status, OrderStatus.MATCHED)
        
        asyncio.run(run_test())
    
    def test_order_lifecycle(self):
        """Test complete order lifecycle"""
        async def run_test():
            order = await self.order_book.create_order(
                buyer_id="buyer_001",
                service_id="svc_001",
                quantity=1,
                max_price=Decimal("10.00")
            )
            
            # Match
            await self.order_book.match_order(order.order_id, "provider_001")
            
            # Start service
            result = await self.order_book.start_service(order.order_id)
            self.assertTrue(result)
            
            updated = await self.order_book.get_order(order.order_id)
            self.assertEqual(updated.status, OrderStatus.IN_PROGRESS)
            
            # Complete
            result = await self.order_book.complete_order(order.order_id)
            self.assertTrue(result)
            
            updated = await self.order_book.get_order(order.order_id)
            self.assertEqual(updated.status, OrderStatus.COMPLETED)
        
        asyncio.run(run_test())


class TestEscrowManager(unittest.TestCase):
    """Test EscrowManager functionality"""
    
    def setUp(self):
        self.escrow = EscrowManager()
    
    def test_create_escrow(self):
        """Test escrow creation"""
        async def run_test():
            result = await self.escrow.create_escrow(
                order_id="order_001",
                buyer_id="buyer_001",
                provider_id="provider_001",
                amount=Decimal("10.00")
            )
            
            self.assertIsNotNone(result)
            self.assertEqual(result.status, EscrowStatus.PENDING)
            self.assertEqual(result.amount, Decimal("10.00"))
        
        asyncio.run(run_test())
    
    def test_release_and_refund(self):
        """Test fund release and refund"""
        async def run_test():
            # Create escrow
            escrow = await self.escrow.create_escrow(
                order_id="order_002",
                buyer_id="buyer_001",
                provider_id="provider_001",
                amount=Decimal("10.00")
            )
            
            # Release to provider
            result = await self.escrow.release_to_provider(escrow.escrow_id)
            self.assertTrue(result)
            
            updated = await self.escrow.get_escrow(escrow.escrow_id)
            self.assertEqual(updated.status, EscrowStatus.RELEASED)
            
            # Create another for refund test
            escrow2 = await self.escrow.create_escrow(
                order_id="order_003",
                buyer_id="buyer_001",
                provider_id="provider_001",
                amount=Decimal("5.00")
            )
            
            # Refund
            result = await self.escrow.refund_to_buyer(escrow2.escrow_id)
            self.assertTrue(result)
            
            updated2 = await self.escrow.get_escrow(escrow2.escrow_id)
            self.assertEqual(updated2.status, EscrowStatus.REFUNDED)
        
        asyncio.run(run_test())


class TestServiceMatchingEngine(unittest.TestCase):
    """Test ServiceMatchingEngine functionality"""
    
    def setUp(self):
        async def setup():
            self.registry = ServiceRegistry()
            self.order_book = OrderBook()
            self.engine = ServiceMatchingEngine(self.registry, self.order_book)
            
            # Register test services
            services = [
                ServiceListing(
                    service_id="llm_cheap",
                    provider_id="provider_cheap",
                    service_type=ServiceType.LLM,
                    description="Cheap LLM",
                    pricing_model=PricingModel.PER_REQUEST,
                    price=Decimal("0.01"),
                    capabilities=["llm", "text"],
                    endpoint="http://cheap",
                    terms_hash="hash",
                    reputation_score=3.0
                ),
                ServiceListing(
                    service_id="llm_quality",
                    provider_id="provider_quality",
                    service_type=ServiceType.LLM,
                    description="Quality LLM",
                    pricing_model=PricingModel.PER_REQUEST,
                    price=Decimal("0.10"),
                    capabilities=["llm", "text", "code"],
                    endpoint="http://quality",
                    terms_hash="hash",
                    reputation_score=5.0
                ),
                ServiceListing(
                    service_id="llm_fast",
                    provider_id="provider_fast",
                    service_type=ServiceType.LLM,
                    description="Fast LLM",
                    pricing_model=PricingModel.PER_REQUEST,
                    price=Decimal("0.05"),
                    capabilities=["llm", "text"],
                    endpoint="http://fast",
                    terms_hash="hash",
                    reputation_score=4.0
                ),
            ]
            
            for svc in services:
                await self.registry.register_service(svc)
        
        asyncio.run(setup())
    
    def test_find_matches(self):
        """Test service matching"""
        async def run_test():
            criteria = MatchCriteria(
                required_capabilities=["llm"],
                strategy=MatchStrategy.BALANCED
            )
            
            result = await self.engine.find_matches(criteria, limit=5)
            
            self.assertTrue(result.success)
            self.assertGreaterEqual(len(result.matches), 3)
            self.assertIsNotNone(result.top_match)
        
        asyncio.run(run_test())
    
    def test_match_strategies(self):
        """Test different matching strategies"""
        async def run_test():
            strategies = [
                MatchStrategy.PRICE_OPTIMIZED,
                MatchStrategy.QUALITY_OPTIMIZED,
                MatchStrategy.BALANCED,
                MatchStrategy.FASTEST
            ]
            
            for strategy in strategies:
                criteria = MatchCriteria(
                    required_capabilities=["llm"],
                    strategy=strategy
                )
                
                result = await self.engine.find_matches(criteria, limit=3)
                self.assertTrue(result.success, f"Strategy {strategy.value} failed")
                self.assertGreater(len(result.matches), 0)
        
        asyncio.run(run_test())
    
    def test_price_filter(self):
        """Test price filtering"""
        async def run_test():
            criteria = MatchCriteria(
                required_capabilities=["llm"],
                max_price=Decimal("0.02"),
                strategy=MatchStrategy.PRICE_OPTIMIZED
            )
            
            result = await self.engine.find_matches(criteria)
            
            self.assertTrue(result.success)
            # Should only get the cheap service
            self.assertEqual(result.matches[0].service_id, "llm_cheap")
        
        asyncio.run(run_test())
    
    def test_capability_matching(self):
        """Test capability-based matching"""
        async def run_test():
            # Search for code capability (only quality has it)
            criteria = MatchCriteria(
                required_capabilities=["code"],
                strategy=MatchStrategy.BALANCED
            )
            
            result = await self.engine.find_matches(criteria)
            
            self.assertTrue(result.success)
            self.assertEqual(len(result.matches), 1)
            self.assertEqual(result.matches[0].service_id, "llm_quality")
        
        asyncio.run(run_test())
    
    def test_check_availability(self):
        """Test availability checking"""
        async def run_test():
            available, wait_time = await self.engine.check_availability("llm_cheap")
            
            self.assertTrue(available)
            self.assertEqual(wait_time, 0)  # No queue initially
        
        asyncio.run(run_test())


class TestMarketplaceIntegration(unittest.TestCase):
    """Full integration test of marketplace components"""
    
    def test_full_transaction_flow(self):
        """Test complete marketplace transaction"""
        async def run_test():
            # Setup components
            registry = ServiceRegistry()
            order_book = OrderBook()
            escrow = EscrowManager()
            engine = ServiceMatchingEngine(registry, order_book)
            
            # 1. Provider registers service
            service = ServiceListing(
                service_id="ai_code_review",
                provider_id="coder_agent_001",
                service_type=ServiceType.ANALYSIS,
                description="AI-powered code review",
                pricing_model=PricingModel.PER_REQUEST,
                price=Decimal("5.00"),
                capabilities=["code_review", "python", "security"],
                endpoint="http://coder-agent:8000/review",
                terms_hash="terms_v1"
            )
            await registry.register_service(service)
            
            # 2. Buyer creates order
            order = await order_book.create_order(
                buyer_id="client_001",
                service_id="ai_code_review",
                quantity=1,
                max_price=Decimal("5.00"),
                requirements={
                    "language": "python",
                    "files": ["src/main.py"]
                }
            )
            
            # 3. Match order
            match_result = await order_book.match_order(
                order_id=order.order_id,
                provider_id="coder_agent_001"
            )
            self.assertTrue(match_result.success)
            
            # 4. Create escrow
            escrow_obj = await escrow.create_escrow(
                order_id=order.order_id,
                buyer_id="client_001",
                provider_id="coder_agent_001",
                amount=Decimal("5.00")
            )
            
            # 5. Service execution
            await order_book.start_service(order.order_id)
            
            # 6. Complete and release funds
            await order_book.complete_order(order.order_id)
            await escrow.release_to_provider(escrow_obj.escrow_id)
            
            # 7. Update reputation
            await registry.update_reputation(
                "ai_code_review",
                rating=5.0,
                transaction_success=True
            )
            
            # Verify final state
            final_order = await order_book.get_order(order.order_id)
            final_escrow = await escrow.get_escrow(escrow_obj.escrow_id)
            final_service = await registry.get_service("ai_code_review")
            
            self.assertEqual(final_order.status, OrderStatus.COMPLETED)
            self.assertEqual(final_escrow.status, EscrowStatus.RELEASED)
            self.assertEqual(final_service.successful_transactions, 1)
            self.assertGreater(final_service.reputation_score, 0)
            
            print("✅ Full transaction flow completed successfully!")
        
        asyncio.run(run_test())


class TestPersistence(unittest.TestCase):
    """Test data persistence"""
    
    def test_registry_persistence(self):
        """Test registry save/load"""
        async def run_test():
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = tmp.name
            
            try:
                # Create and populate registry
                registry1 = ServiceRegistry(storage_path=tmp_path)
                service = ServiceListing(
                    service_id="persist_svc",
                    provider_id="provider_001",
                    service_type=ServiceType.LLM,
                    description="Persistent service",
                    pricing_model=PricingModel.PER_REQUEST,
                    price=Decimal("1.00"),
                    capabilities=["test"],
                    endpoint="http://test",
                    terms_hash="hash"
                )
                await registry1.register_service(service)
                
                # Create new registry instance with same path
                registry2 = ServiceRegistry(storage_path=tmp_path)
                
                # Verify data persisted
                retrieved = await registry2.get_service("persist_svc")
                self.assertIsNotNone(retrieved)
                self.assertEqual(retrieved.provider_id, "provider_001")
                
            finally:
                os.unlink(tmp_path)
        
        asyncio.run(run_test())


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestServiceRegistry))
    suite.addTests(loader.loadTestsFromTestCase(TestOrderBook))
    suite.addTests(loader.loadTestsFromTestCase(TestEscrowManager))
    suite.addTests(loader.loadTestsFromTestCase(TestServiceMatchingEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestMarketplaceIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestPersistence))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
