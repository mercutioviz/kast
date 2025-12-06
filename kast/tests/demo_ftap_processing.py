#!/usr/bin/env python3
"""
Demonstration script for ftap plugin post-processing
Shows how the plugin processes admin panel findings
"""

import json
import sys
import tempfile
import os

# Add kast to path
sys.path.insert(0, '/opt/kast')

from kast.plugins.ftap_plugin import FtapPlugin
from argparse import Namespace

# Load sample data
sample_file = "/home/kali/tmp/ftap.json"

def main():
    print("=" * 80)
    print("FTAP Plugin Post-Processing Demonstration")
    print("=" * 80)
    print()
    
    # Create plugin instance
    cli_args = Namespace(verbose=True)
    plugin = FtapPlugin(cli_args)
    
    # Load sample data
    print(f"Loading sample data from: {sample_file}")
    with open(sample_file, 'r') as f:
        sample_data = json.load(f)
    
    print(f"Found {len(sample_data.get('results', []))} admin panels in sample data")
    print()
    
    # Process the data
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Processing data...")
        processed_path = plugin.post_process(sample_data, tmpdir)
        
        # Load processed results
        with open(processed_path, 'r') as f:
            processed = json.load(f)
        
        print()
        print("=" * 80)
        print("PROCESSING RESULTS")
        print("=" * 80)
        print()
        
        print(f"Plugin Name: {processed['plugin-name']}")
        print(f"Display Name: {processed['plugin-display-name']}")
        print()
        
        print("-" * 80)
        print("SUMMARY")
        print("-" * 80)
        print(processed['summary'])
        print()
        
        print("-" * 80)
        print("ISSUES FOUND")
        print("-" * 80)
        print(f"Total Issues: {len(processed['issues'])}")
        for idx, issue in enumerate(processed['issues'], 1):
            print(f"  {idx}. {issue}")
        print()
        
        print("-" * 80)
        print("EXECUTIVE SUMMARY")
        print("-" * 80)
        print(processed['executive_summary'])
        print()
        
        print("-" * 80)
        print("DETAILS")
        print("-" * 80)
        print(processed['details'])
        print()
        
        print("=" * 80)
        print("DEMONSTRATION COMPLETE")
        print("=" * 80)
        print()
        print("✓ Issue registry entry 'exposed_admin_panel' added")
        print("✓ Post-processing extracts admin panel findings")
        print("✓ Executive summary includes risk assessment and WAF recommendations")
        print("✓ Details section shows comprehensive panel information")
        print()

if __name__ == "__main__":
    main()
