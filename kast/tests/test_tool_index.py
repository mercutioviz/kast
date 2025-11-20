#!/usr/bin/env python3
"""
Test script to verify the new tool index page in PDF reports
"""

import sys
import os

# Add kast to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'kast'))

from report_builder import generate_pdf_report

# Sample plugin results with multiple tools
sample_results = [
    {
        "plugin-name": "subfinder",
        "plugin-display-name": "Subfinder",
        "plugin-description": "Fast subdomain enumeration tool",
        "plugin-website-url": "https://github.com/projectdiscovery/subfinder",
        "timestamp": "2025-11-20 20:00:00",
        "executive_summary": [
            "Discovered 5 subdomains",
            "Found potential admin subdomain"
        ],
        "summary": "Subfinder discovered multiple subdomains for the target domain.",
        "details": "The scan identified several interesting subdomains including administrative interfaces.",
        "disposition": "Success",
        "issues": ["subdomain_enumeration_success"],
        "findings": {
            "disposition": "Success",
            "results": {
                "subdomains": [
                    "admin.example.com",
                    "api.example.com",
                    "dev.example.com",
                    "www.example.com",
                    "mail.example.com"
                ]
            }
        }
    },
    {
        "plugin-name": "whatweb",
        "plugin-display-name": "WhatWeb",
        "plugin-description": "Web technology fingerprinting tool",
        "plugin-website-url": "https://github.com/urbanadventurer/WhatWeb",
        "timestamp": "2025-11-20 20:01:00",
        "executive_summary": [
            "Detected Apache web server",
            "Running PHP version 7.4"
        ],
        "summary": "WhatWeb identified the web technologies in use.",
        "details": "The target is running Apache 2.4 with PHP 7.4 and appears to be using WordPress.",
        "disposition": "Success",
        "issues": ["outdated_php_version"],
        "findings": {
            "disposition": "Success",
            "results": {
                "technologies": [
                    {"name": "Apache", "version": "2.4"},
                    {"name": "PHP", "version": "7.4"},
                    {"name": "WordPress", "version": "5.8"}
                ]
            }
        }
    },
    {
        "plugin-name": "wafw00f",
        "plugin-display-name": "WAFW00F",
        "plugin-description": "Web Application Firewall detection tool",
        "plugin-website-url": "https://github.com/EnableSecurity/wafw00f",
        "timestamp": "2025-11-20 20:02:00",
        "executive_summary": [
            "No WAF detected"
        ],
        "summary": "WAFW00F did not detect any web application firewall.",
        "details": "The target does not appear to be protected by a WAF.",
        "disposition": "No WAF Detected",
        "issues": ["no_waf_detected"],
        "findings": {
            "disposition": "No WAF Detected",
            "results": None
        }
    },
    {
        "plugin-name": "testssl",
        "plugin-display-name": "testssl.sh",
        "plugin-description": "SSL/TLS security scanner",
        "plugin-website-url": "https://testssl.sh/",
        "timestamp": "2025-11-20 20:03:00",
        "executive_summary": [
            "TLS 1.2 and 1.3 supported",
            "Weak cipher suites detected"
        ],
        "summary": "testssl.sh performed comprehensive SSL/TLS testing.",
        "details": "The server supports modern TLS versions but includes some weak cipher suites.",
        "disposition": "Warning",
        "issues": ["weak_cipher_suites", "ssl_certificate_valid"],
        "findings": {
            "disposition": "Warning",
            "results": {
                "protocols": ["TLSv1.2", "TLSv1.3"],
                "certificate_valid": True,
                "weak_ciphers": ["TLS_RSA_WITH_3DES_EDE_CBC_SHA"]
            }
        }
    },
    {
        "plugin-name": "katana",
        "plugin-display-name": "Katana",
        "plugin-description": "Web crawling and spidering tool",
        "plugin-website-url": "https://github.com/projectdiscovery/katana",
        "timestamp": "2025-11-20 20:04:00",
        "executive_summary": [
            "Crawled 150 URLs",
            "Found 5 JavaScript files"
        ],
        "summary": "Katana crawled the target website and discovered various endpoints.",
        "details": "The crawler identified multiple pages, API endpoints, and static resources.",
        "disposition": "Success",
        "issues": [],
        "findings": {
            "disposition": "Success",
            "results": {
                "total_urls": 150,
                "javascript_files": 5,
                "forms_found": 8
            }
        }
    }
]

if __name__ == "__main__":
    print("Testing PDF generation with new tool index page...")
    print("=" * 60)
    
    try:
        # Generate PDF report
        output_path = "test_tool_index_report.pdf"
        generate_pdf_report(
            plugin_results=sample_results,
            output_path=output_path,
            target="example.com"
        )
        
        print("\n✓ PDF report generated successfully!")
        print(f"✓ Output file: {output_path}")
        print("\nThe report should now include:")
        print("  1. A 'Detailed Results by Tool' index page with clickable links")
        print("  2. Each tool listed with its name and description")
        print("  3. Clickable links that navigate to the respective tool's details")
        print("\nPlease open the PDF to verify the changes.")
        
    except Exception as e:
        print(f"\n✗ Error generating PDF: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
