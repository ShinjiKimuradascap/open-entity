#!/usr/bin/env python3
"""
Auto Promotion Script for $ENTITY
Posts periodic updates to Discord/Twitter
"""
import os
import sys
import random
from datetime import datetime

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Promotion messages
MESSAGES = [
    "🚀 $ENTITY - AI Collaboration Platform is LIVE! Autonomous AI agents trading services 24/7. #AI #Crypto",
    "🔧 Our L0 deployment is complete! API Server + Entity A/B running smoothly. $ENTITY economy starting!",
    "🌐 Join the AI revolution! $ENTITY enables AI-to-AI transactions. Be part of the future!",
    "💡 Did you know? $ENTITY uses X25519/AES-256-GCM encryption for secure AI communication!",
    "🤖 AI agents working together autonomously. This is the future $ENTITY is building!",
]

def get_daily_message():
    """Get message of the day based on date"""
    day_of_year = datetime.now().timetuple().tm_yday
    return MESSAGES[day_of_year % len(MESSAGES)]

def post_to_discord(message: str, channel_id: str = None, bot_token: str = None):
    """Post message to Discord channel"""
    import requests
    
    token = bot_token or os.getenv('DISCORD_BOT_TOKEN')
    channel = channel_id or os.getenv('DISCORD_CHANNEL_ID')
    
    if not token or not channel:
        print("Error: DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID not set")
        return False
    
    url = f"https://discord.com/api/v10/channels/{channel}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }
    data = {"content": message}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 200
    except Exception as e:
        print(f"Error posting to Discord: {e}")
        return False

def main():
    """Main function"""
    print(f"[{datetime.now()}] Auto Promotion Starting...")
    
    message = get_daily_message()
    print(f"Message: {message}")
    
    # Try to post to Discord if configured
    if os.getenv('DISCORD_BOT_TOKEN'):
        success = post_to_discord(message)
        print(f"Discord post: {'Success' if success else 'Failed'}")
    else:
        print("Discord not configured. Set DISCORD_BOT_TOKEN env var.")
        print("Message ready to send:")
        print(f"  {message}")
    
    print(f"[{datetime.now()}] Done!")

if __name__ == '__main__':
    main()
