"""
Open Entity + AutoGen Integration Example

This example demonstrates how to:
1. Create AutoGen agents with A2A network capabilities
2. Connect to the A2A bootstrap network
3. Discover and communicate with other Open Entity agents
4. Use A2A as a tool for agent collaboration

Requirements:
    pip install pyautogen>=0.4.0 open-entity

Run:
    python autogen_integration.py
"""

import asyncio
import os
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import AutoGen
try:
    import autogen
    from autogen import ConversableAgent, GroupChat, GroupChatManager
    AUTOGEN_AVAILABLE = True
except ImportError:
    print("AutoGen not installed. Run: pip install pyautogen>=0.4.0")
    AUTOGEN_AVAILABLE = False

# Import Open Entity A2A bridge
try:
    from open_entity.adapters.autogen_bridge import (
        AutoGenConversableAgentWrapper,
        A2ATool,
        register_autogen_agent,
        A2AConfig
    )
    OPEN_ENTITY_AVAILABLE = True
except ImportError:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from open_entity.adapters.autogen_bridge import (
        AutoGenConversableAgentWrapper,
        A2ATool,
        register_autogen_agent,
        A2AConfig
    )
    OPEN_ENTITY_AVAILABLE = True


# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-api-key")
BOOTSTRAP_NODES = [
    "bootstrap.open-entity.fly.dev:9473",
    # Add more bootstrap nodes as needed
]


def create_llm_config() -> Dict[str, Any]:
    """Create LLM configuration for AutoGen."""
    return {
        "config_list": [
            {
                "model": "gpt-4",
                "api_key": OPENAI_API_KEY,
            }
        ],
        "temperature": 0.7,
    }


async def example_1_basic_a2a_agent():
    """Example 1: Create a single A2A-enabled AutoGen agent."""
    print("\n" + "="*60)
    print("Example 1: Basic A2A Agent")
    print("="*60)
    
    # Create an agent with A2A capabilities
    agent = AutoGenConversableAgentWrapper(
        name="code_assistant",
        system_message="""You are a helpful coding assistant.
        You can review code, suggest improvements, and answer programming questions.
        When you need help from other specialists, use the A2A network.
        """,
        llm_config=create_llm_config(),
        a2a_config=A2AConfig(
            bootstrap_nodes=BOOTSTRAP_NODES,
            capabilities=["coding", "python", "javascript", "review"],
            port=8081,
            auto_register=True
        )
    )
    
    # Start A2A participation
    await agent.start_a2a()
    
    print(f"✓ Agent '{agent.name}' started")
    print(f"  - A2A ID: {agent.a2a_identity.agent_id}")
    print(f"  - Endpoint: {agent.a2a_identity.endpoint}")
    print(f"  - Capabilities: {agent.a2a_config.capabilities}")
    
    # Keep agent alive for demonstration
    await asyncio.sleep(5)
    print("✓ Agent ready for A2A communication\n")
    
    return agent


async def example_2_discover_agents(agent: AutoGenConversableAgentWrapper):
    """Example 2: Discover other agents in the network."""
    print("\n" + "="*60)
    print("Example 2: Agent Discovery")
    print("="*60)
    
    # Discover agents by capability
    print("\nSearching for agents with 'code_review' capability...")
    agents = await agent.discover_agents(
        capability="code_review",
        min_reputation=0.3
    )
    
    if agents:
        print(f"✓ Found {len(agents)} agents:")
        for a in agents:
            print(f"  - {a.name} (ID: {a.agent_id[:16]}...)")
            print(f"    Reputation: {a.reputation:.2f}")
            print(f"    Capabilities: {', '.join(a.capabilities)}")
    else:
        print("ℹ No agents found (this is expected if network is empty)")
    
    # Search for other capabilities
    print("\nSearching for agents with 'analysis' capability...")
    analysis_agents = await agent.discover_agents(capability="analysis")
    print(f"✓ Found {len(analysis_agents)} analysis agents\n")


async def example_3_send_a2a_message(agent: AutoGenConversableAgentWrapper):
    """Example 3: Send a message to another agent."""
    print("\n" + "="*60)
    print("Example 3: A2A Messaging")
    print("="*60)
    
    # First, discover potential recipients
    agents = await agent.discover_agents(capability="review")
    
    if not agents:
        print("ℹ No agents available for messaging")
        print("  (In production, you would target a specific agent_id)")
        return
    
    # Send a message to the first available agent
    recipient = agents[0]
    print(f"\nSending message to {recipient.name}...")
    
    message = await agent.send_a2a_message(
        recipient_id=recipient.agent_id,
        content="Can you review this Python function for potential issues?",
        context={
            "code": """
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)
            """,
            "language": "python"
        }
    )
    
    if message:
        print(f"✓ Message sent (ID: {message.message_id})")
    else:
        print("✗ Failed to send message")


