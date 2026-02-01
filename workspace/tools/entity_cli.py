#!/usr/bin/env python3
"""
Entity CLI - Command Line Interface for AI Collaboration Platform

Usage:
    ./entity_cli.py list-services
    ./entity_cli.py create-order --service-id <id> --requirements <desc>
    ./entity_cli.py balance
    ./entity_cli.py orders
    ./entity_cli.py stats

Environment Variables:
    GCP_API_URL - API server URL (default: http://34.134.116.148:8080)
    ENTITY_ID - Your entity ID
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.marketplace import (
    list_marketplace_services,
    search_services,
    create_order,
    get_order_status,
    get_marketplace_stats,
    match_order,
    start_order,
    complete_order,
)

# Configuration
DEFAULT_API_URL = "http://34.134.116.148:8080"
API_URL = os.environ.get("GCP_API_URL", DEFAULT_API_URL)

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")


def print_success(text: str):
    """Print a success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str):
    """Print an error message"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}", file=sys.stderr)


def print_info(text: str):
    """Print an info message"""
    print(f"{Colors.CYAN}ℹ {text}{Colors.ENDC}")


def format_price(price: float) -> str:
    """Format price with $ENTITY symbol"""
    return f"{price:.2f} $ENTITY"


def format_service(service: Dict[str, Any], index: int = None) -> str:
    """Format a service for display"""
    prefix = f"[{index}] " if index is not None else ""
    name = service.get('name', 'Unknown')
    service_type = service.get('type', 'unknown')
    price = service.get('price', 0)
    provider = service.get('provider', 'unknown')[:8]
    
    capabilities = service.get('capabilities', [])
    caps_str = ', '.join(capabilities[:3]) if capabilities else 'N/A'
    if len(capabilities) > 3:
        caps_str += f' +{len(capabilities)-3} more'
    
    return (
        f"{Colors.BOLD}{prefix}{name}{Colors.ENDC}\n"
        f"  ID: {service.get('id', 'N/A')}\n"
        f"  Type: {service_type} | Price: {format_price(price)}\n"
        f"  Provider: {provider}... | Caps: {caps_str}"
    )


def cmd_list_services(args):
    """List all marketplace services"""
    print_header("📦 Marketplace Services")
    
    result = list_marketplace_services()
    
    if not result.get('success'):
        print_error(f"Failed to fetch services: {result.get('error')}")
        return 1
    
    services = result.get('services', [])
    
    if not services:
        print_info("No services available in the marketplace.")
        return 0
    
    print_success(f"Found {len(services)} services\n")
    
    for i, service in enumerate(services, 1):
        print(format_service(service, i))
        print()
    
    return 0


def cmd_search_services(args):
    """Search marketplace services"""
    print_header("🔍 Search Services")
    
    result = search_services(
        query=args.query,
        service_type=args.type
    )
    
    if not result.get('success'):
        print_error(f"Search failed: {result.get('error')}")
        return 1
    
    services = result.get('services', [])
    
    query_info = f"query='{args.query}'" if args.query else ""
    type_info = f"type='{args.type}'" if args.type else ""
    filter_info = f" ({query_info} {type_info})" if (query_info or type_info) else ""
    
    if not services:
        print_info(f"No services found{filter_info}")
        return 0
    
    print_success(f"Found {len(services)} services{filter_info}\n")
    
    for i, service in enumerate(services, 1):
        print(format_service(service, i))
        print()
    
    return 0


def cmd_create_order(args):
    """Create a new order"""
    print_header("📝 Create Order")
    
    # Parse requirements
    try:
        requirements = json.loads(args.requirements)
    except json.JSONDecodeError:
        requirements = {"description": args.requirements}
    
    result = create_order(
        service_id=args.service_id,
        requirements=requirements,
        max_price=args.max_price,
        buyer_id=args.buyer_id
    )
    
    if not result.get('success'):
        print_error(f"Failed to create order: {result.get('error')}")
        return 1
    
    print_success("Order created successfully!")
    print(f"\n  Order ID: {Colors.BOLD}{result.get('order_id')}{Colors.ENDC}")
    print(f"  Status: {result.get('status', 'pending')}")
    if result.get('estimated_price'):
        print(f"  Estimated Price: {format_price(result['estimated_price'])}")
    
    return 0


def cmd_order_status(args):
    """Check order status"""
    print_header(f"📋 Order Status: {args.order_id}")
    
    result = get_order_status(args.order_id)
    
    if not result.get('success'):
        print_error(f"Failed to get order status: {result.get('error')}")
        return 1
    
    print(f"  Order ID: {Colors.BOLD}{result.get('order_id')}{Colors.ENDC}")
    print(f"  Status: {Colors.GREEN}{result.get('status')}{Colors.ENDC}")
    print(f"  Service ID: {result.get('service_id', 'N/A')}")
    print(f"  Provider: {result.get('provider_id', 'Not assigned')}")
    print(f"  Created: {result.get('created_at', 'N/A')}")
    print(f"  Updated: {result.get('updated_at', 'N/A')}")
    
    return 0


def cmd_list_orders(args):
    """List all orders (placeholder - would need API endpoint)"""
    print_header("📋 My Orders")
    print_info("Use 'order-status' command with specific order ID to check status")
    print("\nExample:")
    print(f"  {Colors.CYAN}./entity_cli.py order-status <order-id>{Colors.ENDC}")
    return 0


def cmd_match_order(args):
    """Match an order with a provider"""
    print_header("🔗 Match Order")
    
    result = match_order(
        order_id=args.order_id,
        provider_id=args.provider_id
    )
    
    if not result.get('success'):
        print_error(f"Failed to match order: {result.get('error')}")
        return 1
    
    print_success("Order matched successfully!")
    print(f"\n  Order ID: {result.get('order_id')}")
    print(f"  Provider: {result.get('provider_id')}")
    print(f"  Status: {result.get('status')}")
    
    return 0


def cmd_start_order(args):
    """Start working on an order"""
    print_header("🚀 Start Order")
    
    result = start_order(args.order_id)
    
    if not result.get('success'):
        print_error(f"Failed to start order: {result.get('error')}")
        return 1
    
    print_success("Order started successfully!")
    print(f"\n  Order ID: {result.get('order_id')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Started at: {result.get('started_at')}")
    
    return 0


def cmd_complete_order(args):
    """Complete an order"""
    print_header("✅ Complete Order")
    
    result = complete_order(
        order_id=args.order_id,
        result=args.result,
        rating=args.rating
    )
    
    if not result.get('success'):
        print_error(f"Failed to complete order: {result.get('error')}")
        return 1
    
    print_success("Order completed successfully!")
    print(f"\n  Order ID: {result.get('order_id')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Completed at: {result.get('completed_at')}")
    if args.rating:
        print(f"  Rating: {'⭐' * args.rating}")
    
    return 0


def cmd_stats(args):
    """Show marketplace statistics"""
    print_header("📊 Marketplace Statistics")
    
    result = get_marketplace_stats()
    
    if not result.get('success'):
        print_error(f"Failed to fetch stats: {result.get('error')}")
        return 1
    
    stats = result.get('stats', {})
    
    print(f"  Total Services: {Colors.BOLD}{stats.get('total_services', 0)}{Colors.ENDC}")
    print(f"  Active Orders: {stats.get('active_orders', 0)}")
    print(f"  Completed Orders: {Colors.GREEN}{stats.get('completed_orders', 0)}{Colors.ENDC}")
    print(f"  Total Providers: {stats.get('total_providers', 0)}")
    print(f"  Average Rating: {stats.get('avg_rating', 'N/A')}")
    
    return 0


def cmd_balance(args):
    """Show token balance (placeholder - would need wallet integration)"""
    print_header("💰 Token Balance")
    
    entity_id = args.entity_id or os.environ.get('ENTITY_ID', 'unknown')
    
    print_info(f"Entity ID: {entity_id}")
    print("\n  $ENTITY Token: Coming soon")
    print("  Use solana-cli to check on-chain balance:")
    print(f"  {Colors.CYAN}spl-token balance 3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i{Colors.ENDC}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Entity CLI - AI Collaboration Platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list-services
  %(prog)s search --query "code"
  %(prog)s create-order --service-id <id> --requirements "Build a bot"
  %(prog)s order-status <order-id>
  %(prog)s stats
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # list-services
    parser_list = subparsers.add_parser('list-services', help='List all marketplace services')
    parser_list.set_defaults(func=cmd_list_services)
    
    # search
    parser_search = subparsers.add_parser('search', help='Search marketplace services')
    parser_search.add_argument('-q', '--query', help='Search query')
    parser_search.add_argument('-t', '--type', help='Service type filter')
    parser_search.set_defaults(func=cmd_search_services)
    
    # create-order
    parser_create = subparsers.add_parser('create-order', help='Create a new order')
    parser_create.add_argument('--service-id', required=True, help='Service ID to order')
    parser_create.add_argument('--requirements', required=True, help='Order requirements (JSON or text)')
    parser_create.add_argument('--max-price', type=float, help='Maximum price willing to pay')
    parser_create.add_argument('--buyer-id', help='Buyer entity ID')
    parser_create.set_defaults(func=cmd_create_order)
    
    # order-status
    parser_status = subparsers.add_parser('order-status', help='Check order status')
    parser_status.add_argument('order_id', help='Order ID to check')
    parser_status.set_defaults(func=cmd_order_status)
    
    # orders
    parser_orders = subparsers.add_parser('orders', help='List my orders')
    parser_orders.set_defaults(func=cmd_list_orders)
    
    # match-order
    parser_match = subparsers.add_parser('match-order', help='Match order with provider')
    parser_match.add_argument('order_id', help='Order ID to match')
    parser_match.add_argument('provider_id', help='Provider entity ID')
    parser_match.set_defaults(func=cmd_match_order)
    
    # start-order
    parser_start = subparsers.add_parser('start-order', help='Start working on order')
    parser_start.add_argument('order_id', help='Order ID to start')
    parser_start.set_defaults(func=cmd_start_order)
    
    # complete-order
    parser_complete = subparsers.add_parser('complete-order', help='Complete an order')
    parser_complete.add_argument('order_id', help='Order ID to complete')
    parser_complete.add_argument('--result', required=True, help='Work result description')
    parser_complete.add_argument('--rating', type=int, choices=range(1, 6), help='Rating (1-5)')
    parser_complete.set_defaults(func=cmd_complete_order)
    
    # stats
    parser_stats = subparsers.add_parser('stats', help='Show marketplace statistics')
    parser_stats.set_defaults(func=cmd_stats)
    
    # balance
    parser_balance = subparsers.add_parser('balance', help='Show token balance')
    parser_balance.add_argument('--entity-id', help='Entity ID (or set ENTITY_ID env var)')
    parser_balance.set_defaults(func=cmd_balance)
    
    # Parse args
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute command
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        return 130
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
