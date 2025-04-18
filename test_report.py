#!/usr/bin/env python3

import os
import sys
import json
import argparse
from datetime import datetime

# Add the parent directory to sys.path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src.modules.reporting.report_generator import generate_report
except ImportError:
    print("Error: Could not import the report_generator module.")
    print("Make sure you're running this script from the KAST project directory.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Generate a report from scan results")
    parser.add_argument("results_dir", help="Directory containing scan results")
    parser.add_argument("-o", "--output", help="Output directory for the report (defaults to results_dir)")
    parser.add_argument("-t", "--target", help="Target that was scanned (defaults to extracted from directory name)")
    
    args = parser.parse_args()
    
    # Validate results directory
    if not os.path.isdir(args.results_dir):
        print(f"Error: Results directory '{args.results_dir}' does not exist or is not a directory")
        sys.exit(1)
    
    # Set output directory
    output_dir = args.output if args.output else args.results_dir
    
    # Extract target from directory name if not provided
    target = args.target
    if not target:
        # Try to extract target from directory name (assuming format like "example.com-20250416_182647")
        dir_name = os.path.basename(os.path.normpath(args.results_dir))
        if '-' in dir_name:
            target = dir_name.split('-')[0]
        else:
            target = dir_name
    
    print(f"Generating report for target: {target}")
    print(f"Using results from: {args.results_dir}")
    print(f"Output directory: {output_dir}")
    
    # Load results
    results = {}
    
    # Check for recon results
    recon_dir = os.path.join(args.results_dir, 'recon')
    if os.path.isdir(recon_dir):
        print("Found reconnaissance results directory")
        results['recon'] = load_recon_results(recon_dir)
    
    # Check for vuln results
    vuln_dir = os.path.join(args.results_dir, 'vuln')
    if os.path.isdir(vuln_dir):
        print("Found vulnerability scan results directory")
        results['vuln'] = load_vuln_results(vuln_dir)
    
    if not results:
        print("Error: No results found in the specified directory")
        sys.exit(1)
    
    # Generate the report
    try:
        start_time = datetime.now()
        print(f"Starting report generation at {start_time.strftime('%H:%M:%S')}")
        
        report_path = generate_report(target, results, output_dir)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"Report generated successfully in {duration:.1f} seconds")
        print(f"Report saved to: {report_path}")
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        sys.exit(1)

def load_recon_results(recon_dir):
    """Load reconnaissance results from files in the recon directory"""
    results = {}
    
    # Check for WhatWeb results
    whatweb_file = os.path.join(recon_dir, 'whatweb.json')
    if os.path.exists(whatweb_file):
        try:
            with open(whatweb_file, 'r') as f:
                results['whatweb'] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load WhatWeb results: {e}")
    
    # Check for theHarvester results
    theharvester_file = os.path.join(recon_dir, 'theharvester_parsed.json')
    if os.path.exists(theharvester_file):
        try:
            with open(theharvester_file, 'r') as f:
                results['theharvester'] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load theHarvester results: {e}")
    
    # Check for DNSenum results
    dnsenum_file = os.path.join(recon_dir, 'dnsenum_parsed.json')
    if os.path.exists(dnsenum_file):
        try:
            with open(dnsenum_file, 'r') as f:
                results['dnsenum'] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load DNSenum results: {e}")
    
    # Check for SSLScan results
    sslscan_file = os.path.join(recon_dir, 'sslscan.json')
    if os.path.exists(sslscan_file):
        try:
            with open(sslscan_file, 'r') as f:
                results['sslscan'] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load SSLScan results: {e}")
    
    # Check for wafw00f results
    wafw00f_file = os.path.join(recon_dir, 'wafw00f.json')
    if os.path.exists(wafw00f_file):
        try:
            with open(wafw00f_file, 'r') as f:
                results['wafw00f'] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load wafw00f results: {e}")
    
    # Check for SSL Labs results
    ssllabs_file = os.path.join(recon_dir, 'ssllabs.json')
    if os.path.exists(ssllabs_file):
        try:
            with open(ssllabs_file, 'r') as f:
                results['ssllabs'] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load SSL Labs results: {e}")
    
    # Check for SecurityHeaders results
    securityheaders_file = os.path.join(recon_dir, 'securityheaders.json')
    if os.path.exists(securityheaders_file):
        try:
            with open(securityheaders_file, 'r') as f:
                results['securityheaders'] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load SecurityHeaders results: {e}")
    
    # Check for Mozilla Observatory results
    observatory_file = os.path.join(recon_dir, 'mozilla_observatory.json')
    if os.path.exists(observatory_file):
        try:
            with open(observatory_file, 'r') as f:
                results['mozilla_observatory'] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load Mozilla Observatory results: {e}")
    
    # Check for browser recon results
    browser_file = os.path.join(recon_dir, 'browser_recon.json')
    if os.path.exists(browser_file):
        try:
            with open(browser_file, 'r') as f:
                results['browser'] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load browser recon results: {e}")
    
    return results

def load_vuln_results(vuln_dir):
    """Load vulnerability scan results from files in the vuln directory"""
    results = {}
    
    # Look for Nikto results (could be multiple files with timestamps)
    for filename in os.listdir(vuln_dir):
        if filename.startswith('nikto_') and filename.endswith('.json'):
            try:
                with open(os.path.join(vuln_dir, filename), 'r') as f:
                    results['nikto'] = json.load(f)
                break  # Use the first Nikto result file found
            except Exception as e:
                print(f"Warning: Could not load Nikto results from {filename}: {e}")
    
    # Add more vulnerability scanners here as they are implemented
    
    return results

if __name__ == "__main__":
    main()
