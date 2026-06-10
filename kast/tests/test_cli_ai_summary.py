"""End-to-end CLI smoke for --ai-summary with a mocked adapter.

We mock ``kast.ai.config.get_ai_adapter`` so no real API call is made.
"""

from unittest.mock import MagicMock

from click.testing import CliRunner

from kast.cli.scan import _build_ai_info
from kast.cli.scan import scan as scan_group


def test_build_ai_info_disabled():
    info = _build_ai_info(False, "anthropic", None, None)
    assert info["enabled"] is False
    assert info["status"] == "disabled"
    assert info["model"] is None
    assert info["error"] is None


def test_build_ai_info_success():
    summary = {"_meta": {"model": "claude-sonnet-4-6", "tokens_in": 12,
                         "tokens_out": 34, "latency_ms": 567,
                         "prompt_version": 1}}
    info = _build_ai_info(True, "anthropic", summary, None)
    assert info["enabled"] is True
    assert info["status"] == "success"
    assert info["adapter"] == "anthropic"
    assert info["model"] == "claude-sonnet-4-6"
    assert info["tokens_in"] == 12
    assert info["tokens_out"] == 34
    assert info["latency_ms"] == 567
    assert info["prompt_version"] == 1
    assert info["error"] is None


def test_build_ai_info_error():
    info = _build_ai_info(True, "anthropic", None, "boom")
    assert info["enabled"] is True
    assert info["status"] == "error"
    assert info["adapter"] == "anthropic"
    assert info["error"] == "boom"
    assert info["model"] is None


def test_scan_help_lists_ai_flags():
    runner = CliRunner()
    result = runner.invoke(scan_group, ["--help"])
    assert result.exit_code == 0
    assert "--ai-summary" in result.output
    assert "--ai-model" in result.output
    assert "--ai-adapter" in result.output


def test_scan_dry_run_with_ai_flag_skips_adapter(monkeypatch):
    """``--dry-run`` must NOT instantiate the AI adapter."""
    runner = CliRunner()
    fake_get_adapter = MagicMock()
    monkeypatch.setattr("kast.ai.config.get_ai_adapter", fake_get_adapter)

    with runner.isolated_filesystem():
        runner.invoke(
            scan_group,
            ["--target", "example.com", "--ai-summary", "--dry-run",
             "-o", "outdir", "--log-dir", "."],
            catch_exceptions=True,
        )
    # We don't assert exit code (the orchestrator may or may not run depending
    # on plugin availability); we just need to confirm the adapter was not
    # touched in dry-run mode.
    fake_get_adapter.assert_not_called()
