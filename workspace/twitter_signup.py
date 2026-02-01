#!/usr/bin/env python3
"""Twitter signup automation script"""

from playwright.sync_api import sync_playwright
import time

def signup_twitter():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Go to Twitter signup
        page.goto("https://twitter.com/i/flow/signup")
        time.sleep(3)
        
        # Take screenshot to see current state
        page.screenshot(path="twitter_signup_1.png")
        print("Screenshot saved: twitter_signup_1.png")
        
        # Print page content
        print("Page title:", page.title())
        print("\n=== Page Content ===")
        print(page.content()[:2000])
        
        browser.close()

if __name__ == "__main__":
    signup_twitter()
