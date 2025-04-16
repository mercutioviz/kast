#!/usr/bin/env python3

import os
import json
import subprocess
from src.modules.utils.validators import extract_domain
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def run_dnsenum(target, output_dir, dry_run=False):
    """Run DNSenum for DNS enumeration"""
    logger.info("Running DNSenum for DNS enumeration")
    
    domain = extract_domain(target)
    output_file = os.path.join(output_dir, 'dnsenum.xml')
    
    command = [
        'dnsenum',
        '--noreverse',
        '--nocolor',
        '-o', output_file,
        domain
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
        
        logger.info(f"DNSenum scan completed. Results saved to {output_file}")
        
        # Parse the XML results and convert to JSON for easier processing
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(output_file)
            root = tree.getroot()
            
            results = {
                'nameservers': [],
                'mx_records': [],
                'subdomains': []
            }
            
            # Extract nameservers
            for ns in root.findall('.//name_server'):
                results['nameservers'].append(ns.text)
            
            # Extract MX records
            for mx in root.findall('.//mx'):
                results['mx_records'].append({
                    'host': mx.find('hostname').text if mx.find('hostname') is not None else '',
                    'priority': mx.find('priority').text if mx.find('priority') is not None else ''
                })
            
            # Extract subdomains
            for host in root.findall('.//domain'):
                if host.find('hostname') is not None:
                    results['subdomains'].append({
                        'hostname': host.find('hostname').text,
                        'ip': host.find('address').text if host.find('address') is not None else ''
                    })
            
            # Save parsed results
            parsed_output = os.path.join(output_dir, 'dnsenum_parsed.json')
            with open(parsed_output, 'w') as f:
                json.dump(results, f, indent=4)
            
            logger.debug(f"Parsed DNSenum results saved to {parsed_output}")
            
            return results
        except Exception as e:
            logger.error(f"Error parsing DNSenum results: {str(e)}")
            return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running DNSenum: {e}")
        return None
