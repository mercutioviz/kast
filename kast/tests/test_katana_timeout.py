"""
File: tests/test_katana_timeout.py
Description: Test that katana crawls are bounded and terminate their process tree.

These use a stub `katana` on PATH rather than mocks: the failure being guarded
against is a real subprocess that ignores its budget and a real headless browser
left orphaned, and neither shows up against a mocked Popen.
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from kast.config_manager import ConfigManager
from kast.plugins import katana_plugin
from kast.plugins.katana_plugin import KatanaPlugin

# Writes two URLs, forks a long-lived child (standing in for the headless
# browser), then blocks forever. Exactly the shape that used to hang a scan.
STUB_KATANA = """#!/bin/sh
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
sleep 300 &
echo $! > "${out}.childpid"
printf 'https://example.com/a\\nhttps://example.com/b\\n' > "$out"
wait
"""


def _alive(pid):
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return True


class KatanaTimeoutBase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.bin_dir = tempfile.mkdtemp()
        stub = os.path.join(self.bin_dir, "katana")
        with open(stub, "w") as f:
            f.write(STUB_KATANA)
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC | stat.S_IXGRP)

        self._path_patch = patch.dict(
            os.environ, {"PATH": self.bin_dir + os.pathsep + os.environ["PATH"]}
        )
        self._path_patch.start()
        # The poll loop sleeps between ticks; shrink it so the deadline checks
        # run promptly and these tests stay fast.
        self._poll_patch = patch.object(
            katana_plugin, "KATANA_POLL_INTERVAL_SECONDS", 0.1
        )
        self._poll_patch.start()

    def tearDown(self):
        self._poll_patch.stop()
        self._path_patch.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)
        shutil.rmtree(self.bin_dir, ignore_errors=True)

    def make_plugin(self, **overrides):
        cli_args = Mock()
        cli_args.verbose = False
        cli_args.target = "example.com"
        cli_args.config = None
        cli_args.set = [f"katana.{k}={v}" for k, v in overrides.items()]
        config_manager = ConfigManager(cli_args)
        config_manager.load(config_file=os.path.join(self.test_dir, "absent.yaml"))
        return KatanaPlugin(cli_args, config_manager)

    def child_pid(self):
        path = os.path.join(self.test_dir, "katana.txt.childpid")
        for _ in range(50):
            if os.path.exists(path):
                with open(path) as f:
                    raw = f.read().strip()
                if raw:
                    return int(raw)
            time.sleep(0.1)
        self.fail("stub katana never recorded a child pid")


class TestMaxRuntime(KatanaTimeoutBase):
    def test_hard_cap_terminates_a_hung_crawl(self):
        plugin = self.make_plugin(max_runtime=1, stall_timeout=0)
        started = time.monotonic()
        result = plugin.run("example.com", self.test_dir, report_only=False)
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 30, "run() did not honour max_runtime")
        self.assertEqual(result["disposition"], "success")
        self.assertEqual(result["results"]["termination"], "max_runtime")

    def test_partial_results_are_kept(self):
        """A cut-short crawl must still report the URLs it did find."""
        plugin = self.make_plugin(max_runtime=1, stall_timeout=0)
        result = plugin.run("example.com", self.test_dir, report_only=False)
        self.assertEqual(
            result["results"]["urls"],
            ["https://example.com/a", "https://example.com/b"],
        )

    def test_child_process_is_not_orphaned(self):
        """Killing katana must take the browser it spawned with it."""
        plugin = self.make_plugin(max_runtime=1, stall_timeout=0)

        import threading

        box = {}
        thread = threading.Thread(
            target=lambda: box.update(
                r=plugin.run("example.com", self.test_dir, report_only=False)
            )
        )
        thread.start()
        pid = self.child_pid()
        self.assertTrue(_alive(pid), "stub child was never running")
        thread.join(timeout=40)
        self.assertFalse(thread.is_alive(), "run() never returned")

        for _ in range(30):
            if not _alive(pid):
                break
            time.sleep(0.1)
        self.assertFalse(_alive(pid), f"child {pid} survived termination")


class TestStallTimeout(KatanaTimeoutBase):
    def test_stalled_crawl_is_terminated(self):
        """The stub writes its URLs immediately, then never finds another."""
        plugin = self.make_plugin(stall_timeout=1, max_runtime=0)
        started = time.monotonic()
        result = plugin.run("example.com", self.test_dir, report_only=False)

        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(result["results"]["termination"], "stall_timeout")
        self.assertEqual(result["disposition"], "success")

    def test_progress_file_records_termination(self):
        plugin = self.make_plugin(stall_timeout=1, max_runtime=0)
        plugin.run("example.com", self.test_dir, report_only=False)
        with open(os.path.join(self.test_dir, "katana_progress.json")) as f:
            progress = json.load(f)
        self.assertEqual(progress["status"], "terminated")
        self.assertEqual(progress["termination"], "stall_timeout")

    def test_in_progress_marker_is_removed(self):
        """kast-web's state machine keys on katana.json disappearing."""
        plugin = self.make_plugin(stall_timeout=1, max_runtime=0)
        plugin.run("example.com", self.test_dir, report_only=False)
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "katana.json")))


