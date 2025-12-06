"""
File: plugins/ftap_plugin.py
Description: KAST plugin for Find The Admin Panel

TODO: Customize the following sections:
  1. Command structure in run() method
  2. Output parsing in post_process() method
  3. Issue extraction logic
  4. Executive summary generation
  5. Update _generate_summary() if needed
"""

import subprocess
import shutil
import json
import os
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class FtapPlugin(KastPlugin):
    priority = 50  # Set plugin run order (lower runs earlier)

    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "ftap"
        self.display_name = "Find The Admin Panel"  # Human-readable name for reports
        self.description = "Scans target for exposed admin login pages"
        self.website_url = "https://github.com/DV64/Find-The-Admin-Panel"  # Replace with actual website
        self.description = "Scans target for exposed admin login pages"
        self.scan_type = "passive"  # or "active"
        self.output_type = "file"    # or "stdout"
        self.command_executed = None 

    def setup(self, target, output_dir):
        """
        Optional setup step before the run.
        You could add logic here to validate target, pre-create dirs, etc.
        """
        self.debug("Setup completed.")

    def is_available(self):
        """
        Check if required tool is installed and available in PATH.
        """
        # Example: Check if tool is available
        return shutil.which("ftap") is not None

    def run(self, target, output_dir, report_only):
        """
        Run the tool and return standardized result dict.
        """
        self.setup(target, output_dir)
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, f"{self.name}.json")
        
        # Example command structure
        cmd = [
            "ftap",
            "--url", target,
            "--detection-mode", "stealth",
            "-d", str(output_dir),
            "-e", "json",
            "-f", "ftap.json"
        ]

        # Check if tool is available
        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="Tool is not installed or not found in PATH.",
                timestamp=timestamp
            )

        try:
            if report_only:
                self.debug(f"[REPORT ONLY] Would run command: {' '.join(cmd)}")
                # In report-only mode, you might load existing results
                # or return a placeholder
            else:
                # Execute the command
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    return self.get_result_dict(
                        disposition="fail",
                        results=proc.stderr.strip(),
                        timestamp=timestamp
                    )

            # Load results from output file
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
        Normalize output, extract issues, and build executive_summary.
        """
        # Handle different input types
        if isinstance(raw_output, dict) and raw_output.get('disposition') == 'fail':
            # Plugin run failed, return minimal processed output
            findings = {}
        elif isinstance(raw_output, str) and os.path.isfile(raw_output):
            # Load from file path
            with open(raw_output, "r") as f:
                findings = json.load(f)
        elif isinstance(raw_output, dict):
            # Check if this is a result dict from run() or actual ftap data
            if 'disposition' in raw_output and 'results' in raw_output:
                # This is a result dict from run(), extract the results field
                findings = raw_output.get('results', {})
            else:
                # This is actual ftap data (has scan_info, results, etc.)
                findings = raw_output
        else:
            try:
                findings = json.loads(raw_output)
            except Exception:
                findings = {}

        self.debug(f"{self.name} raw findings:\n{pformat(findings)}")

        # Extract issues - each exposed admin panel is an issue
        # Filter out findings with confidence < 0.86
        issues = []
        # Handle both direct results array and dict with results key
        if isinstance(findings, dict):
            results = findings.get("results", [])
        elif isinstance(findings, list):
            results = findings
        else:
            results = []
        
        for panel in results:
            if panel.get("found", False) and panel.get("confidence", 0) >= 0.86:
                # Create issue entry for each exposed admin panel
                issue_entry = "exposed_admin_panel"
                issues.append(issue_entry)

        # Build details section with formatted information
        details = self._build_details(findings)

        # Build executive summary with panel information
        executive_summary = self._build_executive_summary(findings)

        # Generate summary using helper method
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
            "issues": issues,  # Always present, even if empty
            "executive_summary": executive_summary,  # Always present
            "report": report_notes
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)

        return processed_path

    def _generate_summary(self, findings):
        """
        Generate a human-readable summary from findings.
        """
        self.debug(f"_generate_summary called with findings type: {type(findings)}")
        self.debug(f"_generate_summary findings content: {pformat(findings)}")
        
        if not findings:
            self.debug("No findings, returning default message")
            return f"No findings were produced by {self.name}."
        
        # Extract results array and filter by confidence >= 0.86
        results = findings.get("results", []) if isinstance(findings, dict) else []
        found_count = len([r for r in results if r.get("found", False) and r.get("confidence", 0) >= 0.86])
        
        if found_count == 0:
            return f"No exposed admin panels were found."
        elif found_count == 1:
            return f"Found 1 exposed admin panel."
        else:
            return f"Found {found_count} exposed admin panels."

    def _build_details(self, findings):
        """
        Build detailed information about discovered admin panels.
        Returns formatted string with panel details.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        
        # Filter results by confidence >= 0.86
        high_confidence_results = [r for r in results if r.get("found", False) and r.get("confidence", 0) >= 0.86]
        
        if not high_confidence_results:
            return "No admin panels detected."
        
        details_lines = []
        details_lines.append("Exposed Admin Panels:")
        details_lines.append("")
        
        for idx, panel in enumerate(high_confidence_results, 1):
            url = panel.get("url", "N/A")
            title = panel.get("title", "N/A")
            confidence = panel.get("confidence", 0)
            status_code = panel.get("status_code", "N/A")
            has_login = panel.get("has_login_form", False)
            technologies = panel.get("technologies", [])
            
            details_lines.append(f"Panel #{idx}:")
            details_lines.append(f"  URL: {url}")
            details_lines.append(f"  Title: {title}")
            details_lines.append(f"  Confidence: {confidence:.1%}")
            details_lines.append(f"  Status Code: {status_code}")
            details_lines.append(f"  Login Form Detected: {'Yes' if has_login else 'No'}")
            if technologies:
                details_lines.append(f"  Technologies: {', '.join(technologies)}")
            details_lines.append("")
        
        return "\n".join(details_lines)

    def _build_executive_summary(self, findings):
        """
        Build executive summary - simple one-sentence format.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        # Filter by confidence >= 0.86
        found_panels = [r for r in results if r.get("found", False) and r.get("confidence", 0) >= 0.86]
        
        panel_count = len(found_panels)
        
        if panel_count == 0:
            return "No admin panels found."
        elif panel_count == 1:
            return "Found 1 admin panel."
        else:
            return f"Found {panel_count} admin panels."

    def _format_command_for_report(self):
        """
        Format the executed command for the report notes section.
        Returns HTML-formatted command with dark blue color and monospace font.
        """
        if not self.command_executed:
            return "Command not available"
        
        return f'<code style="color: #00008B; font-family: Consolas, \'Courier New\', monospace;">{self.command_executed}</code>'
