"""
File: plugins/edge_profile_plugin.py
Description: Fingerprints the CDN / edge layer sitting in front of the target
(response headers, cookies, DNS delegation) and correlates that verdict with
wafw00f's WAF verdict to produce a single edge posture statement.
"""

import json
import os
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests
import tldextract
import urllib3

from kast.core.atomic import write_json_atomic
from kast.plugins.base import KastPlugin
from kast.plugins.wafw00f_plugin import Wafw00fPlugin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import dns.resolver
    import dns.reversename
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False


# (header name, value regex or None when presence alone is conclusive, provider)
EDGE_HEADER_SIGNATURES = [
    ("cf-ray", None, "Cloudflare"),
    ("cf-cache-status", None, "Cloudflare"),
    ("cf-apo-via", None, "Cloudflare"),
    ("server", r"cloudflare", "Cloudflare"),
    ("x-amz-cf-id", None, "Amazon CloudFront"),
    ("x-amz-cf-pop", None, "Amazon CloudFront"),
    ("via", r"cloudfront", "Amazon CloudFront"),
    ("x-akamai-transformed", None, "Akamai"),
    ("x-akamai-request-id", None, "Akamai"),
    ("akamai-grn", None, "Akamai"),
    ("server", r"akamaighost|akamainetstorage", "Akamai"),
    ("x-fastly-request-id", None, "Fastly"),
    ("fastly-debug-digest", None, "Fastly"),
    ("x-timer", None, "Fastly"),
    ("x-azure-ref", None, "Azure Front Door / CDN"),
    ("x-msedge-ref", None, "Azure Front Door / CDN"),
    ("x-iinfo", None, "Imperva (Incapsula)"),
    ("x-cdn", r"incapsula|imperva", "Imperva (Incapsula)"),
    ("x-sucuri-id", None, "Sucuri"),
    ("x-sucuri-cache", None, "Sucuri"),
    ("cdn-pullzone", None, "Bunny CDN"),
    ("cdn-uid", None, "Bunny CDN"),
    ("server", r"bunnycdn", "Bunny CDN"),
    ("x-vercel-id", None, "Vercel"),
    ("x-nf-request-id", None, "Netlify"),
    ("server", r"netlify", "Netlify"),
    ("via", r"1\.1 google", "Google Cloud CDN"),
    ("x-hw", None, "StackPath / Highwinds"),
    ("x-cdn", r"stackpath", "StackPath / Highwinds"),
    ("x-cdn77-cache", None, "CDN77"),
    ("x-cdn", r"cdn77", "CDN77"),
    ("x-cdn", r"cdnetworks", "CDNetworks"),
    ("x-edgeconnect-midmile-rtt", None, "Akamai"),
]

# (cookie name regex, provider) — edge-set cookies are as conclusive as headers.
EDGE_COOKIE_SIGNATURES = [
    (r"^(__cf_bm|__cfduid|cf_clearance)$", "Cloudflare"),
    (r"^(incap_ses_|visid_incap_)", "Imperva (Incapsula)"),
    (r"^(ak_bmsc|bm_sv|_abck)$", "Akamai"),
    (r"^barra_counter_session$", "Barracuda"),
]

EDGE_CNAME_SUFFIXES = {
    "cloudfront.net": "Amazon CloudFront",
    "akamaiedge.net": "Akamai",
    "akamaized.net": "Akamai",
    "edgekey.net": "Akamai",
    "edgesuite.net": "Akamai",
    "akadns.net": "Akamai",
    "akamaitechnologies.com": "Akamai",
    "fastly.net": "Fastly",
    "fastlylb.net": "Fastly",
    "azureedge.net": "Azure Front Door / CDN",
    "azurefd.net": "Azure Front Door / CDN",
    "incapdns.net": "Imperva (Incapsula)",
    "cloudflare.net": "Cloudflare",
    "b-cdn.net": "Bunny CDN",
    "stackpathdns.net": "StackPath / Highwinds",
    "stackpathcdn.com": "StackPath / Highwinds",
    "edgecastcdn.net": "Edgecast",
    "llnwd.net": "Limelight / Edgio",
    "edgio.link": "Limelight / Edgio",
    "cdn77.org": "CDN77",
    "cdngc.net": "CDNetworks",
    "gccdn.net": "CDNetworks",
    "sucuri.net": "Sucuri",
    "vercel-dns.com": "Vercel",
    "netlify.app": "Netlify",
    "barracudanetworks.com": "Barracuda",
    "cudawaas.com": "Barracuda WaaS",
}

