"""
File: plugins/script_detection_plugin.py
Description: Detects and analyzes external JavaScript files loaded by target website
"""

import os
import json
import requests
from datetime import datetime
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from kast.plugins.base import KastPlugin
from pprint import pformat


class ScriptDetectionPlugin(KastPlugin):
    priority = 10  # Run after Observatory (priority 5)

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self.name = "script_detection"
        self.display_name = "External Script Detection"
        self.description = "Detects and analyzes external JavaScript files loaded by the target."
        self.website_url = "https://developer.mozilla.org/en-US/docs/Web/HTML/Element/script"
        self.scan_type = "passive"
        self.output_type = "stdout"
        
        # Dependency: wait for Observatory to complete for correlation
        self.dependencies = [
            {
                'plugin': 'mozilla_observatory',
                'condition': lambda result: result.get('disposition') in ['success', 'fail']
            }
        ]

    def setup(self, target, output_dir):
        """Optional setup before run"""
        self.debug("Setup completed.")

    def is_available(self):
        """
        Check if required dependencies are available.
        For static HTML detection, we need:
        - requests (Python package)
        - beautifulsoup4 (Python package)
        These should be in requirements.txt
        """
        try:
            import requests
            import bs4
            return True
        except ImportError:
            return False

    def run(self, target, output_dir, report_only):
        """
        Fetch target HTML and detect external scripts.
        """
        self.setup(target, output_dir)
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        output_file = os.path.join(output_dir, f"{self.name}.json")
        
        if report_only:
            self.debug(f"[REPORT ONLY] Would fetch and analyze scripts")
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

        try:
            # Fetch the HTML
            self.debug(f"Fetching HTML from {target}")
            html_content = self._fetch_html(target)
            
            # Parse and analyze scripts
            self.debug("Parsing HTML and extracting scripts")
            script_analysis = self._analyze_scripts(html_content, target)
            
            # Save raw results to file
            with open(output_file, "w") as f:
                json.dump(script_analysis, f, indent=2)
            
            return self.get_result_dict(
                disposition="success",
                results=script_analysis,
                timestamp=timestamp
            )
            
        except Exception as e:
            self.debug(f"Error during script detection: {e}")
            return self.get_result_dict(
                disposition="fail",
                results=str(e),
                timestamp=timestamp
            )

    def _fetch_html(self, target):
        """
        Fetch HTML content from target URL.
        Handles http/https protocol prefix.
        """
        # Ensure target has protocol
        if not target.startswith(('http://', 'https://')):
            target = f'https://{target}'
        
        headers = {
            'User-Agent': 'KAST-Security-Scanner/1.0'
        }
        
        response = requests.get(
            target, 
            headers=headers,
            timeout=30,
            verify=True,  # Verify SSL certificates
            allow_redirects=True
        )
        response.raise_for_status()
        return response.text

    def _analyze_scripts(self, html_content, target_url):
        """
        Parse HTML and extract script information.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Ensure target URL has protocol for parsing
        if not target_url.startswith(('http://', 'https://')):
            target_url = f'https://{target_url}'
        
        target_origin = f"{urlparse(target_url).scheme}://{urlparse(target_url).netloc}"
        
        # Find all script tags with src attribute
        script_tags = soup.find_all('script', src=True)
        
        scripts = []
        for script in script_tags:
            src = script.get('src')
            
            # Convert relative URLs to absolute
            absolute_url = urljoin(target_url, src)
            parsed_url = urlparse(absolute_url)
            script_origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # Check if same-origin
            is_same_origin = (script_origin == target_origin)
            
            # Check for SRI
            has_sri = script.has_attr('integrity')
            integrity = script.get('integrity', None)
            
            # Check for crossorigin attribute
            crossorigin = script.get('crossorigin', None)
            
            # Check if loaded over HTTPS
            is_https = parsed_url.scheme == 'https'
            
            script_info = {
                'url': absolute_url,
                'origin': script_origin,
                'hostname': parsed_url.netloc,
                'path': parsed_url.path,
                'is_same_origin': is_same_origin,
                'is_cross_origin': not is_same_origin,
                'has_sri': has_sri,
                'integrity': integrity,
                'crossorigin': crossorigin,
                'is_https': is_https,
                'is_secure': is_https and (is_same_origin or has_sri)
            }
            
            scripts.append(script_info)
        
        # Calculate statistics
        same_origin_scripts = [s for s in scripts if s['is_same_origin']]
        cross_origin_scripts = [s for s in scripts if s['is_cross_origin']]
        scripts_with_sri = [s for s in scripts if s['has_sri']]
        scripts_without_sri = [s for s in scripts if not s['has_sri']]
        insecure_scripts = [s for s in scripts if not s['is_https']]
        unique_origins = list(set(s['origin'] for s in scripts))
        
        # Group by origin for easier analysis
        scripts_by_origin = {}
        for script in scripts:
            origin = script['origin']
            if origin not in scripts_by_origin:
                scripts_by_origin[origin] = []
            scripts_by_origin[origin].append(script)
        
        analysis = {
            'target_url': target_url,
            'target_origin': target_origin,
            'total_scripts': len(scripts),
            'same_origin_count': len(same_origin_scripts),
            'cross_origin_count': len(cross_origin_scripts),
            'scripts_with_sri': len(scripts_with_sri),
            'scripts_without_sri': len(scripts_without_sri),
            'insecure_http_scripts': len(insecure_scripts),
            'unique_origins': unique_origins,
            'unique_origin_count': len(unique_origins),
            'scripts': scripts,
            'scripts_by_origin': scripts_by_origin
        }
        
        return analysis

    def _correlate_with_observatory(self, output_dir):
        """
        Read Observatory findings to correlate with script detection.
        Reads raw observatory.json since processed file may not exist yet.
        """
        # Try processed file first, fall back to raw file
        processed_file = os.path.join(output_dir, "mozilla_observatory_processed.json")
        raw_file = os.path.join(output_dir, "mozilla_observatory.json")
        
        observatory_file = processed_file if os.path.exists(processed_file) else raw_file
        
        if not os.path.exists(observatory_file):
            self.debug("Observatory results not found")
            return None
        
        try:
            with open(observatory_file, 'r') as f:
                observatory_data = json.load(f)
            
            # Handle both raw and processed Observatory formats
            if 'findings' in observatory_data:
                # Processed format
                scan_data = observatory_data.get('findings', {}).get('results', {}).get('scan', {})
                issues = observatory_data.get('issues', [])
            else:
                # Raw format
                scan_data = observatory_data.get('scan', {})
                # In raw format, we need to check tests for CSP/SRI issues
                tests = observatory_data.get('tests', {})
                issues = []
                for test_name, test_data in tests.items():
                    if 'csp' in test_name.lower() or 'sri' in test_name.lower():
                        if test_data.get('pass') == False:
                            issues.append(test_name)
            
            # Extract CSP/SRI related issues
            csp_related = [
                issue for issue in issues 
                if 'csp' in str(issue).lower() or 'sri' in str(issue).lower()
            ]
            
            return {
                'observatory_available': True,
                'csp_sri_issues': csp_related,
                'csp_sri_issue_count': len(csp_related),
                'observatory_grade': scan_data.get('grade'),
                'source': 'processed' if 'findings' in observatory_data else 'raw'
            }
        except Exception as e:
            self.debug(f"Could not read Observatory results: {e}")
            return None

    def post_process(self, raw_output, output_dir):
        """
        Process the raw output and create structured report.
        """
        if isinstance(raw_output, dict) and raw_output.get('disposition') == 'fail':
            # Handle failure case
            processed = {
                "plugin-name": self.name,
                "plugin-description": self.description,
                "plugin-display-name": self.display_name,
                "plugin-website-url": self.website_url,
                "timestamp": raw_output.get('timestamp'),
                "findings": raw_output,
                "summary": f"Script detection failed: {raw_output.get('results')}",
                "details": "",
                "issues": [],
                "executive_summary": f"Script detection could not complete: {raw_output.get('results')}",
                "report": "Script detection failed to complete"
            }
        else:
            findings = raw_output.get('results', {})
            
            # Try to correlate with Observatory
            observatory_correlation = self._correlate_with_observatory(output_dir)
            
            # Generate summary
            summary = self._generate_summary(findings)
            
            # Generate executive summary
            executive_summary = self._generate_executive_summary(findings, observatory_correlation)
            
            # Identify issues
            issues = self._find_issues(findings, observatory_correlation)
            
            # Generate details
            details = self._generate_details(findings)
            
            processed = {
                "plugin-name": self.name,
                "plugin-description": self.description,
                "plugin-display-name": self.display_name,
                "plugin-website-url": self.website_url,
                "timestamp": raw_output.get('timestamp'),
                "findings": raw_output,
                "summary": summary,
                "details": details,
                "issues": issues,
                "executive_summary": executive_summary,
                "report": f"Analyzed {findings.get('total_scripts', 0)} external JavaScript files",
                "custom_html": self._generate_custom_html(findings),
                "observatory_correlation": observatory_correlation
            }
        
        # Save processed results
        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)
        
        return processed_path

    def _generate_summary(self, findings):
        """Generate human-readable summary"""
        total = findings.get('total_scripts', 0)
        cross_origin = findings.get('cross_origin_count', 0)
        without_sri = findings.get('scripts_without_sri', 0)
        unique_origins = findings.get('unique_origin_count', 0)
        
        return (
            f"Detected {total} external scripts: "
            f"{cross_origin} cross-origin from {unique_origins} unique origins, "
            f"{without_sri} without SRI protection"
        )

    def _generate_executive_summary(self, findings, observatory_correlation):
        """Generate executive summary with Observatory correlation"""
        lines = []
        
        total = findings.get('total_scripts', 0)
        cross_origin = findings.get('cross_origin_count', 0)
        without_sri = findings.get('scripts_without_sri', 0)
        unique_origins = findings.get('unique_origin_count', 0)
        
        lines.append(f"Website loads {total} external JavaScript files")
        
        if cross_origin > 0:
            lines.append(f"{cross_origin} scripts from {unique_origins} third-party origins")
        
        if without_sri > 0:
            lines.append(f"⚠️ {without_sri} scripts lack Subresource Integrity (SRI) protection")
        
        # Add Observatory correlation if available
        if observatory_correlation and observatory_correlation.get('observatory_available'):
            grade = observatory_correlation.get('observatory_grade', 'Unknown')
            csp_issues = observatory_correlation.get('csp_sri_issues', [])
            
            if csp_issues:
                lines.append(f"Mozilla Observatory (Grade: {grade}) identified {len(csp_issues)} CSP/SRI issues")
        
        return "\n".join(lines)

    def _generate_details(self, findings):
        """Generate detailed breakdown"""
        lines = []
        
        scripts_by_origin = findings.get('scripts_by_origin', {})
        
        for origin, scripts in scripts_by_origin.items():
            without_sri = sum(1 for s in scripts if not s['has_sri'])
            lines.append(f"{origin}: {len(scripts)} scripts ({without_sri} without SRI)")
        
        return "\n".join(lines)

    def _find_issues(self, findings, observatory_correlation):
        """
        Identify security issues based on script analysis.
        These issues should map to issue_registry.json entries.
        """
        issues = []
        
        cross_origin_no_sri = [
            s for s in findings.get('scripts', [])
            if s['is_cross_origin'] and not s['has_sri'] and s['is_https']
        ]
        
        if cross_origin_no_sri:
            # This matches existing entry in issue_registry.json
            issues.append("sri-not-implemented-but-external-scripts-loaded-securely")
        
        # Check for insecure (HTTP) external scripts
        insecure_external = [
            s for s in findings.get('scripts', [])
            if s['is_cross_origin'] and not s['is_https']
        ]
        
        if insecure_external:
            # This matches existing entry in issue_registry.json
            issues.append("sri-not-implemented-and-external-scripts-not-loaded-securely")
        
        # Check for high count of external scripts
        if findings.get('cross_origin_count', 0) > 10:
            issues.append("high-external-script-count")
        
        return issues

    def _generate_custom_html(self, findings):
        """
        Generate custom HTML widget for report display.
        Similar to Katana's URL widget.
        """
        scripts_by_origin = findings.get('scripts_by_origin', {})
        
        html_parts = []
        html_parts.append('<div class="script-analysis-widget">')
        html_parts.append(f'<h4>📊 External JavaScript Analysis</h4>')
        html_parts.append(f'<p><strong>Total Scripts:</strong> {findings.get("total_scripts", 0)}</p>')
        html_parts.append(f'<p><strong>Cross-Origin:</strong> {findings.get("cross_origin_count", 0)} from {findings.get("unique_origin_count", 0)} origins</p>')
        html_parts.append(f'<p><strong>Without SRI:</strong> {findings.get("scripts_without_sri", 0)}</p>')
        
        if findings.get('insecure_http_scripts', 0) > 0:
            html_parts.append(f'<p style="color: #dc3545;"><strong>⚠️ Insecure HTTP Scripts:</strong> {findings.get("insecure_http_scripts", 0)}</p>')
        
        html_parts.append('<div class="script-groups">')
        
        for origin, scripts in scripts_by_origin.items():
            target_origin = findings.get('target_origin', '')
            is_same_origin = (origin == target_origin)
            
            html_parts.append(f'<div class="script-group">')
            html_parts.append(f'<h5>{"🏠" if is_same_origin else "🌐"} {origin} ({len(scripts)} scripts)</h5>')
            html_parts.append('<ul class="script-list">')
            
            for script in scripts[:10]:  # Limit to first 10 per origin
                sri_indicator = "✓" if script['has_sri'] else "⚠️"
                secure_indicator = "🔒" if script['is_https'] else "🔓"
                html_parts.append(f'<li>{sri_indicator} {secure_indicator} {script["path"]}</li>')
            
            if len(scripts) > 10:
                html_parts.append(f'<li><em>... and {len(scripts) - 10} more</em></li>')
            
            html_parts.append('</ul>')
            html_parts.append('</div>')
        
        html_parts.append('</div>')
        html_parts.append('</div>')
        
        return '\n'.join(html_parts)

    def get_dry_run_info(self, target, output_dir):
        """
        Return information about what script_detection would do.
        This is an internal logic plugin with no CLI commands.
        """
        # Ensure target has protocol for display
        if not target.startswith(('http://', 'https://')):
            display_target = f'https://{target}'
        else:
            display_target = target
        
        return {
            "commands": [],  # No CLI commands
            "description": self.description,
            "operations": [
                f"1. Fetch HTML from {display_target}",
                "2. Parse HTML with BeautifulSoup",
                "3. Extract all <script> tags with 'src' attributes",
                "4. Analyze script origins, SRI, and HTTPS usage",
                "5. Correlate findings with Mozilla Observatory results (if available)"
            ]
        }
