"""A2A (AI-to-AI) communication commands."""
import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Optional, List

from ..a2a.protocol import A2AProtocol, AgentIdentity, MessageType
from ..a2a.transport import HTTPTransport

# mDNS import (optional dependency)
try:
    from ..discovery.mdns import (
        MDNSServiceDiscovery, 
        register_local_agent, 
        discover_local_agents,
        ZEROCO_AVAILABLE
    )
except ImportError:
    ZEROCO_AVAILABLE = False

a2a_app = typer.Typer(help="A2A (AI-to-AI) communication")


@a2a_app.command("discover")
def discover_agent(
    endpoint: str = typer.Argument(..., help="Agent endpoint URL"),
):
    """Discover agent at endpoint."""
    console = Console()
    
    async def _discover():
        # Create temporary protocol
        identity = AgentIdentity(
            agent_id="temp",
            name="temp",
            public_key="temp",
            endpoint="",
        )
        protocol = A2AProtocol(identity, "secret")
        transport = HTTPTransport(protocol)
        
        agent_info = await transport.discover_agent(endpoint)
        return agent_info
    
    info = asyncio.run(_discover())
    
    if info:
        table = Table(title="Agent Information")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        
        for key, value in info.items():
            table.add_row(key, str(value))
        
        console.print(table)
    else:
        console.print("[red]Failed to discover agent[/]")


