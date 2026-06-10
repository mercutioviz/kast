"""ExternalToolPlugin base (Phase B8).

Most kast plugins are wrappers around a CLI tool: invoke it via
subprocess, capture output, parse, post-process. v2 plugins
re-implemented this scaffolding (~300 lines of boilerplate per plugin)
because there was no shared base. Audit § 4.3 flagged this as a major
duplication source.

This base absorbs the boilerplate. Subclasses declare:

    class MyPlugin(ExternalToolPlugin):
        # Identity (ExternalToolPlugin inherits the class-attribute pattern)
        name = "mytool"
        display_name = "My Tool"
        description = "What it does"
        website_url = "https://example.com/mytool"
        scan_type = "passive"
        output_type = "file"

        # Tool-specific declarations
        tool_binary = "mytool"            # for shutil.which / is_available
        output_filename = "mytool.json"   # raw tool output, written to scan dir
        output_format = "json"            # "json" | "text"

        config_schema = {...}             # standard

        def build_command(self, target, output_file):
            return ["mytool", "-o", str(output_file), target]

        def count_findings(self, findings):
            return len(findings)

        def extract_issues(self, findings):
            return []  # plugins that report no issue records

        def format_summary(self, findings):
            return f"{len(findings)} item(s) found"

        # Optional (sensible defaults provided)
        # format_details, format_executive_summary, extra_processed_fields

The base provides ``run()`` and ``post_process()``, including:
- Auto-derived ``is_available()`` via shutil.which(tool_binary)
- Subprocess invocation with timeout + return-code handling
- Output-file existence check after the tool runs
- Failure disposition handling in post_process (writes a minimal
  processed dict so kast-web's state machine still gets a completion
  marker)
- Atomic write of ``<plugin>_processed.json`` (Phase A11 helper)
- ``_format_command_for_report`` for the report's per-tool details
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from kast.core.atomic import write_json_atomic
from kast.plugins.base import KastPlugin


class ExternalToolPlugin(KastPlugin):
    """Base for plugins that wrap a CLI tool via subprocess."""

    # ---- subclass-overridable class attributes ----------------------------

    #: Name of the tool binary (used by ``is_available()`` and run()).
    tool_binary: str = ""

    #: Filename within the output dir that the tool writes its raw output to.
    output_filename: str = ""

    #: How to read ``output_filename`` after the tool runs.
    output_format: Literal["json", "text"] = "json"

    #: Subprocess timeout in seconds (default 600 = 10 minutes).
    subprocess_timeout: int = 600

    # ---- instance state ---------------------------------------------------

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        # Latest command for the per-tool details section in the report.
        self.command_executed: str | None = None

    # ---- KastPlugin contract ---------------------------------------------

    def is_available(self) -> bool:
        """Default: shutil.which(tool_binary). Override for multi-tool plugins."""
        if not self.tool_binary:
            return True  # plugins with no external dep override this
        return shutil.which(self.tool_binary) is not None

    def run(self, target: str, output_dir, report_only: bool):
        """Subprocess invocation + raw output read.

        Subclasses provide ``build_command``; the base handles invocation,
        timeout, return-code check, missing-output detection, and raw
        output loading.
        """
        timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        output_path = os.path.join(str(output_dir), self.output_filename)

        if not self.is_available():
            return self.get_result_dict(
                "fail",
                f"{self.tool_binary} not installed or not in PATH.",
                timestamp,
            )

        cmd = self.build_command(target, output_path)
        self.command_executed = " ".join(str(c) for c in cmd)
        self.debug(f"Running: {self.command_executed}")

        try:
            if report_only:
                self.debug(f"[REPORT ONLY] Would run: {self.command_executed}")
            else:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.subprocess_timeout,
                )
                if proc.returncode != 0:
                    err = proc.stderr.strip() or proc.stdout.strip()
                    return self.get_result_dict(
                        "fail", err or f"exit code {proc.returncode}", timestamp,
                    )
                if not os.path.exists(output_path):
                    return self.get_result_dict(
                        "fail",
                        f"{self.tool_binary} completed but did not create "
                        f"{output_path}",
                        timestamp,
                    )

            raw = self._read_raw_output(output_path)
            return self.get_result_dict("success", raw, timestamp)

        except subprocess.TimeoutExpired:
            return self.get_result_dict(
                "fail",
                f"{self.tool_binary} timed out after {self.subprocess_timeout}s",
                timestamp,
            )
        except Exception as e:
            self.debug(f"{self.name} run() failed: {e}")
            return self.get_result_dict("fail", str(e), timestamp)

    def post_process(self, raw_output, output_dir) -> str:
        """Standard processed-dict assembly via subclass hooks.

        Handles the failed-disposition case (writes a minimal processed dict
        so kast-web sees a completion marker) and routes successful runs
        through ``parse_findings`` / ``count_findings`` / ``extract_issues``
        / ``format_summary`` / ``format_executive_summary``.
        """
        # Failed-run path: raw_output is the dict from get_result_dict("fail", ...)
        if isinstance(raw_output, dict) and raw_output.get("disposition") == "fail":
            return self._write_failed_processed(raw_output, output_dir)

        findings_raw = self._unwrap_results(raw_output)
        findings = self.parse_findings(findings_raw)
        issues = self.extract_issues(findings)
        findings_count = self.count_findings(findings)
        summary = self.format_summary(findings)
        details = self.format_details(findings)
        executive_summary = self.format_executive_summary(findings, issues)

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": self.display_name,
            "plugin-website-url": self.website_url,
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "findings": findings,
            "findings_count": findings_count,
            "summary": summary,
            "details": details,
            "issues": issues,
            "executive_summary": executive_summary,
            "report": self._format_command_for_report(),
        }
        # Subclass-provided extras (custom_html, plugin-specific keys)
        processed.update(self.extra_processed_fields(findings, issues))

        processed_path = os.path.join(str(output_dir), f"{self.name}_processed.json")
        write_json_atomic(processed_path, processed)
        return processed_path

    # ---- subclass hooks (required) ---------------------------------------

    def build_command(self, target: str, output_path: str) -> list[str]:
        """Return the argv list to execute the tool. **Required.**

        Use ``self.get_config(key, default)`` to thread CLI/config overrides
        into the command.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.build_command must be overridden"
        )

    def count_findings(self, findings: Any) -> int:
        """Return the integer count of primary findings.

        URL discovery → URL count, vuln scanner → issue count, etc. Always
        return an int (never None).
        """
        if findings is None:
            return 0
        if isinstance(findings, (list, dict)):
            return len(findings)
        return 1

    # ---- subclass hooks (optional, with sensible defaults) ----------------

    def parse_findings(self, raw: Any) -> Any:
        """Normalize raw tool output. Default: pass-through."""
        return raw

    def extract_issues(self, findings: Any) -> list:
        """Extract issue records. Default: empty list (no issues reported)."""
        return []

    def format_summary(self, findings: Any) -> Any:
        """Build the report's summary (string or list-of-dicts).

        Default: a generic per-type message. Override for plugin-specific
        formatting (e.g., the WhatWeb "{target} - HTTP {status}: techs"
        bucket).
        """
        if findings is None:
            return f"No findings were produced by {self.name}."
        if isinstance(findings, list):
            return f"{self.name} produced {len(findings)} result(s)."
        if isinstance(findings, dict):
            return f"{self.name} produced {len(findings)} top-level field(s)."
        return f"{self.name} produced findings of type: {type(findings).__name__}"

    def format_details(self, findings: Any) -> str:
        """Build the report's per-plugin details. Default: empty."""
        return ""

    def format_executive_summary(self, findings: Any, issues: list) -> Any:
        """Build the report's per-plugin executive summary.

        Default: empty string (no summary contribution). Override to surface
        plugin-specific recommendations (e.g., WhatWeb's redirect-target
        recommendations).
        """
        return ""

    def extra_processed_fields(self, findings: Any, issues: list) -> dict:
        """Return additional keys to merge into the processed dict.

        Default: ``{}``. Override to add ``custom_html``, ``custom_html_pdf``,
        ``commands_executed``, or any plugin-specific report fields.
        """
        return {}

    def get_dry_run_info(self, target: str, output_dir) -> dict:
        """Default dry-run info: just shows the command that would run."""
        output_path = os.path.join(str(output_dir), self.output_filename)
        cmd = self.build_command(target, output_path)
        return {
            "commands": [" ".join(str(c) for c in cmd)],
            "description": self.description,
            "operations": "",
        }

    # ---- internal helpers -------------------------------------------------

    def _read_raw_output(self, output_path: str) -> Any:
        """Read the tool's output file per ``output_format``."""
        text = Path(output_path).read_text(encoding="utf-8")
        if self.output_format == "json":
            return json.loads(text) if text.strip() else {}
        return text

    def _unwrap_results(self, raw_output: Any) -> Any:
        """Accept either a ``get_result_dict`` payload or a raw value.

        v2 plugins are inconsistent here — some pass the wrapped dict to
        post_process, some unwrap first. The base normalizes both.
        """
        if isinstance(raw_output, dict) and "results" in raw_output and "disposition" in raw_output:
            return raw_output.get("results")
        return raw_output

    def _write_failed_processed(self, raw_output: dict, output_dir) -> str:
        """Write a minimal processed dict for a failed run.

        kast-web's state machine looks for ``<plugin>_processed.json``;
        this ensures a completion marker exists even when the tool failed,
        carrying the error message for the report.
        """
        error = raw_output.get("results", "Unknown error")
        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": self.display_name,
            "plugin-website-url": self.website_url,
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "findings": {"disposition": "fail", "results": error},
            "findings_count": 0,
            "summary": [{"Error": f"Plugin execution failed: {error}"}],
            "details": "",
            "issues": [],
            "executive_summary": "",
            "report": self._format_command_for_report(),
        }
        processed_path = os.path.join(str(output_dir), f"{self.name}_processed.json")
        write_json_atomic(processed_path, processed)
        return processed_path

    def _format_command_for_report(self) -> str:
        """Format ``self.command_executed`` for the report's per-plugin details.

        Wraps in styled HTML for parity with v2 output. v3 should eventually
        move this styling into the report template (audit § 4.4 layering),
        but for B8 we preserve the existing surface.
        """
        if not self.command_executed:
            return "Command not available"
        return (
            f'<code style="color: #00008B; '
            f'font-family: Consolas, \'Courier New\', monospace;">'
            f"{self.command_executed}</code>"
        )
