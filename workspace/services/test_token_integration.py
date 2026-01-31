#!/usr/bin/env python3
"""
Integration tests for token system v2
Tests persistence + economy features
"""

import unittest
import sys
import shutil
from pathlib import Path

# Add services to path
sys.path.insert(0, str(Path(__file__).parent))

from token_system import create_wallet, get_wallet, get_task_contract
from token_persistence import PersistenceManager
from token_economy import TokenEconomy, TokenMetadata, get_token_economy, initialize_token_economy


class TestTokenPersistence(unittest.TestCase):
    """Test persistence manager"""
    
    def setUp(self):
        self.test_dir = Path("data/test_tokens")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.pm = PersistenceManager(str(self.test_dir))
        
        # Clear global wallet registry to avoid conflicts between tests
        import token_system
        token_system._wallet_registry.clear()
    
    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_save_load_wallets(self):
        """Test saving and loading wallets"""
        wallets = {
            "alice": create_wallet("alice", 1000),
            "bob": create_wallet("bob", 500)
        }
        
        # Save
        self.assertTrue(self.pm.save_wallets(wallets))
        
        # Load
        loaded = self.pm.load_wallets()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded["alice"].get_balance(), 1000)
        self.assertEqual(loaded["bob"].get_balance(), 500)
    
    def test_backup_restore(self):
        """Test backup and restore"""
        wallets = {"alice": create_wallet("alice", 1000)}
        self.pm.save_wallets(wallets)
        
        # Create backup
        backup = self.pm.create_backup("test")
        self.assertIsNotNone(backup)
        
        # Modify data
        wallets["alice"]._balance = 0
        self.pm.save_wallets(wallets)
        
        # Restore
        self.assertTrue(self.pm.restore_backup(backup))
        loaded = self.pm.load_wallets()
        self.assertEqual(loaded["alice"].get_balance(), 1000)


class TestTokenEconomy(unittest.TestCase):
    """Test token economy (mint/burn)"""
    
    def setUp(self):
        # Reset global state
        import token_economy
        token_economy._token_economy = None
        self.economy = get_token_economy()
    
    def test_mint(self):
        """Test token minting"""
        alice = create_wallet("test_alice", 0)
        
        # Mint 1000 tokens
        result = self.economy.mint(1000, "test_alice", "Test mint")
        self.assertTrue(result["success"])
        self.assertEqual(alice.get_balance(), 1000)
        self.assertEqual(self.economy.get_total_supply(), 1000)
    
    def test_mint_max_supply(self):
        """Test minting respects max supply"""
        metadata = TokenMetadata(max_supply=1000)
        economy = TokenEconomy(metadata=metadata)
        
        # First mint should succeed
        result1 = economy.mint(500, "test_alice")
        self.assertTrue(result1["success"])
        
        # Second mint should fail (would exceed max)
        result2 = economy.mint(600, "test_alice")
        self.assertFalse(result2["success"])
    
    def test_burn(self):
        """Test token burning"""
        alice = create_wallet("test_alice2", 0)
        self.economy.mint(1000, "test_alice2")
        
        # Burn 300 tokens
        result = self.economy.burn(300, alice, "Test burn")
        self.assertTrue(result["success"])
        self.assertEqual(alice.get_balance(), 700)
        self.assertEqual(self.economy.get_total_supply(), 700)
    
    def test_burn_insufficient(self):
        """Test burning more than balance fails"""
        alice = create_wallet("test_alice3", 100)
        
        # Try to burn more than balance
        result = self.economy.burn(200, alice)
        self.assertFalse(result["success"])
        self.assertEqual(alice.get_balance(), 100)  # Unchanged


class TestIntegration(unittest.TestCase):
    """Test full integration"""
    
    def setUp(self):
        self.test_dir = Path("data/test_integration")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.pm = PersistenceManager(str(self.test_dir))
        
        # Clear global state to avoid conflicts between tests
        import token_economy
        import token_system
        token_economy._token_economy = None
        token_system._wallet_registry.clear()
        self.economy = get_token_economy()
    
    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_full_workflow(self):
        """Test complete token workflow"""
        # 1. Create user wallets
        alice = create_wallet("int_alice", 0)
        bob = create_wallet("int_bob", 0)
        
        # 2. Mint tokens directly to users (mint transfers directly to recipient)
        result1 = self.economy.mint(1000, "int_alice", "Initial distribution to Alice")
        self.assertTrue(result1["success"])
        
        result2 = self.economy.mint(500, "int_bob", "Initial distribution to Bob")
        self.assertTrue(result2["success"])
        
        # 3. User transfer: Alice sends 200 to Bob
        self.assertTrue(alice.transfer(bob, 200))
        
        # 4. Save state
        from token_system import _wallet_registry
        self.pm.save_wallets(_wallet_registry)
        
        # 5. Verify balances
        self.assertEqual(alice.get_balance(), 800)
        self.assertEqual(bob.get_balance(), 700)
        
        # 6. Load and verify
        loaded = self.pm.load_wallets()
        self.assertEqual(loaded["int_alice"].get_balance(), 800)
        self.assertEqual(loaded["int_bob"].get_balance(), 700)


if __name__ == "__main__":
    unittest.main(verbosity=2)
