"""
File: plugins/observatory_plugin.py
Description: Plugin for running Mozilla Observatory as part of KAST.
"""

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pprint import pformat

from kast.core.atomic import write_json_atomic
from kast.plugins.base import KastPlugin

# Maps Observatory test result strings to issue_registry.json IDs.
# Keys are the raw result values Observatory emits; values are issue_ids.
# Unmapped results are kept as-is (raw string) for forward compatibility.
_OBSERVATORY_RESULT_TO_ISSUE = {
    # CSP
    "csp-not-implemented": "csp-not-implemented",
    "content-security-policy-not-implemented": "csp-not-implemented",
    "csp-implemented-with-unsafe-inline": "csp-implemented-with-unsafe-inline",
    "csp-not-implemented-but-reporting-enabled": "csp-not-implemented-but-reporting-enabled",
    # HSTS
    "hsts-not-implemented": "hsts-not-implemented",
    "hsts-header-invalid": "hsts-header-invalid",
    "hsts-invalid-cert": "hsts-invalid-cert",
    "hsts-implemented-max-age-less-than-six-months": "hsts-implemented-max-age-less-than-six-months",
    # X-Frame-Options
    "x-frame-options-not-implemented": "x-frame-options-not-implemented",
    "x-frame-options-header-invalid": "x-frame-options-header-invalid",
    # X-Content-Type-Options
    "x-content-type-options-not-implemented": "x-content-type-options-not-implemented",
    "x-content-type-options-header-invalid": "x-content-type-options-header-invalid",
    # Referrer-Policy
    "referrer-policy-unsafe": "referrer-policy-unsafe",
    # Modern isolation headers (mapped to new registry entries)
    "cross-origin-embedder-policy-not-implemented": "missing-coep",
    "cross-origin-opener-policy-not-implemented": "missing-coop",
    "permissions-policy-not-implemented": "missing-permissions-policy",
    "permissions-policy-header-not-set": "missing-permissions-policy",
}


def _split_tests_by_status(tests):
    """Partition a flat tests dict into {"passed": {...}, "failed": {...}}."""
    passed = {}
    failed = {}
    for name, data in tests.items():
        if isinstance(data, dict) and data.get("pass") is True:
            passed[name] = data
        else:
            failed[name] = data
    return {"passed": passed, "failed": failed}

