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

    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "wafw00f"
        self.description = "Detects and identifies Web Application Firewalls (WAFs) on the target."
        self.scan_type = "passive"
        self.output_type = "file"

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
            "-f", "json",
            "-o", output_file
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

        # Initialize issues and details
        issues = []
        details = ""
        executive_summary = ""

        # Case 1: No WAF detected
        if not results or not any(r.get("detected", False) for r in results):
            issues = ["No WAF Detected"]
            details = "No WAF detected."
            executive_summary = "No WAFs were detected."

        # Case 2: Generic WAF detected
        elif any(r.get("firewall") == "Generic" for r in results):
            issues = ["WAF Check Inconclusive"]
            details = "A generic WAF was reported by wafw00f."
            executive_summary = "WAF detection was inconclusive."

        # Case 3: Specific WAF detected
        else:
            issues = []  # No issues if a specific WAF is found
            first = next((r for r in results if r.get("detected", False)), {})
            firewall = first.get("firewall", "Unknown")
            manufacturer = first.get("manufacturer", "Unknown")
            trigger_url = first.get("trigger_url", "N/A")

            # Format details as multi-line string
            details = (
                f"WAF Detected: {firewall}\n"
                f"Manufacturer: {manufacturer}\n"
                f"Test URL: {trigger_url}"
            )

            executive_summary = f"Detected WAF: {firewall}."

        summary = self._generate_summary(findings)
        self.debug(f"{self.name} summary: {summary}")
        self.debug(f"{self.name} issues: {issues}")
        self.debug(f"{self.name} details:\n{details}")

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
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