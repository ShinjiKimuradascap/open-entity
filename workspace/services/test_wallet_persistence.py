#!/usr/bin/env python3
"""
Wallet Persistence Test Suite
ウォレット永続化機能のテスト
"""

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest

from services.token_system import TokenWallet, create_wallet
from services.wallet_persistence import WalletPersistence


class TestWalletPersistence:
    """WalletPersistenceクラスのテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリを作成し、テスト後に削除"""
        temp_path = tempfile.mkdtemp()
        yield Path(temp_path)
        shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def persistence(self, temp_dir):
        """テスト用のWalletPersistenceインスタンス"""
        return WalletPersistence(data_dir=temp_dir)
    
    @pytest.fixture
    def sample_wallet(self):
        """テスト用のサンプルウォレット"""
        wallet = TokenWallet(entity_id="test_entity", _balance=1000.0)
        wallet.deposit(500, "Initial deposit")
        wallet.deposit(300, "Second deposit")
        return wallet
    
    def test_init_creates_directory(self, temp_dir):
        """初期化時にディレクトリが作成される"""
        subdir = temp_dir / "wallets" / "nested"
        persistence = WalletPersistence(data_dir=subdir)
        assert subdir.exists()
        assert subdir.is_dir()
    
    def test_save_wallet(self, persistence, sample_wallet):
        """ウォレットを保存できる"""
        result = persistence.save_wallet(sample_wallet)
        assert result is True
        
        # ファイルが作成されたか確認
        file_path = persistence._get_wallet_path("test_entity")
        assert file_path.exists()
    
    def test_save_wallet_creates_valid_json(self, persistence, sample_wallet):
        """保存されたファイルが有効なJSON"""
        persistence.save_wallet(sample_wallet)
        
        file_path = persistence._get_wallet_path("test_entity")
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        assert data['entity_id'] == "test_entity"
        assert data['balance'] == 1000.0
        assert len(data['transactions']) == 2
        assert '_metadata' in data
    
    def test_load_wallet(self, persistence, sample_wallet):
        """保存したウォレットを読み込める"""
        persistence.save_wallet(sample_wallet)
        
        loaded = persistence.load_wallet("test_entity")
        assert loaded is not None
        assert loaded.entity_id == "test_entity"
        assert loaded.get_balance() == 1000.0
        assert len(loaded.get_transaction_history()) == 2
    
    def test_load_wallet_not_found(self, persistence):
        """存在しないウォレットを読み込むとNoneが返る"""
        loaded = persistence.load_wallet("non_existent")
        assert loaded is None
    
    def test_list_wallets(self, persistence):
        """保存されているウォレット一覧を取得"""
        # 複数のウォレットを作成
        wallet1 = TokenWallet(entity_id="alice", _balance=100)
        wallet2 = TokenWallet(entity_id="bob", _balance=200)
        wallet3 = TokenWallet(entity_id="charlie", _balance=300)
        
        persistence.save_wallet(wallet1)
        persistence.save_wallet(wallet2)
        persistence.save_wallet(wallet3)
        
        wallets = persistence.list_wallets()
        assert len(wallets) == 3
        assert wallets == ["alice", "bob", "charlie"]  # ソート済み
    
    def test_list_wallets_empty(self, persistence):
        """ウォレットがない場合は空リスト"""
        wallets = persistence.list_wallets()
        assert wallets == []
    
    def test_delete_wallet(self, persistence, sample_wallet):
        """ウォレットを削除できる"""
        persistence.save_wallet(sample_wallet)
        
        # 削除前に存在確認
        assert persistence.wallet_exists("test_entity") is True
        
        result = persistence.delete_wallet("test_entity")
        assert result is True
        
        # 削除後に存在確認
        assert persistence.wallet_exists("test_entity") is False
    
    def test_delete_wallet_not_found(self, persistence):
        """存在しないウォレットを削除するとFalse"""
        result = persistence.delete_wallet("non_existent")
        assert result is False
    
    def test_wallet_exists(self, persistence, sample_wallet):
        """wallet_existsメソッドの動作確認"""
        assert persistence.wallet_exists("test_entity") is False
        
        persistence.save_wallet(sample_wallet)
        assert persistence.wallet_exists("test_entity") is True
    
    def test_get_wallet_info(self, persistence, sample_wallet):
        """ウォレット情報を取得"""
        persistence.save_wallet(sample_wallet)
        
        info = persistence.get_wallet_info("test_entity")
        assert info is not None
        assert info['entity_id'] == "test_entity"
        assert 'file_path' in info
        assert 'file_size' in info
        assert 'modified_at' in info
        assert 'created_at' in info
    
    def test_get_wallet_info_not_found(self, persistence):
        """存在しないウォレットの情報はNone"""
        info = persistence.get_wallet_info("non_existent")
        assert info is None
    
    def test_save_all_wallets(self, persistence):
        """複数ウォレットを一括保存"""
        wallets = [
            TokenWallet(entity_id="user1", _balance=100),
            TokenWallet(entity_id="user2", _balance=200),
            TokenWallet(entity_id="user3", _balance=300),
        ]
        
        results = persistence.save_all_wallets(wallets)
        
        assert len(results) == 3
        assert all(results.values())  # 全て成功
        assert persistence.list_wallets() == ["user1", "user2", "user3"]
    
    def test_load_all_wallets(self, persistence):
        """複数ウォレットを一括読み込み"""
        # 事前に保存
        for i in range(3):
            wallet = TokenWallet(entity_id=f"user{i}", _balance=float(i * 100))
            persistence.save_wallet(wallet)
        
        results = persistence.load_all_wallets()
        
        assert len(results) == 3
        for i in range(3):
            loaded = results[f"user{i}"]
            assert loaded is not None
            assert loaded.entity_id == f"user{i}"
            assert loaded.get_balance() == float(i * 100)
    
    def test_get_storage_stats(self, persistence):
        """ストレージ統計情報"""
        # ウォレットを作成
        wallet1 = TokenWallet(entity_id="alice", _balance=100)
        wallet2 = TokenWallet(entity_id="bob", _balance=200)
        persistence.save_wallet(wallet1)
        persistence.save_wallet(wallet2)
        
        stats = persistence.get_storage_stats()
        
        assert stats['wallet_count'] == 2
        assert stats['total_size_bytes'] > 0
        assert stats['data_dir'] == str(persistence.data_dir)
        assert "alice" in stats['wallets']
        assert "bob" in stats['wallets']
    
    def test_invalid_wallet_type(self, persistence):
        """無効な型をsave_walletに渡すとFalse"""
        result = persistence.save_wallet("not_a_wallet")
        assert result is False
        
        result = persistence.save_wallet(None)
        assert result is False


