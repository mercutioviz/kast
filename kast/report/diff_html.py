"""HTML renderer for scan comparisons.

Consumes the dict returned by ``kast.report.diff.compute_diff`` and
writes a single self-contained HTML file. Unlike the main report, the
CSS is inlined rather than copied alongside — a comparison is something
an SA emails to a prospect, so it has to survive being detached from its
directory.
"""

from __future__ import annotations

import logging
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kast import __version__
from kast.report.diff import build_headline

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_diff_html(diff, output_path, ai_narrative=None, ai_error=None):
    """Render a comparison dict to a standalone HTML file.

    ``ai_narrative`` is optional. The deterministic ``build_headline`` is
    always rendered, so an absent or failed narrative degrades to the same
    report the flag-free invocation produces plus a banner — the same
    failure mode as the main report's AI executive summary.
    """
    template = _env.get_template("diff_template.html")
    html_content = template.render(
        baseline=diff["baseline"],
        current=diff["current"],
        coverage=diff["coverage"],
        summary=diff["summary"],
        new_issues=diff["new_issues"],
        resolved_issues=diff["resolved_issues"],
        persisting_issues=diff["persisting_issues"],
        headline=build_headline(diff),
        ai_narrative=ai_narrative,
        ai_error=ai_error,
        kast_version=__version__,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"Comparison report saved to {output_path}")
