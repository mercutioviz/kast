"""Report data collector — shared between HTML and PDF renderers.

The v2 ``report_builder.py`` had two ~99% identical functions
(``generate_html_report`` and ``generate_pdf_report``) that each
performed plugin iteration, issue resolution, severity sort,
severity counting, WAF statistics, and missing-issue tracking before
diverging on format-specific concerns. Phase A7 lifts that shared
work here, behind a single ``collect_report_data`` entrypoint.

Renderers consume the dict this returns and apply only the
format-specific differences (HTML copies CSS / references logo by
filename / supports collapsible details; PDF embeds logo as base64 /
pre-renders JSON / has no JS).
"""

from __future__ import annotations

import logging
from datetime import datetime

from kast.core.severity import Severity, severity_sort_key
from kast.report.helpers import (
    generate_registry_template,
    infer_issue_metadata,
)
from kast.report_templates import (
    generate_executive_summary,
    get_category,
    get_issue_metadata,
    get_severity,
    get_talking_point,
)

logger = logging.getLogger(__name__)


# -- internal helpers --------------------------------------------------------


def _normalize_plugin_identity(plugin):
    """Pull (tool_name, reported_by, display_name, purpose) from a plugin result.

    The kebab-case keys (``plugin-name``, ``plugin-display-name``, etc.) are
    part of the kast↔kast-web contract — see ``docs/web-integration.md``.
    """
    tool_name = (
        plugin.get("plugin-name")
        or plugin.get("tool")
        or plugin.get("name", "Unknown Tool")
    )
    reported_by = (
        plugin.get("plugin-display-name")
        or plugin.get("display_name")
        or plugin.get("plugin-description")
        or tool_name
    )
    display_name = (
        plugin.get("plugin-display-name")
        or plugin.get("display_name")
        or plugin.get("plugin-description")
        or tool_name
    )
    purpose = plugin.get("plugin-description") or plugin.get("description") or ""
    return tool_name, reported_by, display_name, purpose


def _track_missing_issue(issue_id, tool_name, reported_by, issue_dict, missing_issues):
    """Side-effect: record an unregistered issue ID with inferred metadata."""
    if issue_id not in missing_issues:
        inferred = infer_issue_metadata(
            issue_id, tool_name, issue_dict.get("description", "")
        )
        missing_issues[issue_id] = {
            "plugin_name": tool_name,
            "plugin_display_name": reported_by,
            "occurrence_count": 1,
            "first_seen": datetime.now().isoformat(),
            "descriptions": {issue_dict.get("description", issue_id)},
            "suggested_metadata": inferred,
            "registry_template": generate_registry_template(issue_id, inferred),
        }
    else:
        missing_issues[issue_id]["occurrence_count"] += 1
        desc = issue_dict.get("description", issue_id)
        if desc:
            missing_issues[issue_id]["descriptions"].add(desc)


def _resolve_issue(issue, tool_name, reported_by, missing_issues):
    """Convert a string-or-dict issue into a structured record.

    Side effect: populates ``missing_issues`` for IDs not in the registry.
    """
    if isinstance(issue, str):
        issue_dict = {"id": issue, "description": issue}
    else:
        issue_dict = issue

    issue_id = issue_dict.get("id")
    if isinstance(issue_id, str):
        issue_id = issue_id.strip()

    metadata = get_issue_metadata(issue_id) if issue_id else None
    if metadata:
        display_name = metadata.get("display_name")
        remediation = get_talking_point(issue_id)
        severity = get_severity(issue_id)  # canonical via Severity enum
        category = get_category(issue_id)
    else:
        display_name = issue_id
        remediation = "No specific remediation available"
        severity = Severity.UNKNOWN.value
        category = "Uncategorized"
        if issue_id:
            logger.warning(f"Issue ID '{issue_id}' not found in issue registry")
            _track_missing_issue(
                issue_id, tool_name, reported_by, issue_dict, missing_issues
            )

    return {
        "id": issue_id,
        "display_name": display_name,
        "reported_by": reported_by,
        "reported_by_tool": tool_name,
        "description": issue_dict.get("description", ""),
        "remediation": remediation,
        "severity": severity,
        "category": category,
    }


# -- public surface ----------------------------------------------------------


def calculate_waf_statistics(all_issues):
    """Statistics about WAF-addressable issues for the report header."""
    total = len(all_issues)
    if total == 0:
        return {
            "total_issues": 0,
            "waf_addressable_count": 0,
            "waf_addressable_percentage": 0,
            "non_waf_count": 0,
            "high_severity_waf": 0,
            "medium_severity_waf": 0,
            "low_severity_waf": 0,
        }

    waf_addressable = 0
    high_severity_waf = 0
    medium_severity_waf = 0
    low_severity_waf = 0

    for issue in all_issues:
        issue_id = issue.get("id")
        if not issue_id:
            continue
        metadata = get_issue_metadata(issue_id)
        if not metadata or not metadata.get("waf_addressable", False):
            continue
        waf_addressable += 1
        severity = Severity.from_registry(issue.get("severity", Severity.UNKNOWN.value))
        if severity is Severity.HIGH:
            high_severity_waf += 1
        elif severity is Severity.MEDIUM:
            medium_severity_waf += 1
        elif severity is Severity.LOW:
            low_severity_waf += 1

    return {
        "total_issues": total,
        "waf_addressable_count": waf_addressable,
        "waf_addressable_percentage": round(waf_addressable / total * 100, 1),
        "non_waf_count": total - waf_addressable,
        "high_severity_waf": high_severity_waf,
        "medium_severity_waf": medium_severity_waf,
        "low_severity_waf": low_severity_waf,
    }


