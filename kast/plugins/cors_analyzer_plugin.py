"""Cross-Origin Policy Analyzer plugin.

Tests CORS policy, bypass patterns, and JSONP endpoint exposure on the
target and its common API paths. All tests are non-destructive HTTP requests.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests
import urllib3

from kast.core.atomic import write_json_atomic
from kast.plugins.base import KastPlugin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---- module-level constants ------------------------------------------------

_ATTACKER_ORIGIN = "https://evil-attacker.example.com"
_JSONP_PROBE_VALUE = "kast_cors_probe_fn"
_JSONP_PARAMS = ["callback", "jsonp", "cb", "_callback", "jsonCallback", "jsoncallback"]
_DEFAULT_PROBE_PATHS = ["/", "/api/", "/api/v1/", "/graphql", "/rest/", "/v1/"]

_ISSUE_SEVERITY_ORDER = [
    "cors-credentials-with-reflected-origin",
    "cors-bypass-subdomain",
    "cors-bypass-suffix",
    "cors-arbitrary-origin-reflected",
    "cors-null-origin-allowed",
    "cors-bypass-http-downgrade",
    "cors-credentials-with-wildcard",
    "jsonp-endpoint-detected",
    "cors-wildcard-origin",
]

_ISSUE_LABELS = {
    "cors-credentials-with-reflected-origin": "Arbitrary Origin Reflected with Credentials",
    "cors-arbitrary-origin-reflected": "Arbitrary Origin Reflected",
    "cors-bypass-subdomain": "Subdomain CORS Bypass",
    "cors-bypass-suffix": "Suffix-Match CORS Bypass",
    "cors-null-origin-allowed": "Null Origin Allowed",
    "cors-bypass-http-downgrade": "HTTP Origin Accepted for HTTPS Site",
    "cors-credentials-with-wildcard": "Wildcard ACAO with Credentials (misconfigured)",
    "cors-wildcard-origin": "Wildcard ACAO",
    "jsonp-endpoint-detected": "JSONP Endpoint Detected",
}

_ISSUE_SEVERITY = {
    "cors-credentials-with-reflected-origin": "Critical",
    "cors-arbitrary-origin-reflected": "High",
    "cors-bypass-subdomain": "High",
    "cors-bypass-suffix": "High",
    "cors-null-origin-allowed": "Medium",
    "cors-bypass-http-downgrade": "Medium",
    "cors-credentials-with-wildcard": "Medium",
    "cors-wildcard-origin": "Low",
    "jsonp-endpoint-detected": "Medium",
}

_SEVERITY_COLORS = {
    "Critical": "#721c24",
    "High":     "#856404",
    "Medium":   "#0c5460",
    "Low":      "#383d41",
}


class CorsAnalyzerPlugin(KastPlugin):
    priority = 30

    name = "cors_analyzer"
    display_name = "Cross-Origin Policy Analyzer"
    description = (
        "Tests CORS policy, bypass patterns, and JSONP endpoint exposure. "
        "Identifies whether unauthorized origins can read application responses."
    )
    website_url = "https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS"
    scan_type = "passive"
    output_type = "stdout"

    config_schema = {
        "type": "object",
        "title": "Cross-Origin Policy Analyzer Configuration",
        "description": "Settings for CORS policy and JSONP endpoint testing",
        "properties": {
            "timeout": {
                "type": "integer",
                "default": 10,
                "minimum": 3,
                "maximum": 60,
                "description": "Request timeout per probe in seconds",
            },
            "probe_paths": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["/", "/api/", "/api/v1/", "/graphql", "/rest/", "/v1/"],
                "description": "URL paths to probe for CORS policy and JSONP",
            },
        },
    }

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self._load_plugin_config()

    def _load_plugin_config(self) -> None:
        self.timeout = self.get_config("timeout", 10)
        self.probe_paths = self.get_config("probe_paths", _DEFAULT_PROBE_PATHS)
        self.debug(
            f"CORSAnalyzer config: timeout={self.timeout}s, paths={self.probe_paths}"
        )

    # ---- KastPlugin contract -----------------------------------------------

    def is_available(self) -> bool:
        return True  # pure Python / requests, no external tool

    def run(self, target: str, output_dir, report_only: bool):
        timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        output_file = os.path.join(str(output_dir), "cors_analyzer.json")

        if report_only:
            if os.path.exists(output_file):
                with open(output_file) as f:
                    return self.get_result_dict("success", json.load(f), timestamp)
            return self.get_result_dict(
                "fail", "No existing results found for report-only mode.", timestamp
            )

        base_url = self._normalize_target(target)
        domain = urlparse(base_url).netloc
        is_https = base_url.startswith("https://")

        session = requests.Session()
        session.verify = False
        session.headers["User-Agent"] = "KAST-Security-Scanner/1.0"

        cors_findings: list[dict] = []
        bypass_findings: list[dict] = []
        jsonp_findings: list[dict] = []

        for path in self.probe_paths:
            url = base_url.rstrip("/") + path
            self._probe_cors(session, url, cors_findings)
            self._probe_jsonp(session, url, jsonp_findings)

        self._probe_bypass(session, base_url, domain, is_https, bypass_findings)

        results = {
            "target": base_url,
            "domain": domain,
            "paths_tested": self.probe_paths,
            "cors_findings": cors_findings,
            "bypass_findings": bypass_findings,
            "jsonp_findings": jsonp_findings,
        }

        write_json_atomic(output_file, results)
        self.debug(
            f"CORS analysis complete: {len(cors_findings)} CORS, "
            f"{len(bypass_findings)} bypass, {len(jsonp_findings)} JSONP findings"
        )
        return self.get_result_dict("success", results, timestamp)

    def post_process(self, raw_output, output_dir) -> str:
        ts = datetime.now(UTC).isoformat(timespec="milliseconds")

        if isinstance(raw_output, dict) and raw_output.get("disposition") == "fail":
            processed = {
                "plugin-name": self.name,
                "plugin-description": self.description,
                "plugin-display-name": self.display_name,
                "plugin-website-url": self.website_url,
                "timestamp": ts,
                "findings": raw_output,
                "findings_count": 0,
                "summary": f"CORS analysis could not complete: {raw_output.get('results')}",
                "details": "",
                "issues": [],
                "executive_summary": "",
            }
            out_path = os.path.join(str(output_dir), f"{self.name}_processed.json")
            write_json_atomic(out_path, processed)
            return out_path

        if isinstance(raw_output, dict) and "results" in raw_output and "disposition" in raw_output:
            results = raw_output["results"]
        else:
            results = raw_output

        if not isinstance(results, dict):
            results = {}

        cors_findings = results.get("cors_findings", [])
        bypass_findings = results.get("bypass_findings", [])
        jsonp_findings = results.get("jsonp_findings", [])
        findings_count = len(cors_findings) + len(bypass_findings) + len(jsonp_findings)

        seen_types: set[str] = set()
        for f in cors_findings + bypass_findings:
            seen_types.add(f["issue_type"])
        if jsonp_findings:
            seen_types.add("jsonp-endpoint-detected")

        issues = [i for i in _ISSUE_SEVERITY_ORDER if i in seen_types]
        issues += [i for i in seen_types if i not in _ISSUE_SEVERITY_ORDER]

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": self.display_name,
            "plugin-website-url": self.website_url,
            "timestamp": ts,
            "findings": results,
            "findings_count": findings_count,
            "summary": self._generate_summary(results, issues),
            "details": self._generate_details(results),
            "issues": issues,
            "executive_summary": self._generate_executive_summary(results, issues),
            "custom_html": self._generate_custom_html(results),
        }

        out_path = os.path.join(str(output_dir), f"{self.name}_processed.json")
        write_json_atomic(out_path, processed)
        return out_path

    # ---- probing methods ---------------------------------------------------

    def _normalize_target(self, target: str) -> str:
        if target.startswith(("http://", "https://")):
            return target
        return f"https://{target}"

    def _probe_cors(self, session: requests.Session, url: str, findings: list) -> None:
        """Test URL with attacker origin and null origin."""
        # attacker origin
        try:
            resp = session.get(
                url,
                headers={"Origin": _ATTACKER_ORIGIN},
                timeout=self.timeout,
                allow_redirects=True,
            )
        except Exception as e:
            self.debug(f"CORS probe failed for {url}: {e}")
            return

        acao = resp.headers.get("Access-Control-Allow-Origin", "")
        acac = resp.headers.get("Access-Control-Allow-Credentials", "").lower() == "true"

        if acao == "*":
            findings.append({
                "url": url,
                "issue_type": "cors-credentials-with-wildcard" if acac else "cors-wildcard-origin",
                "origin_sent": _ATTACKER_ORIGIN,
                "acao_received": acao,
                "credentials": acac,
            })
        elif acao == _ATTACKER_ORIGIN:
            findings.append({
                "url": url,
                "issue_type": "cors-credentials-with-reflected-origin" if acac else "cors-arbitrary-origin-reflected",
                "origin_sent": _ATTACKER_ORIGIN,
                "acao_received": acao,
                "credentials": acac,
            })

        # null origin
        try:
            resp_null = session.get(
                url,
                headers={"Origin": "null"},
                timeout=self.timeout,
                allow_redirects=True,
            )
            if resp_null.headers.get("Access-Control-Allow-Origin", "") == "null":
                findings.append({
                    "url": url,
                    "issue_type": "cors-null-origin-allowed",
                    "origin_sent": "null",
                    "acao_received": "null",
                    "credentials": resp_null.headers.get(
                        "Access-Control-Allow-Credentials", ""
                    ).lower() == "true",
                })
        except Exception:
            pass

    def _probe_bypass(
        self,
        session: requests.Session,
        url: str,
        domain: str,
        is_https: bool,
        findings: list,
    ) -> None:
        """Test common CORS validation bypass patterns against the root URL."""
        tests = [
            (f"https://evil.{domain}", "cors-bypass-subdomain"),
            (f"https://{domain}.evil.com", "cors-bypass-suffix"),
        ]
        if is_https:
            tests.append((f"http://{domain}", "cors-bypass-http-downgrade"))

        for origin, issue_type in tests:
            try:
                resp = session.get(
                    url,
                    headers={"Origin": origin},
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                acao = resp.headers.get("Access-Control-Allow-Origin", "")
                if acao == origin:
                    findings.append({
                        "url": url,
                        "issue_type": issue_type,
                        "origin_sent": origin,
                        "acao_received": acao,
                        "credentials": resp.headers.get(
                            "Access-Control-Allow-Credentials", ""
                        ).lower() == "true",
                    })
            except Exception as e:
                self.debug(f"Bypass probe failed ({origin}): {e}")

    def _probe_jsonp(
        self, session: requests.Session, url: str, findings: list
    ) -> None:
        """Probe URL for JSONP endpoints using common callback parameter names."""
        sep = "&" if "?" in url else "?"
        for param in _JSONP_PARAMS:
            probe_url = f"{url}{sep}{param}={_JSONP_PROBE_VALUE}"
            try:
                resp = session.get(probe_url, timeout=self.timeout, allow_redirects=True)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("Content-Type", "").lower()
                if "text/html" in content_type:
                    continue  # error pages that echo params are false positives
                body = resp.text[:300]
                if f"{_JSONP_PROBE_VALUE}(" in body:
                    findings.append({
                        "url": probe_url,
                        "parameter": param,
                        "content_type": content_type,
                        "response_snippet": body[:200],
                    })
                    return  # one confirmed JSONP endpoint per path is enough
            except Exception:
                pass

    # ---- report generation -------------------------------------------------

    def _generate_summary(self, results: dict, issues: list) -> str:
        n = (
            len(results.get("cors_findings", []))
            + len(results.get("bypass_findings", []))
            + len(results.get("jsonp_findings", []))
        )
        paths = len(results.get("paths_tested", []))
        if n == 0:
            return f"No cross-origin policy issues found across {paths} path(s) tested."
        worst = _ISSUE_LABELS.get(issues[0], issues[0]) if issues else "unknown"
        return (
            f"{n} cross-origin policy finding(s) across {paths} path(s) — "
            f"highest severity: {worst}"
        )

    def _generate_executive_summary(self, results: dict, issues: list) -> str:
        if not issues:
            return (
                "No cross-origin policy misconfigurations detected. "
                "The server does not appear to return permissive CORS headers "
                "and no JSONP endpoints were found."
            )
        worst = issues[0]
        label = _ISSUE_LABELS.get(worst, worst)
        severity = _ISSUE_SEVERITY.get(worst, "Medium")

        if worst == "cors-credentials-with-reflected-origin":
            return (
                f"{severity}: the application reflects arbitrary Origin headers with "
                "credentials enabled. Any website can make authenticated requests to "
                "your API and read the responses, potentially exposing user data to a "
                "malicious third party. A WAF can enforce a strict origin allowlist immediately."
            )
        if worst in ("cors-bypass-subdomain", "cors-bypass-suffix"):
            return (
                f"{severity}: {label} detected. The CORS origin validation uses pattern "
                "matching that an attacker can bypass by registering a domain that satisfies "
                "the check. Any website under attacker control that matches the pattern can "
                "read application responses. A WAF can enforce exact-match CORS origin validation."
            )
        if worst == "cors-arbitrary-origin-reflected":
            return (
                f"{severity}: the server reflects any Origin header, allowing any website "
                "to read application responses cross-origin. "
                "A WAF can enforce a strict CORS origin allowlist at the edge."
            )
        if worst == "jsonp-endpoint-detected":
            return (
                "JSONP endpoint detected. JSONP bypasses CORS entirely — any website can "
                "include the endpoint as a script tag and read the JSON response. "
                "Replace JSONP with standard JSON endpoints that use CORS headers."
            )
        return (
            f"Cross-origin policy issue detected ({label}, {severity}). "
            "Review CORS configuration to ensure only authorized origins can access "
            "application resources. A WAF can enforce a strict CORS allowlist at the edge."
        )

    def _generate_details(self, results: dict) -> str:
        lines = [
            f"Target: {results.get('target', 'unknown')}",
            f"Paths tested: {', '.join(results.get('paths_tested', []))}",
            "",
        ]

        for key, label in (
            ("cors_findings", "CORS Policy Findings"),
            ("bypass_findings", "CORS Bypass Findings"),
        ):
            items = results.get(key, [])
            if items:
                lines.append(f"{label}:")
                for f in items:
                    cred = " [credentials: true]" if f.get("credentials") else ""
                    lines.append(
                        f"  {f['issue_type']} — {f['url']}\n"
                        f"    Origin sent:  {f['origin_sent']}\n"
                        f"    ACAO received: {f['acao_received']}{cred}"
                    )
                lines.append("")

        jsonp = results.get("jsonp_findings", [])
        if jsonp:
            lines.append("JSONP Findings:")
            for f in jsonp:
                lines.append(
                    f"  {f['url']}\n"
                    f"    Parameter: {f['parameter']}  Content-Type: {f.get('content_type', 'N/A')}"
                )

        return "\n".join(lines)

    def _generate_custom_html(self, results: dict) -> str:
        cors = results.get("cors_findings", [])
        bypass = results.get("bypass_findings", [])
        jsonp = results.get("jsonp_findings", [])
        all_policy = cors + bypass
        paths_str = ", ".join(f"<code>{p}</code>" for p in results.get("paths_tested", []))

        parts = [
            '<div class="cors-analyzer-widget">',
            f"<p>Paths tested: {paths_str}</p>",
        ]

        if not all_policy and not jsonp:
            parts.append(
                '<p style="background:#d4edda;color:#155724;padding:8px 12px;'
                'border-radius:4px;border:1px solid #c3e6cb;">'
                "No cross-origin policy issues detected.</p>"
            )
        else:
            if all_policy:
                parts += [
                    "<h5>CORS Policy Findings</h5>",
                    '<table class="table table-sm table-striped">',
                    "<thead><tr>"
                    "<th>URL</th><th>Issue</th><th>Origin Sent</th>"
                    "<th>ACAO Received</th><th>Credentials</th><th>Severity</th>"
                    "</tr></thead><tbody>",
                ]
                for f in all_policy:
                    sev = _ISSUE_SEVERITY.get(f["issue_type"], "Medium")
                    color = _SEVERITY_COLORS.get(sev, "#383d41")
                    label = _ISSUE_LABELS.get(f["issue_type"], f["issue_type"])
                    cred = "Yes" if f.get("credentials") else "No"
                    parts.append(
                        f"<tr>"
                        f'<td style="word-break:break-all;max-width:200px">{f["url"]}</td>'
                        f"<td>{label}</td>"
                        f'<td style="word-break:break-all">{f["origin_sent"]}</td>'
                        f'<td style="word-break:break-all">{f["acao_received"]}</td>'
                        f"<td>{cred}</td>"
                        f'<td><span style="color:{color};font-weight:bold">{sev}</span></td>'
                        f"</tr>"
                    )
                parts.append("</tbody></table>")

            if jsonp:
                parts += [
                    "<h5>JSONP Endpoints</h5>",
                    '<table class="table table-sm table-striped">',
                    "<thead><tr><th>URL</th><th>Parameter</th><th>Content-Type</th></tr></thead><tbody>",
                ]
                for f in jsonp:
                    parts.append(
                        f"<tr>"
                        f'<td style="word-break:break-all">{f["url"]}</td>'
                        f"<td>{f['parameter']}</td>"
                        f"<td>{f.get('content_type', 'N/A')}</td>"
                        f"</tr>"
                    )
                parts.append("</tbody></table>")

        parts.append("</div>")
        return "\n".join(parts)

    def get_dry_run_info(self, target: str, output_dir) -> dict:
        base_url = self._normalize_target(target)
        domain = urlparse(base_url).netloc
        return {
            "commands": [],
            "description": self.description,
            "operations": [
                f"Test CORS policy on {len(self.probe_paths)} path(s) at {base_url}",
                f"Test CORS bypass patterns (subdomain: evil.{domain}, "
                f"suffix: {domain}.evil.com, HTTP downgrade)",
                "Probe each path for JSONP endpoints using common callback parameter names",
            ],
        }
