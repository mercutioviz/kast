"""
File: tests/test_katana_post_process.py
Description: Test katana post-processing URL scoping and crawl-scope reporting.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock

from kast.config_manager import ConfigManager
from kast.plugins.katana_plugin import KatanaPlugin

TARGET = "donate.wbez.org"

TARGET_URLS = [
    "https://donate.wbez.org",
    "https://donate.wbez.org/",
    "https://donate.wbez.org/node/311",
    "https://donate.wbez.org/files/wbez/js/js_GqDCPsE4.js",
]
SIBLING_URLS = [
    "https://www.wbez.org/health/2026/03/02/health-care-illinois-prisons",
    "https://pages.wbez.org/newsletter",
]
EXTERNAL_URLS = [
    "https://chicago.suntimes.com/health/2026/04/24/obamacare-health-insurance",
    "https://twitter.com/intent/tweet?url=https%3A%2F%2Fwww.wbez.org%2Fa&text=x",
    "https://cst.brightspotcdn.com/dims4/default/resize/820x461!/quality/90/?url=x",
]
# page.wbez.org wraps an outbound redirect whose *path* contains the target host.
# A substring search attributes this to donate.wbez.org; host parsing does not.
REDIRECT_TRAP = (
    "https://page.wbez.org/tweedy-sweepstakes-rules/clkn/http/"
    "donate.wbez.org/secure/cet-events-form"
)
# A hostile lookalike: the target is a strict prefix of this host.
LOOKALIKE_TRAP = "https://donate.wbez.org.evil.example/phish"

SAMPLE_URLS = TARGET_URLS + SIBLING_URLS + EXTERNAL_URLS + [REDIRECT_TRAP, LOOKALIKE_TRAP]


class KatanaPostProcessBase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # A real scan leaves katana.txt on disk alongside the returned envelope.
        # Both must be present or the item-1 regression hides: with the envelope
        # misread, post_process silently fell back to this file and emitted it
        # unfiltered, which is the production failure.
        with open(os.path.join(self.test_dir, "katana.txt"), "w") as f:
            f.write("\n".join(SAMPLE_URLS) + "\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def make_plugin(self, target=TARGET, report_scope=None):
        """Build a plugin, routing report_scope through the real config stack."""
        cli_args = Mock()
        cli_args.verbose = False
        cli_args.target = target
        cli_args.config = None
        cli_args.set = (
            [f"katana.report_scope={report_scope}"] if report_scope else []
        )
        config_manager = ConfigManager(cli_args)
        # Point at a path that cannot exist so the developer's own
        # ~/.config/kast/config.yaml can't change what these tests assert.
        # load() still parses --set, which is the plumbing under test.
        config_manager.load(config_file=os.path.join(self.test_dir, "absent.yaml"))
        return KatanaPlugin(cli_args, config_manager)

    def processed(self, plugin, urls=SAMPLE_URLS, target=None):
        envelope = plugin.get_result_dict(
            disposition="success",
            results={"target": target or plugin.cli_args.target, "urls": list(urls)},
        )
        path = plugin.post_process(envelope, self.test_dir)
        with open(path) as f:
            return json.load(f)


class TestTargetScope(KatanaPostProcessBase):
    """report_scope=target reproduces the plugin's original documented contract."""

    def setUp(self):
        super().setUp()
        self.plugin = self.make_plugin(report_scope="target")

    def test_reads_target_from_results_envelope(self):
        """post_process must look under 'results', not the envelope top level.

        Reading the top level returned target="", and find("") matches at index
        0, so every URL was emitted whole and nothing was filtered.
        """
        urls = self.processed(self.plugin)["findings"]["urls"]
        self.assertCountEqual(
            urls, ["/", "/node/311", "/files/wbez/js/js_GqDCPsE4.js"]
        )

    def test_every_entry_is_a_bare_path(self):
        for url in self.processed(self.plugin)["findings"]["urls"]:
            self.assertTrue(url.startswith("/"), f"{url!r} is not a path")
            self.assertNotIn("://", url)

    def test_off_target_hosts_are_absent(self):
        blob = json.dumps(self.processed(self.plugin)["findings"])
        for host in ("www.wbez.org", "chicago.suntimes.com", "twitter.com"):
            self.assertNotIn(host, blob)

    def test_redirect_path_is_attributed_to_its_real_host(self):
        """The clkn redirect belongs to page.wbez.org, not to the target."""
        urls = self.processed(self.plugin)["findings"]["urls"]
        self.assertNotIn("/secure/cet-events-form", urls)

    def test_lookalike_host_is_not_the_target(self):
        """donate.wbez.org.evil.example must never be read as the target."""
        processed = self.processed(self.plugin)
        self.assertNotIn("/phish", processed["findings"]["urls"])

        hosts = {h["host"]: h for h in processed["crawl_scope"]["hosts"]}
        self.assertEqual(hosts["donate.wbez.org.evil.example"]["classification"],
                         "external")
        self.assertFalse(hosts["donate.wbez.org.evil.example"]["reported"])

    def test_interesting_endpoints_only_cover_the_target(self):
        """The prospect-facing highlight box must not list third-party paths."""
        processed = self.processed(self.plugin)
        for paths in processed["interesting_endpoints"].values():
            for path in paths:
                self.assertTrue(path.startswith("/"))
                self.assertNotIn("suntimes.com", path)


