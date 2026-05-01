"""HTML report renderer.

Consumes the dict returned by ``collect_report_data`` and produces an
HTML report alongside the supporting CSS and (optional) custom logo.
Format-specific concerns: CSS file copied next to the report, logo
referenced by filename, executive-summary list items get anchor links
to per-tool detail sections, full JSON results passed through as-is
(template can use ``<details>`` for collapsibility).
"""

from __future__ import annotations

import logging
import os
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kast.report.data import collect_report_data
from kast.report.helpers import (
    format_multiline_text,
    format_multiline_text_as_list,
    write_missing_issues_report,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "templates"
)
_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def _format_for_html(report_data):
    """Apply HTML-specific text formatting to the shared report data."""
    plugin_summaries = [
        {
            "plugin_name": s["plugin_name"],
            "tool_name": s["tool_name"],
            "summary": format_multiline_text_as_list(s["summary"], s["tool_name"]),
        }
        for s in report_data["plugin_executive_summaries"]
    ]

    detailed_results = {
        tool_name: {
            **detail,
            "summary": format_multiline_text(detail["summary"]),
            "details": format_multiline_text(detail["details"]),
            "report": format_multiline_text(detail["report"]),
        }
        for tool_name, detail in report_data["detailed_results"].items()
    }

    executive_summary = format_multiline_text_as_list(
        report_data["executive_summary_text"]
    )

    return plugin_summaries, detailed_results, executive_summary


def _copy_css_to_output(output_dir):
    """Copy ``kast_style.css`` next to the rendered HTML so the report is portable."""
    css_src = os.path.join(TEMPLATE_DIR, "kast_style.css")
    css_dst = os.path.join(output_dir, "kast_style.css")
    try:
        if os.path.isfile(css_src):
            shutil.copyfile(css_src, css_dst)
    except Exception:
        # Don't fail the whole report generation for CSS copy issues.
        pass


def _copy_logo_to_output(logo_path, output_dir):
    """Copy a custom logo into the output dir; return its filename or None."""
    if not (logo_path and os.path.isfile(logo_path)):
        return None
    try:
        logo_filename = os.path.basename(logo_path)
        shutil.copyfile(logo_path, os.path.join(output_dir, logo_filename))
        logger.info(f"Custom logo copied to {output_dir}/{logo_filename}")
        return logo_filename
    except Exception as e:
        logger.warning(f"Failed to copy custom logo: {e}. Using default logo.")
        return None


def render_html(report_data, output_path, logo_path=None):
    """Render the HTML report from already-collected report data."""
    template = _env.get_template("report_template.html")
    plugin_summaries, detailed_results, executive_summary = _format_for_html(report_data)

    output_dir = os.path.dirname(output_path) or os.getcwd()
    _copy_css_to_output(output_dir)
    logo_filename = _copy_logo_to_output(logo_path, output_dir)

    html_content = template.render(
        executive_summary=executive_summary,
        plugin_executive_summaries=plugin_summaries,
        issues=report_data["all_issues"],
        detailed_results=detailed_results,
        target=report_data["target"],
        scan_metadata=report_data["scan_metadata"],
        custom_logo=logo_filename,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"HTML report saved to {output_path}")

    if report_data["missing_issues"]:
        write_missing_issues_report(
            report_data["missing_issues"], output_dir, report_data["target"]
        )


def generate_html_report(
    plugin_results, output_path="kast_report.html", target=None, logo_path=None
):
    """One-shot entrypoint: collect data then render HTML.

    Preserved as the public surface of ``kast.report_builder`` so callers
    that import ``generate_html_report`` continue to work unchanged.
    """
    data = collect_report_data(plugin_results, target)
    render_html(data, output_path, logo_path)
