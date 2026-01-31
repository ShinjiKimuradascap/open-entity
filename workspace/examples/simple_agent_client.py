#!/usr/bin/env python3
"""
Simple Agent Client Example
シンプルなAIエージェントクライアントのサンプル

Usage:
    python simple_agent_client.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "services"))

from token_system import create_wallet, get_task_contract


class SimpleAgent:
    """Simple AI Agent implementation"""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.wallet = create_wallet(agent_id, 0.0)
        print(f"Agent {agent_id} initialized with balance: {self.wallet.get_balance()}")
    
    def receive_task(self, task_id: str, amount: float, description: str):
        """Receive a task from orchestrator"""
        print(f"\n[{self.agent_id}] Received task: {task_id}")
        print(f"  Description: {description}")
        print(f"  Reward: {amount} AIC")
        return True
    
    def complete_task(self, task_id: str):
        """Complete assigned task"""
        print(f"[{self.agent_id}] Completing task: {task_id}")
        tc = get_task_contract()
        tc.complete_task(task_id)
        print(f"  Task completed! New balance: {self.wallet.get_balance()}")
        return True


def main():
    """Main example"""
    print("="*60)
    print("Simple Agent Client Example")
    print("="*60)
    
    # Create agent
    agent = SimpleAgent("sample_agent_001")
    
    # Simulate receiving a task
    agent.receive_task(
        task_id="TASK-EXAMPLE-001",
        amount=100.0,
        description="Process data batch #1234"
    )
    
    print("\nExample completed successfully!")
    print("="*60)


if __name__ == "__main__":
    main()