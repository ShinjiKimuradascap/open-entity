#!/usr/bin/env python3
"""
Wallet Persistence Module
ウォレットの永続化管理（JSONファイル保存/読み込み）
アトミック書き込み・スレッドセーフ実装
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from services.token_system import TokenWallet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WalletPersistence:
    """ウォレット永続化管理クラス
    
    JSONファイルへの保存/読み込みをアトミックに行い、
    スレッドセーフに実装された永続化レイヤー
    
    Attributes:
        data_dir: ウォレットファイルの保存先ディレクトリ
        _locks: エンティティごとの書き込みロック
        _global_lock: ロック管理用のグローバルロック
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        """初期化
        
        Args:
            data_dir: データディレクトリのパス（Noneの場合はデフォルト）
        """
        self.data_dir = data_dir or Path("/home/moco/workspace/data/wallets")
        self._ensure_data_dir()
        
        # スレッドセーフのためのロック管理
        self._global_lock = threading.Lock()
        self._locks: Dict[str, threading.Lock] = {}
    
    def _ensure_data_dir(self) -> None:
        """データディレクトリが存在することを確認し、存在しない場合は作成"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_wallet_path(self, entity_id: str) -> Path:
        """ウォレットファイルのパスを取得
        
        Args:
            entity_id: エンティティID
            
        Returns:
            ウォレットファイルのパス
        """
        return self.data_dir / f"{entity_id}.json"
    
    def _get_lock(self, entity_id: str) -> threading.Lock:
        """エンティティIDに対応するロックを取得（必要に応じて作成）
        
        Args:
            entity_id: エンティティID
            
        Returns:
            エンティティ専用のロック
        """
        with self._global_lock:
            if entity_id not in self._locks:
                self._locks[entity_id] = threading.Lock()
            return self._locks[entity_id]
    
    def save_wallet(self, wallet: TokenWallet) -> bool:
        """ウォレットをJSONファイルに保存（アトミック書き込み）
        
        一時ファイルに書き込んでからリネームすることで、
        クラッシュ時もデータ破損を防ぐ
        
        Args:
            wallet: 保存するTokenWalletインスタンス
            
        Returns:
            保存成功時True、失敗時False
        """
        if not isinstance(wallet, TokenWallet):
            logger.error(f"Invalid wallet type: {type(wallet)}")
            return False
        
        entity_id = wallet.entity_id
        lock = self._get_lock(entity_id)
        
        with lock:
            try:
                file_path = self._get_wallet_path(entity_id)
                temp_path = file_path.with_suffix('.tmp')
                
                # データを準備
                data = wallet.to_dict()
                data['_metadata'] = {
                    'saved_at': datetime.now(timezone.utc).isoformat(),
                    'version': '1.0'
                }
                
                # 一時ファイルに書き込み（アトミック書き込みの第一步）
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                
                # 一時ファイルを本ファイルにリネーム（アトミック操作）
                os.replace(temp_path, file_path)
                
                # ディレクトリの同期も確保（オプションだが安全）
                try:
                    dir_fd = os.open(self.data_dir, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                except OSError:
                    pass  # ディレクトリ同期の失敗は無視
                
                logger.info(f"Saved wallet for {entity_id} to {file_path}")
                return True
                
            except (IOError, OSError, TypeError) as e:
                logger.error(f"Failed to save wallet for {entity_id}: {e}")
                # 一時ファイルが残っていれば削除
                try:
                    temp_path = self._get_wallet_path(entity_id).with_suffix('.tmp')
                    if temp_path.exists():
                        temp_path.unlink()
                except OSError:
                    pass
                return False
    
    def load_wallet(self, entity_id: str) -> Optional[TokenWallet]:
        """JSONファイルからウォレットを読み込み
        
        Args:
            entity_id: 読み込むエンティティID
            
        Returns:
            読み込まれたTokenWallet、存在しないか失敗時はNone
        """
        lock = self._get_lock(entity_id)
        
        with lock:
            try:
                file_path = self._get_wallet_path(entity_id)
                
                if not file_path.exists():
                    logger.warning(f"Wallet file not found: {file_path}")
                    return None
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # メタデータを除去して復元
                data.pop('_metadata', None)
                
                wallet = TokenWallet.from_dict(data)
                
                logger.info(f"Loaded wallet for {entity_id} from {file_path}")
                return wallet
                
            except (IOError, OSError, json.JSONDecodeError, KeyError, TypeError) as e:
                logger.error(f"Failed to load wallet for {entity_id}: {e}")
                return None
    
    def list_wallets(self) -> List[str]:
        """保存されているウォレットのエンティティID一覧を取得
        
        Returns:
            エンティティIDのリスト（アルファベット順）
        """
        try:
            self._ensure_data_dir()
            json_files = self.data_dir.glob("*.json")
            
            # 一時ファイルを除外
            entity_ids = [
                f.stem for f in json_files 
                if f.suffix == '.json' and not f.name.endswith('.tmp')
            ]
            
            return sorted(entity_ids)
            
        except OSError as e:
            logger.error(f"Failed to list wallets: {e}")
            return []
    
    def delete_wallet(self, entity_id: str) -> bool:
        """ウォレットファイルを削除
        
        Args:
            entity_id: 削除するエンティティID
            
        Returns:
            削除成功時True、ファイルが存在しないか失敗時False
        """
        lock = self._get_lock(entity_id)
        
        with lock:
            try:
                file_path = self._get_wallet_path(entity_id)
                
                if not file_path.exists():
                    logger.warning(f"Wallet file not found for deletion: {file_path}")
                    return False
                
                file_path.unlink()
                
                # クリーンアップ：ロックを解放
                with self._global_lock:
                    if entity_id in self._locks:
                        del self._locks[entity_id]
                
                logger.info(f"Deleted wallet for {entity_id}")
                return True
                
            except (IOError, OSError) as e:
                logger.error(f"Failed to delete wallet for {entity_id}: {e}")
                return False
    
    def wallet_exists(self, entity_id: str) -> bool:
        """ウォレットファイルが存在するかチェック
        
        Args:
            entity_id: チェックするエンティティID
            
        Returns:
            ファイルが存在する場合True
        """
        return self._get_wallet_path(entity_id).exists()
    
    def get_wallet_info(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """ウォレットのメタ情報を取得（完全読み込みなし）
        
        Args:
            entity_id: エンティティID
            
        Returns:
            メタ情報の辞書、存在しない場合はNone
        """
        try:
            file_path = self._get_wallet_path(entity_id)
            
            if not file_path.exists():
                return None
            
            stat = file_path.stat()
            
            return {
                'entity_id': entity_id,
                'file_path': str(file_path),
                'file_size': stat.st_size,
                'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat()
            }
            
        except OSError as e:
            logger.error(f"Failed to get wallet info for {entity_id}: {e}")
            return None
    
    def save_all_wallets(self, wallets: List[TokenWallet]) -> Dict[str, bool]:
        """複数のウォレットを一括保存
        
        Args:
            wallets: 保存するTokenWalletのリスト
            
        Returns:
            エンティティID -> 成功/失敗の辞書
        """
        results = {}
        for wallet in wallets:
            results[wallet.entity_id] = self.save_wallet(wallet)
        return results
    
    def load_all_wallets(self) -> Dict[str, Optional[TokenWallet]]:
        """保存されている全てのウォレットを読み込み
        
        Returns:
            エンティティID -> TokenWallet（または失敗時None）の辞書
        """
        entity_ids = self.list_wallets()
        results = {}
        
        for entity_id in entity_ids:
            results[entity_id] = self.load_wallet(entity_id)
        
        return results
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """ストレージ統計情報を取得
        
        Returns:
            統計情報の辞書
        """
        try:
            wallets = self.list_wallets()
            total_size = 0
            
            for entity_id in wallets:
                info = self.get_wallet_info(entity_id)
                if info:
                    total_size += info.get('file_size', 0)
            
            return {
                'wallet_count': len(wallets),
                'total_size_bytes': total_size,
                'data_dir': str(self.data_dir),
                'wallets': wallets
            }
            
        except OSError as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {
                'wallet_count': 0,
                'total_size_bytes': 0,
                'data_dir': str(self.data_dir),
                'wallets': [],
                'error': str(e)
            }
