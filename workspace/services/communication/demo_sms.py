#!/usr/bin/env python3
"""Demo script for SMS Service"""

import asyncio
import sys
sys.path.insert(0, '/home/moco/workspace')

from sms_service import SMSService, PhoneNumber, SMSMessage

async def main():
    # Initialize service (demo mode - no real Twilio API calls)
    service = SMSService()
    await service.initialize()
    
    # Buy a phone number
    print("Buying phone number...")
    number = await service.buy_phone_number(area_code="415")
    print(f"  Purchased: {number.phone_number}")
    
    # Send SMS
    print("Sending SMS...")
    msg = await service.send_sms(
        from_number=number.phone_number,
        to_number="+1234567890",
        message="Hello from AI!"
    )
    print(f"  Sent: {msg.id} (status: {msg.status})")
    
    # Create template
    print("Creating template...")
    template = service.create_template(
        name="welcome",
        content="Welcome {name}! Your code is {code}.",
        description="Welcome message with verification code"
    )
    print(f"  Created: {template.name}")
    
    # Send with template
    print("Sending SMS with template...")
    msg2 = await service.send_sms(
        from_number=number.phone_number,
        to_number="+1234567890",
        message="",
        template="welcome"  # Would need to pass variables in real usage
    )
    
    # Get stats
    print("Getting stats...")
    stats = service.get_stats()
    print(f"  Messages: {stats['messages']}")
    print(f"  Phone numbers: {stats['phone_numbers']}")
    print(f"  Demo mode: {stats['demo_mode']}")
    
    print("\n✓ Demo completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
