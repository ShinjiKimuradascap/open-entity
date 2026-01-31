"""A2A (AI-to-AI) communication commands."""
import asyncio
import typer
from rich.console import Console
from rich.table import Table
from typing import Optional

from ..a2a.protocol import A2AProtocol, AgentIdentity, MessageType
from ..a2a.transport import HTTPTransport

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
):
    """Start A2A server to receive messages."""
    console = Console()
    
    async def _serve():
        identity = AgentIdentity(
            agent_id=f"agent_{port}",
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
        console.print(f"[green]A2A server started at http://{host}:{port}[/]")
        console.print("[dim]Press Ctrl+C to stop[/]")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
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
