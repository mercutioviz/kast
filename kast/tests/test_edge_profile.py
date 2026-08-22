"""Tests for the CDN / Edge Profile plugin.

No network: the HTTP probe and every DNS lookup are mocked. The posture
crossings (edge verdict x wafw00f verdict) are the load-bearing part — they
decide which registry issue the report claims.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from kast.plugins.edge_profile_plugin import (
    CNAME_CHAIN_LIMIT,
    EDGE_CNAME_SUFFIXES,
    EDGE_NS_SUFFIXES,
    EdgeProfilePlugin,
)


class _FakeCname:
    def __init__(self, target):
        self.target = target + "."


def _cname_answer(chain, host):
    if host not in chain:
        raise Exception("NoAnswer")
    return [_FakeCname(chain[host])]


class MinimalArgs:
    verbose = False
    mode = "passive"


def _plugin():
    return EdgeProfilePlugin(MinimalArgs())


class FakeResponse:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = {c: "x" for c in (cookies or [])}


class TestIdentity(unittest.TestCase):
    def test_is_available(self):
        self.assertTrue(_plugin().is_available())

    def test_metadata(self):
        meta = _plugin().get_metadata()
        self.assertEqual(meta["name"], "edge_profile")
        self.assertEqual(meta["scan_type"], "passive")
        self.assertEqual(meta["display_name"], "CDN / Edge Profile")

    def test_runs_after_wafw00f_and_whatweb(self):
        plugin = _plugin()
        self.assertEqual(
            [d["plugin"] for d in plugin.dependencies], ["wafw00f", "whatweb"]
        )
        # Sequential mode ignores dependencies entirely and orders by priority,
        # so the number matters independently of the declarations above.
        self.assertGreater(plugin.priority, 15)


class TestHeaderSignatures(unittest.TestCase):
    def _providers(self, headers):
        return {s["provider"] for s in _plugin()._match_headers(headers)}

    def test_cloudflare_via_cf_ray(self):
        self.assertEqual(self._providers({"cf-ray": "8a1b2c3d"}), {"Cloudflare"})

    def test_cloudfront_via_amz_header(self):
        self.assertEqual(self._providers({"x-amz-cf-id": "abc"}), {"Amazon CloudFront"})

    def test_akamai_via_server_value(self):
        self.assertEqual(self._providers({"server": "AkamaiGHost"}), {"Akamai"})

    def test_fastly_via_x_timer(self):
        self.assertEqual(self._providers({"x-timer": "S1234.56"}), {"Fastly"})

    def test_imperva_via_x_cdn_value(self):
        self.assertEqual(
            self._providers({"x-cdn": "Incapsula"}), {"Imperva (Incapsula)"}
        )

    def test_plain_nginx_is_not_an_edge(self):
        self.assertEqual(self._providers({"server": "nginx/1.24.0"}), set())

    def test_value_pattern_must_match_not_just_header_presence(self):
        """`server` alone means nothing — only its value attributes a provider."""
        self.assertEqual(self._providers({"server": "Apache/2.4.58"}), set())

    def test_header_match_is_case_insensitive_on_value(self):
        self.assertEqual(self._providers({"server": "CLOUDFLARE"}), {"Cloudflare"})

    def test_signal_shape(self):
        signal = _plugin()._match_headers({"cf-ray": "8a1b"})[0]
        self.assertEqual(signal["source"], "response_header")
        self.assertEqual(signal["confidence"], "confirmed")
        self.assertEqual(signal["evidence"], "cf-ray: 8a1b")


class TestCookieSignatures(unittest.TestCase):
    def _providers(self, cookies):
        return {s["provider"] for s in _plugin()._match_cookies(cookies)}

    def test_cloudflare_bot_management_cookie(self):
        self.assertEqual(self._providers(["__cf_bm"]), {"Cloudflare"})

    def test_incapsula_session_cookie_prefix(self):
        self.assertEqual(
            self._providers(["incap_ses_123_456"]), {"Imperva (Incapsula)"}
        )

    def test_ordinary_cookie_ignored(self):
        self.assertEqual(self._providers(["PHPSESSID", "csrftoken"]), set())


class TestSuffixMatching(unittest.TestCase):
    def test_cname_suffix(self):
        self.assertEqual(
            _plugin()._match_suffix("d111abc.cloudfront.net", EDGE_CNAME_SUFFIXES),
            "Amazon CloudFront",
        )

    def test_ns_suffix_identifies_cloudflare(self):
        self.assertEqual(
            _plugin()._match_suffix("kate.ns.cloudflare.com", EDGE_NS_SUFFIXES),
            "Cloudflare",
        )

    def test_unrelated_host_matches_nothing(self):
        self.assertIsNone(
            _plugin()._match_suffix("ns1.example.com", EDGE_NS_SUFFIXES)
        )

    def test_partial_label_does_not_match(self):
        """notcloudfront.net must not match the cloudfront.net suffix."""
        self.assertIsNone(
            _plugin()._match_suffix("notcloudfront.net", EDGE_CNAME_SUFFIXES)
        )

    def test_longest_suffix_wins(self):
        self.assertEqual(
            _plugin()._match_suffix("e123.a.akamaiedge.net", EDGE_CNAME_SUFFIXES),
            "Akamai",
        )

    def test_apex_handles_multi_part_suffix(self):
        self.assertEqual(_plugin()._apex("www.example.co.uk"), "example.co.uk")


class TestClassification(unittest.TestCase):
    def _classify(self, signals, generic, reachable=True):
        results = _plugin()._build_results(
            "example.com", signals, generic, "no_waf", reachable
        )
        return results["classification"]

    def test_named_provider_is_specific(self):
        signals = [{"provider": "Cloudflare", "source": "response_header",
                    "evidence": "cf-ray: x", "confidence": "confirmed"}]
        self.assertEqual(self._classify(signals, []), "specific")

    def test_generic_headers_only(self):
        self.assertEqual(self._classify([], ["via", "x-cache"]), "generic")

    def test_nothing_found_is_none(self):
        self.assertEqual(self._classify([], []), "none")

    def test_unreachable_target_is_unknown_not_none(self):
        """A failed fetch must never be reported to a prospect as "no CDN"."""
        self.assertEqual(self._classify([], [], reachable=False), "unknown")

    def test_unreachable_target_emits_no_issue(self):
        results = _plugin()._build_results("example.com", [], [], "no_waf", False)
        self.assertEqual(
            _plugin()._extract_issues(
                results["classification"], results["waf_classification"]
            ),
            [],
        )

    def test_providers_are_deduplicated_and_sorted(self):
        signals = [
            {"provider": "Cloudflare", "source": "response_header",
             "evidence": "cf-ray: x", "confidence": "confirmed"},
            {"provider": "Cloudflare", "source": "dns_ns",
             "evidence": "kate.ns.cloudflare.com", "confidence": "likely"},
            {"provider": "Akamai", "source": "dns_cname",
             "evidence": "e1.akamaiedge.net", "confidence": "confirmed"},
        ]
        results = _plugin()._build_results("example.com", signals, [], "no_waf", True)
        self.assertEqual(results["providers"], ["Akamai", "Cloudflare"])


class TestPostureCrossings(unittest.TestCase):
    """Edge verdict x wafw00f verdict -> issue IDs. The sales-critical logic."""

    def test_cdn_present_no_waf(self):
        self.assertEqual(
            _plugin()._extract_issues("specific", "no_waf"), ["cdn-without-waf"]
        )

    def test_generic_edge_no_waf_still_flags(self):
        self.assertEqual(
            _plugin()._extract_issues("generic", "no_waf"), ["cdn-without-waf"]
        )

    def test_cdn_present_with_waf_is_clean(self):
        self.assertEqual(_plugin()._extract_issues("specific", "specific"), [])

    def test_no_edge_at_all(self):
        self.assertEqual(
            _plugin()._extract_issues("none", "no_waf"), ["no-cdn-detected"]
        )

    def test_no_edge_flagged_even_when_a_waf_exists(self):
        self.assertEqual(
            _plugin()._extract_issues("none", "specific"), ["no-cdn-detected"]
        )

    def test_disabled_plugin_claims_nothing(self):
        self.assertEqual(_plugin()._extract_issues("disabled", "unknown"), [])

    def test_issue_ids_exist_in_the_registry(self):
        from kast.cli.registry import REGISTRY_PATH, _load_registry

        registry = _load_registry(REGISTRY_PATH)
        for issue_id in ("cdn-without-waf", "no-cdn-detected"):
            self.assertIn(issue_id, registry)
            self.assertEqual(registry[issue_id]["severity"], "Low")

    def test_posture_names_the_provider(self):
        posture = _plugin()._describe_posture("specific", ["Cloudflare"], "no_waf")
        self.assertIn("Cloudflare", posture)
        self.assertIn("no WAF", posture)

    def test_posture_when_wafw00f_did_not_run(self):
        posture = _plugin()._describe_posture("specific", ["Akamai"], "unknown")
        self.assertIn("unknown", posture)


class TestWafCorrelation(unittest.TestCase):
    def _write_wafw00f(self, tmpdir, results, disposition="success"):
        payload = {
            "findings": {
                "name": "wafw00f",
                "disposition": disposition,
                "results": results,
            }
        }
        with open(os.path.join(tmpdir, "wafw00f_processed.json"), "w") as f:
            json.dump(payload, f)

    def test_no_waf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_wafw00f(tmpdir, [{"detected": False, "firewall": "None"}])
            self.assertEqual(_plugin()._read_waf_classification(tmpdir), "no_waf")

    def test_specific_waf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_wafw00f(
                tmpdir, [{"detected": True, "firewall": "Cloudflare"}]
            )
            self.assertEqual(_plugin()._read_waf_classification(tmpdir), "specific")

    def test_generic_waf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_wafw00f(tmpdir, [{"detected": True, "firewall": "Generic"}])
            self.assertEqual(_plugin()._read_waf_classification(tmpdir), "generic")

    def test_missing_file_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(_plugin()._read_waf_classification(tmpdir), "unknown")

    def test_failed_wafw00f_run_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_wafw00f(tmpdir, "Tool not available.", disposition="fail")
            self.assertEqual(_plugin()._read_waf_classification(tmpdir), "unknown")


class TestWhatwebCorroboration(unittest.TestCase):
    def test_reads_edge_plugin_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "whatweb.json"), "w") as f:
                json.dump(
                    [{"target": "https://example.com",
                      "plugins": {"Cloudflare": {}, "Title": {}}}],
                    f,
                )
            signals = _plugin()._analyze_whatweb(tmpdir)
            self.assertEqual([s["provider"] for s in signals], ["Cloudflare"])
            self.assertEqual(signals[0]["confidence"], "likely")

    def test_missing_file_is_silent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(_plugin()._analyze_whatweb(tmpdir), [])


class TestRun(unittest.TestCase):
    def test_cloudflare_without_waf_end_to_end(self):
        plugin = _plugin()
        plugin.dns_enabled = False
        with tempfile.TemporaryDirectory() as tmpdir:
            TestWafCorrelation()._write_wafw00f(
                tmpdir, [{"detected": False, "firewall": "None"}]
            )
            with patch(
                "kast.plugins.edge_profile_plugin.requests.get",
                return_value=FakeResponse(
                    headers={"cf-ray": "8a1b", "Server": "cloudflare"}
                ),
            ):
                result = plugin.run("example.com", tmpdir, False)

            self.assertEqual(result["disposition"], "success")
            results = result["results"]
            self.assertEqual(results["classification"], "specific")
            self.assertEqual(results["providers"], ["Cloudflare"])
            self.assertEqual(results["waf_classification"], "no_waf")

            processed_path = plugin.post_process(result, tmpdir)
            with open(processed_path) as f:
                processed = json.load(f)
            self.assertEqual(processed["issues"], ["cdn-without-waf"])

    def test_unreachable_target_makes_no_claim(self):
        plugin = _plugin()
        plugin.dns_enabled = False
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "kast.plugins.edge_profile_plugin.requests.get",
                side_effect=OSError("connection refused"),
            ):
                result = plugin.run("example.com", tmpdir, False)

            self.assertEqual(result["disposition"], "success")
            self.assertEqual(result["results"]["classification"], "unknown")

            processed_path = plugin.post_process(result, tmpdir)
            with open(processed_path) as f:
                processed = json.load(f)
            self.assertEqual(processed["issues"], [])

    def test_disabled_plugin(self):
        plugin = _plugin()
        plugin.enabled = False
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("kast.plugins.edge_profile_plugin.requests.get") as mock_get:
                result = plugin.run("example.com", tmpdir, False)
            mock_get.assert_not_called()
            self.assertEqual(result["results"]["classification"], "disabled")

    def test_report_only_reloads_without_probing(self):
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            stored = {"target": "example.com", "providers": ["Fastly"],
                      "signals": [], "generic_edge_headers": [],
                      "classification": "specific", "waf_classification": "no_waf",
                      "edge_posture": "stored"}
            with open(os.path.join(tmpdir, "edge_profile.json"), "w") as f:
                json.dump(stored, f)
            with patch("kast.plugins.edge_profile_plugin.requests.get") as mock_get:
                result = plugin.run("example.com", tmpdir, True)
            mock_get.assert_not_called()
            self.assertEqual(result["results"], stored)

    def test_report_only_without_prior_results_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _plugin().run("example.com", tmpdir, True)
            self.assertEqual(result["disposition"], "fail")

    def test_raw_json_written_for_report_only_reuse(self):
        plugin = _plugin()
        plugin.dns_enabled = False
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "kast.plugins.edge_profile_plugin.requests.get",
                return_value=FakeResponse(headers={"x-timer": "S1"}),
            ):
                plugin.run("example.com", tmpdir, False)
            self.assertTrue(
                os.path.isfile(os.path.join(tmpdir, "edge_profile.json"))
            )


class TestDnsSignals(unittest.TestCase):
    def test_cname_to_cloudfront(self):
        plugin = _plugin()

        class FakeRdata:
            target = "d111abc.cloudfront.net."

        with patch(
            "kast.plugins.edge_profile_plugin.dns.resolver.resolve",
            return_value=[FakeRdata()],
        ):
            signals = plugin._probe_cname("www.example.com")

        self.assertEqual(signals[0]["provider"], "Amazon CloudFront")
        self.assertEqual(signals[0]["source"], "dns_cname")
        self.assertEqual(signals[0]["confidence"], "confirmed")

    def test_chain_is_followed_past_non_matching_hops(self):
        """www.barracuda.com chains Traffic Manager -> WaaS -> Front Door; a
        single-hop lookup stops at hop 1 and reports no edge at all."""
        plugin = _plugin()
        chain = {
            "www.example.com": "example.trafficmanager.net",
            "example.trafficmanager.net": "app1.prod.cudawaas.com",
            "app1.prod.cudawaas.com": "ep-1.a01.azurefd.net",
        }
        with patch(
            "kast.plugins.edge_profile_plugin.dns.resolver.resolve",
            side_effect=lambda h, _t: _cname_answer(chain, h),
        ):
            signals = plugin._probe_cname("www.example.com")

        self.assertEqual(
            [(s["provider"], s["evidence"]) for s in signals],
            [
                ("Barracuda WaaS", "app1.prod.cudawaas.com"),
                ("Azure Front Door / CDN", "ep-1.a01.azurefd.net"),
            ],
        )

    def test_chain_loop_does_not_hang(self):
        plugin = _plugin()
        chain = {"a.example.com": "b.example.com", "b.example.com": "a.example.com"}
        with patch(
            "kast.plugins.edge_profile_plugin.dns.resolver.resolve",
            side_effect=lambda h, _t: _cname_answer(chain, h),
        ):
            self.assertEqual(plugin._probe_cname("a.example.com"), [])

    def test_chain_is_capped(self):
        """An unbounded chain must not spray lookups at the prospect's resolver."""
        plugin = _plugin()
        calls = []

        def endless(host, _rtype):
            calls.append(host)
            return [_FakeCname(f"{host}.x")]

        with patch(
            "kast.plugins.edge_profile_plugin.dns.resolver.resolve",
            side_effect=endless,
        ):
            plugin._probe_cname("a.example.com")
        self.assertEqual(len(calls), CNAME_CHAIN_LIMIT)

    def test_ns_delegation_scores_likely_not_confirmed(self):
        """Hosting DNS at a CDN does not prove traffic is proxied through it."""
        plugin = _plugin()

        class FakeRdata:
            target = "kate.ns.cloudflare.com."

        with patch(
            "kast.plugins.edge_profile_plugin.dns.resolver.resolve",
            return_value=[FakeRdata()],
        ):
            signals = plugin._probe_ns("www.example.com")

        self.assertEqual(signals[0]["provider"], "Cloudflare")
        self.assertEqual(signals[0]["confidence"], "likely")

    def test_lookup_failure_is_not_fatal(self):
        plugin = _plugin()
        with patch(
            "kast.plugins.edge_profile_plugin.dns.resolver.resolve",
            side_effect=Exception("NXDOMAIN"),
        ):
            self.assertEqual(plugin._probe_dns("www.example.com"), [])


