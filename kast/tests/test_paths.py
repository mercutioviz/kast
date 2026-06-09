"""Tests for kast.core.paths.resolve_results_dir."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kast.core import paths
from kast.core.paths import resolve_results_dir


class TestResolveResultsDir(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _clear_env(self):
        return patch.dict(os.environ, {}, clear=False) and \
            patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                    if k != "KAST_RESULTS_DIR"}, clear=True)

    def test_cli_arg_wins_over_everything(self):
        cli_dir = Path(self.tmpdir) / "cli"
        env_dir = Path(self.tmpdir) / "env"
        with patch.dict(os.environ, {"KAST_RESULTS_DIR": str(env_dir)}, clear=False), \
             patch.object(paths, "_from_config_files",
                          return_value=str(Path(self.tmpdir) / "config")):
            self.assertEqual(resolve_results_dir(str(cli_dir)), cli_dir)

    def test_env_wins_when_no_cli_arg(self):
        env_dir = Path(self.tmpdir) / "env"
        with patch.dict(os.environ, {"KAST_RESULTS_DIR": str(env_dir)}, clear=False), \
             patch.object(paths, "_from_config_files",
                          return_value=str(Path(self.tmpdir) / "config")):
            self.assertEqual(resolve_results_dir(), env_dir)

    def test_config_wins_when_no_cli_or_env(self):
        config_dir = Path(self.tmpdir) / "config"
        env = {k: v for k, v in os.environ.items() if k != "KAST_RESULTS_DIR"}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(paths, "_from_config_files", return_value=str(config_dir)):
            self.assertEqual(resolve_results_dir(), config_dir)

    def test_default_when_nothing_set(self):
        env = {k: v for k, v in os.environ.items() if k != "KAST_RESULTS_DIR"}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(paths, "_from_config_files", return_value=None):
            self.assertEqual(resolve_results_dir(), Path.home() / "kast_results")

    def test_tilde_expansion(self):
        env = {k: v for k, v in os.environ.items() if k != "KAST_RESULTS_DIR"}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(paths, "_from_config_files", return_value=None):
            result = resolve_results_dir("~/my_results")
            self.assertEqual(result, Path.home() / "my_results")

    def test_envvar_expansion_in_value(self):
        env = {k: v for k, v in os.environ.items() if k != "KAST_RESULTS_DIR"}
        env["MY_BASE"] = "/srv/kast"
        with patch.dict(os.environ, env, clear=True), \
             patch.object(paths, "_from_config_files", return_value=None):
            result = resolve_results_dir("$MY_BASE/scans")
            self.assertEqual(result, Path("/srv/kast/scans"))

    def test_empty_cli_arg_falls_through(self):
        """An empty string for cli_arg should not be treated as a value."""
        env_dir = Path(self.tmpdir) / "env"
        with patch.dict(os.environ, {"KAST_RESULTS_DIR": str(env_dir)}, clear=False):
            self.assertEqual(resolve_results_dir(""), env_dir)


class TestFromConfigFiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def _write_config(self, payload: str) -> Path:
        config_path = self.tmpdir / "config.yaml"
        config_path.write_text(payload)
        return config_path

    def test_reads_global_results_dir(self):
        config_path = self._write_config(
            "global:\n  results_dir: /opt/kast-web/scans\n"
        )
        with patch.object(paths, "_CONFIG_SEARCH_PATHS", [config_path]):
            self.assertEqual(paths._from_config_files(), "/opt/kast-web/scans")

    def test_returns_none_when_no_files_exist(self):
        nonexistent = self.tmpdir / "nope.yaml"
        with patch.object(paths, "_CONFIG_SEARCH_PATHS", [nonexistent]):
            self.assertIsNone(paths._from_config_files())

    def test_returns_none_when_key_missing(self):
        config_path = self._write_config(
            "global:\n  timeout: 300\nplugins: {}\n"
        )
        with patch.object(paths, "_CONFIG_SEARCH_PATHS", [config_path]):
            self.assertIsNone(paths._from_config_files())

    def test_skips_malformed_yaml(self):
        config_path = self._write_config("global: : : bad\n")
        with patch.object(paths, "_CONFIG_SEARCH_PATHS", [config_path]):
            self.assertIsNone(paths._from_config_files())

    def test_returns_none_on_permission_error_for_exists_check(self):
        """A PermissionError from path.exists() must not propagate (service-user scenario)."""
        blocked_dir = self.tmpdir / "blocked_config_dir"
        blocked_dir.mkdir()
        blocked_dir.chmod(0o000)
        try:
            inaccessible_path = blocked_dir / "config.yaml"
            with patch.object(paths, "_CONFIG_SEARCH_PATHS", [inaccessible_path]):
                self.assertIsNone(paths._from_config_files())
        finally:
            blocked_dir.chmod(0o700)

    def test_first_file_wins(self):
        first = self.tmpdir / "first.yaml"
        first.write_text("global:\n  results_dir: /first\n")
        second = self.tmpdir / "second.yaml"
        second.write_text("global:\n  results_dir: /second\n")
        with patch.object(paths, "_CONFIG_SEARCH_PATHS", [first, second]):
            self.assertEqual(paths._from_config_files(), "/first")


if __name__ == "__main__":
    unittest.main()
