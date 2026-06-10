"""
File: plugins/testssl_plugin.py
Description: KAST plugin for testssl.sh - SSL/TLS security assessment tool
"""

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pprint import pformat

from kast.core.atomic import write_json_atomic
from kast.plugins.base import KastPlugin


class TestsslPlugin(KastPlugin):
    priority = 50  # Set plugin run order (lower runs earlier)

    # Configuration schema for kast-web integration
    config_schema = {
        "type": "object",
        "title": "TestSSL Configuration",
        "description": "SSL/TLS security testing configuration",
        "properties": {
            "timeout": {
                "type": "integer",
                "default": 300,
                "minimum": 60,
                "maximum": 1800,
                "description": "Maximum scan timeout in seconds"
            },
            "test_vulnerabilities": {
                "type": "boolean",
                "default": True,
                "description": "Test for SSL/TLS vulnerabilities (-U flag)"
            },
            "test_ciphers": {
                "type": "boolean",
                "default": True,
                "description": "Test cipher categories (-E flag)"
            },
            "connect_timeout": {
                "type": "integer",
                "default": 10,
                "minimum": 5,
                "maximum": 60,
                "description": "Connection timeout in seconds"
            },
            "warnings_batch_mode": {
                "type": "boolean",
                "default": True,
                "description": "Suppress connection warnings for batch mode"
            },
            "test_server_defaults": {
                "type": "boolean",
                "default": True,
                "description": "Test server defaults including certificate expiry and chain (-S flag)"
            },
            "test_protocols": {
                "type": "boolean",
                "default": True,
                "description": "Test supported protocol versions to detect deprecated TLS 1.0/1.1 and SSLv2/v3 (-p flag)"
            }
        }
    }

    name = "testssl"
    display_name = "Test SSL"
    description = "Tests SSL and TLS posture"
    website_url = "https://testssl.sh/"
    scan_type = "passive"
    output_type = "file"

    def __init__(self, cli_args, config_manager=None):

        super().__init__(cli_args, config_manager)

        self.command_executed = None

        # Load configuration values
        self._load_plugin_config()

    def _load_plugin_config(self):
        """Load configuration with defaults from schema."""
        # Get config values (defaults from schema if not set)
        self.timeout = self.get_config('timeout', 300)
        self.test_vulnerabilities = self.get_config('test_vulnerabilities', True)
        self.test_ciphers = self.get_config('test_ciphers', True)
        self.test_server_defaults = self.get_config('test_server_defaults', True)
        self.test_protocols = self.get_config('test_protocols', True)
        self.connect_timeout = self.get_config('connect_timeout', 10)
        self.warnings_batch_mode = self.get_config('warnings_batch_mode', True)

        self.debug(f"TestSSL config loaded: timeout={self.timeout}, "
                  f"vulnerabilities={self.test_vulnerabilities}, "
                  f"ciphers={self.test_ciphers}, "
                  f"server_defaults={self.test_server_defaults}, "
                  f"protocols={self.test_protocols}, "
                  f"connect_timeout={self.connect_timeout}, "
                  f"warnings_batch={self.warnings_batch_mode}")

    def setup(self, target, output_dir):
        """
        Optional setup step before the run.
        """
        self.debug("Setup completed.")

    def is_available(self):
        """
        Check if testssl is installed and available in PATH.
        """
        return shutil.which("testssl") is not None or shutil.which("testssl.sh") is not None

    def run(self, target, output_dir, report_only):
        """
        Run testssl and return standardized result dict.
        """
        self.setup(target, output_dir)
        timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, f"{self.name}.json")

        # Build command dynamically based on configuration
        cmd = ["testssl"]

        # Add test flags based on configuration
        if self.test_protocols:
            cmd.append("-p")
        if self.test_server_defaults:
            cmd.append("-S")
        if self.test_vulnerabilities:
            cmd.append("-U")
        if self.test_ciphers:
            cmd.append("-E")

        # Add connection timeout if configured
        if self.connect_timeout:
            cmd.extend(["--connect-timeout", str(self.connect_timeout)])

        # Add warnings batch mode flag
        if self.warnings_batch_mode:
            cmd.append("--warnings=batch")

        # Add JSON output and target
        cmd.extend(["-oJ", output_file, target])

        # Store command for reference
        self.command_executed = " ".join(cmd)

        # Add verbose flag if enabled
        if getattr(self.cli_args, "verbose", False):
            self.debug(f"Running command: {' '.join(cmd)}")

        # Check if tool is available
        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="testssl is not installed or not found in PATH.",
                timestamp=timestamp
            )

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
                # Execute the command with configured timeout
                try:
                    proc = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout
                    )
                    if proc.returncode != 0:
                        # testssl exits 1 when it finds warnings/issues but still writes
                        # the JSON output file. If the file exists, treat as success.
                        if os.path.exists(output_file):
                            self.debug(f"testssl exited {proc.returncode} but output file exists — treating as success with findings")
                        else:
                            return self.get_result_dict(
                                disposition="fail",
                                results=proc.stderr.strip(),
                                timestamp=timestamp
                            )
                except subprocess.TimeoutExpired:
                    return self.get_result_dict(
                        disposition="fail",
                        results=f"testssl scan exceeded timeout of {self.timeout} seconds",
                        timestamp=timestamp
                    )

            # Load results from output file
            with open(output_file) as f:
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
        Analyzes vulnerabilities and TLS 1.2+ cipher test results.
        """
        # Load findings from various input types
        if isinstance(raw_output, str) and os.path.isfile(raw_output):
            with open(raw_output) as f:
                findings = json.load(f)
        elif isinstance(raw_output, dict):
            findings = raw_output.get("results", raw_output)
        else:
            try:
                findings = json.loads(raw_output)
            except Exception:
                findings = {}

        self.debug(f"{self.name} raw findings:\n{pformat(findings)}")

        # Ensure findings is a dictionary
        if not isinstance(findings, dict):
            self.debug(f"Unexpected findings type: {type(findings)}. Converting to dict.")
            findings = {"raw_data": findings}

        # Extract scan results
        scan_results = findings.get("scanResult", [])
        if not scan_results:
            self.debug("No scan results found")
            scan_results = [{}]

        scan_data = scan_results[0] if scan_results else {}

        # Check for scan problems (connection failures, etc.)
        if scan_data.get("id") == "scanProblem" and scan_data.get("severity") == "FATAL":
            scan_problem_msg = scan_data.get("finding", "Unknown scan problem")
            self.debug(f"Scan problem detected: {scan_problem_msg}")

            # Set concise summary for connection failures
            summary = "Unable to complete TLS scan."

            # Format command for report notes
            report_notes = self._format_command_for_report()

            # Build processed result for scan failure
            processed = {
                "plugin-name": self.name,
                "plugin-description": self.description,
                "plugin-display-name": getattr(self, 'display_name', None),
                "plugin-website-url": getattr(self, 'website_url', None),
                "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "findings": findings,
                "summary": summary or f"{self.name} did not produce any findings",
                "details": f"Unable to complete SSL/TLS scan:\n\n{scan_problem_msg}",
                "issues": [],
                "executive_summary": f"SSL/TLS scan could not be completed. {scan_problem_msg}",
                "report": report_notes,
                "results_message": "Scan could not be completed. See details above for more information."
            }

            processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
            write_json_atomic(processed_path, processed)

            return processed_path

        # Extract protocols, vulnerabilities, cipher tests, and server defaults
        protocols = scan_data.get("protocols", [])
        vulnerabilities = scan_data.get("vulnerabilities", [])
        cipher_tests = scan_data.get("cipherTests", [])
        server_defaults = scan_data.get("serverDefaults", [])

        # Process protocols
        proto_issues, proto_matrix_lines = self._process_protocols(protocols)

        # Process vulnerabilities
        vuln_issues = []
        for vuln in vulnerabilities:
            finding = vuln.get("finding", "")
            vuln_id = vuln.get("id", "unknown")
            severity = vuln.get("severity", "UNKNOWN")

            if severity not in ["OK", "INFO"] and finding.lower() not in ["not vulnerable", "supported"]:
                vuln_issues.append(vuln_id)
                self.debug(f"Vulnerability issue found: {vuln_id} [{severity}]")

        # Process TLS 1.2+ cipher tests
        cipher_issues = []
        for cipher in cipher_tests:
            cipher_id = cipher.get("id", "")
            severity = cipher.get("severity", "")

            if "tls1_2" in cipher_id and severity not in ["OK", "INFO"]:
                cipher_issues.append(cipher_id)
                self.debug(f"Cipher issue found: {cipher_id} [{severity}]")

        # Process server defaults (certificate info)
        cert_issues, cert_detail_lines = self._process_server_defaults(server_defaults)

        # Combine all issues
        issues = proto_issues + vuln_issues + cipher_issues + cert_issues

        # Build details section
        details_parts = []

        if proto_matrix_lines:
            details_parts.append("Protocol Support Matrix:")
            details_parts.extend(proto_matrix_lines)

        if cert_issues:
            details_parts.append(f"\nCertificate Issues ({len(cert_issues)}):")
            for line in cert_detail_lines:
                details_parts.append(f"  • {line}")

        if vuln_issues:
            details_parts.append(f"\nVulnerabilities Found ({len(vuln_issues)}):")
            for issue in vuln_issues:
                details_parts.append(f"  • {issue}")

        if cipher_issues:
            details_parts.append(f"\nTLS 1.2+ Cipher Issues ({len(cipher_issues)}):")
            for issue in cipher_issues:
                details_parts.append(f"  • {issue}")

        if not issues:
            details_parts.append("No SSL/TLS vulnerabilities, cipher issues, certificate problems, or deprecated protocols detected.")

        details = "\n".join(details_parts)

        # Build executive summary
        proto_count = len(proto_issues)
        vuln_count = len(vuln_issues)
        cipher_count = len(cipher_issues)
        cert_count = len(cert_issues)

        if not issues:
            executive_summary = "SSL/TLS configuration appears secure. No vulnerabilities, weak ciphers, certificate issues, or deprecated protocols detected."
        else:
            summary_parts = []
            if proto_count > 0:
                summary_parts.append(f"{proto_count} deprecated protocol(s)")
            if cert_count > 0:
                summary_parts.append(f"{cert_count} certificate issue(s)")
            if vuln_count > 0:
                summary_parts.append(f"{vuln_count} vulnerability issue(s)")
            if cipher_count > 0:
                summary_parts.append(f"{cipher_count} TLS 1.2+ cipher issue(s)")

            executive_summary = f"SSL/TLS scan identified {', '.join(summary_parts)}. Review recommended."

        # Calculate findings_count
        findings_count = len(issues)

        summary = self._generate_summary(findings, vuln_count=vuln_count, cipher_count=cipher_count, cert_count=cert_count, proto_count=proto_count)
        self.debug(f"{self.name} summary: {summary}")
        self.debug(f"{self.name} issues: {issues}")
        self.debug(f"{self.name} details:\n{details}")
        self.debug(f"{self.name} findings_count: {findings_count}")

        # Format command for report notes
        report_notes = self._format_command_for_report()

        # Set appropriate results message based on findings
        if not issues:
            results_message = "Scan completed successfully. No vulnerabilities or cipher issues detected."
        else:
            results_message = f"Scan completed. Found {len(issues)} issue(s). See details above."

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
            "report": report_notes,
            "results_message": results_message
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        write_json_atomic(processed_path, processed)

        return processed_path

    # Maps testssl protocol IDs to kast issue registry keys.
    _PROTOCOL_DISPLAY = {
        "SSLv2": "SSLv2",
        "SSLv3": "SSLv3",
        "TLS1": "TLS 1.0",
        "TLS1_1": "TLS 1.1",
        "TLS1_2": "TLS 1.2",
        "TLS1_3": "TLS 1.3",
    }
    _PROTOCOL_TO_KAST_ISSUE = {
        "SSLv2": "SSLv2",
        "SSLv3": "SSLv3",
        "TLS1": "TLSv1.0",
        "TLS1_1": "TLSv1.1",
    }

    def _process_protocols(self, protocols):
        """Extract legacy-protocol issues and build protocol matrix lines.

        Returns (proto_issues, matrix_lines).
        proto_issues: list of kast registry IDs for deprecated/broken protocols found offered.
        matrix_lines: list of strings suitable for the details section.
        """
        proto_issues = []
        matrix_lines = []

        for proto in protocols:
            proto_id = proto.get("id", "")
            finding = proto.get("finding", "")
            severity = proto.get("severity", "")

            display = self._PROTOCOL_DISPLAY.get(proto_id)
            if display is None:
                continue  # skip NPN/ALPN

            is_offered = finding.startswith("offered") and "not offered" not in finding

            if is_offered and severity not in ("OK", "INFO"):
                status_str = f"OFFERED [{severity}]"
            elif is_offered:
                status_str = "offered (OK)"
            else:
                status_str = "not offered (OK)"

            matrix_lines.append(f"  {display:<10} {status_str}")

            kast_id = self._PROTOCOL_TO_KAST_ISSUE.get(proto_id)
            if kast_id and is_offered and severity not in ("OK", "INFO"):
                proto_issues.append(kast_id)
                self.debug(f"Protocol issue found: {proto_id} -> {kast_id} [{severity}]")

        return proto_issues, matrix_lines

    def _process_server_defaults(self, server_defaults):
        """
        Extract certificate issues and detail lines from the serverDefaults section.
        Returns (cert_issues, cert_detail_lines).
        """
        cert_issues = []
        cert_detail_lines = []
        expiry_date = None

        for entry in server_defaults:
            id_ = entry.get("id", "")
            severity = entry.get("severity", "")
            finding = entry.get("finding", "")

            # Always capture the raw expiry date for the details section
            if id_ == "cert_notAfter":
                expiry_date = finding
                continue

            if severity in ("OK", "INFO"):
                continue

            if id_ == "cert_expirationStatus":
                finding_lower = finding.lower()
                if "expired" in finding_lower:
                    cert_issues.append("cert-expired")
                    cert_detail_lines.append(f"Certificate EXPIRED — {finding}")
                elif "expires" in finding_lower:
                    cert_issues.append("cert-expiring-soon")
                    cert_detail_lines.append(f"Certificate expiring soon — {finding}")
            elif id_ == "cert_chain_of_trust":
                cert_issues.append("cert-chain-invalid")
                cert_detail_lines.append(f"Certificate chain not trusted — {finding}")
            elif id_ == "cert_selfSigned":
                cert_issues.append("cert-self-signed")
                cert_detail_lines.append(f"Self-signed certificate — {finding}")
            elif id_ == "cert_keySize":
                cert_issues.append("cert-weak-key")
                cert_detail_lines.append(f"Weak certificate key — {finding}")

        # Prepend the expiry date as context even when there's no expiry issue
        if expiry_date:
            cert_detail_lines.insert(0, f"Certificate expires: {expiry_date}")

        self.debug(f"Certificate issues found: {cert_issues}")
        return cert_issues, cert_detail_lines

    def _generate_summary(self, findings, vuln_count=None, cipher_count=None, cert_count=None, proto_count=None):
        """Generate a human-readable summary from findings."""
        self.debug(f"_generate_summary called with findings type: {type(findings)}")
        self.debug(f"_generate_summary vuln_count: {vuln_count}, cipher_count: {cipher_count}, cert_count: {cert_count}, proto_count: {proto_count}")

        if not findings:
            self.debug("No findings, returning default message")
            return f"No findings were produced by {self.name}."

        if vuln_count is not None and cipher_count is not None:
            cert_count = cert_count or 0
            proto_count = proto_count or 0
            if vuln_count == 0 and cipher_count == 0 and cert_count == 0 and proto_count == 0:
                return "No vulnerabilities, cipher issues, certificate problems, or deprecated protocols detected."

            summary_parts = []
            if proto_count > 0:
                summary_parts.append(f"{proto_count} deprecated protocol(s)")
            if cert_count > 0:
                summary_parts.append(f"{cert_count} certificate issue(s)")
            if vuln_count > 0:
                summary_parts.append(f"{vuln_count} vulnerability issue(s)")
            if cipher_count > 0:
                summary_parts.append(f"{cipher_count} TLS 1.2+ cipher issue(s)")

            return f"Found {', '.join(summary_parts)}."

        # Fallback for backward compatibility
        if isinstance(findings, dict):
            return f"{self.name} produced {len(findings)} finding(s)."
        elif isinstance(findings, list):
            return f"{self.name} produced {len(findings)} result(s)."
        else:
            return f"{self.name} produced findings of type: {type(findings).__name__}"

    def _generate_executive_summary(self, findings):
        """
        Generate an executive summary for SSL/TLS scan results.
        Provides a high-level overview of vulnerabilities and security issues.
        """
        if not findings:
            return "No SSL/TLS scan results available."

        # Extract scan results
        scan_results = findings.get("scanResult", [])
        if not scan_results:
            return "No SSL/TLS scan results available."

        scan_data = scan_results[0] if scan_results else {}
        vulnerabilities = scan_data.get("vulnerabilities", [])

        # Count vulnerabilities by severity
        severity_counts = {}
        for vuln in vulnerabilities:
            severity = vuln.get("severity", "UNKNOWN")
            if severity not in ["OK", "INFO"]:
                severity_counts[severity] = severity_counts.get(severity, 0) + 1

        if not severity_counts:
            return "SSL/TLS configuration appears secure. No vulnerabilities detected."

        # Build summary message
        total_issues = sum(severity_counts.values())

        if total_issues == 1:
            return "SSL/TLS scan detected 1 security issue requiring attention."
        else:
            severity_details = []
            for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                if severity in severity_counts:
                    count = severity_counts[severity]
                    severity_details.append(f"{count} {severity}")

            if severity_details:
                return f"SSL/TLS scan detected {total_issues} security issues: {', '.join(severity_details)}."
            else:
                return f"SSL/TLS scan detected {total_issues} security issues."

    def _format_command_for_report(self):
        """
        Format the executed command for the report notes section.
        Returns HTML-formatted command with dark blue color and monospace font.
        """
        if not self.command_executed:
            return "Command not available"

        return f'<code style="color: #00008B; font-family: Consolas, \'Courier New\', monospace;">{self.command_executed}</code>'

    def get_dry_run_info(self, target, output_dir):
        """
        Return information about what testssl would execute.
        Builds the actual command with current configuration.
        """
        output_file = os.path.join(output_dir, f"{self.name}.json")

        # Build command with current configuration
        cmd = ["testssl"]

        # Add test flags based on configuration
        if self.test_protocols:
            cmd.append("-p")
        if self.test_server_defaults:
            cmd.append("-S")
        if self.test_vulnerabilities:
            cmd.append("-U")
        if self.test_ciphers:
            cmd.append("-E")

        # Add connection timeout if configured
        if self.connect_timeout:
            cmd.extend(["--connect-timeout", str(self.connect_timeout)])

        # Add warnings batch mode flag
        if self.warnings_batch_mode:
            cmd.append("--warnings=batch")

        # Add JSON output and target
        cmd.extend(["-oJ", output_file, target])

        return {
            "commands": [' '.join(cmd)],
            "description": self.description,
            "operations": f"SSL/TLS security testing (timeout: {self.timeout}s)"
        }