# Managed edges are routinely reached through a chain (Traffic Manager -> WaaS
# -> Front Door, Route 53 alias chains), so the CDN suffix is rarely on hop 1.
CNAME_CHAIN_LIMIT = 8

# Authoritative-nameserver delegation. Weaker than a CNAME — hosting DNS at a
# CDN does not prove traffic is proxied through it — so these score "likely".
EDGE_NS_SUFFIXES = {
    "ns.cloudflare.com": "Cloudflare",
    "akam.net": "Akamai",
    "akamaiedge.net": "Akamai",
    "incapdns.net": "Imperva (Incapsula)",
    "sucuridns.com": "Sucuri",
    "impervadns.net": "Imperva (Incapsula)",
}

# Present on caches and reverse proxies generally; attribute nothing on their own.
GENERIC_EDGE_HEADERS = (
    "via",
    "age",
    "x-cache",
    "x-cache-hits",
    "x-served-by",
    "x-proxy-cache",
    "x-varnish",
    "cdn-cache",
    "x-edge-location",
)

# whatweb plugin name -> provider. Corroboration only; never the sole source.
WHATWEB_EDGE_INDICATORS = {
    "Cloudflare": "Cloudflare",
    "CloudFront": "Amazon CloudFront",
    "Fastly": "Fastly",
    "Akamai": "Akamai",
    "AkamaiGHost": "Akamai",
    "Incapsula": "Imperva (Incapsula)",
    "Sucuri": "Sucuri",
}


