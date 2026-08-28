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
        self.assertIn("panel", processed["issues"][0]["description"])
        self.assertNotIn("panels", processed["issues"][0]["description"])
        self.assertEqual(processed["findings_count"], 1)

    def test_wildcard_routing_collapses_to_one_panel(self):
        """A CMS that serves one sign-in page for every /admin* path must not be
        reported as many panels. Shape taken from www.hingham-ma.gov, where
        CivicEngage returned 12 identical pages including /admin-area-51/."""
        panels = []
        for path, length in [
            ("/Admin/Pages", 271046),
            ("/ADMIN/", 271070),
            ("/admin-03/", 271046),
            ("/admin-2028/", 271052),
            ("/admin-area-51/", 271046),
        ]:
            p = self._panel(f"https://example.com{path}")
            p["title"] = "Sign In - Authentication"
            p["content_length"] = length
            panels.append(p)

        raw = {"disposition": "success", "results": self._make_findings(panels)}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertEqual(processed["findings_count"], 1)
        self.assertIn("1 exposed admin panel detected", processed["issues"][0]["description"])
        # The canonical (shortest) path represents the group, and the rest are
        # still disclosed rather than silently dropped.
        self.assertIn("https://example.com/ADMIN/", processed["issues"][0]["description"])
        self.assertIn("4 other paths", processed["issues"][0]["description"])
        self.assertIn("/admin-area-51/", processed["details"])

    def test_distinct_panels_are_not_collapsed(self):
        """Different applications must survive alias collapsing."""
        wp = self._panel("https://example.com/wp-admin")
        wp["title"] = "Log In"
        wp["content_length"] = 4200
        pma = self._panel("https://example.com/phpmyadmin")
        pma["title"] = "phpMyAdmin"
        pma["content_length"] = 91000

        raw = {"disposition": "success", "results": self._make_findings([wp, pma])}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertEqual(processed["findings_count"], 2)

    def test_same_title_different_size_is_not_collapsed(self):
        """Two apps sharing a generic title are still two panels."""
        a = self._panel("https://example.com/admin")
        a["title"] = "Login"
        a["content_length"] = 4000
        b = self._panel("https://example.com/portal")
        b["title"] = "Login"
        b["content_length"] = 88000

        raw = {"disposition": "success", "results": self._make_findings([a, b])}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertEqual(processed["findings_count"], 2)

    def test_missing_content_length_never_collapses(self):
        """Without a body size there is no evidence two URLs are the same page."""
        panels = [
            self._panel("https://example.com/admin"),
            self._panel("https://example.com/wp-admin"),
        ]
        for p in panels:
            self.assertNotIn("content_length", p)

        raw = {"disposition": "success", "results": self._make_findings(panels)}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertEqual(processed["findings_count"], 2)

    def test_fragment_urls_are_not_panels(self):
        """A fragment is never sent to the server, so /#admin/ is the homepage."""
        real = self._panel("https://example.com/admin")
        real["content_length"] = 5000
        frag = self._panel("https://example.com/#admin/")
        frag["title"] = "Example — Official Website"
        frag["content_length"] = 150000

        raw = {"disposition": "success", "results": self._make_findings([real, frag])}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertEqual(processed["findings_count"], 1)
        self.assertNotIn("#admin", processed["issues"][0]["description"])
        self.assertNotIn("#admin", processed["details"])
        self.assertNotIn("#admin", processed["custom_html_pdf"])
        # Not an exposure, but not silently dropped from the widget either.
        self.assertIn("Other Findings", processed["custom_html"])
        self.assertIn("#admin", processed["custom_html"])

    def test_collapsed_aliases_are_not_relisted_as_other_findings(self):
        """An alias belongs on its panel's card, not in a second group."""
        panels = []
        for path in ["/admin/", "/admin-9/"]:
            p = self._panel(f"https://example.com{path}")
            p["title"] = "Sign In"
            p["content_length"] = 8000
            panels.append(p)

        raw = {"disposition": "success", "results": self._make_findings(panels)}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertEqual(processed["custom_html"].count("/admin-9/"), 1)
        self.assertNotIn("Other Findings", processed["custom_html"])

    def test_every_surface_reports_the_same_count(self):
        """issues, findings_count, summary, details, and exec summary must agree."""
        panels = []
        for path, length in [("/admin/", 8000), ("/admin-7/", 8000), ("/manager/", 40000)]:
            p = self._panel(f"https://example.com{path}")
            p["title"] = "Sign In" if "admin" in path else "Manager"
            p["content_length"] = length
            panels.append(p)

        raw = {"disposition": "success", "results": self._make_findings(panels)}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertEqual(processed["findings_count"], 2)
        self.assertIn("2 exposed admin panels", processed["issues"][0]["description"])
        self.assertIn("Found 2 exposed admin panels", processed["summary"])
        self.assertEqual(processed["executive_summary"], "Found 2 admin panels.")
        self.assertEqual(processed["details"].count("Panel #"), 2)

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

    def _write_whatweb(self, plugins):
        path = os.path.join(self.test_dir, "whatweb_processed.json")
        with open(path, "w") as f:
            json.dump({"findings": {"results": [{"plugins": plugins}]}}, f)

    def test_declares_whatweb_dependency(self):
        """Corroboration needs whatweb's output on disk by post_process time."""
        self.assertIn("whatweb", [d["plugin"] for d in self.plugin.dependencies])

    def test_uncorroborated_technologies_are_dropped(self):
        """ftap substring-matched Laravel and Vue.js on an ASP.NET page."""
        panel = self._panel("https://example.com/admin")
        panel["technologies"] = ["Laravel", "Vue.js", "HTTP/2", "HTTP/3", "ASP.NET"]
        self._write_whatweb({"ASP_NET": {"string": ["4.0.30319"]}, "IIS": {}})

        raw = {"disposition": "success", "results": self._make_findings([panel])}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertIn("ASP.NET", processed["details"])
        for ghost in ["Laravel", "Vue.js", "HTTP/2", "HTTP/3"]:
            self.assertNotIn(ghost, processed["details"])
            self.assertNotIn(ghost, processed["custom_html"])

    def test_corroboration_matches_across_naming_differences(self):
        """whatweb's ASP_NET / JQuery must corroborate ftap's ASP.NET / jQuery."""
        corroborated = FtapPlugin._filter_technologies(
            ["ASP.NET", "jQuery", "Node.js", "Vue.js"],
            {"aspnet", "jquery", "nodejs"},
        )
        self.assertEqual(corroborated, ["ASP.NET", "jQuery", "Node.js"])

    def test_whatweb_string_values_corroborate(self):
        """A technology named only in a plugin's string values still counts."""
        panel = self._panel("https://example.com/admin")
        panel["technologies"] = ["Cloudflare"]
        self._write_whatweb({"HTTPServer": {"string": ["cloudflare"]}})

        raw = {"disposition": "success", "results": self._make_findings([panel])}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertIn("Cloudflare", processed["details"])

    def test_header_derived_entries_survive_without_whatweb(self):
        """Security:/Generator: come from headers and an anchored meta regex."""
        panel = self._panel("https://example.com/admin")
        panel["technologies"] = [
            "Security: HSTS", "Generator: CivicPlus", "Laravel", "React",
        ]

        raw = {"disposition": "success", "results": self._make_findings([panel])}
        with open(self.plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertIn("Security: HSTS", processed["details"])
        self.assertIn("Generator: CivicPlus", processed["details"])
        self.assertNotIn("Laravel", processed["details"])
        self.assertNotIn("React", processed["details"])

    def test_missing_whatweb_output_suppresses_rather_than_guesses(self):
        """No corroborating source means no technology claims, not unfiltered ones."""
        self.assertFalse(
            os.path.exists(os.path.join(self.test_dir, "whatweb_processed.json"))
        )
        self.assertEqual(self.plugin._whatweb_fingerprints(self.test_dir), set())

    def test_corroboration_does_not_alter_the_raw_findings(self):
        """The filter rewrites a copy; ftap.json stays a faithful raw record."""
        panel = self._panel("https://example.com/admin")
        panel["technologies"] = ["Laravel"]
        findings = self._make_findings([panel])

        self.plugin.post_process(
            {"disposition": "success", "results": findings}, self.test_dir
        )

        self.assertEqual(findings["results"][0]["technologies"], ["Laravel"])

    def test_report_only_mode(self):
        """Test plugin behavior in report-only mode."""
        result = self.plugin.run("https://example.com", self.test_dir, report_only=True)
        self.assertIsInstance(result, dict)
        self.assertIn("disposition", result)


