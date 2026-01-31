#!/usr/bin/env python3
"""
DHT Cryptographic Utilities
DHT用暗号化ユーティリティ

Provides Ed25519 signature support for DHT peer verification.
DHTピア検証用のEd25519署名サポートを提供します。
"""

import hashlib
import base64
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

# Import from parent crypto module
from services.crypto import (
    KeyPair, MessageSigner, SignatureVerifier,
    SecureMessage, MessageType
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PeerSignature:
    """ピア情報の署名コンテナ"""
    peer_id: str
    signature: bytes
    timestamp: datetime
    public_key: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "signature": base64.b64encode(self.signature).decode(),
            "timestamp": self.timestamp.isoformat(),
            "public_key": self.public_key
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PeerSignature':
        return cls(
            peer_id=data["peer_id"],
            signature=base64.b64decode(data["signature"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            public_key=data["public_key"]
        )


class DHTCrypto:
    """
    DHT用暗号化マネージャー
    
    PeerInfoの署名・検証を担当します。
    """
    
    def __init__(self, keypair: Optional[KeyPair] = None):
        self.keypair = keypair
        self._verifier = SignatureVerifier()
        
        if keypair:
            self._signer = MessageSigner(keypair)
            logger.info(f"DHTCrypto initialized with keypair for {keypair.entity_id}")
        else:
            self._signer = None
            logger.info("DHTCrypto initialized in verification-only mode")
    
    def sign_peer_info(
        self,
        peer_id: str,
        endpoint: str,
        public_key: str,
        capabilities: list,
        timestamp: Optional[datetime] = None
    ) -> Optional[PeerSignature]:
        """
        ピア情報に署名
        
        Args:
            peer_id: ピアID
            endpoint: エンドポイントURL
            public_key: 公開鍵
            capabilities: 機能リスト
            timestamp: タイムスタンプ（省略時は現在時刻）
            
        Returns:
            PeerSignature or None if signing fails
        """
        if not self._signer:
            logger.warning("Cannot sign: no keypair provided")
            return None
        
        try:
            timestamp = timestamp or datetime.now(timezone.utc)
            
            # 署名対象データを構築
            data = self._build_signing_data(
                peer_id=peer_id,
                endpoint=endpoint,
                public_key=public_key,
                capabilities=capabilities,
                timestamp=timestamp
            )
            
            # 署名実行
            signature = self._signer.sign(data)
            
            return PeerSignature(
                peer_id=peer_id,
                signature=signature,
                timestamp=timestamp,
                public_key=public_key
            )
            
        except Exception as e:
            logger.error(f"Failed to sign peer info: {e}")
            return None
    
    def verify_peer_info(
        self,
        peer_id: str,
        endpoint: str,
        public_key: str,
        capabilities: list,
        signature: bytes,
        signer_public_key: str,
        timestamp: Optional[datetime] = None,
        max_age_seconds: int = 86400
    ) -> bool:
        """
        ピア情報の署名を検証
        
        Args:
            peer_id: ピアID
            endpoint: エンドポイントURL
            public_key: 公開鍵
            capabilities: 機能リスト
            signature: 署名データ
            signer_public_key: 署名者の公開鍵
            timestamp: タイムスタンプ
            max_age_seconds: 署名の最大有効期間
            
        Returns:
            True if signature is valid
        """
        try:
            # タイムスタンプ検証
            if timestamp:
                age = (datetime.now(timezone.utc) - timestamp).total_seconds()
                if age > max_age_seconds:
                    logger.warning(f"Signature expired: {age}s old")
                    return False
            
            # 署名対象データを再構築
            data = self._build_signing_data(
                peer_id=peer_id,
                endpoint=endpoint,
                public_key=public_key,
                capabilities=capabilities,
                timestamp=timestamp or datetime.now(timezone.utc)
            )
            
            # 署名検証
            return self._verifier.verify(data, signature, signer_public_key)
            
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False
    
    def _build_signing_data(
        self,
        peer_id: str,
        endpoint: str,
        public_key: str,
        capabilities: list,
        timestamp: datetime
    ) -> bytes:
        """署名対象データを構築"""
        # 一貫性のあるフォーマットでデータを構築
        data_dict = {
            "peer_id": peer_id,
            "endpoint": endpoint,
            "public_key": public_key,
            "capabilities": sorted(capabilities) if capabilities else [],
            "timestamp": timestamp.isoformat()
        }
        
        # JSON文字列に変換してハッシュ
        data_str = str(sorted(data_dict.items()))
        return hashlib.sha256(data_str.encode()).digest()
    
    def compute_dht_key(self, entity_id: str, capability: str = "") -> bytes:
        """
        DHTキーを計算
        
        Args:
            entity_id: エンティティID
            capability: オプションの機能修飾子
            
        Returns:
            32-byte DHT key
        """
        capability_hash = hashlib.sha256(capability.encode()).hexdigest()[:16]
        key_string = f"{entity_id}:{capability_hash}"
        return hashlib.sha256(key_string.encode()).digest()
    
    @property
    def has_signing_key(self) -> bool:
        """署名キーが利用可能か"""
        return self._signer is not None
    
    @property
    def public_key(self) -> Optional[str]:
        """公開鍵を取得"""
        if self.keypair:
            return self.keypair.public_key
        return None


class SignedPeerInfo:
    """
    署名付きピア情報
    
    PeerInfo + signature for verification
    """
    
    def __init__(
        self,
        peer_id: str,
        endpoint: str,
        public_key: str,
        capabilities: list = None,
        signature: Optional[PeerSignature] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.peer_id = peer_id
        self.endpoint = endpoint
        self.public_key = public_key
        self.capabilities = capabilities or []
        self.signature = signature
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "peer_id": self.peer_id,
            "endpoint": self.endpoint,
            "public_key": self.public_key,
            "capabilities": self.capabilities,
            "metadata": self.metadata
        }
        if self.signature:
            result["signature"] = self.signature.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SignedPeerInfo':
        signature = None
        if "signature" in data:
            signature = PeerSignature.from_dict(data["signature"])
        
        return cls(
            peer_id=data["peer_id"],
            endpoint=data["endpoint"],
            public_key=data["public_key"],
            capabilities=data.get("capabilities", []),
            signature=signature,
            metadata=data.get("metadata", {})
        )
    
    def verify(self, crypto: DHTCrypto) -> bool:
        """署名を検証"""
        if not self.signature:
            logger.warning(f"No signature for peer {self.peer_id}")
            return False
        
        return crypto.verify_peer_info(
            peer_id=self.peer_id,
            endpoint=self.endpoint,
            public_key=self.public_key,
            capabilities=self.capabilities,
            signature=self.signature.signature,
            signer_public_key=self.signature.public_key,
            timestamp=self.signature.timestamp
        )


# Convenience functions
def create_dht_crypto(keypair: Optional[KeyPair] = None) -> DHTCrypto:
    """DHTCryptoインスタンスを作成"""
    return DHTCrypto(keypair)


def compute_peer_key(peer_id: str, prefix: str = "peer:") -> bytes:
    """ピアIDからDHTキーを計算"""
    key_string = f"{prefix}{peer_id}"
    return hashlib.sha256(key_string.encode()).digest()


if __name__ == "__main__":
    # テスト
    print("=== DHT Crypto Test ===")
    
    # テスト用キーペアを作成（簡易版）
    try:
        from services.crypto import generate_keypair
        
        keypair = generate_keypair("test-entity")
        crypto = DHTCrypto(keypair)
        
        # 署名テスト
        sig = crypto.sign_peer_info(
            peer_id="test-peer",
            endpoint="http://127.0.0.1:8000",
            public_key=keypair.public_key,
            capabilities=["chat", "code"]
        )
        
        if sig:
            print(f"Signature created: {sig.signature.hex()[:32]}...")
            
            # 検証テスト
            valid = crypto.verify_peer_info(
                peer_id="test-peer",
                endpoint="http://127.0.0.1:8000",
                public_key=keypair.public_key,
                capabilities=["chat", "code"],
                signature=sig.signature,
                signer_public_key=keypair.public_key,
                timestamp=sig.timestamp
            )
            print(f"Signature valid: {valid}")
        
        # DHTキー計算テスト
        key1 = crypto.compute_dht_key("entity-a")
        key2 = crypto.compute_dht_key("entity-a", "chat")
        print(f"DHT Key (entity): {key1.hex()[:32]}...")
        print(f"DHT Key (capability): {key2.hex()[:32]}...")
        
    except ImportError:
        print("Note: services.crypto not available for full test")
    
    print("\n=== Test Complete ===")
