#!/usr/bin/env python3
"""
Test script to generate a sample PDF report with navigation features.
This script creates a PDF with multiple tools and issues to test all navigation links.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kast.report_builder import generate_pdf_report


def test_pdf_navigation():
    """Generate a sample PDF report to test navigation features."""
    
    # Create sample plugin results with multiple tools and issues
    plugin_results = [
        {
            "plugin-name": "TestSSL",
            "plugin-display-name": "TestSSL.sh",
            "plugin-description": "SSL/TLS security testing tool",
            "plugin-website-url": "https://testssl.sh",
            "timestamp": "2024-01-15 10:30:00",
            "summary": "Tested SSL/TLS configuration",
            "details": "Complete SSL/TLS analysis performed",
            "executive_summary": [
                "SSL certificate is valid",
                "TLS 1.2 and 1.3 supported",
                "Weak cipher suites detected"
            ],
            "disposition": "Issues Found",
            "issues": [
                "ssl-weak-cipher-suite",
                {"id": "ssl-certificate-expiring-soon", "description": "Certificate expires in 45 days"}
            ]
        },
        {
            "plugin-name": "WhatWeb",
            "plugin-display-name": "WhatWeb",
            "plugin-description": "Web technology fingerprinting tool",
            "plugin-website-url": "https://github.com/urbanadventurer/WhatWeb",
            "timestamp": "2024-01-15 10:32:00",
            "summary": "Identified web technologies",
            "details": "Technology stack analysis completed",
            "executive_summary": [
                "Apache web server version 2.4.41 detected",
                "PHP version 7.4.3 in use",
                "jQuery library found"
            ],
            "disposition": "Completed",
            "issues": [
                "server-version-disclosed",
                {"id": "Outdated Apache", "description": "Running Apache 2.4.41, current is 2.4.58"}
            ]
        },
        {
            "plugin-name": "Observatory",
            "plugin-display-name": "Mozilla Observatory",
            "plugin-description": "Security headers and best practices scanner",
            "plugin-website-url": "https://observatory.mozilla.org",
            "timestamp": "2024-01-15 10:35:00",
            "summary": "Security headers analysis",
            "details": "Checked for security headers and configurations",
            "executive_summary": [
                "Content-Security-Policy header present but weak",
                "HSTS not implemented",
                "X-Frame-Options missing"
            ],
            "disposition": "Issues Found",
            "issues": [
                "csp-implemented-with-unsafe-inline",
                "hsts-not-implemented",
                "x-frame-options-header-missing"
            ]
        },
        {
            "plugin-name": "Subfinder",
            "plugin-display-name": "Subfinder",
            "plugin-description": "Subdomain discovery tool",
            "plugin-website-url": "https://github.com/projectdiscovery/subfinder",
            "timestamp": "2024-01-15 10:38:00",
            "summary": "Discovered 15 subdomains",
            "details": "Found subdomains using passive techniques",
            "executive_summary": [
                "15 unique subdomains identified",
                "3 previously unknown subdomains found",
                "Some subdomains may be vulnerable"
            ],
            "disposition": "Completed",
            "issues": [
                {"id": "subdomain-takeover-risk", "description": "Subdomain points to non-existent resource"}
            ]
        },
        {
            "plugin-name": "Katana",
            "plugin-display-name": "Katana",
            "plugin-description": "Web crawling and spidering tool",
            "plugin-website-url": "https://github.com/projectdiscovery/katana",
            "timestamp": "2024-01-15 10:40:00",
            "summary": "Crawled 250 URLs",
            "details": "Performed comprehensive web crawling",
            "executive_summary": [
                "250 URLs discovered and analyzed",
                "45 JavaScript files found",
                "Exposed API endpoints detected"
            ],
            "disposition": "Completed",
            "issues": [
                {"id": "exposed-api-endpoint", "description": "/api/internal/users endpoint accessible"}
            ]
        }
    ]
    
    # Generate PDF report
    output_path = "test_navigation_report.pdf"
    target = "example.com"
    
    print(f"Generating PDF report with navigation features...")
    print(f"Target: {target}")
    print(f"Output: {output_path}")
    print(f"Tools: {len(plugin_results)}")
    
    try:
        generate_pdf_report(plugin_results, output_path, target=target)
        print("\n✓ PDF report generated successfully!")
        print(f"\nThe report includes:")
        print("  • Table of Contents with links to all major sections")
        print("  • Clickable severity boxes on the cover page")
        print("  • Executive Summary with 'View Details' links to tools")
        print("  • Issues section with 'View tool details' links")
        print("  • Tool sections with navigation headers (Back to TOC, Tool Index, Previous/Next)")
        print(f"\nOpen '{output_path}' to test the navigation links.")
        return True
    except Exception as e:
        print(f"\n✗ Error generating PDF: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_pdf_navigation()
    sys.exit(0 if success else 1)
