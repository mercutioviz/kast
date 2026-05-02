"""PDF report renderer (WeasyPrint-backed).

Consumes the dict returned by ``collect_report_data`` and produces a
PDF. Format-specific concerns: logo embedded as base64 (so the PDF is
self-contained), JSON results pre-rendered as nested ``<div>``\\s
(WeasyPrint can't run ``<details>``), executive-summary list items
omit anchor links, custom plugin HTML uses ``custom_html_pdf`` if the
plugin provided a PDF-specific variant.
"""

from __future__ import annotations

import json
import logging
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kast.report.data import collect_report_data
from kast.report.helpers import (
    format_json_for_pdf,
    format_multiline_text,
    format_multiline_text_as_list,
    image_to_base64,
    write_missing_issues_report,
)

# Quiet the noisy PDF stack so kast logs stay readable.
for _name in (
    "weasyprint",
    "PIL",
    "fontTools",
    "fontTools.subset",
    "fontTools.ttLib",
    "fontTools.ttLib.ttFont",
):
    logging.getLogger(_name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "templates"
)
ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets"
)
DEFAULT_LOGO = os.path.join(ASSETS_DIR, "kast-logo.png")

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def _resolve_logo_base64(logo_path):
    """Return a base64 data-URI for the chosen logo (custom or default)."""
    if logo_path and os.path.isfile(logo_path):
        encoded = image_to_base64(logo_path)
        if encoded:
            return encoded
        logger.warning(f"Failed to encode custom logo: {logo_path}. Using default.")
    return image_to_base64(DEFAULT_LOGO)


def _format_for_pdf(report_data):
    """Apply PDF-specific text formatting to the shared report data."""
    plugin_summaries = [
        {
            "plugin_name": s["plugin_name"],
            "tool_name": s["tool_name"],
            # PDF intentionally omits anchor links — preserves v2 behavior.
            "summary": format_multiline_text_as_list(s["summary"]),
        }
        for s in report_data["plugin_executive_summaries"]
    ]

    detailed_results = {}
    for tool_name, detail in report_data["detailed_results"].items():
        results_data = detail.get("results")
        results_html = format_json_for_pdf(results_data) if results_data else ""

        # Prefer custom_html_pdf if the plugin provides one, else fall back.
        custom_html_for_pdf = detail.get("custom_html_pdf") or detail.get("custom_html", "")

        detailed_results[tool_name] = {
            **detail,
            "summary": format_multiline_text(detail["summary"]),
            "details": format_multiline_text(detail["details"]),
            "report": format_multiline_text(detail["report"]),
            "results": None,  # PDF uses pre-rendered results_html
            "results_html": results_html,
            "findings_json": (
                json.dumps(detail.get("findings"), indent=2)
                if detail.get("findings")
                else ""
            ),
            "custom_html": custom_html_for_pdf,
        }

    executive_summary = format_multiline_text_as_list(
        report_data["executive_summary_text"]
    )
    return plugin_summaries, detailed_results, executive_summary


def render_pdf(report_data, output_path, logo_path=None):
    """Render the PDF report from already-collected report data."""
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
    except ImportError:
        logger.error(
            "WeasyPrint is not installed. Install it with: pip install weasyprint"
        )
        return

    template = _env.get_template("report_template_pdf.html")
    plugin_summaries, detailed_results, executive_summary = _format_for_pdf(report_data)
    logo_base64 = _resolve_logo_base64(logo_path)

    html_content = template.render(
        executive_summary=executive_summary,
        plugin_executive_summaries=plugin_summaries,
        issues=report_data["all_issues"],
        detailed_results=detailed_results,
        target=report_data["target"],
        scan_metadata=report_data["scan_metadata"],
        logo_base64=logo_base64,
        ai_summary=report_data.get("ai_summary"),
        ai_error=report_data.get("ai_error"),
    )

    base_url = f"file://{os.path.abspath(TEMPLATE_DIR)}/"
    font_config = FontConfiguration()
    css_path = os.path.join(TEMPLATE_DIR, "kast_style_pdf.css")
    css = CSS(filename=css_path, font_config=font_config)

    try:
        html_obj = HTML(string=html_content, encoding="utf-8", base_url=base_url)
        html_obj.write_pdf(output_path, stylesheets=[css], font_config=font_config)
        logger.info(
            f"PDF report saved to {output_path} "
            f"({len(report_data['all_issues'])} issues)"
        )

        output_dir = os.path.dirname(output_path) or os.getcwd()
        if report_data["missing_issues"]:
            write_missing_issues_report(
                report_data["missing_issues"], output_dir, report_data["target"]
            )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        logger.error(
            "If you see font-related errors, ensure these packages are installed:"
        )
        logger.error("  - fonts-noto-core, fonts-noto-color-emoji, fonts-dejavu")
        raise


def generate_pdf_report(
    plugin_results, output_path="kast_report.pdf", target=None, logo_path=None,
    ai_summary=None, ai_error=None,
):
    """One-shot entrypoint: collect data then render PDF.

    Preserved as the public surface of ``kast.report_builder``.
    """
    data = collect_report_data(
        plugin_results, target, ai_summary=ai_summary, ai_error=ai_error,
    )
    render_pdf(data, output_path, logo_path)
