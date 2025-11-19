#!/usr/bin/env python3
"""
Test script for testssl plugin post-processing
"""

import sys
import os
import argparse
from pprint import pprint

# Add kast to path
sys.path.insert(0, '/opt/kast')

from kast.plugins.testssl_plugin import TestsslPlugin

def main():
    # Create a mock CLI args object
    class MockArgs:
        verbose = True
    
    # Initialize plugin
    plugin = TestsslPlugin(MockArgs())
    
    # Path to test data
    test_file = "/home/kali/kast_results/www.barracuda.com-20251118-012953/testssl.json"
    output_dir = "/tmp/testssl_test"
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    print("=" * 80)
    print("Testing TestSSL Plugin Post-Processing")
    print("=" * 80)
    print(f"\nInput file: {test_file}")
    print(f"Output directory: {output_dir}")
    
    # Run post-processing
    print("\n" + "=" * 80)
    print("Running post_process()...")
    print("=" * 80)
    
    try:
        processed_path = plugin.post_process(test_file, output_dir)
        
        print(f"\n✓ Post-processing completed successfully!")
        print(f"✓ Processed output saved to: {processed_path}")
        
        # Load and display the processed results
        import json
        with open(processed_path, 'r') as f:
            processed = json.load(f)
        
        print("\n" + "=" * 80)
        print("RESULTS SUMMARY")
        print("=" * 80)
        
        print(f"\nPlugin: {processed['plugin-display-name']}")
        print(f"Description: {processed['plugin-description']}")
        print(f"\nSummary: {processed['summary']}")
        
        print("\n" + "=" * 80)
        print("EXECUTIVE SUMMARY")
        print("=" * 80)
        print(f"\n{processed['executive_summary']}")
        
        print("\n" + "=" * 80)
        print("ISSUES FOUND")
        print("=" * 80)
        issues = processed['issues']
        if issues:
            print(f"\nTotal issues: {len(issues)}\n")
            for i, issue in enumerate(issues, 1):
                print(f"{i}. {issue}")
        else:
            print("\nNo issues found.")
        
        print("\n" + "=" * 80)
        print("DETAILS")
        print("=" * 80)
        print(f"\n{processed['details']}")
        
        print("\n" + "=" * 80)
        print("TEST COMPLETED SUCCESSFULLY")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ Error during post-processing: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