class TestOrganizationScope(KatanaPostProcessBase):
    """The shipped default: the target plus any host on its registrable domain."""

    def setUp(self):
        super().setUp()
        self.plugin = self.make_plugin()

    def test_default_scope_is_organization(self):
        self.assertEqual(self.plugin.report_scope, "organization")

    def test_includes_siblings_and_excludes_external(self):
        urls = self.processed(self.plugin)["findings"]["urls"]
        self.assertIn("www.wbez.org/health/2026/03/02/health-care-illinois-prisons", urls)
        self.assertIn("pages.wbez.org/newsletter", urls)
        for url in urls:
            self.assertNotIn("suntimes.com", url)
            self.assertNotIn("twitter.com", url)
            self.assertNotIn("evil.example", url)

    def test_target_stays_relative_and_siblings_stay_qualified(self):
        """A bare path always means the target; anything else names its host."""
        urls = self.processed(self.plugin)["findings"]["urls"]
        self.assertIn("/node/311", urls)
        for url in urls:
            if not url.startswith("/"):
                self.assertIn(".wbez.org/", url)

    def test_redirect_trap_is_qualified_to_page_wbez_org(self):
        urls = self.processed(self.plugin)["findings"]["urls"]
        self.assertIn(
            "page.wbez.org/tweedy-sweepstakes-rules/clkn/http/"
            "donate.wbez.org/secure/cet-events-form",
            urls,
        )
        self.assertNotIn("/secure/cet-events-form", urls)


class TestAllScope(KatanaPostProcessBase):
    def test_all_scope_reports_external_hosts(self):
        plugin = self.make_plugin(report_scope="all")
        processed = self.processed(plugin)
        urls = processed["findings"]["urls"]
        self.assertTrue(any("chicago.suntimes.com" in u for u in urls))
        self.assertEqual(
            processed["crawl_scope"]["excluded_url_count"], 0
        )


class TestCrawlScope(KatanaPostProcessBase):
    """crawl_scope is the block that quantifies what the crawl actually reached."""

    def setUp(self):
        super().setUp()
        self.plugin = self.make_plugin()
        self.scope = self.processed(self.plugin)["crawl_scope"]

    def test_host_classification(self):
        hosts = {h["host"]: h["classification"] for h in self.scope["hosts"]}
        self.assertEqual(hosts["donate.wbez.org"], "target")
        self.assertEqual(hosts["www.wbez.org"], "sibling")
        self.assertEqual(hosts["pages.wbez.org"], "sibling")
        self.assertEqual(hosts["page.wbez.org"], "sibling")
        self.assertEqual(hosts["chicago.suntimes.com"], "external")
        self.assertEqual(hosts["twitter.com"], "external")

    def test_counts_are_internally_consistent(self):
        self.assertEqual(
            self.scope["reported_url_count"] + self.scope["excluded_url_count"],
            self.scope["unique_url_count"],
        )
        self.assertEqual(self.scope["host_count"], len(self.scope["hosts"]))
        self.assertEqual(
            sum(self.scope["hosts_by_class"].values()), self.scope["host_count"]
        )

    def test_raw_count_is_the_pre_dedupe_total(self):
        """Two target URLs collapse to '/', so raw > unique."""
        self.assertEqual(self.scope["raw_url_count"], len(SAMPLE_URLS))
        self.assertLess(self.scope["unique_url_count"], self.scope["raw_url_count"])

    def test_records_the_scope_settings_it_applied(self):
        self.assertEqual(self.scope["target_host"], TARGET)
        self.assertEqual(self.scope["registrable_domain"], "wbez.org")
        self.assertEqual(self.scope["report_scope"], "organization")
        self.assertEqual(self.scope["field_scope"], "rdn")

    def test_findings_count_matches_findings(self):
        processed = self.processed(self.plugin)
        self.assertEqual(
            processed["findings_count"], len(processed["findings"]["urls"])
        )
        self.assertEqual(
            processed["findings_count"], processed["crawl_scope"]["reported_url_count"]
        )

    def test_summary_states_what_was_excluded(self):
        processed = self.processed(self.plugin)
        self.assertIn("Crawl reached", processed["summary"])
        self.assertIn("excluded from this report", processed["summary"])

    def test_scope_panel_is_rendered_in_both_formats(self):
        processed = self.processed(self.plugin)
        for key in ("custom_html", "custom_html_pdf"):
            self.assertIn("Crawl Scope", processed[key])
            self.assertIn("chicago.suntimes.com", processed["custom_html"])


