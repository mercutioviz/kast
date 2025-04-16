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
    
    from src.modules.utils.json_utils import load_json_file
    
    output_file = os.path.join(output_dir, 'whatweb.json')
    
    command = [
        'whatweb', 
        '--no-errors',
        '-a', '3',  # Aggression level
        f'--log-json={output_file}',  # Direct JSON output to file
        target
    ]
    
    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(command)}")
        return {
            "dry_run": True,
            "command": ' '.join(command),
            "output_file": output_file
        }
    
    try:
        # Run the command
        subprocess.run(command, stderr=subprocess.PIPE, check=True)
        
        # Check if the output file was created
        if not os.path.exists(output_file):
            logger.error(f"WhatWeb did not create the output file: {output_file}")
            return None
        
        # Load and parse the JSON file with robust error handling
        whatweb_data = load_json_file(output_file)
        
        if whatweb_data:
            logger.info(f"WhatWeb scan completed. Results saved to {output_file}")
            return whatweb_data
        else:
            logger.error("Failed to parse WhatWeb output")
            return None
            
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
    json_output_file = os.path.join(output_dir, 'theharvester.json')
    
    # Use the correct command name (capital H)
    command = [
        'theHarvester',  # Changed from 'theharvester' to 'theHarvester'
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
        # Run the command
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        # Check if the output file was created
        if not os.path.exists(output_file):
            logger.warning(f"theHarvester did not create the expected output file: {output_file}")
            
            # Try to save the stdout as XML
            with open(output_file, 'w') as f:
                f.write(process.stdout.decode('utf-8', errors='ignore'))
            
            logger.info(f"Saved theHarvester stdout to {output_file}")
        
        # Parse the XML results and convert to JSON for easier processing
        try:
            import xml.etree.ElementTree as ET
            
            # Try to parse the XML file
            try:
                tree = ET.parse(output_file)
                root = tree.getroot()
            except ET.ParseError:
                # If parsing fails, try to read the file and fix common XML issues
                with open(output_file, 'r') as f:
                    content = f.read()
                
                # Add XML declaration if missing
                if not content.startswith('<?xml'):
                    content = '<?xml version="1.0" encoding="UTF-8"?>\n' + content
                
                # Wrap in root element if needed
                if '<theHarvester>' not in content:
                    content = '<theHarvester>\n' + content + '\n</theHarvester>'
                
                # Parse from string
                root = ET.fromstring(content)
            
            results = {
                'emails': [],
                'hosts': [],
                'vhosts': []
            }
            
            # Extract emails
            for email in root.findall('.//email'):
                if email is not None and email.text:
                    results['emails'].append(email.text)
            
            # Extract hosts
            for host in root.findall('.//host'):
                if host is not None and host.text:
                    results['hosts'].append(host.text)
            
            # Extract virtual hosts
            for vhost in root.findall('.//vhost'):
                if vhost is not None and vhost.text:
                    results['vhosts'].append(vhost.text)
            
            # Save parsed results
            from src.modules.utils.json_utils import save_json
            save_json(results, json_output_file)
            
            logger.info(f"theHarvester scan completed. Results saved to {json_output_file}")
            
            return results
        except Exception as e:
            logger.error(f"Error parsing theHarvester results: {str(e)}")
            
            # Create a minimal result structure
            results = {
                'emails': [],
                'hosts': [],
                'vhosts': [],
                'error': str(e)
            }
            
            # Save minimal results
            from src.modules.utils.json_utils import save_json
            save_json(results, json_output_file)
            
            return results
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running theHarvester: {e}")
        return None
