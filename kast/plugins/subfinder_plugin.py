"""
File: plugins/subfinder_plugin.py
Description: Subdomain finder plugin for KAST.
"""

import subprocess
import shutil
import os
import json
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class SubfinderPlugin(KastPlugin):
    priority = 10  # Set plugin run order (lower runs earlier)
    
    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "subfinder"
        self.description = "Subdomain finder."
        self.display_name = "Subfinder"
        self.scan_type = "passive"  # or "active"
        self.output_type = "file"    # or "stdout"

    def is_available(self):
        """
        Check if required tool is installed and available in PATH.
        """
        return shutil.which("subfinder") is not None

    def run(self, target, output_dir, report_only):
        """
        Run the tool and return standardized result dict.
        """
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, "subfinder_tmp.json")
        cmd = [
            "subfinder",
            "-d", target,
            "-o", output_file,
            "-json"
        ]

        if getattr(self.cli_args, "verbose", False):
            cmd.insert(1, "-v")
            self.debug(f"Running command: {' '.join(cmd)}")

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
                if proc.returncode != 0:
                    return self.get_result_dict(
                        disposition="fail",
                        results=proc.stderr.strip()
                    )

            # Read JSON Lines format (one JSON object per line)
            results = []
            with open(output_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:  # Skip empty lines
                        try:
                            results.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            self.debug(f"Failed to parse line: {line}, error: {e}")
            
            # Write out as proper JSON array
            output_file = os.path.join(output_dir, "subfinder.json")
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)

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
        Normalize output, extract issues, and build executive_summary.
        """
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

        # Initialize issues and details
        issues = []
        details = ""

        summary = self._generate_summary(findings)
        executive_summary = self._generate_executive_summary(findings)
        self.debug(f"{self.name} summary: {summary}")
        self.debug(f"{self.name} issues: {issues}")
        self.debug(f"{self.name} details:\n{details}")

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": getattr(self, 'display_name', None),
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "summary": summary or f"{self.name} did not produce any findings",
            "details": details,
            "issues": issues,
            "executive_summary": executive_summary
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)

        return processed_path

    def _generate_summary(self, findings):
        """
        Generate a human-readable summary from subfinder findings.
        """
        self.debug(f"_generate_summary called with findings type: {type(findings)}")
        self.debug(f"_generate_summary findings content: {pformat(findings)}")
        
        results = findings.get("results", []) if isinstance(findings, dict) else []
        self.debug(f"{self.name} results: {pformat(results)}")
        
        if not results:
            self.debug("No results found, returning 'No subdomains were found.'")
            return "No subdomains were found."

        # Extract subdomain names from the 'host' field in each result entry
        detected_subdomains = [entry.get("host") for entry in results if entry.get("host")]

        self.debug(f"Detected subdomains: {pformat(detected_subdomains)}")

        if not detected_subdomains:
            self.debug("No subdomains detected, returning 'No subdomains detected'")
            return "No subdomains detected"

        subdomain_names = detected_subdomains
        summary_text = f"Detected {len(subdomain_names)} subdomain(s): {', '.join(subdomain_names)}"
        self.debug(f"Generated summary: {summary_text}")
        return summary_text

    def _generate_executive_summary(self, findings):
        """
        Generate a simple executive summary showing the count of subdomains detected.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        
        if not results:
            return "No subdomains detected."

        # Extract subdomain names from the 'host' field in each result entry
        detected_subdomains = [entry.get("host") for entry in results if entry.get("host")]
        
        count = len(detected_subdomains)
        
        if count == 0:
            return "No subdomains detected."
        elif count == 1:
            return "Detected 1 subdomain."
        else:
            return f"Detected {count} subdomains."
