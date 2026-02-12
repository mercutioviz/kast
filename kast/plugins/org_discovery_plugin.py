"""
File: plugins/org_discovery_plugin.py
Description: Discovers public-facing web domains belonging to the same organization
using Certificate Transparency logs (crt.sh), DNS analysis (SPF/DMARC), and
optional WHOIS correlation.
"""

import json, os, re, time, socket
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
import requests, tldextract
from requests.exceptions import Timeout as RequestsTimeout
from kast.plugins.base import KastPlugin

try:
    import dns.resolver
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False

try:
    import whois
    HAS_WHOIS = True
except ImportError:
    HAS_WHOIS = False


class OrgDiscoveryPlugin(KastPlugin):
    """Discovers public-facing web domains belonging to the same organization."""

    priority = 3

    config_schema = {
        "type": "object",
        "title": "Organization Domain Discovery Configuration",
        "description": "Settings for discovering domains owned by the same organization",
        "properties": {
            "crtsh_enabled": {"type": "boolean", "default": True, "description": "Enable crt.sh CT log search"},
            "dns_analysis_enabled": {"type": "boolean", "default": True, "description": "Enable SPF/DMARC analysis"},
            "whois_enabled": {"type": "boolean", "default": False, "description": "Enable WHOIS correlation"},
            "crtsh_timeout": {"type": "integer", "default": 30, "minimum": 10, "maximum": 120, "description": "crt.sh timeout (seconds)"},
            "crtsh_max_retries": {"type": "integer", "default": 3, "minimum": 0, "maximum": 5, "description": "Max retries on crt.sh 503/timeout"},
            "crtsh_retry_base_delay": {"type": "number", "default": 5.0, "minimum": 1.0, "maximum": 30.0, "description": "Base delay (seconds) for exponential backoff"},
            "crtsh_rate_limit_delay": {"type": "number", "default": 3.0, "minimum": 1.0, "description": "Delay between crt.sh requests"},
            "max_domains": {"type": ["integer", "null"], "default": 50, "minimum": 1, "description": "Max domains to report"},
            "org_name_override": {"type": ["string", "null"], "default": None, "description": "Override org name for CT search"},
            "confidence_threshold": {"type": "number", "default": 0.3, "minimum": 0.0, "maximum": 1.0, "description": "Min confidence to include domain"},
        }
    }

    CONFIDENCE_WEIGHTS = {"crtsh_org": 0.4, "crtsh_domain": 0.3, "spf_include": 0.3, "dmarc_ref": 0.2, "whois_match": 0.4}
    _CA_SKIP = {"let's encrypt", "digicert inc", "sectigo limited", "globalsign", "comodo ca limited",
                "google trust services llc", "amazon", "microsoft corporation", "cloudflare, inc."}

    def __init__(self, cli_args, config_manager=None):
        self.name = "org_discovery"
        self.display_name = "Organization Domain Discovery"
        self.description = "Discovers public-facing web domains belonging to the same organization"
        self.scan_type = "passive"
        self.output_type = "file"
        super().__init__(cli_args, config_manager)
        self.command_executed = {"crtsh_queries": [], "dns_queries": [], "whois_queries": []}
        self._tld_extract = tldextract.TLDExtract(cache_dir=None)
        self._load_plugin_config()

    def _load_plugin_config(self):
        self.crtsh_enabled = self.get_config("crtsh_enabled", True)
        self.dns_analysis_enabled = self.get_config("dns_analysis_enabled", True)
        self.whois_enabled = self.get_config("whois_enabled", False)
        self.crtsh_timeout = self.get_config("crtsh_timeout", 30)
        self.crtsh_max_retries = self.get_config("crtsh_max_retries", 3)
        self.crtsh_retry_base_delay = self.get_config("crtsh_retry_base_delay", 5.0)
        self.crtsh_rate_limit_delay = self.get_config("crtsh_rate_limit_delay", 3.0)
        self.max_domains = self.get_config("max_domains", 50)
        self.org_name_override = self.get_config("org_name_override", None)
        self.confidence_threshold = self.get_config("confidence_threshold", 0.3)

    def is_available(self):
        return True

    # --- helpers ---

    def _apex(self, fqdn):
        e = self._tld_extract(fqdn)
        return f"{e.domain}.{e.suffix}" if e.domain and e.suffix else ""

    def _apexes_from_name(self, name):
        out = set()
        for p in name.replace("\n", " ").split():
            p = p.strip().lstrip("*.")
            if p and "." in p:
                a = self._apex(p)
                if a:
                    out.add(a)
        return out

    def _crtsh_get(self, url):
        self.command_executed["crtsh_queries"].append(url)
        max_retries = self.crtsh_max_retries
        base_delay = self.crtsh_retry_base_delay
        for attempt in range(max_retries + 1):
            try:
                resp = requests.get(url, timeout=self.crtsh_timeout,
                                    headers={"User-Agent": "KAST Security Scanner"})
                if resp.status_code == 503 and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    self.debug(f"crt.sh returned 503, retrying in {delay:.0f}s "
                               f"(attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp.json()
            except RequestsTimeout:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    self.debug(f"crt.sh timed out, retrying in {delay:.0f}s "
                               f"(attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                raise
        raise requests.exceptions.ConnectionError(
            f"crt.sh failed after {max_retries} retries for {url}")

    # --- Module A: crt.sh ---

    def _extract_org_name(self, apex):
        if self.org_name_override:
            return self.org_name_override, "config override"
        try:
            certs = self._crtsh_get(f"https://crt.sh/?q={quote_plus(apex)}&output=json")
        except Exception as e:
            self.debug(f"crt.sh org query failed: {e}")
            return None, str(e)
        counts = {}
        for c in certs:
            m = re.search(r"O=([^,/]+)", c.get("issuer_name", ""))
            if m:
                o = m.group(1).strip()
                if o.lower() not in self._CA_SKIP:
                    counts[o] = counts.get(o, 0) + 1
        if counts:
            best = max(counts, key=counts.get)
            self.debug(f"Detected org: '{best}' ({counts[best]}x)")
            return best, "crt.sh certificate issuer"
        return None, "No org found"

    def _crtsh_search(self, query, tag):
        domains = {}
        try:
            certs = self._crtsh_get(f"https://crt.sh/?q={quote_plus(query)}&output=json")
        except Exception as e:
            self.debug(f"crt.sh query failed: {e}")
            return domains
        for c in certs:
            for f in [c.get("name_value", ""), c.get("common_name", "")]:
                for a in self._apexes_from_name(f):
                    if a not in domains:
                        domains[a] = {"sources": set(), "cert_count": 0}
                    domains[a]["sources"].add(tag)
                    domains[a]["cert_count"] += 1
        return domains

    # --- Module B: DNS ---

    def _analyze_spf(self, apex):
        if not HAS_DNSPYTHON:
            return []
        out = []
        self.command_executed["dns_queries"].append(f"TXT {apex} (SPF)")
        try:
            for rd in dns.resolver.resolve(apex, "TXT"):
                txt = rd.to_text().strip('"')
                if "v=spf1" in txt.lower():
                    for inc in re.findall(r"include:([^\s]+)", txt):
                        a = self._apex(inc)
                        if a:
                            out.append(a)
        except Exception as e:
            self.debug(f"SPF error: {e}")
        return list(set(out))

    def _analyze_dmarc(self, apex):
        if not HAS_DNSPYTHON:
            return []
        out = []
        host = f"_dmarc.{apex}"
        self.command_executed["dns_queries"].append(f"TXT {host} (DMARC)")
        try:
            for rd in dns.resolver.resolve(host, "TXT"):
                txt = rd.to_text().strip('"')
                if "v=dmarc1" in txt.lower():
                    for em in re.findall(r"(?:rua|ruf)=mailto:([^\s;,]+)", txt):
                        if "@" in em:
                            a = self._apex(em.split("@")[1])
                            if a:
                                out.append(a)
        except Exception as e:
            self.debug(f"DMARC error: {e}")
        return list(set(out))

    # --- Module C: WHOIS ---

    def _query_whois(self, apex):
        if not HAS_WHOIS or not self.whois_enabled:
            return {"status": "disabled", "org": None, "email": None}
        self.command_executed["whois_queries"].append(f"WHOIS {apex}")
        try:
            w = whois.whois(apex)
            org = getattr(w, "org", None)
            emails = getattr(w, "emails", None)
            email = emails[0] if isinstance(emails, list) and emails else emails
            return {"status": "success" if org else "privacy_redacted", "org": org, "email": email}
        except Exception as e:
            return {"status": f"error: {e}", "org": None, "email": None}

    # --- Correlation ---

    def _correlate(self, crtsh, spf, dmarc, whois_info, apex):
        all_d = {}
        for d, info in crtsh.items():
            all_d.setdefault(d, {"sources": set(), "cert_count": 0, "notes": []})
            all_d[d]["sources"].update(info["sources"])
            all_d[d]["cert_count"] += info.get("cert_count", 0)
        for d in spf:
            all_d.setdefault(d, {"sources": set(), "cert_count": 0, "notes": []})
            all_d[d]["sources"].add("spf_include")
            all_d[d]["notes"].append(f"SPF include in {apex}")
        for d in dmarc:
            all_d.setdefault(d, {"sources": set(), "cert_count": 0, "notes": []})
            all_d[d]["sources"].add("dmarc_ref")
            all_d[d]["notes"].append(f"DMARC ref in {apex}")
        all_d.pop(apex, None)

        scored = []
        for d, info in all_d.items():
            conf = sum(self.CONFIDENCE_WEIGHTS.get(s, 0.1) for s in info["sources"])
            conf = min(conf + min(info["cert_count"] * 0.01, 0.2), 1.0)
            if conf >= self.confidence_threshold:
                scored.append({"domain": d, "confidence": round(conf, 3),
                               "sources": sorted(info["sources"]),
                               "cert_count": info["cert_count"], "notes": info["notes"]})
        scored.sort(key=lambda x: x["confidence"], reverse=True)
        return scored[:self.max_domains] if self.max_domains else scored

    # --- run ---

    def run(self, target, output_dir, report_only=False):
        output_dir = Path(output_dir)
        raw_file = output_dir / "org_discovery_raw.json"

        if report_only:
            if raw_file.exists():
                return self.get_result_dict("success", str(raw_file))
            return self.get_result_dict("fail", "No raw output for report-only")

        apex = self._apex(target)
        self.debug(f"Org discovery for {target} (apex={apex})")

        if self.dns_analysis_enabled and not HAS_DNSPYTHON:
            self.debug("DNS analysis enabled but dnspython not installed — skipping SPF/DMARC analysis. "
                       "Install with: pip install dnspython")

        crtsh = {}
        org_name = org_source = None
        if self.crtsh_enabled:
            org_name, org_source = self._extract_org_name(apex)
            if org_name:
                crtsh = self._crtsh_search(org_name, "crtsh_org")
                time.sleep(self.crtsh_rate_limit_delay)
            dom = self._crtsh_search(f"%.{apex}", "crtsh_domain")
            for d, i in dom.items():
                if d not in crtsh:
                    crtsh[d] = i
                else:
                    crtsh[d]["sources"].update(i["sources"])
                    crtsh[d]["cert_count"] += i["cert_count"]

        spf = self._analyze_spf(apex) if self.dns_analysis_enabled else []
        dmarc = self._analyze_dmarc(apex) if self.dns_analysis_enabled else []
        whois_info = self._query_whois(apex)
        scored = self._correlate(crtsh, spf, dmarc, whois_info, apex)

        raw = {"target": target, "apex_domain": apex, "org_name": org_name,
               "org_name_source": org_source,
               "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
               "sources_used": {"crtsh": self.crtsh_enabled,
                                "dns": self.dns_analysis_enabled and HAS_DNSPYTHON,
                                "whois": self.whois_enabled and HAS_WHOIS},
               "queries_executed": self.command_executed, "whois_info": whois_info,
               "domains_discovered": scored, "domains_count": len(scored),
               "spf_references": spf, "dmarc_references": dmarc}

        with open(raw_file, "w") as f:
            json.dump(raw, f, indent=2, default=str)
        return self.get_result_dict("success", str(raw_file))

    # --- post_process ---

    def post_process(self, raw_output, output_dir):
        output_dir = Path(output_dir)
        if isinstance(raw_output, str):
            with open(raw_output) as f:
                data = json.load(f)
        elif isinstance(raw_output, dict):
            data = raw_output
        else:
            data = {"domains_discovered": [], "domains_count": 0}

        domains = data.get("domains_discovered", [])
        count = len(domains)
        org = data.get("org_name", "Unknown")
        apex = data.get("apex_domain", "unknown")

        # Confidence buckets
        high = [d for d in domains if d["confidence"] >= 0.7]
        med = [d for d in domains if 0.4 <= d["confidence"] < 0.7]
        low = [d for d in domains if d["confidence"] < 0.4]

        if count == 0:
            exec_summary = (f"No additional domains were discovered for the organization behind {apex}. "
                            "This may indicate a small web footprint or privacy-protected registrations.")
        else:
            exec_summary = (f"Discovered {count} domain(s) potentially belonging to the same organization as {apex}"
                            f" (org: {org}). {len(high)} high-confidence, {len(med)} medium, {len(low)} low. "
                            "Each domain represents an additional attack surface that should be assessed for WAF coverage.")

        summary_lines = [f"Organization: {org}", f"Target apex: {apex}",
                         f"Domains found: {count}", f"  High confidence: {len(high)}",
                         f"  Medium confidence: {len(med)}", f"  Low confidence: {len(low)}"]
        details = "\n".join(summary_lines)

        # Issues
        issues = []
        if count > 0:
            issues.append({
                "id": "ORG-DISC-001",
                "title": "Multiple organizational domains discovered",
                "severity": "informational",
                "description": f"{count} additional domain(s) found via CT logs and DNS analysis",
                "recommendation": "Ensure WAF coverage extends to all organizational web properties"
            })
        if len(high) >= 5:
            issues.append({
                "id": "ORG-DISC-002",
                "title": "Large organizational web footprint",
                "severity": "low",
                "description": f"{len(high)} high-confidence domains suggest a significant attack surface",
                "recommendation": "Consider a comprehensive WAF deployment across all domains"
            })

        # HTML widgets
        custom_html = self._build_html(domains, org, apex, data)
        custom_html_pdf = self._build_html_pdf(domains, org, apex, data)

        processed = {
            "plugin-name": self.name,
            "plugin-display-name": self.display_name,
            "plugin-description": self.description,
            "timestamp": data.get("timestamp", datetime.utcnow().isoformat(timespec="milliseconds")),
            "findings": data,
            "findings_count": count,
            "summary": details,
            "details": details,
            "issues": issues,
            "executive_summary": exec_summary,
            "custom_html": custom_html,
            "custom_html_pdf": custom_html_pdf,
        }

        out_file = output_dir / "org_discovery_processed.json"
        with open(out_file, "w") as f:
            json.dump(processed, f, indent=2, default=str)
        return str(out_file)

    # --- HTML builders ---

    def _conf_badge(self, c):
        if c >= 0.7:
            return f'<span style="background:#28a745;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">High ({c})</span>'
        if c >= 0.4:
            return f'<span style="background:#ffc107;color:#000;padding:2px 8px;border-radius:4px;font-size:0.85em">Med ({c})</span>'
        return f'<span style="background:#6c757d;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">Low ({c})</span>'

    def _build_html(self, domains, org, apex, data):
        src = data.get("sources_used", {})
        srcs = ", ".join(k for k, v in src.items() if v) or "none"
        rows = ""
        for d in domains:
            rows += (f'<tr><td><a href="https://{d["domain"]}" target="_blank">{d["domain"]}</a></td>'
                     f'<td>{self._conf_badge(d["confidence"])}</td>'
                     f'<td>{", ".join(d["sources"])}</td>'
                     f'<td>{d["cert_count"]}</td></tr>\n')
        if not rows:
            rows = '<tr><td colspan="4" style="text-align:center;color:#999">No additional domains discovered</td></tr>'

        return f"""
<div class="org-discovery-widget">
  <h4>Organization Domain Discovery</h4>
  <p><strong>Organization:</strong> {org or 'Unknown'} &nbsp;|&nbsp;
     <strong>Target:</strong> {apex} &nbsp;|&nbsp;
     <strong>Sources:</strong> {srcs} &nbsp;|&nbsp;
     <strong>Domains found:</strong> {len(domains)}</p>
  <table class="table table-sm table-striped">
    <thead><tr><th>Domain</th><th>Confidence</th><th>Sources</th><th>Certs</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""

    def _build_html_pdf(self, domains, org, apex, data):
        rows = ""
        for d in domains[:20]:
            level = "High" if d["confidence"] >= 0.7 else ("Med" if d["confidence"] >= 0.4 else "Low")
            rows += f'<tr><td>{d["domain"]}</td><td>{level} ({d["confidence"]})</td><td>{", ".join(d["sources"])}</td></tr>\n'
        if not rows:
            rows = '<tr><td colspan="3">No additional domains discovered</td></tr>'
        note = f" (showing 20 of {len(domains)})" if len(domains) > 20 else ""
        return f"""
<div>
  <h4>Organization Domain Discovery</h4>
  <p>Organization: {org or 'Unknown'} | Target: {apex} | Domains: {len(domains)}{note}</p>
  <table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;width:100%">
    <thead><tr><th>Domain</th><th>Confidence</th><th>Sources</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""

    # --- dry run ---

    def get_dry_run_info(self, target, output_dir):
        apex = self._apex(target)
        ops = [f"1. Query crt.sh for certificates matching {apex}",
               "2. Extract organization name from certificate data",
               "3. Query crt.sh by organization name for related domains",
               f"4. Analyze SPF/DMARC DNS records for {apex}",
               "5. Correlate and score discovered domains by confidence"]
        if self.whois_enabled:
            ops.insert(4, f"4a. WHOIS lookup for {apex}")
        cmds = [f"curl 'https://crt.sh/?q={apex}&output=json'",
                f"curl 'https://crt.sh/?q=%25.{apex}&output=json'"]
        if HAS_DNSPYTHON:
            cmds.append(f"dig TXT {apex}  # SPF analysis")
            cmds.append(f"dig TXT _dmarc.{apex}  # DMARC analysis")
        return {"commands": cmds, "description": self.description, "operations": ops}
