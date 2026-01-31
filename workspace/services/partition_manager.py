#!/usr/bin/env python3
"""
Partition Manager - Network Partition Detection and Resolution

Provides Merkle tree-based divergence detection and CRDT-based conflict resolution
for distributed registry consistency during network partitions.

Features:
- Merkle tree for efficient state comparison
- Vector clock-based conflict detection
- Automatic partition recovery
- Deterministic conflict resolution (LWW with tie-breaker)
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PartitionState(Enum):
    """Partition detection states"""
    HEALTHY = "healthy"
    SUSPECTED = "suspected"
    PARTITIONED = "partitioned"
    RECOVERING = "recovering"


class ResolutionAction(Enum):
    """Conflict resolution actions"""
    KEEP_LOCAL = "keep_local"
    ACCEPT_REMOTE = "accept_remote"
    MERGE = "merge"


@dataclass
class ConflictResolution:
    """Result of conflict resolution"""
    entity_id: str
    action: ResolutionAction
    reason: str
    winner: Optional[Any] = None


@dataclass
class MerkleNode:
    """Node in Merkle tree"""
    hash: str
    left: Optional['MerkleNode'] = None
    right: Optional['MerkleNode'] = None
    is_leaf: bool = False
    entity_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Serialize to dict"""
        return {
            "hash": self.hash,
            "is_leaf": self.is_leaf,
            "entity_id": self.entity_id,
            "left": self.left.to_dict() if self.left else None,
            "right": self.right.to_dict() if self.right else None
        }


