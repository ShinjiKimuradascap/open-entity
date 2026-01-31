#!/usr/bin/env python3
"""
Group Messaging (Multi-cast) System
グループメッセージング・マルチキャスト機能

Features:
- Group membership management
- Message fan-out (1-to-many delivery)
- Delivery tracking
- Group encryption support
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GroupRole(Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class MessageDeliveryStatus(Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


@dataclass
class GroupMember:
    entity_id: str
    role: GroupRole
    joined_at: datetime
    last_seen: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Group:
    group_id: str
    name: str
    description: str
    created_by: str
    created_at: datetime
    members: Dict[str, GroupMember] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)
    is_encrypted: bool = False
    encryption_key_id: Optional[str] = None


@dataclass
class GroupMessage:
    message_id: str
    group_id: str
    sender_id: str
    content: Any
    timestamp: datetime
    message_type: str = "text"
    reply_to: Optional[str] = None
    delivery_status: Dict[str, MessageDeliveryStatus] = field(default_factory=dict)


class GroupManager:
    """Manages group creation, membership, and metadata"""
    
    def __init__(self):
        self._groups: Dict[str, Group] = {}
        self._lock = asyncio.Lock()
        
    async def create_group(
        self,
        name: str,
        description: str,
        created_by: str,
        initial_members: Optional[List[str]] = None,
        is_encrypted: bool = False
    ) -> str:
        """Create a new group"""
        group_id = str(uuid.uuid4())
        
        async with self._lock:
            group = Group(
                group_id=group_id,
                name=name,
                description=description,
                created_by=created_by,
                created_at=datetime.now(timezone.utc),
                is_encrypted=is_encrypted
            )
            
            # Add creator as owner
            group.members[created_by] = GroupMember(
                entity_id=created_by,
                role=GroupRole.OWNER,
                joined_at=datetime.now(timezone.utc)
            )
            
            # Add initial members
            if initial_members:
                for member_id in initial_members:
                    if member_id != created_by:
                        group.members[member_id] = GroupMember(
                            entity_id=member_id,
                            role=GroupRole.MEMBER,
                            joined_at=datetime.now(timezone.utc)
                        )
            
            self._groups[group_id] = group
            logger.info(f"Group created: {group_id} by {created_by}")
            
        return group_id
    
    async def delete_group(self, group_id: str, deleted_by: str) -> bool:
        """Delete a group (owner only)"""
        async with self._lock:
            if group_id not in self._groups:
                return False
                
            group = self._groups[group_id]
            if group.members.get(deleted_by, GroupMember("", GroupRole.VIEWER, datetime.now())).role != GroupRole.OWNER:
                return False
                
            del self._groups[group_id]
            logger.info(f"Group deleted: {group_id}")
            return True
    
    async def add_member(
        self,
        group_id: str,
        member_id: str,
        role: GroupRole = GroupRole.MEMBER,
        added_by: str = None
    ) -> bool:
        """Add member to group"""
        async with self._lock:
            if group_id not in self._groups:
                return False
                
            group = self._groups[group_id]
            
            # Check if adder has permission
            if added_by:
                adder_role = group.members.get(added_by, GroupMember("", GroupRole.VIEWER, datetime.now())).role
                if adder_role not in (GroupRole.OWNER, GroupRole.ADMIN):
                    return False
            
            group.members[member_id] = GroupMember(
                entity_id=member_id,
                role=role,
                joined_at=datetime.now(timezone.utc)
            )
            logger.info(f"Member {member_id} added to group {group_id}")
            return True
    
    async def remove_member(
        self,
        group_id: str,
        member_id: str,
        removed_by: str
    ) -> bool:
        """Remove member from group"""
        async with self._lock:
            if group_id not in self._groups:
                return False
                
            group = self._groups[group_id]
            remover_role = group.members.get(removed_by, GroupMember("", GroupRole.VIEWER, datetime.now())).role
            
            # Can only remove if admin/owner or self
            if remover_role not in (GroupRole.OWNER, GroupRole.ADMIN) and removed_by != member_id:
                return False
            
            if member_id in group.members:
                del group.members[member_id]
                logger.info(f"Member {member_id} removed from group {group_id}")
                return True
            
            return False
    
    async def get_group(self, group_id: str) -> Optional[Group]:
        """Get group by ID"""
        return self._groups.get(group_id)
    
    async def get_member_groups(self, entity_id: str) -> List[str]:
        """Get all groups where entity is a member"""
        groups = []
        for group_id, group in self._groups.items():
            if entity_id in group.members:
                groups.append(group_id)
        return groups
    
    async def list_groups(self) -> List[Group]:
        """List all groups"""
        return list(self._groups.values())


class GroupMessagingService:
    """
    Group messaging service with multi-cast capability.
    
    Handles message fan-out to group members and delivery tracking.
    """
    
    def __init__(self, group_manager: GroupManager):
        self._group_manager = group_manager
        self._messages: Dict[str, GroupMessage] = {}
        self._group_messages: Dict[str, List[str]] = defaultdict(list)
        self._delivery_callbacks: List[Callable] = []
        self._lock = asyncio.Lock()
        
    async def send_message(
        self,
        group_id: str,
        sender_id: str,
        content: Any,
        message_type: str = "text",
        reply_to: Optional[str] = None,
        send_callback: Optional[Callable[[str, Any], asyncio.Future]] = None
    ) -> Optional[str]:
        """
        Send message to group (multi-cast).
        
        Returns message_id if successful, None otherwise.
        """
        group = await self._group_manager.get_group(group_id)
        if not group:
            logger.error(f"Group not found: {group_id}")
            return None
        
        if sender_id not in group.members:
            logger.error(f"Sender {sender_id} not in group {group_id}")
            return None
        
        # Create message
        message_id = str(uuid.uuid4())
        message = GroupMessage(
            message_id=message_id,
            group_id=group_id,
            sender_id=sender_id,
            content=content,
            timestamp=datetime.now(timezone.utc),
            message_type=message_type,
            reply_to=reply_to
        )
        
        # Initialize delivery status for all members
        for member_id in group.members:
            if member_id != sender_id:
                message.delivery_status[member_id] = MessageDeliveryStatus.PENDING
        
        async with self._lock:
            self._messages[message_id] = message
            self._group_messages[group_id].append(message_id)
        
        # Fan-out to members
        if send_callback:
            await self._fan_out_message(message, group, send_callback)
        
        logger.info(f"Message {message_id} sent to group {group_id}")
        return message_id
    
    async def _fan_out_message(
        self,
        message: GroupMessage,
        group: Group,
        send_callback: Callable[[str, Any], asyncio.Future]
    ):
        """Fan out message to all group members"""
        tasks = []
        
        for member_id, member in group.members.items():
            if member_id == message.sender_id:
                continue
                
            if member.role == GroupRole.VIEWER:
                continue
            
            # Create delivery task
            task = asyncio.create_task(
                self._deliver_to_member(member_id, message, send_callback)
            )
            tasks.append(task)
        
        # Wait for all deliveries (don't fail if one fails)
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for member_id, result in zip(
                [m for m in group.members if m != message.sender_id],
                results
            ):
                if isinstance(result, Exception):
                    message.delivery_status[member_id] = MessageDeliveryStatus.FAILED
                else:
                    message.delivery_status[member_id] = MessageDeliveryStatus.DELIVERED
    
    async def _deliver_to_member(
        self,
        member_id: str,
        message: GroupMessage,
        send_callback: Callable[[str, Any], asyncio.Future]
    ):
        """Deliver message to single member"""
        try:
            # Prepare message payload
            payload = {
                "type": "group_message",
                "message_id": message.message_id,
                "group_id": message.group_id,
                "sender_id": message.sender_id,
                "content": message.content,
                "timestamp": message.timestamp.isoformat(),
                "message_type": message.message_type
            }
            
            await send_callback(member_id, payload)
            
        except Exception as e:
            logger.error(f"Failed to deliver to {member_id}: {e}")
            raise
    
    async def mark_delivered(self, message_id: str, member_id: str):
        """Mark message as delivered to member"""
        async with self._lock:
            if message_id in self._messages:
                self._messages[message_id].delivery_status[member_id] = MessageDeliveryStatus.DELIVERED
    
    async def mark_read(self, message_id: str, member_id: str):
        """Mark message as read by member"""
        async with self._lock:
            if message_id in self._messages:
                self._messages[message_id].delivery_status[member_id] = MessageDeliveryStatus.READ
    
    async def get_message(self, message_id: str) -> Optional[GroupMessage]:
        """Get message by ID"""
        return self._messages.get(message_id)
    
    async def get_group_messages(
        self,
        group_id: str,
        limit: int = 50,
        before: Optional[datetime] = None
    ) -> List[GroupMessage]:
        """Get messages for group"""
        message_ids = self._group_messages.get(group_id, [])
        messages = []
        
        for msg_id in reversed(message_ids):
            if msg_id in self._messages:
                msg = self._messages[msg_id]
                if before and msg.timestamp >= before:
                    continue
                messages.append(msg)
                if len(messages) >= limit:
                    break
        
        return messages
    
    async def get_delivery_status(self, message_id: str) -> Optional[Dict[str, str]]:
        """Get delivery status for message"""
        if message_id not in self._messages:
            return None
        
        return {
            k: v.value for k, v in self._messages[message_id].delivery_status.items()
        }


class MulticastRouter:
    """
    Efficient multicast router for group messages.
    
    Optimizes delivery paths for multi-group scenarios.
    """
    
    def __init__(self):
        self._entity_groups: Dict[str, Set[str]] = defaultdict(set)
        self._group_entities: Dict[str, Set[str]] = defaultdict(set)
        
    def add_membership(self, entity_id: str, group_id: str):
        """Record entity membership in group"""
        self._entity_groups[entity_id].add(group_id)
        self._group_entities[group_id].add(entity_id)
        
    def remove_membership(self, entity_id: str, group_id: str):
        """Remove entity membership from group"""
        self._entity_groups[entity_id].discard(group_id)
        self._group_entities[group_id].discard(entity_id)
        
    def get_common_groups(self, entity1: str, entity2: str) -> Set[str]:
        """Find common groups between two entities"""
        return self._entity_groups[entity1] & self._entity_groups[entity2]
        
    def get_group_members(self, group_id: str) -> Set[str]:
        """Get all members of a group"""
        return self._group_entities[group_id].copy()


# Convenience functions
async def create_group_messaging_service() -> tuple:
    """Create group manager and messaging service"""
    group_manager = GroupManager()
    messaging_service = GroupMessagingService(group_manager)
    return group_manager, messaging_service
