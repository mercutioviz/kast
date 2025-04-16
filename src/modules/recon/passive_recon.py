#!/usr/bin/env python3

import os
import json
import subprocess
import requests
import time
import asyncio
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from pyppeteer import launch

from src.modules.utils.validators import normalize_url, extract_domain
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def run_whatweb(target, output_dir, dry_run=False):
    """Run WhatWeb for technology detection"""
    logger.info("Running WhatWeb for technology detection")
    
    output_file = os.path.join(output_dir, 'whatweb.json')
    
    command = [
        'whatweb', 
        '--no-errors',
        '-a', '3',  # Aggression level
        '-j',       # JSON output
        target
    ]
    
    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(command)} > {output_file}")
        return {
            "dry_run": True,
            "command": ' '.join(command),
            "output_file": output_file
        }
    
    try:
        subprocess.run(command, stdout=open(output_file, 'w'), stderr=subprocess.PIPE, check=True)
        
        logger.info(f"WhatWeb scan completed. Results saved to {output_file}")
        
        # Parse the results
        with open(output_file, 'r') as f:
            whatweb_data = json.load(f)
        
        return whatweb_data
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running WhatWeb: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error with WhatWeb: {str(e)}")
        return None

def run_theharvester(target, output_dir, dry_run=False):
    """Run theHarvester for email and subdomain enumeration"""
    logger.info("Running theHarvester for email and subdomain enumeration")
    
    domain = extract_domain(target)
    output_file = os.path.join(output_dir, 'theharvester.xml')
    
    command = [
        'theharvester',
        '-d', domain,
        '-b', 'all',
        '-f', output_file
    ]
    
    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(command)}")
        return {
            "dry_run": True,
            "command": ' '.join(command),
            "output_file": output_file
        }
    
    try:
        subprocess.run(command, stderr=subprocess.PIPE, check=True)
        
        logger.info(f"theHarvester scan completed. Results saved to {output_file}")
        
        # Parse the XML results and convert to JSON for easier processing
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(output_file)
            root = tree.getroot()
            
            results = {
                'emails': [],
                'hosts': [],
                'vhosts': []
            }
            
            # Extract emails
            for email in root.findall('.//email'):
                results['emails'].append(email.text)
            
            # Extract hosts
            for host in root.findall('.//host'):
                results['hosts'].append(host.text)
            
            # Extract virtual hosts
            for vhost in root.findall('.//vhost'):
                results['vhosts'].append(vhost.text)
            
            # Save parsed results
            parsed_output = os.path.join(output_dir, 'theharvester_parsed.json')
            with open(parsed_output, 'w') as f:
                json.dump(results, f, indent=4)
            
            logger.debug(f"Parsed theHarvester results saved to {parsed_output}")
            
            return results
        except Exception as e:
            logger.error(f"Error parsing theHarvester results: {str(e)}")
            return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running theHarvester: {e}")
        return None
