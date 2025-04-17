#!/usr/bin/env python3

import os
import json
import time
from datetime import datetime
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def generate_report(target, results, output_dir):
    """
    Generate a report from scan results
    
    Args:
        target (str): The target that was scanned
        results (dict): The scan results
        output_dir (str): Directory to save the report
        
    Returns:
        str: Path to the generated report
    """
    logger.info(f"Generating report for {target}")
    
    # Create report directory if it doesn't exist
    report_dir = os.path.join(output_dir, 'report')
    os.makedirs(report_dir, exist_ok=True)
    
    # Define report file path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(report_dir, f'report_{timestamp}.html')
    json_report_file = os.path.join(report_dir, f'report_{timestamp}.json')
    
    # Save the raw results as JSON for reference
    with open(json_report_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Generate a basic HTML report
    html = generate_html_report(target, results, output_dir)
    
    # Write the HTML report
    with open(report_file, 'w') as f:
        f.write(html)
    
    logger.info(f"Report generated: {report_file}")
    return report_file

def generate_html_report(target, results, output_dir):
    """
    Generate HTML report content
    
    Args:
        target (str): The target that was scanned
        results (dict): The scan results
        output_dir (str): Directory where results are stored
        
    Returns:
        str: HTML report content
    """
    # Get current date and time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Start building the HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KAST Scan Report - {target}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            margin-bottom: 20px;
        }}
        h1, h2, h3 {{
            margin-top: 0;
        }}
        .summary {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .severity-high {{
            color: #d9534f;
            font-weight: bold;
        }}
        .severity-medium {{
            color: #f0ad4e;
            font-weight: bold;
        }}
        .severity-low {{
            color: #5bc0de;
        }}
        .severity-info {{
            color: #5cb85c;
        }}
        footer {{
            margin-top: 30px;
            text-align: center;
            font-size: 0.8em;
            color: #777;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>KAST Security Scan Report</h1>
            <p>Target: {target}</p>
            <p>Generated: {now}</p>
        </header>

        <div class="summary">
            <h2>Scan Summary</h2>
            <p>This report contains the results of security scans performed against {target}.</p>
        </div>
"""
    
    # Add reconnaissance results if available
    if 'recon' in results:
        html += """
        <div class="section">
            <h2>Reconnaissance Results</h2>
"""
        
        # Add WhatWeb results
        if 'whatweb' in results['recon']:
            html += """
            <h3>Technology Detection (WhatWeb)</h3>
            <p>The following technologies were detected:</p>
            <ul>
"""
            whatweb = results['recon']['whatweb']
            if isinstance(whatweb, list) and len(whatweb) > 0:
                for item in whatweb:
                    if 'plugins' in item:
                        for plugin, data in item['plugins'].items():
                            html += f"                <li><strong>{plugin}</strong>: {data}</li>\n"
            html += "            </ul>\n"
        
        html += "        </div>\n"
    
    # Add vulnerability scan results if available
    if 'vuln' in results:
        html += """
        <div class="section">
            <h2>Vulnerability Scan Results</h2>
"""
        
        # Add Nikto results
        if 'nikto' in results['vuln']:
            nikto = results['vuln']['nikto']
            
            if 'summary' in nikto:
                summary = nikto['summary']
                
                html += f"""
            <h3>Web Vulnerability Scan (Nikto)</h3>
            <p>Scan type: {summary.get('scan_type', 'Unknown')}</p>
            <p>Duration: {summary.get('duration', 'Unknown')}</p>
            
            <h4>Findings Summary</h4>
            <table>
                <tr>
                    <th>Severity</th>
                    <th>Count</th>
                </tr>
"""
                
                vulns = summary.get('vulnerabilities', {})
                html += f"""
                <tr>
                    <td class="severity-high">High</td>
                    <td>{vulns.get('high', 0)}</td>
                </tr>
                <tr>
                    <td class="severity-medium">Medium</td>
                    <td>{vulns.get('medium', 0)}</td>
                </tr>
                <tr>
                    <td class="severity-low">Low</td>
                    <td>{vulns.get('low', 0)}</td>
                </tr>
                <tr>
                    <td class="severity-info">Informational</td>
                    <td>{vulns.get('info', 0)}</td>
                </tr>
                <tr>
                    <th>Total</th>
                    <th>{summary.get('total_findings', 0)}</th>
                </tr>
            </table>
"""
                
                # Add detailed findings
                if 'findings' in summary and summary['findings']:
                    html += """
            <h4>Detailed Findings</h4>
            <table>
                <tr>
                    <th>Severity</th>
                    <th>Description</th>
                    <th>URL</th>
                    <th>ID</th>
                </tr>
"""
                    
                    for finding in summary['findings']:
                        severity_class = f"severity-{finding.get('severity', 'info')}"
                        html += f"""
                <tr>
                    <td class="{severity_class}">{finding.get('severity', 'Unknown').upper()}</td>
                    <td>{finding.get('message', 'No description')}</td>
                    <td>{finding.get('url', 'N/A')}</td>
                    <td>{finding.get('id', 'N/A')}</td>
                </tr>"""
                    
                    html += """
            </table>
"""
        
        html += "        </div>\n"
    
    # Close the HTML
    html += """
        <footer>
            <p>This report was generated by KAST (Kali Automated Scanning Tool)</p>
            <p>Use this information responsibly and ethically.</p>
        </footer>
    </div>
</body>
</html>
"""
    
    return html
