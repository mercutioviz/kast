#!/usr/bin/env python3

import os
import sys
import json
import argparse
from datetime import datetime

# Add the parent directory to sys.path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src.modules.vuln_scan.nikto_scanner import run_nikto
except ImportError:
    print("Error: Could not import the nikto_scanner module.")
    print("Make sure you're running this script from the KAST project directory.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Test Nikto scanner module")
    parser.add_argument("target", help="Target URL or domain")
    parser.add_argument("-o", "--output", default="/tmp/nikto_test", help="Output directory")
    parser.add_argument("-t", "--type", choices=["basic", "quick", "thorough", "custom"], default="basic", help="Scan type")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--custom-options", nargs="+", help="Custom Nikto options (for custom scan type)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    print(f"Starting Nikto scan of {args.target}")
    print(f"Scan type: {args.type}")
    print(f"Output directory: {args.output}")
    
    if args.dry_run:
        print("DRY RUN MODE: No actual scan will be performed")
    
    # Run the scan
    start_time = datetime.now()
    print(f"Scan started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = run_nikto(
        args.target,
        args.output,
        scan_type=args.type,
        custom_options=args.custom_options,
        dry_run=args.dry_run
    )
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"Scan completed at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total duration: {duration:.1f} seconds")
    
    # Print results summary
    if "dry_run" in results and results["dry_run"]:
        print(f"\nDry run completed. Would have executed: {results['command']}")
    elif "error" in results:
        print(f"\nError: {results['error']}")
    else:
        print(f"\nScan completed successfully!")
        print(f"Output file: {results['output_file']}")
        print(f"Summary file: {results.get('summary_file', 'N/A')}")
        
        if "summary" in results:
            summary = results["summary"]
            print("\nSummary:")
            print(f"Target: {summary['target']}")
            print(f"Scan type: {summary['scan_type']}")
            print(f"Duration: {summary['duration']}")
            print(f"Total findings: {summary.get('total_findings', 0)}")
            
            vulns = summary.get("vulnerabilities", {})
            print(f"High severity: {vulns.get('high', 0)}")
            print(f"Medium severity: {vulns.get('medium', 0)}")
            print(f"Low severity: {vulns.get('low', 0)}")
            print(f"Informational: {vulns.get('info', 0)}")
            
            if args.verbose and "findings" in summary:
                print("\nFindings:")
                for i, finding in enumerate(summary["findings"], 1):
                    print(f"\n{i}. {finding.get('message', 'No message')}")
                    print(f"   Severity: {finding.get('severity', 'unknown')}")
                    print(f"   URL: {finding.get('url', 'N/A')}")
                    print(f"   Method: {finding.get('method', 'N/A')}")
                    print(f"   OSVDB: {finding.get('osvdb', 'N/A')}")

if __name__ == "__main__":
    main()