async def example_4_a2a_as_tool():
    """Example 4: Use A2A network as an AutoGen tool."""
    print("\n" + "="*60)
    print("Example 4: A2A as AutoGen Tool")
    print("="*60)
    
    # Create an agent
    agent = AutoGenConversableAgentWrapper(
        name="orchestrator",
        system_message="""You are an orchestrator agent.
        Your job is to delegate tasks to other specialized agents via the A2A network.
        Use the discover_agents and send_message tools when needed.
        """,
        llm_config=create_llm_config(),
        a2a_config=A2AConfig(
            bootstrap_nodes=BOOTSTRAP_NODES,
            capabilities=["orchestration", "delegation"],
            port=8082
        )
    )
    
    await agent.start_a2a()
    
    # Create A2A tool wrapper
    a2a_tool = A2ATool(agent)
    
    # Register A2A functions as tools
    agent.register_function(
        function_map={
            "discover_agents": a2a_tool.discover_agents,
            "send_message": a2a_tool.send_message,
            "get_network_status": a2a_tool.get_network_status
        }
    )
    
    print("✓ Agent with A2A tools registered")
    print("  Available functions:")
    print("    - discover_agents(capability, min_reputation)")
    print("    - send_message(agent_id, message, context)")
    print("    - get_network_status()")
    
    # Simulate tool usage
    print("\nTesting tool: get_network_status()")
    status = await a2a_tool.get_network_status()
    print(f"✓ Status: {status[:200]}...\n")


async def example_5_multi_agent_with_a2a():
    """Example 5: Multiple AutoGen agents communicating via A2A."""
    print("\n" + "="*60)
    print("Example 5: Multi-Agent A2A Collaboration")
    print("="*60)
    
    # Create specialized agents
    code_agent = AutoGenConversableAgentWrapper(
        name="coder",
        system_message="You are a Python expert. Write clean, efficient code.",
        llm_config=create_llm_config(),
        a2a_config=A2AConfig(
            bootstrap_nodes=BOOTSTRAP_NODES,
            capabilities=["python", "coding", "development"],
            port=8083
        )
    )
    
    review_agent = AutoGenConversableAgentWrapper(
        name="reviewer",
        system_message="You are a code reviewer. Check for bugs, style issues, and improvements.",
        llm_config=create_llm_config(),
        a2a_config=A2AConfig(
            bootstrap_nodes=BOOTSTRAP_NODES,
            capabilities=["code_review", "quality", "analysis"],
            port=8084
        )
    )
    
    # Start both agents
    await code_agent.start_a2a()
    await review_agent.start_a2a()
    
    print(f"✓ Started 2 agents:")
    print(f"  - {code_agent.name}: {code_agent.a2a_identity.agent_id[:20]}...")
    print(f"  - {review_agent.name}: {review_agent.a2a_identity.agent_id[:20]}...")
    
    # Simulate collaboration
    print("\nSimulating A2A workflow:")
    print("1. Coder sends code to Reviewer...")
    
    msg = await code_agent.send_a2a_message(
        recipient_id=review_agent.a2a_identity.agent_id,
        content="Please review this function",
        context={"code": "def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)"}
    )
    
    if msg:
        print(f"   ✓ Request sent: {msg.message_id[:16]}...")
    
    print("2. Reviewer discovers available coders...")
    coders = await review_agent.discover_agents(capability="coding")
    print(f"   ✓ Found {len(coders)} coding agents\n")


async def example_6_register_with_capabilities():
    """Example 6: Register agent with specific capabilities."""
    print("\n" + "="*60)
    print("Example 6: Capability-Based Registration")
    print("="*60)
    
    # Create agent
    agent = AutoGenConversableAgentWrapper(
        name="data_analyst",
        system_message="You analyze data and create visualizations.",
        llm_config=create_llm_config(),
        a2a_config=A2AConfig(
            bootstrap_nodes=BOOTSTRAP_NODES,
            port=8085
            # Note: capabilities will be set during registration
        )
    )
    
    # Register with specific capabilities
    success = await register_autogen_agent(
        agent,
        capabilities=[
            "data_analysis",
            "pandas",
            "visualization",
            "statistics",
            "python"
        ]
    )
    
    if success:
        print("✓ Agent registered with capabilities:")
        for cap in agent.a2a_config.capabilities:
            print(f"  - {cap}")
    else:
        print("✗ Registration failed")
    
    print()


async def main():
    """Run all examples."""
    print("\n" + "="*60)
    print("Open Entity + AutoGen Integration Examples")
    print("="*60)
    
    if not AUTOGEN_AVAILABLE:
        print("\n❌ AutoGen not available. Install with:")
        print("   pip install pyautogen>=0.4.0")
        return
    
    if not OPEN_ENTITY_AVAILABLE:
        print("\n❌ Open Entity not available.")
        return
    
    print("\n📦 Dependencies check:")
    print("  ✓ AutoGen available")
    print("  ✓ Open Entity A2A Bridge available")
    
    # Check for API key
    if OPENAI_API_KEY == "your-api-key":
        print("\n⚠️  Warning: OPENAI_API_KEY not set")
        print("   Some examples may use placeholder LLM responses")
    else:
        print("  ✓ OpenAI API key configured")
    
    try:
        # Run examples
        agent = await example_1_basic_a2a_agent()
        await example_2_discover_agents(agent)
        await example_3_send_a2a_message(agent)
        await example_4_a2a_as_tool()
        await example_5_multi_agent_with_a2a()
        await example_6_register_with_capabilities()
        
        print("\n" + "="*60)
        print("All examples completed successfully!")
        print("="*60)
        print("\nNext steps:")
        print("  1. Deploy your own bootstrap node: ./scripts/deploy_bootstrap.sh")
        print("  2. Create specialized agents with unique capabilities")
        print("  3. Build agent teams that collaborate via A2A")
        print("  4. Explore the A2A protocol: docs/A2A_PROTOCOL.md")
        print()
        
    except Exception as e:
        logger.error(f"Error running examples: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())