def collect_report_data(plugin_results, target=None, ai_summary=None, ai_error=None):
    """Aggregate plugin results into a single dict consumed by both renderers.

    Returns a dict with keys:

    - ``target`` — passed through
    - ``all_issues`` — list of issue records, sorted by canonical severity
      (highest first); each has id/display_name/reported_by/reported_by_tool/
      description/remediation/severity/category
    - ``detailed_results`` — dict mapping ``tool_name`` → per-plugin detail
      with **raw** text fields (renderers format them; HTML and PDF need
      different escapes / structure)
    - ``plugin_executive_summaries`` — list of {plugin_name, tool_name,
      summary} with raw ``summary`` (renderer formats)
    - ``missing_issues`` — dict for ``write_missing_issues_report``
    - ``executive_summary_text`` — raw output of ``generate_executive_summary``
      (renderer wraps in ``<ul>`` etc.)
    - ``scan_metadata`` — dict with ``scan_date``, ``total_issues``,
      ``total_plugins``, ``severity_counts`` (canonical "Informational" key,
      not "Info" — see audit § 5a.12), and ``waf_statistics``
    - ``ai_summary`` — structured dict from ``kast.ai.summary``
      (``headline / narrative / key_findings / recommended_actions / _meta``)
      or ``None``. Renderers prefer this over ``executive_summary_text``.
    - ``ai_error`` — string explaining why AI failed (or ``None``).
      Renderers surface as a banner alongside the deterministic summary.
    """
    all_issues = []
    detailed_results = {}
    plugin_executive_summaries = []
    missing_issues = {}

    for plugin in plugin_results:
        tool_name, reported_by, display_name, purpose = _normalize_plugin_identity(plugin)

        exec_summary = plugin.get("executive_summary", "")
        if exec_summary:
            plugin_executive_summaries.append(
                {
                    "plugin_name": display_name,
                    "tool_name": tool_name,
                    "summary": exec_summary,  # raw — renderer formats
                }
            )

        # Per-plugin details with raw text fields (renderers format).
        # ``custom_html_pdf`` is preserved here so the PDF renderer can
        # prefer it over ``custom_html`` without re-fetching from plugin.
        detailed_results[tool_name] = {
            "display_name": display_name,
            "purpose": purpose,
            "website_url": plugin.get("plugin-website-url"),
            "summary": plugin.get("summary", ""),
            "details": plugin.get("details", ""),
            "report": plugin.get("report", ""),
            "timestamp": plugin.get("timestamp"),
            "disposition": (
                plugin.get("findings", {}).get("disposition")
                or plugin.get("disposition")
            ),
            "results": (
                plugin.get("findings", {}).get("results") or plugin.get("results")
            ),
            "findings": plugin.get("findings"),
            "custom_html": plugin.get("custom_html", ""),
            "custom_html_pdf": plugin.get("custom_html_pdf", ""),
            "results_message": plugin.get("results_message"),
        }

        for issue in plugin.get("issues", []):
            all_issues.append(
                _resolve_issue(issue, tool_name, reported_by, missing_issues)
            )

    # Sort issues by canonical severity (highest first). Both renderers see
    # the same ordering — A6's severity_sort_key handles legacy "Info" too.
    all_issues.sort(
        key=lambda x: severity_sort_key(x.get("severity", Severity.UNKNOWN.value))
    )

    # Severity counts keyed by canonical Severity values.
    severity_counts = {s.value: 0 for s in Severity}
    for issue in all_issues:
        sev = Severity.from_registry(issue.get("severity")).value
        severity_counts[sev] += 1

    waf_stats = calculate_waf_statistics(all_issues)

    scan_metadata = {
        "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_issues": len(all_issues),
        "total_plugins": len(plugin_results),
        "severity_counts": severity_counts,
        "waf_statistics": waf_stats,
    }

    executive_summary_text = generate_executive_summary(all_issues)

    return {
        "target": target,
        "all_issues": all_issues,
        "detailed_results": detailed_results,
        "plugin_executive_summaries": plugin_executive_summaries,
        "missing_issues": missing_issues,
        "executive_summary_text": executive_summary_text,
        "scan_metadata": scan_metadata,
        "ai_summary": ai_summary,
        "ai_error": ai_error,
    }
