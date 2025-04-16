#!/usr/bin/env python3

import os
import json
import requests
import time
from src.modules.utils.validators import extract_domain
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def run_mozilla_observatory(target, output_dir, dry_run=False):
    """Run Mozilla Observatory scan for web security analysis"""
    logger.info("Running Mozilla Observatory scan for web security analysis")
    
    domain = extract_domain(target)
    output_file = os.path.join(output_dir, 'mozilla_observatory.json')
    
    if dry_run:
        logger.info(f"[DRY RUN] Would request Mozilla Observatory scan for {domain}")
        logger.info(f"[DRY RUN] Would poll API until scan completes")
        logger.info(f"[DRY RUN] Would save results to {output_file}")
        return {
            "dry_run": True,
            "target": domain,
            "api": "Mozilla Observatory",
            "output_file": output_file
        }
    
    try:
        # Start a new scan
        api_url = f"https://http-observatory.security.mozilla.org/api/v1/analyze?host={domain}&rescan=on"
        
        response = requests.post(api_url)
        data = response.json()
        
        if 'error' in data:
            logger.error(f"Mozilla Observatory error: {data['error']}")
            return None
        
        scan_id = data['scan_id']
        
        # Check scan status
        status_url = f"https://http-observatory.security.mozilla.org/api/v1/analyze?host={domain}"
        
        while True:
            response = requests.get(status_url)
            data = response.json()
            
            if data.get('state') == 'FINISHED':
                break
            elif data.get('state') == 'FAILED':
                logger.error(f"Mozilla Observatory scan failed: {data.get('error', 'Unknown error')}")
                return None
            
            logger.info(f"Mozilla Observatory scan in progress. Waiting 10 seconds...")
            time.sleep(10)
        
        # Get the full results
        results_url = f"https://http-observatory.security.mozilla.org/api/v1/getScanResults?scan={scan_id}"
        response = requests.get(results_url)
        test_results = response.json()
        
        # Combine the results
        full_results = {
            'scan_info': data,
            'test_results': test_results
        }
        
        # Save the results
        with open(output_file, 'w') as f:
            json.dump(full_results, f, indent=4)
        
        logger.info(f"Mozilla Observatory scan completed. Results saved to {output_file}")
        
        return full_results
    except Exception as e:
        logger.error(f"Error with Mozilla Observatory scan: {str(e)}")
        return None
