#!/usr/bin/env python3
"""
Voice call tool using Twilio.

Usage:
    python make_call.py <to_number> <message>
    python make_call.py +819012345678 "Hello, this is a test call"
    python make_call.py 09012345678 --twiml-url https://example.com/twiml

Environment Variables:
    TWILIO_ACCOUNT_SID: Twilio Account SID
    TWILIO_AUTH_TOKEN: Twilio Auth Token
    TWILIO_PHONE_NUMBER: Default caller ID
"""

import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.twilio import TwilioClient, TwilioError


def main():
    parser = argparse.ArgumentParser(
        description='Make voice call using Twilio',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python make_call.py +819012345678 "Hello, this is a notification call"
  python make_call.py 09012345678 --message "日本語のメッセージ"
  python make_call.py +14155552671 --twiml-url https://example.com/voice
  python make_call.py +819012345678 --voice Polly.Takumi --language ja-JP
        """
    )
    
    parser.add_argument('to', help='Destination phone number')
    parser.add_argument(
        'message',
        nargs='?',
        help='Message to speak (uses Say verb)'
    )
    parser.add_argument(
        '--from', '-f',
        dest='from_number',
        help='Caller ID (overrides default)'
    )
    parser.add_argument(
        '--twiml-url', '-u',
        help='URL to fetch TwiML (alternative to message)'
    )
    parser.add_argument(
        '--twiml', '-t',
        help='Raw TwiML XML string'
    )
    parser.add_argument(
        '--language', '-l',
        default='ja-JP',
        help='Voice language (default: ja-JP)'
    )
    parser.add_argument(
        '--voice', '-v',
        default='Polly.Mizuki',
        help='Voice type (default: Polly.Mizuki)'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Validate without making call'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Get call status by SID'
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize client
        client = TwilioClient()
        
        # Check for status query
        if args.status:
            result = client.get_call_status(args.to)
            print(f"Call Status:")
            print(f"  SID: {result.get('sid')}")
            print(f"  Status: {result.get('status')}")
            print(f"  To: {result.get('to')}")
            print(f"  From: {result.get('from')}")
            print(f"  Duration: {result.get('duration')}s")
            return 0
        
        # Format phone number
        formatted_to = client.format_phone_number(args.to)
        
        if not client.validate_e164(formatted_to):
            print(f"Error: Invalid phone number format: {args.to}", file=sys.stderr)
            return 1
        
        # Determine TwiML source
        twiml = None
        url = None
        
        if args.twiml:
            twiml = args.twiml
        elif args.twiml_url:
            url = args.twiml_url
        elif args.message:
            # Will be converted to Say verb by client
            twiml = args.message
        else:
            print("Error: Provide message, --twiml, or --twiml-url", file=sys.stderr)
            return 1
        
        if args.dry_run:
            print(f"[DRY RUN] Would call: {formatted_to}")
            if twiml:
                print(f"Message: {twiml[:50]}...")
            if url:
                print(f"TwiML URL: {url}")
            print(f"Language: {args.language}")
            print(f"Voice: {args.voice}")
            return 0
        
        # Make call
        result = client.make_call(
            to=formatted_to,
            twiml=twiml,
            url=url,
            from_number=args.from_number,
            language=args.language,
            voice=args.voice
        )
        
        print(f"Call initiated!")
        print(f"  SID: {result.get('sid')}")
        print(f"  Status: {result.get('status')}")
        print(f"  To: {result.get('to')}")
        print(f"  From: {result.get('from')}")
        print(f"  Direction: {result.get('direction')}")
        
        return 0
        
    except TwilioError as e:
        print(f"Twilio Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
