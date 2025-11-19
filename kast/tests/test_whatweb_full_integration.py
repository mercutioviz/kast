#!/usr/bin/env python3
"""
Full integration test for whatweb redirect detection in reports.
"""

import json
import sys
import os
import tempfile
import shutil

# Add kast to path
sys.path.insert(0, '/opt/kast')

from kast.plugins.whatweb_plugin import WhatWebPlugin
from kast.report_builder import generate_html_report
from argparse import Namespace

def test_full_integration():
    """Test the complete flow from whatweb data to HTML report."""
    print("Testing full integration of WhatWeb redirect detection...")
    print("=" * 70)
    
    # Create temporary directory for test output
    temp_dir = tempfile.mkdtemp(prefix="whatweb_test_")
    print(f"\nTest output directory: {temp_dir}")
    
    try:
        # Load the actual whatweb data
        with open('/home/kali/kast_results/sanger.k12.ca.us-20251118-191643/whatweb.json', 'r') as f:
            whatweb_data = json.load(f)
        
        # Create plugin instance
        cli_args = Namespace(verbose=True)
        plugin = WhatWebPlugin(cli_args)
        plugin.command_executed = "whatweb -a 3 sanger.k12.ca.us --log-json whatweb.json"
        
        # Run post_process
        # First save the data to a temp file
        whatweb_file = os.path.join(temp_dir, "whatweb.json")
        with open(whatweb_file, 'w') as f:
            json.dump(whatweb_data, f, indent=2)
        
        processed_path = plugin.post_process(whatweb_file, temp_dir)
        
        # Load the processed data
        with open(processed_path, 'r') as f:
            processed = json.load(f)
        
        print("\n" + "=" * 70)
        print("PROCESSED DATA - Executive Summary:")
        print("-" * 70)
        exec_summary = processed.get("executive_summary", "")
        if exec_summary:
            for line in exec_summary.split('\n'):
                print(f"  {line}")
        else:
            print("  (No executive summary found)")
        
        print("\n" + "=" * 70)
        print("PROCESSED DATA - Summary:")
        print("-" * 70)
        summary = processed.get("summary", [])
        for item in summary:
            for key, value in item.items():
                print(f"  {key}:")
                print(f"    {value}")
        
        # Generate HTML report
        report_path = os.path.join(temp_dir, "test_report.html")
        generate_html_report([processed], report_path, target="sanger.k12.ca.us")
        
        print("\n" + "=" * 70)
        print(f"HTML Report generated: {report_path}")
        print("=" * 70)
        
        # Check if the recommendation appears in the HTML
        with open(report_path, 'r') as f:
            html_content = f.read()
        
        if "www.sanger.k12.ca.us" in html_content and "redirection location" in html_content:
            print("\n✓ SUCCESS: Recommendation appears in HTML report")
            print(f"\nYou can view the report at: file://{report_path}")
            return True
        else:
            print("\n✗ FAILURE: Recommendation not found in HTML report")
            return False
            
    finally:
        # Clean up
        print(f"\nCleaning up temporary directory: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    success = test_full_integration()
    sys.exit(0 if success else 1)
