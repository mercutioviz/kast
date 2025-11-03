"""
File: plugins/template_plugin.py
Description: Template for KAST plugins. Copy and adapt for new tools.
"""

import os
import json
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class TemplatePlugin(KastPlugin):
    priority = 50  # Set plugin run order (lower runs earlier)

    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "template_tool"
        self.description = "Template plugin for new KAST integrations."
        self.scan_type = "passive"  # or "active"
        self.output_type = "file"    # or "stdout"

    def is_available(self):
        """
        Check if required tool is installed and available in PATH.
        """
        # Example: return shutil.which("toolname") is not None
        return True

    def run(self, target, output_dir, report_only):
        """
        Run the tool and return standardized result dict.
        """
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        # ... run tool, collect results ...
        results = {"raw": "example output"}
        return self.get_result_dict(
            disposition="success",
            results=results,
            timestamp=timestamp
        )

    def post_process(self, raw_output, output_dir):
        """
        Normalize output, extract issues, and build executive_summary.
        """
        # Load findings
        findings = raw_output["results"] if isinstance(raw_output, dict) else {}
        self.debug(f"Raw findings: {pformat(findings)}")

        # Example: Extract issues
        issues = []
        # ... logic to populate issues ...
        # If no issues found, keep as empty list

        # Example: Build executive summary
        executive_summary = {
            "summary": "No critical issues found.",
            "high": 0,
            "medium": 0,
            "low": 0
        }
        # ... logic to update executive_summary ...

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "issues": issues,  # Always present, even if empty
            "executive_summary": executive_summary  # Always present
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)

        return processed_path