class MerkleTree:
    """
    Merkle tree for efficient state divergence detection.
    
    Enables O(log n) comparison of registry states between nodes.
    """
    
    def __init__(self, root: Optional[MerkleNode] = None):
        self.root = root
        self._leaf_map: Dict[str, MerkleNode] = {}
    
    @classmethod
    def from_entries(cls, entries: List[Any]) -> 'MerkleTree':
        """
        Build Merkle tree from registry entries.
        
        Args:
            entries: List of RegistryEntry objects
            
        Returns:
            Constructed MerkleTree
        """
        if not entries:
            return cls(None)
        
        # Sort by entity_id for deterministic tree
        sorted_entries = sorted(entries, key=lambda e: e.entity_id)
        
        # Build leaves
        leaves = []
        for entry in sorted_entries:
            leaf_hash = cls._hash_entry(entry)
            leaf = MerkleNode(
                hash=leaf_hash,
                is_leaf=True,
                entity_id=entry.entity_id
            )
            leaves.append(leaf)
        
        # Build tree bottom-up
        root = cls._build_tree(leaves)
        
        tree = cls(root)
        for leaf in leaves:
            if leaf.entity_id:
                tree._leaf_map[leaf.entity_id] = leaf
        
        return tree
    
    @staticmethod
    def _hash_entry(entry: Any) -> str:
        """Create hash for registry entry"""
        data = {
            "entity_id": entry.entity_id,
            "version": entry.version,
            "last_heartbeat": entry.last_heartbeat.isoformat() if hasattr(entry.last_heartbeat, 'isoformat') else str(entry.last_heartbeat),
            "node_id": entry.node_id
        }
        payload = json.dumps(data, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()
    
    @staticmethod
    def _hash_pair(left_hash: str, right_hash: str) -> str:
        """Hash two child nodes together"""
        combined = left_hash + right_hash
        return hashlib.sha256(combined.encode()).hexdigest()
    
    @classmethod
    def _build_tree(cls, nodes: List[MerkleNode]) -> Optional[MerkleNode]:
        """Build tree from leaf nodes"""
        if not nodes:
            return None
        
        if len(nodes) == 1:
            return nodes[0]
        
        # Build next level
        next_level = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else None
            
            if right:
                parent_hash = cls._hash_pair(left.hash, right.hash)
            else:
                parent_hash = left.hash
            
            parent = MerkleNode(
                hash=parent_hash,
                left=left,
                right=right
            )
            next_level.append(parent)
        
        return cls._build_tree(next_level)
    
    def get_root_hash(self) -> Optional[str]:
        """Get root hash of tree"""
        return self.root.hash if self.root else None
    
    def find_differences(self, other: 'MerkleTree') -> Set[str]:
        """
        Find differing entity IDs between two trees.
        
        Args:
            other: MerkleTree to compare with
            
        Returns:
            Set of entity IDs that differ
        """
        differences = set()
        self._compare_nodes(self.root, other.root, differences)
        return differences
    
    def _compare_nodes(self, local: Optional[MerkleNode], 
                       remote: Optional[MerkleNode], 
                       differences: Set[str]):
        """Recursively compare tree nodes"""
        # Both None - no difference
        if not local and not remote:
            return
        
        # One None - all leaves differ
        if not local or not remote:
            self._collect_leaf_ids(local or remote, differences)
            return
        
        # Same hash - no difference
        if local.hash == remote.hash:
            return
        
        # Both leaves - direct difference
        if local.is_leaf and remote.is_leaf:
            if local.entity_id:
                differences.add(local.entity_id)
            return
        
        # Recurse into children
        self._compare_nodes(local.left, remote.left, differences)
        self._compare_nodes(local.right, remote.right, differences)
    
    def _collect_leaf_ids(self, node: Optional[MerkleNode], result: Set[str]):
        """Collect all leaf entity IDs"""
        if not node:
            return
        
        if node.is_leaf and node.entity_id:
            result.add(node.entity_id)
        
        self._collect_leaf_ids(node.left, result)
        self._collect_leaf_ids(node.right, result)


@dataclass
class VectorClock:
    """Vector clock for causality tracking"""
    clocks: Dict[str, int] = field(default_factory=dict)
    
    def increment(self, node_id: str) -> 'VectorClock':
        """Increment clock for a node"""
        new_clocks = dict(self.clocks)
        new_clocks[node_id] = new_clocks.get(node_id, 0) + 1
        return VectorClock(new_clocks)
    
    def merge(self, other: 'VectorClock') -> 'VectorClock':
        """Merge two vector clocks (taking max of each entry)"""
        merged = dict(self.clocks)
        for node_id, timestamp in other.clocks.items():
            merged[node_id] = max(merged.get(node_id, 0), timestamp)
        return VectorClock(merged)
    
    def compare(self, other: 'VectorClock') -> Optional[int]:
        """
        Compare two vector clocks.
        Returns: -1 if self < other, 0 if concurrent/equal, 1 if self > other
        """
        all_nodes = set(self.clocks.keys()) | set(other.clocks.keys())
        
        has_less = False
        has_greater = False
        
        for node_id in all_nodes:
            self_ts = self.clocks.get(node_id, 0)
            other_ts = other.clocks.get(node_id, 0)
            
            if self_ts < other_ts:
                has_less = True
            elif self_ts > other_ts:
                has_greater = True
        
        if has_less and has_greater:
            return 0  # Concurrent
        elif has_less:
            return -1  # self happens-before other
        elif has_greater:
            return 1  # other happens-before self
        else:
            return 0  # Equal
    
    def is_concurrent_with(self, other: 'VectorClock') -> bool:
        """Check if two vector clocks are concurrent"""
        return self.compare(other) == 0 and self.clocks != other.clocks
    
    def to_dict(self) -> Dict[str, int]:
        return dict(self.clocks)
    
    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> 'VectorClock':
        return cls(data)


class PartitionManager:
    """
    Manages network partition detection and resolution.
    
    Uses Merkle trees for efficient divergence detection
    and vector clocks for conflict resolution.
    """
    
    PARTITION_TIMEOUT = 60  # seconds
    MERKLE_SYNC_INTERVAL = 30  # seconds
    MAX_DIVERGENT_ENTRIES = 100  # Max entries to sync in one batch
    
    def __init__(self, registry: Any, node_id: str):
        """
        Initialize partition manager.
        
        Args:
            registry: DistributedRegistry instance
            node_id: Local node ID
        """
        self.registry = registry
        self.node_id = node_id
        self.merkle_tree: Optional[MerkleTree] = None
        self.partition_state = PartitionState.HEALTHY
        self.known_partitions: Dict[str, PartitionState] = {}
        self._sync_task: Optional[asyncio.Task] = None
        self._divergence_callbacks: List[Callable] = []
        
        # Track partition events
        self._partition_history: List[Dict] = []
    
    async def start(self):
        """Start partition monitoring"""
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info("PartitionManager started")
    
    async def stop(self):
        """Stop partition monitoring"""
        if self._sync_task:
            self._sync_task.cancel()
        logger.info("PartitionManager stopped")
    
    async def _sync_loop(self):
        """Periodic sync loop"""
        while True:
            try:
                await asyncio.sleep(self.MERKLE_SYNC_INTERVAL)
                await self._check_all_peers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
    
    async def _check_all_peers(self):
        """Check all known peers for divergence"""
        # Build local Merkle tree
        self.merkle_tree = MerkleTree.from_entries(
            self.registry.get_all_entries()
        )
        local_root = self.merkle_tree.get_root_hash()
        
        # Check each known peer
        for peer_id in self.registry._known_nodes:
            try:
                await self._check_peer_divergence(peer_id, local_root)
            except Exception as e:
                logger.debug(f"Failed to check peer {peer_id}: {e}")
    
    async def _check_peer_divergence(self, peer_id: str, local_root: str):
        """Check divergence with specific peer"""
        # Request remote Merkle root
        remote_root = await self._request_merkle_root(peer_id)
        
        if remote_root != local_root:
            # Divergence detected
            logger.warning(f"Divergence detected with peer {peer_id}")
            self.partition_state = PartitionState.SUSPECTED
            
            # Trigger divergence resolution
            await self._resolve_divergence(peer_id)
    
    async def _request_merkle_root(self, peer_id: str) -> Optional[str]:
        """Request Merkle root from peer"""
        # This would make actual network request
        # For now, return None (simulated)
        return None
    
    async def _request_merkle_tree(self, peer_id: str) -> Optional[MerkleTree]:
        """Request full Merkle tree from peer"""
        # This would make actual network request
        return None
    
    async def _resolve_divergence(self, peer_id: str):
        """Resolve divergence with peer"""
        logger.info(f"Resolving divergence with {peer_id}")
        self.partition_state = PartitionState.RECOVERING
        
        # Get remote tree
        remote_tree = await self._request_merkle_tree(peer_id)
        if not remote_tree or not self.merkle_tree:
            logger.error("Failed to get Merkle trees for comparison")
            return
        
        # Find differences
        differences = self.merkle_tree.find_differences(remote_tree)
        
        if not differences:
            logger.info("No actual differences found (false positive)")
            self.partition_state = PartitionState.HEALTHY
            return
        
        logger.info(f"Found {len(differences)} differing entries")
        
        # Fetch remote entries
        remote_entries = await self._fetch_remote_entries(peer_id, differences)
        
        # Resolve conflicts
        resolutions = await self.resolve_conflicts(remote_entries)
        
        # Apply resolutions
        await self._apply_resolutions(resolutions)
        
        # Record event
        self._record_partition_event(peer_id, differences, resolutions)
        
        self.partition_state = PartitionState.HEALTHY
        
        # Notify callbacks
        for callback in self._divergence_callbacks:
            try:
                callback(peer_id, differences, resolutions)
            except Exception as e:
                logger.error(f"Divergence callback error: {e}")
    
    async def _fetch_remote_entries(self, peer_id: str, 
                                    entity_ids: Set[str]) -> List[Any]:
        """Fetch specific entries from remote peer"""
        # This would make actual network request
        # Return empty list for now (simulated)
        return []
    
    async def resolve_conflicts(self, remote_entries: List[Any]) -> List[ConflictResolution]:
        """
        Resolve conflicts between local and remote entries.
        
        Args:
            remote_entries: List of RegistryEntry from remote peer
            
        Returns:
            List of conflict resolutions
        """
        resolutions = []
        
        for remote in remote_entries:
            local = self.registry.get_entry(remote.entity_id)
            
            if not local:
                # New entry - accept
                resolutions.append(ConflictResolution(
                    entity_id=remote.entity_id,
                    action=ResolutionAction.ACCEPT_REMOTE,
                    reason="New entry in remote"
                ))
                continue
            
            # Get vector clocks
            local_vc = getattr(local, 'vector_clock', None)
            remote_vc = getattr(remote, 'vector_clock', None)
            
            if not local_vc or not remote_vc:
                # Fallback to timestamp comparison
                if remote.last_heartbeat > local.last_heartbeat:
                    resolutions.append(ConflictResolution(
                        entity_id=remote.entity_id,
                        action=ResolutionAction.ACCEPT_REMOTE,
                        reason="Remote has newer timestamp"
                    ))
                else:
                    resolutions.append(ConflictResolution(
                        entity_id=remote.entity_id,
                        action=ResolutionAction.KEEP_LOCAL,
                        reason="Local has newer timestamp"
                    ))
                continue
            
            # Compare vector clocks
            comparison = local_vc.compare(remote_vc)
            
            if comparison == 1:
                # Local is newer - keep local
                resolutions.append(ConflictResolution(
                    entity_id=remote.entity_id,
                    action=ResolutionAction.KEEP_LOCAL,
                    reason="Local version is causally newer"
                ))
                
            elif comparison == -1:
                # Remote is newer - accept remote
                resolutions.append(ConflictResolution(
                    entity_id=remote.entity_id,
                    action=ResolutionAction.ACCEPT_REMOTE,
                    reason="Remote version is causally newer"
                ))
                
            else:
                # Concurrent - use LWW with deterministic tie-breaker
                winner = self._resolve_concurrent_update(local, remote)
                action = (ResolutionAction.KEEP_LOCAL 
                         if winner == local 
                         else ResolutionAction.ACCEPT_REMOTE)
                
                resolutions.append(ConflictResolution(
                    entity_id=remote.entity_id,
                    action=action,
                    winner=winner,
                    reason="Concurrent update - LWW tie-breaker"
                ))
        
        return resolutions
    
    def _resolve_concurrent_update(self, local: Any, remote: Any) -> Any:
        """
        Resolve concurrent updates using deterministic tie-breaker.
        
        Tie-breaker priority:
        1. Higher version number
        2. Later timestamp
        3. Higher node_id hash
        """
        # Compare versions
        if local.version != remote.version:
            return local if local.version > remote.version else remote
        
        # Compare timestamps
        if local.last_heartbeat != remote.last_heartbeat:
            return (local if local.last_heartbeat > remote.last_heartbeat 
                   else remote)
        
        # Deterministic hash comparison of node_id
        local_hash = hashlib.sha256(local.node_id.encode()).hexdigest()
        remote_hash = hashlib.sha256(remote.node_id.encode()).hexdigest()
        
        return local if local_hash > remote_hash else remote
    
    async def _apply_resolutions(self, resolutions: List[ConflictResolution]):
        """Apply conflict resolutions to registry"""
        for resolution in resolutions:
            if resolution.action == ResolutionAction.ACCEPT_REMOTE:
                # Merge remote entry
                if resolution.winner:
                    self.registry.merge_entry(resolution.winner)
                    logger.debug(f"Applied remote entry: {resolution.entity_id}")
            
            # KEEP_LOCAL requires no action
            # MERGE would require custom logic
    
    def _record_partition_event(self, peer_id: str, 
                                differences: Set[str],
                                resolutions: List[ConflictResolution]):
        """Record partition event to history"""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "peer_id": peer_id,
            "divergent_entries": len(differences),
            "resolutions": [
                {
                    "entity_id": r.entity_id,
                    "action": r.action.value,
                    "reason": r.reason
                }
                for r in resolutions
            ]
        }
        self._partition_history.append(event)
    
    def add_divergence_callback(self, callback: Callable):
        """Add callback for divergence events"""
        self._divergence_callbacks.append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get partition manager statistics"""
        return {
            "partition_state": self.partition_state.value,
            "known_partitions": len(self.known_partitions),
            "merkle_root": self.merkle_tree.get_root_hash() if self.merkle_tree else None,
            "partition_history_count": len(self._partition_history),
            "recent_events": self._partition_history[-10:] if self._partition_history else []
        }


# Global instance management
_partition_managers: Dict[str, PartitionManager] = {}


def get_partition_manager(registry: Any, node_id: str) -> PartitionManager:
    """Get or create partition manager for node"""
    if node_id not in _partition_managers:
        _partition_managers[node_id] = PartitionManager(registry, node_id)
    return _partition_managers[node_id]


if __name__ == "__main__":
    # Test Merkle tree
    from services.distributed_registry import RegistryEntry
    
    entries = [
        RegistryEntry(
            entity_id="agent-1",
            entity_name="Agent 1",
            endpoint="http://localhost:8001",
            capabilities=["code"],
            registered_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
            version=1,
            node_id="node-1"
        ),
        RegistryEntry(
            entity_id="agent-2",
            entity_name="Agent 2",
            endpoint="http://localhost:8002",
            capabilities=["review"],
            registered_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
            version=1,
            node_id="node-2"
        ),
    ]
    
    tree = MerkleTree.from_entries(entries)
    print(f"Merkle root: {tree.get_root_hash()}")
    
    # Test vector clock
    vc1 = VectorClock({"node-1": 1, "node-2": 0})
    vc2 = VectorClock({"node-1": 1, "node-2": 1})
    
    print(f"VC1: {vc1.to_dict()}")
    print(f"VC2: {vc2.to_dict()}")
    print(f"Comparison: {vc1.compare(vc2)}")  # Should be -1 (vc1 < vc2)
