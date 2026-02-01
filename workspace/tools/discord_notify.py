#!/usr/bin/env python3
"""
Discord notification tool.

Usage:
    python discord_notify.py <channel_id> <message>
    python discord_notify.py 123456789 "Hello Discord!"
    python discord_notify.py 123456789 --embed --title "Alert" --description "System notification"
    python discord_notify.py --dm 987654321 "Private message"

Environment Variables:
    DISCORD_BOT_TOKEN: Discord Bot Token
"""

import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.discord import DiscordClient, DiscordError


def main():
    parser = argparse.ArgumentParser(
        description='Send Discord notifications',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send simple message
  python discord_notify.py 123456789 "Hello everyone!"
  
  # Send embed message
  python discord_notify.py 123456789 --embed --title "System Alert" --description "Server load high"
  
  # Send DM
  python discord_notify.py --dm 987654321 "Private notification"
  
  # Send webhook
  python discord_notify.py --webhook https://discord.com/api/webhooks/... --title "Webhook Alert"
        """
    )
    
    # Target options
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument('channel_id', nargs='?', help='Discord channel ID')
    target_group.add_argument('--dm', '-d', help='Send DM to user ID')
    target_group.add_argument('--webhook', '-w', help='Webhook URL')
    
    # Message options
    parser.add_argument('message', nargs='?', help='Message content')
    parser.add_argument('--embed', '-e', action='store_true', help='Send as embed')
    parser.add_argument('--title', '-t', help='Embed title')
    parser.add_argument('--description', '-D', help='Embed description')
    parser.add_argument('--color', '-c', type=int, default=0x3498db, help='Embed color (hex)')
    parser.add_argument('--field', '-f', action='append', nargs=2, metavar=('NAME', 'VALUE'),
                       help='Add embed field (can be used multiple times)')
    parser.add_argument('--footer', help='Embed footer text')
    
    # Bot options
    parser.add_argument('--username', help='Override bot username (webhook only)')
    parser.add_argument('--avatar', help='Override bot avatar URL (webhook only)')
    
    # Action options
    parser.add_argument('--dry-run', '-n', action='store_true', help='Validate without sending')
    parser.add_argument('--delete', help='Delete message by ID')
    parser.add_argument('--list', type=int, metavar='LIMIT', help='List recent messages')
    
    args = parser.parse_args()
    
    try:
        # Initialize client
        client = DiscordClient()
        
        # Handle webhook
        if args.webhook:
            if args.dry_run:
                print(f"[DRY RUN] Would send webhook to: {args.webhook[:50]}...")
                return 0
            
            embeds = None
            if args.embed or args.title:
                embed = {
                    'title': args.title or 'Notification',
                    'description': args.description or args.message or '',
                    'color': args.color
                }
                if args.footer:
                    embed['footer'] = {'text': args.footer}
                if args.field:
                    embed['fields'] = [
                        {'name': name, 'value': value, 'inline': False}
                        for name, value in args.field
                    ]
                embeds = [embed]
            
            result = client.send_webhook(
                webhook_url=args.webhook,
                content=None if embeds else (args.message or args.description),
                username=args.username,
                avatar_url=args.avatar,
                embeds=embeds
            )
            
            print(f"Webhook sent successfully!")
            return 0
        
        # Handle DM
        if args.dm:
            if args.dry_run:
                print(f"[DRY RUN] Would send DM to user: {args.dm}")
                print(f"Message: {args.message or args.description}")
                return 0
            
            if args.embed or args.title:
                result = client.send_dm_embed(
                    user_id=args.dm,
                    title=args.title or 'Notification',
                    description=args.description or args.message or '',
                    color=args.color,
                    fields=[
                        {'name': name, 'value': value, 'inline': False}
                        for name, value in (args.field or [])
                    ],
                    footer=args.footer
                )
            else:
                if not args.message:
                    print("Error: Message content required", file=sys.stderr)
                    return 1
                result = client.send_direct_message(args.dm, args.message)
            
            print(f"DM sent successfully!")
            print(f"  Message ID: {result.get('id')}")
            return 0
        
        # Handle channel operations
        channel_id = args.channel_id
        
        # List messages
        if args.list:
            messages = client.get_messages(channel_id, limit=args.list)
            print(f"Recent messages in channel {channel_id}:")
            for msg in messages:
                author = msg.get('author', {}).get('username', 'Unknown')
                content = msg.get('content', '')[:50]
                print(f"  [{msg['id']}] {author}: {content}...")
            return 0
        
        # Delete message
        if args.delete:
            if args.dry_run:
                print(f"[DRY RUN] Would delete message {args.delete}")
                return 0
            
            client.delete_message(channel_id, args.delete)
            print(f"Message {args.delete} deleted")
            return 0
        
        # Send message
        if args.dry_run:
            print(f"[DRY RUN] Would send to channel: {channel_id}")
            if args.embed or args.title:
                print(f"Embed title: {args.title or 'Notification'}")
                print(f"Description: {args.description or args.message}")
            else:
                print(f"Message: {args.message}")
            return 0
        
        if args.embed or args.title:
            # Send embed
            fields = [
                {'name': name, 'value': value, 'inline': False}
                for name, value in (args.field or [])
            ]
            
            result = client.send_embed(
                channel_id=channel_id,
                title=args.title or 'Notification',
                description=args.description or args.message or '',
                color=args.color,
                fields=fields if fields else None,
                footer=args.footer
            )
        else:
            # Send plain message
            if not args.message:
                print("Error: Message content required", file=sys.stderr)
                return 1
            
            result = client.send_message(channel_id, args.message)
        
        print(f"Message sent successfully!")
        print(f"  Message ID: {result.get('id')}")
        print(f"  Channel: {result.get('channel_id')}")
        
        return 0
        
    except DiscordError as e:
        print(f"Discord Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
