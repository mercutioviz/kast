import tempfile
import os
from kast.report_builder import generate_html_report


def run_test():
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

    with tempfile.TemporaryDirectory() as td:
        out_file = os.path.join(td, 'test_report.html')
        generate_html_report(plugin_results, out_file, target='example.com')
        html = open(out_file, 'r').read()
        assert 'Content Security Policy with unsafe-inline' in html, 'Missing CSP display name'
        assert 'Outdated Apache web server' in html, 'Missing Outdated Apache display name'
        print('Run successful: display names present in generated HTML')

if __name__ == '__main__':
    run_test()
