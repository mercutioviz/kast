"""Tests for the ExternalToolPlugin base (Phase B8).

These verify the contract subclasses depend on: subprocess invocation,
output reading, failure handling, atomic processed-dict writing,
subclass-hook routing.

We define a fake plugin class that wraps a no-op shell command so the
tests don't depend on any real external tool.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kast.plugins.external_tool import ExternalToolPlugin

# ---- fake plugin -----------------------------------------------------------


class _FakeJsonTool(ExternalToolPlugin):
    """Test fixture: pretends to wrap a tool that emits JSON output."""

    name = "faketool"
    display_name = "Fake Tool"
    description = "Test fixture for ExternalToolPlugin"
    website_url = None
    scan_type = "passive"
    output_type = "file"
    tool_binary = "echo"  # always present
    output_filename = "faketool.json"
    output_format = "json"

    def build_command(self, target, output_path):
        # Doesn't matter — tests mock subprocess.run anyway, except for
        # is_available which uses shutil.which(tool_binary).
        return ["echo", target, output_path]

    def count_findings(self, findings):
        return len(findings) if isinstance(findings, list) else 1


class _FakeTextTool(_FakeJsonTool):
    """Same as _FakeJsonTool but reads text output."""
    name = "faketool_text"
    output_filename = "faketool.txt"
    output_format = "text"


class _FakeArgs:
    verbose = False


# ---- is_available ----------------------------------------------------------


def test_is_available_when_binary_present():
    plugin = _FakeJsonTool(_FakeArgs())
    assert plugin.is_available() is True  # echo is always present


def test_is_available_when_binary_missing():
    class _MissingTool(_FakeJsonTool):
        tool_binary = "no_such_binary_anywhere"
    plugin = _MissingTool(_FakeArgs())
    assert plugin.is_available() is False


def test_is_available_no_binary_declared_returns_true():
    """A plugin with empty tool_binary is treated as 'always available'."""
    class _NoBinary(_FakeJsonTool):
        tool_binary = ""
    plugin = _NoBinary(_FakeArgs())
    assert plugin.is_available() is True


# ---- run: success path -----------------------------------------------------


def test_run_success_reads_json_output(tmp_path):
    plugin = _FakeJsonTool(_FakeArgs())
    output_file = tmp_path / "faketool.json"
    output_file.write_text(json.dumps([{"k": "v"}, {"k": "w"}]))

    # Mock subprocess.run to "succeed" without actually running anything
    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("kast.plugins.external_tool.subprocess.run", return_value=mock_proc):
        result = plugin.run("example.com", tmp_path, report_only=False)

    assert result["disposition"] == "success"
    assert result["results"] == [{"k": "v"}, {"k": "w"}]


def test_run_success_reads_text_output(tmp_path):
    plugin = _FakeTextTool(_FakeArgs())
    output_file = tmp_path / "faketool.txt"
    output_file.write_text("line1\nline2\n")

    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("kast.plugins.external_tool.subprocess.run", return_value=mock_proc):
        result = plugin.run("example.com", tmp_path, report_only=False)

    assert result["disposition"] == "success"
    assert result["results"] == "line1\nline2\n"


# ---- run: failure paths ----------------------------------------------------


def test_run_fail_when_binary_missing(tmp_path):
    class _MissingTool(_FakeJsonTool):
        tool_binary = "no_such_binary"
    plugin = _MissingTool(_FakeArgs())
    result = plugin.run("example.com", tmp_path, report_only=False)
    assert result["disposition"] == "fail"
    assert "no_such_binary" in result["results"]


def test_run_fail_when_subprocess_returns_nonzero(tmp_path):
    plugin = _FakeJsonTool(_FakeArgs())
    mock_proc = MagicMock(returncode=1, stdout="", stderr="boom!")
    with patch("kast.plugins.external_tool.subprocess.run", return_value=mock_proc):
        result = plugin.run("example.com", tmp_path, report_only=False)
    assert result["disposition"] == "fail"
    assert "boom!" in result["results"]


def test_run_fail_when_output_file_missing(tmp_path):
    """Tool exited 0 but didn't write the expected file."""
    plugin = _FakeJsonTool(_FakeArgs())
    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("kast.plugins.external_tool.subprocess.run", return_value=mock_proc):
        result = plugin.run("example.com", tmp_path, report_only=False)
    assert result["disposition"] == "fail"
    assert "did not create" in result["results"]


def test_run_fail_on_timeout(tmp_path):
    import subprocess as sp
    plugin = _FakeJsonTool(_FakeArgs())
    with patch(
        "kast.plugins.external_tool.subprocess.run",
        side_effect=sp.TimeoutExpired(cmd="echo", timeout=1),
    ):
        result = plugin.run("example.com", tmp_path, report_only=False)
    assert result["disposition"] == "fail"
    assert "timed out" in result["results"]


