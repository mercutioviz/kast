"""Tests for the scan-to-scan comparison feature.

Scan directories are built on the fly in a tmpdir rather than checked in
as fixtures — the diff only reads ``*_processed.json`` and
``kast_info.json``, so synthesizing them keeps the intent of each test
visible at the call site.

The coverage-gating tests are the important ones: a plugin that ran in
the baseline but not in the current scan must never let its issues be
counted as resolved.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from kast.cli.scan import scan
from kast.report.diff import (
    ScanDiffError,
    build_headline,
    compute_diff,
    diff_scans,
    load_scan_snapshot,
)
from kast.report.diff_html import render_diff_html


def _write_scan(root, name, plugins, target="https://example.com", scan_date=None):
    """Create a scan directory. ``plugins`` maps plugin name -> list of issues."""
    scan_dir = Path(root) / name
    scan_dir.mkdir(parents=True)
    for plugin_name, issues in plugins.items():
        payload = {
            "plugin-name": plugin_name,
            "plugin-display-name": plugin_name.title(),
            "findings_count": len(issues),
            "issues": issues,
        }
        (scan_dir / f"{plugin_name}_processed.json").write_text(json.dumps(payload))
    (scan_dir / "kast_info.json").write_text(json.dumps({
        "kast_version": "3.0.40",
        "start_timestamp": scan_date or "2026-08-01T10:00:00.000+00:00",
        "cli_arguments": {"target": target, "mode": "passive"},
    }))
    return str(scan_dir)


def _issue(issue_id, description=""):
    return {"id": issue_id, "description": description or issue_id}


class ScanDiffTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)


class TestLoadScanSnapshot(ScanDiffTestCase):
    def test_reads_target_date_and_version_from_kast_info(self):
        d = _write_scan(self.tmp, "s1", {"testssl": [_issue("SSLv3")]})
        snap = load_scan_snapshot(d)
        self.assertEqual(snap["target"], "https://example.com")
        self.assertEqual(snap["kast_version"], "3.0.40")
        self.assertEqual(snap["mode"], "passive")
        self.assertEqual(snap["scan_date"], "2026-08-01T10:00:00.000+00:00")

    def test_collects_plugins_that_produced_output(self):
        d = _write_scan(self.tmp, "s1", {
            "testssl": [_issue("SSLv3")],
            "whatweb": [],
        })
        self.assertEqual(load_scan_snapshot(d)["plugins"], {"testssl", "whatweb"})

    def test_resolves_registry_metadata(self):
        d = _write_scan(self.tmp, "s1", {"testssl": [_issue("SSLv3")]})
        issue = load_scan_snapshot(d)["issues"][0]
        self.assertEqual(issue["severity"], "High")
        self.assertEqual(issue["display_name"], "SSLv3 Supported")
        self.assertTrue(issue["waf_addressable"])
        self.assertEqual(issue["reported_by_tool"], "testssl")

    def test_unknown_issue_id_degrades_to_unknown_severity(self):
        d = _write_scan(self.tmp, "s1", {"testssl": [_issue("not-in-the-registry")]})
        issue = load_scan_snapshot(d)["issues"][0]
        self.assertEqual(issue["severity"], "Unknown")
        self.assertFalse(issue["waf_addressable"])

    def test_bare_string_issue_is_accepted(self):
        d = _write_scan(self.tmp, "s1", {"testssl": ["SSLv3"]})
        self.assertEqual(load_scan_snapshot(d)["issues"][0]["id"], "SSLv3")

    def test_issue_id_is_stripped(self):
        d = _write_scan(self.tmp, "s1", {"testssl": [_issue("  SSLv3  ")]})
        self.assertEqual(load_scan_snapshot(d)["issues"][0]["display_name"],
                         "SSLv3 Supported")

    def test_severity_counts_cover_every_severity(self):
        d = _write_scan(self.tmp, "s1", {"testssl": [_issue("SSLv3")]})
        counts = load_scan_snapshot(d)["severity_counts"]
        self.assertEqual(counts["High"], 1)
        self.assertIn("Informational", counts)
        self.assertIn("Unknown", counts)

    def test_plugin_name_falls_back_to_filename(self):
        scan_dir = Path(self.tmp) / "s1"
        scan_dir.mkdir()
        (scan_dir / "mystery_processed.json").write_text(json.dumps({"issues": []}))
        self.assertEqual(load_scan_snapshot(str(scan_dir))["plugins"], {"mystery"})

    def test_missing_kast_info_is_tolerated(self):
        scan_dir = Path(self.tmp) / "s1"
        scan_dir.mkdir()
        (scan_dir / "testssl_processed.json").write_text(
            json.dumps({"plugin-name": "testssl", "issues": []}))
        snap = load_scan_snapshot(str(scan_dir))
        self.assertEqual(snap["target"], "s1")
        self.assertIsNone(snap["scan_date"])

    def test_raises_on_nonexistent_directory(self):
        with self.assertRaises(ScanDiffError):
            load_scan_snapshot(Path(self.tmp) / "nope")

    def test_raises_when_no_processed_files(self):
        empty = Path(self.tmp) / "empty"
        empty.mkdir()
        with self.assertRaises(ScanDiffError):
            load_scan_snapshot(str(empty))

    def test_raises_on_malformed_processed_json(self):
        scan_dir = Path(self.tmp) / "s1"
        scan_dir.mkdir()
        (scan_dir / "testssl_processed.json").write_text("{not json")
        with self.assertRaises(ScanDiffError):
            load_scan_snapshot(str(scan_dir))

    def test_null_issues_list_is_tolerated(self):
        scan_dir = Path(self.tmp) / "s1"
        scan_dir.mkdir()
        (scan_dir / "testssl_processed.json").write_text(
            json.dumps({"plugin-name": "testssl", "issues": None}))
        self.assertEqual(load_scan_snapshot(str(scan_dir))["issues"], [])


class TestComputeDiff(ScanDiffTestCase):
    def _diff(self, baseline_plugins, current_plugins, **kwargs):
        b = _write_scan(self.tmp, "base", baseline_plugins,
                        target=kwargs.get("baseline_target", "https://example.com"))
        c = _write_scan(self.tmp, "curr", current_plugins,
                        target=kwargs.get("current_target", "https://example.com"))
        return diff_scans(b, c)

    def test_resolved_issue_is_detected(self):
        diff = self._diff({"testssl": [_issue("SSLv3")]}, {"testssl": []})
        self.assertEqual(diff["summary"]["resolved_count"], 1)
        self.assertEqual(diff["resolved_issues"][0]["id"], "SSLv3")
        self.assertEqual(diff["summary"]["new_count"], 0)

    def test_new_issue_is_detected(self):
        diff = self._diff({"testssl": []}, {"testssl": [_issue("SSLv3")]})
        self.assertEqual(diff["summary"]["new_count"], 1)
        self.assertEqual(diff["new_issues"][0]["id"], "SSLv3")

    def test_persisting_issue_is_neither_new_nor_resolved(self):
        diff = self._diff({"testssl": [_issue("SSLv3")]}, {"testssl": [_issue("SSLv3")]})
        self.assertEqual(diff["summary"]["persisting_count"], 1)
        self.assertEqual(diff["summary"]["new_count"], 0)
        self.assertEqual(diff["summary"]["resolved_count"], 0)

    def test_same_id_from_different_plugins_is_two_identities(self):
        diff = self._diff(
            {"testssl": [_issue("SSLv3")]},
            {"whatweb": [_issue("SSLv3")]},
        )
        self.assertEqual(len(diff["resolved_issues"]), 1)
        self.assertEqual(len(diff["new_issues"]), 1)
        self.assertEqual(diff["summary"]["persisting_count"], 0)

    def test_occurrences_collapse_with_a_delta(self):
        diff = self._diff(
            {"testssl": [_issue("SSLv3", f"host{i}") for i in range(5)]},
            {"testssl": [_issue("SSLv3", "host0"), _issue("SSLv3", "host1")]},
        )
        entry = diff["persisting_issues"][0]
        self.assertEqual(entry["baseline_occurrences"], 5)
        self.assertEqual(entry["occurrences"], 2)
        self.assertEqual(entry["occurrence_delta"], -3)

    def test_descriptions_are_deduped(self):
        diff = self._diff(
            {"testssl": []},
            {"testssl": [_issue("SSLv3", "same"), _issue("SSLv3", "same"),
                         _issue("SSLv3", "other")]},
        )
        self.assertEqual(diff["new_issues"][0]["descriptions"], ["same", "other"])

    def test_severity_deltas_cover_all_severities(self):
        diff = self._diff({"testssl": [_issue("SSLv3")]}, {"testssl": []})
        deltas = diff["summary"]["severity_deltas"]
        self.assertEqual(deltas["High"], -1)
        self.assertEqual(set(deltas),
                         {"Critical", "High", "Medium", "Low", "Informational", "Unknown"})

    def test_total_delta(self):
        diff = self._diff(
            {"testssl": [_issue("SSLv3"), _issue("TLSv1.0")]},
            {"testssl": [_issue("SSLv3")]},
        )
        self.assertEqual(diff["summary"]["total_delta"], -1)

    def test_waf_addressable_resolved_counts_only_waf_issues(self):
        diff = self._diff(
            {"testssl": [_issue("SSLv3"), _issue("not-in-the-registry")]},
            {"testssl": []},
        )
        self.assertEqual(diff["summary"]["resolved_count"], 2)
        self.assertEqual(diff["summary"]["waf_addressable_resolved"], 1)

    def test_issues_sorted_highest_severity_first(self):
        diff = self._diff(
            {"testssl": [_issue("X-Powered-By"), _issue("SSLv3")]},
            {"testssl": []},
        )
        self.assertEqual([e["severity"] for e in diff["resolved_issues"]],
                         ["High", "Medium"])

    def test_equal_severity_sorted_by_occurrence_count_descending(self):
        diff = self._diff(
            {"testssl": [_issue("SSLv3"), _issue("TLSv1.0"), _issue("TLSv1.0")]},
            {"testssl": []},
        )
        self.assertEqual([e["id"] for e in diff["resolved_issues"]],
                         ["TLSv1.0", "SSLv3"])

    def test_target_mismatch_is_flagged(self):
        diff = self._diff({"testssl": []}, {"testssl": []},
                          current_target="https://other.example.org")
        self.assertFalse(diff["summary"]["target_match"])

    def test_target_match_when_identical(self):
        diff = self._diff({"testssl": [_issue("SSLv3")]}, {"testssl": [_issue("SSLv3")]})
        self.assertTrue(diff["summary"]["target_match"])

    def test_plugins_key_not_leaked_into_output(self):
        diff = self._diff({"testssl": []}, {"testssl": []})
        self.assertNotIn("plugins", diff["baseline"])
        self.assertNotIn("issues", diff["baseline"])

    def test_compute_diff_accepts_snapshots_directly(self):
        b = load_scan_snapshot(_write_scan(self.tmp, "base", {"testssl": [_issue("SSLv3")]}))
        c = load_scan_snapshot(_write_scan(self.tmp, "curr", {"testssl": []}))
        self.assertEqual(compute_diff(b, c)["summary"]["resolved_count"], 1)


class TestCoverageGating(ScanDiffTestCase):
    """A plugin that did not run on both sides cannot support a claim."""

    def _diff(self, baseline_plugins, current_plugins):
        return diff_scans(
            _write_scan(self.tmp, "base", baseline_plugins),
            _write_scan(self.tmp, "curr", current_plugins),
        )

    def test_dropped_plugin_issues_are_not_counted_as_resolved(self):
        diff = self._diff({"testssl": [_issue("SSLv3")]}, {"whatweb": []})
        self.assertEqual(diff["summary"]["resolved_count"], 0)
        self.assertEqual(diff["summary"]["unverifiable_resolved_count"], 1)
        self.assertTrue(diff["resolved_issues"][0]["coverage_gap"])

    def test_added_plugin_issues_are_not_counted_as_new(self):
        diff = self._diff({"testssl": []}, {"testssl": [], "whatweb": [_issue("SSLv3")]})
        self.assertEqual(diff["summary"]["new_count"], 0)
        self.assertEqual(diff["summary"]["unverifiable_new_count"], 1)
        self.assertTrue(diff["new_issues"][0]["coverage_gap"])

    def test_issues_from_shared_plugins_stay_countable(self):
        diff = self._diff(
            {"testssl": [_issue("SSLv3")], "whatweb": [_issue("X-Powered-By")]},
            {"testssl": []},
        )
        by_id = {e["id"]: e for e in diff["resolved_issues"]}
        self.assertFalse(by_id["SSLv3"]["coverage_gap"])
        self.assertTrue(by_id["X-Powered-By"]["coverage_gap"])
        self.assertEqual(diff["summary"]["resolved_count"], 1)

    def test_has_coverage_gap_set_when_plugin_dropped(self):
        diff = self._diff({"testssl": [], "whatweb": []}, {"testssl": []})
        self.assertTrue(diff["summary"]["has_coverage_gap"])
        self.assertEqual(diff["coverage"]["baseline_only"], ["whatweb"])
        self.assertEqual(diff["coverage"]["current_only"], [])

    def test_has_coverage_gap_set_when_plugin_added(self):
        diff = self._diff({"testssl": []}, {"testssl": [], "whatweb": []})
        self.assertTrue(diff["summary"]["has_coverage_gap"])
        self.assertEqual(diff["coverage"]["current_only"], ["whatweb"])

    def test_no_coverage_gap_when_plugin_sets_match(self):
        diff = self._diff({"testssl": [], "whatweb": []}, {"whatweb": [], "testssl": []})
        self.assertFalse(diff["summary"]["has_coverage_gap"])
        self.assertEqual(diff["coverage"]["shared"], ["testssl", "whatweb"])

    def test_waf_addressable_resolved_excludes_coverage_gaps(self):
        diff = self._diff({"testssl": [_issue("SSLv3")]}, {"whatweb": []})
        self.assertEqual(diff["summary"]["waf_addressable_resolved"], 0)


class TestBuildHeadline(ScanDiffTestCase):
    def _headline(self, baseline_plugins, current_plugins):
        return build_headline(diff_scans(
            _write_scan(self.tmp, "base", baseline_plugins),
            _write_scan(self.tmp, "curr", current_plugins),
        ))

    def test_resolved_only(self):
        text = self._headline({"testssl": [_issue("SSLv3")]}, {"testssl": []})
        self.assertIn("no longer", text)
        self.assertIn("no new issues", text)

    def test_new_only(self):
        text = self._headline({"testssl": []}, {"testssl": [_issue("SSLv3")]})
        self.assertIn("none were resolved", text)

    def test_both_directions(self):
        text = self._headline(
            {"testssl": [_issue("SSLv3")]},
            {"testssl": [_issue("X-Powered-By")]},
        )
        self.assertIn("no longer detected", text)
        self.assertIn("new issue type(s) appeared", text)

    def test_no_change(self):
        text = self._headline({"testssl": [_issue("SSLv3")]},
                              {"testssl": [_issue("SSLv3")]})
        self.assertIn("No change", text)

    def test_no_issues_at_all(self):
        self.assertIn("No issues detected", self._headline({"testssl": []},
                                                           {"testssl": []}))

    def test_headline_names_the_target(self):
        text = self._headline({"testssl": [_issue("SSLv3")]}, {"testssl": []})
        self.assertIn("https://example.com", text)


class TestRenderDiffHtml(ScanDiffTestCase):
    def _render(self, baseline_plugins, current_plugins):
        diff = diff_scans(
            _write_scan(self.tmp, "base", baseline_plugins),
            _write_scan(self.tmp, "curr", current_plugins),
        )
        out = Path(self.tmp) / "comparison.html"
        render_diff_html(diff, str(out))
        return out.read_text()

    def test_renders_a_self_contained_document(self):
        html = self._render({"testssl": [_issue("SSLv3")]}, {"testssl": []})
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<style>", html)
        self.assertNotIn("kast_style.css", html)

    def test_includes_resolved_issue_and_headline(self):
        html = self._render({"testssl": [_issue("SSLv3")]}, {"testssl": []})
        self.assertIn("SSLv3 Supported", html)
        self.assertIn("no longer", html)

    def test_coverage_warning_rendered_when_plugins_differ(self):
        html = self._render({"testssl": [_issue("SSLv3")]}, {"whatweb": []})
        self.assertIn("Plugin coverage differs", html)
        self.assertIn("gap-marker", html)

    def test_no_coverage_warning_when_plugins_match(self):
        html = self._render({"testssl": [_issue("SSLv3")]}, {"testssl": []})
        self.assertNotIn("Plugin coverage differs", html)

    def test_target_mismatch_banner(self):
        diff = diff_scans(
            _write_scan(self.tmp, "base", {"testssl": []}),
            _write_scan(self.tmp, "curr", {"testssl": []},
                        target="https://other.example.org"),
        )
        out = Path(self.tmp) / "c.html"
        render_diff_html(diff, str(out))
        self.assertIn("Targets differ", out.read_text())

    def test_empty_sections_render_placeholder_text(self):
        html = self._render({"testssl": []}, {"testssl": []})
        self.assertIn("No new issues appeared", html)

    def test_issue_description_is_escaped(self):
        html = self._render(
            {"testssl": []},
            {"testssl": [_issue("SSLv3", "<script>alert(1)</script>")]},
        )
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class TestRenderDiffHtmlAiNarrative(ScanDiffTestCase):
    def _render(self, **kwargs):
        diff = diff_scans(
            _write_scan(self.tmp, "base", {"testssl": [_issue("SSLv3")]}),
            _write_scan(self.tmp, "curr", {"testssl": []}),
        )
        out = Path(self.tmp) / "comparison.html"
        render_diff_html(diff, str(out), **kwargs)
        return out.read_text()

    def test_no_narrative_block_when_absent(self):
        html = self._render()
        self.assertNotIn('<div class="ai-narrative-block">', html)
        self.assertNotIn("AI narrative unavailable", html)
        self.assertIn('class="headline"', html)

    def test_narrative_is_rendered(self):
        html = self._render(ai_narrative={
            "headline": "Transport security improved.",
            "narrative": "First paragraph.\n\nSecond paragraph.",
            "notable_changes": ["SSLv3 removed"],
            "caveats": ["nikto did not re-run"],
            "_meta": {"model": "claude-sonnet-4-6"},
        })
        self.assertIn("Transport security improved.", html)
        self.assertIn("<p>First paragraph.</p>", html)
        self.assertIn("<p>Second paragraph.</p>", html)
        self.assertIn("SSLv3 removed", html)
        self.assertIn("nikto did not re-run", html)
        self.assertIn("claude-sonnet-4-6", html)

    def test_deterministic_headline_still_rendered_alongside_narrative(self):
        html = self._render(ai_narrative={"headline": "h", "narrative": "n"})
        self.assertIn('class="headline"', html)
        self.assertIn("no longer", html)

    def test_model_output_is_escaped(self):
        html = self._render(ai_narrative={
            "headline": "<script>alert(1)</script>",
            "narrative": "<img src=x onerror=alert(2)>",
            "notable_changes": ["<b>bold</b>"],
        })
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<b>bold</b>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_error_banner_rendered(self):
        html = self._render(ai_error="API key not configured")
        self.assertIn("AI narrative unavailable", html)
        self.assertIn("API key not configured", html)
        self.assertIn('class="headline"', html)


class TestScanDiffCommand(ScanDiffTestCase):
    def setUp(self):
        super().setUp()
        self.runner = CliRunner()
        self.base = _write_scan(self.tmp, "base", {"testssl": [_issue("SSLv3")]})
        self.curr = _write_scan(self.tmp, "curr", {"testssl": []})

    def _run(self, *extra):
        return self.runner.invoke(scan, ["diff", self.base, self.curr, *extra])

    def test_prints_comparison(self):
        result = self.runner.invoke(scan, ["diff", self.base, self.curr])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Scan comparison", result.output)
        self.assertIn("SSLv3", result.output)

    def test_json_output_is_parseable(self):
        result = self.runner.invoke(scan, ["diff", self.base, self.curr, "--json"])
        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.output)
        self.assertEqual(payload["summary"]["resolved_count"], 1)

    def test_html_flag_writes_a_file(self):
        out = Path(self.tmp) / "out.html"
        result = self.runner.invoke(
            scan, ["diff", self.base, self.curr, "--html", str(out)])
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(out.is_file())
        self.assertIn("SSLv3 Supported", out.read_text())

    def test_persisting_hidden_by_default(self):
        base = _write_scan(self.tmp, "b2", {"testssl": [_issue("SSLv3")]})
        curr = _write_scan(self.tmp, "c2", {"testssl": [_issue("SSLv3")]})
        result = self.runner.invoke(scan, ["diff", base, curr])
        self.assertIn("--show-persisting", result.output)
        self.assertNotIn("SSLv3 Supported", result.output)

    def test_show_persisting_lists_them(self):
        base = _write_scan(self.tmp, "b2", {"testssl": [_issue("SSLv3")]})
        curr = _write_scan(self.tmp, "c2", {"testssl": [_issue("SSLv3")]})
        result = self.runner.invoke(scan, ["diff", base, curr, "--show-persisting"])
        self.assertIn("SSLv3 Supported", result.output)

    def test_exits_nonzero_on_unusable_scan_dir(self):
        empty = Path(self.tmp) / "empty"
        empty.mkdir()
        result = self.runner.invoke(scan, ["diff", self.base, str(empty)])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("No *_processed.json files", result.output)

    def test_missing_directory_rejected_by_click(self):
        result = self.runner.invoke(
            scan, ["diff", self.base, str(Path(self.tmp) / "nope")])
        self.assertEqual(result.exit_code, 2)

    def test_coverage_warning_shown(self):
        curr = _write_scan(self.tmp, "c3", {"whatweb": []})
        result = self.runner.invoke(scan, ["diff", self.base, curr])
        self.assertIn("Plugin coverage differs", result.output)

    def test_ai_flags_listed_in_help(self):
        result = CliRunner().invoke(scan, ["diff", "--help"])
        self.assertIn("--ai-summary", result.output)
        self.assertIn("--ai-endpoint", result.output)

    def test_no_adapter_touched_without_the_flag(self):
        with mock.patch("kast.ai.config.get_ai_adapter") as fake:
            self._run()
        fake.assert_not_called()

    def test_ai_narrative_printed_alongside_deterministic_headline(self):
        narrative = {
            "headline": "Transport security improved.",
            "narrative": "SSLv3 is gone.",
            "notable_changes": ["SSLv3 removed"],
            "caveats": [],
            "_meta": {"model": "claude-sonnet-4-6"},
        }
        with mock.patch("kast.ai.config.get_ai_adapter"), \
             mock.patch("kast.ai.diff_narrative.generate_diff_narrative",
                        return_value=narrative):
            result = self._run("--ai-summary")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Transport security improved.", result.output)
        self.assertIn("SSLv3 removed", result.output)
        self.assertIn("no longer detected", result.output)

    def test_ai_failure_degrades_to_deterministic_output(self):
        with mock.patch("kast.ai.config.get_ai_adapter",
                        side_effect=RuntimeError("no API key")):
            result = self._run("--ai-summary")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("AI narrative unavailable", result.output)
        self.assertIn("no longer detected", result.output)

    def test_target_mismatch_warning_shown(self):
        curr = _write_scan(self.tmp, "c4", {"testssl": []},
                           target="https://other.example.org")
        result = self.runner.invoke(scan, ["diff", self.base, curr])
        self.assertIn("targets differ", result.output)
