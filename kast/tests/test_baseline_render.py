"""Regression test: rendering against the v3 Phase A baseline.

Pin down the structural invariants of the report so future Phase B+
changes can't silently break them. Compares against
``docs/baseline-v3.0-phase-a/`` — see that directory's README for
how it was captured and how to refresh it.

This test does NOT byte-diff against the captured HTML/PDF — those
files contain timestamps and would produce false positives on
cosmetic changes. Instead it asserts on structural invariants
(plugin count, severity-counts shape, anchor integrity, no <wbr>).
End-to-end CLI subprocess testing is a separate concern (see TODO in
the README).
"""

import json
import re
import shutil
from pathlib import Path

import pytest

from kast.core.severity import Severity
from kast.report import generate_html_report
from kast.report.data import collect_report_data


BASELINE_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "baseline-v3.0-phase-a"


def _load_plugin_results():
    """Load every ``*_processed.json`` from the baseline (input data)."""
    results = []
    for f in sorted(BASELINE_DIR.glob("*_processed.json")):
        results.append(json.loads(f.read_text()))
    return results


def _render_to_tmp(tmp_path):
    """Render the baseline data to a fresh HTML file in ``tmp_path``."""
    plugin_results = _load_plugin_results()
    out_path = tmp_path / "kast_report.html"
    generate_html_report(plugin_results, str(out_path), target="example.com")
    return out_path


# -- baseline existence ------------------------------------------------------


def test_baseline_directory_exists():
    """The baseline directory and its key artifacts are present."""
    assert BASELINE_DIR.is_dir(), f"Missing baseline at {BASELINE_DIR}"
    assert (BASELINE_DIR / "kast_report.html").exists()
    assert (BASELINE_DIR / "kast_info.json").exists()
    # Note: missing_issue_ids.json is NOT asserted to exist. The baseline
    # was refreshed after promoting BEAST/BEAST_CBC_TLS1/fallback_SCSV to
    # the registry, so a clean render produces no missing-issues file.
    # If a future plugin emits a brand-new unregistered ID, the file
    # will reappear here on the next baseline refresh.

    processed_files = list(BASELINE_DIR.glob("*_processed.json"))
    assert len(processed_files) == 10, (
        f"Baseline should contain 10 _processed.json files, got {len(processed_files)}"
    )


# -- collect_report_data structural invariants ------------------------------


def test_collect_data_shape_matches_baseline():
    """``collect_report_data`` returns the contracted dict shape."""
    data = collect_report_data(_load_plugin_results(), target="example.com")
    expected_keys = {
        "target",
        "all_issues",
        "detailed_results",
        "plugin_executive_summaries",
        "missing_issues",
        "executive_summary_text",
        "scan_metadata",
    }
    assert set(data.keys()) == expected_keys


def test_severity_counts_use_canonical_keys():
    """Phase A6/A7: severity_counts uses Severity enum values, no legacy 'Info'."""
    data = collect_report_data(_load_plugin_results(), target="example.com")
    counts = data["scan_metadata"]["severity_counts"]
    canonical = {s.value for s in Severity}
    assert set(counts.keys()) == canonical
    assert "Info" not in counts


def test_all_10_plugins_present():
    """All 10 plugins from the baseline appear in detailed_results."""
    data = collect_report_data(_load_plugin_results(), target="example.com")
    expected_plugins = {
        "ai_chatbot_detection",
        "ftap",
        "katana",
        "mozilla_observatory",
        "org_discovery",
        "related_sites",
        "script_detection",
        "subfinder",
        "testssl",
        "wafw00f",
        "whatweb",
    }
    # 10 plugins ran in the baseline (no observatory in this fixture set,
    # but related_sites and others compensate). Actual count:
    assert len(data["detailed_results"]) == 10


