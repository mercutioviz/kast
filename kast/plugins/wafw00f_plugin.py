"""Wafw00f plugin — uses ExternalToolPlugin.

Most of the plugin migrates cleanly, but ``run()`` is overridden because
wafw00f has plugin-specific behavior the base can't capture: TLS-error
detection in stderr that triggers an HTTPS→HTTP retry, and a side-file
(``wafw00f_stdout.txt``) that the post-processing layer parses for test
URLs. All other concerns (build_command, post_process scaffolding,
atomic writes, dry-run info) come from the base.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime

from kast.plugins.external_tool import ExternalToolPlugin


class Wafw00fPlugin(ExternalToolPlugin):
    priority = 10

    name = "wafw00f"
    display_name = "Wafw00f"
    description = "Detects and identifies Web Application Firewalls (WAFs) on the target."
    website_url = "https://github.com/EnableSecurity/wafw00f"
    scan_type = "passive"
    output_type = "file"

    tool_binary = "wafw00f"
    output_filename = "wafw00f.json"
    output_format = "json"

    config_schema = {
        "type": "object",
        "title": "Wafw00f Configuration",
        "description": "Web Application Firewall detection configuration",
        "properties": {
            "find_all": {
                "type": "boolean", "default": True,
                "description": "Find all WAFs matching signatures (use -a flag)",
            },
            "verbosity": {
                "type": "integer", "default": 3, "minimum": 0, "maximum": 3,
                "description": "Verbosity level (0=quiet, 3=maximum)",
            },
            "follow_redirects": {
                "type": "boolean", "default": True,
                "description": "Follow HTTP redirections",
            },
            "timeout": {
                "type": "integer", "default": 30, "minimum": 5, "maximum": 120,
                "description": "Request timeout in seconds",
            },
            "proxy": {
                "type": ["string", "null"], "default": None,
                "description": "HTTP/SOCKS proxy URL (e.g., http://hostname:8080)",
            },
            "test_specific_waf": {
                "type": ["string", "null"], "default": None,
                "description": "Test for specific WAF only (e.g., 'Cloudflare')",
            },
        },
    }

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self._load_plugin_config()

    def _load_plugin_config(self) -> None:
        self.find_all = self.get_config("find_all", True)
        self.verbosity = self.get_config("verbosity", 3)
        self.follow_redirects = self.get_config("follow_redirects", True)
        self.timeout = self.get_config("timeout", 30)
        self.proxy = self.get_config("proxy", None)
        self.test_specific_waf = self.get_config("test_specific_waf", None)
        self.debug(
            f"Wafw00f config loaded: find_all={self.find_all}, "
            f"verbosity={self.verbosity}, "
            f"follow_redirects={self.follow_redirects}, "
            f"timeout={self.timeout}, "
            f"proxy={'(set)' if self.proxy else '(none)'}, "
            f"test_specific_waf={self.test_specific_waf or '(all)'}"
        )

    # -- ExternalToolPlugin hooks ------------------------------------------

    def build_command(self, target: str, output_path: str) -> list[str]:
        cmd = ["wafw00f", target]
        if self.find_all:
            cmd.append("-a")
        if self.verbosity > 0:
            cmd.append("-" + "v" * self.verbosity)
        if not self.follow_redirects:
            cmd.append("-r")
        if self.timeout:
            cmd.extend(["-T", str(self.timeout)])
        if self.proxy:
            cmd.extend(["-p", self.proxy])
        if self.test_specific_waf:
            cmd.extend(["-t", self.test_specific_waf])
        cmd.extend(["-f", "json", "-o", output_path])
        return cmd

    def run(self, target, output_dir, report_only):
        """Override the base's run() to handle the TLS-error retry case.

        wafw00f against an HTTPS target sometimes hits
        ``TLSV1_ALERT_PROTOCOL_VERSION`` errors when the target negotiates
        an old protocol the wafw00f-bundled libssl doesn't support. The
        retry-with-HTTP fallback was a v2 workaround that's still required.

        Also writes ``wafw00f_stdout.txt`` for the post-processing test-URL
        extraction (a side-file specific to this plugin; not part of the
        ExternalToolPlugin contract).
        """
        # Captured so format_details() / _read_test_urls() can locate
        # wafw00f_stdout.txt (the base's hooks don't receive output_dir).
        self._scan_output_dir = str(output_dir)
        if report_only:
            return super().run(target, output_dir, report_only)

        timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        output_file = os.path.join(str(output_dir), self.output_filename)
        stdout_file = os.path.join(str(output_dir), "wafw00f_stdout.txt")

        if not self.is_available():
            return self.get_result_dict(
                "fail", f"{self.tool_binary} not installed or not in PATH.", timestamp,
            )

        cmd = self.build_command(target, output_file)
        self.command_executed = " ".join(cmd)
        self.debug(f"Running: {self.command_executed}")

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self.subprocess_timeout)
            self._write_stdout_file(stdout_file, proc)

            if proc.stderr and any(
                line.startswith("ERROR:") and "TLSV1_ALERT_PROTOCOL_VERSION" in line
                for line in proc.stderr.split("\n")
            ):
                self.debug("TLS version error detected; retrying with HTTP")
                # Save the error transcript before overwriting
                error_stdout = os.path.join(str(output_dir), "wafw00f_stdout_error.txt")
                if os.path.exists(stdout_file):
                    os.rename(stdout_file, error_stdout)

                http_target = target.replace("https://", "http://")
                if not http_target.startswith("http://"):
                    http_target = "http://" + http_target
                http_cmd = self.build_command(http_target, output_file)
                self.command_executed = " ".join(http_cmd)
                self.debug(f"Retrying: {self.command_executed}")

                # Touch the output file so kast-web's state machine sees the
                # plugin-running marker before the second wafw00f finishes.
                open(output_file, "a").close()
                proc = subprocess.run(http_cmd, capture_output=True, text=True,
                                      timeout=self.subprocess_timeout)
                self._write_stdout_file(stdout_file, proc)

            if proc.returncode != 0:
                return self.get_result_dict(
                    "fail",
                    proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}",
                    timestamp,
                )
            if not os.path.exists(output_file):
                return self.get_result_dict(
                    "fail",
                    f"{self.tool_binary} completed but did not create {output_file}",
                    timestamp,
                )

            with open(output_file) as f:
                results = json.load(f)
            return self.get_result_dict("success", results, timestamp)

        except subprocess.TimeoutExpired:
            return self.get_result_dict(
                "fail", f"{self.tool_binary} timed out after {self.subprocess_timeout}s", timestamp,
            )
        except Exception as e:
            self.debug(f"{self.name} run() failed: {e}")
            return self.get_result_dict("fail", str(e), timestamp)

    def parse_findings(self, raw):
        """Normalize wafw00f's raw output into the v2-baseline dict shape.

        ``wafw00f.json`` is a top-level JSON array of detection records.
        v2 stored the entire ``get_result_dict`` wrapper as findings, which
        produced a dict with ``{name, timestamp, disposition, results}``.
        Preserve that shape here so kast-web parsers and the report's
        ``findings.results`` consumer don't break.

        Also drops the synthetic 'Generic' WAF entry when more specific
        results exist (v2 behavior).
        """
        # Normalize into a list of detections
        if isinstance(raw, list):
            results_list = raw
        elif isinstance(raw, dict):
            results_list = raw.get("results") or []
        else:
            results_list = []

        # Generic-WAF cleanup
        if len(results_list) > 1 and any(r.get("firewall") == "Generic" for r in results_list):
            results_list = [r for r in results_list if r.get("firewall") != "Generic"]
            self.debug("Removed Generic WAF entries from findings.")

        return {
            "name": self.name,
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "disposition": "success",
            "results": results_list,
        }

    def count_findings(self, findings) -> int:
        """Count detected WAFs (excluding 'None' placeholders)."""
        results = (findings.get("results") or []) if isinstance(findings, dict) else []
        return len(
            [
                r for r in results
                if r.get("detected", False) and r.get("firewall", "None") != "None"
            ]
        )

    def extract_issues(self, findings) -> list:
        """Map detection state to issue-registry IDs."""
        case = self._classify(findings)
        if case == "no_waf":
            return ["No WAF Detected"]
        if case == "generic":
            return ["WAF Check Inconclusive"]
        return []

    def format_summary(self, findings):
        """Generate a human-readable summary from wafw00f results."""
        results = (findings.get("results") or []) if isinstance(findings, dict) else []
        if not results:
            return "No WAFs were detected."
        detected = [
            r for r in results
            if r.get("detected", False) and r.get("firewall", "None") != "None"
        ]
        if not detected:
            return "No WAF detected"
        names = [r.get("firewall", "Unknown") for r in detected]
        return f"Detected {len(names)} WAF(s): {', '.join(names)}"

    def format_details(self, findings) -> str:
        """Three-case detail formatting (matches v2's behavior)."""
        results = (findings.get("results") or []) if isinstance(findings, dict) else []
        case = self._classify(findings)
        # Test URLs from the wafw00f stdout side-file
        test_urls = self._read_test_urls()

        if case == "no_waf":
            details = "No WAF detected."
            if test_urls:
                details += "\n" + "\n".join(f"Test URL: {u}" for u in test_urls)
            return details
        if case == "generic":
            details = "A generic WAF was reported by wafw00f."
            if test_urls:
                details += "\n" + "\n".join(f"Test URL: {u}" for u in test_urls)
            return details
        # specific WAF
        first = next((r for r in results if r.get("detected", False)), {})
        firewall = first.get("firewall", "Unknown")
        manufacturer = first.get("manufacturer", "Unknown")
        trigger_url = first.get("trigger_url", "N/A")
        lines = [
            f"<b>WAF Detected:</b> {firewall}",
            f"<b>Manufacturer:</b> {manufacturer}",
        ]
        for url in test_urls:
            lines.append(f"<b>Test URL:</b> {url}")
        lines.append(f"<b>Trigger URL:</b> {trigger_url}")
        return "\n".join(lines)

    def format_executive_summary(self, findings, issues):
        case = self._classify(findings)
        if case == "no_waf":
            return "No WAFs were detected."
        if case == "generic":
            return "WAF detection was inconclusive."
        results = (findings.get("results") or []) if isinstance(findings, dict) else []
        first = next((r for r in results if r.get("detected", False)), {})
        return f"Detected WAF: {first.get('firewall', 'Unknown')}."

    def get_dry_run_info(self, target, output_dir):
        info = super().get_dry_run_info(target, output_dir)
        operations_parts = []
        if self.find_all:
            operations_parts.append("test all WAF signatures")
        if self.test_specific_waf:
            operations_parts.append(f"test for {self.test_specific_waf}")
        operations_parts.append(f"timeout {self.timeout}s")
        info["operations"] = f"WAF detection ({', '.join(operations_parts)})"
        return info

    # -- wafw00f-specific helpers -----------------------------------------

    @staticmethod
    def _write_stdout_file(stdout_path: str, proc) -> None:
        """Persist subprocess stdout/stderr to ``wafw00f_stdout.txt``."""
        out = ""
        if proc.stdout:
            out += "=== STDOUT ===\n" + proc.stdout + "\n"
        if proc.stderr:
            out += "=== STDERR ===\n" + proc.stderr + "\n"
        with open(stdout_path, "w") as f:
            f.write(out)

    @staticmethod
    def _classify(findings) -> str:
        """Classify wafw00f findings: 'no_waf' | 'generic' | 'specific'."""
        results = (findings.get("results") or []) if isinstance(findings, dict) else []
        if not results or not any(r.get("detected", False) for r in results):
            return "no_waf"
        if any(r.get("firewall") == "Generic" for r in results):
            return "generic"
        return "specific"

    def _read_test_urls(self) -> list[str]:
        """Extract probed URLs from wafw00f_stdout.txt for the report's details.

        wafw00f's verbose mode logs every probe via urllib3's connection pool;
        each line looks like:
            DEBUG:urllib3.connectionpool:http://example.com:80 "GET /?cisgshjh=...XSS... HTTP/1.1" 302 0
        Including these in the report lets the customer see what was tested.
        """
        output_dir = getattr(self, "_scan_output_dir", None)
        if not output_dir:
            return []
        stdout_path = os.path.join(output_dir, "wafw00f_stdout.txt")
        if not os.path.exists(stdout_path):
            return []
        urls: list[str] = []
        try:
            with open(stdout_path) as f:
                for line in f:
                    if not (line.startswith("DEBUG:urllib3.connectionpool:") and "GET /?" in line):
                        continue
                    parts = line.split('"')
                    if len(parts) < 2:
                        continue
                    get_part = parts[1]
                    if get_part.startswith("GET "):
                        urls.append(get_part.split()[1])
        except Exception as e:
            self.debug(f"Error reading {stdout_path}: {e}")
        return urls
