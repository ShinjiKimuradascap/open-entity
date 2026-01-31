#!/usr/bin/env python3
"""
Token Persistence Manager
Handles saving and loading of token system data
"""

import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any
import logging

from .token_system import TokenWallet, Task, TaskStatus, TransactionType

logger = logging.getLogger(__name__)


class PersistenceManager:
    """Manages persistence of token system data"""
    
    def __init__(self, data_dir: str = "data/tokens"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.data_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        self._lock = threading.Lock()
    
    def save_wallets(self, wallets: Dict[str, TokenWallet],
                     filename: str = "wallets.json") -> bool:
        """Save wallets to JSON file"""
        with self._lock:
            try:
                filepath = self.data_dir / filename
                data = {
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "wallets": {
                        entity_id: wallet.to_dict()
                        for entity_id, wallet in wallets.items()
                    }
                }
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2)
                logger.info(f"Saved {len(wallets)} wallets to {filepath}")
                return True
            except Exception as e:
                logger.error(f"Failed to save wallets: {e}")
                return False
    
    def load_wallets(self, filename: str = "wallets.json") -> Dict[str, TokenWallet]:
        """Load wallets from JSON file"""
        filepath = self.data_dir / filename
        if not filepath.exists():
            logger.info(f"No wallet file found at {filepath}")
            return {}
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            wallets = {}
            for entity_id, wallet_data in data.get("wallets", {}).items():
                wallets[entity_id] = TokenWallet.from_dict(wallet_data)
            
            logger.info(f"Loaded {len(wallets)} wallets from {filepath}")
            return wallets
        except Exception as e:
            logger.error(f"Failed to load wallets: {e}")
            return {}
    
    def save_tasks(self, tasks: Dict[str, Task],
                   filename: str = "tasks.json") -> bool:
        """Save tasks to JSON file"""
        with self._lock:
            try:
                filepath = self.data_dir / filename
                data = {
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "tasks": {
                        task_id: task.to_dict()
                        for task_id, task in tasks.items()
                    }
                }
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2)
                logger.info(f"Saved {len(tasks)} tasks to {filepath}")
                return True
            except Exception as e:
                logger.error(f"Failed to save tasks: {e}")
                return False
    
    def load_tasks(self, filename: str = "tasks.json") -> Dict[str, Task]:
        """Load tasks from JSON file"""
        filepath = self.data_dir / filename
        if not filepath.exists():
            logger.info(f"No task file found at {filepath}")
            return {}
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            tasks = {}
            for task_id, task_data in data.get("tasks", {}).items():
                tasks[task_id] = Task.from_dict(task_data)
            
            logger.info(f"Loaded {len(tasks)} tasks from {filepath}")
            return tasks
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")
            return {}
    
    def create_backup(self, tag: Optional[str] = None) -> Optional[Path]:
        """Create a backup of current data"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tag_suffix = f"_{tag}" if tag else ""
        backup_name = f"backup_{timestamp}{tag_suffix}"
        backup_path = self.backup_dir / backup_name
        
        try:
            backup_path.mkdir(exist_ok=True)
            
            # Copy wallet and task files if they exist
            for filename in ["wallets.json", "tasks.json"]:
                src = self.data_dir / filename
                if src.exists():
                    shutil.copy2(src, backup_path / filename)
            
            logger.info(f"Created backup at {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return None
    
    def restore_backup(self, backup_path: Path) -> bool:
        """Restore data from backup"""
        try:
            for filename in ["wallets.json", "tasks.json"]:
                src = backup_path / filename
                if src.exists():
                    shutil.copy2(src, self.data_dir / filename)
            
            logger.info(f"Restored backup from {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False
    
    def list_backups(self) -> list[Path]:
        """List available backups"""
        return sorted(self.backup_dir.glob("backup_*"), reverse=True)
    
    def auto_save(self, wallets: Dict[str, TokenWallet],
                  tasks: Dict[str, Task]) -> bool:
        """Save both wallets and tasks, with backup"""
        # Create backup before saving
        self.create_backup("auto")
        
        success = True
        if not self.save_wallets(wallets):
            success = False
        if not self.save_tasks(tasks):
            success = False
        
        return success


# Global persistence manager
_persistence_manager: Optional[PersistenceManager] = None


def get_persistence_manager(data_dir: str = "data/tokens") -> PersistenceManager:
    """Get or create global persistence manager"""
    global _persistence_manager
    if _persistence_manager is None:
        _persistence_manager = PersistenceManager(data_dir)
    return _persistence_manager


if __name__ == "__main__":
    # Test
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from token_system import create_wallet, get_task_contract
    
    print("=== Persistence Manager Test ===")
    
    pm = PersistenceManager("data/tokens_test")
    
    # Create test wallets
    wallets = {
        "alice": create_wallet("alice", 1000),
        "bob": create_wallet("bob", 500)
    }
    
    # Save
    pm.save_wallets(wallets)
    
    # Load
    loaded = pm.load_wallets()
    print(f"Loaded {len(loaded)} wallets")
    for name, w in loaded.items():
        print(f"  {name}: {w.get_balance()} AIC")
    
    # Backup test
    backup = pm.create_backup("test")
    print(f"Created backup: {backup}")
    
    print("=== Test Complete ===")
