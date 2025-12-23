"""
File: plugins/ftap_plugin.py
Description: KAST plugin for Find The Admin Panel

TODO: Customize the following sections:
  1. Command structure in run() method
  2. Output parsing in post_process() method
  3. Issue extraction logic
  4. Executive summary generation
  5. Update _generate_summary() if needed
"""

import subprocess
import shutil
import json
import os
from datetime import datetime
from kast.plugins.base import KastPlugin
from pprint import pformat

class FtapPlugin(KastPlugin):
    priority = 50  # Set plugin run order (lower runs earlier)
    
    # Configuration schema for FTAP
    config_schema = {
        "type": "object",
        "title": "FTAP Configuration",
        "description": "Configuration for Find The Admin Panel plugin",
        "properties": {
            "detection_mode": {
                "type": "string",
                "title": "Detection Mode",
                "description": "Scanning strategy: simple (basic), stealth (careful), or aggressive (fast)",
                "enum": ["simple", "stealth", "aggressive"],
                "default": "stealth"
            },
            "wordlist_path": {
                "type": "string",
                "title": "Custom Wordlist Path",
                "description": "Path to custom wordlist file for admin path discovery",
                "default": None
            },
            "update_wordlist": {
                "type": "boolean",
                "title": "Update Wordlist",
                "description": "Update wordlists with latest admin paths before scanning",
                "default": False
            },
            "wordlist_source": {
                "type": "string",
                "title": "Wordlist Update Source",
                "description": "Source URL for wordlist updates (requires update_wordlist=true)",
                "default": None
            },
            "machine_learning": {
                "type": "boolean",
                "title": "Machine Learning Detection",
                "description": "Enable ML-based admin panel detection (experimental)",
                "default": False
            },
            "fuzzing": {
                "type": "boolean",
                "title": "Path Fuzzing",
                "description": "Enable path fuzzing capabilities for discovery",
                "default": False
            },
            "http3": {
                "type": "boolean",
                "title": "HTTP/3 Support",
                "description": "Enable HTTP/3 protocol support",
                "default": False
            },
            "concurrency": {
                "type": "integer",
                "title": "Concurrent Requests",
                "description": "Maximum number of concurrent requests",
                "minimum": 1,
                "maximum": 200,
                "default": None
            },
            "export_format": {
                "type": "string",
                "title": "Export Format",
                "description": "Output format for results",
                "enum": ["json", "html", "csv", "txt"],
                "default": "json"
            },
            "interactive": {
                "type": "boolean",
                "title": "Interactive Mode",
                "description": "Run in interactive mode (prompts for input)",
                "default": False
            }
        }
    }

    def __init__(self, cli_args, config_manager=None):
        self.name = "ftap"  # Set name before calling parent __init__
        super().__init__(cli_args, config_manager)
        self.display_name = "Find The Admin Panel"  # Human-readable name for reports
        self.description = "Scans target for exposed admin login pages"
        self.website_url = "https://github.com/DV64/Find-The-Admin-Panel"
        self.scan_type = "active"
        self.output_type = "file"
        self.command_executed = None
        
        # Load plugin configuration values into instance variables
        self._load_plugin_config()
    
    def _load_plugin_config(self):
        """
        Load configuration values from ConfigManager.
        Sets instance variables for all configurable options.
        """
        # Detection settings
        self.detection_mode = self.get_config("detection_mode", "stealth")
        self.machine_learning = self.get_config("machine_learning", False)
        self.fuzzing = self.get_config("fuzzing", False)
        self.http3 = self.get_config("http3", False)
        
        # Wordlist settings
        self.wordlist_path = self.get_config("wordlist_path", None)
        self.update_wordlist = self.get_config("update_wordlist", False)
        self.wordlist_source = self.get_config("wordlist_source", None)
        
        # Performance settings
        self.concurrency = self.get_config("concurrency", None)
        
        # Output settings
        self.export_format = self.get_config("export_format", "json")
        self.interactive = self.get_config("interactive", False)
        
        # Debug log configuration
        self.debug(f"FTAP configuration loaded:")
        self.debug(f"  detection_mode: {self.detection_mode}")
        self.debug(f"  machine_learning: {self.machine_learning}")
        self.debug(f"  fuzzing: {self.fuzzing}")
        self.debug(f"  http3: {self.http3}")
        self.debug(f"  wordlist_path: {self.wordlist_path}")
        self.debug(f"  update_wordlist: {self.update_wordlist}")
        self.debug(f"  concurrency: {self.concurrency}")
        self.debug(f"  export_format: {self.export_format}")

    def setup(self, target, output_dir):
        """
        Optional setup step before the run.
        You could add logic here to validate target, pre-create dirs, etc.
        """
        self.debug("Setup completed.")

    def is_available(self):
        """
        Check if required tool is installed and available in PATH.
        """
        # Example: Check if tool is available
        return shutil.which("ftap") is not None

    def run(self, target, output_dir, report_only):
        """
        Run the tool and return standardized result dict.
        Builds command dynamically based on configuration.
        """
        self.setup(target, output_dir)
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        
        # Determine output filename based on export format
        if self.export_format == "json":
            output_filename = "ftap.json"
        elif self.export_format == "html":
            output_filename = "ftap.html"
        elif self.export_format == "csv":
            output_filename = "ftap.csv"
        else:  # txt
            output_filename = "ftap.txt"
        
        output_file = os.path.join(output_dir, output_filename)
        
        # Build command dynamically based on configuration
        cmd = ["ftap", "--url", target]
        
        # Add detection mode
        cmd.extend(["--detection-mode", self.detection_mode])
        
        # Add output directory and format
        cmd.extend(["-d", str(output_dir)])
        cmd.extend(["-e", self.export_format])
        cmd.extend(["-f", output_filename])
        
        # Add wordlist if specified
        if self.wordlist_path:
            cmd.extend(["-w", self.wordlist_path])
        
        # Add wordlist update if enabled
        if self.update_wordlist:
            cmd.append("--update-wordlist")
            if self.wordlist_source:
                cmd.extend(["--source", self.wordlist_source])
        
        # Add advanced features
        if self.machine_learning:
            cmd.append("--machine-learning")
        
        if self.fuzzing:
            cmd.append("--fuzzing")
        
        if self.http3:
            cmd.append("--http3")
        
        # Add concurrency if specified
        if self.concurrency is not None:
            cmd.extend(["--concurrency", str(self.concurrency)])
        
        # Add interactive mode if enabled
        if self.interactive:
            cmd.append("-i")

        # Store command for reporting
        self.command_executed = ' '.join(cmd)
        
        self.debug(f"Built FTAP command: {self.command_executed}")

        # Check if tool is available
        if not self.is_available():
            return self.get_result_dict(
                disposition="fail",
                results="Tool is not installed or not found in PATH.",
                timestamp=timestamp
            )

        try:
            if report_only:
                self.debug(f"[REPORT ONLY] Would run command: {self.command_executed}")
                # In report-only mode, try to load existing results
                if os.path.exists(output_file):
                    with open(output_file, "r") as f:
                        if self.export_format == "json":
                            results = json.load(f)
                        else:
                            results = f.read()
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
                # Create empty output file first, so that kast-web knows we are running
                in_progress_file = os.path.join(output_dir, output_filename)
                open(in_progress_file, 'a').close()

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
                if self.export_format == "json":
                    results = json.load(f)
                else:
                    results = f.read()

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
        """
        # Handle different input types
        if isinstance(raw_output, dict) and raw_output.get('disposition') == 'fail':
            # Plugin run failed, return minimal processed output
            findings = {}
        elif isinstance(raw_output, str) and os.path.isfile(raw_output):
            # Load from file path
            with open(raw_output, "r") as f:
                findings = json.load(f)
        elif isinstance(raw_output, dict):
            # Check if this is a result dict from run() or actual ftap data
            if 'disposition' in raw_output and 'results' in raw_output:
                # This is a result dict from run(), extract the results field
                findings = raw_output.get('results', {})
            else:
                # This is actual ftap data (has scan_info, results, etc.)
                findings = raw_output
        else:
            try:
                findings = json.loads(raw_output)
            except Exception:
                findings = {}

        self.debug(f"{self.name} raw findings:\n{pformat(findings)}")

        # Extract issues - each exposed admin panel is an issue
        # Filter out findings with confidence < 0.86
        issues = []
        # Handle both direct results array and dict with results key
        if isinstance(findings, dict):
            results = findings.get("results", [])
        elif isinstance(findings, list):
            results = findings
        else:
            results = []
        
        for panel in results:
            if panel.get("found", False) and panel.get("confidence", 0) >= 0.86:
                # Create issue entry for each exposed admin panel
                issue_entry = "exposed_admin_panel"
                issues.append(issue_entry)

        # Build details section with formatted information
        details = self._build_details(findings)

        # Build executive summary with panel information
        executive_summary = self._build_executive_summary(findings)

        # Generate summary using helper method
        summary = self._generate_summary(findings)
        self.debug(f"{self.name} summary: {summary}")
        self.debug(f"{self.name} issues: {issues}")
        self.debug(f"{self.name} details:\n{details}")

        # Format command for report notes
        report_notes = self._format_command_for_report()

        # Generate custom HTML for interactive display
        custom_html = self._generate_panel_display_html(findings)
        custom_html_pdf = self._generate_pdf_panel_list(findings)

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": getattr(self, 'display_name', None),
            "plugin-website-url": getattr(self, 'website_url', None),
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "summary": summary or f"{self.name} did not produce any findings",
            "details": details,
            "issues": issues,  # Always present, even if empty
            "executive_summary": executive_summary,  # Always present
            "report": report_notes,
            "custom_html": custom_html,
            "custom_html_pdf": custom_html_pdf,
            "results_message": "📋 View panel details below"
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
        
        # Extract results array and filter by confidence >= 0.86
        results = findings.get("results", []) if isinstance(findings, dict) else []
        found_count = len([r for r in results if r.get("found", False) and r.get("confidence", 0) >= 0.86])
        
        if found_count == 0:
            return f"No exposed admin panels were found."
        elif found_count == 1:
            return f"Found 1 exposed admin panel."
        else:
            return f"Found {found_count} exposed admin panels."

    def _build_details(self, findings):
        """
        Build detailed information about discovered admin panels.
        Returns formatted string with panel details.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        
        # Filter results by confidence >= 0.86
        high_confidence_results = [r for r in results if r.get("found", False) and r.get("confidence", 0) >= 0.86]
        
        if not high_confidence_results:
            return "No admin panels detected."
        
        details_lines = []
        details_lines.append("Exposed Admin Panels:")
        details_lines.append("")
        
        for idx, panel in enumerate(high_confidence_results, 1):
            url = panel.get("url", "N/A")
            title = panel.get("title", "N/A")
            confidence = panel.get("confidence", 0)
            status_code = panel.get("status_code", "N/A")
            has_login = panel.get("has_login_form", False)
            technologies = panel.get("technologies", [])
            
            details_lines.append(f"Panel #{idx}:")
            details_lines.append(f"  URL: {url}")
            details_lines.append(f"  Title: {title}")
            details_lines.append(f"  Confidence: {confidence:.1%}")
            details_lines.append(f"  Status Code: {status_code}")
            details_lines.append(f"  Login Form Detected: {'Yes' if has_login else 'No'}")
            if technologies:
                details_lines.append(f"  Technologies: {', '.join(technologies)}")
            details_lines.append("")
        
        return "\n".join(details_lines)

    def _build_executive_summary(self, findings):
        """
        Build executive summary - simple one-sentence format.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        # Filter by confidence >= 0.86
        found_panels = [r for r in results if r.get("found", False) and r.get("confidence", 0) >= 0.86]
        
        panel_count = len(found_panels)
        
        if panel_count == 0:
            return "No admin panels found."
        elif panel_count == 1:
            return "Found 1 admin panel."
        else:
            return f"Found {panel_count} admin panels."

    def _format_command_for_report(self):
        """
        Format the executed command for the report notes section.
        Returns HTML-formatted command with dark blue color and monospace font.
        """
        if not self.command_executed:
            return "Command not available"
        
        return f'<code style="color: #00008B; font-family: Consolas, \'Courier New\', monospace;">{self.command_executed}</code>'

    def _generate_panel_display_html(self, findings):
        """
        Generate custom HTML for displaying admin panels with grouping and search.
        Panels are grouped into three categories:
        1. "Exposed Admin Panels" (found=True, confidence ≥0.86)
        2. "Other Findings" (found=True, confidence <0.86)
        3. "Other URLs Tested" (found=False or not categorized above)
        Simplified single-level display matching katana's style.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        
        if not results:
            return "<p>No admin panels found.</p>"
        
        # Split into three groups
        exposed_panels = [r for r in results if r.get("found", False) and r.get("confidence", 0) >= 0.86]
        other_findings = [r for r in results if r.get("found", False) and r.get("confidence", 0) < 0.86]
        # Other URLs tested includes everything that wasn't found (found=False or missing 'found' key)
        other_urls = [r for r in results if not r.get("found", False)]
        
        # Generate unique ID for this instance
        widget_id = f"ftap-panel-widget-{id(self)}"
        
        html = f'''
        <div class="url-display-widget" id="{widget_id}">
            <div class="url-search-container">
                <input type="text" 
                       class="url-search-input" 
                       placeholder="🔍 Search panels (e.g., admin, login, dashboard)..."
                       onkeyup="filterFtapPanels('{widget_id}')">
                <span class="url-count-badge">Total: {len(results)} URL(s) Tested</span>
            </div>
            
            <div class="url-groups-container">
        '''
        
        # Generate exposed panels group
        if exposed_panels:
            html += self._generate_group_html("Exposed Admin Panels", exposed_panels, f"{widget_id}-exposed", "🔐")
        
        # Generate other findings group
        if other_findings:
            html += self._generate_group_html("Other Findings", other_findings, f"{widget_id}-other", "📋")
        
        # Generate other URLs tested group
        if other_urls:
            html += self._generate_group_html("Other URLs Tested", other_urls, f"{widget_id}-tested", "🔍")
        
        html += '''
            </div>
        </div>
        '''
        
        return html

    def _generate_group_html(self, group_name, panels, group_id, icon):
        """
        Generate HTML for a single panel group with pagination.
        Matches katana's style with 50 panels per page.
        """
        panels_per_page = 50
        total_panels = len(panels)
        total_pages = (total_panels + panels_per_page - 1) // panels_per_page
        
        html = f'''
        <div class="url-group" data-group="{group_id}">
            <div class="url-group-header" onclick="toggleUrlGroup('{group_id}')">
                <span class="url-group-icon">{icon}</span>
                <span class="url-group-title">{group_name}</span>
                <span class="url-group-count">{total_panels} Panel(s)</span>
                <span class="url-group-toggle">▼</span>
            </div>
            <div class="url-group-content" id="{group_id}-content" style="display: none;">
                <div class="ftap-panels-list" id="{group_id}-list">
        '''
        
        # Add all panels with page data attributes
        for page_num in range(total_pages):
            start_idx = page_num * panels_per_page
            end_idx = min(start_idx + panels_per_page, total_panels)
            
            for idx in range(start_idx, end_idx):
                panel = panels[idx]
                display_style = 'display: none;' if page_num > 0 else ''
                html += self._get_panel_html(panel, idx + 1, group_id, page_num + 1, display_style)
        
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

    def _get_panel_html(self, panel, panel_idx, group_id, page_num, display_style):
        """
        Generate HTML for a single admin panel card.
        Simplified flat display matching katana's style - all details always visible.
        """
        panel_id = f"{group_id}-panel-{panel_idx}"
        url = panel.get("url", "N/A")
        title = panel.get("title", "Unknown")
        confidence = panel.get("confidence", 0)
        status_code = panel.get("status_code", "N/A")
        has_login = panel.get("has_login_form", False)
        technologies = panel.get("technologies", [])
        
        # Determine confidence color
        if confidence >= 0.9:
            confidence_color = "#28a745"
        elif confidence >= 0.7:
            confidence_color = "#ffc107"
        else:
            confidence_color = "#dc3545"
        
        # Create searchable data attribute
        search_text = f"{url} {title} {' '.join(technologies)}".lower()
        
        # Build a clean, always-visible card matching katana's simplicity
        html = f'''
        <div class="url-item" data-page="{page_num}" data-url="{search_text}" style="{display_style}">
            <div style="padding: 0.8em; background: #f8fbfd; border-radius: 6px; border: 1px solid #e6eef6; margin: 0.3em 0;">
                <div style="display: flex; align-items: center; gap: 0.8em; margin-bottom: 0.6em;">
                    <span style="background: #075985; color: white; padding: 0.25em 0.5em; border-radius: 4px; font-size: 0.85em; font-weight: 600;">#{panel_idx}</span>
                    <span style="flex: 1; font-weight: 600; color: #083344; font-size: 0.95em;">{title}</span>
                    <span style="background-color: {confidence_color}20; color: {confidence_color}; border: 1px solid {confidence_color}; padding: 0.3em 0.7em; border-radius: 12px; font-size: 0.85em; font-weight: 600;">
                        {confidence:.1%}
                    </span>
                </div>
                <div style="padding-left: 2.5em;">
                    <div style="margin: 0.4em 0;">
                        <span style="font-weight: 600; color: #075985; font-size: 0.85em;">URL:</span>
                        <a href="{url}" target="_blank" style="color: #0284c7; text-decoration: none; margin-left: 0.5em; font-family: 'Courier New', Consolas, monospace; font-size: 0.85em; word-break: break-all;">{url}</a>
                    </div>
                    <div style="margin: 0.4em 0;">
                        <span style="font-weight: 600; color: #075985; font-size: 0.85em;">Status Code:</span>
                        <span style="margin-left: 0.5em; color: #083344; font-size: 0.85em;">{status_code}</span>
                    </div>
                    <div style="margin: 0.4em 0;">
                        <span style="font-weight: 600; color: #075985; font-size: 0.85em;">Login Form:</span>
                        <span style="margin-left: 0.5em; color: #083344; font-size: 0.85em;">{'✓ Yes' if has_login else '✗ No'}</span>
                    </div>
        '''
        
        if technologies:
            html += '''
                    <div style="margin: 0.4em 0;">
                        <span style="font-weight: 600; color: #075985; font-size: 0.85em;">Technologies:</span>
                        <div style="display: inline-flex; flex-wrap: wrap; gap: 0.4em; margin-left: 0.5em;">
            '''
            for tech in technologies:
                html += f'<span style="background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); color: #0369a1; padding: 0.2em 0.6em; border-radius: 10px; font-size: 0.75em; font-weight: 500; border: 1px solid #93c5fd;">{tech}</span>'
            html += '''
                        </div>
                    </div>
            '''
        
        html += '''
                </div>
            </div>
        </div>
        '''
        
        return html

    def _generate_pdf_panel_list(self, findings, max_panels=50):
        """
        Generate a PDF-friendly list of admin panels.
        Shows only high-confidence panels (≥0.86) with truncation notice.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        exposed_panels = [r for r in results if r.get("found", False) and r.get("confidence", 0) >= 0.86]
        
        if not exposed_panels:
            return "<p>No admin panels found.</p>"
        
        total_count = len(exposed_panels)
        display_panels = exposed_panels[:max_panels]
        truncated_count = total_count - len(display_panels)
        
        html = '<div class="pdf-url-list">'
        html += f'<div class="pdf-url-header"><strong>Exposed Admin Panels</strong> (showing {len(display_panels)} of {total_count})</div>'
        html += '<ul class="pdf-url-items">'
        
        for panel in display_panels:
            url = panel.get("url", "N/A")
            title = panel.get("title", "Unknown")
            confidence = panel.get("confidence", 0)
            
            safe_url = url.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            html += f'''
            <li class="pdf-url-item">
                <div><strong>{title}</strong> - Confidence: {confidence:.1%}</div>
                <div><code>{safe_url}</code></div>
            </li>
            '''
        
        html += '</ul>'
        
        if truncated_count > 0:
            html += f'<div class="pdf-url-truncation">📋 <strong>Note:</strong> {truncated_count} additional panel(s) not shown in PDF. View the full interactive HTML report for complete details.</div>'
        
        html += '</div>'
        
        return html

    def get_dry_run_info(self, target, output_dir):
        """
        Return information about what this plugin would do in a real run.
        Builds command using current configuration.
        """
        # Determine output filename based on export format
        if self.export_format == "json":
            output_filename = "ftap.json"
        elif self.export_format == "html":
            output_filename = "ftap.html"
        elif self.export_format == "csv":
            output_filename = "ftap.csv"
        else:  # txt
            output_filename = "ftap.txt"
        
        # Build command dynamically based on configuration
        cmd = ["ftap", "--url", target]
        
        # Add detection mode
        cmd.extend(["--detection-mode", self.detection_mode])
        
        # Add output directory and format
        cmd.extend(["-d", str(output_dir)])
        cmd.extend(["-e", self.export_format])
        cmd.extend(["-f", output_filename])
        
        # Add wordlist if specified
        if self.wordlist_path:
            cmd.extend(["-w", self.wordlist_path])
        
        # Add wordlist update if enabled
        if self.update_wordlist:
            cmd.append("--update-wordlist")
            if self.wordlist_source:
                cmd.extend(["--source", self.wordlist_source])
        
        # Add advanced features
        if self.machine_learning:
            cmd.append("--machine-learning")
        
        if self.fuzzing:
            cmd.append("--fuzzing")
        
        if self.http3:
            cmd.append("--http3")
        
        # Add concurrency if specified
        if self.concurrency is not None:
            cmd.extend(["--concurrency", str(self.concurrency)])
        
        # Add interactive mode if enabled
        if self.interactive:
            cmd.append("-i")
        
        # Build operations description
        operations = f"Scan for admin panels using {self.detection_mode} mode"
        
        if self.machine_learning:
            operations += " with machine learning detection"
        if self.fuzzing:
            operations += " and path fuzzing"
        if self.http3:
            operations += ", HTTP/3 support enabled"
        if self.concurrency:
            operations += f", concurrency: {self.concurrency}"
        if self.wordlist_path:
            operations += f", custom wordlist: {self.wordlist_path}"
        
        return {
            "commands": [' '.join(cmd)],
            "description": self.description,
            "operations": operations
        }
