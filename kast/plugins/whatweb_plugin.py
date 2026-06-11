"""WhatWeb plugin — uses ExternalToolPlugin.

Inherits subprocess invocation, output reading, and processed-dict assembly
from ``ExternalToolPlugin``. The
plugin-specific logic (config-driven command building, the
target/HTTP-status-bucketed summary, domain-redirect recommendations)
moves into the format hooks.
"""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse, urlunparse

from kast.plugins.external_tool import ExternalToolPlugin


class WhatWebPlugin(ExternalToolPlugin):
    priority = 15  # High priority

    # (safe_major, safe_minor): detected version < boundary → EOL
    _EOL_TECHNOLOGIES: dict = {
        "PHP": (8, 0),
        "JQuery": (3, 0),
        "jQuery UI": (1, 13),
        "Bootstrap": (4, 0),
        "AngularJS": (2, 0),
        "Angular": (2, 0),
        "Lodash": (4, 17),
        "Apache": (2, 4),
        "WordPress": (6, 0),
        "Drupal": (9, 0),
        "Ruby on Rails": (6, 0),
    }

    name = "whatweb"
    display_name = "WhatWeb"
    description = "Identifies technologies used by a website."
    website_url = "https://github.com/urbanadventurer/whatweb"
    scan_type = "passive"
    output_type = "file"

    tool_binary = "whatweb"
    output_filename = "whatweb.json"
    output_format = "json"

    config_schema = {
        "type": "object",
        "title": "WhatWeb Configuration",
        "description": "Web technology detection configuration",
        "properties": {
            "aggression_level": {
                "type": "integer", "default": 3, "minimum": 1, "maximum": 4,
                "description": "Aggression level (1=stealthy, 3=aggressive, 4=heavy)",
            },
            "timeout": {
                "type": "integer", "default": 30, "minimum": 5, "maximum": 120,
                "description": "HTTP request timeout in seconds",
            },
            "user_agent": {
                "type": ["string", "null"], "default": None,
                "description": "Custom User-Agent string (null for default)",
            },
            "follow_redirects": {
                "type": "integer", "default": 2, "minimum": 0, "maximum": 10,
                "description": "Maximum redirect depth to follow",
            },
        },
    }

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self._load_plugin_config()

    def _load_plugin_config(self) -> None:
        self.aggression_level = self.get_config("aggression_level", 3)
        self.timeout = self.get_config("timeout", 30)
        self.user_agent = self.get_config("user_agent", None)
        self.follow_redirects = self.get_config("follow_redirects", 2)
        self.debug(
            f"WhatWeb config loaded: aggression={self.aggression_level}, "
            f"timeout={self.timeout}, "
            f"user_agent={'(custom)' if self.user_agent else '(default)'}, "
            f"follow_redirects={self.follow_redirects}"
        )

    # -- ExternalToolPlugin hooks ------------------------------------------

    def build_command(self, target: str, output_path: str) -> list[str]:
        cmd = ["whatweb", "-a", str(self.aggression_level)]
        if self.timeout:
            cmd.extend(["--read-timeout", str(self.timeout)])
        if self.user_agent:
            cmd.extend(["--user-agent", self.user_agent])
        if self.follow_redirects:
            cmd.extend(["--max-redirects", str(self.follow_redirects)])
        # target must come last in WhatWeb's CLI
        cmd.extend(["--log-json", output_path, target])
        return cmd

    def parse_findings(self, raw):
        """Wrap raw output in the v2-compatible {disposition, results} shape.

        WhatWeb's --log-json writes a top-level JSON array; v2 wrapped it
        for storage in the processed dict. Preserved here for byte-compat
        with kast-web parsers and the v3 baseline.
        """
        return {
            "disposition": "success" if raw else "fail",
            "results": raw or [],
        }

    def count_findings(self, findings) -> int:
        """Count URL entries analyzed by WhatWeb."""
        return len(self._results_list(findings))

    def format_summary(self, findings):
        """One line per URL showing HTTP status and detected technologies."""
        results = self._results_list(findings)
        if not results:
            return f"No findings were produced by {self.name}."

        buckets: dict[str, list] = defaultdict(list)
        for entry in results:
            raw_target = entry.get("target", "unknown")
            parsed = urlparse(raw_target)
            normalized = urlunparse(parsed._replace(path=parsed.path.rstrip("/")))
            buckets[normalized].append(entry)

        lines = []
        for target, entries in buckets.items():
            for idx, entry in enumerate(entries, start=1):
                status = entry.get("http_status", "N/A")
                tech_list = []
                for plugin_name, data in (entry.get("plugins") or {}).items():
                    if not data:
                        continue
                    if "version" in data and data["version"]:
                        tech_list.append(f"{plugin_name} (v{', '.join(data['version'])})")
                    elif "string" in data and data["string"]:
                        tech_list.append(f"{plugin_name} [{', '.join(data['string'])}]")
                    else:
                        tech_list.append(plugin_name)
                techs = "; ".join(tech_list) if tech_list else "no detectable technologies"
                label = target if len(entries) == 1 else f"{target} (#{idx})"
                lines.append(f"{label} — HTTP {status}: {techs}")
        return "\n".join(lines)

    def format_executive_summary(self, findings, issues):
        """Summarize EOL technology detections; append cross-domain redirect recommendations."""
        eol_detections = self._collect_eol_detections(findings)
        recommendations = self._detect_domain_redirects(findings)

        parts = []
        if eol_detections:
            eol_list = "; ".join(f"{tech} {ver}" for tech, ver in eol_detections)
            parts.append(f"End-of-life technologies detected: {eol_list}")
        parts.extend(recommendations)
        return "\n".join(parts)

    def get_dry_run_info(self, target, output_dir):
        info = super().get_dry_run_info(target, output_dir)
        info["operations"] = (
            f"Technology detection (aggression level {self.aggression_level}, "
            f"timeout {self.timeout}s, max redirects {self.follow_redirects})"
        )
        return info

    def extract_issues(self, findings) -> list[str]:
        """Emit whatweb-eol-technology when a detected technology version is EOL."""
        return ["whatweb-eol-technology"] if self._collect_eol_detections(findings) else []

    def _collect_eol_detections(self, findings) -> list[tuple[str, str]]:
        """Return unique (tech_name, version_str) pairs for each EOL detection found."""
        detections = []
        seen: set[tuple[str, str]] = set()
        for entry in self._results_list(findings):
            plugins = entry.get("plugins") or {}
            for plugin_name, data in plugins.items():
                if not isinstance(data, dict):
                    continue
                versions = data.get("version") or []
                if not isinstance(versions, list):
                    versions = [versions]
                boundary = self._EOL_TECHNOLOGIES.get(plugin_name)
                if boundary is None:
                    continue
                for version_str in versions:
                    parsed = self._parse_version(str(version_str))
                    if parsed and parsed < boundary:
                        key = (plugin_name, str(version_str))
                        if key not in seen:
                            seen.add(key)
                            detections.append(key)
                            self.debug(
                                f"EOL: {plugin_name} {version_str} "
                                f"(safe boundary: {boundary[0]}.{boundary[1]})"
                            )
        return detections

    # -- WhatWeb-specific helpers ------------------------------------------

    @staticmethod
    def _parse_version(version_str: str):
        """Parse 'major.minor[.patch]' to (major, minor) tuple, or None on failure."""
        try:
            parts = str(version_str).split(".")
            return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (ValueError, IndexError, AttributeError):
            return None

    @staticmethod
    def _results_list(findings) -> list:
        """Return the inner results list regardless of wrapping shape."""
        if isinstance(findings, dict):
            return findings.get("results") or []
        if isinstance(findings, list):
            return findings
        return []

    def _detect_domain_redirects(self, findings) -> list[str]:
        """Detect redirects that change the domain and recommend follow-up scans."""
        recommendations = []
        seen: set[tuple[str, str]] = set()
        for entry in self._results_list(findings):
            if entry.get("http_status") not in (301, 302):
                continue
            target = entry.get("target", "")
            redirect_loc = (entry.get("plugins") or {}).get("RedirectLocation", {}).get("string", [])
            if not redirect_loc:
                continue
            redirect_url = redirect_loc[0] if isinstance(redirect_loc, list) else redirect_loc
            try:
                target_domain = urlparse(target).netloc.lower()
                redirect_domain = urlparse(redirect_url).netloc.lower()
            except Exception as e:
                self.debug(f"Error parsing redirect URLs: {e}")
                continue
            # v2 only skips when both sides resolve to the same domain (e.g.
            # http→https on the same host). Empty redirect_domain (relative
            # URLs like "login.php") still produces a recommendation — that
            # output is malformed but preserved here for v2 byte-compat.
            if target_domain == redirect_domain:
                continue
            key = (target_domain, redirect_domain)
            if key in seen:
                continue
            seen.add(key)
            recommendations.append(
                f"Recommend running a scan on {redirect_domain}, which was the "
                f"target redirection location from {target_domain}"
            )
        return recommendations
