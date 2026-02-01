#!/usr/bin/env python3
"""
SMS sending tool using Twilio.

Usage:
    python send_sms.py <to_number> <message>
    python send_sms.py +819012345678 "Hello from AI!"
    python send_sms.py 09012345678 "Test message" --from +815012345678

Environment Variables:
    TWILIO_ACCOUNT_SID: Twilio Account SID
    TWILIO_AUTH_TOKEN: Twilio Auth Token
    TWILIO_PHONE_NUMBER: Default sender phone number
"""

import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.twilio import TwilioClient, TwilioError


def main():
    parser = argparse.ArgumentParser(
        description='Send SMS using Twilio',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python send_sms.py +819012345678 "Hello!"
  python send_sms.py 09012345678 "Test" --from +815012345678
  python send_sms.py "+1 415 555 2671" "Hello from CLI"
        """
    )
    
    parser.add_argument('to', help='Destination phone number')
    parser.add_argument('message', help='Message text (max 1600 chars)')
    parser.add_argument(
        '--from', '-f',
        dest='from_number',
        help='Sender phone number (overrides default)'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Validate without sending'
    )
    parser.add_argument(
        '--format',
        action='store_true',
        help='Show formatted phone number and exit'
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize client
        client = TwilioClient()
        
        # Format phone number
        formatted_to = client.format_phone_number(args.to)
        
        if args.format:
            print(f"Original: {args.to}")
            print(f"Formatted: {formatted_to}")
            print(f"Valid E.164: {client.validate_e164(formatted_to)}")
            return 0
        
        # Validate
        if not client.validate_e164(formatted_to):
            print(f"Error: Invalid phone number format: {args.to}", file=sys.stderr)
            print(f"Formatted: {formatted_to}", file=sys.stderr)
            return 1
        
        if args.dry_run:
            print(f"[DRY RUN] Would send SMS to: {formatted_to}")
            print(f"Message: {args.message[:50]}...")
            return 0
        
        # Send SMS
        result = client.send_sms(
            to=formatted_to,
            body=args.message,
            from_number=args.from_number
        )
        
        print(f"SMS sent successfully!")
        print(f"  SID: {result.get('sid')}")
        print(f"  Status: {result.get('status')}")
        print(f"  To: {result.get('to')}")
        print(f"  From: {result.get('from')}")
        
        if result.get('error_code'):
            print(f"  Error Code: {result.get('error_code')}")
        
        return 0
        
    except TwilioError as e:
        print(f"Twilio Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
