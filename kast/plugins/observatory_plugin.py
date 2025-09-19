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

    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "mozilla_observatory"
        self.description = "Runs Mozilla Observatory to analyze web application security."
        self.scan_type = "passive"
        self.output_type = "stdout"

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
        output_file = os.path.join(output_dir, "observatory.json")
        self.debug(f"Output file will be: {output_file}")

        cmd = [
            "mdn-http-observatory-scan",
            target
        ]

        self.debug(f"Running command: {' '.join(cmd)}")

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

        summary = self._generate_summary(findings)
        self.debug(f"{self.name} summary: {summary}")

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "summary": summary or f"{self.name} did not produce any findings"
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)

        return processed_path

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
