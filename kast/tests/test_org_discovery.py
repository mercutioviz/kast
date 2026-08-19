"""Tests for the organization-discovery plugin.

org_discovery reaches five external sources (crt.sh, DNS, WHOIS, amass,
Shodan). None of them are contacted here — every network and subprocess
boundary is mocked, and the post-processing path runs off the committed
fixture at ``fixtures/org_discovery_output.json``.

Several test groups are regression guards for bugs fixed in shipped
releases; each is annotated with the version that fixed it.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from kast.plugins.org_discovery_plugin import OrgDiscoveryPlugin

FIXTURE = Path(__file__).parent / "fixtures" / "org_discovery_output.json"


def _make_plugin(**config):
    plugin = OrgDiscoveryPlugin(Mock(verbose=False))
    for key, value in config.items():
        setattr(plugin, key, value)
    return plugin


def _cert(issuer_org=None, name_value="", common_name=""):
    return {
        "issuer_name": f"C=US, O={issuer_org}, CN=Some CA" if issuer_org else "C=US, CN=Some CA",
        "name_value": name_value,
        "common_name": common_name,
    }


class TestOrgDiscoveryIdentity(unittest.TestCase):
    """Class-attribute identity must follow the v3 contract."""

    def setUp(self):
        self.plugin = _make_plugin()

    def test_identity_class_attributes(self):
        self.assertEqual(OrgDiscoveryPlugin.name, "org_discovery")
        self.assertEqual(OrgDiscoveryPlugin.display_name, "Organization Domain Discovery")
        self.assertEqual(OrgDiscoveryPlugin.scan_type, "passive")
        self.assertEqual(OrgDiscoveryPlugin.output_type, "file")
        self.assertEqual(OrgDiscoveryPlugin.priority, 3)
        self.assertTrue(OrgDiscoveryPlugin.description)

    def test_config_schema_well_formed(self):
        schema = OrgDiscoveryPlugin.config_schema
        self.assertEqual(schema["type"], "object")
        for key in ("crtsh_enabled", "amass_enabled", "shodan_enabled",
                    "confidence_threshold", "max_domains"):
            self.assertIn(key, schema["properties"])

    def test_defaults_applied(self):
        self.assertTrue(self.plugin.crtsh_enabled)
        self.assertTrue(self.plugin.dns_analysis_enabled)
        self.assertFalse(self.plugin.whois_enabled)
        self.assertFalse(self.plugin.shodan_enabled)
        self.assertEqual(self.plugin.confidence_threshold, 0.3)
        self.assertEqual(self.plugin.max_domains, 50)

    def test_is_available_returns_true(self):
        # Pure-Python plugin — every external source degrades gracefully.
        self.assertTrue(self.plugin.is_available())

    def test_confidence_weights_cover_every_source_tag(self):
        emitted = {"crtsh_org", "crtsh_domain", "spf_include", "dmarc_ref",
                   "whois_match", "amass", "shodan"}
        self.assertEqual(emitted, set(OrgDiscoveryPlugin.CONFIDENCE_WEIGHTS))


class TestApexExtraction(unittest.TestCase):
    """_apex / _apexes_from_name."""

    def setUp(self):
        self.plugin = _make_plugin()

    def test_apex_from_fqdn(self):
        self.assertEqual(self.plugin._apex("www.example.com"), "example.com")
        self.assertEqual(self.plugin._apex("example.com"), "example.com")

    def test_apex_handles_multipart_suffix(self):
        self.assertEqual(self.plugin._apex("shop.example.co.uk"), "example.co.uk")

    def test_apex_returns_empty_for_garbage(self):
        self.assertEqual(self.plugin._apex("localhost"), "")
        self.assertEqual(self.plugin._apex(""), "")

    def test_apexes_from_name_splits_and_strips_wildcards(self):
        names = "*.example.com\nwww.example.com mail.example-corp.net"
        self.assertEqual(
            self.plugin._apexes_from_name(names),
            {"example.com", "example-corp.net"},
        )

    def test_apexes_from_name_ignores_non_domains(self):
        self.assertEqual(self.plugin._apexes_from_name("not a domain"), set())


class TestCrtshGet(unittest.TestCase):
    """_crtsh_get retry behaviour. 502 retry added in v3.0.30."""

    def setUp(self):
        self.plugin = _make_plugin(crtsh_max_retries=2, crtsh_retry_base_delay=1.0)

    def _response(self, status_code, payload=None):
        resp = Mock()
        resp.status_code = status_code
        resp.json.return_value = payload if payload is not None else []
        if status_code >= 400:
            resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
                f"{status_code} Server Error")
        else:
            resp.raise_for_status.return_value = None
        return resp

    @patch("kast.plugins.org_discovery_plugin.time.sleep")
    @patch("kast.plugins.org_discovery_plugin.requests.get")
    def test_retries_on_502(self, mock_get, mock_sleep):
        mock_get.side_effect = [self._response(502), self._response(200, [{"ok": 1}])]
        self.assertEqual(self.plugin._crtsh_get("https://crt.sh/?q=x"), [{"ok": 1}])
        self.assertEqual(mock_get.call_count, 2)

    @patch("kast.plugins.org_discovery_plugin.time.sleep")
    @patch("kast.plugins.org_discovery_plugin.requests.get")
    def test_retries_on_503(self, mock_get, mock_sleep):
        mock_get.side_effect = [self._response(503), self._response(200, [{"ok": 1}])]
        self.assertEqual(self.plugin._crtsh_get("https://crt.sh/?q=x"), [{"ok": 1}])
        self.assertEqual(mock_get.call_count, 2)

    @patch("kast.plugins.org_discovery_plugin.time.sleep")
    @patch("kast.plugins.org_discovery_plugin.requests.get")
    def test_backoff_is_exponential(self, mock_get, mock_sleep):
        mock_get.side_effect = [self._response(503), self._response(503),
                                self._response(200, [])]
        self.plugin._crtsh_get("https://crt.sh/?q=x")
        self.assertEqual([c.args[0] for c in mock_sleep.call_args_list], [1.0, 2.0])

    @patch("kast.plugins.org_discovery_plugin.time.sleep")
    @patch("kast.plugins.org_discovery_plugin.requests.get")
    def test_raises_after_retries_exhausted(self, mock_get, mock_sleep):
        # The final attempt skips the retry branch and falls through to
        # raise_for_status(), so the surfaced error is HTTPError — the
        # trailing ConnectionError in _crtsh_get is unreachable.
        mock_get.return_value = self._response(503)
        with self.assertRaises(requests.exceptions.HTTPError):
            self.plugin._crtsh_get("https://crt.sh/?q=x")
        self.assertEqual(mock_get.call_count, 3)  # initial + 2 retries

    @patch("kast.plugins.org_discovery_plugin.time.sleep")
    @patch("kast.plugins.org_discovery_plugin.requests.get")
    def test_exhausted_retries_are_caught_by_callers(self, mock_get, mock_sleep):
        # Whatever _crtsh_get raises, neither caller may propagate it.
        mock_get.return_value = self._response(503)
        self.assertEqual(self.plugin._extract_org_name("example.com"), (None, "503 Server Error"))
        self.assertEqual(self.plugin._crtsh_search("example.com", "crtsh_domain"), {})

    @patch("kast.plugins.org_discovery_plugin.time.sleep")
    @patch("kast.plugins.org_discovery_plugin.requests.get")
    def test_timeout_is_retried_then_reraised(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.Timeout("slow")
        with self.assertRaises(requests.exceptions.Timeout):
            self.plugin._crtsh_get("https://crt.sh/?q=x")
        self.assertEqual(mock_get.call_count, 3)

    @patch("kast.plugins.org_discovery_plugin.requests.get")
    def test_query_url_is_recorded(self, mock_get):
        mock_get.return_value = self._response(200, [])
        self.plugin._crtsh_get("https://crt.sh/?q=example.com&output=json")
        self.assertEqual(self.plugin.command_executed["crtsh_queries"],
                         ["https://crt.sh/?q=example.com&output=json"])


class TestExtractOrgName(unittest.TestCase):
    """_extract_org_name. CA substring skipping fixed in v3.0.30; quote
    stripping in v3.0.26."""

    def setUp(self):
        self.plugin = _make_plugin()

    def test_override_short_circuits(self):
        self.plugin.org_name_override = "Acme Corp"
        with patch.object(self.plugin, "_crtsh_get") as mock_get:
            name, source = self.plugin._extract_org_name("example.com")
        self.assertEqual((name, source), ("Acme Corp", "config override"))
        mock_get.assert_not_called()

    def test_most_common_non_ca_org_wins(self):
        certs = [_cert("Example Holdings Inc"), _cert("Example Holdings Inc"),
                 _cert("Other Org")]
        with patch.object(self.plugin, "_crtsh_get", return_value=certs):
            name, source = self.plugin._extract_org_name("example.com")
        self.assertEqual(name, "Example Holdings Inc")
        self.assertEqual(source, "crt.sh certificate issuer")

    def test_bare_ca_name_is_skipped(self):
        # v3.0.30: the old exact-match set held "digicert inc", so a bare
        # "DigiCert" issuer was mistaken for the site owner.
        certs = [_cert("DigiCert")] * 5 + [_cert("Example Holdings Inc")]
        with patch.object(self.plugin, "_crtsh_get", return_value=certs):
            name, _ = self.plugin._extract_org_name("example.com")
        self.assertEqual(name, "Example Holdings Inc")

    def test_ca_name_variants_are_all_skipped(self):
        for variant in ("DigiCert", "DigiCert Inc", "DigiCert, Inc.",
                        "Let's Encrypt", "Sectigo Limited", "GlobalSign nv-sa",
                        "Google Trust Services LLC", "Amazon", "Cloudflare, Inc."):
            with self.subTest(variant=variant):
                with patch.object(self.plugin, "_crtsh_get", return_value=[_cert(variant)]):
                    name, source = self.plugin._extract_org_name("example.com")
                self.assertIsNone(name)
                self.assertEqual(source, "No org found")

    def test_quotes_are_stripped_from_org_name(self):
        # v3.0.26: O="Example Holdings" leaked its quotes into the amass and
        # Shodan queries.
        certs = [{"issuer_name": 'C=US, O="Example Holdings", CN=CA'}]
        with patch.object(self.plugin, "_crtsh_get", return_value=certs):
            name, _ = self.plugin._extract_org_name("example.com")
        self.assertEqual(name, "Example Holdings")

    def test_crtsh_failure_returns_error_reason(self):
        with patch.object(self.plugin, "_crtsh_get", side_effect=RuntimeError("boom")):
            name, source = self.plugin._extract_org_name("example.com")
        self.assertIsNone(name)
        self.assertIn("boom", source)


class TestCrtshSearch(unittest.TestCase):
    """_crtsh_search domain harvesting."""

    def setUp(self):
        self.plugin = _make_plugin()

    def test_collects_apexes_from_both_name_fields(self):
        certs = [
            _cert(name_value="*.example.com\nwww.example.com", common_name="cdn.examplecdn.io"),
            _cert(name_value="mail.example-corp.net"),
        ]
        with patch.object(self.plugin, "_crtsh_get", return_value=certs):
            domains = self.plugin._crtsh_search("O=Example", "crtsh_org")
        self.assertEqual(set(domains), {"example.com", "examplecdn.io", "example-corp.net"})
        self.assertEqual(domains["example.com"]["sources"], {"crtsh_org"})

    def test_cert_counts_accumulate(self):
        certs = [_cert(name_value="example.com"), _cert(name_value="www.example.com")]
        with patch.object(self.plugin, "_crtsh_get", return_value=certs):
            domains = self.plugin._crtsh_search("example.com", "crtsh_domain")
        self.assertEqual(domains["example.com"]["cert_count"], 2)

    def test_failure_returns_empty_dict(self):
        with patch.object(self.plugin, "_crtsh_get", side_effect=RuntimeError("boom")):
            self.assertEqual(self.plugin._crtsh_search("example.com", "crtsh_domain"), {})


class TestWhois(unittest.TestCase):
    """_query_whois gating."""

    def test_disabled_by_default(self):
        plugin = _make_plugin()
        self.assertEqual(plugin._query_whois("example.com"),
                         {"status": "disabled", "org": None, "email": None})

    def test_no_query_recorded_when_disabled(self):
        plugin = _make_plugin()
        plugin._query_whois("example.com")
        self.assertEqual(plugin.command_executed["whois_queries"], [])


class TestAmass(unittest.TestCase):
    """_run_amass. The -org flag was removed in v3.0.30 (dropped upstream in
    amass v4/v5; its presence made v5.1.1 exit 1)."""

    def setUp(self):
        self.plugin = _make_plugin()

    def test_disabled_returns_empty(self):
        self.plugin.amass_enabled = False
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.plugin._run_amass("example.com", "Example", tmp), {})

    @patch("kast.plugins.org_discovery_plugin.shutil.which", return_value=None)
    def test_missing_binary_returns_empty(self, mock_which):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.plugin._run_amass("example.com", "Example", tmp), {})

    @patch("kast.plugins.org_discovery_plugin.shutil.which", return_value="/usr/local/bin/amass")
    @patch("kast.plugins.org_discovery_plugin.subprocess.run")
    def test_command_shape_has_no_org_flag(self, mock_run, mock_which):
        mock_run.return_value = Mock(returncode=0, stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            self.plugin._run_amass("example.com", "Example Holdings Inc", tmp)
        cmd = mock_run.call_args.args[0]
        self.assertNotIn("-org", cmd)
        self.assertEqual(cmd[:5], ["amass", "enum", "-passive", "-d", "example.com"])
        self.assertIn("-passive", cmd)

    @patch("kast.plugins.org_discovery_plugin.shutil.which", return_value="/usr/local/bin/amass")
    @patch("kast.plugins.org_discovery_plugin.subprocess.run")
    def test_parses_jsonl_output(self, mock_run, mock_which):
        mock_run.return_value = Mock(returncode=0, stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            lines = [
                json.dumps({"name": "mail.example-corp.net", "sources": ["Crtsh"]}),
                json.dumps({"name": "vpn.example-corp.net", "sources": "DNSDumpster"}),
                "",
                "{not json}",
                json.dumps({"name": ""}),
            ]
            (Path(tmp) / "amass_output.json").write_text("\n".join(lines))
            domains = self.plugin._run_amass("example.com", "Example", tmp)
        self.assertEqual(set(domains), {"example-corp.net"})
        self.assertEqual(domains["example-corp.net"]["amass_sources"],
                         {"Crtsh", "DNSDumpster"})
        self.assertEqual(domains["example-corp.net"]["sources"], {"amass"})

    @patch("kast.plugins.org_discovery_plugin.shutil.which", return_value="/usr/local/bin/amass")
    @patch("kast.plugins.org_discovery_plugin.subprocess.run")
    def test_missing_output_file_returns_empty(self, mock_run, mock_which):
        mock_run.return_value = Mock(returncode=1, stderr="failed")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.plugin._run_amass("example.com", "Example", tmp), {})

    @patch("kast.plugins.org_discovery_plugin.shutil.which", return_value="/usr/local/bin/amass")
    @patch("kast.plugins.org_discovery_plugin.subprocess.run",
           side_effect=OSError("exec format error"))
    def test_subprocess_error_does_not_raise(self, mock_run, mock_which):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.plugin._run_amass("example.com", "Example", tmp), {})


class TestShodanGating(unittest.TestCase):
    """_shodan_available / _search_shodan gating. Never contacts Shodan."""

    def test_disabled_returns_empty(self):
        plugin = _make_plugin()
        self.assertEqual(plugin._search_shodan("example.com", "Example"), ({}, []))

    def test_unavailable_without_api_key(self):
        plugin = _make_plugin(shodan_enabled=True, shodan_api_key=None)
        available, reason = plugin._shodan_available()
        self.assertFalse(available)
        self.assertTrue(reason)

    def test_enabled_but_keyless_returns_empty_without_calling_api(self):
        plugin = _make_plugin(shodan_enabled=True, shodan_api_key=None)
        self.assertEqual(plugin._search_shodan("example.com", "Example"), ({}, []))
        self.assertEqual(plugin.command_executed["shodan_queries"], [])


class TestCorrelate(unittest.TestCase):
    """_correlate scoring, filtering, and merging."""

    def setUp(self):
        self.plugin = _make_plugin()

    def _correlate(self, **kwargs):
        args = {
            "target_apex": "example.com",
            "raw_domains": {},
            "spf_domains": [],
            "dmarc_domains": [],
            "whois_info": {"status": "disabled", "org": None},
            "amass_domains": {},
            "shodan_domains": {},
            "shodan_exposure": [],
        }
        args.update(kwargs)
        return self.plugin._correlate(**args)

    def test_target_apex_is_excluded(self):
        raw = {"example.com": {"sources": {"crtsh_org"}, "cert_count": 9}}
        self.assertEqual(self._correlate(raw_domains=raw), [])

    def test_score_sums_source_weights(self):
        raw = {"example-corp.net": {"sources": {"crtsh_org", "crtsh_domain"}, "cert_count": 2}}
        result = self._correlate(raw_domains=raw)
        self.assertEqual(result[0]["confidence"], 0.7)  # 0.4 + 0.3

    def test_score_is_capped_at_one(self):
        raw = {"example-corp.net": {
            "sources": {"crtsh_org", "crtsh_domain", "amass", "shodan", "spf_include"},
            "cert_count": 2}}
        self.assertEqual(self._correlate(raw_domains=raw)[0]["confidence"], 1.0)

    def test_below_threshold_is_dropped(self):
        self.plugin.confidence_threshold = 0.35
        self.assertEqual(self._correlate(dmarc_domains=["example-mail.com"]), [])  # 0.2

    def test_spf_and_dmarc_sources_merge_on_one_domain(self):
        result = self._correlate(spf_domains=["example-mail.com"],
                                 dmarc_domains=["example-mail.com"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sources"], ["dmarc_ref", "spf_include"])
        self.assertEqual(result[0]["confidence"], 0.5)

    def test_whois_org_boosts_only_already_known_domains(self):
        raw = {"example-corp.net": {"sources": {"crtsh_domain"}, "cert_count": 1}}
        result = self._correlate(raw_domains=raw,
                                 whois_info={"status": "success", "org": "Example Holdings Inc"})
        self.assertIn("whois_match", result[0]["sources"])
        self.assertEqual(result[0]["confidence"], 0.7)  # 0.3 + 0.4

    def test_amass_sources_are_carried_through(self):
        amass = {"example-corp.net": {"sources": {"amass"}, "cert_count": 0,
                                      "amass_sources": {"Crtsh", "HackerTarget"}}}
        result = self._correlate(amass_domains=amass)
        self.assertEqual(result[0]["amass_sources"], ["Crtsh", "HackerTarget"])

    def test_shodan_services_attach_by_apex(self):
        shodan = {"example-corp.net": {"sources": {"shodan"}, "cert_count": 0}}
        exposure = [
            {"ip": "198.51.100.12", "hostnames": ["legacy.example-corp.net"]},
            {"ip": "203.0.113.9", "hostnames": ["unrelated.other.org"]},
        ]
        result = self._correlate(shodan_domains=shodan, shodan_exposure=exposure)
        self.assertEqual(len(result[0]["shodan_services"]), 1)
        self.assertEqual(result[0]["shodan_services"][0]["ip"], "198.51.100.12")

    def test_results_sorted_by_confidence_descending(self):
        raw = {
            "low.net": {"sources": {"crtsh_domain"}, "cert_count": 1},
            "high.net": {"sources": {"crtsh_org", "amass"}, "cert_count": 1},
        }
        result = self._correlate(raw_domains=raw)
        self.assertEqual([d["domain"] for d in result], ["high.net", "low.net"])

    def test_max_domains_caps_the_list(self):
        self.plugin.max_domains = 2
        raw = {f"site{i}.net": {"sources": {"crtsh_org"}, "cert_count": i}
               for i in range(10)}
        self.assertEqual(len(self._correlate(raw_domains=raw)), 2)

    def test_null_max_domains_means_no_cap(self):
        self.plugin.max_domains = None
        raw = {f"site{i}.net": {"sources": {"crtsh_org"}, "cert_count": i}
               for i in range(10)}
        self.assertEqual(len(self._correlate(raw_domains=raw)), 10)


class TestPostProcess(unittest.TestCase):
    """post_process against the committed fixture."""

    def setUp(self):
        self.plugin = _make_plugin()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def _process(self, run_result):
        out = self.plugin.post_process(run_result, self.tmpdir)
        self.assertTrue(out.endswith("org_discovery_processed.json"))
        with open(out) as f:
            return json.load(f)

    def _success_result(self):
        return self.plugin.get_result_dict("success", {"raw_output": str(FIXTURE)})

    def test_processed_contract_fields(self):
        processed = self._process(self._success_result())
        self.assertEqual(processed["plugin-name"], "org_discovery")
        self.assertEqual(processed["plugin-display-name"], "Organization Domain Discovery")
        self.assertTrue(processed["plugin-description"])
        self.assertTrue(processed["timestamp"])

    def test_findings_count_matches_discovered_domains(self):
        processed = self._process(self._success_result())
        self.assertEqual(processed["findings_count"], 4)

    def test_executive_summary_names_every_active_source(self):
        processed = self._process(self._success_result())
        summary = processed["executive_summary"]
        for token in ("Amass", "Shodan", "CT logs", "DNS records"):
            self.assertIn(token, summary)

    def test_executive_summary_counts_high_confidence_and_exposure(self):
        processed = self._process(self._success_result())
        summary = processed["executive_summary"]
        self.assertIn("2 high-confidence match(es)", summary)  # 1.0 and 0.7
        self.assertIn("3 exposed service(s)", summary)

    def test_details_block_is_populated(self):
        processed = self._process(self._success_result())
        details = processed["details"]
        self.assertIn("Example Holdings Inc", details)
        self.assertIn("Apex domain: example.com", details)
        self.assertIn("Domains discovered: 4", details)

    def test_summary_is_a_string(self):
        processed = self._process(self._success_result())
        self.assertIsInstance(processed["summary"], str)
        self.assertTrue(processed["summary"])

    def test_findings_carries_the_raw_payload(self):
        processed = self._process(self._success_result())
        self.assertEqual(processed["findings"]["apex_domain"], "example.com")
        self.assertEqual(len(processed["findings"]["discovered_domains"]), 4)

    def test_issues_is_empty_by_design(self):
        # org_discovery is a recon widget: it maps to no registry issue IDs.
        self.assertEqual(self._process(self._success_result())["issues"], [])

    def test_custom_html_renders_domains_and_exposure(self):
        processed = self._process(self._success_result())
        html = processed["custom_html"]
        self.assertIn("example-corp.net", html)
        self.assertIn("Discovered Domains", html)
        self.assertIn("Shodan: Internet-Exposed Services", html)
        self.assertIn("nginx", html)

    def test_custom_html_pdf_renders_domains(self):
        processed = self._process(self._success_result())
        pdf_html = processed["custom_html_pdf"]
        self.assertIn("example-corp.net", pdf_html)
        self.assertIn("Internet-Exposed Services (Shodan)", pdf_html)

    def test_fail_disposition_still_emits_a_complete_processed_dict(self):
        # kast-web's file-presence state machine needs the marker file, and
        # its scan-details page needs findings_count on every processed dict.
        processed = self._process(self.plugin.get_result_dict("fail", {"error": "no apex"}))
        self.assertEqual(processed["findings_count"], 0)
        self.assertEqual(processed["issues"], [])
        self.assertEqual(processed["findings"], {})
        self.assertIn("did not complete", processed["executive_summary"])

    def test_success_without_raw_output_path_is_treated_as_failure(self):
        processed = self._process(self.plugin.get_result_dict("success", {}))
        self.assertEqual(processed["findings_count"], 0)

    def test_unreadable_raw_file_is_reported_not_raised(self):
        missing = str(Path(self.tmpdir) / "does_not_exist.json")
        processed = self._process(self.plugin.get_result_dict("success", {"raw_output": missing}))
        self.assertEqual(processed["findings_count"], 0)
        self.assertIn("Error", processed["executive_summary"])

    def test_empty_discovery_summary_falls_back_to_generic_source_wording(self):
        payload = {"discovered_domains": [], "shodan_exposure": [], "sources_used": []}
        raw_path = Path(self.tmpdir) / "empty_raw.json"
        raw_path.write_text(json.dumps(payload))
        processed = self._process(
            self.plugin.get_result_dict("success", {"raw_output": str(raw_path)}))
        self.assertEqual(processed["findings_count"], 0)
        self.assertIn("passive sources", processed["executive_summary"])


class TestRun(unittest.TestCase):
    """run() report-only and bad-target paths. No live scan is performed."""

    def setUp(self):
        self.plugin = _make_plugin()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def test_report_only_finds_existing_raw_file(self):
        raw = Path(self.tmpdir) / "org_discovery_raw.json"
        raw.write_text(json.dumps({"discovered_domains": []}))
        result = self.plugin.run("example.com", self.tmpdir, report_only=True)
        self.assertEqual(result["disposition"], "success")
        self.assertEqual(result["results"]["raw_output"], str(raw))

    def test_report_only_without_prior_data_fails(self):
        result = self.plugin.run("example.com", self.tmpdir, report_only=True)
        self.assertEqual(result["disposition"], "fail")
        self.assertIn("No previous data", result["results"]["error"])

    def test_unparseable_target_fails_before_any_network_call(self):
        result = self.plugin.run("localhost", self.tmpdir, report_only=False)
        self.assertEqual(result["disposition"], "fail")
        self.assertIn("Cannot extract apex", result["results"]["error"])

    def test_all_sources_disabled_still_writes_raw_output(self):
        self.plugin.crtsh_enabled = False
        self.plugin.dns_analysis_enabled = False
        self.plugin.amass_enabled = False
        self.plugin.shodan_enabled = False
        result = self.plugin.run("https://www.example.com/path", self.tmpdir)
        self.assertEqual(result["disposition"], "success")
        with open(result["results"]["raw_output"]) as f:
            data = json.load(f)
        self.assertEqual(data["apex_domain"], "example.com")
        self.assertEqual(data["discovered_domains"], [])


class TestDryRunInfo(unittest.TestCase):
    """get_dry_run_info shape. kast doctor --check-syntax consumes this."""

    def test_default_commands(self):
        info = _make_plugin().get_dry_run_info("https://www.example.com", "/tmp/out")
        self.assertEqual(info["plugin"], "Organization Domain Discovery")
        self.assertIsInstance(info["commands"], list)
        joined = " ".join(info["commands"])
        self.assertIn("crt.sh", joined)
        self.assertIn("amass enum -passive -d example.com", joined)
        self.assertNotIn("-org", joined)

    def test_output_files_names_the_raw_json(self):
        info = _make_plugin().get_dry_run_info("example.com", "/tmp/out")
        self.assertEqual(info["output_files"], ["/tmp/out/org_discovery_raw.json"])

    def test_disabled_sources_are_omitted(self):
        plugin = _make_plugin(crtsh_enabled=False, amass_enabled=False,
                              dns_analysis_enabled=False, whois_enabled=False)
        info = plugin.get_dry_run_info("example.com", "/tmp/out")
        self.assertEqual(info["commands"], [])

    def test_notes_report_each_source_state(self):
        info = _make_plugin().get_dry_run_info("example.com", "/tmp/out")
        note = info["notes"][0]
        for token in ("crt.sh=on", "DNS=on", "WHOIS=off", "Amass=on", "Shodan=off"):
            self.assertIn(token, note)
