"""Tests for ``kast self-update`` (Phase B6).

The command shells out to ``update.sh`` for real updates, so most
tests mock subprocess to verify command construction. The Python-side
``--check-only`` path is tested with mocked git output.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from kast.cli.self_update import (
    _find_update_script,
    _read_local_version,
    _read_remote_version,
    self_update,
)


# -- helpers ----------------------------------------------------------------


def test_local_version_reads_VERSION_file():
    """The dev checkout has a VERSION file at the project root."""
    version = _read_local_version()
    assert version is not None
    # VERSION format is M.N.P
    parts = version.split(".")
    assert len(parts) >= 2
    assert parts[0].isdigit()


def test_find_update_script_dev_checkout():
    """In the dev checkout, _find_update_script should return the repo's update.sh."""
    script = _find_update_script()
    assert script is not None
    assert script.name == "update.sh"
    assert script.exists()


# -- --check-only path ------------------------------------------------------


def test_check_only_up_to_date():
    """When local == remote, exit 0 and report up-to-date."""
    runner = CliRunner()
    with patch("kast.cli.self_update._read_local_version", return_value="3.0.0"), \
         patch("kast.cli.self_update._read_remote_version", return_value="3.0.0"):
        result = runner.invoke(self_update, ["--check-only"])
    assert result.exit_code == 0
    assert "Up to date" in result.output


def test_check_only_update_available():
    """When local != remote, the user is told an update is available (exit 0)."""
    runner = CliRunner()
    with patch("kast.cli.self_update._read_local_version", return_value="2.14.5"), \
         patch("kast.cli.self_update._read_remote_version", return_value="3.0.0"):
        result = runner.invoke(self_update, ["--check-only"])
    assert result.exit_code == 0
    assert "Update available" in result.output


def test_check_only_no_remote():
    """If git can't fetch the remote VERSION, exit 2 with a clear message."""
    runner = CliRunner()
    with patch("kast.cli.self_update._read_local_version", return_value="3.0.0"), \
         patch("kast.cli.self_update._read_remote_version", return_value=None):
        result = runner.invoke(self_update, ["--check-only"])
    assert result.exit_code == 2
    assert "Could not fetch remote version" in result.output


def test_check_only_no_local():
    """If VERSION file is missing, exit 1 with a remediation hint."""
    runner = CliRunner()
    with patch("kast.cli.self_update._read_local_version", return_value=None):
        result = runner.invoke(self_update, ["--check-only"])
    assert result.exit_code == 1
    assert "VERSION file not found" in result.output


# -- subprocess pass-through ------------------------------------------------


@pytest.fixture
def fake_script(tmp_path):
    """A fake update.sh path; patches _find_update_script to return it."""
    script = tmp_path / "update.sh"
    script.write_text("#!/bin/bash\nexit 0\n")
    script.chmod(0o755)
    with patch("kast.cli.self_update._find_update_script", return_value=script):
        yield script


def _mock_subprocess_run():
    """Returns a mock that captures the cmd arg and returns rc=0."""
    return MagicMock(return_value=MagicMock(returncode=0))


def test_self_update_default_invokes_sudo_update_sh(fake_script):
    runner = CliRunner()
    mock_run = _mock_subprocess_run()
    with patch("kast.cli.self_update.subprocess.run", mock_run):
        result = runner.invoke(self_update, [])
    assert result.exit_code == 0
    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "sudo"
    assert cmd[1] == str(fake_script)
    # No extra flags by default
    assert len(cmd) == 2


def test_self_update_auto_passes_auto_flag(fake_script):
    runner = CliRunner()
    mock_run = _mock_subprocess_run()
    with patch("kast.cli.self_update.subprocess.run", mock_run):
        result = runner.invoke(self_update, ["--auto"])
    assert result.exit_code == 0
    cmd = mock_run.call_args.args[0]
    assert "--auto" in cmd


def test_self_update_dry_run_passes_dry_run_flag(fake_script):
    runner = CliRunner()
    mock_run = _mock_subprocess_run()
    with patch("kast.cli.self_update.subprocess.run", mock_run):
        result = runner.invoke(self_update, ["--dry-run"])
    cmd = mock_run.call_args.args[0]
    assert "--dry-run" in cmd


def test_self_update_list_backups_passes_flag(fake_script):
    runner = CliRunner()
    mock_run = _mock_subprocess_run()
    with patch("kast.cli.self_update.subprocess.run", mock_run):
        result = runner.invoke(self_update, ["--list-backups"])
    cmd = mock_run.call_args.args[0]
    assert "--list-backups" in cmd


def test_self_update_rollback_passes_timestamp(fake_script):
    runner = CliRunner()
    mock_run = _mock_subprocess_run()
    with patch("kast.cli.self_update.subprocess.run", mock_run):
        result = runner.invoke(self_update, ["--rollback", "20260501_120000"])
    cmd = mock_run.call_args.args[0]
    assert "--rollback" in cmd
    assert "20260501_120000" in cmd


def test_self_update_install_dir_passes_through(fake_script):
    runner = CliRunner()
    mock_run = _mock_subprocess_run()
    with patch("kast.cli.self_update.subprocess.run", mock_run):
        result = runner.invoke(self_update, ["--install-dir", "/opt/kast-test"])
    cmd = mock_run.call_args.args[0]
    assert "--install-dir" in cmd
    assert "/opt/kast-test" in cmd


def test_self_update_propagates_exit_code(fake_script):
    """Non-zero exit from update.sh should propagate."""
    runner = CliRunner()
    mock_run = MagicMock(return_value=MagicMock(returncode=42))
    with patch("kast.cli.self_update.subprocess.run", mock_run):
        result = runner.invoke(self_update, [])
    assert result.exit_code == 42


def test_self_update_missing_script_errors():
    """If neither dev nor installed update.sh exists, exit non-zero with a message."""
    runner = CliRunner()
    with patch("kast.cli.self_update._find_update_script", return_value=None):
        result = runner.invoke(self_update, [])
    assert result.exit_code != 0
    assert "Could not locate update.sh" in result.output
