"""
File: plugins/plugin_related_sites.py
Description: Discovers related subdomains and probes for live web services.

This plugin combines subdomain enumeration with HTTP probing to identify
related web properties. It extracts the apex domain from the target FQDN,
discovers subdomains using subfinder, and probes them with httpx to find
live web services.
"""

import subprocess
import shutil
import os
import json
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat
import tldextract

class RelatedSitesPlugin(KastPlugin):
    priority = 45  # After initial recon, before deep analysis
    
    # Configuration schema for kast-web integration
    config_schema = {
        "type": "object",
        "title": "Related Sites Discovery Configuration",
        "description": "Settings for subdomain enumeration and HTTP probing",
        "properties": {
            "httpx_rate_limit": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
                "description": "Maximum HTTP requests per second for httpx probing"
            },
            "subfinder_timeout": {
                "type": "integer",
                "default": 300,
                "minimum": 30,
                "maximum": 3600,
                "description": "Timeout for subfinder execution in seconds"
            },
            "max_subdomains": {
                "type": ["integer", "null"],
                "default": None,
                "minimum": 1,
                "description": "Maximum number of subdomains to process (null for unlimited)"
            },
            "httpx_ports": {
                "type": "array",
                "items": {"type": "integer"},
                "default": [80, 443, 8080, 8443, 8000, 8888],
                "description": "List of ports to probe with httpx"
            },
            "httpx_timeout": {
                "type": "integer",
                "default": 10,
                "minimum": 5,
                "maximum": 60,
                "description": "Timeout per host for httpx in seconds"
            },
            "httpx_threads": {
                "type": "integer",
                "default": 50,
                "minimum": 1,
                "maximum": 200,
                "description": "Number of parallel threads for httpx"
            }
        }
    }
    
    def __init__(self, cli_args, config_manager=None):
        # IMPORTANT: Set plugin name BEFORE calling super().__init__()
        # so that schema registration uses the correct plugin name
        self.name = "related_sites"
        self.display_name = "Related Sites Discovery"
        self.description = "Discovers related subdomains and probes for live web services"
        self.website_url = "https://github.com/mercutioviz/kast"
        self.scan_type = "passive"  # Makes HTTP requests
        self.output_type = "file"
        
        # Now call parent init (this will register our schema under correct name)
        super().__init__(cli_args, config_manager)
        
        self.command_executed = {
            "subfinder": None,
            "httpx": None
        }
        
        # Load configuration values (with backward compatibility for CLI args)
        self._load_plugin_config()
    
    def _load_plugin_config(self):
        """Load configuration with backward compatibility for legacy CLI args."""
        # Get config values (defaults from schema if not set)
        self.httpx_rate_limit = self.get_config('httpx_rate_limit', 10)
        self.subfinder_timeout = self.get_config('subfinder_timeout', 300)
        self.max_subdomains = self.get_config('max_subdomains', None)
        self.httpx_ports = self.get_config('httpx_ports', [80, 443, 8080, 8443, 8000, 8888])
        self.httpx_timeout = self.get_config('httpx_timeout', 10)
        self.httpx_threads = self.get_config('httpx_threads', 50)
        
        # Backward compatibility: Check for legacy CLI args
        if hasattr(self.cli_args, 'httpx_rate_limit') and self.cli_args.httpx_rate_limit:
            self.httpx_rate_limit = self.cli_args.httpx_rate_limit
            self.debug("Using deprecated --httpx-rate-limit CLI arg. Please use --set related_sites.httpx_rate_limit=N")

    def is_available(self):
        """
        Check if required tools (subfinder and httpx) are installed.
        """
        has_subfinder = shutil.which("subfinder") is not None
        has_httpx = shutil.which("httpx") is not None
        
        if not has_subfinder:
            self.debug("subfinder not found in PATH")
        if not has_httpx:
            self.debug("httpx not found in PATH")
        
        # Both required for full functionality
        return has_subfinder and has_httpx

    def _extract_apex_domain(self, fqdn):
        """
        Extract apex domain from FQDN using tldextract.
        
        Examples:
          www.example.com -> example.com
          admin.portal.example.com -> example.com
          example.com -> example.com
          example.co.uk -> example.co.uk
        
        :param fqdn: The fully qualified domain name
        :return: The apex domain (domain.tld)
        """
        extracted = tldextract.extract(fqdn)
        apex = f"{extracted.domain}.{extracted.suffix}"
        self.debug(f"Extracted apex domain '{apex}' from '{fqdn}'")
        return apex

    def _should_scan_apex(self, original_target, apex_domain):
        """
        Decide whether to scan apex domain or original FQDN.
        
        Logic:
        - If target IS apex (e.g., example.com), scan it
        - If target is subdomain (e.g., www.example.com), scan apex
        - This behavior ensures we discover all related subdomains
        
        :param original_target: The original target from user
        :param apex_domain: The extracted apex domain
        :return: True to scan apex, False to scan original
        """
        # For this standalone implementation, always scan apex
        # to discover all related subdomains
        return original_target != apex_domain

    def _run_subfinder(self, domain, output_dir):
        """
        Execute subfinder to discover subdomains.
        
        :param domain: The domain to scan
        :param output_dir: Directory to write output files
        :return: List of discovered subdomain strings
        """
        output_file = os.path.join(output_dir, "related_sites_subfinder.json")
        
        cmd = [
            "subfinder",
            "-d", domain,
            "-o", output_file,
            "-json",
            "-silent"  # Reduce noise in output
        ]
        
        # Add verbose flag if enabled
        if getattr(self.cli_args, "verbose", False):
            cmd.remove("-silent")
            cmd.insert(1, "-v")
        
        # Store command for reporting
        self.command_executed["subfinder"] = ' '.join(cmd)
        self.debug(f"Running subfinder: {' '.join(cmd)}")
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.subfinder_timeout  # Use config value
            )
            
            if proc.returncode != 0:
                self.debug(f"Subfinder failed with return code {proc.returncode}")
                self.debug(f"Stderr: {proc.stderr}")
                return []
            
            # Parse JSON Lines format (one JSON object per line)
            subdomains = []
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                host = data.get('host', '').strip()
                                if host:
                                    subdomains.append(host)
                            except json.JSONDecodeError as e:
                                self.debug(f"Failed to parse line: {line}, error: {e}")
                                continue
            
            # Deduplicate
            unique_subdomains = list(set(subdomains))
            self.debug(f"Subfinder discovered {len(unique_subdomains)} unique subdomain(s)")
            
            return unique_subdomains
            
        except subprocess.TimeoutExpired:
            self.debug(f"Subfinder timed out after {self.subfinder_timeout} seconds")
            return []
        except Exception as e:
            self.debug(f"Subfinder execution error: {e}")
            return []

    def _probe_subdomains_with_httpx(self, subdomains, output_dir):
        """
        Probe subdomains with httpx to find live web services.
        
        :param subdomains: List of subdomain strings to probe
        :param output_dir: Directory to write output files
        :return: Dict with categorized results
        """
        if not subdomains:
            return {
                "live_hosts": [],
                "dead_hosts": [],
                "by_status": {},
                "by_port": {},
                "technologies": {},
                "redirects": [],
                "with_cdn": [],
                "websockets": []
            }
        
        # Write subdomains to temp file (httpx input)
        input_file = os.path.join(output_dir, "related_sites_targets.txt")
        with open(input_file, 'w') as f:
            f.write('\n'.join(subdomains))
        
        self.debug(f"Wrote {len(subdomains)} subdomains to {input_file}")
        
        # Apply max_subdomains limit if configured
        if self.max_subdomains and len(subdomains) > self.max_subdomains:
            self.debug(f"Limiting subdomains from {len(subdomains)} to {self.max_subdomains}")
            subdomains = subdomains[:self.max_subdomains]
            # Re-write limited list to input file
            with open(input_file, 'w') as f:
                f.write('\n'.join(subdomains))
        
        output_file = os.path.join(output_dir, "related_sites_httpx.json")
        
        # Use config values
        self.debug(f"Using httpx rate limit: {self.httpx_rate_limit} requests/second")
        self.debug(f"Using httpx timeout: {self.httpx_timeout} seconds")
        self.debug(f"Using httpx threads: {self.httpx_threads}")
        self.debug(f"Using httpx ports: {','.join(map(str, self.httpx_ports))}")
        
        # Configure httpx command with config values
        cmd = [
            "httpx",
            "-l", input_file,           # Input list
            "-json",                     # JSON output
            "-o", output_file,          # Output file
            "-silent",                   # Reduce noise
            "-timeout", str(self.httpx_timeout),  # Use config value
            "-retries", "2",             # Retry failed requests
            "-threads", str(self.httpx_threads),  # Use config value
            "-rate-limit", str(self.httpx_rate_limit),  # Use config value
            "-ports", ",".join(map(str, self.httpx_ports)),  # Use config value
            "-follow-redirects",         # Follow redirects
            "-status-code",              # Include status code
            "-title",                    # Extract page title
            "-tech-detect",              # Detect technologies
            "-websocket",                # Check for websocket
            "-cdn"                       # Detect CDN
        ]
        
        # Store command for reporting
        self.command_executed["httpx"] = ' '.join(cmd)
        self.debug(f"Running httpx: {' '.join(cmd)}")
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            self.debug(f"HTTPx completed with return code {proc.returncode}")
            
            # Parse results even if non-zero return code (partial results)
            return self._parse_httpx_results(output_file, subdomains)
            
        except subprocess.TimeoutExpired:
            self.debug("HTTPx timed out after 600 seconds")
            # Try to parse partial results
            return self._parse_httpx_results(output_file, subdomains)
        except Exception as e:
            self.debug(f"HTTPx execution error: {e}")
            return {
                "live_hosts": [],
                "dead_hosts": subdomains,
                "by_status": {},
                "by_port": {},
                "technologies": {},
                "redirects": [],
                "with_cdn": [],
                "websockets": []
            }

    def _parse_httpx_results(self, output_file, all_subdomains):
        """
        Parse httpx JSON output and categorize findings.
        
        A "host" is a subdomain. A host is "live" if it responds on ANY port.
        Results are aggregated by host, not by port response.
        
        :param output_file: Path to httpx JSON output
        :param all_subdomains: List of all subdomains that were probed
        :return: Dict with categorized results
        """
        # Aggregate responses by host
        hosts_data = {}  # host -> list of port responses
        
        if not os.path.exists(output_file):
            self.debug(f"HTTPx output file not found: {output_file}")
            return {
                "live_hosts": [],
                "dead_hosts": all_subdomains,
                "hosts_by_subdomain": {}
            }
        
        # Parse httpx JSON Lines output and group by host
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        host = data.get('host', '')
                        if not host:
                            continue
                        
                        # Port can be string or int from httpx, normalize to int
                        port = int(data.get('port', 0)) if data.get('port') else 0
                        status_code = data.get('status_code', 0)
                        title = data.get('title', '')
                        tech = data.get('tech', [])
                        cdn = data.get('cdn', '')
                        websocket = data.get('websocket', False)
                        url = data.get('url', '')
                        
                        port_response = {
                            "port": port,
                            "url": url,
                            "status_code": status_code,
                            "title": title,
                            "technologies": tech if isinstance(tech, list) else [],
                            "cdn": cdn,
                            "websocket": websocket
                        }
                        
                        if host not in hosts_data:
                            hosts_data[host] = []
                        hosts_data[host].append(port_response)
                        
                    except json.JSONDecodeError as e:
                        self.debug(f"Failed to parse HTTPx line: {line}, error: {e}")
                        continue
        except Exception as e:
            self.debug(f"Error reading HTTPx output: {e}")
        
        # Build host-centric results
        live_hosts = []
        for host, port_responses in hosts_data.items():
            # Aggregate technologies across all ports
            all_technologies = set()
            ports = []
            has_cdn = False
            has_websocket = False
            
            for resp in port_responses:
                ports.append(resp["port"])
                all_technologies.update(resp["technologies"])
                if resp["cdn"]:
                    has_cdn = True
                if resp["websocket"]:
                    has_websocket = True
            
            host_info = {
                "host": host,
                "ports": sorted(list(set(ports))),  # Unique ports, sorted
                "port_responses": port_responses,  # Detailed per-port data
                "technologies": sorted(list(all_technologies)),
                "has_cdn": has_cdn,
                "has_websocket": has_websocket
            }
            live_hosts.append(host_info)
        
        # Determine dead hosts (subdomains that didn't respond on any port)
        live_hosts_set = set(hosts_data.keys())
        dead_hosts = [h for h in all_subdomains if h not in live_hosts_set]
        
        self.debug(f"HTTPx found {len(live_hosts)} unique live host(s) (responded on any port), "
                  f"{len(dead_hosts)} dead host(s)")
        
        return {
            "live_hosts": live_hosts,  # List of host info dicts
            "dead_hosts": dead_hosts,  # List of hostnames
            "hosts_by_subdomain": hosts_data  # Raw data for reference
        }

    def run(self, target, output_dir, report_only):
        """
        Execute the plugin workflow.
        
        :param target: The target domain or FQDN to scan
        :param output_dir: Directory to write output files
        :param report_only: If True, skip execution and load existing results
        :return: Standardized result dictionary
        """
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        
        # Handle report-only mode
        if report_only:
            output_file = os.path.join(output_dir, f"{self.name}.json")
            if os.path.exists(output_file):
                self.debug(f"Loading existing results from {output_file}")
                with open(output_file, 'r') as f:
                    results = json.load(f)
                return self.get_result_dict("success", results, timestamp)
            else:
                return self.get_result_dict("fail", "No existing results found", timestamp)
        
        # Check tool availability
        if not self.is_available():
            return self.get_result_dict(
                "fail",
                "Required tools (subfinder and/or httpx) not found in PATH",
                timestamp
            )
        
        # Create empty related_sites.json file first, so that kast-web knows we are running
        in_progress_file = os.path.join(output_dir, "related_sites.json")
        open(in_progress_file, 'a').close()
        
        # Step 1: Extract apex domain
        apex_domain = self._extract_apex_domain(target)
        self.debug(f"Target: {target}, Apex: {apex_domain}")
        
        # Determine what to scan
        if self._should_scan_apex(target, apex_domain):
            scan_target = apex_domain
            self.debug(f"Will scan apex domain: {scan_target}")
        else:
            scan_target = target
            self.debug(f"Will scan original target: {scan_target}")
        
        # Step 2: Discover subdomains with subfinder
        self.debug(f"Discovering subdomains for {scan_target}")
        subdomains = self._run_subfinder(scan_target, output_dir)
        
        if not subdomains:
            self.debug("No subdomains discovered, scan failed")
            return self.get_result_dict(
                "fail",
                f"No subdomains discovered for {scan_target}",
                timestamp
            )
        
        self.debug(f"Discovered {len(subdomains)} subdomain(s)")
        
        # Step 3: Probe with httpx
        self.debug(f"Probing {len(subdomains)} subdomain(s) with httpx")
        probe_results = self._probe_subdomains_with_httpx(subdomains, output_dir)
        
        # Step 4: Calculate statistics from host-centric data
        live_hosts = probe_results["live_hosts"]
        dead_hosts = probe_results["dead_hosts"]
        
        # Aggregate technologies across all live hosts
        all_technologies = set()
        cdn_count = 0
        websocket_count = 0
        
        for host_info in live_hosts:
            all_technologies.update(host_info["technologies"])
            if host_info["has_cdn"]:
                cdn_count += 1
            if host_info["has_websocket"]:
                websocket_count += 1
        
        final_results = {
            "target": target,
            "apex_domain": apex_domain,
            "scanned_domain": scan_target,
            "total_subdomains": len(subdomains),
            "subdomains": subdomains,
            "live_hosts": live_hosts,
            "dead_hosts": dead_hosts,
            "statistics": {
                "total_discovered": len(subdomains),
                "total_live": len(live_hosts),
                "total_dead": len(dead_hosts),
                "response_rate": (len(live_hosts) / len(subdomains) * 100) if len(subdomains) > 0 else 0,
                "unique_technologies": len(all_technologies),
                "cdn_protected": cdn_count,
                "websocket_enabled": websocket_count
            }
        }
        
        # Save results
        output_file = os.path.join(output_dir, f"{self.name}.json")
        with open(output_file, 'w') as f:
            json.dump(final_results, f, indent=2)
        
        self.debug(f"Results saved to {output_file}")
        
        return self.get_result_dict("success", final_results, timestamp)

    def post_process(self, raw_output, output_dir):
        """
        Post-process the raw output and generate reports.
        
        :param raw_output: Raw output from run() method
        :param output_dir: Directory to write processed output
        :return: Path to processed JSON file
        """
        # Extract the actual results from the nested structure
        # raw_output has structure: {"name": ..., "disposition": ..., "results": {...}}
        # We need to pass the "results" dict to our helper methods
        findings = raw_output.get("results", {}) if isinstance(raw_output, dict) else {}
        
        self.debug(f"{self.name} processing findings")
        
        # Generate components
        summary = self._generate_summary(findings)
        exec_summary = self._generate_executive_summary(findings)
        details = self._generate_details(findings)
        issues = self._identify_issues(findings)
        custom_html = self._generate_custom_html(findings)
        custom_html_pdf = self._generate_pdf_html(findings)
        
        # Calculate findings_count - number of live hosts (subdomains responding to HTTP requests)
        stats = findings.get("statistics", {})
        findings_count = stats.get("total_live", 0)
        
        self.debug(f"{self.name} findings_count: {findings_count}")
        
        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": self.display_name,
            "plugin-website-url": self.website_url,
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "findings_count": findings_count,
            "summary": summary,
            "details": details,
            "issues": issues,
            "executive_summary": exec_summary,
            "custom_html": custom_html,
            "custom_html_pdf": custom_html_pdf,
            "commands_executed": self.command_executed,
            "results_message": "See live and dead host information below"
        }
        
        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, 'w') as f:
            json.dump(processed, f, indent=2)
        
        self.debug(f"Processed output saved to {processed_path}")
        
        return processed_path

    def _generate_summary(self, findings):
        """Generate a human-readable summary."""
        stats = findings.get("statistics", {})
        total = stats.get("total_discovered", 0)
        live = stats.get("total_live", 0)
        rate = stats.get("response_rate", 0)
        
        return f"Discovered {total} subdomain(s), {live} responding to HTTP requests ({rate:.1f}% response rate)"

    def _generate_executive_summary(self, findings):
        """Generate high-level summary for executives."""
        stats = findings.get("statistics", {})
        live_count = stats.get("total_live", 0)
        total_count = stats.get("total_discovered", 0)
        response_rate = stats.get("response_rate", 0)
        
        summary_points = []
        
        summary_points.append(
            f"Discovered {total_count} related subdomain(s), "
            f"{live_count} responding to HTTP requests ({response_rate:.1f}% response rate)"
        )
        
        # Analyze live hosts for interesting findings
        live_hosts = findings.get("live_hosts", [])
        
        if live_hosts:
            # Count status codes across all port responses
            status_200_count = 0
            redirect_count = 0
            
            for host_info in live_hosts:
                for port_resp in host_info.get("port_responses", []):
                    status = port_resp.get("status_code", 0)
                    if status == 200:
                        status_200_count += 1
                    elif 300 <= status < 400:
                        redirect_count += 1
            
            if status_200_count > 0:
                summary_points.append(f"{status_200_count} successful HTTP response(s) (200 OK) across all hosts")
            
            if redirect_count > 0:
                summary_points.append(f"{redirect_count} redirect response(s) configured")
        
        # CDN and WebSocket stats
        cdn_count = stats.get("cdn_protected", 0)
        if cdn_count > 0:
            summary_points.append(f"{cdn_count} subdomain(s) using CDN protection")
        
        websocket_count = stats.get("websocket_enabled", 0)
        if websocket_count > 0:
            summary_points.append(f"{websocket_count} subdomain(s) supporting WebSocket connections")
        
        # Technology summary
        if live_hosts:
            # Count technology occurrences across hosts
            tech_counts = {}
            for host_info in live_hosts:
                for tech in host_info.get("technologies", []):
                    tech_counts[tech] = tech_counts.get(tech, 0) + 1
            
            if tech_counts:
                top_techs = sorted(tech_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                tech_summary = ", ".join([f"{name} ({count})" for name, count in top_techs])
                summary_points.append(f"Most common technologies: {tech_summary}")
        
        return summary_points

    def _generate_details(self, findings):
        """Generate concise details summary."""
        stats = findings.get("statistics", {})
        
        lines = []
        lines.append(f"Target: {findings.get('target', 'N/A')}")
        lines.append(f"Apex Domain: {findings.get('apex_domain', 'N/A')}")
        lines.append(f"Scanned Domain: {findings.get('scanned_domain', 'N/A')}")
        lines.append("")
        lines.append(f"Total Subdomains Discovered: {stats.get('total_discovered', 0)}")
        lines.append(f"Live Hosts: {stats.get('total_live', 0)}")
        lines.append(f"Dead Hosts: {stats.get('total_dead', 0)}")
        lines.append(f"Response Rate: {stats.get('response_rate', 0):.1f}%")
        lines.append(f"Unique Technologies: {stats.get('unique_technologies', 0)}")
        
        if stats.get('cdn_protected', 0) > 0:
            lines.append(f"CDN Protected: {stats['cdn_protected']}")
        
        if stats.get('websocket_enabled', 0) > 0:
            lines.append(f"WebSocket Enabled: {stats['websocket_enabled']}")
        
        return "\n".join(lines)

    def _identify_issues(self, findings):
        """Identify security issues from findings."""
        issues = []
        
        # This plugin is primarily for discovery
        # Issues would be identified by other plugins analyzing the discovered hosts
        # For now, return empty list
        
        return issues

    def _generate_custom_html(self, findings):
        """Generate custom HTML widget for interactive report display with host-centric view."""
        stats = findings.get("statistics", {})
        live_hosts = findings.get("live_hosts", [])
        dead_hosts = findings.get("dead_hosts", [])
        
        total_subdomains = stats.get("total_discovered", 0)
        total_live = stats.get("total_live", 0)
        total_dead = stats.get("total_dead", 0)
        response_rate = stats.get("response_rate", 0)
        
        # Serialize data for JavaScript
        import json
        live_hosts_json = json.dumps(live_hosts)
        dead_hosts_json = json.dumps(dead_hosts)
        
        html = f'''
        <div class="related-sites-widget">
            <div class="stats-summary">
                <div class="stat-card">
                    <div class="stat-value">{total_subdomains}</div>
                    <div class="stat-label">Total Subdomains</div>
                </div>
                <div class="stat-card stat-success">
                    <div class="stat-value">{total_live}</div>
                    <div class="stat-label">Live Hosts ({response_rate:.1f}%)</div>
                </div>
                <div class="stat-card stat-dead">
                    <div class="stat-value">{total_dead}</div>
                    <div class="stat-label">Dead Hosts ({100 - response_rate:.1f}%)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get("unique_technologies", 0)}</div>
                    <div class="stat-label">Technologies</div>
                </div>
            </div>
            
            <!-- Live Hosts Section -->
            <div class="hosts-section">
                <div class="section-header" onclick="toggleSection('live-hosts-section')">
                    <h3>▼ Live Hosts ({total_live})</h3>
                </div>
                <div class="section-content" id="live-hosts-section">
                    <div class="pagination-controls">
                        <button onclick="setLivePageSize(25)">Show 25</button>
                        <button onclick="setLivePageSize(50)">Show 50</button>
                        <button onclick="setLivePageSize(100)">Show 100</button>
                        <button onclick="setLivePageSize(-1)">Show All</button>
                        <span id="live-pagination-info"></span>
                    </div>
                    <div id="live-hosts-container"></div>
                    <div class="pagination-nav" id="live-pagination-nav"></div>
                </div>
            </div>
            
            <!-- Dead Hosts Section -->
            <div class="hosts-section">
                <div class="section-header" onclick="toggleSection('dead-hosts-section')">
                    <h3>▶ Dead Hosts ({total_dead})</h3>
                </div>
                <div class="section-content" id="dead-hosts-section" style="display: none;">
                    <div class="pagination-controls">
                        <button onclick="setDeadPageSize(25)">Show 25</button>
                        <button onclick="setDeadPageSize(50)">Show 50</button>
                        <button onclick="setDeadPageSize(100)">Show 100</button>
                        <button onclick="setDeadPageSize(-1)">Show All</button>
                        <span id="dead-pagination-info"></span>
                    </div>
                    <div id="dead-hosts-container"></div>
                    <div class="pagination-nav" id="dead-pagination-nav"></div>
                </div>
            </div>
        </div>
        
        <script>
        // Data
        const liveHostsData = {live_hosts_json};
        const deadHostsData = {dead_hosts_json};
        
        // State
        let livePageSize = 25;
        let liveCurrentPage = 1;
        let deadPageSize = 25;
        let deadCurrentPage = 1;
        
        // Toggle section visibility
        function toggleSection(sectionId) {{
            const section = document.getElementById(sectionId);
            const header = section.previousElementSibling;
            const h3 = header.querySelector('h3');
            
            if (section.style.display === 'none') {{
                section.style.display = 'block';
                h3.textContent = h3.textContent.replace('▶', '▼');
            }} else {{
                section.style.display = 'none';
                h3.textContent = h3.textContent.replace('▼', '▶');
            }}
        }}
        
        // Live hosts pagination
        function setLivePageSize(size) {{
            livePageSize = size;
            liveCurrentPage = 1;
            renderLiveHosts();
        }}
        
        function renderLiveHosts() {{
            const container = document.getElementById('live-hosts-container');
            const paginationNav = document.getElementById('live-pagination-nav');
            const paginationInfo = document.getElementById('live-pagination-info');
            
            const totalHosts = liveHostsData.length;
            const itemsPerPage = livePageSize === -1 ? totalHosts : livePageSize;
            const totalPages = Math.ceil(totalHosts / itemsPerPage);
            const start = (liveCurrentPage - 1) * itemsPerPage;
            const end = livePageSize === -1 ? totalHosts : Math.min(start + itemsPerPage, totalHosts);
            
            // Render hosts
            let html = '<div class="hosts-list">';
            for (let i = start; i < end; i++) {{
                const host = liveHostsData[i];
                html += renderLiveHost(host);
            }}
            html += '</div>';
            container.innerHTML = html;
            
            // Render pagination info
            paginationInfo.textContent = `Showing ${{start + 1}}-${{end}} of ${{totalHosts}}`;
            
            // Render pagination controls
            if (totalPages > 1) {{
                let navHtml = '';
                if (liveCurrentPage > 1) {{
                    navHtml += '<button onclick="changeLivePage(-1)">Previous</button>';
                }}
                navHtml += ` Page ${{liveCurrentPage}} of ${{totalPages}} `;
                if (liveCurrentPage < totalPages) {{
                    navHtml += '<button onclick="changeLivePage(1)">Next</button>';
                }}
                paginationNav.innerHTML = navHtml;
            }} else {{
                paginationNav.innerHTML = '';
            }}
        }}
        
        function changeLivePage(delta) {{
            liveCurrentPage += delta;
            renderLiveHosts();
        }}
        
        function renderLiveHost(host) {{
            let html = `
                <div class="host-card">
                    <div class="host-name">${{host.host}}</div>
                    <div class="host-ports">Ports: ${{host.ports.join(', ')}}</div>
            `;
            
            // Render each port response
            for (const resp of host.port_responses) {{
                const statusClass = resp.status_code >= 200 && resp.status_code < 300 ? 'status-success' : 
                                  resp.status_code >= 300 && resp.status_code < 400 ? 'status-redirect' : 'status-error';
                html += `
                    <div class="port-response">
                        <div class="port-header">
                            <span class="port-number">Port ${{resp.port}}</span>
                            <span class="status-badge ${{statusClass}}">${{resp.status_code}}</span>
                        </div>
                        <div class="port-url"><a href="${{resp.url}}" target="_blank">${{resp.url}}</a></div>
                        <div class="port-title">${{resp.title || 'No title'}}</div>
                `;
                
                if (resp.technologies && resp.technologies.length > 0) {{
                    html += `<div class="port-tech">🔧 ${{resp.technologies.join(', ')}}</div>`;
                }}
                if (resp.cdn) {{
                    html += `<div class="port-cdn">🛡️ CDN: ${{resp.cdn}}</div>`;
                }}
                if (resp.websocket) {{
                    html += `<div class="port-websocket">🔌 WebSocket Enabled</div>`;
                }}
                
                html += '</div>';
            }}
            
            html += '</div>';
            return html;
        }}
        
        // Dead hosts pagination
        function setDeadPageSize(size) {{
            deadPageSize = size;
            deadCurrentPage = 1;
            renderDeadHosts();
        }}
        
        function renderDeadHosts() {{
            const container = document.getElementById('dead-hosts-container');
            const paginationNav = document.getElementById('dead-pagination-nav');
            const paginationInfo = document.getElementById('dead-pagination-info');
            
            const totalHosts = deadHostsData.length;
            const itemsPerPage = deadPageSize === -1 ? totalHosts : deadPageSize;
            const totalPages = Math.ceil(totalHosts / itemsPerPage);
            const start = (deadCurrentPage - 1) * itemsPerPage;
            const end = deadPageSize === -1 ? totalHosts : Math.min(start + itemsPerPage, totalHosts);
            
            // Render hosts
            let html = '<div class="dead-hosts-list">';
            for (let i = start; i < end; i++) {{
                html += `<div class="dead-host-item">${{deadHostsData[i]}}</div>`;
            }}
            html += '</div>';
            container.innerHTML = html;
            
            // Render pagination info
            paginationInfo.textContent = `Showing ${{start + 1}}-${{end}} of ${{totalHosts}}`;
            
            // Render pagination controls
            if (totalPages > 1) {{
                let navHtml = '';
                if (deadCurrentPage > 1) {{
                    navHtml += '<button onclick="changeDeadPage(-1)">Previous</button>';
                }}
                navHtml += ` Page ${{deadCurrentPage}} of ${{totalPages}} `;
                if (deadCurrentPage < totalPages) {{
                    navHtml += '<button onclick="changeDeadPage(1)">Next</button>';
                }}
                paginationNav.innerHTML = navHtml;
            }} else {{
                paginationNav.innerHTML = '';
            }}
        }}
        
        function changeDeadPage(delta) {{
            deadCurrentPage += delta;
            renderDeadHosts();
        }}
        
        // Initial render
        renderLiveHosts();
        renderDeadHosts();
        </script>
        
        <style>
        .related-sites-widget {{
            margin: 2em 0;
        }}
        
        .stats-summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1em;
            margin-bottom: 2em;
        }}
        
        .stat-card {{
            padding: 1.5em;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 8px;
            text-align: center;
        }}
        
        .stat-card.stat-success {{
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        }}
        
        .stat-card.stat-dead {{
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        }}
        
        .stat-value {{
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 0.25em;
        }}
        
        .stat-label {{
            font-size: 0.95em;
            opacity: 0.95;
        }}
        
        .hosts-section {{
            margin: 2em 0;
            border: 1px solid #e6eef6;
            border-radius: 8px;
            overflow: hidden;
        }}
        
        .section-header {{
            background: #f8fbfd;
            padding: 1em 1.5em;
            cursor: pointer;
            user-select: none;
        }}
        
        .section-header:hover {{
            background: #e6f0fa;
        }}
        
        .section-header h3 {{
            margin: 0;
            color: #075985;
        }}
        
        .section-content {{
            padding: 1.5em;
            background: white;
        }}
        
        .pagination-controls {{
            display: flex;
            gap: 0.5em;
            align-items: center;
            margin-bottom: 1em;
            padding: 1em;
            background: #f8fbfd;
            border-radius: 4px;
        }}
        
        .pagination-controls button {{
            padding: 0.5em 1em;
            background: #075985;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }}
        
        .pagination-controls button:hover {{
            background: #0c4a6e;
        }}
        
        #live-pagination-info, #dead-pagination-info {{
            margin-left: auto;
            color: #075985;
            font-weight: 500;
        }}
        
        .hosts-list {{
            display: flex;
            flex-direction: column;
            gap: 1em;
        }}
        
        .host-card {{
            border: 1px solid #e6eef6;
            border-radius: 8px;
            padding: 1.5em;
            background: #fafbfc;
        }}
        
        .host-name {{
            font-size: 1.2em;
            font-weight: bold;
            color: #075985;
            margin-bottom: 0.5em;
        }}
        
        .host-ports {{
            color: #666;
            font-size: 0.9em;
            margin-bottom: 1em;
        }}
        
        .port-response {{
            margin: 1em 0;
            padding: 1em;
            background: white;
            border-left: 3px solid #075985;
            border-radius: 4px;
        }}
        
        .port-header {{
            display: flex;
            align-items: center;
            gap: 1em;
            margin-bottom: 0.5em;
        }}
        
        .port-number {{
            font-weight: bold;
            color: #075985;
        }}
        
        .status-badge {{
            padding: 0.25em 0.75em;
            border-radius: 4px;
            font-weight: bold;
            font-size: 0.9em;
        }}
        
        .status-success {{
            background: #dcfce7;
            color: #166534;
        }}
        
        .status-redirect {{
            background: #fef3c7;
            color: #92400e;
        }}
        
        .status-error {{
            background: #fee2e2;
            color: #991b1b;
        }}
        
        .port-url a {{
            color: #075985;
            text-decoration: none;
            font-weight: 500;
        }}
        
        .port-url a:hover {{
            text-decoration: underline;
        }}
        
        .port-title {{
            color: #666;
            font-size: 0.9em;
            margin: 0.5em 0;
        }}
        
        .port-tech, .port-cdn, .port-websocket {{
            font-size: 0.85em;
            color: #666;
            margin: 0.25em 0;
        }}
        
        .dead-hosts-list {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 0.5em;
        }}
        
        .dead-host-item {{
            padding: 0.75em;
            background: #f8fbfd;
            border-radius: 4px;
            color: #666;
            font-family: monospace;
            font-size: 0.9em;
        }}
        
        .pagination-nav {{
            margin-top: 1em;
            padding: 1em;
            text-align: center;
            background: #f8fbfd;
            border-radius: 4px;
        }}
        
        .pagination-nav button {{
            padding: 0.5em 1.5em;
            background: #075985;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin: 0 0.5em;
        }}
        
        .pagination-nav button:hover {{
            background: #0c4a6e;
        }}
        </style>
        '''
        
        return html

    def _generate_pdf_html(self, findings):
        """Generate PDF-friendly HTML output with host-centric table."""
        stats = findings.get("statistics", {})
        live_hosts = findings.get("live_hosts", [])
        dead_hosts = findings.get("dead_hosts", [])
        
        html = '<div class="pdf-related-sites">'
        html += f'<p><strong>Total Subdomains:</strong> {stats.get("total_discovered", 0)}</p>'
        html += f'<p><strong>Live Hosts:</strong> {stats.get("total_live", 0)} ({stats.get("response_rate", 0):.1f}% response rate)</p>'
        html += f'<p><strong>Dead Hosts:</strong> {stats.get("total_dead", 0)}</p>'
        
        if live_hosts:
            html += '<h4>Live Hosts (Top 25)</h4>'
            html += '<table style="width:100%; border-collapse: collapse; margin: 1em 0;">'
            html += '<tr style="background: #f0f0f0; border-bottom: 2px solid #333;">'
            html += '<th style="padding: 0.5em; text-align: left;">Host</th>'
            html += '<th style="padding: 0.5em; text-align: left;">Ports</th>'
            html += '<th style="padding: 0.5em; text-align: left;">Technologies</th>'
            html += '</tr>'
            
            for host_info in live_hosts[:25]:
                host = host_info.get('host', 'N/A')
                ports = ', '.join(map(str, host_info.get('ports', [])))
                
                # Build per-port details
                port_details = []
                for port_resp in host_info.get('port_responses', []):
                    port = port_resp.get('port', '')
                    status = port_resp.get('status_code', '')
                    tech = port_resp.get('technologies', [])
                    tech_str = ', '.join(tech) if tech else 'None'
                    port_details.append(f"Port {port} ({status}): {tech_str}")
                
                technologies = '<br/>'.join(port_details) if port_details else 'None detected'
                
                html += '<tr style="border-bottom: 1px solid #ddd;">'
                html += f'<td style="padding: 0.5em; vertical-align: top;"><strong>{host}</strong></td>'
                html += f'<td style="padding: 0.5em; vertical-align: top;">{ports}</td>'
                html += f'<td style="padding: 0.5em; vertical-align: top; font-size: 0.9em;">{technologies}</td>'
                html += '</tr>'
            
            html += '</table>'
            
            if len(live_hosts) > 25:
                html += f'<p><em>... and {len(live_hosts) - 25} more live host(s). View full HTML report for complete list.</em></p>'
        
        if dead_hosts:
            dead_count = len(dead_hosts)
            html += f'<h4>Dead Hosts ({dead_count})</h4>'
            if dead_count <= 50:
                html += '<p style="font-family: monospace; font-size: 0.9em; line-height: 1.6;">'
                html += ', '.join(dead_hosts)
                html += '</p>'
            else:
                html += '<p style="font-family: monospace; font-size: 0.9em; line-height: 1.6;">'
                html += ', '.join(dead_hosts[:50])
                html += f'</p><p><em>... and {dead_count - 50} more dead hosts. View full HTML report for complete list.</em></p>'
        
        html += '</div>'
        
        return html

    def get_dry_run_info(self, target, output_dir):
        """
        Return information about what related_sites would execute.
        This plugin runs TWO commands in sequence.
        """
        apex_domain = self._extract_apex_domain(target)
        scan_target = apex_domain if self._should_scan_apex(target, apex_domain) else target
        
        # Command 1: Subfinder
        subfinder_output = os.path.join(output_dir, "related_sites_subfinder.json")
        subfinder_cmd = [
            "subfinder",
            "-d", scan_target,
            "-o", subfinder_output,
            "-json",
            "-silent"
        ]
        
        # Command 2: HTTPx  
        httpx_input = os.path.join(output_dir, "related_sites_targets.txt")
        httpx_output = os.path.join(output_dir, "related_sites_httpx.json")
        httpx_cmd = [
            "httpx",
            "-l", httpx_input,
            "-json",
            "-o", httpx_output,
            "-silent",
            "-timeout", str(self.httpx_timeout),
            "-retries", "2",
            "-threads", str(self.httpx_threads),
            "-rate-limit", str(self.httpx_rate_limit),
            "-ports", ",".join(map(str, self.httpx_ports)),
            "-follow-redirects",
            "-status-code",
            "-title",
            "-tech-detect",
            "-websocket",
            "-cdn"
        ]
        
        operations_desc = (
            f"1. Subdomain enumeration for {scan_target}\n"
            f"2. HTTP probing discovered subdomains on ports: {','.join(map(str, self.httpx_ports))}"
        )
        
        return {
            "commands": [' '.join(subfinder_cmd), ' '.join(httpx_cmd)],
            "description": self.description,
            "operations": operations_desc
        }
