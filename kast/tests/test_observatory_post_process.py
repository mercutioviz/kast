"""
Test Mozilla Observatory post-processing: tests dict is split into
{"passed": {...}, "failed": {...}} and issues are derived from the failed bucket.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import Mock

from kast.config_manager import ConfigManager
from kast.plugins.observatory_plugin import ObservatoryPlugin, _split_tests_by_status


def _raw_findings(tests):
    return {
        "name": "mozilla_observatory",
        "timestamp": "2026-06-08T00:00:00.000+00:00",
        "disposition": "success",
        "results": {
            "scan": {
                "grade": "B",
                "score": 75,
                "testsPassed": sum(1 for t in tests.values() if t.get("pass") is True),
                "testsFailed": sum(1 for t in tests.values() if t.get("pass") is not True),
            },
            "tests": tests,
        },
    }


class TestSplitHelper(unittest.TestCase):
    def test_partitions_by_pass_field(self):
        tests = {
            "a": {"pass": True, "result": "ok-a"},
            "b": {"pass": False, "result": "csp-not-implemented"},
            "c": {"pass": True, "result": "ok-c"},
            "d": {"pass": False, "result": "hsts-not-implemented"},
        }
        out = _split_tests_by_status(tests)
        self.assertEqual(set(out.keys()), {"passed", "failed"})
        self.assertEqual(set(out["passed"].keys()), {"a", "c"})
        self.assertEqual(set(out["failed"].keys()), {"b", "d"})

    def test_empty_dict(self):
        self.assertEqual(_split_tests_by_status({}), {"passed": {}, "failed": {}})

    def test_non_bool_pass_treated_as_failed(self):
        tests = {
            "weird": {"pass": None, "result": "x"},
            "missing": {"result": "y"},
            "passing": {"pass": True, "result": "z"},
        }
        out = _split_tests_by_status(tests)
        self.assertEqual(set(out["passed"].keys()), {"passing"})
        self.assertEqual(set(out["failed"].keys()), {"weird", "missing"})


class TestPostProcessSplit(unittest.TestCase):
    def setUp(self):
        self.cli_args = Mock()
        self.cli_args.verbose = False
        self.cli_args.set = []
        self.config_manager = ConfigManager(self.cli_args)
        self.plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        self.tmpdir = tempfile.mkdtemp()

    def _load_processed(self):
        path = os.path.join(self.tmpdir, "mozilla_observatory_processed.json")
        with open(path) as f:
            return json.load(f)

    def test_post_process_splits_tests(self):
        raw = _raw_findings({
            "content-security-policy": {
                "pass": False,
                "result": "csp-implemented-with-unsafe-inline",
                "scoreModifier": -20,
                "data": {},
            },
            "cookies": {"pass": True, "result": "cookies-without-secure-flag", "scoreModifier": 0},
            "hsts": {"pass": False, "result": "hsts-not-implemented", "scoreModifier": -20},
            "x-frame-options": {"pass": True, "result": "x-frame-options-implemented", "scoreModifier": 0},
        })
        self.plugin.post_process(raw, self.tmpdir)

        processed = self._load_processed()
        tests = processed["findings"]["results"]["tests"]
        self.assertEqual(set(tests.keys()), {"passed", "failed"})
        self.assertEqual(set(tests["passed"].keys()), {"cookies", "x-frame-options"})
        self.assertEqual(set(tests["failed"].keys()), {"content-security-policy", "hsts"})

    def test_post_process_issues_derived_from_failed(self):
        raw = _raw_findings({
            "content-security-policy": {
                "pass": False,
                "result": "csp-implemented-with-unsafe-inline",
            },
            "cookies": {"pass": True, "result": "cookies-without-secure-flag"},
            "hsts": {"pass": False, "result": "hsts-not-implemented"},
        })
        self.plugin.post_process(raw, self.tmpdir)

        processed = self._load_processed()
        self.assertEqual(
            sorted(processed["issues"]),
            sorted(["csp-implemented-with-unsafe-inline", "hsts-not-implemented"]),
        )
        self.assertEqual(processed["findings_count"], 2)

    def test_post_process_empty_tests(self):
        raw = _raw_findings({})
        self.plugin.post_process(raw, self.tmpdir)

        processed = self._load_processed()
        self.assertEqual(
            processed["findings"]["results"]["tests"],
            {"passed": {}, "failed": {}},
        )
        self.assertEqual(processed["issues"], [])
        self.assertEqual(processed["findings_count"], 0)

    def test_post_process_failure_disposition_skips_split(self):
        raw = {
            "name": "mozilla_observatory",
            "timestamp": "2026-06-08T00:00:00.000+00:00",
            "disposition": "fail",
            "results": "mdn-http-observatory-scan exited with error",
        }
        self.plugin.post_process(raw, self.tmpdir)

        processed = self._load_processed()
        self.assertEqual(processed["issues"], [])
        self.assertEqual(processed["findings_count"], 0)
        self.assertEqual(processed["findings"]["results"], "mdn-http-observatory-scan exited with error")


if __name__ == "__main__":
    unittest.main()
