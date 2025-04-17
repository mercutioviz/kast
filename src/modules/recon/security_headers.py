#!/usr/bin/env python3

import os
import json
import requests
from src.modules.utils.validators import normalize_url
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def run_securityheaders(target, output_dir, dry_run=False):
    """Run SecurityHeaders.io scan for HTTP security headers analysis"""
    logger.info("Running SecurityHeaders.io scan for HTTP security headers analysis")
    
    # Get API key from configuration
    from src.config.config_manager import get_config
    api_key = get_config().get_api_key('securityheaders')
    
    url = normalize_url(target)
    output_file = os.path.join(output_dir, 'securityheaders.json')
    
    # Base API URL
    api_url = f"https://securityheaders.com/?q={url}&followRedirects=on&hide=on&json=on"
    
    # Add API key if available
    if api_key:
        api_url += f"&apikey={api_key}"
        logger.info("Using SecurityHeaders.io API key")
    else:
        logger.warning("No SecurityHeaders.io API key found. Please use an API Key from https://securityheaders.com/api")
    
    if dry_run:
        logger.info(f"[DRY RUN] Would request SecurityHeaders.io analysis for {url}")
        logger.info(f"[DRY RUN] Would save results to {output_file}")
        return {
            "dry_run": True,
            "target": url,
            "api": "SecurityHeaders.io",
            "output_file": output_file,
            "using_api_key": bool(api_key)
        }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'
        }
        
        response = requests.get(api_url, headers=headers)
        
        # SecurityHeaders.io doesn't have a public API, so we need to parse the HTML response
        # This is a simplified approach - in a real scenario, you might need to handle this differently
        
        # For now, we'll just save the raw response and headers
        result = {
            'url': url,
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'content_length': len(response.text)
        }
        
        # Extract security headers
        security_headers = {
            'Strict-Transport-Security': response.headers.get('Strict-Transport-Security', 'Not Set'),
            'Content-Security-Policy': response.headers.get('Content-Security-Policy', 'Not Set'),
            'X-Frame-Options': response.headers.get('X-Frame-Options', 'Not Set'),
            'X-Content-Type-Options': response.headers.get('X-Content-Type-Options', 'Not Set'),
            'Referrer-Policy': response.headers.get('Referrer-Policy', 'Not Set'),
            'Permissions-Policy': response.headers.get('Permissions-Policy', 'Not Set'),
            'X-XSS-Protection': response.headers.get('X-XSS-Protection', 'Not Set')
        }
        
        result['security_headers'] = security_headers
        
        # Save the results
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=4)
        
        logger.info(f"SecurityHeaders.io scan completed. Results saved to {output_file}")
        
        return result
    except Exception as e:
        logger.error(f"Error with SecurityHeaders.io scan: {str(e)}")
        return None
