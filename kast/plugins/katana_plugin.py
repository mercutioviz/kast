"""
File: plugins/katana_plugin.py
Description: Site crawler and URL finder plugin for KAST.
"""

import subprocess
import shutil
import os
import json
from datetime import datetime, timezone
from kast.plugins.base import KastPlugin
from kast.core.atomic import write_json_atomic
from pprint import pformat

# Categories ordered by security priority (first-match wins per URL).
INTERESTING_PATH_PATTERNS = {
    "Config / Exposed Files": [
        "/.env", "/.git/", "/web.config", "/config.", "/settings.",
        "/swagger", "/openapi", "/api-docs", "/redoc",
    ],
    "Admin / CMS": [
        "/admin/", "/wp-admin/", "/wp-login", "/administrator/",
        "/manage/", "/management/", "/backoffice/", "/cms/", "/cpanel",
        "/dashboard/",
    ],
    "Debug / Diagnostics": [
        "/debug/", "/actuator/", "/_profiler/", "/phpinfo",
        "/console/", "/server-status", "/health/", "/metrics/", "/trace/",
    ],
    "Authentication": [
        "/login", "/signin", "/auth/", "/oauth", "/sso/", "/saml",
        "/logout", "/signout", "/register", "/signup", "/forgot-password",
        "/reset-password",
    ],
    "API Endpoints": [
        "/api/", "/graphql", "/rest/", "/rpc/", "/gql",
    ],
    "Upload / Storage": [
        "/upload/", "/uploads/", "/files/", "/media/", "/private/",
    ],
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
                "default": 0,
                "minimum": 0,
                "description": "Maximum duration to crawl in seconds (0 = no limit)"
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
                "default": False,
                "description": "Enable headless browser crawling (experimental)"
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
            }
        }
    }

    name = "katana"
    description = "Site crawler and URL finder."
    display_name = "Katana"
    website_url = "https://github.com/projectdiscovery/katana"
    scan_type = "passive"  # or "active"
    output_type = "file"  # or "stdout"
    
    def __init__(self, cli_args, config_manager=None):
        
        super().__init__(cli_args, config_manager)
        
        self.command_executed = None  # Store the command for reporting
        
        # Load configuration values
        self._load_plugin_config()
    
    def _load_plugin_config(self):
        """Load configuration with defaults from schema."""
        # Get config values (defaults from schema if not set)
        self.depth = self.get_config('depth', 3)
        self.js_crawl = self.get_config('js_crawl', False)
        self.crawl_duration = self.get_config('crawl_duration', 0)
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
        self.headless = self.get_config('headless', False)
        self.xhr_extraction = self.get_config('xhr_extraction', False)
        self.extension_filter = self.get_config('extension_filter', [])
        self.omit_body = self.get_config('omit_body', True)
        
        self.debug(f"Katana config loaded: "
                  f"depth={self.depth}, "
                  f"js_crawl={self.js_crawl}, "
                  f"duration={self.crawl_duration}s, "
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
                  f"omit_body={self.omit_body}")

    def is_available(self):
        """
        Check if required tool is installed and available in PATH.
        """
        return shutil.which("katana") is not None

    def run(self, target, output_dir, report_only):
        """
        Run the tool and return standardized result dict.
        """
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
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
                proc = subprocess.run(cmd, capture_output=True, text=True)
                os.remove(in_progress_file)
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
        summary = self._generate_summary(parsed_urls, interesting_endpoints)
        executive_summary = self._generate_executive_summary(parsed_urls, interesting_endpoints)

        # Calculate findings_count - count of URLs found
        findings_count = len(parsed_urls)

        # Generate both HTML and PDF versions of URL display
        custom_html = self._generate_url_display_html(parsed_urls, interesting_endpoints)
        custom_html_pdf = self._generate_pdf_url_list(parsed_urls, interesting_endpoints)
        
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
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "findings": {"urls": parsed_urls},
            "findings_count": findings_count,
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

    def _find_interesting_paths(self, parsed_urls):
        """
        Identify security-relevant paths observed during crawl.
        Returns {category: [matching_paths]} — first-match-wins across categories.
        """
        results = {cat: [] for cat in INTERESTING_PATH_PATTERNS}
        seen = set()

        for url in parsed_urls:
            url_lower = url.lower()
            for category, patterns in INTERESTING_PATH_PATTERNS.items():
                matched = False
                for pattern in patterns:
                    if url_lower.startswith(pattern.lower()) or pattern.lower() in url_lower:
                        matched = True
                        break
                if matched and url not in seen:
                    results[category].append(url)
                    seen.add(url)
                    break  # first-match-wins: stop checking other categories

        return {cat: paths for cat, paths in results.items() if paths}

    def _generate_summary(self, parsed_urls, interesting_endpoints=None):
        """Generate a human-readable summary from katana findings."""
        self.debug(f"_generate_summary called with parsed_urls type: {type(parsed_urls)}")

        if not parsed_urls:
            return "No URLs were found."

        count = len(parsed_urls)
        interesting_count = sum(len(v) for v in (interesting_endpoints or {}).values())
        if interesting_count:
            return f"Detected {count} unique URL(s) including {interesting_count} security-relevant path(s)."
        return f"Detected {count} unique URL(s)."

    def _generate_executive_summary(self, parsed_urls, interesting_endpoints=None):
        """Generate an executive summary for katana results."""
        if not parsed_urls:
            return "No URLs detected."

        count = len(parsed_urls)
        interesting_count = sum(len(v) for v in (interesting_endpoints or {}).values())
        cats = list((interesting_endpoints or {}).keys())

        if not interesting_count:
            return f"Detected {count} URL(s) during crawl."

        cat_str = ", ".join(cats[:3])
        if len(cats) > 3:
            cat_str += f", and {len(cats) - 3} more"
        return (
            f"Detected {count} URL(s) during crawl. "
            f"{interesting_count} security-relevant path(s) observed: {cat_str}."
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

    def _generate_url_display_html(self, parsed_urls, interesting_endpoints=None):
        """
        Generate custom HTML for displaying URLs with grouping, search, and pagination.
        URLs are grouped by file extension for better organization.
        """
        if not parsed_urls:
            return "<p>No URLs found.</p>"

        # Group URLs by file extension
        url_groups = self._group_urls_by_extension(parsed_urls)

        # Generate unique ID for this instance (in case multiple plugins use this)
        widget_id = f"katana-url-widget-{id(self)}"

        html = self._generate_interesting_endpoints_html(interesting_endpoints or {})

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

    def _generate_pdf_url_list(self, parsed_urls, interesting_endpoints=None, max_urls=75):
        """
        Generate a PDF-friendly truncated URL list, preceded by the Interesting Endpoints table.
        """
        html = ""

        # Interesting endpoints section
        if interesting_endpoints:
            total_interesting = sum(len(v) for v in interesting_endpoints.values())
            html += f'<div style="background:#fff8e6;border:1px solid #f0c040;border-radius:4px;padding:0.8em;margin-bottom:1em;">'
            html += f'<div style="font-weight:700;font-size:0.9em;color:#7a5200;margin-bottom:0.3em;">Interesting Endpoints Observed ({total_interesting})</div>'
            html += f'<div style="font-size:0.8em;color:#5a4000;margin-bottom:0.5em;">Paths found during normal crawl that may warrant security review.</div>'
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
