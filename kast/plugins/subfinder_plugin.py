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
        self.scan_type = "passive"  # or "active"
        self.output_type = "file"    # or "stdout"

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

    def post_process(self, raw_output, output_dir):
        """
        Normalize output, extract issues, and build executive_summary.
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

        # Initialize issues and details
        issues = []
        details = ""

        summary = self._generate_summary(findings)
        executive_summary = self._generate_executive_summary(findings)
        custom_html = self._generate_custom_html(findings)
        self.debug(f"{self.name} summary: {summary}")
        self.debug(f"{self.name} issues: {issues}")
        self.debug(f"{self.name} details:\n{details}")

        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": getattr(self, 'display_name', None),
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "summary": summary or f"{self.name} did not produce any findings",
            "details": details,
            "issues": issues,
            "executive_summary": executive_summary,
            "custom_html": custom_html
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
        
        # Generate a concise summary instead of listing all subdomains
        # The full list is available in the custom HTML table below
        if count <= 10:
            # For small numbers, we can list them
            subdomain_names = detected_subdomains
            summary_text = f"Detected {count} subdomain(s): {', '.join(subdomain_names)}"
        else:
            # For large numbers, just show the count and refer to the table
            summary_text = f"Detected {count} unique subdomain(s). See the table below for the complete list."
        
        self.debug(f"Generated summary: {summary_text}")
        return summary_text

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

    def _generate_custom_html(self, findings):
        """
        Generate custom HTML for displaying subdomains in a sortable table with pagination.
        """
        results = findings.get("results", []) if isinstance(findings, dict) else []
        
        if not results:
            return ""
        
        # Extract subdomain data
        subdomains = []
        for entry in results:
            host = entry.get("host", "")
            source = entry.get("source", "unknown")
            subdomains.append({"host": host, "source": source})
        
        # Sort by host name
        subdomains.sort(key=lambda x: x["host"])
        
        # Generate HTML
        html = """
<div class="subfinder-table-container">
    <div style="margin-bottom: 1em;">
        <button id="subfinder-toggle-btn" onclick="toggleSubfinderTable()" 
                style="padding: 0.5em 1em; background: #075985; color: white; border: none; border-radius: 4px; cursor: pointer; margin-right: 1em;">
            Hide Table
        </button>
        <span style="color: #365b6a; font-weight: bold;">
            <span id="subfinder-total-count">0</span> subdomains found
        </span>
    </div>
    <div id="subfinder-table-wrapper">
        <div style="margin-bottom: 1em;">
            <input type="text" id="subfinder-search" placeholder="Search subdomains..." 
                   style="padding: 0.5em; width: 300px; border: 1px solid #cfe6fb; border-radius: 4px;">
            <span style="margin-left: 1em; color: #365b6a;">
                Showing <span id="subfinder-visible-count">0</span> of <span id="subfinder-total-count-2">0</span> subdomains
            </span>
        </div>
    <table id="subfinder-table" style="width: 100%; border-collapse: collapse; background: white;">
        <thead>
            <tr style="background: #e6f0fa; border-bottom: 2px solid #075985;">
                <th style="padding: 0.75em; text-align: left; cursor: pointer; user-select: none;" onclick="sortSubfinderTable(0)">
                    Subdomain <span id="sort-icon-0">▼</span>
                </th>
                <th style="padding: 0.75em; text-align: left; cursor: pointer; user-select: none;" onclick="sortSubfinderTable(1)">
                    Source <span id="sort-icon-1"></span>
                </th>
            </tr>
        </thead>
        <tbody id="subfinder-tbody">
"""
        
        # Add rows
        for i, subdomain in enumerate(subdomains):
            row_class = "subfinder-row" + (" subfinder-hidden" if i >= 50 else "")
            html += f"""
            <tr class="{row_class}" style="border-bottom: 1px solid #e6eef6;">
                <td style="padding: 0.5em; font-family: monospace;">{subdomain['host']}</td>
                <td style="padding: 0.5em; color: #365b6a;">{subdomain['source']}</td>
            </tr>