class TestPostProcess(unittest.TestCase):
    def _processed(self, results):
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = plugin.get_result_dict("success", results)
            path = plugin.post_process(raw, tmpdir)
            with open(path) as f:
                return json.load(f)

    def _specific_results(self):
        return _plugin()._build_results(
            "example.com",
            [{"provider": "Cloudflare", "source": "response_header",
              "evidence": "cf-ray: 8a1b", "confidence": "confirmed"}],
            ["via"],
            "no_waf",
            True,
        )

    def test_contract_keys_present(self):
        processed = self._processed(self._specific_results())
        for key in ("plugin-name", "plugin-display-name", "plugin-description",
                    "plugin-website-url", "findings_count", "summary", "details",
                    "issues", "executive_summary", "custom_html"):
            self.assertIn(key, processed)
        self.assertEqual(processed["plugin-name"], "edge_profile")

    def test_findings_is_the_raw_wrapper_the_report_expects(self):
        """report/data.py reads findings.disposition and findings.results; a flat
        results dict there renders the per-tool details block blank."""
        processed = self._processed(self._specific_results())
        self.assertEqual(processed["findings"]["disposition"], "success")
        self.assertEqual(
            processed["findings"]["results"]["classification"], "specific"
        )

    def test_findings_count_is_provider_count(self):
        processed = self._processed(self._specific_results())
        self.assertEqual(processed["findings_count"], 1)

    def test_findings_count_is_an_int_when_nothing_found(self):
        results = _plugin()._build_results("example.com", [], [], "no_waf", True)
        processed = self._processed(results)
        self.assertIsInstance(processed["findings_count"], int)
        self.assertEqual(processed["findings_count"], 0)

    def test_custom_html_renders_the_provider_table(self):
        processed = self._processed(self._specific_results())
        html = processed["custom_html"]
        self.assertIn("Cloudflare", html)
        self.assertIn("cf-ray: 8a1b", html)
        self.assertIn("edge-profile-results", html)

    def test_no_pdf_variant_emitted(self):
        """The v2 dual custom_html/custom_html_pdf requirement is gone."""
        self.assertNotIn("custom_html_pdf", self._processed(self._specific_results()))

    def test_executive_summary_frames_the_enable_not_buy_story(self):
        processed = self._processed(self._specific_results())
        self.assertIn("Cloudflare", processed["executive_summary"])
        self.assertIn("not switched on", processed["executive_summary"])

    def test_malformed_raw_output_still_emits_a_processed_file(self):
        """kast-web's state machine keys off the completion marker existing."""
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = plugin.get_result_dict("fail", "Something went wrong.")
            path = plugin.post_process(raw, tmpdir)
            self.assertTrue(os.path.isfile(path))
            with open(path) as f:
                processed = json.load(f)
            self.assertEqual(processed["issues"], [])
            self.assertEqual(processed["findings_count"], 0)


if __name__ == "__main__":
    unittest.main()
