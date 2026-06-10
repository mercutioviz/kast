"""Tests for the CORS analyzer plugin.

Focused on the post-processing business logic, registry coverage, and the
report-rendering helpers. The network-probing methods (``_probe_cors``,
``_probe_bypass``, ``_probe_jsonp``) are exercised indirectly via fixture
inputs; testing them against live HTTP is brittle and not how this plugin
is meant to be unit-tested.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock

from kast.plugins.cors_analyzer_plugin import (
    _DEFAULT_PROBE_PATHS,
    _ISSUE_LABELS,
    _ISSUE_SEVERITY,
    _ISSUE_SEVERITY_ORDER,
    CorsAnalyzerPlugin,
)


def _no_findings() -> dict:
    return {
        "target": "https://example.com",
        "domain": "example.com",
        "paths_tested": list(_DEFAULT_PROBE_PATHS),
        "cors_findings": [],
        "bypass_findings": [],
        "jsonp_findings": [],
    }


def _cors_finding(issue_type: str, url: str = "https://example.com/", credentials: bool = False):
    return {
        "url": url,
        "issue_type": issue_type,
        "origin_sent": "https://evil-attacker.example.com",
        "acao_received": "https://evil-attacker.example.com",
        "credentials": credentials,
    }


def _jsonp_finding(url: str = "https://example.com/api/v1/?callback=kast_cors_probe_fn"):
    return {
        "url": url,
        "parameter": "callback",
        "content_type": "application/javascript",
        "response_snippet": "kast_cors_probe_fn({...})",
    }


class TestCorsAnalyzerIdentity(unittest.TestCase):
    """Class-attribute identity must follow the v3 contract."""

    def setUp(self):
        self.plugin = CorsAnalyzerPlugin(Mock(verbose=False))

    def test_identity_class_attributes(self):
        self.assertEqual(CorsAnalyzerPlugin.name, "cors_analyzer")
        self.assertEqual(CorsAnalyzerPlugin.display_name, "Cross-Origin Policy Analyzer")
        self.assertEqual(CorsAnalyzerPlugin.scan_type, "passive")
        self.assertEqual(CorsAnalyzerPlugin.output_type, "stdout")
        self.assertTrue(CorsAnalyzerPlugin.description)
        self.assertTrue(CorsAnalyzerPlugin.website_url.startswith("https://"))

    def test_config_schema_well_formed(self):
        schema = CorsAnalyzerPlugin.config_schema
        self.assertEqual(schema["type"], "object")
        self.assertIn("timeout", schema["properties"])
        self.assertIn("probe_paths", schema["properties"])

    def test_default_config_applied(self):
        self.assertEqual(self.plugin.timeout, 10)
        self.assertEqual(self.plugin.probe_paths, _DEFAULT_PROBE_PATHS)

    def test_is_available_returns_true(self):
        # Pure-Python plugin — no external tool required.
        self.assertTrue(self.plugin.is_available())


class TestNormalizeTarget(unittest.TestCase):
    """Target URL normalization."""

    def setUp(self):
        self.plugin = CorsAnalyzerPlugin(Mock(verbose=False))

    def test_bare_hostname_prepends_https(self):
        self.assertEqual(self.plugin._normalize_target("example.com"), "https://example.com")

    def test_https_url_preserved(self):
        self.assertEqual(
            self.plugin._normalize_target("https://example.com/path"),
            "https://example.com/path",
        )

    def test_http_url_preserved(self):
        # HTTP is preserved as-is — the bypass probe relies on this to decide
        # whether to test the HTTPS→HTTP downgrade pattern.
        self.assertEqual(
            self.plugin._normalize_target("http://example.com"),
            "http://example.com",
        )


class TestPostProcessNoFindings(unittest.TestCase):
    """Empty-findings input produces the expected clean processed dict."""

    def setUp(self):
        self.plugin = CorsAnalyzerPlugin(Mock(verbose=False))
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_no_findings_produces_zero_count_and_empty_issues(self):
        raw = {"disposition": "success", "results": _no_findings()}
        out_path = self.plugin.post_process(raw, self.tmp)
        processed = json.loads(open(out_path).read())

        self.assertEqual(processed["findings_count"], 0)
        self.assertEqual(processed["issues"], [])
        self.assertIn("No cross-origin policy issues", processed["summary"])
        self.assertIn("No cross-origin policy misconfigurations", processed["executive_summary"])

    def test_no_findings_processed_dict_has_required_v3_keys(self):
        raw = {"disposition": "success", "results": _no_findings()}
        out_path = self.plugin.post_process(raw, self.tmp)
        processed = json.loads(open(out_path).read())

        # kast↔kast-web contract: every processed.json carries these keys.
        for required_key in (
            "plugin-name", "plugin-display-name", "plugin-description",
            "plugin-website-url", "timestamp", "findings", "findings_count",
            "summary", "details", "issues", "executive_summary", "custom_html",
        ):
            self.assertIn(required_key, processed)

    def test_no_findings_atomic_write_target(self):
        raw = {"disposition": "success", "results": _no_findings()}
        out_path = self.plugin.post_process(raw, self.tmp)
        # post_process should write to <plugin>_processed.json
        self.assertTrue(out_path.endswith("cors_analyzer_processed.json"))
        self.assertTrue(os.path.exists(out_path))


class TestPostProcessWithFindings(unittest.TestCase):
    """Mixed findings produce the right count, issue list, and severity order."""

    def setUp(self):
        self.plugin = CorsAnalyzerPlugin(Mock(verbose=False))
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_mixed_findings_count_aggregates(self):
        results = _no_findings()
        results["cors_findings"] = [_cors_finding("cors-wildcard-origin")]
        results["bypass_findings"] = [_cors_finding("cors-bypass-subdomain")]
        results["jsonp_findings"] = [_jsonp_finding(), _jsonp_finding()]

        raw = {"disposition": "success", "results": results}
        processed = json.loads(open(self.plugin.post_process(raw, self.tmp)).read())

        # 1 cors + 1 bypass + 2 jsonp = 4 findings.
        self.assertEqual(processed["findings_count"], 4)

    def test_issues_are_unique_by_type(self):
        # Three CORS findings of the same type should still produce one issue ID.
        results = _no_findings()
        results["cors_findings"] = [
            _cors_finding("cors-wildcard-origin", "https://example.com/api/"),
            _cors_finding("cors-wildcard-origin", "https://example.com/v1/"),
            _cors_finding("cors-wildcard-origin", "https://example.com/graphql"),
        ]
        raw = {"disposition": "success", "results": results}
        processed = json.loads(open(self.plugin.post_process(raw, self.tmp)).read())

        self.assertEqual(processed["issues"], ["cors-wildcard-origin"])
        self.assertEqual(processed["findings_count"], 3)

    def test_issues_ordered_by_severity(self):
        # When multiple issue types are present, the worst comes first.
        results = _no_findings()
        results["cors_findings"] = [
            _cors_finding("cors-wildcard-origin"),                     # Low
            _cors_finding("cors-credentials-with-reflected-origin"),   # Critical
            _cors_finding("cors-null-origin-allowed"),                 # Medium
        ]
        raw = {"disposition": "success", "results": results}
        processed = json.loads(open(self.plugin.post_process(raw, self.tmp)).read())

        self.assertEqual(
            processed["issues"][0],
            "cors-credentials-with-reflected-origin",
            "Critical issue must lead the issues list",
        )
        # All three present.
        self.assertEqual(set(processed["issues"]), {
            "cors-wildcard-origin",
            "cors-credentials-with-reflected-origin",
            "cors-null-origin-allowed",
        })

    def test_jsonp_finding_adds_jsonp_issue_id(self):
        results = _no_findings()
        results["jsonp_findings"] = [_jsonp_finding()]
        raw = {"disposition": "success", "results": results}
        processed = json.loads(open(self.plugin.post_process(raw, self.tmp)).read())

        self.assertIn("jsonp-endpoint-detected", processed["issues"])

    def test_summary_names_worst_finding(self):
        results = _no_findings()
        results["cors_findings"] = [_cors_finding("cors-credentials-with-reflected-origin")]
        raw = {"disposition": "success", "results": results}
        processed = json.loads(open(self.plugin.post_process(raw, self.tmp)).read())

        self.assertIn("highest severity", processed["summary"].lower())
        self.assertIn(_ISSUE_LABELS["cors-credentials-with-reflected-origin"], processed["summary"])


class TestPostProcessFailDisposition(unittest.TestCase):
    """Fail input still produces a complete processed.json (kast-web state contract)."""

    def setUp(self):
        self.plugin = CorsAnalyzerPlugin(Mock(verbose=False))
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_fail_disposition_produces_zero_findings_processed_dict(self):
        raw = {"disposition": "fail", "results": "Network unreachable"}
        processed = json.loads(open(self.plugin.post_process(raw, self.tmp)).read())

        self.assertEqual(processed["findings_count"], 0)
        self.assertEqual(processed["issues"], [])
        self.assertIn("could not complete", processed["summary"])


class TestExecutiveSummaryVariants(unittest.TestCase):
    """Each canonical issue type should produce a distinct executive summary."""

    def setUp(self):
        self.plugin = CorsAnalyzerPlugin(Mock(verbose=False))

    def test_credentials_reflected_warns_about_authenticated_requests(self):
        text = self.plugin._generate_executive_summary(
            _no_findings(), ["cors-credentials-with-reflected-origin"]
        )
        self.assertIn("credentials", text.lower())

    def test_bypass_subdomain_mentions_pattern_matching(self):
        text = self.plugin._generate_executive_summary(
            _no_findings(), ["cors-bypass-subdomain"]
        )
        self.assertIn("pattern", text.lower())

    def test_jsonp_explains_cors_bypass(self):
        text = self.plugin._generate_executive_summary(
            _no_findings(), ["jsonp-endpoint-detected"]
        )
        self.assertIn("jsonp", text.lower())


class TestDryRunInfo(unittest.TestCase):
    """get_dry_run_info shape — what shows under `kast scan --dry-run`."""

    def setUp(self):
        self.plugin = CorsAnalyzerPlugin(Mock(verbose=False))

    def test_dry_run_info_returns_expected_shape(self):
        info = self.plugin.get_dry_run_info("example.com", "/tmp")
        self.assertIn("operations", info)
        self.assertIn("description", info)
        # CORS plugin does not shell out, so no commands.
        self.assertEqual(info["commands"], [])
        # Should mention the number of paths + example.com.
        joined = " ".join(info["operations"])
        self.assertIn("example.com", joined)
        self.assertIn(str(len(self.plugin.probe_paths)), joined)


class TestReportOnlyMode(unittest.TestCase):
    """report_only=True reads from the existing cors_analyzer.json."""

    def setUp(self):
        self.plugin = CorsAnalyzerPlugin(Mock(verbose=False))
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_report_only_loads_existing_results(self):
        existing = _no_findings()
        existing["cors_findings"] = [_cors_finding("cors-wildcard-origin")]
        with open(os.path.join(self.tmp, "cors_analyzer.json"), "w") as f:
            json.dump(existing, f)

        result = self.plugin.run("https://example.com", self.tmp, report_only=True)
        self.assertEqual(result["disposition"], "success")
        self.assertEqual(result["results"]["cors_findings"][0]["issue_type"], "cors-wildcard-origin")

    def test_report_only_fails_when_no_existing_results(self):
        result = self.plugin.run("https://example.com", self.tmp, report_only=True)
        self.assertEqual(result["disposition"], "fail")


class TestRegistryCoverage(unittest.TestCase):
    """Every issue ID the plugin can emit must be in the registry."""

    def test_all_issue_ids_present_in_registry(self):
        registry_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "issue_registry.json"
        )
        with open(registry_path) as f:
            registry = json.load(f)

        # Every key in _ISSUE_SEVERITY is an ID the plugin can emit.
        for issue_id in _ISSUE_SEVERITY:
            self.assertIn(
                issue_id, registry,
                f"Issue '{issue_id}' produced by CorsAnalyzerPlugin is missing from "
                f"kast/data/issue_registry.json — kast-web reports would render it "
                f"as 'Issue ID not found.'",
            )

    def test_severity_order_covers_all_known_types(self):
        # Every issue in _ISSUE_SEVERITY should appear in _ISSUE_SEVERITY_ORDER
        # (otherwise it would lose its preferred ordering position in the issues list).
        for issue_id in _ISSUE_SEVERITY:
            self.assertIn(issue_id, _ISSUE_SEVERITY_ORDER)
