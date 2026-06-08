"""
Tests for `kast doctor --check-updates`: local version probe, upstream fetch
dispatch, version comparison, cache TTL, and the end-to-end CheckResult shape.

All subprocess calls and HTTP calls are mocked — no network, no tools required.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from kast.cli.doctor import (
    UPDATE_SPECS,
    ToolUpdateSpec,
    _CACHE_TTL_SECONDS,
    _cached_upstream_version,
    _compare_versions,
    _github_latest,
    _load_cache,
    _local_version,
    _npm_latest,
    _pypi_latest,
    _save_cache,
    _strip_ansi,
    _upstream_version,
    _version_tuple,
    check_external_tool_updates,
)


# ----- regex fixtures: real --version output captured 2026-06 -----

OUTPUT_TESTSSL = (
    "\n\x1b[1m\n###\n  \x1b[1mtestssl\x1b[m version \x1b[1m3.2.1\x1b[m from "
    "\x1b[1mhttps://testssl.sh/\x1b[m\n  ([0;37m8177539 2026-06-08[m)\n"
)
OUTPUT_WHATWEB = "WhatWeb version 0.5.5 ( https://www.morningstarsecurity.com/ )\n"
OUTPUT_WAFW00F = (
    "                        ~ WAFW00F : v2.3.1 ~\n"
    "[+] The version of WAFW00F you have is \x1b[1;94mv2.3.1\x1b[0m\n"
)
OUTPUT_KATANA = (
    "\n   __        __\n  / /_____ _/ /____ ____  ___ _\n\n"
    "\t\tprojectdiscovery.io\n\n"
    "[\x1b[34mINF\x1b[0m] Current version: v1.5.0\n"
)
OUTPUT_SUBFINDER = (
    "[\x1b[34mINF\x1b[0m] Current Version: v2.14.0\n"
    "[\x1b[34mINF\x1b[0m] Subfinder Config Directory: /home/u/.config/subfinder\n"
)
OUTPUT_HTTPX = (
    "\n    __    __  __       _  __\n\n\t\tprojectdiscovery.io\n\n"
    "[\x1b[34mINF\x1b[0m] Current Version: v1.9.0\n"
)
OUTPUT_OBSERVATORY = "1.0.0\n"


def _make_proc(stdout="", stderr=""):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = 0
    return m


def _spec_by_binary(binary):
    for s in UPDATE_SPECS:
        if s.binary == binary:
            return s
    raise KeyError(binary)


class TestStripAnsi(unittest.TestCase):
    def test_strips_color_codes(self):
        self.assertEqual(_strip_ansi("\x1b[1mhello\x1b[0m"), "hello")

    def test_passthrough_when_no_codes(self):
        self.assertEqual(_strip_ansi("plain text"), "plain text")


class TestVersionTuple(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(_version_tuple("3.2.1"), (3, 2, 1))

    def test_two_part(self):
        self.assertEqual(_version_tuple("1.0"), (1, 0))

    def test_drops_pre_release_suffix(self):
        self.assertEqual(_version_tuple("3.2.1-rc1"), (3, 2, 1))

    def test_handles_dev_suffix(self):
        # "3.2.1.dev0" — dropped at the .dev0 piece.
        self.assertEqual(_version_tuple("3.2.1.dev0"), (3, 2, 1))

    def test_empty_returns_empty(self):
        self.assertEqual(_version_tuple(""), ())

    def test_garbage_returns_empty(self):
        self.assertEqual(_version_tuple("not-a-version"), ())


class TestCompareVersions(unittest.TestCase):
    def test_current(self):
        self.assertEqual(_compare_versions("1.2.3", "1.2.3"), "current")

    def test_outdated_patch(self):
        self.assertEqual(_compare_versions("1.2.3", "1.2.4"), "outdated")

    def test_outdated_minor(self):
        self.assertEqual(_compare_versions("1.2.3", "1.3.0"), "outdated")

    def test_ahead(self):
        self.assertEqual(_compare_versions("2.0.0", "1.9.9"), "ahead")

    def test_unknown_when_unparseable(self):
        self.assertEqual(_compare_versions("garbage", "1.0.0"), "unknown")

    def test_two_part_vs_three_part(self):
        # 1.0 < 1.0.1 because tuple comparison: (1, 0) < (1, 0, 1)
        self.assertEqual(_compare_versions("1.0", "1.0.1"), "outdated")


class TestLocalVersion(unittest.TestCase):
    def test_testssl_parses_with_ansi(self):
        with patch("kast.cli.doctor.shutil.which", return_value="/usr/bin/testssl"), \
             patch("kast.cli.doctor.subprocess.run", return_value=_make_proc(stdout=OUTPUT_TESTSSL)):
            self.assertEqual(_local_version(_spec_by_binary("testssl")), "3.2.1")

    def test_whatweb(self):
        with patch("kast.cli.doctor.shutil.which", return_value="/usr/bin/whatweb"), \
             patch("kast.cli.doctor.subprocess.run", return_value=_make_proc(stdout=OUTPUT_WHATWEB)):
            self.assertEqual(_local_version(_spec_by_binary("whatweb")), "0.5.5")

    def test_wafw00f(self):
        with patch("kast.cli.doctor.shutil.which", return_value="/usr/bin/wafw00f"), \
             patch("kast.cli.doctor.subprocess.run", return_value=_make_proc(stdout=OUTPUT_WAFW00F)):
            self.assertEqual(_local_version(_spec_by_binary("wafw00f")), "2.3.1")

    def test_katana_reads_stderr(self):
        # ProjectDiscovery tools print the version line to stderr.
        with patch("kast.cli.doctor.shutil.which", return_value="/usr/bin/katana"), \
             patch("kast.cli.doctor.subprocess.run", return_value=_make_proc(stderr=OUTPUT_KATANA)):
            self.assertEqual(_local_version(_spec_by_binary("katana")), "1.5.0")

    def test_subfinder(self):
        with patch("kast.cli.doctor.shutil.which", return_value="/usr/bin/subfinder"), \
             patch("kast.cli.doctor.subprocess.run", return_value=_make_proc(stderr=OUTPUT_SUBFINDER)):
            self.assertEqual(_local_version(_spec_by_binary("subfinder")), "2.14.0")

    def test_httpx(self):
        with patch("kast.cli.doctor.shutil.which", return_value="/usr/bin/httpx"), \
             patch("kast.cli.doctor.subprocess.run", return_value=_make_proc(stderr=OUTPUT_HTTPX)):
            self.assertEqual(_local_version(_spec_by_binary("httpx")), "1.9.0")

    def test_observatory(self):
        with patch("kast.cli.doctor.shutil.which", return_value="/usr/bin/mdn-http-observatory-scan"), \
             patch("kast.cli.doctor.subprocess.run", return_value=_make_proc(stdout=OUTPUT_OBSERVATORY)):
            self.assertEqual(_local_version(_spec_by_binary("mdn-http-observatory-scan")), "1.0.0")

    def test_returns_none_when_binary_missing(self):
        with patch("kast.cli.doctor.shutil.which", return_value=None):
            self.assertIsNone(_local_version(_spec_by_binary("katana")))

    def test_returns_none_on_timeout(self):
        import subprocess
        with patch("kast.cli.doctor.shutil.which", return_value="/usr/bin/katana"), \
             patch("kast.cli.doctor.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="x", timeout=5)):
            self.assertIsNone(_local_version(_spec_by_binary("katana")))

    def test_returns_none_when_regex_does_not_match(self):
        with patch("kast.cli.doctor.shutil.which", return_value="/usr/bin/katana"), \
             patch("kast.cli.doctor.subprocess.run", return_value=_make_proc(stdout="garbage")):
            self.assertIsNone(_local_version(_spec_by_binary("katana")))


# ----- upstream fetchers -----


def _mock_urlopen(body: dict):
    """Return a context-manager mock with body as JSON."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=MagicMock(read=lambda: json.dumps(body).encode()))
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestUpstreamFetchers(unittest.TestCase):
    def test_github_latest_strips_v_prefix(self):
        with patch("kast.cli.doctor.urllib.request.urlopen",
                   return_value=_mock_urlopen({"tag_name": "v3.2.1"})):
            self.assertEqual(_github_latest("drwetter/testssl.sh"), "3.2.1")

    def test_github_latest_without_v_prefix(self):
        with patch("kast.cli.doctor.urllib.request.urlopen",
                   return_value=_mock_urlopen({"tag_name": "1.5.0"})):
            self.assertEqual(_github_latest("projectdiscovery/katana"), "1.5.0")

    def test_github_latest_returns_none_on_http_error(self):
        import urllib.error
        with patch("kast.cli.doctor.urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError("u", 403, "rate limit", {}, None)):
            self.assertIsNone(_github_latest("any/repo"))

    def test_github_latest_honors_github_token(self):
        captured_headers = {}

        def fake_urlopen(req, timeout=None):
            captured_headers.update(dict(req.header_items()))
            return _mock_urlopen({"tag_name": "1.0.0"})

        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_abc"}, clear=False):
            with patch("kast.cli.doctor.urllib.request.urlopen", side_effect=fake_urlopen):
                _github_latest("a/b")

        self.assertIn("Authorization", captured_headers)
        self.assertEqual(captured_headers["Authorization"], "Bearer ghp_abc")

    def test_npm_latest(self):
        with patch("kast.cli.doctor.urllib.request.urlopen",
                   return_value=_mock_urlopen({"version": "1.6.2"})):
            self.assertEqual(_npm_latest("@mdn/mdn-http-observatory"), "1.6.2")

    def test_pypi_latest(self):
        with patch("kast.cli.doctor.urllib.request.urlopen",
                   return_value=_mock_urlopen({"info": {"version": "2.4.2"}})):
            self.assertEqual(_pypi_latest("wafw00f"), "2.4.2")

    def test_upstream_version_dispatches_by_kind(self):
        spec_gh = _spec_by_binary("katana")
        spec_npm = _spec_by_binary("mdn-http-observatory-scan")
        spec_pypi = _spec_by_binary("wafw00f")

        with patch("kast.cli.doctor._github_latest", return_value="1.0.0") as gh, \
             patch("kast.cli.doctor._npm_latest", return_value="2.0.0") as npm, \
             patch("kast.cli.doctor._pypi_latest", return_value="3.0.0") as pypi:
            self.assertEqual(_upstream_version(spec_gh), "1.0.0")
            self.assertEqual(_upstream_version(spec_npm), "2.0.0")
            self.assertEqual(_upstream_version(spec_pypi), "3.0.0")

        gh.assert_called_once_with(spec_gh.upstream_id)
        npm.assert_called_once_with(spec_npm.upstream_id)
        pypi.assert_called_once_with(spec_pypi.upstream_id)


# ----- cache layer -----


class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._xdg_patch = patch.dict(os.environ, {"XDG_CACHE_HOME": self.tmpdir}, clear=False)
        self._xdg_patch.start()

    def tearDown(self):
        self._xdg_patch.stop()

    def test_save_and_load_roundtrip(self):
        _save_cache({"k": {"fetched_at": 123.0, "latest": "1.0.0"}})
        loaded = _load_cache()
        self.assertEqual(loaded, {"k": {"fetched_at": 123.0, "latest": "1.0.0"}})

    def test_load_returns_empty_dict_when_missing(self):
        self.assertEqual(_load_cache(), {})

    def test_cached_upstream_hits_cache_within_ttl(self):
        spec = _spec_by_binary("katana")
        key = f"{spec.upstream_kind}:{spec.upstream_id}"
        _save_cache({key: {"fetched_at": time.time(), "latest": "1.5.0"}})

        with patch("kast.cli.doctor._upstream_version") as net_call:
            result = _cached_upstream_version(spec, use_cache=True)
            self.assertEqual(result, "1.5.0")
            net_call.assert_not_called()

    def test_cached_upstream_refetches_after_ttl(self):
        spec = _spec_by_binary("katana")
        key = f"{spec.upstream_kind}:{spec.upstream_id}"
        # Save a stale entry.
        _save_cache({key: {"fetched_at": time.time() - _CACHE_TTL_SECONDS - 1, "latest": "1.0.0"}})

        with patch("kast.cli.doctor._upstream_version", return_value="1.6.1") as net_call:
            result = _cached_upstream_version(spec, use_cache=True)
            self.assertEqual(result, "1.6.1")
            net_call.assert_called_once()

    def test_no_cache_forces_fresh_fetch(self):
        spec = _spec_by_binary("katana")
        key = f"{spec.upstream_kind}:{spec.upstream_id}"
        _save_cache({key: {"fetched_at": time.time(), "latest": "1.5.0"}})

        with patch("kast.cli.doctor._upstream_version", return_value="1.6.1") as net_call:
            result = _cached_upstream_version(spec, use_cache=False)
            self.assertEqual(result, "1.6.1")
            net_call.assert_called_once()


# ----- end-to-end -----


class TestCheckExternalToolUpdates(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._xdg_patch = patch.dict(os.environ, {"XDG_CACHE_HOME": self.tmpdir}, clear=False)
        self._xdg_patch.start()

    def tearDown(self):
        self._xdg_patch.stop()

    def test_outdated_current_and_missing_mix(self):
        """katana outdated, subfinder current, all others not installed."""
        def fake_which(name):
            return f"/usr/bin/{name}" if name in {"katana", "subfinder"} else None

        def fake_local(spec):
            return {"katana": "1.5.0", "subfinder": "2.14.0"}.get(spec.binary)

        def fake_cached(spec, *, use_cache):
            return {"katana": "1.6.1", "subfinder": "2.14.0"}.get(spec.binary)

        with patch("kast.cli.doctor.shutil.which", side_effect=fake_which), \
             patch("kast.cli.doctor._local_version", side_effect=fake_local), \
             patch("kast.cli.doctor._cached_upstream_version", side_effect=fake_cached):
            results = check_external_tool_updates(use_cache=True)

        by_name = {r.name: r for r in results}
        self.assertEqual(by_name["katana"].status, "warn")
        self.assertIn("1.5.0", by_name["katana"].detail)
        self.assertIn("1.6.1", by_name["katana"].detail)
        self.assertEqual(by_name["subfinder"].status, "ok")
        # Tools not in PATH → INFO "not installed (skipped)"
        self.assertEqual(by_name["whatweb"].status, "info")
        self.assertIn("not installed", by_name["whatweb"].detail)

    def test_upstream_failure_yields_info_row(self):
        def fake_which(name):
            return f"/usr/bin/{name}" if name == "katana" else None

        with patch("kast.cli.doctor.shutil.which", side_effect=fake_which), \
             patch("kast.cli.doctor._local_version", return_value="1.5.0"), \
             patch("kast.cli.doctor._cached_upstream_version", return_value=None):
            results = check_external_tool_updates(use_cache=True)

        katana = next(r for r in results if r.name == "katana")
        self.assertEqual(katana.status, "info")
        self.assertIn("upstream check failed", katana.detail)

    def test_local_version_unreadable_yields_info_row(self):
        def fake_which(name):
            return f"/usr/bin/{name}" if name == "katana" else None

        with patch("kast.cli.doctor.shutil.which", side_effect=fake_which), \
             patch("kast.cli.doctor._local_version", return_value=None):
            results = check_external_tool_updates(use_cache=True)

        katana = next(r for r in results if r.name == "katana")
        self.assertEqual(katana.status, "info")
        self.assertIn("could not determine", katana.detail)

    def test_ahead_status(self):
        def fake_which(name):
            return f"/usr/bin/{name}" if name == "katana" else None

        with patch("kast.cli.doctor.shutil.which", side_effect=fake_which), \
             patch("kast.cli.doctor._local_version", return_value="2.0.0"), \
             patch("kast.cli.doctor._cached_upstream_version", return_value="1.9.0"):
            results = check_external_tool_updates(use_cache=True)

        katana = next(r for r in results if r.name == "katana")
        self.assertEqual(katana.status, "info")
        self.assertIn("ahead", katana.detail)


if __name__ == "__main__":
    unittest.main()