class ObservatoryPlugin(KastPlugin):
    priority = 5  # High priority (lower number = higher priority)

    # Configuration schema for kast-web integration
    config_schema = {
        "type": "object",
        "title": "Mozilla Observatory Configuration",
        "description": "Settings for Mozilla Observatory HTTP security scanner",
        "properties": {
            "timeout": {
                "type": "integer",
                "default": 300,
                "minimum": 30,
                "maximum": 1800,
                "description": "Command execution timeout in seconds"
            },
            "retry_attempts": {
                "type": "integer",
                "default": 1,
                "minimum": 1,
                "maximum": 5,
                "description": "Number of retry attempts on failure"
            },
            "additional_args": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": "Additional command line arguments to pass to mdn-http-observatory-scan"
            },
            "format": {
                "type": "string",
                "enum": ["json"],
                "default": "json",
                "description": "Output format (currently only JSON is supported)"
            }
        }
    }

    name = "mozilla_observatory"
    display_name = "Mozilla Observatory"
    tested_tool_version = "1.6.2"
    description = "Runs Mozilla Observatory to analyze web application security."
    website_url = "https://developer.mozilla.org/en-US/blog/mdn-http-observatory-launch/"
    scan_type = "passive"
    output_type = "stdout"

    def __init__(self, cli_args, config_manager=None):

        super().__init__(cli_args, config_manager)

        self.command_executed = None  # Store the command for reporting

        # Load configuration values
        self._load_plugin_config()

    def _load_plugin_config(self):
        """Load configuration with defaults from schema."""
        # Get config values (defaults from schema if not set)
        self.timeout = self.get_config('timeout', 300)
        self.retry_attempts = self.get_config('retry_attempts', 1)
        self.additional_args = self.get_config('additional_args', [])
        self.format = self.get_config('format', 'json')

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
        timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, "mozilla_observatory.json")
        self.debug(f"Output file will be: {output_file}")

        # Build command with configuration
        cmd = [
            "mdn-http-observatory-scan",
            target
        ]

        # Add any additional arguments from config
        if self.additional_args:
            cmd.extend(self.additional_args)
            self.debug(f"Added additional args from config: {self.additional_args}")

        self.debug(f"Running command: {' '.join(cmd)}")
        self.debug(f"Timeout: {self.timeout}s, Retry attempts: {self.retry_attempts}")

        # Store command for reporting
        self.command_executed = ' '.join(cmd)

        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="mdn-http-observatory-scan is not installed or not found in PATH."
            )

        # Try execution with retry logic
        last_error = None
        for attempt in range(self.retry_attempts):
            if attempt > 0:
                self.debug(f"Retry attempt {attempt + 1} of {self.retry_attempts}")

            try:
                if report_only:
                    self.debug(f"[REPORT ONLY] Would run command: {' '.join(cmd)}")
                    # In report-only mode, check if results already exist
                    if os.path.exists(output_file):
                        with open(output_file) as f:
                            results = json.load(f)
                        return self.get_result_dict(
                            disposition="success",
                            results=results,
                            timestamp=timestamp
                        )
                    else:
                        return self.get_result_dict(
                            disposition="fail",
                            results="No existing results found for report-only mode.",
                            timestamp=timestamp
                        )
                else:
                    # Execute command with timeout
                    with open(output_file, "w") as outfile:
                        proc = subprocess.run(
                            cmd,
                            stdout=outfile,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=self.timeout
                        )

                    if proc.returncode != 0:
                        last_error = proc.stderr.strip()
                        self.debug(f"Command failed (attempt {attempt + 1}): {last_error}")
                        if attempt < self.retry_attempts - 1:
                            continue  # Retry
                        return self.get_result_dict(
                            disposition="fail",
                            results=last_error
                        )

                # Read the output file
                with open(output_file) as f:
                    results = json.load(f)

                return self.get_result_dict(
                    disposition="success",
                    results=results,
                    timestamp=timestamp
                )

            except subprocess.TimeoutExpired:
                last_error = f"Command timed out after {self.timeout} seconds"
                self.debug(f"{last_error} (attempt {attempt + 1})")
                if attempt < self.retry_attempts - 1:
                    continue  # Retry
                return self.get_result_dict(
                    disposition="fail",
                    results=last_error
                )
            except Exception as e:
                last_error = str(e)
                self.debug(f"Execution error (attempt {attempt + 1}): {last_error}")
                if attempt < self.retry_attempts - 1:
                    continue  # Retry
                return self.get_result_dict(
                    disposition="fail",
                    results=last_error
                )

        # Should not reach here, but just in case
        return self.get_result_dict(
            disposition="fail",
            results=last_error or "Unknown error"
        )

    def post_process(self, raw_output, output_dir):
        """
        Process the raw output from the Mozilla Observatory scan.
        Extracts relevant summary information.
        """
        if isinstance(raw_output, str) and os.path.isfile(raw_output):
            with open(raw_output) as f:
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
            # Reshape findings.results.tests from a flat dict into
            # {"passed": {...}, "failed": {...}} so the tree-json renderer
            # groups results by status. Must run before _find_issues.
            results = findings.get("results")
            if isinstance(results, dict) and isinstance(results.get("tests"), dict):
                results["tests"] = _split_tests_by_status(results["tests"])

            summary = self._generate_summary(findings)
            self.debug(f"{self.name} summary: {summary}")

            executive_summary = summary
            self.debug(f"{self.name} executive_summary: {executive_summary}")

            issues = self._find_issues(findings)
            self.debug(f"{self.name} issues: {issues}")

            details = self._generate_details(findings)

        # Calculate findings_count - count of failed tests (security issues)
        findings_count = len(issues) if isinstance(issues, list) else 0

        # Format command for report notes
        report_notes = self._format_command_for_report()

        self.debug(f"{self.name} findings_count: {findings_count}")

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": getattr(self, 'display_name', None),
            "plugin-website-url": getattr(self, 'website_url', None),
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "findings": findings,
            "findings_count": findings_count,
            "summary": summary or f"{self.name} did not produce any findings",
            "details": details,
            "issues": issues,
            "executive_summary": executive_summary,
            "report": report_notes
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        write_json_atomic(processed_path, processed)

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
        Maps known result strings to issue_registry.json IDs; unknown results
        are kept as raw strings for forward compatibility.
        """
        issues = []
        failed = findings.get("results", {}).get("tests", {}).get("failed", {})

        for _test_name, test_data in failed.items():
            if test_data.get("pass") is False:
                result = test_data.get("result", "")
                issue_id = _OBSERVATORY_RESULT_TO_ISSUE.get(result, result)
                if issue_id:
                    issues.append(issue_id)

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

    def _generate_details(self, findings):
        """Describe each failing Observatory test."""
        failed = findings.get("results", {}).get("tests", {}).get("failed", {})
        if not failed:
            return ""
        lines = ["Failed tests:"]
        for test_name, data in failed.items():
            if not isinstance(data, dict):
                continue
            result = data.get("result", "")
            score_modifier = data.get("scoreModifier", 0)
            desc = data.get("recommendation") or data.get("description") or result
            lines.append(f"  {test_name}: {result} (score modifier: {score_modifier})")
            if desc and desc != result:
                lines.append(f"    {desc}")
        return "\n".join(lines)

    def get_dry_run_info(self, target, output_dir):
        """
        Return information about what this plugin would do in a real run.
        """
        cmd = [
            "mdn-http-observatory-scan",
            target
        ]

        return {
            "commands": [' '.join(cmd)],
            "description": self.description
        }
