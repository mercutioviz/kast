#!/usr/bin/env python3

import os
import json
import subprocess
from src.modules.utils.validators import normalize_url
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def run_wafw00f(target, output_dir, dry_run=False):
    """Run wafw00f to detect Web Application Firewalls"""
    logger.info("Running wafw00f to detect Web Application Firewalls")
    
    url = normalize_url(target)
    output_file = os.path.join(output_dir, 'wafw00f.json')
    
    command = [
        'wafw00f',
        url,
        '-a',  # Find all WAFs, don't stop at the first one
        '-o', output_file,
        '-f', 'json'
    ]
    
    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(command)}")
        return {
            "dry_run": True,
            "command": ' '.join(command),
            "output_file": output_file
        }
    
    try:
        # Run wafw00f with JSON output
        process = subprocess.run(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE, check=True)
        
        logger.info(f"wafw00f scan completed. Results saved to {output_file}")
        
        # Parse the results
        try:
            with open(output_file, 'r') as f:
                wafw00f_data = json.load(f)
            
            return wafw00f_data
        except json.JSONDecodeError:
            # If JSON parsing fails, save the raw output
            with open(output_file, 'w') as f:
                f.write(process.stdout.decode())
            
            # Try to parse the output manually
            output = process.stdout.decode()
            result = {
                'url': url,
                'detected_wafs': []
            }
            
            for line in output.split('\n'):
                if 'is behind' in line:
                    waf = line.split('is behind')[-1].strip()
                    result['detected_wafs'].append(waf)
            
            # Save the parsed results
            parsed_output = os.path.join(output_dir, 'wafw00f_parsed.json')
            with open(parsed_output, 'w') as f:
                json.dump(result, f, indent=4)
            
            logger.debug(f"Parsed wafw00f results saved to {parsed_output}")
            
            return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running wafw00f: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error with wafw00f: {str(e)}")
        return None
