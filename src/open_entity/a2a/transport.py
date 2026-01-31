"""HTTP/WebSocket transport for A2A protocol."""
import asyncio
import aiohttp
from aiohttp import web
from typing import Optional, Callable
import json

from .protocol import A2AProtocol, A2AMessage


class HTTPTransport:
    """HTTP transport for A2A messaging."""
    
    def __init__(self, protocol: A2AProtocol, host: str = "0.0.0.0", port: int = 8000):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.app = web.Application()
        self.app.router.add_post("/a2a/message", self.handle_message)
        self.app.router.add_get("/a2a/identity", self.get_identity)
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
    
    async def handle_message(self, request: web.Request) -> web.Response:
        """Handle incoming A2A message."""
        try:
            body = await request.text()
            message = A2AMessage.from_json(body)
            
            response = await self.protocol.handle_message(message)
            
            if response:
                return web.Response(
                    text=response.to_json(),
                    content_type="application/json"
                )
            return web.Response(status=204)
        except Exception as e:
            return web.Response(
                status=400,
                text=json.dumps({"error": str(e)}),
                content_type="application/json"
            )
    
    async def get_identity(self, request: web.Request) -> web.Response:
        """Return agent identity."""
        return web.json_response(self.protocol.identity.to_dict())
    
    async def start(self):
        """Start HTTP server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
    
    async def stop(self):
        """Stop HTTP server."""
        if self.runner:
            await self.runner.cleanup()
    
    async def send_message(self, endpoint: str, message: A2AMessage) -> Optional[A2AMessage]:
        """Send message to remote agent."""
        url = f"{endpoint}/a2a/message"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    data=message.to_json(),
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        body = await response.text()
                        return A2AMessage.from_json(body)
                    elif response.status == 204:
                        return None
                    else:
                        raise Exception(f"HTTP {response.status}")
            except Exception as e:
                print(f"Failed to send message: {e}")
                return None
    
    async def discover_agent(self, endpoint: str) -> Optional[dict]:
        """Discover agent at endpoint."""
        url = f"{endpoint}/a2a/identity"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
            except Exception as e:
                print(f"Failed to discover agent: {e}")
                return None
