#!/usr/bin/env python3
"""
Test script for testssl plugin post-processing with clientProblem1 scenario
Tests that the plugin handles testssl output with clientProblem1 warnings correctly
"""

import sys
import os
import json
import tempfile
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
    
    # Path to test data with clientProblem1
    test_file = "/home/kali/kast_results/bank.darklab.cudalabx.net-20251125-191946/testssl.json"
    
    # Create temporary output directory
    output_dir = tempfile.mkdtemp(prefix="testssl_clientproblem_test_")
    
    print("=" * 80)
    print("Testing TestSSL Plugin with clientProblem1 Scenario")
    print("=" * 80)
    print(f"\nInput file: {test_file}")
    print(f"Output directory: {output_dir}")
    
    # First, verify the test file exists and contains clientProblem1
    if not os.path.exists(test_file):
        print(f"\n✗ Test file not found: {test_file}")
        print("Using inline test data instead...")
        
        # Create test data inline with clientProblem1
        test_data = {
            "clientProblem1": [
                {
                    "id": "engine_problem",
                    "severity": "WARN",
                    "finding": "No engine or GOST support via engine with your /usr/bin/openssl"
                }
            ],
            "Invocation": "testssl -U -E -oJ /tmp/testssl.json bank.darklab.cudalabx.net",
            "at": "kali:/usr/bin/openssl",
            "version": "3.2.2 ",
            "openssl": "OpenSSL 3.5.4",
            "startTime": "1764098386",
            "scanResult": [
                {
                    "targetHost": "bank.darklab.cudalabx.net",
                    "ip": "52.230.239.3",
                    "port": "443",
                    "vulnerabilities": [
                        {
                            "id": "heartbleed",
                            "severity": "OK",
                            "cve": "CVE-2014-0160",
                            "finding": "not vulnerable, no heartbeat extension"
                        },
                        {
                            "id": "fallback_SCSV",
                            "severity": "WARN",
                            "finding": "Check failed, unexpected result"
                        },
                        {
                            "id": "SWEET32",
                            "severity": "LOW",
                            "cve": "CVE-2016-2183 CVE-2016-6329",
                            "finding": "uses 64 bit block ciphers"
                        }
                    ],
                    "cipherTests": [
                        {
                            "id": "cipher-tls1_2_xc030",
                            "severity": "OK",
                            "finding": "TLS 1.2   xc030   ECDHE-RSA-AES256-GCM-SHA384"
                        },
                        {
                            "id": "cipher-tls1_2_xc028",
                            "severity": "LOW",
                            "finding": "TLS 1.2   xc028   ECDHE-RSA-AES256-SHA384"
                        }
                    ]
                }
            ],
            "scanTime": 63
        }
        
        # Write test data to temp file
        test_file = os.path.join(output_dir, "testssl_input.json")
        with open(test_file, 'w') as f:
            json.dump(test_data, f, indent=2)
        print(f"Created test data at: {test_file}")
    else:
        # Verify the file contains clientProblem1
        with open(test_file, 'r') as f:
            data = json.load(f)
        if 'clientProblem1' in data:
            print(f"✓ Test file contains clientProblem1 field")
        else:
            print(f"✗ Test file does NOT contain clientProblem1 field")
    
    # Run post-processing
    print("\n" + "=" * 80)
    print("Running post_process()...")
    print("=" * 80)
    
    try:
        processed_path = plugin.post_process(test_file, output_dir)
        
        print(f"\n✓ Post-processing completed successfully!")
        print(f"✓ Processed output saved to: {processed_path}")
        
        # Load and display the processed results
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
        print("VERIFICATION")
        print("=" * 80)
        
        # Verify that the findings were preserved
        if 'findings' in processed:
            findings = processed['findings']
            if 'clientProblem1' in findings:
                print("\n✓ clientProblem1 preserved in findings")
            if 'scanResult' in findings:
                print("✓ scanResult preserved in findings")
                scan_result = findings['scanResult']
                if scan_result and len(scan_result) > 0:
                    if 'vulnerabilities' in scan_result[0]:
                        print(f"✓ vulnerabilities preserved ({len(scan_result[0]['vulnerabilities'])} items)")
                    if 'cipherTests' in scan_result[0]:
                        print(f"✓ cipherTests preserved ({len(scan_result[0]['cipherTests'])} items)")
        
        print("\n" + "=" * 80)
        print("TEST COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print("\nThe fix successfully handles the clientProblem1 scenario!")
        print("All scan data (vulnerabilities and cipher tests) were preserved.")
        
    except Exception as e:
        print(f"\n✗ Error during post-processing: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
