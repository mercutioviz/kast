"""Report generation pipeline.

Phase A7 split the v2 ``report_builder.py`` — which had two ~99% identical
functions for HTML and PDF — into a shared data collector plus thin
format-specific renderers:

- ``collect_report_data(plugin_results, target)`` returns the structured
  data both renderers consume.
- ``render_html(data, output_path, logo_path=None)`` renders HTML.
- ``render_pdf(data, output_path, logo_path=None)`` renders PDF.

The backward-compat entrypoints ``generate_html_report`` and
``generate_pdf_report`` remain for callers that imported from
``kast.report_builder``; they collect data and render in one call.

Format-specific differences (PDF pre-renders JSON, embeds logo as base64,
uses different templates; HTML copies CSS to output dir, references logo
by filename) live in their respective renderers. Both consume the same
data structure.
"""

from kast.report.data import calculate_waf_statistics, collect_report_data
from kast.report.html import generate_html_report, render_html
from kast.report.pdf import generate_pdf_report, render_pdf

__all__ = [
    "collect_report_data",
    "calculate_waf_statistics",
    "render_html",
    "render_pdf",
    "generate_html_report",
    "generate_pdf_report",
]
