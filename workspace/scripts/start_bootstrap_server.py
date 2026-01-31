#!/usr/bin/env python3
"""
Bootstrap Server Startup Script
ブートストラップサーバー起動スクリプト

Usage:
    python scripts/start_bootstrap_server.py [--port PORT] [--host HOST]

L2 Phase 1: 分散型AIネットワークのブートストラップサーバー
"""

import argparse
import asyncio
import sys
import os

# Add services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))

from bootstrap_server import BootstrapServer


async def main():
    parser = argparse.ArgumentParser(
        description="AI Collaboration Network Bootstrap Server"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="Port to bind (default: 9000)"
    )
    parser.add_argument(
        "--cleanup-interval",
        type=int,
        default=300,
        help="Cleanup interval in seconds (default: 300)"
    )
    parser.add_argument(
        "--peer-timeout",
        type=int,
        default=1800,
        help="Peer timeout in seconds (default: 1800)"
    )
    parser.add_argument(
        "--max-peers",
        type=int,
        default=10000,
        help="Maximum peers (default: 10000)"
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print("AI Collaboration Network - Bootstrap Server")
    print("="*60)
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Cleanup Interval: {args.cleanup_interval}s")
    print(f"Peer Timeout: {args.peer_timeout}s")
    print(f"Max Peers: {args.max_peers}")
    print("="*60)
    print("Endpoints:")
    print(f"  POST http://{args.host}:{args.port}/register")
    print(f"  GET  http://{args.host}:{args.port}/discover")
    print(f"  GET  http://{args.host}:{args.port}/find/{{entity_id}}")
    print(f"  POST http://{args.host}:{args.port}/heartbeat/{{entity_id}}")
    print(f"  GET  http://{args.host}:{args.port}/stats")
    print(f"  GET  http://{args.host}:{args.port}/health")
    print("="*60)
    print("Press Ctrl+C to stop")
    print("="*60)
    
    server = BootstrapServer(
        host=args.host,
        port=args.port,
        cleanup_interval=args.cleanup_interval,
        peer_timeout=args.peer_timeout,
        max_peers=args.max_peers
    )
    
    try:
        await server.start()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        await server.stop()
        print("Server stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
