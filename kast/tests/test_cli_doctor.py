"""Tests for ``kast doctor`` (Phase B5).

Doctor's purpose is to give an SA setting up a fresh kast install (or
diagnosing a broken one) a single command that reports environment
health. These tests pin the exit-code contract (0 if no failures, 1
otherwise) and the JSON output shape (consumed by external tooling).
"""

import json
from unittest.mock import patch

from click.testing import CliRunner

from kast.cli.doctor import (
    OK, WARN, FAIL, INFO,
    CheckResult,
    check_issue_registry,
    check_plugin_loading,
    check_python_version,
    check_results_dir,
    doctor,
)


# -- individual checks -------------------------------------------------------


def test_python_version_ok_on_current_interpreter():
    """The current interpreter (>= 3.9) must pass the version check."""
    result = check_python_version()
    assert result.status == OK
    assert "Python" in result.detail


def test_issue_registry_loads():
    """The shipped registry must be valid JSON."""
    result = check_issue_registry()
    assert result.status == OK
    # Detail should report the entry count
    assert "entries" in result.detail


def test_plugin_loading_passes():
    """All plugins should discover and instantiate cleanly."""
    results = check_plugin_loading()
    # Two checks: discover + instantiate
    assert len(results) == 2
    assert all(r.status == OK for r in results)
    # Count is flexible — just verify N/N format (all succeeded)
    instantiate_result = next(r for r in results if r.name == "instantiate")
    detail = instantiate_result.detail  # e.g. "13/13 instantiated"
    total = detail.split("/")[0]
    assert detail.startswith(f"{total}/{total}"), f"Not all plugins instantiated: {detail}"


def test_results_dir_writable():
    """~/kast_results should be creatable in any normal environment."""
    result = check_results_dir()
    assert result.status == OK


# -- driver / Click command --------------------------------------------------


def test_doctor_runs_and_produces_summary():
    runner = CliRunner()
    result = runner.invoke(doctor, [])
    # Exit code: 0 if no FAILs (which on a healthy dev env should hold),
    # otherwise 1. Either way, the output should contain the summary line.
    assert "Summary:" in result.output
    assert result.exit_code in (0, 1)


def test_doctor_json_output_shape():
    runner = CliRunner()
    result = runner.invoke(doctor, ["--json"])
    payload = json.loads(result.output)
    assert "results" in payload
    assert "summary" in payload
    # Summary keys mirror the four statuses
    assert set(payload["summary"].keys()) == {OK, WARN, FAIL, INFO}
    # Each result has the expected shape
    for r in payload["results"]:
        assert {"section", "name", "status", "detail", "hint"} <= set(r.keys())
        assert r["status"] in (OK, WARN, FAIL, INFO)


def test_doctor_exit_code_is_1_when_failures_present():
    """Inject a failing check; doctor should exit non-zero."""
    fake_fail = CheckResult(
        section="Test",
        name="injected fail",
        status=FAIL,
        detail="simulated",
        hint="(test)",
    )
    with patch("kast.cli.doctor.run_all_checks", return_value=[fake_fail]):
        runner = CliRunner()
        result = runner.invoke(doctor, [])
        assert result.exit_code == 1


def test_doctor_exit_code_is_0_when_no_failures():
    """Inject only OK results; doctor should exit 0."""
    fake_ok = CheckResult(
        section="Test",
        name="injected ok",
        status=OK,
        detail="simulated",
    )
    with patch("kast.cli.doctor.run_all_checks", return_value=[fake_ok]):
        runner = CliRunner()
        result = runner.invoke(doctor, [])
        assert result.exit_code == 0


def test_doctor_warn_does_not_fail_exit_code():
    """A WARN result should NOT trigger exit code 1 — only FAIL does."""
    fake_warn = CheckResult(
        section="Test",
        name="injected warn",
        status=WARN,
        detail="missing optional tool",
        hint="(test)",
    )
    with patch("kast.cli.doctor.run_all_checks", return_value=[fake_warn]):
        runner = CliRunner()
        result = runner.invoke(doctor, [])
        assert result.exit_code == 0
