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

class RelatedSitesPlugin(KastPlugin):
    priority = 45  # After initial recon, before deep analysis
    
    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "related_sites"
        self.display_name = "Related Sites Discovery"
        self.description = "Discovers related subdomains and probes for live web services"
        self.website_url = "https://github.com/mercutioviz/kast"
        self.scan_type = "active"  # Makes HTTP requests
        self.output_type = "file"
        self.command_executed = {
            "subfinder": None,
            "httpx": None
        }

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
        try:
            import tldextract
            extracted = tldextract.extract(fqdn)
            apex = f"{extracted.domain}.{extracted.suffix}"
            self.debug(f"Extracted apex domain '{apex}' from '{fqdn}'")
            return apex
        except ImportError:
            self.debug("tldextract not available, using fallback method")
            # Simple fallback: take last 2 segments
            # Note: This fails on multi-part TLDs like .co.uk
            parts = fqdn.split('.')
            if len(parts) >= 2:
                return '.'.join(parts[-2:])
            return fqdn

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
                timeout=300  # 5 minute timeout
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
            self.debug("Subfinder timed out after 300 seconds")
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
        
        output_file = os.path.join(output_dir, "related_sites_httpx.json")
        
        # Get rate limit from CLI args (default 10 if not specified)
        rate_limit = getattr(self.cli_args, 'httpx_rate_limit', 10)
        self.debug(f"Using httpx rate limit: {rate_limit} requests/second")
        
        # Configure httpx command
        cmd = [
            "httpx",
            "-l", input_file,           # Input list
            "-json",                     # JSON output
            "-o", output_file,          # Output file
            "-silent",                   # Reduce noise
            "-timeout", "10",            # 10 second timeout per host
            "-retries", "2",             # Retry failed requests
            "-threads", "50",            # Parallel requests
            "-rate-limit", str(rate_limit),  # Rate limit requests/second
            "-ports", "80,443,8080,8443,8000,8888",  # Common web ports
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
        
        :param output_file: Path to httpx JSON output
        :param all_subdomains: List of all subdomains that were probed
        :return: Dict with categorized results
        """
        results = {
            "live_hosts": [],
            "dead_hosts": [],
            "by_status": {},
            "by_port": {},
            "technologies": {},
            "redirects": [],
            "with_cdn": [],
            "websockets": []
        }
        
        if not os.path.exists(output_file):
            self.debug(f"HTTPx output file not found: {output_file}")
            results["dead_hosts"] = all_subdomains
            return results
        
        # Parse httpx JSON Lines output
        live_hosts_set = set()
        
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        url = data.get('url', '')
                        host = data.get('host', '')
                        port = data.get('port', 0)
                        status_code = data.get('status_code', 0)
                        title = data.get('title', '')
                        tech = data.get('tech', [])
                        cdn = data.get('cdn', '')
                        websocket = data.get('websocket', False)
                        
                        # Track live host
                        live_hosts_set.add(host)
                        
                        host_info = {
                            "url": url,
                            "host": host,
                            "port": port,
                            "status_code": status_code,
                            "title": title,
                            "technologies": tech if isinstance(tech, list) else [],
                            "cdn": cdn,
                            "websocket": websocket
                        }
                        
                        results["live_hosts"].append(host_info)
                        
                        # Categorize by status code
                        if status_code not in results["by_status"]:
                            results["by_status"][status_code] = []
                        results["by_status"][status_code].append(host_info)
                        
                        # Categorize by port
                        if port not in results["by_port"]:
                            results["by_port"][port] = []
                        results["by_port"][port].append(host_info)
                        
                        # Track technologies
                        for t in tech if isinstance(tech, list) else []:
                            if t not in results["technologies"]:
                                results["technologies"][t] = []
                            results["technologies"][t].append(host)
                        
                        # Track CDN usage
                        if cdn:
                            results["with_cdn"].append(host_info)
                        
                        # Track websockets
                        if websocket:
                            results["websockets"].append(host_info)
                        
                        # Track redirects (3xx status codes)
                        if 300 <= status_code < 400:
                            results["redirects"].append(host_info)
                            
                    except json.JSONDecodeError as e:
                        self.debug(f"Failed to parse HTTPx line: {line}, error: {e}")
                        continue
        except Exception as e:
            self.debug(f"Error reading HTTPx output: {e}")
        
        # Determine dead hosts (subdomains that didn't respond)
        results["dead_hosts"] = [h for h in all_subdomains if h not in live_hosts_set]
        
        self.debug(f"HTTPx found {len(results['live_hosts'])} live host(s), "
                  f"{len(results['dead_hosts'])} dead host(s)")
        
        return results

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
        
        # Step 4: Aggregate results
        final_results = {
            "target": target,
            "apex_domain": apex_domain,
            "scanned_domain": scan_target,
            "total_subdomains": len(subdomains),
            "subdomains": subdomains,
            "live_hosts": probe_results["live_hosts"],
            "dead_hosts": probe_results["dead_hosts"],
            "by_status": probe_results["by_status"],
            "by_port": probe_results["by_port"],
            "technologies": probe_results["technologies"],
            "redirects": probe_results["redirects"],
            "with_cdn": probe_results["with_cdn"],
            "websockets": probe_results["websockets"],
            "statistics": {
                "total_discovered": len(subdomains),
                "total_live": len(probe_results["live_hosts"]),
                "total_dead": len(probe_results["dead_hosts"]),
                "response_rate": (len(probe_results["live_hosts"]) / len(subdomains) * 100) if len(subdomains) > 0 else 0,
                "unique_technologies": len(probe_results["technologies"]),
                "cdn_protected": len(probe_results["with_cdn"]),
                "websocket_enabled": len(probe_results["websockets"]),
                "redirects_count": len(probe_results["redirects"])
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
        findings = raw_output if isinstance(raw_output, dict) else {}
        
        self.debug(f"{self.name} processing findings")
        
        # Generate components
        summary = self._generate_summary(findings)
        exec_summary = self._generate_executive_summary(findings)
        details = self._generate_details(findings)
        issues = self._identify_issues(findings)
        custom_html = self._generate_custom_html(findings)
        custom_html_pdf = self._generate_pdf_html(findings)
        
        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": self.display_name,
            "plugin-website-url": self.website_url,
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "summary": summary,
            "details": details,
            "issues": issues,
            "executive_summary": exec_summary,
            "custom_html": custom_html,
            "custom_html_pdf": custom_html_pdf,
            "commands_executed": self.command_executed
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
        
        # Highlight interesting findings
        by_status = findings.get("by_status", {})
        if 200 in by_status:
            summary_points.append(f"{len(by_status[200])} subdomain(s) with active web servers (200 OK)")
        
        redirects = findings.get("redirects", [])
        if redirects:
            summary_points.append(f"{len(redirects)} subdomain(s) configured with redirects")
        
        cdn_hosts = findings.get("with_cdn", [])
        if cdn_hosts:
            summary_points.append(f"{len(cdn_hosts)} subdomain(s) using CDN protection")
        
        websockets = findings.get("websockets", [])
        if websockets:
            summary_points.append(f"{len(websockets)} subdomain(s) supporting WebSocket connections")
        
        tech = findings.get("technologies", {})
        if tech:
            top_techs = sorted(tech.items(), key=lambda x: len(x[1]), reverse=True)[:3]
            tech_summary = ", ".join([f"{name} ({len(hosts)})" for name, hosts in top_techs])
            summary_points.append(f"Most common technologies: {tech_summary}")
        
        return summary_points

    def _generate_details(self, findings):
        """Generate detailed findings text."""
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
        lines.append("")
        
        by_status = findings.get("by_status", {})
        if by_status:
            lines.append("Response by Status Code:")
            for status, hosts in sorted(by_status.items()):
                lines.append(f"  {status}: {len(hosts)} host(s)")
            lines.append("")
        
        by_port = findings.get("by_port", {})
        if by_port:
            lines.append("Response by Port:")
            for port, hosts in sorted(by_port.items()):
                lines.append(f"  {port}: {len(hosts)} host(s)")
            lines.append("")
        
        technologies = findings.get("technologies", {})
        if technologies:
            lines.append(f"Technologies Detected: {len(technologies)}")
            for tech, hosts in sorted(technologies.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
                lines.append(f"  {tech}: {len(hosts)} host(s)")
            lines.append("")
        
        if stats.get('cdn_protected', 0) > 0:
            lines.append(f"CDN Protected Hosts: {stats['cdn_protected']}")
        
        if stats.get('websocket_enabled', 0) > 0:
            lines.append(f"WebSocket Enabled Hosts: {stats['websocket_enabled']}")
        
        if stats.get('redirects_count', 0) > 0:
            lines.append(f"Redirects Configured: {stats['redirects_count']}")
        
        return "\n".join(lines)

    def _identify_issues(self, findings):
        """Identify security issues from findings."""
        issues = []
        
        # This plugin is primarily for discovery
        # Issues would be identified by other plugins analyzing the discovered hosts
        # For now, return empty list
        
        return issues

    def _generate_custom_html(self, findings):
        """Generate custom HTML widget for interactive report display."""
        stats = findings.get("statistics", {})
        live_hosts = findings.get("live_hosts", [])
        
        if not live_hosts:
            return "<p>No live hosts discovered.</p>"
        
        # Group by status code for display
        by_status = findings.get("by_status", {})
        
        html = f'''
        <div class="related-sites-widget">
            <div class="stats-summary">
                <div class="stat-card">
                    <div class="stat-value">{stats.get("total_discovered", 0)}</div>
                    <div class="stat-label">Subdomains</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get("total_live", 0)}</div>
                    <div class="stat-label">Live Hosts</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get("response_rate", 0):.1f}%</div>
                    <div class="stat-label">Response Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get("unique_technologies", 0)}</div>
                    <div class="stat-label">Technologies</div>
                </div>
            </div>
            
            <div class="hosts-container">
                <h4>Live Hosts by Status Code</h4>
        '''
        
        # Display hosts grouped by status code
        for status, hosts in sorted(by_status.items(), key=lambda x: x[0]):
            status_class = "status-success" if 200 <= status < 300 else "status-redirect" if 300 <= status < 400 else "status-error"
            
            html += f'''
                <div class="status-group">
                    <div class="status-header" onclick="toggleStatusGroup('status-{status}')">
                        <span class="status-code {status_class}">{status}</span>
                        <span class="host-count">{len(hosts)} host(s)</span>
                        <span class="toggle-icon">▼</span>
                    </div>
                    <div class="status-content" id="status-{status}" style="display: none;">
            '''
            
            for host_info in hosts[:50]:  # Limit display
                url = host_info.get('url', '')
                title = host_info.get('title', 'No title')
                tech = host_info.get('technologies', [])
                cdn = host_info.get('cdn', '')
                
                html += f'''
                    <div class="host-item">
                        <div class="host-url"><a href="{url}" target="_blank">{url}</a></div>
                        <div class="host-title">{title}</div>
                '''
                
                if tech:
                    html += f'<div class="host-tech">🔧 {", ".join(tech[:5])}</div>'
                if cdn:
                    html += f'<div class="host-cdn">🛡️ CDN: {cdn}</div>'
                
                html += '</div>'
            
            if len(hosts) > 50:
                html += f'<div class="more-hosts">... and {len(hosts) - 50} more</div>'
            
            html += '''
                    </div>
                </div>
            '''
        
        html += '''
            </div>
        </div>
        
        <script>
        function toggleStatusGroup(groupId) {
            const content = document.getElementById(groupId);
            const header = content.previousElementSibling;
            const icon = header.querySelector('.toggle-icon');
            
            if (content.style.display === 'none') {
                content.style.display = 'block';
                icon.style.transform = 'rotate(180deg)';
            } else {
                content.style.display = 'none';
                icon.style.transform = 'rotate(0deg)';
            }
        }
        </script>
        
        <style>
        .related-sites-widget {
            margin: 1em 0;
        }
        
        .stats-summary {
            display: flex;
            gap: 1em;
            margin-bottom: 2em;
            flex-wrap: wrap;
        }
        
        .stat-card {
            flex: 1;
            min-width: 150px;
            padding: 1em;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 8px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 0.25em;
        }
        
        .stat-label {
            font-size: 0.9em;
            opacity: 0.9;
        }
        
        .hosts-container h4 {
            color: #075985;
            margin-bottom: 1em;
        }
        
        .status-group {
            margin-bottom: 1em;
            border: 1px solid #e6eef6;
            border-radius: 4px;
            overflow: hidden;
        }
        
        .status-header {
            display: flex;
            align-items: center;
            padding: 1em;
            background: #f8fbfd;
            cursor: pointer;
            user-select: none;
        }
        
        .status-header:hover {
            background: #e6f0fa;
        }
        
        .status-code {
            font-weight: bold;
            padding: 0.25em 0.75em;
            border-radius: 4px;
            margin-right: 1em;
        }
        
        .status-success {
            background: #dcfce7;
            color: #166534;
        }
        
        .status-redirect {
            background: #fef3c7;
            color: #92400e;
        }
        
        .status-error {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .host-count {
            flex: 1;
            color: #075985;
        }
        
        .toggle-icon {
            color: #075985;
            transition: transform 0.2s;
        }
        
        .status-content {
            padding: 1em;
            background: white;
        }
        
        .host-item {
            padding: 1em;
            margin-bottom: 0.5em;
            background: #f8fbfd;
            border-radius: 4px;
            border-left: 3px solid #075985;
        }
        
        .host-url a {
            color: #075985;
            font-weight: bold;
            text-decoration: none;
        }
        
        .host-url a:hover {
            text-decoration: underline;
        }
        
        .host-title {
            color: #666;
            font-size: 0.9em;
            margin-top: 0.25em;
        }
        
        .host-tech, .host-cdn {
            font-size: 0.85em;
            color: #666;
            margin-top: 0.25em;
        }
        
        .more-hosts {
            text-align: center;
            color: #666;
            font-style: italic;
            padding: 1em;
        }
        </style>
        '''
        
        return html

    def _generate_pdf_html(self, findings):
        """Generate PDF-friendly HTML output."""
        stats = findings.get("statistics", {})
        live_hosts = findings.get("live_hosts", [])
        
        html = '<div class="pdf-related-sites">'
        html += f'<p><strong>Total Subdomains:</strong> {stats.get("total_discovered", 0)}</p>'
        html += f'<p><strong>Live Hosts:</strong> {stats.get("total_live", 0)} ({stats.get("response_rate", 0):.1f}% response rate)</p>'
        
        if live_hosts:
            html += '<h4>Live Hosts (Top 25)</h4>'
            html += '<ul>'
            for host_info in live_hosts[:25]:
                url = host_info.get('url', '')
                status = host_info.get('status_code', 0)
                title = host_info.get('title', 'No title')
                html += f'<li><strong>{status}</strong> - <a href="{url}">{url}</a> - {title}</li>'
            html += '</ul>'
            
            if len(live_hosts) > 25:
                html += f'<p><em>... and {len(live_hosts) - 25} more host(s). View full HTML report for complete list.</em></p>'
        
        html += '</div>'
        
        return html