class TestAtomicWrite:
    """アトミック書き込みのテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield Path(temp_path)
        shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def persistence(self, temp_dir):
        return WalletPersistence(data_dir=temp_dir)
    
    def test_atomic_write_no_partial_file(self, persistence):
        """書き込み失敗時に一時ファイルが残らない"""
        # 無効なデータを直接書き込もうとするテストは難しいので、
        # 代わりに正常系で.tmpファイルが残らないことを確認
        wallet = TokenWallet(entity_id="test", _balance=100)
        persistence.save_wallet(wallet)
        
        # .tmpファイルが存在しないことを確認
        temp_file = persistence._get_wallet_path("test").with_suffix('.tmp')
        assert not temp_file.exists()
    
    def test_data_integrity_after_save(self, persistence):
        """保存後のデータ整合性"""
        wallet = TokenWallet(entity_id="integrity_test", _balance=500.0)
        wallet.deposit(100.5, "Test deposit")
        wallet.withdraw(50.25, "Test withdraw")
        
        persistence.save_wallet(wallet)
        loaded = persistence.load_wallet("integrity_test")
        
        assert loaded.get_balance() == 500.0 + 100.5 - 50.25
        assert loaded.entity_id == "integrity_test"
        
        history = loaded.get_transaction_history()
        assert len(history) == 2


class TestThreadSafety:
    """スレッドセーフのテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield Path(temp_path)
        shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def persistence(self, temp_dir):
        return WalletPersistence(data_dir=temp_dir)
    
    def test_concurrent_save_same_wallet(self, persistence):
        """同じウォレットへの並行保存"""
        wallet = TokenWallet(entity_id="concurrent", _balance=0)
        
        results = []
        errors = []
        
        def save_with_increment(amount):
            try:
                wallet.deposit(amount)
                result = persistence.save_wallet(wallet)
                results.append(result)
            except Exception as e:
                errors.append(str(e))
        
        # 複数スレッドで同時に保存
        threads = []
        for i in range(10):
            t = threading.Thread(target=save_with_increment, args=(10.0,))
            threads.append(t)
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # エラーがないことを確認
        assert len(errors) == 0
        
        # ファイルが有効なJSONであることを確認
        loaded = persistence.load_wallet("concurrent")
        assert loaded is not None
        # すべてのdepositが反映されているはず
        assert loaded.get_balance() == 100.0  # 10 * 10
    
    def test_concurrent_different_wallets(self, persistence):
        """異なるウォレットへの並行保存"""
        wallets = [
            TokenWallet(entity_id=f"user_{i}", _balance=float(i * 100))
            for i in range(10)
        ]
        
        results = []
        errors = []
        
        def save_wallet(wallet):
            try:
                result = persistence.save_wallet(wallet)
                results.append((wallet.entity_id, result))
            except Exception as e:
                errors.append((wallet.entity_id, str(e)))
        
        threads = []
        for wallet in wallets:
            t = threading.Thread(target=save_wallet, args=(wallet,))
            threads.append(t)
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # エラーがないことを確認
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r[1] for r in results)  # 全て成功
        
        # 全てのウォレットが保存されていることを確認
        assert len(persistence.list_wallets()) == 10
    
    def test_concurrent_read_write(self, persistence):
        """読み書きの並行アクセス"""
        wallet = TokenWallet(entity_id="rw_test", _balance=0)
        persistence.save_wallet(wallet)
        
        read_results = []
        write_errors = []
        
        def writer():
            for i in range(20):
                try:
                    w = persistence.load_wallet("rw_test")
                    if w:
                        w.deposit(1.0)
                        persistence.save_wallet(w)
                except Exception as e:
                    write_errors.append(str(e))
                time.sleep(0.001)
        
        def reader():
            for _ in range(20):
                try:
                    w = persistence.load_wallet("rw_test")
                    if w:
                        read_results.append(w.get_balance())
                except Exception:
                    pass
                time.sleep(0.001)
        
        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=writer))
            threads.append(threading.Thread(target=reader))
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 致命的なエラーがないことを確認
        assert len(write_errors) == 0
        
        # 最終的な残高が整合していることを確認
        final = persistence.load_wallet("rw_test")
        assert final.get_balance() == 60.0  # 3 writers * 20 iterations