class EdgeProfilePlugin(KastPlugin):
    """Identifies the CDN / edge provider fronting the target and its WAF posture.

    Answers the question wafw00f cannot: a site behind Cloudflare with the WAF
    feature switched off looks identical to a bare origin in wafw00f's output
    (both report "No WAF Detected"). Knowing the edge is already there changes
    the remediation conversation from "buy a WAF" to "turn one on".
    """

    priority = 20  # after wafw00f (10) and whatweb (15)

    name = "edge_profile"
    display_name = "CDN / Edge Profile"
    description = "Fingerprints the CDN/edge provider in front of the target and correlates it with the WAF verdict."
    website_url = "https://github.com/mercutioviz/kast"
    scan_type = "passive"
    output_type = "analysis"

    config_schema = {
        "type": "object",
        "title": "CDN / Edge Profile Configuration",
        "description": "Settings for CDN and edge-provider fingerprinting",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": True,
                "description": "Enable or disable edge profiling"
            },
            "timeout": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 120,
                "description": "HTTP request timeout (seconds)"
            },
            "dns_enabled": {
                "type": "boolean",
                "default": True,
                "description": "Enable CNAME/NS/PTR lookups as an additional signal source"
            }
        }
    }

    def __init__(self, cli_args, config_manager=None):
        self.dependencies = [
            {"plugin": "wafw00f", "condition": lambda r: True},
            {"plugin": "whatweb", "condition": lambda r: True},
        ]
        super().__init__(cli_args, config_manager)
        self._load_plugin_config()

    def _load_plugin_config(self):
        self.enabled = self.get_config("enabled", True)
        self.timeout = self.get_config("timeout", 10)
        self.dns_enabled = self.get_config("dns_enabled", True)

    def is_available(self):
        return True

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, target, output_dir, report_only):
        ts = datetime.now(UTC).isoformat(timespec="milliseconds")
        output_file = os.path.join(str(output_dir), f"{self.name}.json")

        if report_only:
            if os.path.exists(output_file):
                with open(output_file) as f:
                    return self.get_result_dict("success", json.load(f), ts)
            return self.get_result_dict(
                "fail", "No existing results found for report-only mode.", ts
            )

        if not self.enabled:
            return self.get_result_dict(
                "success",
                self._inconclusive_results(
                    target, "disabled", "Edge profiling was disabled via configuration."
                ),
                ts,
            )

        url = self._normalize_target(target)
        host = urlparse(url).hostname

        signals, generic_headers, reachable = self._probe_headers(url)
        if self.dns_enabled and host:
            signals.extend(self._probe_dns(host))
        signals.extend(self._analyze_whatweb(output_dir))

        signals = self._dedupe(signals)
        waf_classification = self._read_waf_classification(output_dir)
        results = self._build_results(
            target, signals, generic_headers, waf_classification, reachable
        )

        try:
            write_json_atomic(output_file, results)
        except Exception as e:
            self.debug(f"Error writing {output_file}: {e}")

        self.debug(
            f"Edge profile: {results['classification']} "
            f"({len(results['providers'])} provider(s)), WAF: {waf_classification}"
        )
        return self.get_result_dict("success", results, ts)

    def _build_results(self, target, signals, generic_headers, waf_classification, reachable):
        providers = sorted({s["provider"] for s in signals})
        if providers:
            classification = "specific"
        elif generic_headers:
            classification = "generic"
        elif reachable:
            classification = "none"
        else:
            # Never assert "no CDN" off a failed fetch — that is a claim about the
            # prospect's infrastructure we did not actually observe.
            return self._inconclusive_results(
                target,
                "unknown",
                "The target could not be reached, so the edge layer could not be profiled.",
            )

        return {
            "target": target,
            "providers": providers,
            "signals": signals,
            "generic_edge_headers": sorted(generic_headers),
            "classification": classification,
            "waf_classification": waf_classification,
            "edge_posture": self._describe_posture(
                classification, providers, waf_classification
            ),
        }

    @staticmethod
    def _inconclusive_results(target, classification, posture):
        return {
            "target": target,
            "providers": [],
            "signals": [],
            "generic_edge_headers": [],
            "classification": classification,
            "waf_classification": "unknown",
            "edge_posture": posture,
        }

    @staticmethod
    def _normalize_target(target):
        if target.startswith(("http://", "https://")):
            return target
        return f"https://{target}"

    @staticmethod
    def _dedupe(signals):
        seen = set()
        unique = []
        for s in signals:
            key = (s["provider"], s["source"], s["evidence"])
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique

    # ------------------------------------------------------------------
    # Signal source: HTTP response
    # ------------------------------------------------------------------

    def _probe_headers(self, url):
        """Return (signals, generic_header_names, reachable) from one GET against the target."""
        try:
            resp = requests.get(
                url,
                timeout=self.timeout,
                verify=False,
                allow_redirects=True,
                headers={"User-Agent": "KAST-Security-Scanner/1.0"},
            )
        except Exception as e:
            self.debug(f"Edge header probe failed for {url}: {e}")
            return [], [], False

        headers = {k.lower(): v for k, v in resp.headers.items()}
        signals = self._match_headers(headers)
        signals.extend(self._match_cookies(resp.cookies.keys()))
        generic = [h for h in GENERIC_EDGE_HEADERS if h in headers]
        return signals, generic, True

    @staticmethod
    def _match_headers(headers):
        """Match a lowercased header dict against EDGE_HEADER_SIGNATURES."""
        signals = []
        for header, pattern, provider in EDGE_HEADER_SIGNATURES:
            value = headers.get(header)
            if value is None:
                continue
            if pattern and not re.search(pattern, str(value), re.IGNORECASE):
                continue
            evidence = f"{header}: {value}" if value else header
            signals.append({
                "provider": provider,
                "source": "response_header",
                "evidence": evidence,
                "confidence": "confirmed",
            })
        return signals

    @staticmethod
    def _match_cookies(cookie_names):
        signals = []
        for cookie in cookie_names:
            for pattern, provider in EDGE_COOKIE_SIGNATURES:
                if re.search(pattern, cookie, re.IGNORECASE):
                    signals.append({
                        "provider": provider,
                        "source": "cookie",
                        "evidence": cookie,
                        "confidence": "confirmed",
                    })
                    break
        return signals

    # ------------------------------------------------------------------
    # Signal source: DNS
    # ------------------------------------------------------------------

    def _probe_dns(self, host):
        if not HAS_DNSPYTHON:
            self.debug("dnspython unavailable; skipping DNS signals")
            return []

        signals = []
        signals.extend(self._probe_cname(host))
        signals.extend(self._probe_ns(host))
        signals.extend(self._probe_ptr(host))
        return signals

    def _probe_cname(self, host):
        signals = []
        hop = host.rstrip(".").lower()
        visited = {hop}

        for _ in range(CNAME_CHAIN_LIMIT):
            try:
                answers = dns.resolver.resolve(hop, "CNAME")
            except Exception as e:
                self.debug(f"CNAME chain ended at {hop}: {e}")
                break

            cname = str(answers[0].target).rstrip(".").lower()
            if cname in visited:
                break
            visited.add(cname)
            hop = cname

            provider = self._match_suffix(cname, EDGE_CNAME_SUFFIXES)
            if provider:
                signals.append({
                    "provider": provider,
                    "source": "dns_cname",
                    "evidence": cname,
                    "confidence": "confirmed",
                })
        return signals

    def _probe_ns(self, host):
        signals = []
        apex = self._apex(host)
        if not apex:
            return signals
        try:
            answers = dns.resolver.resolve(apex, "NS")
        except Exception as e:
            self.debug(f"NS lookup failed for {apex}: {e}")
            return signals

        for rd in answers:
            ns = str(rd.target).rstrip(".").lower()
            provider = self._match_suffix(ns, EDGE_NS_SUFFIXES)
            if provider:
                signals.append({
                    "provider": provider,
                    "source": "dns_ns",
                    "evidence": ns,
                    "confidence": "likely",
                })
        return signals

    def _probe_ptr(self, host):
        signals = []
        try:
            addresses = [str(rd) for rd in dns.resolver.resolve(host, "A")]
        except Exception as e:
            self.debug(f"A lookup failed for {host}: {e}")
            return signals

        for address in addresses:
            try:
                rev = dns.reversename.from_address(address)
                ptrs = [str(rd).rstrip(".").lower() for rd in dns.resolver.resolve(rev, "PTR")]
            except Exception as e:
                self.debug(f"PTR lookup failed for {address}: {e}")
                continue

            for ptr in ptrs:
                provider = self._match_suffix(ptr, EDGE_CNAME_SUFFIXES)
                if provider:
                    signals.append({
                        "provider": provider,
                        "source": "dns_ptr",
                        "evidence": f"{address} -> {ptr}",
                        "confidence": "likely",
                    })
        return signals

    @staticmethod
    def _apex(fqdn):
        e = tldextract.extract(fqdn)
        return f"{e.domain}.{e.suffix}" if e.domain and e.suffix else ""

    @staticmethod
    def _match_suffix(hostname, suffix_map):
        """Longest-suffix match so akamaiedge.net wins over a shorter overlap."""
        best = None
        for suffix, provider in suffix_map.items():
            if hostname == suffix or hostname.endswith(f".{suffix}"):
                if best is None or len(suffix) > len(best[0]):
                    best = (suffix, provider)
        return best[1] if best else None

    # ------------------------------------------------------------------
    # Signal source: sibling plugin output
    # ------------------------------------------------------------------

    def _analyze_whatweb(self, output_dir):
        path = os.path.join(str(output_dir), "whatweb.json")
        if not os.path.isfile(path):
            return []

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            self.debug(f"Error reading whatweb.json: {e}")
            return []

        entries = data.get("results", []) if isinstance(data, dict) else data
        signals = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for plugin_name in (entry.get("plugins") or {}):
                provider = WHATWEB_EDGE_INDICATORS.get(plugin_name)
                if provider:
                    signals.append({
                        "provider": provider,
                        "source": "whatweb",
                        "evidence": f"whatweb plugin: {plugin_name}",
                        "confidence": "likely",
                    })
        return signals

    def _read_waf_classification(self, output_dir):
        """Reuse wafw00f's own no_waf/generic/specific verdict rather than re-deriving it."""
        path = os.path.join(str(output_dir), "wafw00f_processed.json")
        if not os.path.isfile(path):
            return "unknown"

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            self.debug(f"Error reading wafw00f_processed.json: {e}")
            return "unknown"

        findings = data.get("findings")
        if not isinstance(findings, dict) or findings.get("disposition") != "success":
            return "unknown"
        return Wafw00fPlugin._classify(findings)

    # ------------------------------------------------------------------
    # Posture
    # ------------------------------------------------------------------

    @staticmethod
    def _describe_posture(classification, providers, waf_classification):
        if classification == "none":
            edge = "No CDN or edge layer detected — traffic reaches the origin directly"
        elif classification == "generic":
            edge = "An edge cache or reverse proxy is present, but the provider could not be identified"
        else:
            edge = f"Edge provider identified: {', '.join(providers)}"

        if waf_classification == "no_waf":
            waf = "no WAF was detected"
        elif waf_classification == "generic":
            waf = "a WAF is present but could not be identified"
        elif waf_classification == "specific":
            waf = "a WAF was detected"
        else:
            waf = "WAF status is unknown (wafw00f did not run)"

        return f"{edge}; {waf}."

    # ------------------------------------------------------------------
    # Post-process
    # ------------------------------------------------------------------

    def post_process(self, raw_output, output_dir):
        ts = raw_output.get("timestamp", datetime.now(UTC).isoformat(timespec="milliseconds"))
        results = raw_output.get("results")
        if not isinstance(results, dict):
            results = self._inconclusive_results(
                "unknown", "unknown", "The edge layer could not be profiled."
            )

        target = results.get("target", "unknown")
        providers = results.get("providers", [])
        classification = results.get("classification", "unknown")
        waf_classification = results.get("waf_classification", "unknown")
        posture = results.get("edge_posture", "")

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": self.display_name,
            "plugin-website-url": self.website_url,
            "timestamp": ts,
            "target": target,
            "findings": {
                "name": self.name,
                "timestamp": ts,
                "disposition": raw_output.get("disposition", "success"),
                "results": results,
            },
            "findings_count": len(providers),
            "summary": self._build_summary(classification, providers),
            "details": self._build_details(results),
            "issues": self._extract_issues(classification, waf_classification),
            "executive_summary": self._build_executive_summary(
                classification, providers, waf_classification, posture
            ),
            "custom_html": self._build_html(results),
        }

        out_path = os.path.join(str(output_dir), f"{self.name}_processed.json")
        try:
            write_json_atomic(out_path, processed)
            self.debug(f"Processed JSON written to {out_path}")
        except Exception as e:
            self.debug(f"Error writing processed JSON: {e}")

        return out_path

    @staticmethod
    def _extract_issues(classification, waf_classification):
        if classification == "none":
            return ["no-cdn-detected"]
        if waf_classification == "no_waf":
            return ["cdn-without-waf"]
        return []

    @staticmethod
    def _build_summary(classification, providers):
        if classification == "specific":
            return f"Edge provider(s) detected: {', '.join(providers)}."
        if classification == "generic":
            return "Unidentified edge cache or reverse proxy detected."
        if classification == "none":
            return "No CDN or edge provider detected."
        if classification == "disabled":
            return "Edge profiling disabled."
        return "Edge profile inconclusive."

    @staticmethod
    def _build_details(results):
        lines = [results.get("edge_posture", "")]

        signals = results.get("signals", [])
        if signals:
            lines.append(f"\nSignals ({len(signals)}):")
            for s in signals:
                lines.append(
                    f"  - {s['provider']} [{s['confidence']}] via {s['source']}: {s['evidence']}"
                )
        else:
            lines.append("\nNo provider-attributable signals found.")

        generic = results.get("generic_edge_headers", [])
        if generic:
            lines.append(f"\nGeneric edge/cache headers present: {', '.join(generic)}")

        return "\n".join(lines)

    @staticmethod
    def _build_executive_summary(classification, providers, waf_classification, posture):
        if classification in ("unknown", "disabled"):
            return posture
        if classification == "none":
            return (
                f"{posture} With no edge layer in place, the origin server absorbs all traffic "
                "directly, including volumetric and application-layer attacks, and has no "
                "upstream point at which malicious requests can be filtered."
            )
        if waf_classification == "no_waf":
            named = ", ".join(providers) if providers else "an edge cache or reverse proxy"
            return (
                f"{posture} The application is already fronted by {named}, but no web "
                "application firewall was detected on it. Edge infrastructure is in place; "
                "the application-layer protection it can carry is not switched on."
            )
        return posture

    # ------------------------------------------------------------------
    # Report widget
    # ------------------------------------------------------------------

    def _build_html(self, results):
        posture = results.get("edge_posture", "")
        signals = results.get("signals", [])
        generic = results.get("generic_edge_headers", [])

        parts = [f'<p class="report-paragraph"><strong>{posture}</strong></p>']

        if signals:
            rows = []
            for s in signals:
                conf_class = "info" if s["confidence"] == "confirmed" else "secondary"
                rows.append(
                    f'<tr><td>{s["provider"]}</td>'
                    f'<td><span class="badge badge-{conf_class}">{s["confidence"]}</span></td>'
                    f'<td>{s["source"]}</td>'
                    f'<td style="word-break:break-all;max-width:400px">{s["evidence"]}</td></tr>'
                )
            parts.append(
                '<table class="table table-striped table-sm">'
                '<thead><tr><th>Provider</th><th>Confidence</th><th>Source</th>'
                '<th>Evidence</th></tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table>'
            )
        else:
            parts.append(
                '<p class="report-paragraph">No provider-attributable signals were found.</p>'
            )

        if generic:
            parts.append(
                '<p class="report-paragraph">Generic edge/cache headers present: '
                f'{", ".join(generic)}</p>'
            )

        return f'<div class="edge-profile-results">{"".join(parts)}</div>'

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def get_dry_run_info(self, target, output_dir):
        return {
            "description": self.description,
            "operations": [
                f"HTTP GET {self._normalize_target(target)} and match response headers "
                "and cookies against known CDN/edge signatures",
                "Resolve CNAME, NS, and PTR records to identify edge delegation",
                "Read whatweb.json for corroborating edge technology fingerprints",
                "Read wafw00f_processed.json to correlate the edge verdict with the WAF verdict",
            ],
        }