def test_run_report_only_skips_subprocess(tmp_path):
    """report_only=True must NOT invoke subprocess.run."""
    plugin = _FakeJsonTool(_FakeArgs())
    output_file = tmp_path / "faketool.json"
    output_file.write_text(json.dumps([{"existing": True}]))

    with patch("kast.plugins.external_tool.subprocess.run") as mock_run:
        result = plugin.run("example.com", tmp_path, report_only=True)
    mock_run.assert_not_called()
    assert result["disposition"] == "success"


# ---- post_process ----------------------------------------------------------


def test_post_process_success_writes_processed_json(tmp_path):
    plugin = _FakeJsonTool(_FakeArgs())
    raw_output = {"disposition": "success", "results": [{"a": 1}, {"b": 2}]}
    processed_path = plugin.post_process(raw_output, tmp_path)

    assert Path(processed_path).exists()
    data = json.loads(Path(processed_path).read_text())
    # Standard fields all present
    for key in (
        "plugin-name", "plugin-description", "plugin-display-name",
        "timestamp", "findings", "findings_count", "summary",
        "details", "issues", "executive_summary", "report",
    ):
        assert key in data
    assert data["plugin-name"] == "faketool"
    assert data["findings_count"] == 2
    assert data["issues"] == []  # default extract_issues
    assert data["findings"] == [{"a": 1}, {"b": 2}]


def test_post_process_failed_run_writes_minimal_dict(tmp_path):
    plugin = _FakeJsonTool(_FakeArgs())
    raw_output = {"disposition": "fail", "results": "tool exploded"}
    processed_path = plugin.post_process(raw_output, tmp_path)

    data = json.loads(Path(processed_path).read_text())
    assert data["plugin-name"] == "faketool"
    assert data["findings"]["disposition"] == "fail"
    assert "tool exploded" in data["findings"]["results"]
    assert data["findings_count"] == 0
    assert data["issues"] == []


def test_post_process_extra_fields_merge_in(tmp_path):
    """Subclass-provided extra_processed_fields are merged into the dict."""
    class _WithExtras(_FakeJsonTool):
        def extra_processed_fields(self, findings, issues):
            return {"custom_html": "<div>hi</div>", "results_message": "all good"}

    plugin = _WithExtras(_FakeArgs())
    raw_output = {"disposition": "success", "results": []}
    processed_path = plugin.post_process(raw_output, tmp_path)
    data = json.loads(Path(processed_path).read_text())
    assert data["custom_html"] == "<div>hi</div>"
    assert data["results_message"] == "all good"


def test_post_process_subclass_extract_issues_used(tmp_path):
    class _WithIssues(_FakeJsonTool):
        def extract_issues(self, findings):
            return [{"id": "TEST-001"}, {"id": "TEST-002"}]

    plugin = _WithIssues(_FakeArgs())
    raw_output = {"disposition": "success", "results": [{}, {}]}
    processed_path = plugin.post_process(raw_output, tmp_path)
    data = json.loads(Path(processed_path).read_text())
    assert {i["id"] for i in data["issues"]} == {"TEST-001", "TEST-002"}


def test_post_process_uses_atomic_write(tmp_path):
    """Verify the helper goes through write_json_atomic (Phase A11 contract)."""
    plugin = _FakeJsonTool(_FakeArgs())
    raw_output = {"disposition": "success", "results": []}
    with patch("kast.plugins.external_tool.write_json_atomic") as mock_write:
        plugin.post_process(raw_output, tmp_path)
    mock_write.assert_called_once()
    # First arg is the path; should end with the canonical _processed.json name
    path_arg = str(mock_write.call_args.args[0])
    assert path_arg.endswith("faketool_processed.json")


# ---- get_dry_run_info ------------------------------------------------------


def test_dry_run_info_includes_command(tmp_path):
    plugin = _FakeJsonTool(_FakeArgs())
    info = plugin.get_dry_run_info("example.com", tmp_path)
    assert "commands" in info
    assert len(info["commands"]) == 1
    assert "example.com" in info["commands"][0]


# ---- abstract-method enforcement ------------------------------------------


def test_subclass_must_implement_build_command(tmp_path):
    class _NoBuild(ExternalToolPlugin):
        name = "nobuild"
        display_name = "No Build"
        description = "incomplete subclass"
        tool_binary = "echo"
        output_filename = "nobuild.json"

    plugin = _NoBuild(_FakeArgs())
    with pytest.raises(NotImplementedError):
        plugin.build_command("example.com", "/tmp/x")
