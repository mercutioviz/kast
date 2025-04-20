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

def run_sslscan(target, output_dir, dry_run=False):
    """Run SSLScan for SSL/TLS configuration analysis"""
    logger.info("Running SSLScan for SSL/TLS configuration analysis")
    
    output_file = os.path.join(output_dir, 'sslscan.json')
    text_output_file = os.path.join(output_dir, 'sslscan.txt')
    domain = extract_domain(target)
    
    # Check if the target is using HTTPS
    url = normalize_url(target)
    is_https = url.startswith('https://')
    
    command = [
        'sslscan',
        '--no-colour',
        '--json=' + output_file,
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
        # Run the command and capture output
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        
        # Save stdout to text file regardless of exit code
        with open(text_output_file, 'w') as f:
            f.write(process.stdout)
        
        # Check if the process failed
        if process.returncode != 0:
            logger.warning(f"SSLScan exited with code {process.returncode}")
            logger.warning(f"SSLScan stderr: {process.stderr}")
            logger.info(f"SSLScan stdout saved to {text_output_file}")
        
        # Check if the JSON file was created
        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            logger.info(f"SSLScan did not create a valid JSON file at {output_file}, attempting to create from raw output...")
            
            # Create a JSON file from the text output
            sslscan_data = {
                'target': domain,
                'is_https': is_https,
                'raw_output': process.stdout,
                'error': process.stderr if process.returncode != 0 else None
            }
            
            # Extract information from stdout using regex
            import re
            
            # Extract SSL/TLS protocols
            protocols = {}
            protocol_matches = re.findall(r'(SSLv2|SSLv3|TLSv1\.0|TLSv1\.1|TLSv1\.2|TLSv1\.3)\s+(enabled|disabled)', process.stdout)
            for protocol, status in protocol_matches:
                protocols[protocol] = (status == 'enabled')
            
            sslscan_data['protocols'] = protocols
            
            # Extract ciphers
            ciphers = []
            cipher_matches = re.findall(r'(Preferred|Accepted)\s+(TLSv[\d\.]+)\s+(\d+) bits\s+([\w-]+)\s+(.*)', process.stdout)
            for preference, protocol, bits, cipher, extra in cipher_matches:
                ciphers.append({
                    'preference': preference,
                    'protocol': protocol,
                    'bits': bits,
                    'cipher': cipher,
                    'extra': extra.strip()
                })
            
            sslscan_data['ciphers'] = ciphers
            
            # Extract certificate information
            cert_info = {}
            
            # Subject
            subject_match = re.search(r'Subject:\s+(.*?)$', process.stdout, re.MULTILINE)
            if subject_match:
                cert_info['subject'] = subject_match.group(1).strip()
            
            # Issuer
            issuer_match = re.search(r'Issuer:\s+(.*?)$', process.stdout, re.MULTILINE)
            if issuer_match:
                cert_info['issuer'] = issuer_match.group(1).strip()
            
            # Validity
            not_before_match = re.search(r'Not valid before:\s+(.*?)$', process.stdout, re.MULTILINE)
            if not_before_match:
                cert_info['not_before'] = not_before_match.group(1).strip()
                
            not_after_match = re.search(r'Not valid after:\s+(.*?)$', process.stdout, re.MULTILINE)
            if not_after_match:
                cert_info['not_after'] = not_after_match.group(1).strip()
            
            # RSA key strength
            rsa_match = re.search(r'RSA Key Strength:\s+(\d+)', process.stdout)
            if rsa_match:
                cert_info['rsa_key_strength'] = rsa_match.group(1).strip()
            
            sslscan_data['certificate'] = cert_info
            
            # Save the extracted data to JSON
            from src.modules.utils.json_utils import save_json
            save_json(sslscan_data, output_file)
            
            logger.info(f"Created JSON from SSLScan text output: {output_file}")
        else:
            # Load the JSON file
            from src.modules.utils.json_utils import load_json_file
            sslscan_data = load_json_file(output_file)
            
            if not sslscan_data:
                logger.warning(f"Failed to parse SSLScan JSON output: {output_file}")
                
                # Create a basic JSON structure
                sslscan_data = {
                    'target': domain,
                    'is_https': is_https,
                    'raw_output': process.stdout,
                    'error': 'Failed to parse JSON output'
                }
                
                # Save the basic data
                from src.modules.utils.json_utils import save_json
                save_json(sslscan_data, output_file)
        
        logger.info(f"SSLScan completed. Results saved to {output_file}")
        return sslscan_data
        
    except Exception as e:
        logger.error(f"Unexpected error with SSLScan: {str(e)}")
        
        # Create a minimal result structure
        sslscan_data = {
            'target': domain,
            'is_https': is_https,
            'error': str(e)
        }
        
        # Save the error data
        from src.modules.utils.json_utils import save_json
        save_json(sslscan_data, output_file)
        
        return sslscan_data

def run_ssllabs(target, output_dir, dry_run=False):
    """Run SSL Labs API scan for comprehensive SSL/TLS analysis"""
    logger.info("Running SSL Labs scan for comprehensive SSL/TLS analysis")
    
    domain = extract_domain(target)
    output_file = os.path.join(output_dir, 'ssllabs.json')
    
    if dry_run:
        logger.info(f"[DRY RUN] Would call SSL Labs API for {domain}")
        logger.info(f"[DRY RUN] Would poll API until scan completes")
        logger.info(f"[DRY RUN] Would save results to {output_file}")
        return {
            "dry_run": True,
            "target": domain,
            "api": "SSL Labs",
            "output_file": output_file
        }
    
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
