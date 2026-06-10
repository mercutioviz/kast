"""Tests for ``kast scan`` group + ``list/show/rerun`` subcommands.

Exercises the Click invocation surface. Heavy actual-scan logic is
exercised by other integration tests; here we focus on the new
subcommands that didn't exist in v2.
"""

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kast.cli.scan import (
    _read_scan_metadata,
)
from kast.cli.scan import (
    scan as scan_group,
)

# Reuse the v3 baseline as a known-good scan dir fixture
BASELINE_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "baseline-v3.0-phase-a"


# -- _read_scan_metadata ----------------------------------------------------


def test_read_scan_metadata_complete_dir():
    """Reading metadata from the v3 baseline (a complete scan)."""
    meta = _read_scan_metadata(BASELINE_DIR)
    assert meta["status"] == "complete"
    assert meta["target"]  # whatever the baseline target is
    assert meta["plugin_count"] is not None
    assert meta["plugin_count"] > 0


def test_read_scan_metadata_missing_kast_info(tmp_path):
    """A dir without kast_info.json is reported as incomplete."""
    bad_dir = tmp_path / "broken-20260101-120000"
    bad_dir.mkdir()
    meta = _read_scan_metadata(bad_dir)
    assert meta["status"] == "incomplete"


def test_read_scan_metadata_malformed_kast_info(tmp_path):
    """A dir with malformed kast_info.json is reported as incomplete."""
    bad_dir = tmp_path / "malformed-20260101-120000"
    bad_dir.mkdir()
    (bad_dir / "kast_info.json").write_text("not valid json {")
    meta = _read_scan_metadata(bad_dir)
    assert meta["status"] == "incomplete"


# -- scan list --------------------------------------------------------------


def test_scan_list_no_results_dir(tmp_path):
    """Empty results dir → 'No scans found' message and clean exit."""
    fake_results = tmp_path / "kast_results"  # doesn't exist
    with patch("kast.cli.scan._resolve_results_dir", return_value=fake_results):
        runner = CliRunner()
        result = runner.invoke(scan_group, ["list"])
        assert result.exit_code == 0
        assert "No results directory" in result.output


def test_scan_list_json_with_one_scan(tmp_path):
    """Inject one scan dir and verify list --json includes it."""
    results_dir = tmp_path / "kast_results"
    results_dir.mkdir()
    scan_dir = results_dir / "example.com-20260501-120000"
    scan_dir.mkdir()
    # Minimal kast_info.json
    (scan_dir / "kast_info.json").write_text(json.dumps({
        "kast_version": "3.0.0",
        "start_timestamp": "2026-05-01T12:00:00",
        "duration_seconds": 95,
        "cli_arguments": {"target": "example.com", "mode": "passive"},
        "plugins": [{"plugin_name": "whatweb", "status": "success"}],
    }))

    with patch("kast.cli.scan._resolve_results_dir", return_value=results_dir):
        runner = CliRunner()
        result = runner.invoke(scan_group, ["list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert len(payload["scans"]) == 1
        assert payload["scans"][0]["target"] == "example.com"
        assert payload["scans"][0]["status"] == "complete"


def test_scan_list_target_pattern_filter(tmp_path):
    """--target PATTERN filters by case-insensitive substring."""
    results_dir = tmp_path / "kast_results"
    results_dir.mkdir()
    for target in ("example.com", "barracuda.com", "test.example.org"):
        sd = results_dir / f"{target}-20260501-120000"
        sd.mkdir()
        (sd / "kast_info.json").write_text(json.dumps({
            "cli_arguments": {"target": target},
            "plugins": [],
        }))

    with patch("kast.cli.scan._resolve_results_dir", return_value=results_dir):
        runner = CliRunner()
        result = runner.invoke(scan_group, ["list", "--json", "--target", "example"])
        payload = json.loads(result.output)
        targets = {s["target"] for s in payload["scans"]}
        assert targets == {"example.com", "test.example.org"}


def test_scan_list_limit(tmp_path):
    """--limit N caps the number of scans returned."""
    results_dir = tmp_path / "kast_results"
    results_dir.mkdir()
    for i in range(5):
        sd = results_dir / f"target{i}.com-20260501-12000{i}"
        sd.mkdir()
        (sd / "kast_info.json").write_text(json.dumps({
            "cli_arguments": {"target": f"target{i}.com"},
            "plugins": [],
        }))

    with patch("kast.cli.scan._resolve_results_dir", return_value=results_dir):
        runner = CliRunner()
        result = runner.invoke(scan_group, ["list", "--json", "--limit", "2"])
        payload = json.loads(result.output)
        assert len(payload["scans"]) == 2


# -- scan show --------------------------------------------------------------


def test_scan_show_against_baseline():
    """End-to-end: scan show against the v3 baseline dir."""
    runner = CliRunner()
    result = runner.invoke(scan_group, ["show", str(BASELINE_DIR)])
    assert result.exit_code == 0
    # Sanity: the baseline target name should appear
    assert "Scan:" in result.output
    assert "Plugins:" in result.output
    assert "Reports:" in result.output


def test_scan_show_json_against_baseline():
    """JSON variant produces valid structured output with kast_info + reports."""
    runner = CliRunner()
    result = runner.invoke(scan_group, ["show", str(BASELINE_DIR), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "path" in payload
    assert "kast_info" in payload
    assert "plugin_issues" in payload
    assert "reports" in payload
    # The baseline has both HTML and PDF reports
    report_names = {r["name"] for r in payload["reports"]}
    assert "kast_report.html" in report_names
    assert "kast_report.pdf" in report_names


def test_scan_show_nonexistent_dir():
    """Click validates the path argument before scan_show even runs."""
    runner = CliRunner()
    result = runner.invoke(scan_group, ["show", "/nonexistent/dir"])
    assert result.exit_code != 0


# -- scan rerun -------------------------------------------------------------


def test_scan_rerun_re_renders_html(tmp_path):
    """rerun should regenerate kast_report.html from the baseline _processed.json files."""
    # Copy baseline to tmp (don't mutate the real baseline)
    import shutil
    target = tmp_path / "scan-copy"
    shutil.copytree(BASELINE_DIR, target)
    # Remove any existing report so we know rerun produced it
    for name in ("kast_report.html", "kast_style.css"):
        (target / name).unlink(missing_ok=True)
    assert not (target / "kast_report.html").exists()

    runner = CliRunner()
    runner.invoke(scan_group, ["rerun", str(target)])
    # Tolerate exit codes — rerun may emit warnings about WeasyPrint etc.
    # But the HTML report MUST appear.
    assert (target / "kast_report.html").exists()


# -- default scan still works (v2 compat through the group) -----------------


def test_scan_dry_run_still_works():
    """The base `kast scan -t X --dry-run` invocation (no subcommand)."""
    runner = CliRunner()
    result = runner.invoke(scan_group, ["-t", "example.com", "--dry-run"])
    # Dry run is meant to succeed without doing real work
    assert result.exit_code == 0


def test_scan_without_target_or_report_only_errors():
    runner = CliRunner()
    result = runner.invoke(scan_group, [])
    # When invoke_without_command=True and no subcommand given, our group
    # function runs and exits 1 because target/report-only is required.
    assert result.exit_code == 1
    assert "--target is required" in result.output
