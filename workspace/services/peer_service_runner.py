#!/usr/bin/env python3
"""
Peer Service Runner
Docker環境用のエントリポイント

Usage:
    python peer_service_runner.py --id entity-a --port 8001
"""

import argparse
import asyncio
import logging
import os
import sys

# パス設定
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from peer_service import PeerService, PeerServer, init_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(
        description='AI Peer Communication Service Runner'
    )
    parser.add_argument(
        '--id', '-i',
        type=str,
        default=os.getenv('ENTITY_ID', 'entity-default'),
        help='Entity ID (default: from ENTITY_ID env or entity-default)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=int(os.getenv('PORT', '8000')),
        help='Port number (default: from PORT env or 8000)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host address (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--api-server',
        type=str,
        default=os.getenv('API_SERVER_URL', 'http://localhost:8000'),
        help='API Server URL (default: from API_SERVER_URL env)'
    )
    return parser.parse_args()


async def main():
    """メイン実行関数"""
    args = parse_args()
    
    logger.info("=" * 60)
    logger.info("AI Peer Communication Service")
    logger.info("=" * 60)
    logger.info(f"Entity ID: {args.id}")
    logger.info(f"Port: {args.port}")
    logger.info(f"Host: {args.host}")
    logger.info(f"API Server: {args.api_server}")
    
    # サービス初期化
    try:
        service = init_service(
            entity_id=args.id,
            port=args.port,
            api_server_url=args.api_server
        )
        logger.info(f"Service initialized: {service.entity_id}")
        logger.info(f"Public key: {service.get_public_key_hex()[:32]}...")
    except Exception as e:
        logger.error(f"Failed to initialize service: {e}")
        sys.exit(1)
    
    # サーバー作成・起動
    try:
        server = PeerServer(service)
        logger.info(f"Starting server on {args.host}:{args.port}")
        await server.start(host=args.host, port=args.port)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
