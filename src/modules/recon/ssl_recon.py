#!/usr/bin/env python3

import os
import json
import subprocess
import requests
import time
from src.modules.utils.validators import extract_domain, normalize_url
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def run_sslscan(target, output_dir):
    """Run SSLScan for SSL/TLS configuration analysis"""
    logger.info("Running SSLScan for SSL/TLS configuration analysis")
    
    output_file = os.path.join(output_dir, 'sslscan.json')
    
    try:
        domain = extract_domain(target)
        
        subprocess.run([
            'sslscan',
            '--no-colour',
            '--json=' + output_file,
            domain
        ], stderr=subprocess.PIPE, check=True)
        
        logger.info(f"SSLScan completed. Results saved to {output_file}")
        
        # Parse the results
        with open(output_file, 'r') as f:
            sslscan_data = json.load(f)
        
        return sslscan_data
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running SSLScan: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error with SSLScan: {str(e)}")
        return None

def run_ssllabs(target, output_dir):
    """Run SSL Labs API scan for comprehensive SSL/TLS analysis"""
    logger.info("Running SSL Labs scan for comprehensive SSL/TLS analysis")
    
    domain = extract_domain(target)
    output_file = os.path.join(output_dir, 'ssllabs.json')
    
    try:
        # Start new scan
        start_new = 'on'
        api_url = f"https://api.ssllabs.com/api/v3/analyze?host={domain}&startNew={start_new}&all=done"
        
        response = requests.get(api_url)
        data = response.json()
        
        # Check if scan is in progress
        while data['status'] != 'READY' and data['status'] != 'ERROR':
            logger.info(f"SSL Labs scan in progress: {data['status']}. Waiting 30 seconds...")
            time.sleep(30)
            response = requests.get(f"https://api.ssllabs.com/api/v3/analyze?host={domain}")
            data = response.json()
        
        if data['status'] == 'ERROR':
            logger.error(f"SSL Labs scan error: {data.get('statusMessage', 'Unknown error')}")
            return None
        
        # Save the results
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=4)
        
        logger.info(f"SSL Labs scan completed. Results saved to {output_file}")
        
        return data
    except Exception as e:
        logger.error(f"Error with SSL Labs scan: {str(e)}")
        return None