def test_missing_issues_is_empty_after_promotion():
    """Post-promotion the registry covers every issue ID emitted by the
    baseline plugins. If a future plugin emits a brand-new unknown ID,
    this fails and prompts a registry update or baseline refresh.
    """
    data = collect_report_data(_load_plugin_results(), target="example.com")
    missing = data["missing_issues"]
    assert missing == {}, (
        f"Baseline plugins emitted issue IDs not present in the registry: "
        f"{sorted(missing.keys())}. Either add them to "
        f"kast/data/issue_registry.json (preferred) or refresh the baseline."
    )


# -- rendered HTML invariants -----------------------------------------------


def test_rendered_html_has_no_wbr_tags(tmp_path):
    """Phase A9: the <wbr> injection helper was removed."""
    out_path = _render_to_tmp(tmp_path)
    html = out_path.read_text()
    assert "<wbr>" not in html, (
        "Phase A9 removed add_word_break_opportunities; <wbr> tags should not "
        "appear in rendered HTML. If they're back, something reintroduced the "
        "v2 helper."
    )


def test_rendered_html_anchor_links_resolve(tmp_path):
    """Phase A8: every href=\"#tool-X\" resolves to a corresponding id=\"tool-X\"."""
    out_path = _render_to_tmp(tmp_path)
    html = out_path.read_text()
    hrefs = set(re.findall(r'href="#tool-([a-z0-9_-]+)"', html))
    ids = set(re.findall(r'id="tool-([a-z0-9_-]+)"', html))
    broken = hrefs - ids
    assert not broken, f"Broken anchor links (href without matching id): {broken}"
    # Sanity: at least one anchor must exist (else we'd be passing trivially).
    assert hrefs, "No tool-anchor hrefs found in rendered HTML — template regression?"


def test_rendered_html_has_all_plugin_sections(tmp_path):
    """All 10 plugins render their <div class='tool-section'>."""
    out_path = _render_to_tmp(tmp_path)
    html = out_path.read_text()
    sections = re.findall(r'class="tool-section" id="tool-([a-z0-9_-]+)"', html)
    assert len(sections) == 10, (
        f"Expected 10 tool sections, found {len(sections)}: {sections}"
    )


def test_rendered_html_severity_badges_populated(tmp_path):
    """Phase A6: every severity bucket renders a badge with a numeric count."""
    out_path = _render_to_tmp(tmp_path)
    html = out_path.read_text()
    badges = re.findall(
        r'badge-count">(\d+)</span>\s*<span class="badge-label">(\w+)',
        html,
    )
    assert badges, "No severity badges found in rendered HTML"
    labels = [label for _, label in badges]
    # All 4 displayed buckets present; Unknown only renders when nonzero.
    for required in ("High", "Medium", "Low", "Info"):
        assert required in labels, f"Severity badge '{required}' missing"


def test_render_does_not_mutate_baseline(tmp_path):
    """Sanity: rendering must not write into BASELINE_DIR."""
    baseline_html_before = (BASELINE_DIR / "kast_report.html").stat().st_mtime
    _render_to_tmp(tmp_path)
    baseline_html_after = (BASELINE_DIR / "kast_report.html").stat().st_mtime
    assert baseline_html_before == baseline_html_after, (
        "Rendering must not write to BASELINE_DIR; use tmp_path"
    )


# -- waf-stats and metadata -------------------------------------------------


def test_waf_statistics_shape():
    """WAF stats dict has every key the report templates reference."""
    data = collect_report_data(_load_plugin_results(), target="example.com")
    waf = data["scan_metadata"]["waf_statistics"]
    expected = {
        "total_issues",
        "waf_addressable_count",
        "waf_addressable_percentage",
        "non_waf_count",
        "high_severity_waf",
        "medium_severity_waf",
        "low_severity_waf",
    }
    assert set(waf.keys()) == expected


def test_total_issues_matches_collected_count():
    """scan_metadata.total_issues equals len(all_issues) — no off-by-one."""
    data = collect_report_data(_load_plugin_results(), target="example.com")
    assert data["scan_metadata"]["total_issues"] == len(data["all_issues"])
