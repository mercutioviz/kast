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
    json_output_file = os.path.join(output_dir, 'dnsenum.json')
    text_output_file = os.path.join(output_dir, 'dnsenum.txt')
    
    # Remove the -o option since it's causing issues
    command = [
        'dnsenum',
        '--noreverse',
        '--nocolor',
        domain
    ]
    
    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(command)}")
        return {
            "dry_run": True,
            "command": ' '.join(command),
            "output_file": json_output_file
        }
    
    try:
        # Run the command and capture output
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        
        # Save stdout to text file regardless of exit code
        with open(text_output_file, 'w') as f:
            f.write(process.stdout)
        
        # Check if the process failed
        if process.returncode != 0:
            logger.warning(f"DNSenum exited with code {process.returncode}")
            logger.warning(f"DNSenum stderr: {process.stderr}")
            logger.info(f"DNSenum stdout saved to {text_output_file}")
        
        # Create a basic results structure from stdout
        results = {
            'nameservers': [],
            'mx_records': [],
            'subdomains': [],
            'hosts': [],
            'raw_output': process.stdout,
            'error': process.stderr if process.returncode != 0 else None
        }
        
        # Extract information from stdout using regex
        import re
        
        # Extract nameservers
        ns_matches = re.findall(r'NS: (.*?)$', process.stdout, re.MULTILINE)
        for match in ns_matches:
            results['nameservers'].append(match.strip())
        
        # Extract MX records
        mx_matches = re.findall(r'MX: (.*?) (.*?)$', process.stdout, re.MULTILINE)
        for priority, host in mx_matches:
            results['mx_records'].append({
                'host': host.strip(),
                'priority': priority.strip()
            })
        
        # Extract hosts (more general pattern)
        host_pattern = r'([\w\.-]+\.[\w\.-]+)\s+\d+\s+IN\s+A\s+(\d+\.\d+\.\d+\.\d+)'
        host_matches = re.findall(host_pattern, process.stdout)
        
        for hostname, ip in host_matches:
            host_entry = {
                'hostname': hostname.strip(),
                'ip': ip.strip()
            }
            results['hosts'].append(host_entry)
            
            # Also add to subdomains if it's a subdomain of the target
            if hostname.endswith(f".{domain}"):
                results['subdomains'].append(host_entry)
        
        # Save results to JSON
        from src.modules.utils.json_utils import save_json
        save_json(results, json_output_file)
        
        logger.info(f"DNSenum scan completed. Results saved to {json_output_file}")
        return results
        
    except Exception as e:
        logger.error(f"Error with DNSenum: {str(e)}")
        return {
            'nameservers': [],
            'mx_records': [],
            'subdomains': [],
            'hosts': [],
            'error': str(e)
        }
