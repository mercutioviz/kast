#!/usr/bin/env python3
"""
Test to verify HTML report contains proper bulleted list structure.
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

def test_html_list_structure():
    """Verify that the HTML report contains <ul> and <li> tags for executive summaries."""
    print("Testing HTML list structure in report...")
    print("=" * 70)
    
    # Create temporary directory for test output
    temp_dir = tempfile.mkdtemp(prefix="html_list_test_")
    print(f"\nTest output directory: {temp_dir}")
    
    try:
        # Load the actual whatweb data
        with open('/home/kali/kast_results/sanger.k12.ca.us-20251118-191643/whatweb.json', 'r') as f:
            whatweb_data = json.load(f)
        
        # Create plugin instance and process
        cli_args = Namespace(verbose=False)
        plugin = WhatWebPlugin(cli_args)
        plugin.command_executed = "whatweb -a 3 sanger.k12.ca.us --log-json whatweb.json"
        
        # Save and process the data
        whatweb_file = os.path.join(temp_dir, "whatweb.json")
        with open(whatweb_file, 'w') as f:
            json.dump(whatweb_data, f, indent=2)
        
        processed_path = plugin.post_process(whatweb_file, temp_dir)
        
        # Load the processed data
        with open(processed_path, 'r') as f:
            processed = json.load(f)
        
        # Generate HTML report
        report_path = os.path.join(temp_dir, "test_report.html")
        generate_html_report([processed], report_path, target="sanger.k12.ca.us")
        
        # Read the HTML content
        with open(report_path, 'r') as f:
            html_content = f.read()
        
        print("\n" + "=" * 70)
        print("HTML STRUCTURE VERIFICATION:")
        print("-" * 70)
        
        # Check for bulleted list structure
        has_ul = '<ul class="executive-summary-list">' in html_content
        has_li = '<li>' in html_content
        has_recommendation = 'www.sanger.k12.ca.us' in html_content
        
        # Check that we DON'T have paragraph tags for executive summary
        scan_findings_section = html_content[html_content.find('<h4>Scan Findings</h4>'):html_content.find('<h4>Potential Issues</h4>')]
        has_p_in_findings = '<p class="report-paragraph">' in scan_findings_section
        
        print(f"✓ Has <ul> tag with executive-summary-list class: {has_ul}")
        print(f"✓ Has <li> tags: {has_li}")
        print(f"✓ Contains recommendation text: {has_recommendation}")
        print(f"✓ No paragraph tags in Scan Findings: {not has_p_in_findings}")
        
        if has_ul and has_li and has_recommendation and not has_p_in_findings:
            print("\n" + "=" * 70)
            print("✓ SUCCESS: HTML report uses bulleted lists for executive summary")
            print(f"\nYou can view the report at: file://{report_path}")
            
            # Extract and display a snippet
            ul_start = html_content.find('<ul class="executive-summary-list">')
            ul_end = html_content.find('</ul>', ul_start) + 5
            snippet = html_content[ul_start:ul_end]
            
            print("\nHTML Snippet:")
            print("-" * 70)
            print(snippet)
            print("=" * 70)
            return True
        else:
            print("\n✗ FAILURE: HTML structure issues detected")
            return False
            
    finally:
        # Keep the temp directory for inspection
        print(f"\nTest directory preserved for inspection: {temp_dir}")

if __name__ == "__main__":
    success = test_html_list_structure()
    sys.exit(0 if success else 1)
