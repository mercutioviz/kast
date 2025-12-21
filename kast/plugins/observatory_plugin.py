"""
File: plugins/observatory_plugin.py
Description: Plugin for running Mozilla Observatory as part of KAST.
"""

import subprocess
import shutil
import os
import json
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class ObservatoryPlugin(KastPlugin):
    priority = 5  # High priority (lower number = higher priority)

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self.name = "mozilla_observatory"
        self.display_name = "Mozilla Observatory"
        self.description = "Runs Mozilla Observatory to analyze web application security."
        self.website_url = "https://developer.mozilla.org/en-US/blog/mdn-http-observatory-launch/"
        self.scan_type = "passive"
        self.output_type = "stdout"
        self.command_executed = None  # Store the command for reporting

    def setup(self, target, output_dir):
        """
        Optional setup step before the run.
        You could add logic here to validate target, pre-create dirs, etc.
        """
        self.debug("Setup completed.")

    def is_available(self):
        """
        Check if mdn-http-observatory-scan is installed and available in PATH.
        """
        return shutil.which("mdn-http-observatory-scan") is not None

    def run(self, target, output_dir, report_only):
        """
        Run Mozilla Observatory against the target and capture output.
        Returns a standardized result dictionary.
        """
        self.setup(target, output_dir)
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, "mozilla_observatory.json")
        self.debug(f"Output file will be: {output_file}")

        cmd = [
            "mdn-http-observatory-scan",
            target
        ]

        self.debug(f"Running command: {' '.join(cmd)}")

        # Store command for reporting
        self.command_executed = ' '.join(cmd)

        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="mdn-http-observatory-scan is not installed or not found in PATH."
            )

        try:
            if report_only:
                self.debug(f"[REPORT ONLY] Would run command: {' '.join(cmd)}")

            else:
                #proc = subprocess.run(cmd, capture_output=True, text=True)
                with open(output_file, "w") as outfile:
                    proc = subprocess.run(cmd, stdout=outfile, stderr=subprocess.PIPE, text=True)

                if proc.returncode != 0:
                    self.debug(f"Command stderr: {proc.stderr} in Observatory run attempt")
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
                results=str(e)
            )

    def post_process(self, raw_output, output_dir):
        """
        Process the raw output from the Mozilla Observatory scan.
        Extracts relevant summary information.
        """
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

        # Normalize findings: sometimes the 'results' field is a JSON string
        if isinstance(findings, dict) and "results" in findings and isinstance(findings["results"], str):
            try:
                findings["results"] = json.loads(findings["results"])
                self.debug("Normalized 'results' field from JSON string to dict")
            except Exception:
                self.debug("Failed to parse 'results' field as JSON; leaving as-is")

        # Debugging: log the 'results' field type and preview to help diagnose unexpected shapes
        if isinstance(findings, dict):
            r = findings.get("results")
            try:
                self.debug(f"'results' type: {type(r)}, preview: {pformat(r)[:200]}")
            except Exception:
                self.debug("Could not pretty-print 'results' preview")

        # Initialize issues and details
        issues = []
        details = ""

        # If the run failed or produced no results, avoid parsing structured fields
        if not findings or findings.get("disposition") != "success" or not findings.get("results"):
            summary = f"{self.name} run failed: {findings.get('results') or 'No output'}"
            self.debug(f"{self.name} summary (failure/no results): {summary}")
            executive_summary = summary
            # If results is a string, put it in details for visibility
            if isinstance(findings.get("results"), str):
                details = findings.get("results")
            issues = []
        else:
            summary = self._generate_summary(findings)
            self.debug(f"{self.name} summary: {summary}")

            executive_summary = (
                "-= Observatory grade and score summary =-\n"
                f"{summary}"
            )
            self.debug(f"{self.name} executive_summary: {executive_summary}")

            issues = self._find_issues(findings)
            self.debug(f"{self.name} issues: {issues}")

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

    def _find_issues(self, findings):
        """
        Extract failed tests from Mozilla Observatory findings.
        Returns a list of failed test result strings.
        """
        issues = []
        tests = findings.get("results", {}).get("tests", {})
        
        for test_name, test_data in tests.items():
            if test_data.get("pass") is False:  # Explicitly check for False
                result = test_data.get("result", "Unknown issue")
                issues.append(result)
        
        return issues

    def _generate_summary(self, findings):
        """
        Generate a human-readable summary from Mozilla Observatory findings.
        Extracts grade, score, testsPassed, and testsFailed.
        """
        self.debug(f"_generate_summary called with findings type: {type(findings)}")
        self.debug(f"_generate_summary findings content: {pformat(findings)}")

        scan_info = findings.get("results", {}).get("scan", {})
        grade = scan_info.get("grade", "N/A")
        score = scan_info.get("score", "N/A")
        tests_passed = scan_info.get("testsPassed", "N/A")
        tests_failed = scan_info.get("testsFailed", "N/A")

        summary_text = (
            f"Grade: {grade}, Score: {score}, "
            f"Tests Passed: {tests_passed}, Tests Failed: {tests_failed}"
        )
        self.debug(f"Generated summary: {summary_text}")
        return summary_text
