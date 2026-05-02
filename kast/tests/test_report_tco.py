"""Tests for kast.report.tco — TCO appendix renderer (Phase C5 / F1)."""

from unittest.mock import patch

from kast.report.tco import compute_tco, format_days, parse_timeframe


def test_parse_timeframe_weeks_range():
    assert parse_timeframe("1-2 weeks") == (7, 14)
    assert parse_timeframe("4-6 weeks") == (28, 42)


def test_parse_timeframe_single_value():
    assert parse_timeframe("1 week") == (7, 7)
    assert parse_timeframe("2 weeks") == (14, 14)


def test_parse_timeframe_days():
    assert parse_timeframe("1-2 days") == (1, 2)
    assert parse_timeframe("3 days") == (3, 3)


def test_parse_timeframe_unparseable():
    assert parse_timeframe(None) is None
    assert parse_timeframe("") is None
    assert parse_timeframe("N/A") is None
    assert parse_timeframe("n/a") is None
    assert parse_timeframe("two weeks") is None
    assert parse_timeframe("immediate") is None


def test_format_days_weekly_range():
    assert format_days(7, 14) == "1-2 weeks"
    assert format_days(28, 42) == "4-6 weeks"


def test_format_days_single():
    assert format_days(7, 7) == "1 week"
    assert format_days(14, 14) == "2 weeks"
    assert format_days(1, 1) == "1 day"


def test_format_days_falls_back_to_days():
    assert format_days(1, 2) == "1-2 days"
    assert format_days(3, 5) == "3-5 days"
    # Mixed week+day → days representation, since not cleanly weekly
    assert format_days(5, 14) == "5-14 days"


def _fake_meta(timeframes_by_id: dict[str, tuple[str | None, str | None]]):
    """Patch get_issue_metadata to return canned timeframes per issue id."""
    def fake(issue_id):
        if issue_id not in timeframes_by_id:
            return None
        code, waf = timeframes_by_id[issue_id]
        return {
            "code_fix_timeframe": code,
            "waf_deployment_timeframe": waf,
        }
    return fake


def test_compute_tco_aggregates_known_timeframes():
    issues = [
        {"id": "A", "display_name": "Issue A", "severity": "High", "category": "X"},
        {"id": "B", "display_name": "Issue B", "severity": "Medium", "category": "X"},
    ]
    fake = _fake_meta({
        "A": ("1-2 weeks", "1-2 days"),
        "B": ("4-6 weeks", "1-2 days"),
    })
    with patch("kast.report.tco.get_issue_metadata", side_effect=fake):
        tco = compute_tco(issues)

    assert tco["issue_count"] == 2
    assert tco["code_fix_count"] == 2
    assert tco["waf_deploy_count"] == 2
    assert tco["totals"]["code_fix_min_days"] == 7 + 28
    assert tco["totals"]["code_fix_max_days"] == 14 + 42
    assert tco["totals"]["code_fix_summary"] == "5-8 weeks"
    assert tco["totals"]["waf_deploy_summary"] == "2-4 days"
    assert tco["has_data"] is True


def test_compute_tco_handles_missing_timeframes():
    """N/A or absent timeframes are excluded from the totals but listed."""
    issues = [
        {"id": "C", "display_name": "Issue C", "severity": "High", "category": "X"},
        {"id": "D", "display_name": "Issue D", "severity": "Low", "category": "Y"},
    ]
    fake = _fake_meta({
        "C": ("1-2 weeks", "1-2 days"),
        "D": ("N/A", None),
    })
    with patch("kast.report.tco.get_issue_metadata", side_effect=fake):
        tco = compute_tco(issues)

    assert tco["code_fix_count"] == 1
    assert tco["waf_deploy_count"] == 1
    assert tco["has_data"] is True

    # Per-issue rows still present for both, even when N/A
    rows = {r["id"]: r for r in tco["per_issue"]}
    assert rows["C"]["code_fix_range"] == "1-2 weeks"
    assert rows["C"]["waf_deploy_range"] == "1-2 days"
    assert rows["D"]["code_fix_range"] == "N/A"
    assert rows["D"]["waf_deploy_range"] == "N/A"


def test_compute_tco_no_known_issues_returns_no_data():
    """If every issue is unregistered, has_data is False."""
    issues = [
        {"id": "UNKNOWN1", "display_name": "x", "severity": "High", "category": "Y"},
    ]
    with patch("kast.report.tco.get_issue_metadata", return_value=None):
        tco = compute_tco(issues)
    assert tco["issue_count"] == 1
    assert tco["code_fix_count"] == 0
    assert tco["waf_deploy_count"] == 0
    assert tco["has_data"] is False


def test_compute_tco_empty_issue_list():
    tco = compute_tco([])
    assert tco["issue_count"] == 0
    assert tco["has_data"] is False
    assert tco["totals"]["code_fix_summary"] == "N/A"
    assert tco["totals"]["waf_deploy_summary"] == "N/A"


def test_compute_tco_handles_issues_without_id():
    """Issues without registry IDs (e.g., string-only entries) don't crash."""
    issues = [{"id": None, "display_name": "raw", "severity": "Low", "category": "Z"}]
    tco = compute_tco(issues)
    assert tco["issue_count"] == 1
    assert tco["code_fix_count"] == 0
    assert tco["has_data"] is False
