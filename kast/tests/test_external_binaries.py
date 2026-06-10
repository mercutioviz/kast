"""Tests for kast.core.external_binaries.find_pd_httpx."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kast.core import external_binaries
from kast.core.external_binaries import find_pd_httpx


def _make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\necho test\n")
    path.chmod(0o755)


class TestFindPdHttpx(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_prefers_well_known_path(self):
        sys_bin = Path(self.tmpdir) / "usr_local_bin"
        sys_bin.mkdir()
        _make_executable(sys_bin / "httpx")

        with patch.object(external_binaries, "_PD_HTTPX_CANDIDATES",
                          [str(sys_bin / "httpx"), "/nonexistent/httpx"]):
            self.assertEqual(find_pd_httpx(), str(sys_bin / "httpx"))

    def test_falls_back_to_path_when_no_well_known_match(self):
        path_bin = Path(self.tmpdir) / "path_bin"
        path_bin.mkdir()
        _make_executable(path_bin / "httpx")

        with patch.object(external_binaries, "_PD_HTTPX_CANDIDATES",
                          ["/nonexistent/httpx"]), \
             patch.dict(os.environ, {"PATH": str(path_bin)}, clear=False):
            self.assertEqual(find_pd_httpx(), str(path_bin / "httpx"))

    def test_skips_venv_bin_with_activate_sibling(self):
        venv_bin = Path(self.tmpdir) / "venv_bin"
        venv_bin.mkdir()
        _make_executable(venv_bin / "httpx")
        # Marker that identifies this as a venv.
        (venv_bin / "activate").write_text("# venv activate stub\n")

        sys_bin = Path(self.tmpdir) / "sys_bin"
        sys_bin.mkdir()
        _make_executable(sys_bin / "httpx")

        path = os.pathsep.join([str(venv_bin), str(sys_bin)])
        with patch.object(external_binaries, "_PD_HTTPX_CANDIDATES",
                          ["/nonexistent/httpx"]), \
             patch.dict(os.environ, {"PATH": path}, clear=False):
            # Must skip venv_bin/httpx (has activate sibling) and pick sys_bin/httpx.
            self.assertEqual(find_pd_httpx(), str(sys_bin / "httpx"))

    def test_returns_none_when_no_binary_anywhere(self):
        empty = Path(self.tmpdir) / "empty"
        empty.mkdir()
        with patch.object(external_binaries, "_PD_HTTPX_CANDIDATES",
                          ["/nonexistent/httpx"]), \
             patch.dict(os.environ, {"PATH": str(empty)}, clear=False):
            self.assertIsNone(find_pd_httpx())
