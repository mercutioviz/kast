"""Pin the katana files kast-web reads to what docs/web-integration.md documents.

Surface 3 of the kast<->kast-web contract is frozen: kast-web infers plugin
state and renders crawl progress from these documents. A key added or renamed
here without a corresponding doc change is a silent contract break, so the key
sets below and the schemas in docs/web-integration.md must be edited together.
"""

import json
import logging
import os
import tempfile
import unittest
from unittest.mock import Mock

from kast.config_manager import ConfigManager
from kast.plugins.katana_plugin import KatanaPlugin

# docs/web-integration.md -> "Schema of katana_progress.json"
PROGRESS_KEYS = {
    "status", "urls_found", "stalled_seconds", "termination", "last_updated",
}

# docs/web-integration.md -> "crawl_scope in katana_processed.json"
CRAWL_SCOPE_KEYS = {
    "target_host", "registrable_domain", "report_scope", "field_scope",
    "raw_url_count", "unique_url_count", "reported_url_count",
    "excluded_url_count", "host_count", "hosts_by_class", "hosts",
    "unparseable_lines", "js_artifact_count", "canonicalized_url_count",
    "termination", "runtime_seconds", "complete",
}

HOST_ROW_KEYS = {"host", "classification", "unique_urls", "reported"}

# The four states kast-web switches on. "terminated" must stay distinct from
# "done": it means the crawl was cut short and the results are partial.
PROGRESS_STATUSES = {"crawling", "stalled", "done", "terminated"}


class KatanaWebContract(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.dir = tempfile.mkdtemp()
        args = Mock()
        args.verbose = False
        args.target = "example.com"
        args.config = None
        args.set = []
        cm = ConfigManager(args)
        # Isolate from the developer's own ~/.config/kast/config.yaml.
        cm.load(config_file=os.path.join(self.dir, "absent.yaml"))
        self.plugin = KatanaPlugin(args, cm)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _progress(self, **kwargs):
        self.plugin._write_progress(self.dir, **kwargs)
        with open(os.path.join(self.dir, "katana_progress.json")) as f:
            return json.load(f)

    def _crawl_scope(self, urls, termination=None):
        with open(os.path.join(self.dir, "katana.txt"), "w") as f:
            f.write("\n".join(urls) + "\n")
        results = {"target": "example.com", "urls": list(urls)}
        if termination:
            results["termination"] = termination
        envelope = self.plugin.get_result_dict(disposition="success", results=results)
        with open(self.plugin.post_process(envelope, self.dir)) as f:
            return json.load(f)["crawl_scope"]

    def test_progress_document_has_exactly_the_documented_keys(self):
        doc = self._progress(status="crawling", urls_found=10)
        self.assertEqual(set(doc), PROGRESS_KEYS)

    def test_every_documented_status_is_writable(self):
        for status in PROGRESS_STATUSES:
            with self.subTest(status=status):
                self.assertEqual(self._progress(status=status, urls_found=1)["status"],
                                 status)

    def test_terminated_status_carries_the_reason(self):
        """kast-web renders this as a partial result, so the reason must survive."""
        doc = self._progress(
            status="terminated", urls_found=42, termination="max_runtime"
        )
        self.assertEqual(doc["status"], "terminated")
        self.assertEqual(doc["termination"], "max_runtime")

    def test_an_uncut_crawl_reports_no_termination(self):
        self.assertIsNone(self._progress(status="done", urls_found=5)["termination"])

    def test_crawl_scope_has_exactly_the_documented_keys(self):
        scope = self._crawl_scope(["https://example.com/a"])
        self.assertEqual(set(scope), CRAWL_SCOPE_KEYS)

    def test_host_rows_have_exactly_the_documented_keys(self):
        scope = self._crawl_scope(["https://example.com/a", "https://other.test/b"])
        for row in scope["hosts"]:
            self.assertEqual(set(row), HOST_ROW_KEYS)

    def test_hosts_by_class_covers_all_three_classifications(self):
        scope = self._crawl_scope(["https://example.com/a"])
        self.assertEqual(set(scope["hosts_by_class"]),
                         {"target", "sibling", "external"})

    def test_complete_is_false_exactly_when_the_crawl_was_cut_short(self):
        self.assertTrue(self._crawl_scope(["https://example.com/a"])["complete"])
        cut = self._crawl_scope(["https://example.com/a"], termination="stall_timeout")
        self.assertFalse(cut["complete"])
        self.assertEqual(cut["termination"], "stall_timeout")

    def test_progress_file_survives_completion(self):
        """Completion is signalled by katana_processed.json, never by this file."""
        self._progress(status="done", urls_found=1)
        self._crawl_scope(["https://example.com/a"])
        self.assertTrue(
            os.path.exists(os.path.join(self.dir, "katana_progress.json"))
        )

    def test_rerun_recovers_termination_from_the_progress_file(self):
        """post_process has no envelope on rerun, so the reason comes off disk.

        Without this, re-rendering a truncated scan presents it as complete.
        """
        self._progress(status="terminated", urls_found=1, termination="max_runtime")
        scope = self._crawl_scope(["https://example.com/a"])
        self.assertEqual(scope["termination"], "max_runtime")
        self.assertFalse(scope["complete"])


if __name__ == "__main__":
    unittest.main()
