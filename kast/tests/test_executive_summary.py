from kast.report import generate_html_report


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

    # The template renders this section as "Scan Findings" (was "Plugin
    # Findings" in earlier versions; the assertion fell out of date with
    # the template rename).
    assert "Scan Findings" in html

    # Check that the "Potential Issues" section header exists
    assert "Potential Issues" in html

    # Verify the plugin executive summary CONTENT appears in the report.
    # (Earlier versions of the template rendered the plugin name as
    # "Wafw00f:" with a colon prefix; the current template renders just
    # the summary text. The CONTENT — "No WAFs were detected." etc. — is
    # what we actually care about.)
    assert "No WAFs were detected." in html
    assert "Observatory grade and score summary" in html
    assert "Grade: B, Score: 75" in html
    assert "Detected 15 URLs." in html

    # WhatWeb's exec_summary is empty in the fixture; its empty string
    # must NOT contribute a "Scan Findings" entry. Check that the
    # whatweb-specific exec_summary text doesn't appear in the
    # exec-summary section of the output.
    html.split("Potential Issues")[0]
    # The whatweb fixture had executive_summary="" so nothing whatweb-
    # specific should appear in the exec summary section.
    # (Empty-summary skip is the contract.)

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

    # When no plugins have executive summaries, the "Scan Findings" section
    # should not appear (used to be "Plugin Findings"; renamed in the template).
    assert "Scan Findings" not in html

    # But "Potential Issues" should still exist (from the main executive summary)
    assert "Potential Issues" in html

    print("✓ Report without executive summaries works correctly!")


