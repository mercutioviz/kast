#!/usr/bin/env python3
"""
Test script to verify whatweb plugin domain redirect detection.
"""

import json
import sys
import os

# Add kast to path
sys.path.insert(0, '/opt/kast')

from kast.plugins.whatweb_plugin import WhatWebPlugin
from argparse import Namespace

# Sample whatweb data with domain redirect
test_data = [
    {
        "target": "http://sanger.k12.ca.us",
        "http_status": 301,
        "request_config": {"headers": {"User-Agent": "WhatWeb/0.6.3"}},
        "plugins": {
            "Apache": {},
            "RedirectLocation": {"string": ["https://www.sanger.k12.ca.us/"]}
        }
    },
    {
        "target": "https://sanger.k12.ca.us",
        "http_status": 301,
        "request_config": {"headers": {"User-Agent": "WhatWeb/0.6.3"}},
        "plugins": {
            "Apache": {},
            "RedirectLocation": {"string": ["https://www.sanger.k12.ca.us/"]}
        }
    },
    {
        "target": "https://www.sanger.k12.ca.us/",
        "http_status": 200,
        "request_config": {"headers": {"User-Agent": "WhatWeb/0.6.3"}},
        "plugins": {
            "Apache": {},
            "WordPress": {}
        }
    }
]

def test_domain_redirect_detection():
    """Test that domain redirects are properly detected."""
    print("Testing WhatWeb domain redirect detection...")
    print("=" * 60)
    
    # Create a mock CLI args object
    cli_args = Namespace(verbose=True)
    
    # Create plugin instance
    plugin = WhatWebPlugin(cli_args)
    
    # Test the redirect detection
    recommendations = plugin._detect_domain_redirects(test_data)
    
    print(f"\nNumber of recommendations found: {len(recommendations)}")
    print("\nRecommendations:")
    print("-" * 60)
    
    for rec in recommendations:
        print(f"  {rec}")
    
    print("\n" + "=" * 60)
    
    # Verify the expected recommendation is present
    expected_domain = "www.sanger.k12.ca.us"
    expected_from = "sanger.k12.ca.us"
    
    found = False
    for rec in recommendations:
        if expected_domain in rec and expected_from in rec:
            found = True
            print(f"\n✓ SUCCESS: Found expected recommendation for {expected_domain}")
            break
    
    if not found:
        print(f"\n✗ FAILURE: Did not find recommendation for {expected_domain}")
        return False
    
    # Verify we don't have duplicate recommendations
    if len(recommendations) > 1:
        print(f"\n⚠ WARNING: Expected 1 recommendation but got {len(recommendations)}")
    
    return True

if __name__ == "__main__":
    success = test_domain_redirect_detection()
    sys.exit(0 if success else 1)
