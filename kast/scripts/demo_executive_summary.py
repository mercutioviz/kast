#!/usr/bin/env python
"""
Demo script to show the executive summary feature in action.
This creates a sample report with plugin executive summaries.
"""
import sys
import os

# Add the parent directory to path so we can import kast modules
sys.path.insert(0, '/opt/kast')

from kast.report_builder import generate_html_report

# Sample plugin results with executive summaries
demo_plugin_results = [
    {
        "plugin-name": "wafw00f",
        "plugin-display-name": "Wafw00f",
        "plugin-description": "Detects and identifies Web Application Firewalls (WAFs)",
        "plugin-website-url": "https://github.com/EnableSecurity/wafw00f",
        "summary": "No WAF detected",
        "details": "No WAF detected.",
        "executive_summary": "No WAFs were detected.",
        "issues": ["No WAF Detected"],
        "findings": {"disposition": "success"},
        "timestamp": "2025-11-16T21:00:00.000"
    },
    {
        "plugin-name": "mozilla_observatory",
        "plugin-display-name": "Mozilla Observatory",
        "plugin-description": "Runs Mozilla Observatory to analyze web application security",
        "plugin-website-url": "https://developer.mozilla.org/en-US/blog/mdn-http-observatory-launch/",
        "summary": "Grade: B, Score: 75, Tests Passed: 8, Tests Failed: 2",
        "details": "Observatory scan completed",
        "executive_summary": "-= Observatory grade and score summary =-\nGrade: B, Score: 75, Tests Passed: 8, Tests Failed: 2",
        "issues": ["csp-implemented-with-unsafe-inline", "x-content-type-options-not-set"],
        "findings": {"disposition": "success"},
        "timestamp": "2025-11-16T21:05:00.000"
    },
    {
        "plugin-name": "katana",
        "plugin-display-name": "Katana",
        "plugin-description": "Site crawler and URL finder",
        "plugin-website-url": "https://github.com/projectdiscovery/katana",
        "summary": "Detected 23 unique URL(s).",
        "details": "Detected 23 unique URL(s).",
        "executive_summary": "Detected 23 URLs.",
        "issues": [],
        "findings": {"disposition": "success", "results": {"urls": ["/", "/about", "/contact"]}},
        "timestamp": "2025-11-16T21:10:00.000"
    },
    {
        "plugin-name": "whatweb",
        "plugin-display-name": "WhatWeb",
        "plugin-description": "Identifies technologies used by a website",
        "plugin-website-url": "https://github.com/urbanadventurer/whatweb",
        "summary": "Detected various technologies",
        "details": "Technologies found: Apache, PHP, jQuery",
        "executive_summary": "",  # Empty - won't show in executive summary
        "issues": [],
        "findings": {"disposition": "success"},
        "timestamp": "2025-11-16T21:15:00.000"
    }
]

if __name__ == "__main__":
    output_file = "demo_executive_summary_report.html"
    
    print("Generating demo report with plugin executive summaries...")
    print(f"Output file: {output_file}")
    print()
    
    # Generate the report
    generate_html_report(demo_plugin_results, output_file, target="demo.example.com")
    
    print()
    print("✅ Demo report generated successfully!")
    print()
    print("The executive summary section now includes:")
    print("  1. Plugin Findings - Executive summaries from each plugin")
    print("  2. Potential Issues - The original issue-based summary")
    print()
    print(f"Open the report in your browser: file://{os.path.abspath(output_file)}")
