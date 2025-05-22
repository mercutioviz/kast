# wafw00f_plugin.py
"""
File: wafw00f_plugin.py
Description: Plugin for running wafw00f as part of KAST.
"""

import subprocess
import shutil
import datetime
import json
from kast.plugins.base import KastPlugin

class Wafw00fPlugin(KastPlugin):
    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "wafw00f"
        self.description = "Detects and identifies Web Application Firewalls (WAFs) on the target."
        self.scan_type = "passive"
        self.output_type = "file"

    def is_available(self):
        """
        Check if wafw00f is installed and available in PATH.
        """
        return shutil.which("wafw00f") is not None

    def run(self, target, output_dir):
        """
        Run wafw00f against the target and save output to a file.
        Returns a result dictionary.
        """
        timestamp = datetime.datetime.now().isoformat()
        output_file = f"{output_dir}/wafw00f.json"
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
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                return self.get_result_dict(
                    disposition="fail",
                    results=proc.stderr.strip(),
                    timestamp=timestamp
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

    def get_result_dict(self, disposition, results, timestamp=None):
        """
        Standardized result dictionary for plugin output.
        """
        if not timestamp:
            timestamp = datetime.datetime.now().isoformat()
        return {
            "name": self.name,
            "timestamp": timestamp,
            "disposition": disposition,
            "results": results
        }
