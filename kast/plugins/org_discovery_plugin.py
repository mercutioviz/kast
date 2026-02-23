"""
File: plugins/org_discovery_plugin.py
Description: Discovers public-facing web domains belonging to the same organization
using Certificate Transparency logs (crt.sh), DNS analysis (SPF/DMARC),
optional WHOIS correlation, OWASP Amass passive enumeration, and Shodan
internet exposure search.
"""

import json, os, re, shutil, subprocess, time, socket
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

try:
    import shodan as shodan_lib
    HAS_SHODAN = True
except ImportError:
    HAS_SHODAN = False


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
            "crtsh_timeout": {"type": "integer", "default": 30, "minimum": 10, "maximum": 300, "description": "crt.sh timeout (seconds)"},
            "crtsh_max_retries": {"type": "integer", "default": 3, "minimum": 0, "maximum": 5, "description": "Max retries on crt.sh 503/timeout"},
            "crtsh_retry_base_delay": {"type": "number", "default": 5.0, "minimum": 1.0, "maximum": 30.0, "description": "Base delay (seconds) for exponential backoff"},
            "crtsh_rate_limit_delay": {"type": "number", "default": 3.0, "minimum": 1.0, "description": "Delay between crt.sh requests"},
            "max_domains": {"type": ["integer", "null"], "default": 50, "minimum": 1, "description": "Max domains to report"},
            "org_name_override": {"type": ["string", "null"], "default": None, "description": "Override org name for CT search"},
            "confidence_threshold": {"type": "number", "default": 0.3, "minimum": 0.0, "maximum": 1.0, "description": "Min confidence to include domain"},
            "amass_enabled": {"type": "boolean", "default": True, "description": "Enable OWASP Amass passive enumeration"},
            "amass_timeout": {"type": "integer", "default": 300, "minimum": 60, "maximum": 1800, "description": "Amass timeout in seconds"},
            "amass_extra_args": {"type": ["string", "null"], "default": None, "description": "Additional amass CLI arguments"},
            "shodan_enabled": {"type": "boolean", "default": False, "description": "Enable Shodan internet exposure search (requires API key)"},
            "shodan_api_key": {"type": ["string", "null"], "default": None, "description": "Shodan API key (or set KAST_SHODAN_API_KEY env var)"},
            "shodan_max_results": {"type": "integer", "default": 100, "minimum": 1, "maximum": 1000, "description": "Max Shodan results to process"},
            "shodan_query_override": {"type": ["string", "null"], "default": None, "description": "Custom Shodan query (overrides auto-generated)"},
        }
    }

    CONFIDENCE_WEIGHTS = {
        "crtsh_org": 0.4, "crtsh_domain": 0.3,
        "spf_include": 0.3, "dmarc_ref": 0.2,
        "whois_match": 0.4,
        "amass": 0.5,
        "shodan": 0.45,
    }
    _CA_SKIP = {"let's encrypt", "digicert inc", "sectigo limited", "globalsign", "comodo ca limited",
                "google trust services llc", "amazon", "microsoft corporation", "cloudflare, inc."}

    def __init__(self, cli_args, config_manager=None):
        self.name = "org_discovery"
        self.display_name = "Organization Domain Discovery"
        self.description = "Discovers public-facing web domains belonging to the same organization"
        self.scan_type = "passive"
        self.output_type = "file"
        super().__init__(cli_args, config_manager)
        self.command_executed = {
            "crtsh_queries": [], "dns_queries": [], "whois_queries": [],
            "amass_commands": [], "shodan_queries": [],
        }
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
        self.amass_enabled = self.get_config("amass_enabled", True)
        self.amass_timeout = self.get_config("amass_timeout", 300)
        self.amass_extra_args = self.get_config("amass_extra_args", None)
        self.shodan_enabled = self.get_config("shodan_enabled", False)
        self.shodan_max_results = self.get_config("shodan_max_results", 100)
        self.shodan_query_override = self.get_config("shodan_query_override", None)
        self.shodan_api_key = self.get_config("shodan_api_key", None)
        if not self.shodan_api_key:
            self.shodan_api_key = os.environ.get("KAST_SHODAN_API_KEY")

    def is_available(self):
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Module A: crt.sh
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Module B: DNS
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Module C: WHOIS
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Module D: OWASP Amass
    # ------------------------------------------------------------------

    def _amass_available(self):
        """Check if the amass binary is on PATH."""
        return shutil.which("amass") is not None

    def _run_amass(self, apex, org_name, output_dir):
        """Run amass enum -passive and return discovered domains dict."""
        domains = {}
        if not self.amass_enabled:
            self.debug("Amass disabled in config")
            return domains
        if not self._amass_available():
            self.debug("Amass not found on PATH -- skipping. "
                       "Install: go install -v github.com/owasp-amass/amass/v4/...@master")
            return domains

        json_file = Path(output_dir) / "amass_output.json"
        timeout_min = max(1, self.amass_timeout // 60)

        cmd = [
            "amass", "enum", "-passive",
            "-d", apex,
            "-json", str(json_file),
            "-timeout", str(timeout_min),
        ]
        if org_name:
            cmd.extend(["-org", org_name])
        if self.amass_extra_args:
            cmd.extend(self.amass_extra_args.split())

        cmd_str = " ".join(cmd)
        self.command_executed["amass_commands"].append(cmd_str)
        self.debug(f"Running: {cmd_str}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.amass_timeout + 30,
                cwd=str(output_dir),
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()[:500] if result.stderr else "(no stderr)"
                self.debug(f"Amass exited with code {result.returncode}: {stderr}")
        except subprocess.TimeoutExpired:
            self.debug(f"Amass process timed out after {self.amass_timeout + 30}s")
        except FileNotFoundError:
            self.debug("Amass binary not found")
            return domains
        except Exception as e:
            self.debug(f"Amass execution error: {e}")
            return domains

        if not json_file.exists():
            self.debug("Amass produced no JSON output")
            return domains

        try:
            with open(json_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    name = entry.get("name", "")
                    if not name:
                        continue
                    a = self._apex(name)
                    if not a:
                        continue
                    source_list = entry.get("sources", [])
                    if isinstance(source_list, str):
                        source_list = [source_list]
                    if a not in domains:
                        domains[a] = {"sources": {"amass"}, "cert_count": 0,
                                      "amass_sources": set(), "notes": []}
                    else:
                        domains[a]["sources"].add("amass")
                    for s in source_list:
                        if s:
                            domains[a]["amass_sources"].add(s)
        except Exception as e:
            self.debug(f"Error parsing amass output: {e}")

        self.debug(f"Amass discovered {len(domains)} unique apex domain(s)")
        return domains

    # ------------------------------------------------------------------
    # Module E: Shodan
    # ------------------------------------------------------------------

    def _shodan_available(self):
        """Check if Shodan integration can run."""
        if not HAS_SHODAN:
            return False, "shodan package not installed (pip install shodan)"
        if not self.shodan_api_key:
            return False, ("No Shodan API key (set org_discovery.shodan_api_key "
                           "in config or KAST_SHODAN_API_KEY env var)")
        return True, "ok"

    def _search_shodan(self, apex, org_name):
        """Query Shodan for internet-exposed assets related to the target.

        Returns:
            tuple: (domains_dict, exposure_data)
        """
        domains = {}
        exposure = []

        if not self.shodan_enabled:
            self.debug("Shodan disabled in config")
            return domains, exposure

        available, reason = self._shodan_available()
        if not available:
            self.debug(f"Shodan unavailable: {reason}")
            return domains, exposure

        api = shodan_lib.Shodan(self.shodan_api_key)

        try:
            api.info()
        except shodan_lib.APIError as e:
            self.debug(f"Shodan API key validation failed: {e}")
            return domains, exposure

        queries = []
        if self.shodan_query_override:
            queries.append(("custom", self.shodan_query_override))
        else:
            queries.append(("hostname", f"hostname:{apex}"))
            if org_name:
                queries.append(("org", f'org:"{org_name}"'))

        processed = 0
        for label, query in queries:
            self.command_executed["shodan_queries"].append(f"Shodan search: {query}")
            self.debug(f"Shodan query ({label}): {query}")
            try:
                page = 1
                while processed < self.shodan_max_results:
                    results = api.search(query, page=page)
                    matches = results.get("matches", [])
                    if not matches:
                        break
                    for match in matches:
                        if processed >= self.shodan_max_results:
                            break
                        processed += 1
                        hostnames = match.get("hostnames", [])
                        ip = match.get("ip_str", "")
                        port = match.get("port", 0)
                        transport = match.get("transport", "tcp")
                        product = match.get("product", "")
                        version = match.get("version", "")
                        org_val = match.get("org", "")
                        ssl_cn = ""
                        ssl_info = match.get("ssl", {})
                        if ssl_info and ssl_info.get("cert", {}).get("subject", {}).get("CN"):
                            ssl_cn = ssl_info["cert"]["subject"]["CN"]
                        all_names = set(hostnames)
                        if ssl_cn:
                            all_names.add(ssl_cn)
                        for h in all_names:
                            a = self._apex(h)
                            if a:
                                if a not in domains:
                                    domains[a] = {"sources": {"shodan"}, "cert_count": 0,
                                                  "amass_sources": set(), "notes": []}
                                else:
                                    domains[a]["sources"].add("shodan")
                        svc = f"{port}/{transport}"
                        if product:
                            svc += f" ({product}"
                            if version:
                                svc += f" {version}"
                            svc += ")"
                        exposure.append({
                            "ip": ip, "port": port, "transport": transport,
                            "product": product, "version": version,
                            "hostnames": list(hostnames), "org": org_val,
                            "service": svc,
                        })
                    page += 1
                    time.sleep(1)  # Shodan rate limit
            except shodan_lib.APIError as e:
                self.debug(f"Shodan API error for query '{query}': {e}")
            except Exception as e:
                self.debug(f"Shodan error: {e}")

        self.debug(f"Shodan found {len(domains)} domain(s), {len(exposure)} exposed service(s)")
        return domains, exposure

    # ------------------------------------------------------------------
    # Correlation
    # ------------------------------------------------------------------

    def _correlate(self, target_apex, raw_domains, spf_domains, dmarc_domains, whois_info,
                   amass_domains, shodan_domains, shodan_exposure):
        merged = {}
        for d, info in raw_domains.items():
            merged.setdefault(d, {"sources": set(), "cert_count": 0,
                                  "amass_sources": set(), "notes": []})
            merged[d]["sources"].update(info.get("sources", set()))
            merged[d]["cert_count"] += info.get("cert_count", 0)
        for d in spf_domains:
            merged.setdefault(d, {"sources": set(), "cert_count": 0,
                                  "amass_sources": set(), "notes": []})
            merged[d]["sources"].add("spf_include")
        for d in dmarc_domains:
            merged.setdefault(d, {"sources": set(), "cert_count": 0,
                                  "amass_sources": set(), "notes": []})
            merged[d]["sources"].add("dmarc_ref")
        if whois_info.get("org"):
            for d in list(merged):
                merged[d]["sources"].add("whois_match")
        for d, info in amass_domains.items():
            merged.setdefault(d, {"sources": set(), "cert_count": 0,
                                  "amass_sources": set(), "notes": []})
            merged[d]["sources"].update(info.get("sources", set()))
            merged[d]["amass_sources"].update(info.get("amass_sources", set()))
        for d, info in shodan_domains.items():
            merged.setdefault(d, {"sources": set(), "cert_count": 0,
                                  "amass_sources": set(), "notes": []})
            merged[d]["sources"].update(info.get("sources", set()))

        result = []
        for d, info in merged.items():
            if d == target_apex:
                continue
            score = min(1.0, sum(self.CONFIDENCE_WEIGHTS.get(s, 0.1) for s in info["sources"]))
            if score < self.confidence_threshold:
                continue
            svcs = [e for e in shodan_exposure if self._apex(h) == d
                    for h in e.get("hostnames", [])]
            result.append({
                "domain": d,
                "confidence": round(score, 2),
                "sources": sorted(info["sources"]),
                "cert_count": info["cert_count"],
                "amass_sources": sorted(info.get("amass_sources", set())),
                "shodan_services": svcs[:10],
                "notes": info.get("notes", []),
            })
        result.sort(key=lambda x: x["confidence"], reverse=True)
        if self.max_domains:
            result = result[:self.max_domains]
        return result

    # ------------------------------------------------------------------
    # run / post_process / dry_run
    # ------------------------------------------------------------------

    def run(self, target, output_dir, report_only=False):
        start_time = datetime.utcnow().isoformat(timespec="milliseconds")

        if report_only:
            json_file = Path(output_dir) / "org_discovery_raw.json"
            if json_file.exists():
                return self.get_result_dict("success", {
                    "raw_output": str(json_file),
                    "start_time": start_time,
                    "end_time": datetime.utcnow().isoformat(timespec="milliseconds"),
                })
            else:
                return self.get_result_dict("fail", {
                    "error": "No previous data",
                    "start_time": start_time,
                    "end_time": datetime.utcnow().isoformat(timespec="milliseconds"),
                })

        apex = self._apex(target.replace("https://", "").replace("http://", "").split("/")[0])
        if not apex:
            return self.get_result_dict("fail", {
                "error": f"Cannot extract apex domain from '{target}'",
                "start_time": start_time,
                "end_time": datetime.utcnow().isoformat(timespec="milliseconds"),
            })
        self.debug(f"Target apex: {apex}")

        org_name, org_source = None, None
        raw_domains = {}
        if self.crtsh_enabled:
            org_name, org_source = self._extract_org_name(apex)
            if org_name:
                time.sleep(self.crtsh_rate_limit_delay)
                raw_domains.update(self._crtsh_search(f"O={org_name}", "crtsh_org"))
                time.sleep(self.crtsh_rate_limit_delay)
            raw_domains.update(self._crtsh_search(apex, "crtsh_domain"))

        spf_domains, dmarc_domains = [], []
        if self.dns_analysis_enabled:
            spf_domains = self._analyze_spf(apex)
            dmarc_domains = self._analyze_dmarc(apex)

        whois_info = self._query_whois(apex)

        amass_domains = self._run_amass(apex, org_name, output_dir)

        shodan_domains, shodan_exposure = self._search_shodan(apex, org_name)

        correlated = self._correlate(apex, raw_domains, spf_domains, dmarc_domains,
                                     whois_info, amass_domains, shodan_domains, shodan_exposure)

        data = {
            "target": target, "apex_domain": apex,
            "org_name": org_name, "org_source": org_source,
            "whois": whois_info,
            "amass_available": self._amass_available(),
            "shodan_enabled": self.shodan_enabled,
            "shodan_available": self._shodan_available()[0] if self.shodan_enabled else False,
            "shodan_exposure": shodan_exposure[:50],
            "discovered_domains": correlated,
            "sources_used": sorted(set(s for d in correlated for s in d["sources"])),
            "command_executed": {k: v for k, v in self.command_executed.items() if v},
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
        }

        json_file = Path(output_dir) / "org_discovery_raw.json"
        with open(json_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

        return self.get_result_dict("success", {
            "raw_output": str(json_file),
            "start_time": start_time,
            "end_time": datetime.utcnow().isoformat(timespec="milliseconds"),
        })

    def post_process(self, raw_output, output_dir):
        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": self.display_name,
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
        }

        raw_results = raw_output.get("results", {})
        if raw_output.get("disposition") != "success" or not raw_results.get("raw_output"):
            processed["executive_summary"] = "Organization domain discovery did not complete."
            processed["findings_count"] = 0
            processed["findings"] = {}
            processed["issues"] = []
            processed["summary"] = "No results available."
            processed["details"] = "Plugin did not complete successfully."
            out_file = Path(output_dir) / "org_discovery_processed.json"
            with open(out_file, "w") as f:
                json.dump(processed, f, indent=2)
            return str(out_file)

        try:
            with open(raw_results["raw_output"]) as f:
                data = json.load(f)
        except Exception as e:
            processed["executive_summary"] = f"Error reading results: {e}"
            processed["findings_count"] = 0
            processed["findings"] = {}
            processed["issues"] = []
            processed["summary"] = f"Error: {e}"
            processed["details"] = f"Failed to read raw output file: {e}"
            out_file = Path(output_dir) / "org_discovery_processed.json"
            with open(out_file, "w") as f:
                json.dump(processed, f, indent=2)
            return str(out_file)

        domains = data.get("discovered_domains", [])
        exposure = data.get("shodan_exposure", [])
        sources = data.get("sources_used", [])
        n = len(domains)

        high = [d for d in domains if d["confidence"] >= 0.7]
        med = [d for d in domains if 0.4 <= d["confidence"] < 0.7]

        src_parts = []
        if "amass" in sources:
            src_parts.append("Amass")
        if "shodan" in sources:
            src_parts.append("Shodan")
        if any(s.startswith("crtsh") for s in sources):
            src_parts.append("CT logs")
        if any(s in sources for s in ("spf_include", "dmarc_ref")):
            src_parts.append("DNS records")
        src_str = ", ".join(src_parts) if src_parts else "passive sources"

        parts = [f"Discovered {n} domain(s) potentially belonging to the same organization via {src_str}."]
        if high:
            parts.append(f"{len(high)} high-confidence match(es).")
        if exposure:
            parts.append(f"Shodan identified {len(exposure)} exposed service(s) across organizational assets.")

        processed["executive_summary"] = " ".join(parts)
        processed["findings_count"] = n
        processed["findings"] = data
        processed["issues"] = []
        processed["summary"] = self._generate_summary(domains)
        processed["details"] = (
            f"Organization: {data.get('org_name', 'Unknown')}\n"
            f"Apex domain: {data.get('apex_domain', '')}\n"
            f"Domains discovered: {n}\n"
            f"High confidence: {len(high)}\n"
            f"Sources: {src_str}\n"
            f"Exposed services (Shodan): {len(exposure)}"
        )
        processed["custom_html"] = self._build_html(data)
        processed["custom_html_pdf"] = self._build_html_pdf(data)

        out_file = Path(output_dir) / "org_discovery_processed.json"
        with open(out_file, "w") as f:
            json.dump(processed, f, indent=2, default=str)
        return str(out_file)

    # ------------------------------------------------------------------
    # HTML builders
    # ------------------------------------------------------------------

    def _build_html(self, data):
        domains = data.get("discovered_domains", [])
        exposure = data.get("shodan_exposure", [])
        org = data.get("org_name", "Unknown")
        apex = data.get("apex_domain", "")

        h = ['<div class="org-discovery-widget">']
        h.append(f'<p><strong>Target:</strong> {apex} &nbsp; <strong>Org:</strong> {org or "Not detected"}</p>')

        if domains:
            h.append('<h4>Discovered Domains</h4>')
            h.append('<table class="table table-sm table-striped"><thead><tr>'
                     '<th>Domain</th><th>Confidence</th><th>Sources</th><th>Amass Intel</th><th>Exposed Services</th>'
                     '</tr></thead><tbody>')
            for d in domains:
                conf = d["confidence"]
                badge = "success" if conf >= 0.7 else "warning" if conf >= 0.4 else "secondary"
                amass_src = ", ".join(d.get("amass_sources", [])[:5]) or "-"
                svc_count = len(d.get("shodan_services", []))
                svc_str = f'{svc_count} service(s)' if svc_count else "-"
                h.append(f'<tr><td>{d["domain"]}</td>'
                         f'<td><span class="badge bg-{badge}">{conf:.0%}</span></td>'
                         f'<td>{", ".join(d["sources"])}</td>'
                         f'<td><small>{amass_src}</small></td>'
                         f'<td>{svc_str}</td></tr>')
            h.append('</tbody></table>')

        if exposure:
            h.append('<h4>Shodan: Internet-Exposed Services</h4>')
            h.append('<table class="table table-sm table-striped"><thead><tr>'
                     '<th>IP</th><th>Port</th><th>Service</th><th>Hostnames</th><th>Org</th>'
                     '</tr></thead><tbody>')
            for e in exposure[:30]:
                hosts = ", ".join(e.get("hostnames", [])[:3]) or "-"
                h.append(f'<tr><td>{e["ip"]}</td><td>{e["port"]}/{e["transport"]}</td>'
                         f'<td>{e.get("product", "")} {e.get("version", "")}</td>'
                         f'<td><small>{hosts}</small></td><td>{e.get("org", "")}</td></tr>')
            h.append('</tbody></table>')
            if len(exposure) > 30:
                h.append(f'<p class="text-muted"><em>Showing 30 of {len(exposure)} results</em></p>')

        h.append('</div>')
        return "\n".join(h)

    def _build_html_pdf(self, data):
        domains = data.get("discovered_domains", [])
        exposure = data.get("shodan_exposure", [])
        org = data.get("org_name", "Unknown")
        apex = data.get("apex_domain", "")

        h = ['<div class="org-discovery-widget">']
        h.append(f'<p><strong>Target:</strong> {apex} | <strong>Org:</strong> {org or "Not detected"}</p>')

        if domains:
            h.append('<h4>Discovered Domains</h4><table border="1" cellpadding="4" cellspacing="0" '
                     'style="border-collapse:collapse;width:100%;font-size:10px;">'
                     '<tr style="background:#f0f0f0;"><th>Domain</th><th>Confidence</th>'
                     '<th>Sources</th><th>Amass</th></tr>')
            for d in domains[:30]:
                conf = d["confidence"]
                h.append(f'<tr><td>{d["domain"]}</td><td>{conf:.0%}</td>'
                         f'<td>{", ".join(d["sources"])}</td>'
                         f'<td>{", ".join(d.get("amass_sources", [])[:3]) or "-"}</td></tr>')
            h.append('</table>')

        if exposure:
            h.append('<h4>Internet-Exposed Services (Shodan)</h4>'
                     '<table border="1" cellpadding="4" cellspacing="0" '
                     'style="border-collapse:collapse;width:100%;font-size:10px;">'
                     '<tr style="background:#f0f0f0;"><th>IP</th><th>Service</th><th>Hostnames</th></tr>')
            for e in exposure[:20]:
                hosts = ", ".join(e.get("hostnames", [])[:2]) or "-"
                h.append(f'<tr><td>{e["ip"]}</td><td>{e["service"]}</td><td>{hosts}</td></tr>')
            h.append('</table>')

        h.append('</div>')
        return "\n".join(h)

    def get_dry_run_info(self, target, output_dir):
        apex = self._apex(target.replace("https://", "").replace("http://", "").split("/")[0])
        cmds = []
        if self.crtsh_enabled:
            cmds.append(f"curl 'https://crt.sh/?q={apex}&output=json'")
        if self.dns_analysis_enabled and HAS_DNSPYTHON:
            cmds.append(f"dig TXT {apex}  # SPF")
            cmds.append(f"dig TXT _dmarc.{apex}  # DMARC")
        if self.whois_enabled and HAS_WHOIS:
            cmds.append(f"whois {apex}")
        if self.amass_enabled:
            amass_cmd = f"amass enum -passive -d {apex} -json amass_output.json -timeout {max(1, self.amass_timeout // 60)}"
            if not self._amass_available():
                amass_cmd += "  # (amass not installed)"
            cmds.append(amass_cmd)
        if self.shodan_enabled:
            avail, reason = self._shodan_available()
            shodan_cmd = f"shodan search 'hostname:{apex}'"
            if not avail:
                shodan_cmd += f"  # ({reason})"
            cmds.append(shodan_cmd)
        return {
            "plugin": self.display_name,
            "commands": cmds,
            "output_files": [str(Path(output_dir) / "org_discovery_raw.json")],
            "notes": [
                f"Sources: crt.sh={'on' if self.crtsh_enabled else 'off'}, "
                f"DNS={'on' if self.dns_analysis_enabled else 'off'}, "
                f"WHOIS={'on' if self.whois_enabled else 'off'}, "
                f"Amass={'on' if self.amass_enabled else 'off'} "
                f"({'found' if self._amass_available() else 'NOT found'}), "
                f"Shodan={'on' if self.shodan_enabled else 'off'} "
                f"({'key set' if self.shodan_api_key else 'no key'})",
            ],
        }

