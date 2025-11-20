"""
File: plugins/subfinder_plugin.py
Description: Subdomain finder plugin for KAST.
"""

import subprocess
import shutil
import os
import json
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class SubfinderPlugin(KastPlugin):
    priority = 10  # Set plugin run order (lower runs earlier)
    
    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "subfinder"
        self.description = "Subdomain finder."
        self.display_name = "Subfinder"
        self.website_url = "https://github.com/projectdiscovery/subfinder"
        self.scan_type = "passive"  # or "active"
        self.output_type = "file"    # or "stdout"
        self.command_executed = None  # Store the command for reporting

    def is_available(self):
        """
        Check if required tool is installed and available in PATH.
        """
        return shutil.which("subfinder") is not None

    def run(self, target, output_dir, report_only):
        """
        Run the tool and return standardized result dict.
        """
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, "subfinder_tmp.json")
        cmd = [
            "subfinder",
            "-d", target,
            "-o", output_file,
            "-json"
        ]

        if getattr(self.cli_args, "verbose", False):
            cmd.insert(1, "-v")
            self.debug(f"Running command: {' '.join(cmd)}")

        # Store command for reporting
        self.command_executed = ' '.join(cmd)

        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="subfinder is not installed or not found in PATH.",
                timestamp=timestamp
            )

        try:
            if report_only:
                self.debug(f"[REPORT ONLY] Would run command: {' '.join(cmd)}")

            else: 
                # Create empty subfinder.json first, so that kast-web knows we are running
                in_progress_file = os.path.join(output_dir, "subfinder.json")
                open(in_progress_file, 'a').close()
                proc = subprocess.run(cmd, capture_output=True, text=True)
                os.remove(in_progress_file)
                if proc.returncode != 0:
                    return self.get_result_dict(
                        disposition="fail",
                        results=proc.stderr.strip()
                    )

            # Read JSON Lines format (one JSON object per line)
            results = []
            with open(output_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:  # Skip empty lines
                        try:
                            results.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            self.debug(f"Failed to parse line: {line}, error: {e}")
            
            # Write out as proper JSON array
            output_file = os.path.join(output_dir, "subfinder.json")
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)

            return self.get_result_dict(
                disposition="success",
                results=results
            )

        except Exception as e:
            return self.get_result_dict(
                disposition="fail",
                results=str(e)
            )

    def post_process(self, raw_output, output_dir, pdf_mode=False):
        """
        Normalize output, extract issues, and build executive_summary.
        
        Args:
            raw_output: Raw plugin output
            output_dir: Directory containing output files
            pdf_mode: If True, generate PDF-friendly truncated output
        """
        # Load input if path to a file
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

        self.debug(f"{self.name} raw findings:\n{pformat(findings)}")

        # Deduplicate subdomains based on 'host' field
        findings = self._deduplicate_findings(findings)
        self.debug(f"{self.name} deduplicated findings:\n{pformat(findings)}")

        # Extract subdomain data
        results = findings.get("results", []) if isinstance(findings, dict) else []
        subdomains = []
        for entry in results:
            host = entry.get("host", "")
            source = entry.get("source", "unknown")
            subdomains.append({"host": host, "source": source})
        
        # Sort by host name
        subdomains.sort(key=lambda x: x["host"])

        # Initialize issues and details
        issues = []
        subdomain_count = len(subdomains)
        details = f"Detected {subdomain_count} unique subdomain(s)."

        summary = self._generate_summary(findings)
        executive_summary = self._generate_executive_summary(findings)
        
        # Generate both HTML and PDF versions of subdomain display
        custom_html = self._generate_subdomain_display_html(subdomains)
        custom_html_pdf = self._generate_pdf_subdomain_list(subdomains)
        
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
            "report": report_notes,
            "custom_html": custom_html,
            "custom_html_pdf": custom_html_pdf,
            "results_message": "📋 View subdomain details below"
        }

        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)

        return processed_path

    def _generate_summary(self, findings):
        """
        Generate a human-readable summary from subfinder findings.
        """
        self.debug(f"_generate_summary called with findings type: {type(findings)}")
        self.debug(f"_generate_summary findings content: {pformat(findings)}")
        
        results = findings.get("results", []) if isinstance(findings, dict) else []
        self.debug(f"{self.name} results: {pformat(results)}")
        
        if not results:
            self.debug("No results found, returning 'No subdomains were found.'")
            return "No subdomains were found."

        # Extract subdomain names from the 'host' field in each result entry
        detected_subdomains = [entry.get("host") for entry in results if entry.get("host")]

        self.debug(f"Detected subdomains: {pformat(detected_subdomains)}")

        if not detected_subdomains:
            self.debug("No subdomains detected, returning 'No subdomains detected'")
            return "No subdomains detected"

        count = len(detected_subdomains)
        return f"Detected {count} unique subdomain(s)."

    def _generate_executive_summary(self, findings):
        """
        Generate a simple executive summary showing the count of subdomains detected.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        
        if not results:
            return "No subdomains detected."

        # Extract subdomain names from the 'host' field in each result entry
        detected_subdomains = [entry.get("host") for entry in results if entry.get("host")]
        
        count = len(detected_subdomains)
        
        if count == 0:
            return "No subdomains detected."
        elif count == 1:
            return "Detected 1 subdomain."
        else:
            return f"Detected {count} subdomains."

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
        Remove duplicate subdomains from findings based on the 'host' field.
        Keeps the first occurrence of each unique subdomain.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        
        if not results:
            return findings
        
        # Track seen hosts and deduplicated results
        seen_hosts = set()
        deduplicated_results = []
        
        for entry in results:
            host = entry.get("host")
            if host and host not in seen_hosts:
                seen_hosts.add(host)
                deduplicated_results.append(entry)
        
        # Update findings with deduplicated results
        if isinstance(findings, dict):
            findings["results"] = deduplicated_results
        else:
            findings = deduplicated_results
        
        self.debug(f"Deduplicated {len(results)} results to {len(deduplicated_results)} unique subdomains")
        
        return findings

    def _group_subdomains_by_source(self, subdomains):
        """
        Group subdomains by their source.
        Returns a dictionary where keys are source names and values are lists of subdomains.
        """
        groups = {}
        
        for subdomain in subdomains:
            source = subdomain['source']
            if source not in groups:
                groups[source] = []
            groups[source].append(subdomain)
        
        return groups

    def _get_source_icon(self, source_name):
        """
        Return an appropriate icon emoji for the source type.
        """
        icons = {
            'censys': '🔍',
            'certspotter': '📜',
            'crtsh': '🔐',
            'dnsdumpster': '💾',
            'hackertarget': '🎯',
            'rapiddns': '⚡',
            'securitytrails': '🛡️',
            'shodan': '🔎',
            'threatcrowd': '👥',
            'virustotal': '🦠',
            'wayback': '🕰️',
            'alienvault': '👽',
            'binaryedge': '🔢',
            'bufferover': '📊',
            'urlscan': '🌐',
            'unknown': '❓'
        }
        return icons.get(source_name.lower(), '🔸')

    def _generate_group_html(self, group_name, subdomains, group_id):
        """
        Generate HTML for a single subdomain group with pagination.
        """
        subdomains_per_page = 50
        total_subdomains = len(subdomains)
        total_pages = (total_subdomains + subdomains_per_page - 1) // subdomains_per_page
        
        # Generate icon based on source type
        icon = self._get_source_icon(group_name)
        
        html = f'''
        <div class="subdomain-group" data-group="{group_id}">
            <div class="subdomain-group-header" onclick="toggleSubdomainGroup('{group_id}')">
                <span class="subdomain-group-icon">{icon}</span>
                <span class="subdomain-group-title">{group_name}</span>
                <span class="subdomain-group-count">{total_subdomains} Subdomains</span>
                <span class="subdomain-group-toggle">▼</span>
            </div>
            <div class="subdomain-group-content" id="{group_id}-content" style="display: none;">
                <div class="subdomain-list" id="{group_id}-list">
        '''
        
        # Add all subdomains with page data attributes
        for page_num in range(total_pages):
            start_idx = page_num * subdomains_per_page
            end_idx = min(start_idx + subdomains_per_page, total_subdomains)
            
            for subdomain in subdomains[start_idx:end_idx]:
                host = subdomain['host']
                # Make subdomain searchable
                display_style = 'display: none;' if page_num > 0 else ''
                html += f'''
                    <div class="subdomain-item" data-page="{page_num + 1}" data-subdomain="{host.lower()}" style="{display_style}">
                        <code class="subdomain-host">{host}</code>
                    </div>
                '''
        
        html += '''
                </div>
        '''
        
        # Add pagination controls if needed
        if total_pages > 1:
            html += f'''
                <div class="subdomain-pagination" id="{group_id}-pagination">
                    <button onclick="changeSubdomainPage('{group_id}', -1)" class="subdomain-page-btn">« Previous</button>
                    <span class="subdomain-page-info">
                        Page <span id="{group_id}-current-page">1</span> of {total_pages}
                    </span>
                    <button onclick="changeSubdomainPage('{group_id}', 1)" class="subdomain-page-btn">Next »</button>
                </div>
            '''
        
        html += '''
            </div>
        </div>
        '''
        
        return html

    def _generate_subdomain_display_html(self, subdomains):
        """
        Generate custom HTML for displaying subdomains with grouping, search, and pagination.
        Subdomains are grouped by source for better organization.
        """
        if not subdomains:
            return "<p>No subdomains found.</p>"
        
        # Group subdomains by source
        subdomain_groups = self._group_subdomains_by_source(subdomains)
        
        # Generate unique ID for this instance
        widget_id = f"subfinder-widget-{id(self)}"
        
        html = f'''
        <div class="subdomain-display-widget" id="{widget_id}">
            <div class="subdomain-search-container">
                <input type="text" 
                       class="subdomain-search-input" 
                       placeholder="🔍 Search subdomains..."
                       onkeyup="filterSubfinderSubdomains('{widget_id}')">
                <span class="subdomain-count-badge">Total: {len(subdomains)} Subdomains</span>
            </div>
            
            <div class="subdomain-groups-container">
        '''
        
        # Generate HTML for each group
        for group_name, group_subdomains in sorted(subdomain_groups.items(), key=lambda x: (-len(x[1]), x[0])):
            group_id = f"{widget_id}-{group_name.replace('.', '-').replace(' ', '-')}"
            html += self._generate_group_html(group_name, group_subdomains, group_id)
        
        html += '''
            </div>
        </div>
        
        <script>
        function toggleSubdomainGroup(groupId) {
            const content = document.getElementById(groupId + '-content');
            const toggle = document.querySelector(`[data-group="${groupId}"] .subdomain-group-toggle`);
            
            if (content.style.display === 'none' || content.style.display === '') {
                content.style.display = 'block';
                toggle.style.transform = 'rotate(180deg)';
            } else {
                content.style.display = 'none';
                toggle.style.transform = 'rotate(0deg)';
            }
        }
        
        function changeSubdomainPage(groupId, direction) {
            const list = document.getElementById(groupId + '-list');
            const items = list.querySelectorAll('.subdomain-item');
            const currentPageSpan = document.getElementById(groupId + '-current-page');
            let currentPage = parseInt(currentPageSpan.textContent);
            
            // Calculate total pages
            let totalPages = 1;
            items.forEach(item => {
                const page = parseInt(item.getAttribute('data-page'));
                if (page > totalPages) totalPages = page;
            });
            
            // Calculate new page
            const newPage = Math.max(1, Math.min(currentPage + direction, totalPages));
            
            if (newPage === currentPage) return;
            
            // Update display
            items.forEach(item => {
                const itemPage = parseInt(item.getAttribute('data-page'));
                item.style.display = itemPage === newPage ? '' : 'none';
            });
            
            currentPageSpan.textContent = newPage;
        }
        
        function filterSubfinderSubdomains(widgetId) {
            const widget = document.getElementById(widgetId);
            const searchInput = widget.querySelector('.subdomain-search-input');
            const searchTerm = searchInput.value.toLowerCase();
            const groups = widget.querySelectorAll('.subdomain-group');
            
            groups.forEach(group => {
                const items = group.querySelectorAll('.subdomain-item');
                let visibleCount = 0;
                
                items.forEach(item => {
                    const subdomain = item.getAttribute('data-subdomain');
                    if (subdomain.includes(searchTerm)) {
                        item.style.display = '';
                        visibleCount++;
                    } else {
                        item.style.display = 'none';
                    }
                });
                
                // Hide group if no visible items
                if (visibleCount === 0) {
                    group.style.display = 'none';
                } else {
                    group.style.display = '';
                }
            });
        }
        </script>
        
        <style>
        .subdomain-display-widget {
            margin: 1em 0;
        }
        
        .subdomain-search-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1em;
            padding: 1em;
            background: #f8fbfd;
            border-radius: 4px;
        }
        
        .subdomain-search-input {
            flex: 1;
            max-width: 500px;
            padding: 0.75em;
            border: 1px solid #cfe6fb;
            border-radius: 4px;
            font-size: 1em;
        }
        
        .subdomain-count-badge {
            background: #075985;
            color: white;
            padding: 0.5em 1em;
            border-radius: 4px;
            font-weight: bold;
            margin-left: 1em;
        }
        
        .subdomain-groups-container {
            border: 1px solid #e6eef6;
            border-radius: 4px;
        }
        
        .subdomain-group {
            border-bottom: 1px solid #e6eef6;
        }
        
        .subdomain-group:last-child {
            border-bottom: none;
        }
        
        .subdomain-group-header {
            display: flex;
            align-items: center;
            padding: 1em;
            background: #f8fbfd;
            cursor: pointer;
            user-select: none;
        }
        
        .subdomain-group-header:hover {
            background: #e6f0fa;
        }
        
        .subdomain-group-icon {
            font-size: 1.2em;
            margin-right: 0.5em;
        }
        
        .subdomain-group-title {
            flex: 1;
            font-weight: bold;
            color: #075985;
        }
        
        .subdomain-group-count {
            background: #e6f0fa;
            color: #075985;
            padding: 0.25em 0.75em;
            border-radius: 12px;
            font-size: 0.9em;
            margin-right: 0.5em;
        }
        
        .subdomain-group-toggle {
            color: #075985;
            transition: transform 0.2s;
        }
        
        .subdomain-group-content {
            padding: 1em;
            background: white;
        }
        
        .subdomain-list {
            display: flex;
            flex-direction: column;
            gap: 0.5em;
        }
        
        .subdomain-item {
            padding: 0.75em;
            background: #f8fbfd;
            border-radius: 4px;
            border-left: 3px solid #075985;
        }
        
        .subdomain-item:hover {
            background: #e6f0fa;
        }
        
        .subdomain-host {
            font-family: 'Courier New', monospace;
            color: #075985;
            font-weight: bold;
        }
        
        .subdomain-pagination {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 1em;
            margin-top: 1em;
            padding: 1em;
            background: #f8fbfd;
            border-radius: 4px;
        }
        
        .subdomain-page-btn {
            padding: 0.5em 1em;
            background: #075985;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        
        .subdomain-page-btn:hover {
            background: #064668;
        }
        
        .subdomain-page-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        
        .subdomain-page-info {
            color: #075985;
            font-weight: bold;
        }
        </style>
        '''
        
        return html

    def _generate_pdf_subdomain_list(self, subdomains, max_subdomains=75):
        """
        Generate a PDF-friendly truncated subdomain list.
        Shows the first max_subdomains subdomains in a simple list format with a truncation notice.
        
        Args:
            subdomains: List of subdomain dictionaries with 'host' and 'source' keys
            max_subdomains: Maximum number of subdomains to display (default: 75)
            
        Returns:
            HTML string with truncated subdomain list
        """
        if not subdomains:
            return "<p>No subdomains found.</p>"
        
        total_count = len(subdomains)
        display_subdomains = subdomains[:max_subdomains]
        truncated_count = total_count - len(display_subdomains)
        
        html = '<div class="pdf-subdomain-list">'
        html += f'<div class="pdf-subdomain-header"><strong>Discovered Subdomains</strong> (showing {len(display_subdomains)} of {total_count})</div>'
        html += '<ul class="pdf-subdomain-items">'
        
        for subdomain in display_subdomains:
            host = subdomain['host']
            source = subdomain['source']
            # Escape HTML characters
            safe_host = host.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            safe_source = source.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            html += f'<li class="pdf-subdomain-item"><code>{safe_host}</code> <span style="color: #666; font-size: 0.9em;">({safe_source})</span></li>'
        
        html += '</ul>'
        
        if truncated_count > 0:
            html += f'<div class="pdf-subdomain-truncation">📋 <strong>Note:</strong> {truncated_count} additional subdomain(s) not shown in PDF. View the full interactive HTML report for complete subdomain list with search and filtering capabilities.</div>'
        
        html += '</div>'
        
        return html
