"""Backward-compat shim for ``kast.report_builder``.

Phase A7 split the report pipeline into ``kast.report.{data,html,pdf,helpers}``.
This module re-exports the original public surface so callers that imported
from ``kast.report_builder`` continue to work without modification.

New code should import directly from ``kast.report``.
"""

# Public report-generation entrypoints (one-shot collect+render).
from kast.report import (
    calculate_waf_statistics,
    collect_report_data,
    generate_html_report,
    generate_pdf_report,
    render_html,
    render_pdf,
)

# Helpers that some callers (and tests) imported directly from report_builder.
from kast.report.helpers import (
    format_json_for_pdf,
    format_multiline_text,
    format_multiline_text_as_list,
    generate_registry_template,
    generate_tool_anchor_id,
    image_to_base64,
    infer_issue_metadata,
    write_missing_issues_report,
)

__all__ = [
    # Pipeline
    "collect_report_data",
    "render_html",
    "render_pdf",
    "generate_html_report",
    "generate_pdf_report",
    "calculate_waf_statistics",
    # Helpers
    "format_json_for_pdf",
    "format_multiline_text",
    "format_multiline_text_as_list",
    "generate_registry_template",
    "generate_tool_anchor_id",
    "image_to_base64",
    "infer_issue_metadata",
    "write_missing_issues_report",
]
