#!/usr/bin/env python3

import os
import json
import asyncio
from pyppeteer import launch
from src.modules.utils.validators import normalize_url
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

async def run_browser_recon(target, output_dir, dry_run=False):
    """Run browser-based reconnaissance"""
    logger.info("Launching headless browser for JavaScript analysis")
    
    url = normalize_url(target)
    output_file = os.path.join(output_dir, 'browser_recon.json')
    screenshot_path = os.path.join(output_dir, 'screenshot.png')
    
    if dry_run:
        logger.info(f"[DRY RUN] Would launch headless browser for {url}")
        logger.info(f"[DRY RUN] Would extract JS files, forms, links, cookies")
        logger.info(f"[DRY RUN] Would take screenshot and save to {screenshot_path}")
        logger.info(f"[DRY RUN] Would save browser recon data to {output_file}")
        return {
            "dry_run": True,
            "target": url,
            "tool": "Browser Reconnaissance",
            "actions": [
                "Extract JavaScript files",
                "Extract form information",
                "Extract links",
                "Take screenshot",
                "Get cookies",
                "Get local/session storage",
                "Detect frameworks"
            ],
            "output_file": output_file,
            "screenshot": screenshot_path
        }
    
    browser = await launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
    page = await browser.newPage()
    
    # Set user agent to avoid detection
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36')
    
    try:
        await page.goto(url, {'waitUntil': 'networkidle0', 'timeout': 60000})
        
        # Extract JavaScript files
        js_files = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('script[src]')).map(script => script.src);
        }''')
        
        # Extract form information
        forms = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('form')).map(form => {
                return {
                    action: form.action,
                    method: form.method,
                    inputs: Array.from(form.querySelectorAll('input')).map(input => {
                        return {
                            name: input.name,
                            type: input.type,
                            id: input.id
                        };
                    })
                };
            });
        }''')
        
        # Extract links
        links = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('a[href]')).map(a => a.href);
        }''')
        
        # Take screenshot
        await page.screenshot({'path': screenshot_path, 'fullPage': True})
        
        # Get cookies
        cookies = await page.cookies()
        
        # Get local storage
        local_storage = await page.evaluate('() => Object.entries(localStorage)')
        
        # Get session storage
        session_storage = await page.evaluate('() => Object.entries(sessionStorage)')
        
        # Check for common web frameworks
        frameworks = await page.evaluate('''() => {
            const frameworks = [];
            
            // Check for React
            if (window.React || document.querySelector('[data-reactroot]')) {
                frameworks.push('React');
            }
            
            // Check for Angular
            if (window.angular || document.querySelector('[ng-app]')) {
                frameworks.push('Angular');
            }
            
            // Check for Vue
            if (window.__VUE__ || document.querySelector('[data-v-]')) {
                frameworks.push('Vue');
            }

            // Check for jQuery
            if (window.jQuery || window.$) {
                frameworks.push('jQuery');
            }
            
            return frameworks;
        }''')
        
        browser_data = {
            'js_files': js_files,
            'forms': forms,
            'links': links,
            'cookies': cookies,
            'local_storage': local_storage,
            'session_storage': session_storage,
            'frameworks': frameworks,
            'screenshot': screenshot_path
        }
        
        # Save browser data
        with open(output_file, 'w') as f:
            json.dump(browser_data, f, indent=4)
            
        logger.info(f"Browser reconnaissance completed. Screenshot saved to {screenshot_path}")
        return browser_data
        
    except Exception as e:
        logger.error(f"Error during browser reconnaissance: {str(e)}")
        return None
    finally:
        await browser.close()

def browser_recon(target, output_dir, dry_run=False):
    """Wrapper function to run browser recon in asyncio event loop"""
    try:
        if dry_run:
            return asyncio.get_event_loop().run_until_complete(run_browser_recon(target, output_dir, dry_run=True))
        else:
            return asyncio.get_event_loop().run_until_complete(run_browser_recon(target, output_dir))
    except Exception as e:
        logger.error(f"Error setting up browser reconnaissance: {str(e)}")
        return None