class TestIntegrationWithTokenSystem:
    """TokenSystemとの統合テスト"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield Path(temp_path)
        shutil.rmtree(temp_path, ignore_errors=True)
    
    def test_round_trip_persistence(self, temp_dir):
        """完全な往復テスト：作成→保存→読み込み→検証"""
        persistence = WalletPersistence(data_dir=temp_dir)
        
        # ウォレット作成と操作
        wallet = TokenWallet(entity_id="round_trip_user", _balance=1000)
        wallet.deposit(500, "Salary")
        wallet.withdraw(200, "Payment")
        wallet.deposit(100, "Bonus")
        
        # 保存
        assert persistence.save_wallet(wallet) is True
        
        # 読み込み
        loaded = persistence.load_wallet("round_trip_user")
        assert loaded is not None
        
        # 検証
        assert loaded.entity_id == "round_trip_user"
        assert loaded.get_balance() == 1400.0  # 1000 + 500 - 200 + 100
        
        history = loaded.get_transaction_history()
        assert len(history) == 3
        
        # トランザクションの種類を確認
        types = [t.type.value for t in history]
        assert "deposit" in types
        assert "withdraw" in types
    
    def test_persistence_with_transfers(self, temp_dir):
        """送金履歴も正しく保存される"""
        persistence = WalletPersistence(data_dir=temp_dir)
        
        # 2つのウォレットを作成
        alice = TokenWallet(entity_id="alice_persist", _balance=1000)
        bob = TokenWallet(entity_id="bob_persist", _balance=500)
        
        # 送金
        alice.transfer(bob, 200, "Payment for services")
        
        # 両方を保存
        persistence.save_wallet(alice)
        persistence.save_wallet(bob)
        
        # 読み込み
        loaded_alice = persistence.load_wallet("alice_persist")
        loaded_bob = persistence.load_wallet("bob_persist")
        
        # 検証
        assert loaded_alice.get_balance() == 800.0
        assert loaded_bob.get_balance() == 700.0
        
        # トランザクション履歴に送金が記録されている
        alice_history = loaded_alice.get_transaction_history()
        assert any(t.type.value == "transfer_out" for t in alice_history)
        
        bob_history = loaded_bob.get_transaction_history()
        assert any(t.type.value == "transfer_in" for t in bob_history)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
