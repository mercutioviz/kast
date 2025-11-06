"""
File: plugins/template_plugin.py
Description: Template for KAST plugins. Copy and adapt for new tools.
"""

import subprocess
import shutil
import json
import os
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class TemplatePlugin(KastPlugin):
    priority = 50  # Set plugin run order (lower runs earlier)

    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "template_tool"
        self.display_name = "Template Tool"  # Human-readable name for reports
        self.description = "Template plugin for new KAST integrations."
        self.scan_type = "passive"  # or "active"
        self.output_type = "file"    # or "stdout"

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
        # return shutil.which("toolname") is not None
        return True

    def run(self, target, output_dir, report_only):
        """
        Run the tool and return standardized result dict.
        """
        self.setup(target, output_dir)
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, f"{self.name}.json")
        
        # Example command structure
        cmd = [
            "toolname",
            target,
            "-o", output_file
        ]

        # Add verbose flag if enabled
        if getattr(self.cli_args, "verbose", False):
            cmd.insert(1, "-v")
            self.debug(f"Running command: {' '.join(cmd)}")

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
        # Load findings from various input types
        if isinstance(raw_output, str) and os.path.isfile(raw_output):
            with open(raw_output, "r") as f:
                findings = json.load(f)
        elif isinstance(raw_output, dict):
            findings = raw_output.get("results", raw_output)
        else:
            try:
                findings = json.loads(raw_output)
            except Exception:
                findings = {}

        self.debug(f"{self.name} raw findings:\n{pformat(findings)}")

        # Example: Extract issues
        issues = []
        # ... logic to populate issues ...
        # Example: issues = ["Issue 1", "Issue 2"]
        # If no issues found, keep as empty list

        # Example: Build details (multi-line formatted string)
        details = ""
        # ... logic to build details ...
        # Example:
        # details = (
        #     f"Finding 1: Value\n"
        #     f"Finding 2: Value\n"
        #     f"Total Items: {len(findings)}"
        # )

        # Example: Build executive summary
        executive_summary = "No critical issues found."
        # ... logic to update executive_summary ...
        # Example: executive_summary = f"Found {len(issues)} issues."

        # Generate summary using helper method
        summary = self._generate_summary(findings)
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
            "issues": issues,  # Always present, even if empty
            "executive_summary": executive_summary  # Always present
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)

        return processed_path

    def _generate_summary(self, findings):
        """
        Generate a human-readable summary from findings.
        Override this method to provide tool-specific summaries.
        """
        self.debug(f"_generate_summary called with findings type: {type(findings)}")
        self.debug(f"_generate_summary findings content: {pformat(findings)}")
        
        if not findings:
            self.debug("No findings, returning default message")
            return f"No findings were produced by {self.name}."
        
        # Example: Count items in findings
        if isinstance(findings, dict):
            count = len(findings)
            return f"{self.name} produced {count} finding(s)."
        elif isinstance(findings, list):
            count = len(findings)
            return f"{self.name} produced {count} result(s)."
        else:
            return f"{self.name} produced findings of type: {type(findings).__name__}"
