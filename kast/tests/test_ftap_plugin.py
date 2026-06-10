"""
File: tests/test_ftap_plugin.py
Description: Unit tests for ftap plugin
Created: 2025-12-05
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock

from kast.plugins.ftap_plugin import FtapPlugin


class TestFtapPlugin(unittest.TestCase):
    """Test suite for FtapPlugin."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_cli_args = Mock()
        self.mock_cli_args.verbose = False
        self.plugin = FtapPlugin(self.mock_cli_args)
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_plugin_initialization(self):
        """Test plugin initializes with correct attributes."""
        self.assertEqual(self.plugin.name, "ftap")
        self.assertIsNotNone(self.plugin.display_name)
        self.assertIsNotNone(self.plugin.description)
        self.assertIn(self.plugin.scan_type, ["passive", "active"])
        self.assertIn(self.plugin.output_type, ["file", "stdout"])

    def test_is_available(self):
        """Test tool availability check."""
        # This will depend on whether the tool is installed
        result = self.plugin.is_available()
        self.assertIsInstance(result, bool)

    def _make_findings(self, panels):
        return {
            "scan_info": {"target": "https://example.com"},
            "results": panels,
        }

    def _panel(self, url, confidence=0.95, found=True):
        return {
            "url": url,
            "found": found,
            "confidence": confidence,
            "title": "Admin Login",
            "status_code": 200,
            "has_login_form": True,
            "technologies": [],
        }

    def test_post_process_multiple_panels_single_issue(self):
        """Multiple high-confidence panels produce exactly one issue entry."""
        findings = self._make_findings([
            self._panel("https://example.com/admin"),
            self._panel("https://example.com/wp-admin"),
            self._panel("https://example.com/administrator"),
        ])
        raw = {"disposition": "success", "results": findings}
        result_path = self.plugin.post_process(raw, self.test_dir)
        with open(result_path) as f:
            processed = json.load(f)

        issues = processed["issues"]
        self.assertEqual(len(issues), 1, "Three panels must collapse to one issue")
        issue = issues[0]
        self.assertEqual(issue["id"], "exposed_admin_panel")
        self.assertIn("3", issue["description"])
        self.assertIn("https://example.com/admin", issue["description"])
        self.assertIn("https://example.com/wp-admin", issue["description"])
        self.assertIn("https://example.com/administrator", issue["description"])
        self.assertEqual(processed["findings_count"], 3)

    def test_post_process_single_panel_single_issue(self):
        """One high-confidence panel produces one issue with singular noun."""
        findings = self._make_findings([self._panel("https://example.com/admin")])
        raw = {"disposition": "success", "results": findings}
        result_path = self.plugin.post_process(raw, self.test_dir)
        with open(result_path) as f:
            processed = json.load(f)

        self.assertEqual(len(processed["issues"]), 1)
        self.assertIn("1", processed["issues"][0]["description"])
        self.assertIn("URL", processed["issues"][0]["description"])
        self.assertNotIn("URLs", processed["issues"][0]["description"])
        self.assertEqual(processed["findings_count"], 1)

    def test_post_process_no_exposed_panels(self):
        """No high-confidence panels produces empty issues list."""
        findings = self._make_findings([
            self._panel("https://example.com/admin", confidence=0.5),
            self._panel("https://example.com/wp-admin", found=False),
        ])
        raw = {"disposition": "success", "results": findings}
        result_path = self.plugin.post_process(raw, self.test_dir)
        with open(result_path) as f:
            processed = json.load(f)

        self.assertEqual(processed["issues"], [])
        self.assertEqual(processed["findings_count"], 0)

    def test_post_process_low_confidence_excluded(self):
        """Panels below confidence threshold 0.86 are excluded."""
        findings = self._make_findings([
            self._panel("https://example.com/admin", confidence=0.85),  # just below
            self._panel("https://example.com/wp-admin", confidence=0.86),  # exactly at threshold
        ])
        raw = {"disposition": "success", "results": findings}
        result_path = self.plugin.post_process(raw, self.test_dir)
        with open(result_path) as f:
            processed = json.load(f)

        self.assertEqual(len(processed["issues"]), 1)
        self.assertEqual(processed["findings_count"], 1)
        self.assertIn("https://example.com/wp-admin", processed["issues"][0]["description"])
        self.assertNotIn("https://example.com/admin", processed["issues"][0]["description"])

    def test_report_only_mode(self):
        """Test plugin behavior in report-only mode."""
        result = self.plugin.run("https://example.com", self.test_dir, report_only=True)
        self.assertIsInstance(result, dict)
        self.assertIn("disposition", result)