"""
        
        html += """
        </tbody>
    </table>
    <div id="subfinder-show-more" style="margin-top: 1em; text-align: center;">
        <button onclick="showAllSubfinderRows()" style="padding: 0.5em 1.5em; background: #075985; color: white; border: none; border-radius: 4px; cursor: pointer;">
            Show All Results
        </button>
    </div>
    </div>
</div>

<script>
(function() {
    let subfinderSortOrder = [1, 0]; // [column, direction] - 0: asc, 1: desc
    let subfinderTableVisible = true;
    
    window.toggleSubfinderTable = function() {
        const wrapper = document.getElementById('subfinder-table-wrapper');
        const btn = document.getElementById('subfinder-toggle-btn');
        subfinderTableVisible = !subfinderTableVisible;
        
        if (subfinderTableVisible) {
            wrapper.style.display = 'block';
            btn.textContent = 'Hide Table';
        } else {
            wrapper.style.display = 'none';
            btn.textContent = 'Show Table';
        }
    };
    
    function updateSubfinderCount() {
        const rows = document.querySelectorAll('#subfinder-tbody tr');
        const visibleRows = document.querySelectorAll('#subfinder-tbody tr:not(.subfinder-hidden)');
        const totalCount = rows.length;
        document.getElementById('subfinder-total-count').textContent = totalCount;
        document.getElementById('subfinder-total-count-2').textContent = totalCount;
        document.getElementById('subfinder-visible-count').textContent = visibleRows.length;
        
        // Hide "Show All" button if all rows are visible
        const showMoreDiv = document.getElementById('subfinder-show-more');
        if (visibleRows.length === rows.length) {
            showMoreDiv.style.display = 'none';
        } else {
            showMoreDiv.style.display = 'block';
        }
    }
    
    window.sortSubfinderTable = function(column) {
        const tbody = document.getElementById('subfinder-tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        
        // Toggle sort direction if same column, otherwise default to ascending
        if (subfinderSortOrder[0] === column) {
            subfinderSortOrder[1] = 1 - subfinderSortOrder[1];
        } else {
            subfinderSortOrder = [column, 0];
        }
        
        // Update sort icons
        document.querySelectorAll('[id^="sort-icon-"]').forEach(el => el.textContent = '');
        document.getElementById('sort-icon-' + column).textContent = subfinderSortOrder[1] === 0 ? '▼' : '▲';
        
        // Sort rows
        rows.sort((a, b) => {
            const aText = a.cells[column].textContent.trim();
            const bText = b.cells[column].textContent.trim();
            const comparison = aText.localeCompare(bText);
            return subfinderSortOrder[1] === 0 ? comparison : -comparison;
        });
        
        // Re-append sorted rows
        rows.forEach(row => tbody.appendChild(row));
    };
    
    window.showAllSubfinderRows = function() {
        document.querySelectorAll('.subfinder-row').forEach(row => {
            row.classList.remove('subfinder-hidden');
        });
        updateSubfinderCount();
    };
    
    // Search functionality
    document.getElementById('subfinder-search').addEventListener('input', function(e) {
        const searchTerm = e.target.value.toLowerCase();
        const rows = document.querySelectorAll('#subfinder-tbody tr');
        
        rows.forEach(row => {
            const host = row.cells[0].textContent.toLowerCase();
            const source = row.cells[1].textContent.toLowerCase();
            
            if (host.includes(searchTerm) || source.includes(searchTerm)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
        
        updateSubfinderCount();
    });
    
    // Initialize count on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateSubfinderCount);
    } else {
        updateSubfinderCount();
    }
})();
</script>

<style>
.subfinder-hidden {
    display: none;
}
#subfinder-table th:hover {
    background: #d6eafc;
}
#subfinder-table tbody tr:hover {
    background: #f8fbfd;
}
</style>
"""
        
        return html
