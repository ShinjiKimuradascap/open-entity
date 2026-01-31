#!/usr/bin/env python3
"""
DHT Node Tests
Kademlia DHT実装のテスト
"""

import asyncio
import hashlib
import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from dht_node import (
    NodeID, NodeInfo, ValueEntry, KBucket, RoutingTable,
    DHTNode, DHTClient, K, KEY_SIZE
)


class TestNodeID(unittest.TestCase):
    """NodeIDのテスト"""
    
    def test_random_generation(self):
        """ランダム生成テスト"""
        node_id = NodeID()
        self.assertEqual(len(node_id.bytes), KEY_SIZE // 8)
        self.assertIsInstance(node_id.int, int)
    
    def test_from_string(self):
        """文字列からの生成テスト"""
        node_id = NodeID("test-string")
        expected_hash = hashlib.sha1(b"test-string").digest()
        self.assertEqual(node_id.bytes, expected_hash)
    
    def test_from_int(self):
        """整数からの生成テスト"""
        test_int = 12345
        node_id = NodeID(test_int)
        self.assertEqual(node_id.int, test_int)
    
    def test_distance_calculation(self):
        """XOR距離計算テスト"""
        id1 = NodeID(b'\x00' * 20)
        id2 = NodeID(b'\xff' * 20)
        
        distance = id1.distance_to(id2)
        expected = int.from_bytes(b'\xff' * 20, 'big')
        self.assertEqual(distance, expected)
    
    def test_distance_to_self(self):
        """自分自身との距離は0"""
        node_id = NodeID(b'\xab' * 20)
        self.assertEqual(node_id.distance_to(node_id), 0)
    
    def test_hex_conversion(self):
        """16進数変換テスト"""
        node_id = NodeID(b'\xab\xcd' + b'\x00' * 18)
        hex_str = node_id.hex
        self.assertEqual(len(hex_str), 40)  # 160 bits = 40 hex chars
        
        # 復元
        restored = NodeID.from_hex(hex_str)
        self.assertEqual(node_id.bytes, restored.bytes)
    
    def test_bit_length(self):
        """ビット長計算テスト"""
        id1 = NodeID(b'\x00' * 20)  # 0
        self.assertEqual(id1.bit_length(), 0)
        
        id2 = NodeID(b'\x80' + b'\x00' * 19)  # MSB set
        self.assertEqual(id2.bit_length(), 159)
    
    def test_comparison(self):
        """比較テスト"""
        id1 = NodeID(100)
        id2 = NodeID(200)
        
        self.assertTrue(id1 < id2)
        self.assertFalse(id2 < id1)
    
    def test_equality(self):
        """等価性テスト"""
        id1 = NodeID("same-string")
        id2 = NodeID("same-string")
        id3 = NodeID("different-string")
        
        self.assertEqual(id1, id2)
        self.assertNotEqual(id1, id3)
        self.assertEqual(hash(id1), hash(id2))


class TestNodeInfo(unittest.TestCase):
    """NodeInfoのテスト"""
    
    def test_creation(self):
        """生成テスト"""
        node_id = NodeID("test-node")
        info = NodeInfo(node_id, "127.0.0.1", 8000)
        
        self.assertEqual(info.node_id, node_id)
        self.assertEqual(info.host, "127.0.0.1")
        self.assertEqual(info.port, 8000)
        self.assertIsNotNone(info.last_seen)
    
    def test_endpoint(self):
        """エンドポイントテスト"""
        node_id = NodeID("test")
        info = NodeInfo(node_id, "192.168.1.1", 9000)
        
        self.assertEqual(info.endpoint, "http://192.168.1.1:9000")
    
    def test_distance_to(self):
        """距離計算テスト"""
        id1 = NodeID("node1")
        id2 = NodeID("node2")
        
        info = NodeInfo(id1, "127.0.0.1", 8000)
        distance = info.distance_to(id2)
        
        self.assertEqual(distance, id1.distance_to(id2))
    
    def test_dict_conversion(self):
        """辞書変換テスト"""
        node_id = NodeID("test")
        info = NodeInfo(node_id, "127.0.0.1", 8000)
        
        data = info.to_dict()
        self.assertEqual(data["host"], "127.0.0.1")
        self.assertEqual(data["port"], 8000)
        self.assertEqual(data["node_id"], node_id.hex)
        
        # 復元
        restored = NodeInfo.from_dict(data)
        self.assertEqual(restored.host, info.host)
        self.assertEqual(restored.port, info.port)
        self.assertEqual(restored.node_id, info.node_id)


class TestValueEntry(unittest.TestCase):
    """ValueEntryのテスト"""
    
    def test_creation(self):
        """生成テスト"""
        key = b"test-key"
        value = b"test-value"
        
        entry = ValueEntry(key=key, value=value)
        
        self.assertEqual(entry.key, key)
        self.assertEqual(entry.value, value)
        self.assertIsNotNone(entry.timestamp)
        self.assertIsNotNone(entry.expiration)
    
    def test_expiration(self):
        """期限切れテスト"""
        from datetime import datetime, timedelta
        
        entry = ValueEntry(key=b"k", value=b"v")
        self.assertFalse(entry.is_expired())
        
        # 期限切れに設定
        entry.expiration = datetime.utcnow() - timedelta(hours=1)
        self.assertTrue(entry.is_expired())
    
    def test_dict_conversion(self):
        """辞書変換テスト"""
        key = b"test-key"
        value = b"test-value"
        publisher = NodeID("publisher")
        
        entry = ValueEntry(key=key, value=value, publisher_id=publisher)
        data = entry.to_dict()
        
        self.assertEqual(data["key"], key.hex())
        self.assertEqual(data["value"], value.hex())
        self.assertEqual(data["publisher_id"], publisher.hex)
        
        # 復元
        restored = ValueEntry.from_dict(data)
        self.assertEqual(restored.key, entry.key)
        self.assertEqual(restored.value, entry.value)
        self.assertEqual(restored.publisher_id, entry.publisher_id)


class TestKBucket(unittest.TestCase):
    """KBucketのテスト"""
    
    def test_creation(self):
        """生成テスト"""
        bucket = KBucket(0, 159, k=20)
        self.assertEqual(bucket.min_distance, 0)
        self.assertEqual(bucket.max_distance, 159)
        self.assertEqual(bucket.k, 20)
        self.assertEqual(len(bucket.nodes), 0)
    
    def test_add_node(self):
        """ノード追加テスト"""
        bucket = KBucket(0, 159)
        
        node = NodeInfo(NodeID("node1"), "127.0.0.1", 8000)
        
        self.assertTrue(bucket.add_node(node))
        self.assertEqual(len(bucket.nodes), 1)
        self.assertIn(node.node_id, bucket)
    
    def test_add_duplicate(self):
        """重複追加テスト"""
        bucket = KBucket(0, 159)
        
        node = NodeInfo(NodeID("node1"), "127.0.0.1", 8000)
        
        bucket.add_node(node)
        bucket.add_node(node)  # 2回目
        
        self.assertEqual(len(bucket.nodes), 1)  # 重複は1つ
        self.assertEqual(bucket.nodes[0].host, "127.0.0.1")  # 先頭に移動
    
    def test_bucket_full(self):
        """バケット満杯テスト"""
        bucket = KBucket(0, 159, k=2)
        
        node1 = NodeInfo(NodeID("node1"), "127.0.0.1", 8001)
        node2 = NodeInfo(NodeID("node2"), "127.0.0.1", 8002)
        node3 = NodeInfo(NodeID("node3"), "127.0.0.1", 8003)
        
        self.assertTrue(bucket.add_node(node1))
        self.assertTrue(bucket.add_node(node2))
        self.assertFalse(bucket.add_node(node3))  # 満杯
    
    def test_remove_node(self):
        """ノード削除テスト"""
        bucket = KBucket(0, 159)
        
        node_id = NodeID("node1")
        node = NodeInfo(node_id, "127.0.0.1", 8000)
        
        bucket.add_node(node)
        self.assertTrue(bucket.remove_node(node_id))
        self.assertEqual(len(bucket.nodes), 0)
    
    def test_get_least_recently_seen(self):
        """最も古いノード取得テスト"""
        bucket = KBucket(0, 159)
        
        node1 = NodeInfo(NodeID("node1"), "127.0.0.1", 8001)
        node2 = NodeInfo(NodeID("node2"), "127.0.0.1", 8002)
        
        bucket.add_node(node1)
        bucket.add_node(node2)
        
        # 再追加で順序変更
        bucket.add_node(node1)
        
        oldest = bucket.get_least_recently_seen()
        self.assertEqual(oldest.node_id, node2.node_id)
    
    def test_split(self):
        """バケット分割テスト"""
        bucket = KBucket(0, 159, k=2)
        
        # 距離が異なるノードを追加
        id1 = NodeID(b'\x00' + b'\xff' * 19)  # 小さい距離
        id2 = NodeID(b'\xff' + b'\x00' * 19)  # 大きい距離
        
        node1 = NodeInfo(id1, "127.0.0.1", 8001)
        node2 = NodeInfo(id2, "127.0.0.1", 8002)
        
        bucket.add_node(node1)
        bucket.add_node(node2)
        
        left, right = bucket.split()
        
        # 分割後の範囲を確認
        self.assertLess(left.max_distance, right.min_distance)
        # ノードが正しく分配されたか
        total_nodes = len(left.nodes) + len(right.nodes)
        self.assertEqual(total_nodes, 2)


class TestRoutingTable(unittest.TestCase):
    """RoutingTableのテスト"""
    
    def test_creation(self):
        """生成テスト"""
        node_id = NodeID("self")
        table = RoutingTable(node_id)
        
        self.assertEqual(table.node_id, node_id)
        self.assertEqual(len(table.buckets), 1)
    
    def test_add_node(self):
        """ノード追加テスト"""
        self_id = NodeID("self")
        table = RoutingTable(self_id)
        
        node = NodeInfo(NodeID("other"), "127.0.0.1", 8000)
        
        self.assertTrue(table.add_node(node))
        self.assertEqual(table.get_stats()["total_nodes"], 1)
    
    def test_add_self(self):
        """自分自身の追加テスト"""
        self_id = NodeID("self")
        table = RoutingTable(self_id)
        
        node = NodeInfo(self_id, "127.0.0.1", 8000)
        
        # 自分自身は追加されない（Trueを返すが無視される）
        self.assertTrue(table.add_node(node))
        self.assertEqual(table.get_stats()["total_nodes"], 0)
    
    def test_find_closest(self):
        """最近傍探索テスト"""
        self_id = NodeID(b'\x00' * 20)
        table = RoutingTable(self_id)
        
        # 異なる距離のノードを追加
        for i in range(10):
            node_id = NodeID(bytes([i] * 20))
            node = NodeInfo(node_id, f"127.0.0.{i}", 8000 + i)
            table.add_node(node)
        
        # ターゲットに最も近いノードを検索
        target = NodeID(bytes([5] * 20))
        closest = table.find_closest(target, 3)
        
        self.assertEqual(len(closest), 3)
        # 距離順にソートされているか
        for i in range(len(closest) - 1):
            d1 = closest[i].distance_to(target)
            d2 = closest[i + 1].distance_to(target)
            self.assertLessEqual(d1, d2)
    
    def test_bucket_split(self):
        """バケット自動分割テスト"""
        self_id = NodeID(b'\x80' + b'\x00' * 19)  # bit 127
        table = RoutingTable(self_id, k=2)
        
        # バケットが満杯になり、自分の範囲内なら分割される
        for i in range(5):
            node_id = NodeID(bytes([i * 50] + [0] * 19))
            node = NodeInfo(node_id, "127.0.0.1", 8000 + i)
            table.add_node(node)
        
        # バケットが分割されたはず
        self.assertGreater(len(table.buckets), 1)


class TestDHTNode(unittest.TestCase):
    """DHTNodeのテスト"""
    
    def setUp(self):
        """テストセットアップ"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        """テストクリーンアップ"""
        self.loop.close()
    
    def test_creation(self):
        """生成テスト"""
        node = DHTNode(
            host="127.0.0.1",
            port=0,
            node_id=NodeID("test-node")
        )
        
        self.assertEqual(node.host, "127.0.0.1")
        self.assertIsNotNone(node.node_id)
        self.assertIsNotNone(node.routing_table)
        self.assertFalse(node._started)
    
    def test_start_stop(self):
        """起動・停止テスト"""
        async def test():
            node = DHTNode(host="127.0.0.1", port=0)
            
            await node.start()
            self.assertTrue(node._started)
            self.assertGreater(node.port, 0)
            
            await node.stop()
            self.assertFalse(node._started)
        
        self.loop.run_until_complete(test())
    
    def test_store_and_find_local(self):
        """ローカル保存・検索テスト"""
        async def test():
            node = DHTNode(host="127.0.0.1", port=0)
            await node.start()
            
            try:
                key = b"test-key"
                value = b"test-value"
                
                # ローカル保存
                await node.store(key, value)
                
                # ローカルから取得
                retrieved = node.get_local_value(key)
                self.assertEqual(retrieved, value)
                
            finally:
                await node.stop()
        
        self.loop.run_until_complete(test())
    
    def test_find_value_remote(self):
        """リモート値検索テスト"""
        async def test():
            # ノード1を作成
            node1 = DHTNode(
                host="127.0.0.1",
                port=0,
                node_id=NodeID("node1")
            )
            await node1.start()
            
            # ノード2を作成（ノード1をブートストラップ）
            node2 = DHTNode(
                host="127.0.0.1",
                port=0,
                node_id=NodeID("node2"),
                bootstrap_nodes=[{"host": "127.0.0.1", "port": node1.port}]
            )
            await node2.start()
            
            try:
                # 少し待ってブートストラップ完了
                await asyncio.sleep(1)
                
                # ノード2に値を保存
                key = b"shared-key"
                value = b"shared-value"
                
                success = await node2.store(key, value)
                self.assertTrue(success)
                
                # ノード1から検索
                retrieved = await node1.find_value(key)
                self.assertEqual(retrieved, value)
                
            finally:
                await node1.stop()
                await node2.stop()
        
        self.loop.run_until_complete(test())
    
    def test_find_node(self):
        """ノード探索テスト"""
        async def test():
            # 複数ノードを作成
            nodes = []
            bootstrap_port = None
            
            for i in range(3):
                bootstrap = [{"host": "127.0.0.1", "port": bootstrap_port}] if bootstrap_port else []
                node = DHTNode(
                    host="127.0.0.1",
                    port=0,
                    node_id=NodeID(f"node{i}"),
                    bootstrap_nodes=bootstrap
                )
                await node.start()
                nodes.append(node)
                if bootstrap_port is None:
                    bootstrap_port = node.port
                await asyncio.sleep(0.5)
            
            try:
                # 少し待って接続確立
                await asyncio.sleep(2)
                
                # ノード探索
                target = NodeID("target-node")
                closest = await nodes[0].find_node(target)
                
                # 結果が返ってくる
                self.assertIsInstance(closest, list)
                self.assertGreater(len(closest), 0)
                
            finally:
                for node in nodes:
                    await node.stop()
        
        self.loop.run_until_complete(test())
    
    def test_stats(self):
        """統計情報テスト"""
        async def test():
            node = DHTNode(
                host="127.0.0.1",
                port=0,
                node_id=NodeID("stats-test")
            )
            await node.start()
            
            try:
                stats = node.get_stats()
                
                self.assertIn("node_id", stats)
                self.assertIn("endpoint", stats)
                self.assertIn("started", stats)
                self.assertIn("routing_table", stats)
                self.assertIn("storage_entries", stats)
                
                self.assertTrue(stats["started"])
                self.assertEqual(stats["node_id"], node.node_id.hex)
                
            finally:
                await node.stop()
        
        self.loop.run_until_complete(test())


class TestDHTClient(unittest.TestCase):
    """DHTClientのテスト"""
    
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        self.loop.close()
    
    def test_client_connect(self):
        """クライアント接続テスト"""
        async def test():
            # サーバを起動
            server = DHTNode(host="127.0.0.1", port=0)
            await server.start()
            
            try:
                # クライアントで接続
                client = DHTClient([{"host": "127.0.0.1", "port": server.port}])
                connected = await client.connect()
                
                self.assertTrue(connected)
                self.assertGreater(len(client._nodes), 0)
                
            finally:
                await server.stop()
        
        self.loop.run_until_complete(test())
    
    def test_client_get(self):
        """クライアント取得テスト"""
        async def test():
            # サーバを起動
            server = DHTNode(host="127.0.0.1", port=0)
            await server.start()
            
            try:
                # データを保存
                key = b"client-test-key"
                value = b"client-test-value"
                await server.store(key, value)
                
                # クライアントで取得
                client = DHTClient([{"host": "127.0.0.1", "port": server.port}])
                await client.connect()
                
                retrieved = await client.get(key)
                self.assertEqual(retrieved, value)
                
            finally:
                await server.stop()
        
        self.loop.run_until_complete(test())


def run_async_test(coro):
    """非同期テストを実行"""
    return asyncio.run(coro)


if __name__ == "__main__":
    # テストを実行
    unittest.main(verbosity=2)