class TestHostEdgeCases(KatanaPostProcessBase):
    def test_multi_part_suffix(self):
        """shop.example.co.uk and www.example.co.uk share a registrable domain."""
        plugin = self.make_plugin(target="shop.example.co.uk")
        urls = [
            "https://shop.example.co.uk/basket",
            "https://www.example.co.uk/about",
            "https://other.co.uk/unrelated",
            "https://example.co.uk.evil.com/phish",
        ]
        processed = self.processed(plugin, urls=urls)
        hosts = {h["host"]: h["classification"] for h in processed["crawl_scope"]["hosts"]}
        self.assertEqual(hosts["shop.example.co.uk"], "target")
        self.assertEqual(hosts["www.example.co.uk"], "sibling")
        self.assertEqual(hosts["other.co.uk"], "external")
        self.assertEqual(hosts["example.co.uk.evil.com"], "external")

    def test_ip_target_has_no_siblings(self):
        """An IP has no registrable domain, so nothing may group with it."""
        plugin = self.make_plugin(target="192.168.1.10")
        urls = ["https://192.168.1.10/admin", "https://192.168.1.11/admin"]
        processed = self.processed(plugin, urls=urls)
        hosts = {h["host"]: h["classification"] for h in processed["crawl_scope"]["hosts"]}
        self.assertEqual(hosts["192.168.1.10"], "target")
        self.assertEqual(hosts["192.168.1.11"], "external")

    def test_malformed_lines_are_counted_not_crashed(self):
        plugin = self.make_plugin()
        urls = ["https://donate.wbez.org/ok", "not-a-url", ""]
        processed = self.processed(plugin, urls=urls)
        self.assertEqual(processed["crawl_scope"]["unparseable_lines"], 2)
        self.assertEqual(processed["findings"]["urls"], ["/ok"])

    def test_query_and_fragment_survive(self):
        plugin = self.make_plugin(report_scope="target")
        urls = ["https://donate.wbez.org/x?a=1&b=2#frag"]
        processed = self.processed(plugin, urls=urls)
        self.assertEqual(processed["findings"]["urls"], ["/x?a=1&b=2#frag"])


class TestFallbackPaths(KatanaPostProcessBase):
    def test_falls_back_to_katana_txt_and_still_scopes(self):
        """The report-only path reads katana.txt, and must scope it too."""
        plugin = self.make_plugin(report_scope="target")
        processed = self.processed(plugin, urls=[])
        self.assertEqual(processed["findings_count"], 3)
        self.assertNotIn("suntimes.com", json.dumps(processed["findings"]))

    def test_non_dict_results_fall_back_to_cli_target(self):
        """A failed run carries an error string, not a dict; target must survive."""
        plugin = self.make_plugin(report_scope="target")
        failed = plugin.get_result_dict(
            disposition="fail", results="katana exited with code 1"
        )
        path = plugin.post_process(failed, self.test_dir)
        with open(path) as f:
            processed = json.load(f)
        self.assertEqual(processed["findings_count"], 3)
        self.assertNotIn("twitter.com", json.dumps(processed["findings"]))


if __name__ == "__main__":
    unittest.main()


JS_ARTIFACT_URLS = [
    # Katana extracting a JS concatenation: "/files/wbez/js/" + e.iframeSrc + "/"
    "https://donate.wbez.org/files/wbez/js/'+e.iframeSrc+'",
    'https://donate.wbez.org/api/"+t+"/load',
    "https://donate.wbez.org/path/${endpoint}",
    "https://donate.wbez.org/a path/with spaces",
    "https://donate.wbez.org/<div>",
]

