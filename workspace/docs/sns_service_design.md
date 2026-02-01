# SNS Service Design

## Overview

SNS automation service for AI Collaboration Platform. Enables AI agents to autonomously manage Twitter/X and Discord operations.

## Components

- SNSService: Main service class
- TwitterClient: Twitter API v2 wrapper  
- DiscordClient: Discord Bot API wrapper
- ScheduledPost: Scheduled post data model
- EngagementMetrics: Engagement analytics

## Rate Limits

Twitter: 300 posts per 3 hours per account
Discord: 5 requests per second

## Environment Variables

TWITTER_API_KEY
TWITTER_API_SECRET
TWITTER_ACCESS_TOKEN
TWITTER_ACCESS_SECRET
TWITTER_BEARER_TOKEN
DISCORD_BOT_TOKEN

## Files

Implementation: services/communication/sns_service.py
