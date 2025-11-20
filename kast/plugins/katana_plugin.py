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
        self.website_url = "https://github.com/projectdiscovery/katana"
        self.scan_type = "passive"  # or "active"
        self.output_type = "file"    # or "stdout"
        self.command_executed = None  # Store the command for reporting

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
        
        # Generate custom HTML for URL display
        custom_html = self._generate_url_display_html(parsed_urls)
        
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
            "findings": {"urls": parsed_urls},
            "summary": summary or f"{self.name} did not produce any findings",
            "details": details,
            "issues": issues,
            "executive_summary": executive_summary,
            "report": report_notes,
            "custom_html": custom_html
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)

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

    def _generate_url_display_html(self, parsed_urls):
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
        
        html = f'''
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
