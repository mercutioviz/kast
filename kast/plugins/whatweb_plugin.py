"""
File: plugins/whatweb_plugin.py
Description: Plugin for running WhatWeb as part of KAST.
"""

import subprocess
import shutil
import json
import os
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class WhatWebPlugin(KastPlugin):
    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "whatweb"
        self.description = "Identifies technologies used by a website."
        self.scan_type = "passive"
        self.output_type = "file"
        self.priority = 15  # Executes after wafw00f (priority 10)

    def is_available(self):
        """
        Check if WhatWeb is installed and available in PATH.
        """
        return shutil.which("whatweb") is not None

    def setup(self):
        """
        Optional pre-run setup. Nothing required for WhatWeb currently.
        """
        pass

    def run(self, target, output_dir):
        """
        Run WhatWeb against the target and save output to a file.
        Returns a result dictionary.
        """
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, "whatweb.json")
        cmd = [
            "whatweb",
            "-a", "3",
            target,
            "--log-json", output_file
        ]

        if getattr(self.cli_args, "verbose", False):
            self.debug(f"Running command: {' '.join(cmd)}")

        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="WhatWeb is not installed or not found in PATH.",
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

    def post_process(self, raw_output, output_dir):
        """
        Post-process WhatWeb output into standardized structure.
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

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "summary": self._generate_summary(findings)
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)
        return processed_path
