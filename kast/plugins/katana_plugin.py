"""
File: plugins/katana_plugin.py
Description: Site crawler and URL finder plugin for KAST.
"""

import subprocess
import shutil
import os
import json
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class KatanaPlugin(KastPlugin):
    priority = 60  # Set plugin run order (lower runs earlier)
    
    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "katana"
        self.description = "Site crawler and URL finder."
        self.display_name = "Katana"
        self.scan_type = "passive"  # or "active"
        self.output_type = "file"    # or "stdout"

    def is_available(self):
        """
        Check if required tool is installed and available in PATH.
        """
        return shutil.which("katana") is not None

    def run(self, target, output_dir, report_only):
        """
        Run the tool and return standardized result dict.
        """
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, "katana.txt")
        
        cmd = [
            "katana",
            "-silent",
            "-u", target,
            "-ob",
            "-rl", "15",
            "-fs", "fqdn",
            "-o", output_file
        ]

        if getattr(self.cli_args, "verbose", False):
            cmd.insert(1, "-v")
            self.debug(f"Running command: {' '.join(cmd)}")

        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="katana is not installed or not found in PATH.",
                timestamp=timestamp
            )

        try:
            if report_only:
                self.debug(f"[REPORT ONLY] Would run command: {' '.join(cmd)}")
                # Return empty results for report-only mode
                return self.get_result_dict(
                    disposition="success",
                    results={"target": target, "urls": []}
                )
            else:    
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    return self.get_result_dict(
                        disposition="fail",
                        results=proc.stderr.strip()
                    )

                # Read plain text output file and store raw URLs
                raw_urls = []
                if os.path.exists(output_file):
                    with open(output_file, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                raw_urls.append(line)

                return self.get_result_dict(
                    disposition="success",
                    results={"target": target, "urls": raw_urls}
                )

        except Exception as e:
            return self.get_result_dict(
                disposition="fail",
                results=str(e)
            )

    def post_process(self, raw_output, output_dir):
        """
        Normalize output, extract issues, and build executive_summary.
        Parse katana output to extract only URL paths after the target domain.
        """
        self.debug(f"{self.name} post_process called with raw_output type: {type(raw_output)}")
        self.debug(f"{self.name} post_process raw_output: {pformat(raw_output)}")
        
        # Read the katana.txt file directly since that's where the actual output is
        katana_file = os.path.join(output_dir, "katana.txt")
        
        target = self.cli_args.target
        raw_urls = []
        
        # Try to get target from raw_output if it's a dict
        if isinstance(raw_output, dict):
            target = raw_output.get("target", "")
            raw_urls = raw_output.get("urls", [])
        
        # If we don't have URLs yet, read from the katana.txt file
        if not raw_urls and os.path.exists(katana_file):
            self.debug(f"Reading URLs from {katana_file}")
            with open(katana_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        raw_urls.append(line)
            self.debug(f"Read {len(raw_urls)} URLs from katana.txt")

        # Parse URLs to extract only the path portion after the target domain
        parsed_urls = []
        for url in raw_urls:
            parsed_url = self._extract_url_path(url, target)
            if parsed_url:
                parsed_urls.append(parsed_url)
        
        # Remove duplicates and sort
        parsed_urls = sorted(list(set(parsed_urls)))
        
        self.debug(f"{self.name} parsed {len(raw_urls)} raw URLs into {len(parsed_urls)} unique URL paths")

        # Initialize issues (empty as requested)
        issues = []
        
        # Generate details and summaries
        url_count = len(parsed_urls)
        details = f"Detected {url_count} unique URL(s)."
        summary = self._generate_summary(parsed_urls)
        executive_summary = self._generate_executive_summary(parsed_urls)
        
        self.debug(f"{self.name} summary: {summary}")
        self.debug(f"{self.name} issues: {issues}")
        self.debug(f"{self.name} details:\n{details}")

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": getattr(self, 'display_name', None),
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": {"urls": parsed_urls},
            "summary": summary or f"{self.name} did not produce any findings",
            "details": details,
            "issues": issues,
            "executive_summary": executive_summary
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)

        return processed_path

    def _extract_url_path(self, full_url, target):
        """
        Extract the URL path portion after the target domain.
        
        Example:
        Input: [a] [GET] https://waas.az.hackazon.lkscd.com/cart/view
        Target: waas.az.hackazon.lkscd.com
        Output: /cart/view
        
        :param full_url: The complete URL from katana output
        :param target: The target domain
        :return: The URL path after the target domain
        """
        # Find the target domain in the URL
        target_index = full_url.find(target)
        
        if target_index != -1:
            # Extract everything after the target domain
            path = full_url[target_index + len(target):]
            # If path is empty, return root
            return path if path else "/"
        
        # If target not found in URL, return None to skip this URL
        self.debug(f"Target '{target}' not found in URL: {full_url}")
        return None

    def _generate_summary(self, parsed_urls):
        """
        Generate a human-readable summary from katana findings.
        """
        self.debug(f"_generate_summary called with parsed_urls type: {type(parsed_urls)}")
        self.debug(f"_generate_summary parsed_urls content: {pformat(parsed_urls)}")
        
        if not parsed_urls:
            return "No URLs were found."
        
        count = len(parsed_urls)
        return f"Detected {count} unique URL(s)."

    def _generate_executive_summary(self, parsed_urls):
        """
        Generate a simple executive summary for katana results.
        """
        if not parsed_urls:
            return "No URLs detected."
        
        count = len(parsed_urls)
        if count == 0:
            return "No URLs detected."
        elif count == 1:
            return "Detected 1 URL."
        else:
            return f"Detected {count} URLs."
