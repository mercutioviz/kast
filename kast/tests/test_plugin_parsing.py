"""Fixture-based plugin parsing tests.

Each test loads a saved real-tool output file from kast/tests/fixtures/ and
runs it through the full parse → extract_issues → post_process pipeline.
These tests verify the parsing logic without needing the external tool
installed, and will catch output-format changes after tool updates.

Fixtures are real scan outputs committed to the repo. When a tool update
changes its output format, update the fixture to match the new format AND
update the plugin's parsing code.

Calling convention:
  ExternalToolPlugin subclasses (wafw00f, whatweb):
    run() calls _read_raw_output(path) → parsed JSON dict/list → stored in results
    post_process receives {"disposition":"success", "results": <parsed JSON>, ...}

  KastPlugin subclasses (testssl, cors_analyzer, observatory):
    Same pattern — pass parsed JSON dict as results.

  The processed output dict does NOT have a top-level "disposition" field.
  Use "plugin-name" or "findings_count" to confirm successful processing.
  The only exception: testssl's fail guard returns a dict with "disposition":"fail".
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from kast.config_manager import ConfigManager

FIXTURES = Path(__file__).parent / "fixtures"


def _make_plugin(plugin_class):
    cli_args = Mock()
    cli_args.verbose = False
    cli_args.set = []
    config_manager = ConfigManager(cli_args)
    return plugin_class(cli_args, config_manager)


def _run_result(disposition, results, timestamp=""):
    return {"disposition": disposition, "results": results, "timestamp": timestamp}


def _post_process_and_read(plugin, run_result, tmpdir):
    """Call post_process and return the processed JSON dict.

    post_process() returns a path string for most plugins. Read and parse it.
    For testssl's fail guard it returns a dict directly.
    """
    out = plugin.post_process(run_result, tmpdir)
    if isinstance(out, dict):
        return out
    with open(out) as f:
        return json.load(f)


def _load_fixture(path):
    with open(path) as f:
        return json.load(f)


class TestWafw00fParsing(unittest.TestCase):
    """wafw00f: Barracuda detection, Generic-entry stripping."""

    def setUp(self):
        from kast.plugins.wafw00f_plugin import Wafw00fPlugin
        self.plugin = _make_plugin(Wafw00fPlugin)
        self.fixture = FIXTURES / "wafw00f_output.json"

    def test_fixture_exists(self):
        self.assertTrue(self.fixture.exists(), f"Fixture missing: {self.fixture}")

    def _process(self, tmpdir):
        raw = _load_fixture(self.fixture)
        return _post_process_and_read(
            self.plugin, _run_result("success", raw), tmpdir
        )

    def test_post_process_runs_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            self.assertEqual(result.get("plugin-name"), "wafw00f")
            self.assertIn("findings_count", result)

    def test_generic_entry_stripped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            findings = result.get("findings", {})
            results_list = findings.get("results", []) if isinstance(findings, dict) else []
            names = [r.get("firewall", "") for r in results_list]
            self.assertNotIn("Generic", names, "Generic WAF entry should be stripped")

    def test_barracuda_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            findings = result.get("findings", {})
            results_list = findings.get("results", []) if isinstance(findings, dict) else []
            names = [r.get("firewall", "") for r in results_list]
            self.assertIn("Barracuda", names)

    def test_findings_count_positive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            self.assertGreater(result.get("findings_count", 0), 0)

    def test_processed_json_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = _load_fixture(self.fixture)
            self.plugin.post_process(_run_result("success", raw), tmpdir)
            self.assertTrue((Path(tmpdir) / "wafw00f_processed.json").exists())


class TestWhatWebParsing(unittest.TestCase):
    """whatweb: JQuery EOL detection, issues emitted."""

    def setUp(self):
        from kast.plugins.whatweb_plugin import WhatWebPlugin
        self.plugin = _make_plugin(WhatWebPlugin)
        self.fixture = FIXTURES / "whatweb_output.json"

    def test_fixture_exists(self):
        self.assertTrue(self.fixture.exists(), f"Fixture missing: {self.fixture}")

    def _process(self, tmpdir):
        raw = _load_fixture(self.fixture)
        return _post_process_and_read(
            self.plugin, _run_result("success", raw), tmpdir
        )

    def test_post_process_runs_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            self.assertEqual(result.get("plugin-name"), "whatweb")
            self.assertIn("findings_count", result)

    def test_findings_count_positive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            self.assertGreater(result.get("findings_count", 0), 0)

    def test_eol_jquery_detected(self):
        # Fixture contains jQuery 1.8.2 which is below the (3,0) EOL boundary.
        # WhatWeb reports the plugin name as "JQuery" (capital J, lowercase q).
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            issues = result.get("issues", [])
            issue_ids = [i.get("id") if isinstance(i, dict) else i for i in issues]
            self.assertIn(
                "whatweb-eol-technology", issue_ids,
                "jQuery 1.8.2 should trigger whatweb-eol-technology issue "
                "(check _EOL_TECHNOLOGIES key is 'JQuery' not 'jQuery')"
            )


class TestTestsslParsing(unittest.TestCase):
    """testssl: protocols parsed, cert fields extracted, cert-expiring-soon emitted."""

    def setUp(self):
        from kast.plugins.testssl_plugin import TestsslPlugin
        self.plugin = _make_plugin(TestsslPlugin)
        self.fixture = FIXTURES / "testssl_output.json"

    def test_fixture_exists(self):
        self.assertTrue(self.fixture.exists(), f"Fixture missing: {self.fixture}")

    def _process(self, tmpdir):
        raw = _load_fixture(self.fixture)
        return _post_process_and_read(
            self.plugin, _run_result("success", raw), tmpdir
        )

    def test_post_process_runs_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            self.assertIn("findings_count", result)

    def test_cert_expiring_soon_detected(self):
        # Fixture has cert_expirationStatus = "expires < 30 days (19)"
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            issues = result.get("issues", [])
            issue_ids = [i.get("id") if isinstance(i, dict) else i for i in issues]
            self.assertIn(
                "cert-expiring-soon", issue_ids,
                "cert expiring <30 days should trigger cert-expiring-soon"
            )

    def test_fail_disposition_produces_honest_summary(self):
        # When run() returns disposition="fail", post_process must NOT produce
        # a misleading "no issues found" summary.
        with tempfile.TemporaryDirectory() as tmpdir:
            fail_result = _run_result(
                "fail",
                "/usr/local/bin/testssl: unrecognized option \"--connect-timeout\""
            )
            result = _post_process_and_read(self.plugin, fail_result, tmpdir)
            self.assertEqual(result.get("disposition"), "fail")
            summary = result.get("summary", "")
            self.assertIn("fail", summary.lower(),
                          "Failure summary must mention 'fail', not claim all-clear")
            self.assertNotIn("No vulnerabilities", summary)
            self.assertNotIn("appears secure", summary)


class TestCorsAnalyzerParsing(unittest.TestCase):
    """cors_analyzer: wildcard origin → issue emitted, findings_count correct."""

    def setUp(self):
        from kast.plugins.cors_analyzer_plugin import CorsAnalyzerPlugin
        self.plugin = _make_plugin(CorsAnalyzerPlugin)
        self.fixture = FIXTURES / "cors_analyzer_output.json"

    def test_fixture_exists(self):
        self.assertTrue(self.fixture.exists(), f"Fixture missing: {self.fixture}")

    def _process(self, tmpdir):
        raw = _load_fixture(self.fixture)
        return _post_process_and_read(
            self.plugin, _run_result("success", raw), tmpdir
        )

    def test_post_process_runs_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            self.assertIn("findings_count", result)

    def test_wildcard_origin_issue_emitted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            issues = result.get("issues", [])
            issue_ids = [i.get("id") if isinstance(i, dict) else i for i in issues]
            self.assertIn(
                "cors-wildcard-origin", issue_ids,
                "Fixture has wildcard CORS findings — cors-wildcard-origin must be emitted"
            )

    def test_findings_count_matches_fixture(self):
        raw = _load_fixture(self.fixture)
        expected = len(raw.get("cors_findings", []))
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            self.assertEqual(result.get("findings_count"), expected)


class TestObservatoryParsing(unittest.TestCase):
    """observatory: grade/score parsed, failed tests map to issues."""

    def setUp(self):
        from kast.plugins.observatory_plugin import ObservatoryPlugin
        self.plugin = _make_plugin(ObservatoryPlugin)
        self.fixture = FIXTURES / "observatory_output.json"

    def test_fixture_exists(self):
        self.assertTrue(self.fixture.exists(), f"Fixture missing: {self.fixture}")

    def _process(self, tmpdir):
        raw = _load_fixture(self.fixture)
        return _post_process_and_read(
            self.plugin, _run_result("success", raw), tmpdir
        )

    def test_post_process_runs_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            self.assertIn("findings_count", result)

    def test_grade_and_score_in_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            summary = result.get("summary", "")
            self.assertIn("C-", summary, "Grade C- should appear in summary")
            self.assertIn("45", summary, "Score 45 should appear in summary")

    def test_failed_tests_become_issues(self):
        # Fixture has 4 failed tests: CSP, HSTS, SRI, x-content-type-options
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._process(tmpdir)
            self.assertGreaterEqual(result.get("findings_count", 0), 4)


if __name__ == "__main__":
    unittest.main()
