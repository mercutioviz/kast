"""
File: tests/test_ftap_post_process.py
Description: Test the ftap plugin post-processing functionality
"""

import unittest
import os
import json
import sys
import tempfile
import shutil
from unittest.mock import Mock

# Add kast to path
sys.path.insert(0, '/opt/kast')

from kast.plugins.ftap_plugin import FtapPlugin


class TestFtapPostProcess(unittest.TestCase):
    """Test suite for ftap plugin post-processing."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_cli_args = Mock()
        self.mock_cli_args.verbose = False
        self.plugin = FtapPlugin(self.mock_cli_args)
        self.test_dir = tempfile.mkdtemp()
        
        # Sample ftap data (similar to the provided sample)
        self.sample_data = {
            "scan_info": {
                "url": "https://waas.cudalabx.net/",
                "mode": "simple",
                "found_count": 4,
                "total_count": 4
            },
            "results": [
                {
                    "url": "https://waas.cudalabx.net/#admin/",
                    "status_code": 200,
                    "title": "Hackazon",
                    "confidence": 0.9,
                    "found": True,
                    "has_login_form": True,
                    "technologies": ["Node.js", "jQuery", "PHP", "Bootstrap"]
                },
                {
                    "url": "https://waas.cudalabx.net/account/",
                    "status_code": 200,
                    "title": "Hackazon — Login",
                    "confidence": 1.0,
                    "found": True,
                    "has_login_form": True,
                    "technologies": ["Node.js", "jQuery", "Bootstrap"]
                },
                {
                    "url": "https://waas.cudalabx.net/admin",
                    "status_code": 200,
                    "title": "Webscantest Admin",
                    "confidence": 1.0,
                    "found": True,
                    "has_login_form": True,
                    "technologies": ["Bootstrap", "HTTP/3"]
                },
                {
                    "url": "https://waas.cudalabx.net/admin#/",
                    "status_code": 200,
                    "title": "Webscantest Admin",
                    "confidence": 1.0,
                    "found": True,
                    "has_login_form": True,
                    "technologies": ["Bootstrap", "HTTP/3"]
                }
            ]
        }
        
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_post_process_with_findings(self):
        """Test post-processing with admin panel findings."""
        # Process the sample data
        processed_path = self.plugin.post_process(self.sample_data, self.test_dir)
        
        # Verify processed file was created
        self.assertTrue(os.path.exists(processed_path))
        
        # Load and verify processed data
        with open(processed_path, 'r') as f:
            processed = json.load(f)
        
        # Check required fields
        self.assertIn("plugin-name", processed)
        self.assertEqual(processed["plugin-name"], "ftap")
        self.assertIn("issues", processed)
        self.assertIn("executive_summary", processed)
        self.assertIn("summary", processed)
        self.assertIn("details", processed)
        
        # Verify issues were extracted
        self.assertEqual(len(processed["issues"]), 4)
        self.assertTrue(all(issue == "exposed_admin_panel" for issue in processed["issues"]))
        
        # Verify summary
        self.assertIn("4 exposed admin panels", processed["summary"])
        
        # Verify executive summary is simplified (one sentence)
        self.assertEqual(processed["executive_summary"], "Found 4 admin panels.")
        
        # Verify details section
        self.assertIn("Exposed Admin Panels:", processed["details"])
        self.assertIn("Hackazon", processed["details"])
        self.assertIn("Webscantest Admin", processed["details"])
        
    def test_post_process_no_findings(self):
        """Test post-processing with no admin panel findings."""
        empty_data = {
            "scan_info": {
                "url": "https://example.com/",
                "found_count": 0
            },
            "results": []
        }
        
        processed_path = self.plugin.post_process(empty_data, self.test_dir)
        
        with open(processed_path, 'r') as f:
            processed = json.load(f)
        
        # Verify no issues were found
        self.assertEqual(len(processed["issues"]), 0)
        self.assertIn("No exposed admin panels", processed["summary"])
        self.assertEqual(processed["executive_summary"], "No admin panels found.")
        
    def test_generate_summary(self):
        """Test summary generation."""
        # Test with findings
        summary = self.plugin._generate_summary(self.sample_data)
        self.assertIn("Found 4 exposed admin panels", summary)
        
        # Test with no findings
        empty_data = {"results": []}
        summary = self.plugin._generate_summary(empty_data)
        self.assertIn("No exposed admin panels", summary)
        
        # Test with single finding (with high confidence >= 0.86)
        single_data = {
            "results": [
                {
                    "url": "https://example.com/admin",
                    "found": True,
                    "confidence": 0.95
                }
            ]
        }
        summary = self.plugin._generate_summary(single_data)
        self.assertIn("Found 1 exposed admin panel", summary)
    
    def test_build_details(self):
        """Test details building."""
        details = self.plugin._build_details(self.sample_data)
        
        # Check for key information
        self.assertIn("Exposed Admin Panels:", details)
        self.assertIn("Panel #1:", details)
        self.assertIn("https://waas.cudalabx.net/#admin/", details)
        self.assertIn("Hackazon", details)
        self.assertIn("Confidence: 90.0%", details)
        self.assertIn("Login Form Detected: Yes", details)
        self.assertIn("Technologies: Node.js, jQuery, PHP, Bootstrap", details)
        
    def test_build_executive_summary(self):
        """Test executive summary building."""
        summary = self.plugin._build_executive_summary(self.sample_data)
        
        # Check for simplified one-sentence format
        self.assertEqual(summary, "Found 4 admin panels.")
        
        # Test with no findings
        empty_data = {"results": []}
        summary_empty = self.plugin._build_executive_summary(empty_data)
        self.assertEqual(summary_empty, "No admin panels found.")
        
        # Test with single finding
        single_data = {
            "results": [
                {
                    "url": "https://example.com/admin",
                    "found": True,
                    "confidence": 0.95
                }
            ]
        }
        summary_single = self.plugin._build_executive_summary(single_data)
        self.assertEqual(summary_single, "Found 1 admin panel.")
        
    def test_issue_registry_entry(self):
        """Test that exposed_admin_panel exists in issue registry."""
        # Load issue registry
        registry_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "issue_registry.json"
        )
        
        with open(registry_path, 'r') as f:
            registry = json.load(f)
        
        # Verify exposed_admin_panel entry exists
        self.assertIn("exposed_admin_panel", registry)
        
        entry = registry["exposed_admin_panel"]
        self.assertEqual(entry["display_name"], "Exposed Admin Panel")
        self.assertEqual(entry["severity"], "High")
        self.assertEqual(entry["category"], "Access Control")
        self.assertIn("WAF", entry["remediation"])
        self.assertIn("rate-limiting", entry["remediation"])


if __name__ == '__main__':
    unittest.main()
