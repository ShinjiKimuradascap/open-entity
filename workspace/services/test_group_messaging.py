#!/usr/bin/env python3
"""Tests for Group Messaging System"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from group_messaging import (
    GroupManager,
    GroupMessagingService,
    MulticastRouter,
    GroupRole,
    create_group_messaging_service
)


async def test_group_creation():
    """Test group creation and management"""
    gm = GroupManager()
    
    # Create group
    group_id = await gm.create_group(
        name="Test Group",
        description="A test group",
        created_by="user-1",
        initial_members=["user-2", "user-3"]
    )
    
    assert group_id is not None
    
    # Get group
    group = await gm.get_group(group_id)
    assert group is not None
    assert group.name == "Test Group"
    assert len(group.members) == 3  # creator + 2 members
    
    # Check creator is owner
    assert group.members["user-1"].role == GroupRole.OWNER
    
    print("  test_group_creation: PASSED")


async def test_member_management():
    """Test adding and removing members"""
    gm = GroupManager()
    
    group_id = await gm.create_group(
        name="Test Group",
        description="Test",
        created_by="user-1"
    )
    
    # Add member
    result = await gm.add_member(group_id, "user-4", GroupRole.MEMBER, "user-1")
    assert result is True
    
    group = await gm.get_group(group_id)
    assert "user-4" in group.members
    
    # Remove member
    result = await gm.remove_member(group_id, "user-4", "user-1")
    assert result is True
    
    group = await gm.get_group(group_id)
    assert "user-4" not in group.members
    
    print("  test_member_management: PASSED")


async def test_group_messaging():
    """Test group message sending"""
    gm, ms = await create_group_messaging_service()
    
    # Create group
    group_id = await gm.create_group(
        name="Chat Group",
        description="Test chat",
        created_by="user-1",
        initial_members=["user-2", "user-3"]
    )
    
    # Track deliveries
    delivered = []
    async def mock_send(member_id, payload):
        delivered.append(member_id)
    
    # Send message
    msg_id = await ms.send_message(
        group_id=group_id,
        sender_id="user-1",
        content="Hello everyone!",
        send_callback=mock_send
    )
    
    assert msg_id is not None
    
    # Wait for delivery
    await asyncio.sleep(0.1)
    
    # Check message stored
    message = await ms.get_message(msg_id)
    assert message is not None
    assert message.content == "Hello everyone!"
    
    print("  test_group_messaging: PASSED")


async def test_multicast_router():
    """Test multicast router"""
    router = MulticastRouter()
    
    # Add memberships
    router.add_membership("user-1", "group-a")
    router.add_membership("user-1", "group-b")
    router.add_membership("user-2", "group-b")
    router.add_membership("user-2", "group-c")
    
    # Find common groups
    common = router.get_common_groups("user-1", "user-2")
    assert "group-b" in common
    assert "group-a" not in common
    
    # Get group members
    members = router.get_group_members("group-b")
    assert "user-1" in members
    assert "user-2" in members
    
    print("  test_multicast_router: PASSED")


async def main():
    print("=== Group Messaging Tests ===\n")
    
    try:
        await test_group_creation()
        await test_member_management()
        await test_group_messaging()
        await test_multicast_router()
        print("\n=== All tests passed! ===")
        return 0
    except Exception as e:
        print(f"\n=== FAILED: {e} ===")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
