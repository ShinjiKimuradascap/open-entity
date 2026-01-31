"""
Unit tests for DHT Foundation package
"""

import unittest
from services.dht import NodeID, NodeInfo, KBucket, RoutingTable, DHTRouter


class TestNodeID(unittest.TestCase):
    def test_creation(self):
        n = NodeID()
        self.assertEqual(len(n.bytes), 20)
        self.assertEqual(len(n.hex), 40)
    
    def test_from_entity(self):
        n = NodeID.from_entity("test_entity")
        self.assertIsInstance(n, NodeID)
        self.assertEqual(n, NodeID.from_entity("test_entity"))
    
    def test_distance(self):
        n1 = NodeID.from_entity("a")
        n2 = NodeID.from_entity("b")
        dist = n1.distance_to(n2)
        self.assertIsInstance(dist, int)
        self.assertGreaterEqual(dist, 0)


class TestNodeInfo(unittest.TestCase):
    def test_creation(self):
        node = NodeInfo(
            node_id=NodeID.from_entity("test"),
            host="127.0.0.1",
            port=8080,
        )
        self.assertEqual(node.endpoint, "http://127.0.0.1:8080")
    
    def test_serialization(self):
        node = NodeInfo(
            node_id=NodeID.from_entity("test"),
            host="127.0.0.1",
            port=8080,
            capabilities=["v1.2", "dht"],
        )
        data = node.to_dict()
        restored = NodeInfo.from_dict(data)
        self.assertEqual(node.node_id, restored.node_id)
        self.assertEqual(node.capabilities, restored.capabilities)


class TestKBucket(unittest.TestCase):
    def test_add_node(self):
        bucket = KBucket(0, 159, k=3)
        node = NodeInfo(NodeID.from_entity("n1"), "127.0.0.1", 8001)
        self.assertTrue(bucket.add_node(node))
        self.assertIn(node.node_id, bucket)
    
    def test_bucket_full(self):
        bucket = KBucket(0, 159, k=2)
        bucket.add_node(NodeInfo(NodeID.from_entity("n1"), "127.0.0.1", 8001))
        bucket.add_node(NodeInfo(NodeID.from_entity("n2"), "127.0.0.1", 8002))
        # Third should fail (bucket full)
        result = bucket.add_node(NodeInfo(NodeID.from_entity("n3"), "127.0.0.1", 8003))
        self.assertFalse(result)
    
    def test_split(self):
        bucket = KBucket(0, 159, k=2)
        bucket.add_node(NodeInfo(NodeID.from_entity("n1"), "127.0.0.1", 8001))
        left, right = bucket.split()
        self.assertLess(left.max_distance, right.min_distance)


class TestRoutingTable(unittest.TestCase):
    def test_add_node(self):
        own_id = NodeID.from_entity("self")
        table = RoutingTable(own_id, k=3)
        node = NodeInfo(NodeID.from_entity("peer"), "127.0.0.1", 8001)
        self.assertTrue(table.add_node(node))
        self.assertEqual(len(table.get_all_nodes()), 1)
    
    def test_find_closest(self):
        own_id = NodeID.from_entity("self")
        table = RoutingTable(own_id, k=3)
        
        # Add nodes
        for i in range(5):
            node = NodeInfo(NodeID.from_entity(f"peer{i}"), "127.0.0.1", 8000 + i)
            table.add_node(node)
        
        # Find closest to target
        target = NodeID.from_entity("target")
        closest = table.find_closest(target, count=3)
        self.assertLessEqual(len(closest), 3)


class TestDHTRouter(unittest.TestCase):
    def test_creation(self):
        router = DHTRouter()
        self.assertIsNotNone(router.node_id)
        self.assertIsNotNone(router.routing_table)
    
    def test_store_and_find(self):
        import asyncio
        
        async def test():
            router = DHTRouter()
            key = b"test_key"
            value = b"test_value"
            
            result = await router.store(key, value)
            self.assertTrue(result)
            
            found = await router.find_value(key)
            self.assertEqual(found, value)
        
        asyncio.run(test())


if __name__ == "__main__":
    unittest.main()
