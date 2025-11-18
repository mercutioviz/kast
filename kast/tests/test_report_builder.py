import os
from kast.report_builder import generate_html_report


def test_generate_html_report_string_and_dict_issues(tmp_path):
    # Prepare fake plugin results: one plugin returns string issues and one returns dict issue
    plugin_results = [
        {
            "plugin-name": "observatory_test",
            "summary": "Observatory summary",
            "details": "Line1\nLine2",
            "report": "Report notes",
            "issues": [
                "csp-implemented-with-unsafe-inline",
                {"id": "Outdated Apache", "description": "Old Apache version detected"}
            ]
        }
    ]

    out_file = tmp_path / "test_report.html"
    # Generate the HTML report
    generate_html_report(plugin_results, str(out_file), target="example.com")

    # Read generated HTML and assert that registry display names appear
    html = out_file.read_text()
    assert "Content Security Policy with unsafe-inline" in html
    assert "Outdated Apache web server" in html
