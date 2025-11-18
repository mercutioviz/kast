import os
from kast.report_builder import generate_html_report


def test_plugin_executive_summaries_in_report(tmp_path):
    """Test that plugin executive summaries are collected and displayed in the report."""
    
    # Prepare fake plugin results with executive summaries
    plugin_results = [
        {
            "plugin-name": "wafw00f",
            "plugin-display-name": "Wafw00f",
            "plugin-description": "Detects and identifies Web Application Firewalls (WAFs)",
            "summary": "No WAF detected",
            "details": "No WAF detected.",
            "executive_summary": "No WAFs were detected.",
            "issues": ["No WAF Detected"]
        },
        {
            "plugin-name": "mozilla_observatory",
            "plugin-display-name": "Mozilla Observatory",
            "plugin-description": "Runs Mozilla Observatory to analyze web application security",
            "summary": "Grade: B, Score: 75, Tests Passed: 8, Tests Failed: 2",
            "details": "Observatory scan completed",
            "executive_summary": "-= Observatory grade and score summary =-\nGrade: B, Score: 75, Tests Passed: 8, Tests Failed: 2",
            "issues": ["csp-implemented-with-unsafe-inline"]
        },
        {
            "plugin-name": "katana",
            "plugin-display-name": "Katana",
            "plugin-description": "Site crawler and URL finder",
            "summary": "Detected 15 unique URL(s).",
            "details": "Detected 15 unique URL(s).",
            "executive_summary": "Detected 15 URLs.",
            "issues": []
        },
        {
            "plugin-name": "whatweb",
            "plugin-display-name": "WhatWeb",
            "plugin-description": "Identifies technologies used by a website",
            "summary": "Technologies detected",
            "details": "Various technologies found",
            "executive_summary": "",  # Empty executive summary - should not appear
            "issues": []
        }
    ]

    out_file = tmp_path / "test_executive_summary_report.html"
    
    # Generate the HTML report
    generate_html_report(plugin_results, str(out_file), target="example.com")

    # Read generated HTML
    html = out_file.read_text()
    
    # Check that the "Plugin Findings" section header exists
    assert "Plugin Findings" in html
    
    # Check that the "Potential Issues" section header exists
    assert "Potential Issues" in html
    
    # Verify that plugin executive summaries appear in the report
    assert "Wafw00f:" in html
    assert "No WAFs were detected." in html
    
    assert "Mozilla Observatory:" in html
    assert "Observatory grade and score summary" in html
    assert "Grade: B, Score: 75" in html
    
    assert "Katana:" in html
    assert "Detected 15 URLs." in html
    
    # Verify that WhatWeb is NOT in the executive summary section (empty summary)
    # We need to check the context - it should appear in detailed results but not in executive summary
    # Count occurrences - should appear once in detailed section, not in executive summary
    whatweb_exec_summary_section = html.split("Potential Issues")[0]  # Get just the executive summary section
    assert "WhatWeb:" not in whatweb_exec_summary_section
    
    print("✓ All executive summary checks passed!")
    print(f"Report saved to: {out_file}")


def test_report_without_executive_summaries(tmp_path):
    """Test that report works correctly when no plugins have executive summaries."""
    
    plugin_results = [
        {
            "plugin-name": "test_plugin",
            "plugin-display-name": "Test Plugin",
            "summary": "Test summary",
            "details": "Test details",
            "issues": []
        }
    ]

    out_file = tmp_path / "test_no_exec_summary_report.html"
    
    # Generate the HTML report
    generate_html_report(plugin_results, str(out_file), target="example.com")

    # Read generated HTML
    html = out_file.read_text()
    
    # When no plugins have executive summaries, the "Plugin Findings" section should not appear
    assert "Plugin Findings" not in html
    
    # But "Potential Issues" should still exist (from the main executive summary)
    assert "Potential Issues" in html
    
    print("✓ Report without executive summaries works correctly!")


if __name__ == "__main__":
    import tempfile
    import shutil
    
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    
    try:
        from pathlib import Path
        tmp_path = Path(temp_dir)
        
        print("Running test_plugin_executive_summaries_in_report...")
        test_plugin_executive_summaries_in_report(tmp_path)
        print()
        
        print("Running test_report_without_executive_summaries...")
        test_report_without_executive_summaries(tmp_path)
        print()
        
        print("✅ All tests passed!")
    finally:
        # Clean up
        shutil.rmtree(temp_dir)
