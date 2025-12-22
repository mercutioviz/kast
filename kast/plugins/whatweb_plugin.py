"""
File: plugins/whatweb_plugin.py
Description: Plugin for running WhatWeb as part of KAST.
"""

import subprocess
import shutil
import json
import os
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat
from collections import defaultdict
from urllib.parse import urlparse, urlunparse

class WhatWebPlugin(KastPlugin):
    priority = 15  # High priority (lower number = higher priority)
    
    # Configuration schema for kast-web integration
    config_schema = {
        "type": "object",
        "title": "WhatWeb Configuration",
        "description": "Web technology detection configuration",
        "properties": {
            "aggression_level": {
                "type": "integer",
                "default": 3,
                "minimum": 1,
                "maximum": 4,
                "description": "Aggression level (1=stealthy, 3=aggressive, 4=heavy)"
            },
            "timeout": {
                "type": "integer",
                "default": 30,
                "minimum": 5,
                "maximum": 120,
                "description": "HTTP request timeout in seconds"
            },
            "user_agent": {
                "type": ["string", "null"],
                "default": None,
                "description": "Custom User-Agent string (null for default)"
            },
            "follow_redirects": {
                "type": "integer",
                "default": 2,
                "minimum": 0,
                "maximum": 10,
                "description": "Maximum redirect depth to follow"
            }
        }
    }

    def __init__(self, cli_args, config_manager=None):
        # IMPORTANT: Set plugin name BEFORE calling super().__init__()
        # so that schema registration uses the correct plugin name
        self.name = "whatweb"
        self.display_name = "WhatWeb"
        self.description = "Identifies technologies used by a website."
        self.website_url = "https://github.com/urbanadventurer/whatweb"
        self.scan_type = "passive"
        self.output_type = "file"
        
        # Now call parent init (this will register our schema under correct name)
        super().__init__(cli_args, config_manager)
        
        self.command_executed = None  # Store the command for reporting
        
        # Load configuration values
        self._load_plugin_config()
    
    def _load_plugin_config(self):
        """Load configuration with defaults from schema."""
        # Get config values (defaults from schema if not set)
        self.aggression_level = self.get_config('aggression_level', 3)
        self.timeout = self.get_config('timeout', 30)
        self.user_agent = self.get_config('user_agent', None)
        self.follow_redirects = self.get_config('follow_redirects', 2)
        
        self.debug(f"WhatWeb config loaded: aggression={self.aggression_level}, "
                  f"timeout={self.timeout}, "
                  f"user_agent={'(custom)' if self.user_agent else '(default)'}, "
                  f"follow_redirects={self.follow_redirects}")

    def is_available(self):
        """
        Check if WhatWeb is installed and available in PATH.
        """
        return shutil.which("whatweb") is not None

    def setup(self):
        """
        Optional pre-run setup. Nothing required for WhatWeb currently.
        """
        pass

    def run(self, target, output_dir, report_only):
        """
        Run WhatWeb against the target and save output to a file.
        Returns a result dictionary.
        """
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, "whatweb.json")
        
        # Build command dynamically based on configuration
        cmd = ["whatweb"]
        
        # Add aggression level
        cmd.extend(["-a", str(self.aggression_level)])
        
        # Add timeout if configured
        if self.timeout:
            cmd.extend(["--max-http-scan-time", str(self.timeout)])
        
        # Add custom user-agent if configured
        if self.user_agent:
            cmd.extend(["--user-agent", self.user_agent])
        
        # Add redirect follow depth
        if self.follow_redirects:
            cmd.extend(["--max-redirects", str(self.follow_redirects)])
        
        # Add output file and target (target must come LAST)
        cmd.extend(["--log-json", output_file, target])

        if getattr(self.cli_args, "verbose", False):
            self.debug(f"Running command: {' '.join(cmd)}")

        # Store command for reporting
        self.command_executed = ' '.join(cmd)

        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="WhatWeb is not installed or not found in PATH.",
                timestamp=timestamp
            )

        try:
            if report_only:
                self.debug(f"[REPORT ONLY] Would run command: {' '.join(cmd)}")

            else:    
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    return self.get_result_dict(
                        disposition="fail",
                        results=proc.stderr.strip()
                    )

            # Read the output file
            with open(output_file, "r") as f:
                results = json.load(f)

            return self.get_result_dict(
                disposition="success",
                results=results,
                timestamp=timestamp
            )

        except Exception as e:
            return self.get_result_dict(
                disposition="fail",
                results=str(e),
                timestamp=timestamp
            )

    def post_process(self, raw_output, output_dir):
        """
        Post-process WhatWeb output into standardized structure.
        Handles both successful findings and failure cases gracefully.
        """
        # Handle failure cases from run() method
        if isinstance(raw_output, dict) and raw_output.get('disposition') == 'fail':
            # This is a failed run result, not actual findings
            error_message = raw_output.get('results', 'Unknown error')
            self.debug(f"{self.name} failed during execution: {error_message}")
            
            # Return a minimal processed result for failures
            processed = {
                "plugin-name": self.name,
                "plugin-description": self.description,
                "plugin-display-name": getattr(self, 'display_name', None),
                "plugin-website-url": getattr(self, 'website_url', None),
                "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
                "findings": {"disposition": "fail", "results": error_message},
                "summary": [{"Error": f"Plugin execution failed: {error_message}"}],
                "details": "",
                "issues": [],
                "executive_summary": "",
                "report": self._format_command_for_report()
            }
            
            processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
            with open(processed_path, "w") as f:
                json.dump(processed, f, indent=2)
            return processed_path
        
        # Handle successful findings
        if isinstance(raw_output, str) and os.path.isfile(raw_output):
            with open(raw_output, "r") as f:
                findings = json.load(f)
        elif isinstance(raw_output, dict):
            findings = raw_output
        else:
            try:
                findings = json.loads(raw_output)
            except Exception:
                findings = {}

        self.debug(f"{self.name} raw findings:\n {pformat(findings)}")

        # Initialize issues and details
        issues = []
        details = ""
        executive_summary = ""

        # Detect domain redirects and generate recommendations
        redirect_recommendations = self._detect_domain_redirects(findings)
        if redirect_recommendations:
            executive_summary = "\n".join(redirect_recommendations)

        # Format command for report notes
        report_notes = self._format_command_for_report()

        # Properly structure the findings
        structured_findings = {
            "disposition": "success" if findings else "fail",
            "results": findings
        }

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": getattr(self, 'display_name', None),
            "plugin-website-url": getattr(self, 'website_url', None),
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": structured_findings,
            "summary": self._generate_summary(findings),
            "details": details,
            "issues": issues,
            "executive_summary": executive_summary,
            "report": report_notes
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)
        return processed_path

    def _detect_domain_redirects(self, findings):
        """
        Detect redirects that change the domain name (not just protocol changes).
        Returns a list of recommendation strings for the executive summary.
        """
        recommendations = []
        
        # Handle both list and dict formats
        if isinstance(findings, list):
            results = findings
        elif isinstance(findings, dict):
            results = findings.get("results", [])
        else:
            results = []
        
        # Track redirects we've already seen to avoid duplicates
        seen_redirects = set()
        
        for entry in results:
            # Check if this is a redirect (301 or 302)
            http_status = entry.get("http_status")
            if http_status not in [301, 302]:
                continue
            
            # Get the target and redirect location
            target = entry.get("target", "")
            plugins = entry.get("plugins", {})
            redirect_location = plugins.get("RedirectLocation", {}).get("string", [])
            
            if not redirect_location:
                continue
            
            # RedirectLocation string is typically a list with one element
            redirect_url = redirect_location[0] if isinstance(redirect_location, list) else redirect_location
            
            # Parse both URLs to extract domains
            try:
                target_parsed = urlparse(target)
                redirect_parsed = urlparse(redirect_url)
                
                target_domain = target_parsed.netloc.lower()
                redirect_domain = redirect_parsed.netloc.lower()
                
                # Skip if domains are the same (e.g., just http->https redirect)
                if target_domain == redirect_domain:
                    continue
                
                # Create a unique key for this redirect pair
                redirect_key = (target_domain, redirect_domain)
                if redirect_key in seen_redirects:
                    continue
                
                seen_redirects.add(redirect_key)
                
                # Generate recommendation
                recommendation = (
                    f"Recommend running a scan on {redirect_domain}, which was the "
                    f"target redirection location from {target_domain}"
                )
                recommendations.append(recommendation)
                
            except Exception as e:
                self.debug(f"Error parsing redirect URLs: {e}")
                continue
        
        return recommendations

    def _format_command_for_report(self):
        """
        Format the executed command for the report notes section.
        Returns HTML-formatted command with dark blue color and monospace font.
        """
        if not self.command_executed:
            return "Command not available"
        
        return f'<code style="color: #00008B; font-family: Consolas, \'Courier New\', monospace;">{self.command_executed}</code>'

    def _generate_summary(self, findings):
            """
            Generate a JSON-array summary from WhatWeb JSON output.
            Each entry in the returned list is a single-key dict where
            the key is "<target> - HTTP <status>" and the value is
            a semicolon-delimited list of detected technologies.
            """
            # Ensure we have a list of results
            results = findings.get("results") if isinstance(findings, dict) else None
            if not results or not isinstance(results, list):
                return [{"No findings": f"No findings were produced by {self.name}." }]

            # Bucket entries by normalized target URL
            from collections import defaultdict
            from urllib.parse import urlparse, urlunparse

            buckets = defaultdict(list)
            for entry in results:
                raw_target = entry.get("target", "unknown")
                parsed = urlparse(raw_target)
                # Strip trailing slash from path
                path = parsed.path.rstrip("/")
                normalized = urlunparse(parsed._replace(path=path))
                buckets[normalized].append(entry)

            summary_list = []
            for target, entries in buckets.items():
                for idx, entry in enumerate(entries, start=1):
                    status = entry.get("http_status", "N/A")
                    plugins = entry.get("plugins", {})
                    tech_list = []

                    for plugin_name, data in plugins.items():
                        if not data:
                            continue
                        if "version" in data and data["version"]:
                            versions = ", ".join(data["version"])
                            tech_list.append(f"{plugin_name} (v{versions})")
                        elif "string" in data and data["string"]:
                            examples = ", ".join(data["string"])
                            tech_list.append(f"{plugin_name} [{examples}]")
                        else:
                            tech_list.append(plugin_name)

                    techs = "; ".join(tech_list) if tech_list else "no detectable technologies"

                    # If multiple entries share the same target, number them
                    label = target if len(entries) == 1 else f"{target} (#{idx})"
                    key = f"{label} - HTTP {status}"
                    summary_list.append({key: techs})

            return summary_list

    def get_dry_run_info(self, target, output_dir):
        """
        Return information about what WhatWeb would execute.
        Builds the actual command with current configuration.
        """
        output_file = os.path.join(output_dir, "whatweb.json")
        
        # Build command with current configuration (same as run() method)
        cmd = ["whatweb"]
        
        # Add aggression level
        cmd.extend(["-a", str(self.aggression_level)])
        
        # Add timeout if configured
        if self.timeout:
            cmd.extend(["--max-http-scan-time", str(self.timeout)])
        
        # Add custom user-agent if configured
        if self.user_agent:
            cmd.extend(["--user-agent", self.user_agent])
        
        # Add redirect follow depth
        if self.follow_redirects:
            cmd.extend(["--max-redirects", str(self.follow_redirects)])
        
        # Add output file and target (target must come LAST)
        cmd.extend(["--log-json", output_file, target])
        
        # Build operations description with config values
        operations_desc = (
            f"Technology detection (aggression level {self.aggression_level}, "
            f"timeout {self.timeout}s, max redirects {self.follow_redirects})"
        )
        
        return {
            "commands": [' '.join(cmd)],
            "description": self.description,
            "operations": operations_desc
        }
