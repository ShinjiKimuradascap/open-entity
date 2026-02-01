const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    
    await page.goto('https://twitter.com/i/flow/signup');
    await page.waitForTimeout(3000);
    
    // Click "Create account"
    await page.click('text=Create account');
    await page.waitForTimeout(3000);
    
    // Click "Use email instead"
    await page.click('text=Use email instead');
    await page.waitForTimeout(2000);
    
    // Fill in Name - use placeholder or aria-label
    const nameInput = await page.$('input[autocomplete="name"], input[name="name"], input[placeholder*="Name"]');
    if (nameInput) {
        await nameInput.fill('Entity AI');
    }
    await page.waitForTimeout(500);
    
    // Fill in Email - use new email address
    const NEW_EMAIL = 'entity-ai-1769910973905@virgilian.com';
    const emailInput = await page.$('input[autocomplete="email"], input[name="email"], input[type="email"]');
    if (emailInput) {
        await emailInput.fill(NEW_EMAIL);
    }
    await page.waitForTimeout(500);
    
    // Select Date of Birth - use select elements
    const selects = await page.$$('select');
    if (selects.length >= 3) {
        await selects[0].selectOption('1'); // January
        await selects[1].selectOption('1'); // Day 1
        await selects[2].selectOption('1990'); // Year 1990
    }
    await page.waitForTimeout(500);
    
    await page.screenshot({ path: 'twitter_signup_4.png', fullPage: true });
    console.log('\nScreenshot saved: twitter_signup_4.png');
    
    // Click Next
    await page.click('text=Next');
    await page.waitForTimeout(5000);
    
    // Get page text to see current state
    const bodyText = await page.evaluate(() => document.body.innerText);
    console.log('\n=== Page Text (first 3000 chars) ===');
    console.log(bodyText.substring(0, 3000));
    
    await page.screenshot({ path: 'twitter_signup_5.png', fullPage: true });
    console.log('\nScreenshot saved: twitter_signup_5.png');
    
    // Check if there's a "Sign up" or "Create account" button
    const buttons = await page.$$('button');
    console.log('\n=== Buttons found:', buttons.length);
    for (let i = 0; i < buttons.length; i++) {
        const text = await buttons[i].innerText().catch(() => '');
        console.log(`Button ${i}:`, text);
    }
    
    await browser.close();
})();
