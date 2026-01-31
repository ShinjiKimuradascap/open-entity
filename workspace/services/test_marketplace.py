#!/usr/bin/env python3
"""
Tests for AI Multi-Agent Marketplace
"""

import unittest
import tempfile
import shutil
from decimal import Decimal
from pathlib import Path
from datetime import datetime

from marketplace.order_book import OrderBook, ServiceOrder, OrderStatus
from marketplace.escrow import EscrowManager, EscrowStatus
from marketplace.service_registry import ServiceRegistry, ServiceListing, ServiceType, PricingModel


class TestOrderBook(unittest.TestCase):
    """Test OrderBook functionality"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.order_book = OrderBook(data_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_create_order(self):
        """Test creating an order"""
        order = self.order_book.create_order(
            client_id="client_1",
            provider_id="provider_1",
            service_id="service_1",
            price=Decimal("100.00")
        )
        
        self.assertIsNotNone(order.order_id)
        self.assertEqual(order.client_id, "client_1")
        self.assertEqual(order.provider_id, "provider_1")
        self.assertEqual(order.price, Decimal("100.00"))
        self.assertEqual(order.status, OrderStatus.PENDING)

    def test_get_order(self):
        """Test retrieving an order"""
        created = self.order_book.create_order(
            client_id="client_1",
            provider_id="provider_1",
            service_id="service_1",
            price=Decimal("50.00")
        )
        
        retrieved = self.order_book.get_order(created.order_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.order_id, created.order_id)

    def test_list_orders_with_filter(self):
        """Test listing orders with filters"""
        # Create orders
        self.order_book.create_order("client_1", "provider_1", "svc1", Decimal("10.00"))
        self.order_book.create_order("client_1", "provider_2", "svc2", Decimal("20.00"))
        self.order_book.create_order("client_2", "provider_1", "svc3", Decimal("30.00"))
        
        # Filter by client
        client_orders = self.order_book.list_orders(client_id="client_1")
        self.assertEqual(len(client_orders), 2)
        
        # Filter by provider
        provider_orders = self.order_book.list_orders(provider_id="provider_1")
        self.assertEqual(len(provider_orders), 2)

    def test_update_status(self):
        """Test updating order status"""
        order = self.order_book.create_order(
            client_id="client_1",
            provider_id="provider_1",
            service_id="service_1",
            price=Decimal("100.00")
        )
        
        result = self.order_book.update_status(order.order_id, OrderStatus.IN_PROGRESS)
        self.assertTrue(result)
        
        updated = self.order_book.get_order(order.order_id)
        self.assertEqual(updated.status, OrderStatus.IN_PROGRESS)

    def test_complete_order(self):
        """Test completing an order"""
        order = self.order_book.create_order(
            client_id="client_1",
            provider_id="provider_1",
            service_id="service_1",
            price=Decimal("100.00")
        )
        
        self.order_book.accept_order(order.order_id)
        self.order_book.start_order(order.order_id)
        self.order_book.complete_order(order.order_id)
        
        completed = self.order_book.get_order(order.order_id)
        self.assertEqual(completed.status, OrderStatus.COMPLETED)
        self.assertIsNotNone(completed.completed_at)

    def test_cancel_order(self):
        """Test cancelling an order"""
        order = self.order_book.create_order(
            client_id="client_1",
            provider_id="provider_1",
            service_id="service_1",
            price=Decimal("100.00")
        )
        
        result = self.order_book.cancel_order(order.order_id)
        self.assertTrue(result)
        
        cancelled = self.order_book.get_order(order.order_id)
        self.assertEqual(cancelled.status, OrderStatus.CANCELLED)


class TestEscrowManager(unittest.TestCase):
    """Test EscrowManager functionality"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.escrow = EscrowManager(data_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_create_escrow(self):
        """Test creating an escrow"""
        escrow_id = self.escrow.create_escrow(
            order_id="order_1",
            amount=Decimal("100.00"),
            client_id="client_1",
            provider_id="provider_1"
        )
        
        self.assertIsNotNone(escrow_id)
        
        escrow = self.escrow.get_escrow(escrow_id)
        self.assertIsNotNone(escrow)
        self.assertEqual(escrow["order_id"], "order_1")
        self.assertEqual(escrow["amount"], "100.00")
        self.assertEqual(escrow["status"], "pending")

    def test_release_escrow(self):
        """Test releasing escrow to provider"""
        escrow_id = self.escrow.create_escrow(
            order_id="order_1",
            amount=Decimal("100.00"),
            client_id="client_1",
            provider_id="provider_1"
        )
        
        result = self.escrow.release_escrow(escrow_id)
        self.assertTrue(result)
        
        escrow = self.escrow.get_escrow(escrow_id)
        self.assertEqual(escrow["status"], "released")

    def test_refund_escrow(self):
        """Test refunding escrow to client"""
        escrow_id = self.escrow.create_escrow(
            order_id="order_1",
            amount=Decimal("100.00"),
            client_id="client_1",
            provider_id="provider_1"
        )
        
        result = self.escrow.refund_escrow(escrow_id)
        self.assertTrue(result)
        
        escrow = self.escrow.get_escrow(escrow_id)
        self.assertEqual(escrow["status"], "refunded")


class TestServiceRegistry(unittest.TestCase):
    """Test ServiceRegistry functionality"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.registry = ServiceRegistry(data_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_register_service(self):
        """Test registering a service"""
        service = self.registry.register_service(
            provider_id="provider_1",
            service_type=ServiceType.LLM,
            description="Test LLM service",
            pricing_model=PricingModel.PER_REQUEST,
            price=Decimal("0.01"),
            capabilities=["text_generation", "summarization"],
            endpoint="https://api.example.com/llm"
        )
        
        self.assertIsNotNone(service.service_id)
        self.assertEqual(service.provider_id, "provider_1")
        self.assertEqual(service.service_type, ServiceType.LLM)

    def test_search_services(self):
        """Test searching services"""
        self.registry.register_service(
            provider_id="provider_1",
            service_type=ServiceType.LLM,
            description="GPT-style LLM",
            pricing_model=PricingModel.PER_REQUEST,
            price=Decimal("0.01"),
            capabilities=["chat"],
            endpoint="https://api1.example.com"
        )
        
        self.registry.register_service(
            provider_id="provider_2",
            service_type=ServiceType.VISION,
            description="Image analysis",
            pricing_model=PricingModel.PER_REQUEST,
            price=Decimal("0.05"),
            capabilities=["object_detection"],
            endpoint="https://api2.example.com"
        )
        
        # Search by type
        llm_services = self.registry.search_services(service_type=ServiceType.LLM)
        self.assertEqual(len(llm_services), 1)
        
        # Search all
        all_services = self.registry.search_services()
        self.assertEqual(len(all_services), 2)


if __name__ == "__main__":
    unittest.main()
