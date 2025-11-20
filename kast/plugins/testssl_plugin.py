"""
File: plugins/testssl_plugin.py
Description: KAST plugin for testssl.sh - SSL/TLS security assessment tool
"""

import subprocess
import shutil
import json
import os
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class TestsslPlugin(KastPlugin):
    priority = 50  # Set plugin run order (lower runs earlier)

    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "testssl"
        self.display_name = "Test SSL"
        self.description = "Tests SSL and TLS posture"
        self.website_url = "https://testssl.sh/"
        self.scan_type = "passive"
        self.output_type = "file"
        self.command_executed = None

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
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, f"{self.name}.json")
        
        # Build command as specified
        cmd = ["testssl",
               "-U",
               "-E",
               "-oJ", output_file,
               target]

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
                    with open(output_file, "r") as f:
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
        Analyzes vulnerabilities and TLS 1.2+ cipher test results.
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
                "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
                "findings": findings,
                "summary": summary or f"{self.name} did not produce any findings",
                "details": f"Unable to complete SSL/TLS scan:\n\n{scan_problem_msg}",
                "issues": [],
                "executive_summary": f"SSL/TLS scan could not be completed. {scan_problem_msg}",
                "report": report_notes
            }
            
            processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
            with open(processed_path, "w") as f:
                json.dump(processed, f, indent=2)
            
            return processed_path
        
        # Extract vulnerabilities and cipher tests
        vulnerabilities = scan_data.get("vulnerabilities", [])
        cipher_tests = scan_data.get("cipherTests", [])
        
        # Process vulnerabilities
        vuln_issues = []
        for vuln in vulnerabilities:
            finding = vuln.get("finding", "")
            vuln_id = vuln.get("id", "unknown")
            severity = vuln.get("severity", "UNKNOWN")
            
            # Exclude OK and INFO severity items and findings that indicate no vulnerability
            if severity not in ["OK", "INFO"] and finding.lower() not in ["not vulnerable", "supported"]:
                # Use only the vulnerability ID as the issue identifier
                vuln_issues.append(vuln_id)
                self.debug(f"Vulnerability issue found: {vuln_id} [{severity}]")
        
        # Process TLS 1.2+ cipher tests
        cipher_issues = []
        for cipher in cipher_tests:
            cipher_id = cipher.get("id", "")
            severity = cipher.get("severity", "")
            finding = cipher.get("finding", "")
            
            # Only process TLS 1.2+ ciphers with non-OK severity
            if "tls1_2" in cipher_id and severity not in ["OK", "INFO"]:
                # Use only the cipher ID as the issue identifier
                cipher_issues.append(cipher_id)
                self.debug(f"Cipher issue found: {cipher_id} [{severity}]")
        
        # Combine all issues
        issues = vuln_issues + cipher_issues
        
        # Build details section
        details_parts = []
        
        if vuln_issues:
            details_parts.append(f"Vulnerabilities Found ({len(vuln_issues)}):")
            for issue in vuln_issues:
                details_parts.append(f"  • {issue}")
        
        if cipher_issues:
            details_parts.append(f"\nTLS 1.2+ Cipher Issues ({len(cipher_issues)}):")
            for issue in cipher_issues:
                details_parts.append(f"  • {issue}")
        
        if not issues:
            details_parts.append("No SSL/TLS vulnerabilities or cipher issues detected.")
        
        details = "\n".join(details_parts)
        
        # Build executive summary
        if not issues:
            executive_summary = "SSL/TLS configuration appears secure. No vulnerabilities or weak ciphers detected in TLS 1.2+."
        else:
            vuln_count = len(vuln_issues)
            cipher_count = len(cipher_issues)
            
            summary_parts = []
            if vuln_count > 0:
                summary_parts.append(f"{vuln_count} vulnerability issue(s)")
            if cipher_count > 0:
                summary_parts.append(f"{cipher_count} TLS 1.2+ cipher issue(s)")
            
            executive_summary = f"SSL/TLS scan identified {' and '.join(summary_parts)}. Review recommended."

        # Generate summary using helper method
        summary = self._generate_summary(findings)
        self.debug(f"{self.name} summary: {summary}")
        self.debug(f"{self.name} issues: {issues}")
        self.debug(f"{self.name} details:\n{details}")

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

    def _generate_summary(self, findings):
        """
        Generate a human-readable summary from findings.
        """
        self.debug(f"_generate_summary called with findings type: {type(findings)}")
        self.debug(f"_generate_summary findings content: {pformat(findings)}")
        
        if not findings:
            self.debug("No findings, returning default message")
            return f"No findings were produced by {self.name}."
        
        # Basic summary - will be enhanced during post-processing implementation
        if isinstance(findings, dict):
            count = len(findings)
            return f"{self.name} produced {count} finding(s)."
        elif isinstance(findings, list):
            count = len(findings)
            return f"{self.name} produced {count} result(s)."
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

    def _deduplicate_findings(self, findings):
        """
        Remove duplicate findings from the results.
        This is a stub function to be implemented when needed.
        """
        # TODO: Implement deduplication logic if needed for testssl results
        return findings
