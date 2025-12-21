"""
File: plugins/wafw00f_plugin.py
Description: Plugin for running wafw00f as part of KAST.
"""

import subprocess
import shutil
import json
import os
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class Wafw00fPlugin(KastPlugin):
    priority = 10  # High priority (lower number = higher priority)

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self.name = "wafw00f"
        self.display_name = "Wafw00f"
        self.description = "Detects and identifies Web Application Firewalls (WAFs) on the target."
        self.website_url = "https://github.com/EnableSecurity/wafw00f"
        self.scan_type = "passive"
        self.output_type = "file"
        self.command_executed = None  # Store the command for reporting

    def setup(self, target, output_dir):
        """
        Optional setup step before the run.
        You could add logic here to validate target, pre-create dirs, etc.
        """
        self.debug("Setup completed.")

    def is_available(self):
        """
        Check if wafw00f is installed and available in PATH.
        """
        return shutil.which("wafw00f") is not None

    def run(self, target, output_dir, report_only):
        """
        Run wafw00f against the target and save output to a file.
        Returns a standardized result dictionary.
        """
        self.setup(target, output_dir)
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, "wafw00f.json")
        cmd = [
            "wafw00f",
            target,
            "-a",
            "-vvv",
            "-f", "json",
            "-o", output_file
        ]

        if getattr(self.cli_args, "verbose", False):
            #cmd.insert(1, "-v")
            self.debug(f"Running command: {' '.join(cmd)}")

        # Store command for reporting
        self.command_executed = ' '.join(cmd)

        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="wafw00f is not installed or not found in PATH.",
                timestamp=timestamp
            )

        try:
            if report_only:
                self.debug(f"[REPORT ONLY] Would run command: {' '.join(cmd)}")

            else:    
                proc = subprocess.run(cmd, capture_output=True, text=True)
                
                # Save STDOUT/STDERR to file
                stdout_file = os.path.join(output_dir, "wafw00f_stdout.txt")
                combined_output = ""
                if proc.stdout:
                    combined_output += "=== STDOUT ===\n" + proc.stdout + "\n"
                if proc.stderr:
                    combined_output += "=== STDERR ===\n" + proc.stderr + "\n"
                
                with open(stdout_file, "w") as f:
                    f.write(combined_output)
                
                # Check for TLS version error in STDERR
                tls_error_detected = False
                if proc.stderr:
                    for line in proc.stderr.split('\n'):
                        if line.startswith("ERROR:") and "TLSV1_ALERT_PROTOCOL_VERSION" in line:
                            tls_error_detected = True
                            self.debug("TLS version error detected, will retry with HTTP")
                            break
                
                # If TLS error detected, retry with HTTP
                if tls_error_detected:
                    # Rename the error output file
                    error_stdout_file = os.path.join(output_dir, "wafw00f_stdout_error.txt")
                    os.rename(stdout_file, error_stdout_file)
                    self.debug(f"Renamed {stdout_file} to {error_stdout_file}")
                    
                    # Modify target to use HTTP instead of HTTPS
                    http_target = target.replace("https://", "http://")
                    if not http_target.startswith("http://"):
                        http_target = "http://" + http_target
                    
                    self.debug(f"Retrying with HTTP target: {http_target}")
                    
                    # Update command with HTTP target
                    http_cmd = [
                        "wafw00f",
                        http_target,
                        "-a",
                        "-vvv",
                        "-f", "json",
                        "-o", output_file
                    ]
                    
                    if getattr(self.cli_args, "verbose", False):
                        self.debug(f"Running HTTP command: {' '.join(http_cmd)}")
                    
                    # Run wafw00f with HTTP
                    # Create empty output_file first, so that kast-web knows we are running
                    open(output_file, 'a').close()
                    proc = subprocess.run(http_cmd, capture_output=True, text=True)
                    
                    # Save new STDOUT/STDERR to wafw00f_stdout.txt
                    combined_output = ""
                    if proc.stdout:
                        combined_output += "=== STDOUT ===\n" + proc.stdout + "\n"
                    if proc.stderr:
                        combined_output += "=== STDERR ===\n" + proc.stderr + "\n"
                    
                    with open(stdout_file, "w") as f:
                        f.write(combined_output)
                
                if proc.returncode != 0:
                    return self.get_result_dict(
                        disposition="fail",
                        results=proc.stderr.strip()
                    )

            with open(output_file, "r") as f:
                results = json.load(f)

            return self.get_result_dict(
                disposition="success",
                results=results
            )

        except Exception as e:
            return self.get_result_dict(
                disposition="fail",
                results=str(e)
            )

    def post_process(self, raw_output, output_dir):
        """
        Clean up and normalize wafw00f output.
        Adds 'details' and 'issues' fields based on detection results.
        """
        # Handle the case where raw_output is a result dict with disposition='fail'
        if isinstance(raw_output, dict) and raw_output.get('disposition') == 'fail':
            # Plugin failed, create a minimal processed output
            error_message = raw_output.get('results', 'Unknown error')
            processed = {
                "plugin-name": self.name,
                "plugin-description": self.description,
                "plugin-display-name": getattr(self, 'display_name', None),
                "timestamp": raw_output.get('timestamp', datetime.utcnow().isoformat(timespec="milliseconds")),
                "findings": {},
                "summary": f"Plugin failed: {error_message}",
                "details": f"The {self.name} plugin encountered an error: {error_message}",
                "issues": [],
                "executive_summary": f"Plugin failed to execute."
            }
            
            processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
            with open(processed_path, "w") as f:
                json.dump(processed, f, indent=2)
            
            return processed_path
        
        # Load input if path to a file
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

        self.debug(f"{self.name} raw findings:\n{pformat(findings)}")

        # Remove generic WAF entries if more specific ones exist
        if 'results' in findings and isinstance(findings['results'], list):
            waf_results = findings['results']
            if len(waf_results) > 1 and any(r.get('firewall') == 'Generic' for r in waf_results):
                findings['results'] = [r for r in waf_results if r.get('firewall') != 'Generic']
                self.debug("Removed Generic WAF entries from findings.")

        results = findings.get("results", []) if isinstance(findings, dict) else []

        # Extract test URLs from wafw00f_stdout.txt
        test_urls = []
        stdout_file = os.path.join(output_dir, "wafw00f_stdout.txt")
        if os.path.exists(stdout_file):
            try:
                with open(stdout_file, "r") as f:
                    for line in f:
                        if line.startswith("DEBUG:urllib3.connectionpool:") and "GET /?" in line:
                            # Extract the URL from the line
                            # Format: DEBUG:urllib3.connectionpool:http://example.com:80 "GET /?param=value HTTP/1.1" 302 0
                            parts = line.split('"')
                            if len(parts) >= 2:
                                # Get the part with "GET /? ..."
                                get_part = parts[1]
                                # Extract just the path with query string
                                if get_part.startswith("GET "):
                                    url_path = get_part.split()[1]  # Get the second part (the URL path)
                                    test_urls.append(url_path)
                self.debug(f"Extracted {len(test_urls)} test URLs from wafw00f_stdout.txt")
            except Exception as e:
                self.debug(f"Error reading wafw00f_stdout.txt: {e}")

        # Initialize issues and details
        issues = []
        details = ""
        executive_summary = ""

        # Case 1: No WAF detected
        if not results or not any(r.get("detected", False) for r in results):
            issues = ["No WAF Detected"]
            details = "No WAF detected."
            
            # Add test URLs if any were found
            if test_urls:
                details += "\n"
                for test_url in test_urls:
                    details += f"Test URL: {test_url}\n"
                # Remove trailing newline
                details = details.rstrip('\n')
            
            executive_summary = "No WAFs were detected."

        # Case 2: Generic WAF detected
        elif any(r.get("firewall") == "Generic" for r in results):
            issues = ["WAF Check Inconclusive"]
            details = "A generic WAF was reported by wafw00f."
            
            # Add test URLs if any were found
            if test_urls:
                details += "\n"
                for test_url in test_urls:
                    details += f"Test URL: {test_url}\n"
                # Remove trailing newline
                details = details.rstrip('\n')
            
            executive_summary = "WAF detection was inconclusive."

        # Case 3: Specific WAF detected
        else:
            issues = []  # No issues if a specific WAF is found
            first = next((r for r in results if r.get("detected", False)), {})
            firewall = first.get("firewall", "Unknown")
            manufacturer = first.get("manufacturer", "Unknown")
            trigger_url = first.get("trigger_url", "N/A")

            # Format details as multi-line string
            details = f"<b>WAF Detected:</b> {firewall}\n"
            details += f"<b>Manufacturer:</b> {manufacturer}\n"
            
            # Add test URLs if any were found
            for test_url in test_urls:
                details += f"<b>Test URL:</b> {test_url}\n"
            
            # Add trigger URL
            details += f"<b>Trigger URL:</b> {trigger_url}"

            executive_summary = f"Detected WAF: {firewall}."

        summary = self._generate_summary(findings)
        self.debug(f"{self.name} summary: {summary}")
        self.debug(f"{self.name} issues: {issues}")
        self.debug(f"{self.name} details:\n{details}")

        # Format command for report notes
        report_notes = self._format_command_for_report()

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": getattr(self, 'display_name', None),
            "plugin-website-url": getattr(self, 'website_url', None),
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "summary": summary or f"{self.name} did not produce any findings",
            "details": details,
            "issues": issues,
            "executive_summary": executive_summary,
            "report": report_notes
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)

        return processed_path


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
        Generate a human-readable summary from wafw00f findings.
        """
        self.debug(f"_generate_summary called with findings type: {type(findings)}")
        self.debug(f"_generate_summary findings content: {pformat(findings)}")
        
        results = findings.get("results", []) if isinstance(findings, dict) else []
        self.debug(f"{self.name} results: {pformat(results)}")
        
        if not results:
            self.debug("No results found, returning 'No WAFs were detected.'")
            return "No WAFs were detected."

        # Filter for actually detected WAFs (where detected=True and firewall is not "None")
        detected_wafs = [
            entry for entry in results 
            if entry.get("detected", False) and entry.get("firewall", "None") != "None"
        ]
        
        self.debug(f"Detected WAFs after filtering: {pformat(detected_wafs)}")
        
        if not detected_wafs:
            self.debug("No WAFs detected, returning 'No WAF detected'")
            return "No WAF detected"
        
        waf_names = [entry.get("firewall", "Unknown") for entry in detected_wafs]
        summary_text = f"Detected {len(waf_names)} WAF(s): {', '.join(waf_names)}"
        self.debug(f"Generated summary: {summary_text}")
        return summary_text
