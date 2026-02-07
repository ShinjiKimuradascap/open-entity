---
name: browser-tools
description: Playwright-based browser automation tools for web page interaction, clicking, scrolling, screenshots, form filling, and navigation. Use when the user asks to open a URL, scrape a page, take a screenshot, click elements, fill forms, or interact with web elements.
disable-model-invocation: false
user-invocable: true
allowed-tools: browser_open, browser_attach, browser_snapshot, browser_click, browser_fill, browser_type, browser_press, browser_hover, browser_select, browser_get_text, browser_get_value, browser_get_url, browser_get_title, browser_is_visible, browser_is_enabled, browser_wait, browser_screenshot, browser_scroll, browser_back, browser_forward, browser_reload, browser_eval, browser_close, browser_console, browser_errors, browser_tab, browser_set_viewport, browser_set_device
version: 1.0.0
tools:
  browser_open:
    description: Open URL in browser
  browser_attach:
    description: Attach to existing browser (remote debugging mode)
  browser_snapshot:
    description: Get accessibility snapshot of page
  browser_click:
    description: Click element by selector
  browser_fill:
    description: Clear input field and type text
  browser_type:
    description: Type text into element (preserving existing text)
  browser_press:
    description: Press keyboard key
  browser_hover:
    description: Hover mouse over element
  browser_select:
    description: Select option from dropdown
  browser_get_text:
    description: Get text content of element
  browser_get_value:
    description: Get value of input element
  browser_get_url:
    description: Get current page URL
  browser_get_title:
    description: Get current page title
  browser_is_visible:
    description: Check if element is visible
  browser_is_enabled:
    description: Check if element is enabled
  browser_wait:
    description: Wait for element or specified milliseconds
  browser_screenshot:
    description: Take screenshot of page
  browser_scroll:
    description: Scroll page
  browser_back:
    description: Navigate back
  browser_forward:
    description: Navigate forward
  browser_reload:
    description: Reload page
  browser_eval:
    description: Execute JavaScript on page
  browser_close:
    description: Close browser
  browser_console:
    description: Get browser console logs
  browser_errors:
    description: Get page errors
  browser_tab:
    description: Manage browser tabs
  browser_set_viewport:
    description: Set viewport size
  browser_set_device:
    description: Emulate device
---

# Browser Tools

Playwright-based browser automation for web interaction.
Use these tools for web scraping, form filling, screenshots, and page interaction.