class TestTruncationIsSurfaced(KatanaTimeoutBase):
    def test_report_states_the_crawl_was_partial(self):
        plugin = self.make_plugin(stall_timeout=1, max_runtime=0)
        raw = plugin.run("example.com", self.test_dir, report_only=False)
        with open(plugin.post_process(raw, self.test_dir)) as f:
            processed = json.load(f)

        self.assertFalse(processed["crawl_scope"]["complete"])
        self.assertEqual(processed["crawl_scope"]["termination"], "stall_timeout")
        self.assertIn("partial", processed["summary"].lower())
        self.assertIn("Partial crawl", processed["custom_html"])
        self.assertIn("Partial crawl", processed["custom_html_pdf"])

    def test_rerender_recovers_truncation_from_the_progress_file(self):
        """`kast scan rerun` has no envelope; the flag must survive anyway."""
        plugin = self.make_plugin(stall_timeout=1, max_runtime=0)
        plugin.run("example.com", self.test_dir, report_only=False)

        # report_only-shaped envelope: no termination, no urls.
        rerun = plugin.get_result_dict(
            disposition="success", results={"target": "example.com", "urls": []}
        )
        with open(plugin.post_process(rerun, self.test_dir)) as f:
            processed = json.load(f)

        self.assertEqual(processed["crawl_scope"]["termination"], "stall_timeout")
        self.assertFalse(processed["crawl_scope"]["complete"])
        self.assertIn("Partial crawl", processed["custom_html"])

    def test_complete_crawl_carries_no_warning(self):
        """The banner must not appear when the crawl finished on its own."""
        plugin = self.make_plugin()
        envelope = plugin.get_result_dict(
            disposition="success",
            results={
                "target": "example.com",
                "urls": ["https://example.com/a"],
                "termination": None,
                "runtime_seconds": 4.2,
            },
        )
        with open(plugin.post_process(envelope, self.test_dir)) as f:
            processed = json.load(f)

        self.assertTrue(processed["crawl_scope"]["complete"])
        self.assertNotIn("Partial crawl", processed["custom_html"])
        self.assertNotIn("partial", processed["summary"].lower())


class TestTerminateHelper(unittest.TestCase):
    """_terminate must reach the whole process group, and escalate if ignored."""

    def setUp(self):
        self.plugin = KatanaPlugin(Mock(verbose=False, target="example.com"))

    def test_kills_parent_and_child(self):
        proc = subprocess.Popen(
            ["sh", "-c", "sleep 300 & echo $!; wait"],
            stdout=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        child = int(proc.stdout.readline().strip())
        self.assertTrue(_alive(child))

        self.plugin._terminate(proc)

        self.assertIsNotNone(proc.poll(), "parent survived _terminate")
        for _ in range(30):
            if not _alive(child):
                break
            time.sleep(0.1)
        self.assertFalse(_alive(child), "child survived _terminate")

    def test_escalates_to_sigkill_when_sigterm_is_ignored(self):
        proc = subprocess.Popen(
            ["sh", "-c", "trap '' TERM; sleep 300"],
            start_new_session=True,
        )
        try:
            started = time.monotonic()
            self.plugin._terminate(proc)
            self.assertIsNotNone(proc.poll(), "SIGTERM-ignoring process survived")
            self.assertLess(time.monotonic() - started, 25)
        finally:
            if proc.poll() is None:  # pragma: no cover - cleanup only
                proc.kill()
                proc.wait()

    def test_already_dead_process_is_not_an_error(self):
        proc = subprocess.Popen(["true"], start_new_session=True)
        proc.wait()
        self.plugin._terminate(proc)


if __name__ == "__main__":
    unittest.main()