@a2a_app.command("serve")
def serve_agent(
    host: str = typer.Option("0.0.0.0", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    name: str = typer.Option("agent", "--name", "-n"),
    mdns: bool = typer.Option(True, "--mdns/--no-mdns", help="Register on local network via mDNS"),
    capabilities: Optional[str] = typer.Option(None, "--capabilities", "-c", help="Comma-separated capabilities (e.g., 'coding,review')"),
):
    """Start A2A server to receive messages."""
    console = Console()
    
    async def _serve():
        agent_id = f"agent_{port}"
        identity = AgentIdentity(
            agent_id=agent_id,
            name=name,
            public_key="dummy_key",
            endpoint=f"http://{host}:{port}",
        )
        
        protocol = A2AProtocol(identity, "secret_key")
        transport = HTTPTransport(protocol, host, port)
        
        # Register message handler
        async def handle_request(message):
            console.print(f"[green]Received:[/] {message.payload}")
            return None
        
        protocol.register_handler(MessageType.REQUEST, handle_request)
        
        await transport.start()
        console.print(Panel.fit(
            f"[green]A2A server started[/]\n"
            f"Endpoint: http://{host}:{port}\n"
            f"Agent ID: {agent_id}",
            title="🤖 Open Entity Agent",
            border_style="green"
        ))
        
        # mDNS registration
        mdns_discovery = None
        if mdns:
            if ZEROCO_AVAILABLE:
                try:
                    caps = [c.strip() for c in capabilities.split(",") if c.strip()] if capabilities else []
                    mdns_discovery = MDNSServiceDiscovery()
                    await mdns_discovery.register(
                        agent_id=agent_id,
                        port=port,
                        capabilities=caps,
                        metadata={"name": name, "version": "1.0.0"}
                    )
                    console.print(f"[cyan]📡 Registered on local network (mDNS)[/]")
                    console.print(f"[dim]   Other agents on same WiFi can discover you automatically[/]")
                except Exception as e:
                    console.print(f"[yellow]⚠️ mDNS registration failed: {e}[/]")
            else:
                console.print(f"[yellow]⚠️ zeroconf not installed[/]")
                console.print(f"[dim]   Install: pip install zeroconf[/]")
                console.print(f"[dim]   Or disable: oe a2a serve --no-mdns[/]")
        
        console.print("\n[dim]Press Ctrl+C to stop[/]")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            if mdns_discovery:
                await mdns_discovery.close()
            await transport.stop()
    
    asyncio.run(_serve())


@a2a_app.command("send")
def send_message(
    endpoint: str = typer.Argument(..., help="Target agent endpoint"),
    message: str = typer.Argument(..., help="Message content"),
):
    """Send message to another agent."""
    console = Console()
    
    async def _send():
        identity = AgentIdentity(
            agent_id="sender",
            name="sender",
            public_key="key",
            endpoint="",
        )
        
        target = AgentIdentity(
            agent_id="target",
            name="target",
            public_key="key",
            endpoint=endpoint,
        )
        
        protocol = A2AProtocol(identity, "secret")
        transport = HTTPTransport(protocol)
        
        msg = protocol.create_message(
            recipient=target,
            message_type=MessageType.REQUEST,
            payload={"content": message},
        )
        
        response = await transport.send_message(endpoint, msg)
        return response
    
    response = asyncio.run(_send())
    
    if response:
        console.print(f"[green]Response:[/] {response.payload}")
    else:
        console.print("[yellow]No response received[/]")


@a2a_app.command("local-discover")
def local_discover(
    timeout: float = typer.Option(3.0, "--timeout", "-t", help="Discovery timeout (seconds)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Discover AI agents on local network via mDNS (same WiFi)."""
    console = Console()
    
    if not ZEROCO_AVAILABLE:
        console.print(Panel.fit(
            "[yellow]⚠️ zeroconf is not installed[/]\n\n"
            "[white]Install it:[/]\n"
            "  pip install zeroconf\n\n"
            "[dim]This enables automatic discovery of other AI agents\n"
            "on the same local network without any configuration.[/]",
            title="mDNS Not Available",
            border_style="yellow"
        ))
        raise typer.Exit(1)
    
    async def _discover():
        console.print(f"[cyan]🔍 Scanning local network for AI agents...[/] (timeout: {timeout}s)\n")
        
        agents: List = []
        
        def on_add(agent):
            if verbose:
                console.print(f"[green]➕ Found:[/] {agent.name}")
        
        def on_remove(agent):
            if verbose:
                console.print(f"[red]➖ Lost:[/] {agent.name}")
        
        discovery = MDNSServiceDiscovery()
        try:
            agents = await discovery.discover(timeout=timeout, on_add=on_add, on_remove=on_remove)
        finally:
            await discovery.close()
        
        return agents
    
    agents = asyncio.run(_discover())
    
    if not agents:
        console.print(Panel.fit(
            "[yellow]No AI agents found on local network[/]\n\n"
            "[white]Tips:[/]\n"
            "  • Make sure other agents are on the same WiFi/network\n"
            "  • Agents must be started with: oe a2a serve\n"
            "  • Try increasing timeout: --timeout 10",
            border_style="yellow"
        ))
        return
    
    # Display results
    table = Table(title=f"🔍 {len(agents)} AI Agent(s) on Local Network")
    table.add_column("Agent", style="cyan", min_width=20)
    table.add_column("Endpoint", style="green")
    table.add_column("Capabilities", style="magenta")
    
    for agent in agents:
        caps = ", ".join(agent.capabilities) or "-"
        table.add_row(
            agent.agent_id,
            agent.a2a_endpoint,
            caps
        )
    
    console.print(table)
    console.print(f"\n[dim]To connect: oe a2a send {agents[0].a2a_endpoint} \"hello\"[/]")


@a2a_app.command("local-register")
def local_register(
    agent_id: str = typer.Option(..., "--agent-id", "-i", help="Unique agent ID"),
    port: int = typer.Option(8000, "--port", "-p"),
    capabilities: Optional[str] = typer.Option(None, "--capabilities", "-c"),
):
    """Register this agent on local network via mDNS (without starting server)."""
    console = Console()
    
    if not ZEROCO_AVAILABLE:
        console.print("[red]zeroconf not installed. Run: pip install zeroconf[/]")
        raise typer.Exit(1)
    
    async def _register():
        caps = [c.strip() for c in capabilities.split(",") if c.strip()] if capabilities else []
        
        discovery = MDNSServiceDiscovery()
        await discovery.register(
            agent_id=agent_id,
            port=port,
            capabilities=caps
        )
        
        console.print(Panel.fit(
            f"[green]✅ Agent registered on local network[/]\n\n"
            f"Agent ID: {agent_id}\n"
            f"Port: {port}\n"
            f"Capabilities: {', '.join(caps) or 'None'}\n\n"
            f"[dim]Other agents on same WiFi can now discover you.[/]\n"
            f"[dim]Press Ctrl+C to unregister[/]",
            title="📡 mDNS Registration",
            border_style="green"
        ))
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await discovery.close()
            console.print("[dim]Unregistered[/]")
    
    asyncio.run(_register())