VOLATILE_PARAM_URLS = [
    "https://donate.wbez.org/page?_ga=2.111.222.333",
    "https://donate.wbez.org/page?_ga=2.999.888.777",
    "https://donate.wbez.org/page?utm_source=twitter&utm_campaign=spring",
    "https://donate.wbez.org/scripts/libphonenumber-min.js?_=1762800000000",
    "https://donate.wbez.org/scripts/libphonenumber-min.js?_=1762800099999",
]


class TestJavaScriptArtifacts(KatanaPostProcessBase):
    """Katana emits JS string fragments as URLs. They are not endpoints."""

    def setUp(self):
        super().setUp()
        self.plugin = self.make_plugin(report_scope="target")
        self.processed_out = self.processed(
            self.plugin, urls=TARGET_URLS + JS_ARTIFACT_URLS
        )
        self.scope = self.processed_out["crawl_scope"]

    def test_fragments_are_not_reported_as_urls(self):
        urls = self.processed_out["findings"]["urls"]
        for bad in ("'+e.iframeSrc+'", '"+t+"', "${endpoint}", "<div>"):
            self.assertFalse(
                any(bad in u for u in urls), f"{bad} leaked into the report"
            )

    def test_every_fragment_is_counted_not_silently_dropped(self):
        self.assertEqual(self.scope["js_artifact_count"], len(JS_ARTIFACT_URLS))

    def test_real_urls_survive_alongside_them(self):
        self.assertIn("/node/311", self.processed_out["findings"]["urls"])

    def test_summary_accounts_for_the_discards(self):
        self.assertIn(
            "JavaScript source fragment(s) were discarded",
            self.processed_out["summary"],
        )

    def test_percent_encoded_quote_is_a_real_url(self):
        """%27 is legal in a URL; only a literal quote signals a source fragment."""
        out = self.processed(
            self.plugin, urls=["https://donate.wbez.org/search?q=it%27s"]
        )
        self.assertEqual(out["crawl_scope"]["js_artifact_count"], 0)
        self.assertEqual(out["findings_count"], 1)

    def test_route_template_braces_are_kept(self):
        """/api/{id} is a route katana really found, not a JS fragment."""
        out = self.processed(self.plugin, urls=["https://donate.wbez.org/api/{id}"])
        self.assertEqual(out["crawl_scope"]["js_artifact_count"], 0)
        self.assertIn("/api/{id}", out["findings"]["urls"])


class TestVolatileQueryParams(KatanaPostProcessBase):
    """Cache-busting and campaign params mint a new URL on every page load."""

    def setUp(self):
        super().setUp()
        self.plugin = self.make_plugin(report_scope="target")
        self.processed_out = self.processed(self.plugin, urls=VOLATILE_PARAM_URLS)
        self.scope = self.processed_out["crawl_scope"]

    def test_duplicates_collapse_to_one_url_each(self):
        """5 raw URLs are 2 real pages once the volatile params come off."""
        self.assertEqual(
            sorted(self.processed_out["findings"]["urls"]),
            ["/page", "/scripts/libphonenumber-min.js"],
        )

    def test_collapse_is_counted(self):
        self.assertEqual(
            self.scope["canonicalized_url_count"], len(VOLATILE_PARAM_URLS)
        )

    def test_summary_accounts_for_the_collapse(self):
        self.assertIn("were collapsed after dropping", self.processed_out["summary"])

    def test_meaningful_params_are_preserved(self):
        out = self.processed(self.plugin, urls=[
            "https://donate.wbez.org/search?q=privacy&utm_source=x",
            "https://donate.wbez.org/search?q=security",
        ])
        self.assertEqual(
            sorted(out["findings"]["urls"]), ["/search?q=privacy", "/search?q=security"]
        )

    def test_ambiguous_names_are_left_alone(self):
        """v/t/ts/cb are plausible cache-busters and plausible real params.

        Merging two distinct URLs understates the surface, so they stay.
        """
        out = self.processed(self.plugin, urls=[
            "https://donate.wbez.org/api?v=1",
            "https://donate.wbez.org/api?v=2",
        ])
        self.assertEqual(out["findings_count"], 2)

    def test_prefix_match_is_not_a_substring_match(self):
        """utm_ is a prefix rule; a param merely containing it is untouched."""
        out = self.processed(self.plugin, urls=[
            "https://donate.wbez.org/x?my_utm_code=7",
        ])
        self.assertEqual(out["crawl_scope"]["canonicalized_url_count"], 0)
        self.assertIn("/x?my_utm_code=7", out["findings"]["urls"])
