"""
File: plugins/katana_plugin.py
Description: Site crawler and URL finder plugin for KAST.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pprint import pformat
from urllib.parse import urlsplit

import tldextract

from kast.core.atomic import write_json_atomic
from kast.plugins.base import KastPlugin

# How often to check katana.txt's line count while the crawl is running.
KATANA_POLL_INTERVAL_SECONDS = 3
# If the URL count hasn't grown in this long, flag the crawl as stalled
# (still running, but no new URLs — likely near the end of the frontier,
# or genuinely stuck on a slow/unresponsive page).
KATANA_STALL_THRESHOLD_SECONDS = 45

# A dated path run is editorial content, not an endpoint: /health/2026/03/02/slug
# is a news article and /health is a health check. Every mainstream CMS emits this
# shape, so it is the one reliable way to tell them apart from the path alone.
# Applied to every category — a genuine admin path dated this way is rare enough
# that suppressing it costs less than listing a prospect's news archive as
# "security-relevant".
EDITORIAL_DATE_PATH = re.compile(r"/(?:19|20)\d{2}/\d{1,2}(?:/\d{1,2})?(?:/|$)")

# Bundled assets are not attack surface worth highlighting. Without this, a site
# that serves CSS and JS out of /files/ fills the section with build artifacts.
STATIC_ASSET_EXTENSIONS = {
    ".css", ".js", ".mjs", ".map", ".json.gz", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".ico", ".webp", ".avif", ".bmp", ".woff", ".woff2", ".ttf", ".eot",
    ".otf", ".mp4", ".webm", ".mp3", ".wav", ".m4a",
}

# Categories ordered by security priority (first-match wins per URL).
#
# Matching is on whole path segments, never substrings: the old table matched
# "/health/" anywhere in a URL, so every news article under a /health/ section
# was reported as a diagnostics endpoint. Query strings are excluded too — a
# share link carrying ?url=...%2Fadmin%2F is not an admin panel.
#
#   segments          — any path segment equal to one of these
#   filenames         — the last segment equal to one of these
#   filename_prefixes — the last segment starting with one of these
#   max_depth         — only match paths no deeper than this
INTERESTING_PATH_PATTERNS = {
    "Config / Exposed Files": {
        "segments": {
            ".git", ".svn", ".env", "swagger", "swagger-ui", "openapi",
            "api-docs", "redoc",
        },
        "filenames": {
            ".env", ".htaccess", ".npmrc", "web.config", "swagger.json",
            "openapi.json", "openapi.yaml", "docker-compose.yml",
        },
        "filename_prefixes": {"config.", "settings."},
    },
    "Admin / CMS": {
        "segments": {
            "admin", "wp-admin", "administrator", "backoffice", "cms",
            "cpanel", "dashboard", "manage", "management",
        },
        "filenames": {"wp-login.php"},
    },
    "Debug / Diagnostics": {
        "segments": {
            "debug", "actuator", "_profiler", "console", "metrics", "trace",
            "health", "healthz", "livez", "readyz", "server-status",
            "server-info",
        },
        "filenames": {"phpinfo.php", "server-status"},
        # Real diagnostics endpoints sit near the root (/health, /actuator/health).
        "max_depth": 3,
    },
    "Authentication": {
        "segments": {
            "login", "signin", "sign-in", "auth", "oauth", "oauth2", "sso",
            "saml", "logout", "signout", "sign-out", "register", "signup",
            "sign-up", "forgot-password", "reset-password",
        },
    },
    "API Endpoints": {
        "segments": {"api", "graphql", "gql", "rest", "rpc", "jsonrpc"},
    },
    # "files" and "media" were dropped deliberately: on real sites they are the
    # static-asset root, and they produced only false positives. What is left
    # names actual upload or storage functionality.
    "Upload / Storage": {
        "segments": {
            "upload", "uploads", "attachments", "private", "backup", "backups",
        },
    },
}

class KatanaPlugin(KastPlugin):
    priority = 60  # Set plugin run order (lower runs earlier)

    # Configuration schema for kast-web integration
    config_schema = {
        "type": "object",
        "title": "Katana Configuration",
        "description": "Web crawler configuration",
        "properties": {
            "depth": {
                "type": "integer",
                "default": 3,
                "minimum": 1,
                "maximum": 10,
                "description": "Maximum depth to crawl"
            },
            "js_crawl": {
                "type": "boolean",
                "default": False,
                "description": "Enable endpoint parsing/crawling in JavaScript files"
            },
            "crawl_duration": {
                "type": "integer",
                "default": 300,
                "minimum": 0,
                "description": (
                    "Katana's own crawl budget in seconds, passed as -ct (0 = no limit). "
                    "Katana stops crawling and exits cleanly when this elapses."
                )
            },
            "max_runtime": {
                "type": "integer",
                "default": 600,
                "minimum": 0,
                "description": (
                    "Hard wall-clock cap in seconds on the katana process (0 = no cap). "
                    "Backstop for when katana overruns its own -ct budget; partial "
                    "results are kept."
                )
            },
            "stall_timeout": {
                "type": "integer",
                "default": 180,
                "minimum": 0,
                "description": (
                    "Terminate the crawl after this many seconds with no new URL "
                    "(0 = never). Partial results are kept."
                )
            },
            "known_files": {
                "type": "string",
                "enum": ["", "all", "robotstxt", "sitemapxml"],
                "default": "",
                "description": "Enable crawling of known files (requires depth >= 3)"
            },
            "automatic_form_fill": {
                "type": "boolean",
                "default": False,
                "description": "Enable automatic form filling (experimental)"
            },
            "strategy": {
                "type": "string",
                "enum": ["depth-first", "breadth-first"],
                "default": "depth-first",
                "description": "Visit strategy for crawling"
            },
            "concurrency": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
                "description": "Number of concurrent fetchers"
            },
            "parallelism": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
                "description": "Number of concurrent inputs to process"
            },
            "rate_limit": {
                "type": "integer",
                "default": 150,
                "minimum": 1,
                "maximum": 500,
                "description": "Maximum requests per second"
            },
            "delay": {
                "type": "integer",
                "default": 0,
                "minimum": 0,
                "maximum": 60,
                "description": "Request delay in seconds between each request"
            },
            "timeout": {
                "type": "integer",
                "default": 10,
                "minimum": 5,
                "maximum": 300,
                "description": "Request timeout in seconds"
            },
            "retry": {
                "type": "integer",
                "default": 1,
                "minimum": 0,
                "maximum": 5,
                "description": "Number of times to retry failed requests"
            },
            "proxy": {
                "type": ["string", "null"],
                "default": None,
                "description": "HTTP/SOCKS5 proxy to use (e.g., http://proxy:8080)"
            },
            "field_scope": {
                "type": "string",
                "enum": ["dn", "rdn", "fqdn"],
                "default": "rdn",
                "description": "Scope field for crawling (dn=domain, rdn=root domain, fqdn=full domain)"
            },
            "headless": {
                "type": "boolean",
                "default": True,
                "description": "Enable headless browser crawling for full JavaScript app coverage (disable with --set katana.headless=false)"
            },
            "xhr_extraction": {
                "type": "boolean",
                "default": False,
                "description": "Extract XHR request URLs in headless mode"
            },
            "extension_filter": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": "Filter out URLs with these extensions (e.g., png, css, jpg)"
            },
            "omit_body": {
                "type": "boolean",
                "default": True,
                "description": "Omit response body from output (saves space)"
            },
            "report_scope": {
                "type": "string",
                "enum": ["target", "organization", "all"],
                "default": "organization",
                "description": (
                    "Which discovered URLs reach the report: 'target' = the target host "
                    "only, 'organization' = any host sharing the target's registrable "
                    "domain, 'all' = every host seen. Crawl breadth is set separately by "
                    "field_scope; this only controls what is reported."
                )
            }
        }
    }

    name = "katana"
    description = "Site crawler and URL finder."
    display_name = "Katana"
    tested_tool_version = "1.6.1"
    website_url = "https://github.com/projectdiscovery/katana"
    scan_type = "passive"  # or "active"
    output_type = "file"  # or "stdout"

    def __init__(self, cli_args, config_manager=None):

        super().__init__(cli_args, config_manager)

        self.command_executed = None  # Store the command for reporting

        # suffix_list_urls=() pins tldextract to its bundled snapshot. post_process
        # must not make a network call to decide what goes in the report.
        self._tld_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

        # Load configuration values
        self._load_plugin_config()

    def _load_plugin_config(self):
        """Load configuration with defaults from schema."""
        # Get config values (defaults from schema if not set)
        self.depth = self.get_config('depth', 3)
        self.js_crawl = self.get_config('js_crawl', False)
        self.crawl_duration = self.get_config('crawl_duration', 300)
        self.max_runtime = self.get_config('max_runtime', 600)
        self.stall_timeout = self.get_config('stall_timeout', 180)
        self.known_files = self.get_config('known_files', "")
        self.automatic_form_fill = self.get_config('automatic_form_fill', False)
        self.strategy = self.get_config('strategy', "depth-first")
        self.concurrency = self.get_config('concurrency', 10)
        self.parallelism = self.get_config('parallelism', 10)
        self.rate_limit = self.get_config('rate_limit', 150)
        self.delay = self.get_config('delay', 0)
        self.timeout = self.get_config('timeout', 10)
        self.retry = self.get_config('retry', 1)
        self.proxy = self.get_config('proxy', None)
        self.field_scope = self.get_config('field_scope', "rdn")
        self.headless = self.get_config('headless', True)
        self.xhr_extraction = self.get_config('xhr_extraction', False)
        self.extension_filter = self.get_config('extension_filter', [])
        self.omit_body = self.get_config('omit_body', True)
        self.report_scope = self.get_config('report_scope', "organization")

        self.debug(f"Katana config loaded: "
                  f"depth={self.depth}, "
                  f"js_crawl={self.js_crawl}, "
                  f"duration={self.crawl_duration}s, "
                  f"max_runtime={self.max_runtime}s, "
                  f"stall_timeout={self.stall_timeout}s, "
                  f"known_files='{self.known_files or '(none)'}', "
                  f"form_fill={self.automatic_form_fill}, "
                  f"strategy={self.strategy}, "
                  f"concurrency={self.concurrency}, "
                  f"parallelism={self.parallelism}, "
                  f"rate_limit={self.rate_limit}/s, "
                  f"delay={self.delay}s, "
                  f"timeout={self.timeout}s, "
                  f"retry={self.retry}, "
                  f"proxy={'(set)' if self.proxy else '(none)'}, "
                  f"field_scope={self.field_scope}, "
                  f"headless={self.headless}, "
                  f"xhr={self.xhr_extraction}, "
                  f"ext_filter={self.extension_filter or '(none)'}, "
                  f"omit_body={self.omit_body}, "
                  f"report_scope={self.report_scope}")

    def is_available(self):
        """
        Check if required tool is installed and available in PATH.
        """
        return shutil.which("katana") is not None

    def _count_lines(self, path):
        """Count non-empty lines in a file, tolerating concurrent writes."""
        if not os.path.exists(path):
            return 0
        count = 0
        try:
            with open(path) as f:
                for line in f:
                    if line.strip():
                        count += 1
        except OSError:
            # File may be mid-write/rotated by katana; treat as no update this tick.
            return None
        return count

    def _write_progress(
        self, output_dir, status, urls_found, stalled_seconds=0, termination=None
    ):
        """
        Write a small progress snapshot so kast-web can show crawl activity
        instead of an opaque "in progress" state. Katana's total URL count
        isn't known ahead of time (it's a discovery crawl), so we report the
        running count plus a stall signal rather than a percentage.

        :param output_dir: Directory to write the progress file
        :param status: One of "crawling", "stalled", "done", "terminated"
        :param urls_found: Current count of lines in katana.txt
        :param stalled_seconds: Seconds since urls_found last changed
        :param termination: Why the crawl was cut short, if it was
        """
        progress_file = os.path.join(output_dir, "katana_progress.json")
        data = {
            "status": status,
            "urls_found": urls_found,
            "stalled_seconds": stalled_seconds,
            "termination": termination,
            "last_updated": datetime.now(UTC).isoformat(timespec="milliseconds"),
        }
        write_json_atomic(progress_file, data)

    @staticmethod
    def _termination_from_progress(output_dir):
        """Read the termination reason a previous run recorded, if any."""
        path = os.path.join(output_dir, "katana_progress.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return json.load(f).get("termination")
        except (OSError, ValueError):
            return None

    def _terminate(self, proc):
        """
        Stop katana and every process it spawned, escalating if it ignores SIGTERM.

        Signals go to the process group, not the pid: katana's headless mode runs
        a Chrome child that outlives its parent otherwise, and an orphaned browser
        per scan is how a demo box runs out of memory.
        """
        for sig, grace in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
            try:
                os.killpg(os.getpgid(proc.pid), sig)
            except (ProcessLookupError, PermissionError):
                return
            try:
                proc.wait(timeout=grace)
                return
            except subprocess.TimeoutExpired:
                continue

    def run(self, target, output_dir, report_only):
        """
        Run the tool and return standardized result dict.
        """
        timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, "katana.txt")

        # Build command dynamically based on configuration
        cmd = ["katana", "-silent", "-u", target]

        # Add crawl configuration
        if self.depth != 3:  # Only add if different from default
            cmd.extend(["-d", str(self.depth)])

        if self.js_crawl:
            cmd.append("-jc")

        if self.crawl_duration > 0:
            cmd.extend(["-ct", f"{self.crawl_duration}s"])

        if self.known_files:
            cmd.extend(["-kf", self.known_files])

        if self.automatic_form_fill:
            cmd.append("-aff")

        if self.strategy != "depth-first":  # Only add if not default
            cmd.extend(["-s", self.strategy])

        # Add rate limiting and concurrency
        if self.concurrency != 10:  # Only add if different from default
            cmd.extend(["-c", str(self.concurrency)])

        if self.parallelism != 10:  # Only add if different from default
            cmd.extend(["-p", str(self.parallelism)])

        if self.rate_limit != 150:  # Only add if different from default
            cmd.extend(["-rl", str(self.rate_limit)])

        if self.delay > 0:
            cmd.extend(["-rd", str(self.delay)])

        # Add network configuration
        if self.timeout != 10:  # Only add if different from default
            cmd.extend(["-timeout", str(self.timeout)])

        if self.retry != 1:  # Only add if different from default
            cmd.extend(["-retry", str(self.retry)])

        if self.proxy:
            cmd.extend(["-proxy", self.proxy])

        # Add scope configuration
        if self.field_scope != "rdn":  # Only add if different from default
            cmd.extend(["-fs", self.field_scope])

        # Add headless options
        if self.headless:
            cmd.append("-hl")

        if self.xhr_extraction:
            cmd.append("-xhr")

        # Add filtering options
        if self.extension_filter:
            cmd.extend(["-ef", ",".join(self.extension_filter)])

        # Add output options
        cmd.extend(["-o", output_file])

        if self.omit_body:
            cmd.append("-ob")

        if getattr(self.cli_args, "verbose", False):
            cmd.insert(1, "-v")
            self.debug(f"Running command: {' '.join(cmd)}")

        # Store command for reporting
        self.command_executed = ' '.join(cmd)

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
                # Create empty katana.json file first, so that kast-web knows we are running
                in_progress_file = os.path.join(output_dir, "katana.json")
                open(in_progress_file, 'a').close()

                # stdout/stderr go to a spooled temp file rather than PIPE: with -o
                # writing URLs directly to katana.txt, katana shouldn't produce much
                # on either stream, but an unread PIPE can fill its OS buffer and
                # deadlock the process during a long poll loop. A real file has no
                # such limit and needs no draining.
                with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as combined_output:
                    # start_new_session puts katana and the headless browser it
                    # spawns in their own process group, so termination reaches the
                    # whole tree. Signalling katana alone leaves Chrome orphaned.
                    proc = subprocess.Popen(
                        cmd,
                        stdout=combined_output,
                        stderr=combined_output,
                        start_new_session=True,
                    )

                    started_at = time.monotonic()
                    deadline = (
                        started_at + self.max_runtime if self.max_runtime else None
                    )
                    termination = None
                    last_count = 0
                    last_change_time = time.monotonic()
                    while proc.poll() is None:
                        time.sleep(KATANA_POLL_INTERVAL_SECONDS)
                        count = self._count_lines(output_file)
                        now = time.monotonic()
                        if count is not None:
                            if count != last_count:
                                last_count = count
                                last_change_time = now
                            stalled_seconds = int(now - last_change_time)
                            status = (
                                "stalled"
                                if stalled_seconds >= KATANA_STALL_THRESHOLD_SECONDS
                                else "crawling"
                            )
                            self._write_progress(
                                output_dir, status, last_count, stalled_seconds
                            )
                        else:
                            # katana.txt was mid-write; skip this tick's counting but
                            # still let the deadline checks below run, or an unreadable
                            # file would defeat the timeouts entirely.
                            stalled_seconds = int(now - last_change_time)

                        if deadline and now >= deadline:
                            termination = "max_runtime"
                        elif self.stall_timeout and stalled_seconds >= self.stall_timeout:
                            termination = "stall_timeout"
                        if termination:
                            self.debug(
                                f"katana terminated by {termination} after "
                                f"{int(now - started_at)}s with {last_count} URL(s)"
                            )
                            self._terminate(proc)
                            break

                    proc.wait()
                    final_count = self._count_lines(output_file) or 0
                    self._write_progress(
                        output_dir,
                        "terminated" if termination else "done",
                        final_count,
                        termination=termination,
                    )

                    os.remove(in_progress_file)
                    # A non-zero code after we signalled katana is our own doing, not
                    # a crawl failure — the URLs written so far are still good.
                    if proc.returncode != 0 and termination is None:
                        combined_output.seek(0)
                        error_output = combined_output.read().strip()
                        return self.get_result_dict(
                            disposition="fail",
                            results=error_output
                        )

                # Read plain text output file and store raw URLs
                raw_urls = []
                if os.path.exists(output_file):
                    with open(output_file) as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                raw_urls.append(line)

                return self.get_result_dict(
                    disposition="success",
                    results={
                        "target": target,
                        "urls": raw_urls,
                        "termination": termination,
                        "runtime_seconds": round(time.monotonic() - started_at, 1),
                    }
                )

        except Exception as e:
            return self.get_result_dict(
                disposition="fail",
                results=str(e)
            )

    def post_process(self, raw_output, output_dir, pdf_mode=False):
        """
        Normalize output, extract issues, and build executive_summary.
        Parse katana output to extract only URL paths after the target domain.

        Args:
            raw_output: Raw plugin output
            output_dir: Directory containing output files
            pdf_mode: If True, generate PDF-friendly truncated output
        """
        self.debug(f"{self.name} post_process called with raw_output type: {type(raw_output)}")
        self.debug(f"{self.name} post_process raw_output: {pformat(raw_output)}")

        # Read the katana.txt file directly since that's where the actual output is
        katana_file = os.path.join(output_dir, "katana.txt")

        target = self.cli_args.target
        raw_urls = []

        # run() hands back the get_result_dict envelope, so this plugin's payload
        # sits under "results". Reading the top level instead yielded target="",
        # and the host filter then matched the empty string against every URL —
        # the whole crawl, third-party hosts included, was reported as the target's.
        results = raw_output.get("results") if isinstance(raw_output, dict) else None
        termination = None
        runtime_seconds = None
        if isinstance(results, dict):
            target = results.get("target") or target
            raw_urls = results.get("urls", [])
            termination = results.get("termination")
            runtime_seconds = results.get("runtime_seconds")

        # run() carries the termination reason in-process only. `kast scan rerun`
        # re-reads katana.txt with no such envelope, so recover it from the
        # progress file — otherwise re-rendering a truncated scan would present
        # it as a complete one, which is the claim the banner exists to prevent.
        if termination is None:
            termination = self._termination_from_progress(output_dir)

        # If we don't have URLs yet, read from the katana.txt file
        if not raw_urls and os.path.exists(katana_file):
            self.debug(f"Reading URLs from {katana_file}")
            with open(katana_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        raw_urls.append(line)
            self.debug(f"Read {len(raw_urls)} URLs from katana.txt")

        # Classify every discovered URL by host, then keep the ones report_scope allows.
        parsed_urls, crawl_scope = self._scope_urls(raw_urls, target)
        crawl_scope["termination"] = termination
        crawl_scope["runtime_seconds"] = runtime_seconds
        crawl_scope["complete"] = termination is None

        self.debug(
            f"{self.name} parsed {len(raw_urls)} raw URLs into "
            f"{crawl_scope['unique_url_count']} unique URL(s) across "
            f"{crawl_scope['host_count']} host(s); report_scope="
            f"{crawl_scope['report_scope']} kept {len(parsed_urls)}"
        )

        # Identify security-relevant paths observed during crawl (informational only)
        interesting_endpoints = self._find_interesting_paths(parsed_urls)

        # Initialize issues (empty — Katana is pure discovery)
        issues = []

        # Generate details and summaries
        url_count = len(parsed_urls)
        interesting_count = sum(len(v) for v in interesting_endpoints.values())
        if interesting_count:
            details = (
                f"Detected {url_count} unique URL(s). "
                f"{interesting_count} security-relevant path(s) observed across "
                f"{len(interesting_endpoints)} category(s) — see Interesting Endpoints below."
            )
        else:
            details = f"Detected {url_count} unique URL(s)."
        scope_sentence = self._scope_sentence(crawl_scope)
        if scope_sentence:
            details = f"{details} {scope_sentence}"
        summary = self._generate_summary(parsed_urls, interesting_endpoints, crawl_scope)
        executive_summary = self._generate_executive_summary(
            parsed_urls, interesting_endpoints, crawl_scope
        )

        # Calculate findings_count - count of URLs found
        findings_count = len(parsed_urls)

        # Generate both HTML and PDF versions of URL display
        custom_html = self._generate_url_display_html(
            parsed_urls, interesting_endpoints, crawl_scope
        )
        custom_html_pdf = self._generate_pdf_url_list(
            parsed_urls, interesting_endpoints, crawl_scope
        )

        self.debug(f"{self.name} summary: {summary}")
        self.debug(f"{self.name} issues: {issues}")
        self.debug(f"{self.name} details:\n{details}")
        self.debug(f"{self.name} findings_count: {findings_count}")

        # Format command for report notes
        report_notes = self._format_command_for_report()

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": getattr(self, 'display_name', None),
            "plugin-website-url": getattr(self, 'website_url', None),
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "findings": {"urls": parsed_urls},
            "findings_count": findings_count,
            "crawl_scope": crawl_scope,
            "interesting_endpoints": interesting_endpoints,
            "summary": summary or f"{self.name} did not produce any findings",
            "details": details,
            "issues": issues,
            "executive_summary": executive_summary,
            "report": report_notes,
            "custom_html": custom_html,
            "custom_html_pdf": custom_html_pdf,
            "results_message": "📋 View URL details below"
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

    def _registrable_domain(self, host):
        """Return the registrable domain for a host, or "" when it has none."""
        extracted = self._tld_extract(host)
        if extracted.domain and extracted.suffix:
            return f"{extracted.domain}.{extracted.suffix}"
        return ""

    def _classify_host(self, host, target_host, target_domain):
        """Label a host as target, sibling (same registrable domain), or external."""
        if host == target_host:
            return "target"
        # An IP literal or bare hostname has no registrable domain. Without this
        # guard the empty string would compare equal for every such host and the
        # whole internet would classify as a sibling of the target.
        if target_domain and self._registrable_domain(host) == target_domain:
            return "sibling"
        return "external"

    def _url_suffix(self, split_url):
        """Everything after the host: path, query and fragment."""
        suffix = split_url.path or "/"
        if split_url.query:
            suffix += f"?{split_url.query}"
        if split_url.fragment:
            suffix += f"#{split_url.fragment}"
        return suffix

    def _scope_urls(self, raw_urls, target):
        """
        Group katana's discovered URLs by host and keep the ones report_scope allows.

        Host identity comes from urlsplit, not a substring search. The old
        find(target) matched the target anywhere in the string, so a redirect
        like page.wbez.org/.../clkn/http/donate.wbez.org/secure/x was reported as
        a path on the target.

        :return: (sorted list of display labels, crawl_scope dict)
        """
        target_host = (urlsplit(f"//{target}").hostname or target).lower()
        target_domain = self._registrable_domain(target_host)

        labels_by_host = {}
        classification = {}
        unparseable = 0

        for url in raw_urls:
            split_url = urlsplit(url)
            host = (split_url.hostname or "").lower()
            if not host:
                # katana writes absolute URLs; anything else is a malformed line.
                unparseable += 1
                continue
            if host not in classification:
                classification[host] = self._classify_host(
                    host, target_host, target_domain
                )
            suffix = self._url_suffix(split_url)
            # Paths are relative to the target; any other host stays qualified so
            # a report never implies a sibling's path belongs to the target.
            label = suffix if host == target_host else f"{host}{suffix}"
            labels_by_host.setdefault(host, set()).add(label)

        reported_classes = {
            "target": {"target"},
            "organization": {"target", "sibling"},
            "all": {"target", "sibling", "external"},
        }[self.report_scope]

        labels = set()
        for host, host_labels in labels_by_host.items():
            if classification[host] in reported_classes:
                labels |= host_labels

        unique_total = sum(len(v) for v in labels_by_host.values())
        hosts = sorted(
            (
                {
                    "host": host,
                    "classification": classification[host],
                    "unique_urls": len(host_labels),
                    "reported": classification[host] in reported_classes,
                }
                for host, host_labels in labels_by_host.items()
            ),
            key=lambda h: (-h["unique_urls"], h["host"]),
        )

        hosts_by_class = {"target": 0, "sibling": 0, "external": 0}
        for host in hosts:
            hosts_by_class[host["classification"]] += 1

        crawl_scope = {
            "target_host": target_host,
            "registrable_domain": target_domain,
            "report_scope": self.report_scope,
            "field_scope": self.field_scope,
            "raw_url_count": len(raw_urls),
            "unique_url_count": unique_total,
            "reported_url_count": len(labels),
            "excluded_url_count": unique_total - len(labels),
            "host_count": len(labels_by_host),
            "hosts_by_class": hosts_by_class,
            "hosts": hosts,
            "unparseable_lines": unparseable,
        }

        return sorted(labels), crawl_scope

    @staticmethod
    def _label_segments(label):
        """
        Split a display label into lowercased path segments.

        Labels are either "/path" (the target) or "host/path" (any other host),
        and may carry a query or fragment. Only the path is considered.
        """
        path = label if label.startswith("/") else "/" + label.partition("/")[2]
        path = path.split("#", 1)[0].split("?", 1)[0]
        return path, [seg for seg in path.lower().split("/") if seg]

    @staticmethod
    def _is_static_asset(segments):
        if not segments:
            return False
        name = segments[-1]
        return any(name.endswith(ext) for ext in STATIC_ASSET_EXTENSIONS)

    def _find_interesting_paths(self, parsed_urls):
        """
        Identify security-relevant paths observed during crawl.
        Returns {category: [matching_paths]} — first-match-wins across categories.
        """
        results = {cat: [] for cat in INTERESTING_PATH_PATTERNS}
        seen = set()

        for url in parsed_urls:
            path, segments = self._label_segments(url)
            if not segments:
                continue
            if EDITORIAL_DATE_PATH.search(path) or self._is_static_asset(segments):
                continue

            segment_set = set(segments)
            filename = segments[-1]
            depth = len(segments)

            for category, rules in INTERESTING_PATH_PATTERNS.items():
                max_depth = rules.get("max_depth")
                if max_depth and depth > max_depth:
                    continue
                matched = (
                    bool(segment_set & rules.get("segments", set()))
                    or filename in rules.get("filenames", set())
                    or any(
                        filename.startswith(prefix)
                        for prefix in rules.get("filename_prefixes", set())
                    )
                )
                if matched and url not in seen:
                    results[category].append(url)
                    seen.add(url)
                    break  # first-match-wins: stop checking other categories

        return {cat: paths for cat, paths in results.items() if paths}

    def _scope_sentence(self, crawl_scope):
        """
        State what the crawl reached versus what the report shows.

        The crawl follows links across the whole registrable domain, so the
        reported count describes a narrower surface than the scan touched.
        Saying so is the point: an unqualified URL count invites a prospect to
        read third-party link targets as their own attack surface.
        """
        if not crawl_scope or not crawl_scope["unique_url_count"]:
            return ""

        truncation = self._truncation_sentence(crawl_scope)
        target_host = crawl_scope["target_host"]
        reported = crawl_scope["reported_url_count"]
        unique = crawl_scope["unique_url_count"]
        hosts = crawl_scope["hosts_by_class"]
        scope = crawl_scope["report_scope"]

        parts = [
            f"Crawl reached {unique} unique URL(s) across "
            f"{crawl_scope['host_count']} host(s)."
        ]
        if scope == "target":
            parts.append(f"Reporting the {reported} on {target_host} only.")
        elif scope == "organization":
            domain = crawl_scope["registrable_domain"] or target_host
            parts.append(
                f"Reporting the {reported} under {domain} "
                f"({hosts['sibling']} sibling host(s) besides {target_host})."
            )
        else:
            parts.append(f"Reporting all {reported}, including third-party hosts.")

        excluded = crawl_scope["excluded_url_count"]
        if excluded:
            parts.append(
                f"{excluded} URL(s) on {hosts['external']} external host(s) "
                "were referenced but are excluded from this report."
            )
        if truncation:
            parts.append(truncation)
        return " ".join(parts)

    TERMINATION_REASONS = {
        "max_runtime": "hit its wall-clock limit",
        "stall_timeout": "stopped finding new URLs",
    }

    def _truncation_sentence(self, crawl_scope):
        """
        Say so when the crawl was cut short.

        A truncated crawl reported as a finished one understates the surface,
        and "we found N URLs" is a claim an SA may have to defend.
        """
        termination = (crawl_scope or {}).get("termination")
        if not termination:
            return ""
        reason = self.TERMINATION_REASONS.get(termination, termination)
        runtime = crawl_scope.get("runtime_seconds")
        elapsed = f" after {runtime:g}s" if runtime else ""
        return (
            f"NOTE: the crawl was stopped early because it {reason}{elapsed}, "
            "so this list is partial."
        )

    def _generate_summary(self, parsed_urls, interesting_endpoints=None, crawl_scope=None):
        """Generate a human-readable summary from katana findings."""
        self.debug(f"_generate_summary called with parsed_urls type: {type(parsed_urls)}")

        if not parsed_urls:
            return "No URLs were found."

        count = len(parsed_urls)
        interesting_count = sum(len(v) for v in (interesting_endpoints or {}).values())
        if interesting_count:
            base = (
                f"Detected {count} unique URL(s) including "
                f"{interesting_count} security-relevant path(s)."
            )
        else:
            base = f"Detected {count} unique URL(s)."

        scope_sentence = self._scope_sentence(crawl_scope)
        return f"{base} {scope_sentence}".strip() if scope_sentence else base

    def _generate_executive_summary(
        self, parsed_urls, interesting_endpoints=None, crawl_scope=None
    ):
        """Generate an executive summary for katana results."""
        if not parsed_urls:
            return "No URLs detected."

        count = len(parsed_urls)
        interesting_count = sum(len(v) for v in (interesting_endpoints or {}).values())
        cats = list((interesting_endpoints or {}).keys())

        if not interesting_count:
            base = f"Detected {count} URL(s) during crawl."
        else:
            cat_str = ", ".join(cats[:3])
            if len(cats) > 3:
                cat_str += f", and {len(cats) - 3} more"
            base = (
                f"Detected {count} URL(s) during crawl. "
                f"{interesting_count} security-relevant path(s) observed: {cat_str}."
            )

        scope_sentence = self._scope_sentence(crawl_scope)
        return f"{base} {scope_sentence}".strip() if scope_sentence else base

    CLASS_LABELS = {
        "target": ("Target", "#0a6b3d", "#e6f5ec"),
        "sibling": ("Same domain", "#8a5a00", "#fff5e0"),
        "external": ("External", "#555", "#f0f0f0"),
    }

    def _truncation_banner_html(self, crawl_scope):
        """Amber banner stating the crawl was cut short, shown above the scope table."""
        sentence = self._truncation_sentence(crawl_scope)
        if not sentence:
            return ""
        return (
            '<div style="background:#fdf0d5;border:1px solid #d9a441;border-radius:6px;'
            'padding:0.7em 1em;margin-bottom:0.8em;color:#7a4b00;font-size:0.88em;">'
            f'<strong>Partial crawl.</strong> {self._esc(sentence)}'
            '</div>'
        )

    def _generate_crawl_scope_html(self, crawl_scope, max_rows=40):
        """
        Render the per-host breakdown of what the crawl actually reached.

        This is the section that lets an SA answer "why does a scan of one
        hostname list URLs on another" without having to open katana.txt.
        """
        if not crawl_scope or not crawl_scope["unique_url_count"]:
            return ""

        hosts = crawl_scope["hosts"]
        by_class = crawl_scope["hosts_by_class"]
        shown = hosts[:max_rows]
        hidden = len(hosts) - len(shown)

        html = self._truncation_banner_html(crawl_scope)
        html += (
            '<div style="background:#f4f8fb;border:1px solid #c3d5e3;border-radius:6px;'
            'padding:1em 1.2em;margin-bottom:1.2em;">'
            '<div style="font-weight:700;font-size:1em;color:#1b4b6e;margin-bottom:0.4em;">'
            f'Crawl Scope ({crawl_scope["host_count"]} hosts reached)</div>'
            '<div style="font-size:0.85em;color:#33556e;margin-bottom:0.8em;">'
            f'The crawler follows links across <code>{self._esc(crawl_scope["registrable_domain"] or crawl_scope["target_host"])}</code> '
            f'(katana field-scope <code>{self._esc(crawl_scope["field_scope"])}</code>), so it encounters hosts '
            f'other than the scan target. Report scope is '
            f'<code>{self._esc(crawl_scope["report_scope"])}</code>: '
            f'{crawl_scope["reported_url_count"]} of {crawl_scope["unique_url_count"]} '
            f'unique URL(s) are listed below; {crawl_scope["excluded_url_count"]} are excluded. '
            'Hosts marked External were referenced as link targets from in-scope pages.'
            '</div>'
            '<table style="width:100%;border-collapse:collapse;font-size:0.84em;">'
            '<tr style="text-align:left;border-bottom:1px solid #c3d5e3;">'
            '<th style="padding:0.3em 0.4em;">Host</th>'
            '<th style="padding:0.3em 0.4em;">Classification</th>'
            '<th style="padding:0.3em 0.4em;text-align:right;">Unique URLs</th>'
            '<th style="padding:0.3em 0.4em;">In report</th></tr>'
        )

        for host in shown:
            label, fg, bg = self.CLASS_LABELS[host["classification"]]
            html += (
                '<tr style="border-bottom:1px solid #e3ecf3;">'
                f'<td style="padding:0.25em 0.4em;"><code>{self._esc(host["host"])}</code></td>'
                f'<td style="padding:0.25em 0.4em;">'
                f'<span style="background:{bg};color:{fg};padding:0.1em 0.5em;'
                f'border-radius:3px;font-size:0.9em;">{label}</span></td>'
                f'<td style="padding:0.25em 0.4em;text-align:right;">{host["unique_urls"]}</td>'
                f'<td style="padding:0.25em 0.4em;">{"yes" if host["reported"] else "no"}</td>'
                '</tr>'
            )

        html += '</table>'
        if hidden > 0:
            html += (
                f'<div style="font-size:0.8em;color:#33556e;margin-top:0.5em;">'
                f'{hidden} further host(s) not shown.</div>'
            )
        html += (
            '<div style="font-size:0.8em;color:#33556e;margin-top:0.6em;">'
            f'Hosts: {by_class["target"]} target, {by_class["sibling"]} same-domain, '
            f'{by_class["external"]} external.</div>'
            '</div>'
        )
        return html

    def _generate_crawl_scope_pdf(self, crawl_scope, max_rows=15):
        """Compact crawl-scope table for the PDF report."""
        if not crawl_scope or not crawl_scope["unique_url_count"]:
            return ""

        by_class = crawl_scope["hosts_by_class"]
        shown = [h for h in crawl_scope["hosts"] if h["reported"]][:max_rows]
        html = self._truncation_banner_html(crawl_scope)
        html += (
            '<div style="background:#f4f8fb;border:1px solid #c3d5e3;border-radius:4px;'
            'padding:0.8em;margin-bottom:1em;">'
            '<div style="font-weight:700;font-size:0.9em;color:#1b4b6e;margin-bottom:0.3em;">'
            f'Crawl Scope ({crawl_scope["host_count"]} hosts reached)</div>'
            '<div style="font-size:0.8em;color:#33556e;margin-bottom:0.5em;">'
            f'{crawl_scope["reported_url_count"]} of {crawl_scope["unique_url_count"]} unique URL(s) '
            f'reported (scope: {self._esc(crawl_scope["report_scope"])}). '
            f'{by_class["target"]} target host, {by_class["sibling"]} same-domain, '
            f'{by_class["external"]} external.</div>'
            '<ul style="margin:0.2em 0 0 1.2em;padding:0;">'
        )
        for host in shown:
            label = self.CLASS_LABELS[host["classification"]][0]
            html += (
                f'<li style="font-size:0.8em;"><code>{self._esc(host["host"])}</code> '
                f'— {label}, {host["unique_urls"]} URL(s)</li>'
            )
        html += '</ul></div>'
        return html

    @staticmethod
    def _esc(value):
        return (
            str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        )

    def _generate_interesting_endpoints_html(self, interesting_endpoints):
        """Render the Interesting Endpoints Observed section for the HTML report."""
        if not interesting_endpoints:
            return ""

        total = sum(len(v) for v in interesting_endpoints.values())
        html = f'''
        <div style="background:#fff8e6;border:1px solid #f0c040;border-radius:6px;padding:1em 1.2em;margin-bottom:1.2em;">
            <div style="font-weight:700;font-size:1em;color:#7a5200;margin-bottom:0.4em;">
                Interesting Endpoints Observed ({total} paths)
            </div>
            <div style="font-size:0.85em;color:#5a4000;margin-bottom:0.8em;">
                Paths encountered during normal site crawl that may warrant security review.
                No active probing was performed; these were found through ordinary site traversal.
            </div>
        '''
        for category, paths in interesting_endpoints.items():
            html += f'''
            <div style="margin-bottom:0.6em;">
                <div style="font-weight:600;color:#7a5200;font-size:0.9em;margin-bottom:0.25em;">
                    {category} ({len(paths)})
                </div>
                <div style="padding-left:1em;">
        '''
            for path in paths:
                safe = path.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                html += f'<code style="display:block;font-size:0.82em;color:#333;padding:0.1em 0;">{safe}</code>'
            html += '</div></div>'

        html += '</div>'
        return html

    def _generate_url_display_html(
        self, parsed_urls, interesting_endpoints=None, crawl_scope=None
    ):
        """
        Generate custom HTML for displaying URLs with grouping, search, and pagination.
        URLs are grouped by file extension for better organization.
        """
        scope_html = self._generate_crawl_scope_html(crawl_scope)

        if not parsed_urls:
            return scope_html + "<p>No URLs found.</p>"

        # Group URLs by file extension
        url_groups = self._group_urls_by_extension(parsed_urls)

        # Generate unique ID for this instance (in case multiple plugins use this)
        widget_id = f"katana-url-widget-{id(self)}"

        html = scope_html
        html += self._generate_interesting_endpoints_html(interesting_endpoints or {})

        html += f'''
        <div class="url-display-widget" id="{widget_id}">
            <div class="url-search-container">
                <input type="text"
                       class="url-search-input"
                       placeholder="🔍 Search URLs (e.g., /api, .js, admin)..."
                       onkeyup="filterKatanaUrls('{widget_id}')">
                <span class="url-count-badge">Total: {len(parsed_urls)} URLs</span>
            </div>

            <div class="url-groups-container">
        '''

        # Generate HTML for each group
        for group_name, urls in sorted(url_groups.items(), key=lambda x: (-len(x[1]), x[0])):
            group_id = f"{widget_id}-{group_name.replace('.', '-').replace(' ', '-')}"
            html += self._generate_group_html(group_name, urls, group_id)

        html += '''
            </div>
        </div>
        '''

        return html

    def _group_urls_by_extension(self, urls):
        """
        Group URLs by their file extension.
        Returns a dictionary where keys are extension names and values are lists of URLs.
        """
        groups = {}

        for url in urls:
            # Determine the extension/category
            if '.' in url.split('?')[0].split('/')[-1]:
                # Has an extension
                ext = '.' + url.split('?')[0].split('.')[-1].lower()
                # Limit extension length to avoid weird cases
                if len(ext) > 10:
                    ext = "Other"
            else:
                # No extension - likely a directory or endpoint
                ext = "Endpoints"

            if ext not in groups:
                groups[ext] = []
            groups[ext].append(url)

        return groups

    def _generate_group_html(self, group_name, urls, group_id):
        """
        Generate HTML for a single URL group with pagination.
        """
        urls_per_page = 50
        total_urls = len(urls)
        total_pages = (total_urls + urls_per_page - 1) // urls_per_page

        # Generate icon based on group type
        icon = self._get_group_icon(group_name)

        html = f'''
        <div class="url-group" data-group="{group_id}">
            <div class="url-group-header" onclick="toggleUrlGroup('{group_id}')">
                <span class="url-group-icon">{icon}</span>
                <span class="url-group-title">{group_name}</span>
                <span class="url-group-count">{total_urls} URLs</span>
                <span class="url-group-toggle">▼</span>
            </div>
            <div class="url-group-content" id="{group_id}-content" style="display: none;">
                <div class="url-list" id="{group_id}-list">
        '''

        # Add all URLs with page data attributes
        for page_num in range(total_pages):
            start_idx = page_num * urls_per_page
            end_idx = min(start_idx + urls_per_page, total_urls)

            for url in urls[start_idx:end_idx]:
                # Make URL searchable and clickable
                display_style = 'display: none;' if page_num > 0 else ''
                html += f'''
                    <div class="url-item" data-page="{page_num + 1}" data-url="{url.lower()}" style="{display_style}">
                        <code class="url-path">{url}</code>
                    </div>
                '''

        html += '''
                </div>
        '''

        # Add pagination controls if needed
        if total_pages > 1:
            html += f'''
                <div class="url-pagination" id="{group_id}-pagination">
                    <button onclick="changeUrlPage('{group_id}', -1)" class="url-page-btn">« Previous</button>
                    <span class="url-page-info">
                        Page <span id="{group_id}-current-page">1</span> of {total_pages}
                    </span>
                    <button onclick="changeUrlPage('{group_id}', 1)" class="url-page-btn">Next »</button>
                </div>
            '''

        html += '''
            </div>
        </div>
        '''

        return html

    def _get_group_icon(self, group_name):
        """
        Return an appropriate icon emoji for the group type.
        """
        icons = {
            '.js': '📜',
            '.css': '🎨',
            '.html': '📄',
            '.htm': '📄',
            '.json': '📋',
            '.xml': '📋',
            '.php': '🐘',
            '.jsp': '☕',
            '.asp': '🌐',
            '.aspx': '🌐',
            '.png': '🖼️',
            '.jpg': '🖼️',
            '.jpeg': '🖼️',
            '.gif': '🖼️',
            '.svg': '🖼️',
            '.ico': '🖼️',
            '.pdf': '📕',
            '.txt': '📝',
            '.woff': '🔤',
            '.woff2': '🔤',
            '.ttf': '🔤',
            '.eot': '🔤',
            'Endpoints': '🔗',
            'Other': '📦'
        }
        return icons.get(group_name, '📄')

    def _generate_pdf_url_list(
        self, parsed_urls, interesting_endpoints=None, crawl_scope=None, max_urls=75
    ):
        """
        Generate a PDF-friendly truncated URL list, preceded by the Interesting Endpoints table.
        """
        html = self._generate_crawl_scope_pdf(crawl_scope)

        # Interesting endpoints section
        if interesting_endpoints:
            total_interesting = sum(len(v) for v in interesting_endpoints.values())
            html += '<div style="background:#fff8e6;border:1px solid #f0c040;border-radius:4px;padding:0.8em;margin-bottom:1em;">'
            html += f'<div style="font-weight:700;font-size:0.9em;color:#7a5200;margin-bottom:0.3em;">Interesting Endpoints Observed ({total_interesting})</div>'
            html += '<div style="font-size:0.8em;color:#5a4000;margin-bottom:0.5em;">Paths found during normal crawl that may warrant security review.</div>'
            for category, paths in interesting_endpoints.items():
                html += f'<div style="margin-bottom:0.4em;"><strong style="font-size:0.85em;">{category}:</strong>'
                html += '<ul style="margin:0.2em 0 0.2em 1.2em;padding:0;">'
                for path in paths:
                    safe = path.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    html += f'<li style="font-size:0.8em;"><code>{safe}</code></li>'
                html += '</ul></div>'
            html += '</div>'

        if not parsed_urls:
            html += "<p>No URLs found.</p>"
            return html

        total_count = len(parsed_urls)
        display_urls = parsed_urls[:max_urls]
        truncated_count = total_count - len(display_urls)

        html += '<div class="pdf-url-list">'
        html += f'<div class="pdf-url-header"><strong>Discovered URLs</strong> (showing {len(display_urls)} of {total_count})</div>'
        html += '<ul class="pdf-url-items">'

        for url in display_urls:
            safe_url = url.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            html += f'<li class="pdf-url-item"><code>{safe_url}</code></li>'

        html += '</ul>'

        if truncated_count > 0:
            html += f'<div class="pdf-url-truncation"><strong>Note:</strong> {truncated_count} additional URL(s) not shown in PDF. View the full interactive HTML report for the complete list.</div>'

        html += '</div>'
        return html

    def get_dry_run_info(self, target, output_dir):
        """
        Return information about what this plugin would do in a real run.
        Builds the actual command with current configuration.
        """
        output_file = os.path.join(output_dir, "katana.txt")

        # Build command with current configuration (same as run() method)
        cmd = ["katana", "-silent", "-u", target]

        # Add crawl configuration
        if self.depth != 3:
            cmd.extend(["-d", str(self.depth)])

        if self.js_crawl:
            cmd.append("-jc")

        if self.crawl_duration > 0:
            cmd.extend(["-ct", f"{self.crawl_duration}s"])

        if self.known_files:
            cmd.extend(["-kf", self.known_files])

        if self.automatic_form_fill:
            cmd.append("-aff")

        if self.strategy != "depth-first":
            cmd.extend(["-s", self.strategy])

        # Add rate limiting and concurrency
        if self.concurrency != 10:
            cmd.extend(["-c", str(self.concurrency)])

        if self.parallelism != 10:
            cmd.extend(["-p", str(self.parallelism)])

        if self.rate_limit != 150:
            cmd.extend(["-rl", str(self.rate_limit)])

        if self.delay > 0:
            cmd.extend(["-rd", str(self.delay)])

        # Add network configuration
        if self.timeout != 10:
            cmd.extend(["-timeout", str(self.timeout)])

        if self.retry != 1:
            cmd.extend(["-retry", str(self.retry)])

        if self.proxy:
            cmd.extend(["-proxy", self.proxy])

        # Add scope configuration
        if self.field_scope != "rdn":
            cmd.extend(["-fs", self.field_scope])

        # Add headless options
        if self.headless:
            cmd.append("-hl")

        if self.xhr_extraction:
            cmd.append("-xhr")

        # Add filtering options
        if self.extension_filter:
            cmd.extend(["-ef", ",".join(self.extension_filter)])

        # Add output options
        cmd.extend(["-o", output_file])

        if self.omit_body:
            cmd.append("-ob")

        # Build operations description with config values
        operations_parts = []
        operations_parts.append(f"depth: {self.depth}")

        if self.js_crawl:
            operations_parts.append("JS crawling")

        if self.headless:
            operations_parts.append("headless mode")

        operations_parts.append(f"rate: {self.rate_limit}/s")
        operations_parts.append(f"timeout: {self.timeout}s")

        if self.extension_filter:
            operations_parts.append(f"filtering: {', '.join(self.extension_filter)}")

        operations_desc = f"Web crawling ({', '.join(operations_parts)})"

        return {
            "commands": [' '.join(cmd)],
            "description": self.description,
            "operations": operations_desc
        }
