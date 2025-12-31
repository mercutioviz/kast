#!/usr/bin/env python3
"""
Test for related_sites plugin error handling in post_process.

This test verifies that the plugin correctly handles failure cases where
the results field is a string error message instead of a dict.
"""

import unittest
import sys
import os
import json
import tempfile
from unittest.mock import Mock
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from kast.plugins.related_sites_plugin import RelatedSitesPlugin


class TestRelatedSitesErrorHandling(unittest.TestCase):
    """Test cases for error handling in related_sites plugin post_process."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create mock CLI args
        self.mock_args = Mock()
        self.mock_args.verbose = False
        self.mock_args.httpx_rate_limit = None
        
        # Create plugin instance
        self.plugin = RelatedSitesPlugin(self.mock_args)
        
        # Create temporary output directory
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test fixtures."""
        # Remove temp directory and contents
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_post_process_handles_string_error(self):
        """Test that post_process handles string error messages gracefully."""
        # Simulate a failure result where results is a string
        raw_output = {
            "name": "related_sites",
            "disposition": "fail",
            "results": "No subdomains discovered for example.com"
        }
        
        # Call post_process - should not raise AttributeError
        processed_path = self.plugin.post_process(raw_output, self.temp_dir)
        
        # Verify processed file was created
        self.assertTrue(os.path.exists(processed_path))
        
        # Load and verify processed data
        with open(processed_path, 'r') as f:
            processed = json.load(f)
        
        # Verify structure
        self.assertEqual(processed["plugin-name"], "related_sites")
        self.assertEqual(processed["findings_count"], 0)
        self.assertEqual(processed["findings"], {})
        self.assertIn("Plugin failed", processed["summary"])
        self.assertIn("No subdomains discovered", processed["details"])
        self.assertEqual(processed["issues"], [])
        self.assertEqual(len(processed["executive_summary"]), 1)
        self.assertIn("failed", processed["executive_summary"][0].lower())
    
    def test_post_process_handles_success_dict(self):
        """Test that post_process still works with success dict results."""
        # Simulate a success result where results is a dict
        raw_output = {
            "name": "related_sites",
            "disposition": "success",
            "results": {
                "target": "www.example.com",
                "apex_domain": "example.com",
                "scanned_domain": "example.com",
                "total_subdomains": 3,
                "subdomains": ["www.example.com", "mail.example.com", "api.example.com"],
                "filtered_target_duplicates": 1,
                "related_subdomains": ["mail.example.com", "api.example.com"],
                "live_hosts": [
                    {
                        "host": "mail.example.com",
                        "ports": [443],
                        "port_responses": [
                            {
                                "port": 443,
                                "url": "https://mail.example.com",
                                "status_code": 200,
                                "title": "Mail",
                                "technologies": ["nginx"],
                                "cdn": "",
                                "websocket": False
                            }
                        ],
                        "technologies": ["nginx"],
                        "has_cdn": False,
                        "has_websocket": False
                    }
                ],
                "dead_hosts": ["api.example.com"],
                "statistics": {
                    "total_discovered": 3,
                    "filtered_duplicates": 1,
                    "total_related": 2,
                    "total_live": 1,
                    "total_dead": 1,
                    "response_rate": 50.0,
                    "unique_technologies": 1,
                    "cdn_protected": 0,
                    "websocket_enabled": 0
                }
            }
        }
        
        # Call post_process - should work normally
        processed_path = self.plugin.post_process(raw_output, self.temp_dir)
        
        # Verify processed file was created
        self.assertTrue(os.path.exists(processed_path))
        
        # Load and verify processed data
        with open(processed_path, 'r') as f:
            processed = json.load(f)
        
        # Verify structure
        self.assertEqual(processed["plugin-name"], "related_sites")
        self.assertEqual(processed["findings_count"], 1)  # 1 live host
        self.assertIsInstance(processed["findings"], dict)
        self.assertIn("Discovered 3 subdomain", processed["summary"])
        self.assertIsInstance(processed["executive_summary"], list)
        self.assertGreater(len(processed["executive_summary"]), 0)
    
    def test_post_process_handles_various_error_messages(self):
        """Test that post_process handles various error message formats."""
        error_messages = [
            "Required tools (subfinder and/or httpx) not found in PATH",
            "No subdomains discovered for example.com",
            "No related subdomains found for example.com (only target itself discovered)",
            "No existing results found"
        ]
        
        for error_msg in error_messages:
            with self.subTest(error_message=error_msg):
                raw_output = {
                    "name": "related_sites",
                    "disposition": "fail",
                    "results": error_msg
                }
                
                # Should not raise any exceptions
                processed_path = self.plugin.post_process(raw_output, self.temp_dir)
                
                # Verify file exists and contains error
                self.assertTrue(os.path.exists(processed_path))
                with open(processed_path, 'r') as f:
                    processed = json.load(f)
                
                self.assertIn(error_msg, processed["details"])
                self.assertEqual(processed["findings_count"], 0)


def run_tests():
    """Run the test suite."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestRelatedSitesErrorHandling)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
