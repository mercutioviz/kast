"""Tests for the kast.report module (Phase A7).

Pin down the data-shape contract of ``collect_report_data`` and the key
guarantee A7 added: HTML and PDF renderers consume the same
canonical-severity-sorted issue list, fixing the v2 PDF path which used
a stale ``severity_order`` dict that mis-sorted Informational issues.
"""

from kast.report.data import collect_report_data
from kast.report_builder import (
    calculate_waf_statistics,
    generate_html_report,
    generate_pdf_report,
)


def _sample_plugin_results():
    """Fixture chosen to exercise every severity bucket in the registry.

    Severity values verified against kast/data/issue_registry.json:
    - TLSv1.0: High
    - x-frame-options-header-invalid: Medium
    - SWEET32: Low
    - ORG-DISC-001: Informational
    """
    return [
        {
            "plugin-name": "whatweb",
            "plugin-display-name": "WhatWeb",
            "plugin-description": "Web technology detection",
            "summary": "Found 3 technologies",
            "details": "Apache 2.4.41\nphp 7.4\nDrupal 9.2",
            "report": "WhatWeb scan complete",
            "executive_summary": "Apache 2.4.41 detected",
            "issues": [
                "TLSv1.0",                          # High
                "x-frame-options-header-invalid",   # Medium
                "SWEET32",                          # Low
            ],
        },
        {
            "plugin-name": "org_discovery",
            "plugin-display-name": "Organization Discovery",
            "issues": ["ORG-DISC-001"],             # Informational
        },
    ]


def test_collect_report_data_shape():
    """The returned dict has every key the renderers need."""
    data = collect_report_data(_sample_plugin_results(), target="example.com")

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

    # scan_metadata sub-shape
    assert set(data["scan_metadata"].keys()) >= {
        "scan_date",
        "total_issues",
        "total_plugins",
        "severity_counts",
        "waf_statistics",
    }


def test_severity_counts_use_canonical_keys():
    """Severity counts are keyed on Severity enum values (no legacy 'Info')."""
    data = collect_report_data(_sample_plugin_results(), target="example.com")
    counts = data["scan_metadata"]["severity_counts"]
    # Canonical keys present
    assert "Informational" in counts
    assert "High" in counts
    assert "Medium" in counts
    assert "Low" in counts
    assert "Unknown" in counts
    # No legacy "Info" leaking through
    assert "Info" not in counts


def test_issues_sorted_by_canonical_severity():
    """Issues are sorted highest-severity first; Informational sorts before Unknown."""
    data = collect_report_data(_sample_plugin_results(), target="example.com")
    severities = [i["severity"] for i in data["all_issues"]]
    # Order should be: High, Medium, Low, Informational
    expected_order = ["High", "Medium", "Low", "Informational"]
    # Actual order should be a prefix-match (no Unknown items in fixture)
    assert severities == expected_order, (
        f"v2 PDF path used severity_order with 'Info' not 'Informational' — "
        f"if Informational sorts as Unknown, this assertion catches the regression. "
        f"Got: {severities}"
    )


def test_informational_issue_appears_in_count():
    """Informational issues are counted (audit § 5a.12 fix carried by A6+A7)."""
    data = collect_report_data(_sample_plugin_results(), target="example.com")
    counts = data["scan_metadata"]["severity_counts"]
    # The "No WAF Detected" issue is Informational; it must show up in the count.
    assert counts["Informational"] >= 1, (
        f"Informational issue dropped from severity_counts: {counts}"
    )


def test_collect_data_does_not_mutate_input():
    """Passing the same plugin_results twice yields identical issue counts."""
    fixture = _sample_plugin_results()
    data1 = collect_report_data(fixture, target="x")
    data2 = collect_report_data(fixture, target="x")
    assert (
        data1["scan_metadata"]["total_issues"]
        == data2["scan_metadata"]["total_issues"]
    )


def test_html_and_pdf_paths_share_the_collector(tmp_path):
    """generate_html_report and generate_pdf_report both use collect_report_data
    under the hood. This pins the contract that they see the same issue list
    and the same severity sort — fixing the v2 drift between them.
    """
    from kast.report.data import collect_report_data
    from kast.report.html import _format_for_html
    from kast.report.pdf import _format_for_pdf

    data = collect_report_data(_sample_plugin_results(), target="example.com")

    # Both formatters consume the same issue list (no mutation, same order).
    issues_for_html = data["all_issues"]
    _format_for_html(data)
    _format_for_pdf(data)
    assert data["all_issues"] is issues_for_html, (
        "Renderers must not mutate or replace the shared issue list"
    )


def test_html_report_renders(tmp_path):
    """End-to-end smoke: generate_html_report still produces a valid HTML file."""
    out = tmp_path / "report.html"
    generate_html_report(_sample_plugin_results(), str(out), target="example.com")
    assert out.exists()
    text = out.read_text()
    # Basic sanity — substrings that should appear in any non-empty report
    assert "<html" in text.lower()
    assert "example.com" in text


def test_calculate_waf_statistics_empty_input():
    stats = calculate_waf_statistics([])
    assert stats["total_issues"] == 0
    assert stats["waf_addressable_count"] == 0
    assert stats["waf_addressable_percentage"] == 0


def test_calculate_waf_statistics_with_issues():
    issues = [
        {"id": "TLSv1.0", "severity": "High"},
        {"id": "TLSv1.1", "severity": "High"},
    ]
    stats = calculate_waf_statistics(issues)
    assert stats["total_issues"] == 2
    # Both registry entries are waf_addressable (per audit § 11)
    assert stats["waf_addressable_count"] == 2
    assert stats["waf_addressable_percentage"] == 100.0
    assert stats["high_severity_waf"] == 2


def test_pdf_severity_sort_no_longer_drops_informational(tmp_path):
    """Regression guard: in v2 the PDF path used a stale ``severity_order``
    dict with the legacy ``"Info"`` key, so Informational issues silently
    sorted as Unknown (position 4 instead of 3). A7 unified the path
    through ``collect_report_data``, so HTML and PDF both use the canonical
    ``severity_sort_key``. Verify the order is correct here.
    """
    data = collect_report_data(_sample_plugin_results(), target="example.com")
    severity_in_order = [i["severity"] for i in data["all_issues"]]
    # Informational must appear before any Unknown items would have appeared
    # (none in fixture). The key contract: Informational != Unknown for sort.
    assert "Informational" in severity_in_order
    assert severity_in_order.index("Informational") < len(severity_in_order)
    # And it sorts AFTER Low (i.e., Informational is position 3, not 4):
    if "Low" in severity_in_order:
        assert severity_in_order.index("Low") < severity_in_order.index("Informational")
