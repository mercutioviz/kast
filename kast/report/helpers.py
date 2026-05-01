"""Formatting and metadata helpers for the report pipeline.

Module home for the small functions that were sprinkled through the v2
``report_builder.py``. Both renderers and the data collector import from
here. Kept distinct from ``kast.report.data`` (which orchestrates) and
the renderers (which produce final artifacts) so the helpers can be
unit-tested in isolation.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime

from kast.core.atomic import write_json_atomic

logger = logging.getLogger(__name__)


# -- issue-registry helpers --------------------------------------------------


def infer_issue_metadata(issue_id, plugin_name, description=""):
    """Infer registry-shaped metadata for an issue ID not in the registry.

    Used to populate ``missing_issue_ids.json`` so an operator can promote
    inferred entries into the registry rather than re-typing them.
    """
    issue_lower = issue_id.lower() if issue_id else ""

    category = "Uncategorized"
    if plugin_name.lower() in ["testssl", "testssl.sh"]:
        category = "Encryption"
    elif plugin_name.lower() in ["wafw00f", "waf"]:
        category = "Security Misconfiguration"
    elif plugin_name.lower() in ["observatory", "mozilla observatory"]:
        category = "Security Headers"
    elif plugin_name.lower() in ["script_detection", "script detection"]:
        category = "Third-Party Risk"
    elif "xss" in issue_lower or "injection" in issue_lower:
        category = "Injection"
    elif "header" in issue_lower or "hsts" in issue_lower or "csp" in issue_lower:
        category = "Security Headers"
    elif (
        "ssl" in issue_lower
        or "tls" in issue_lower
        or "cipher" in issue_lower
        or "certificate" in issue_lower
    ):
        category = "Encryption"

    severity = "Medium"
    if any(w in issue_lower for w in ["critical", "severe", "rce", "remote code"]):
        severity = "High"
    elif any(
        w in issue_lower
        for w in ["xss", "injection", "sql", "command", "broken", "vulnerable"]
    ):
        severity = "High"
    elif any(
        w in issue_lower
        for w in ["export", "weak", "insecure", "deprecated", "md5", "sha1", "rc4"]
    ):
        severity = "Medium"
    elif any(w in issue_lower for w in ["info", "information", "disclosure", "detected"]):
        severity = "Low"
    elif any(w in issue_lower for w in ["missing", "absent", "not found"]):
        severity = "Low"

    waf_addressable = False
    if category in ["Security Headers", "Injection"]:
        waf_addressable = True
    elif any(w in issue_lower for w in ["xss", "injection", "sql"]):
        waf_addressable = True

    display_name = issue_id.replace("_", " ").replace("-", " ").title()

    remediation = f"Review and address the {issue_id} issue"
    if "cipher" in issue_lower or "tls" in issue_lower or "ssl" in issue_lower:
        remediation = (
            f"Disable weak cipher suite or protocol: {issue_id}. "
            "Update server TLS/SSL configuration to use only strong, "
            "modern cipher suites."
        )
    elif "header" in issue_lower:
        remediation = (
            f"Implement the {display_name} security header in server configuration."
        )
    elif category == "Third-Party Risk":
        remediation = (
            f"Review third-party script {issue_id} for security implications "
            "and consider alternatives if necessary."
        )

    return {
        "display_name": display_name,
        "category": category,
        "severity": severity,
        "waf_addressable": waf_addressable,
        "remediation": remediation,
    }


def generate_registry_template(issue_id, metadata):
    """Wrap inferred metadata in a registry-ready entry shape."""
    return {
        issue_id: {
            "display_name": metadata["display_name"],
            "category": metadata["category"],
            "severity": metadata["severity"],
            "waf_addressable": metadata["waf_addressable"],
            "remediation": metadata["remediation"],
        }
    }


def write_missing_issues_report(missing_issues, output_dir, target=None):
    """Write ``missing_issue_ids.json`` documenting issues absent from the registry."""
    if not missing_issues:
        return

    report = {
        "scan_metadata": {
            "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "target": target or "Unknown",
            "total_missing_issues": len(missing_issues),
            "total_occurrences": sum(
                item["occurrence_count"] for item in missing_issues.values()
            ),
        },
        "missing_issues": [],
    }

    for issue_id, info in sorted(missing_issues.items()):
        report["missing_issues"].append(
            {
                "issue_id": issue_id,
                "plugin_name": info["plugin_name"],
                "plugin_display_name": info["plugin_display_name"],
                "occurrence_count": info["occurrence_count"],
                "first_seen": info["first_seen"],
                "descriptions": list(info["descriptions"]),
                "suggested_metadata": info["suggested_metadata"],
                "registry_template": info["registry_template"],
            }
        )

    output_path = os.path.join(output_dir, "missing_issue_ids.json")
    try:
        write_json_atomic(output_path, report)
        logger.info(f"Missing issue IDs documented in {output_path}")
    except Exception as e:
        logger.error(f"Failed to write missing issues report: {e}")


# -- text formatting helpers -------------------------------------------------


def add_word_break_opportunities(text):
    """Insert ``<wbr>`` after URL-like delimiters in long strings.

    NOTE: A9 will replace this with a CSS rule (``overflow-wrap: anywhere;
    word-break: break-word;``) on URL cells in ``kast_style_pdf.css``.
    Tracking the existing call sites here so the function can be deleted
    in one go.
    """
    if not text or len(text) < 80:
        return text

    result = []
    inside_tag = False
    for char in text:
        if char == "<":
            inside_tag = True
            result.append(char)
        elif char == ">":
            inside_tag = False
            result.append(char)
        elif not inside_tag and char in [
            "/", "?", "&", "=", "-", "_", ".", ":", ";", ",",
        ]:
            result.append(char)
            result.append("<wbr>")
        else:
            result.append(char)
    return "".join(result)


def format_multiline_text(text):
    """Convert newline-separated text or a list into ``<p>`` paragraphs."""
    if not text:
        return ""

    paragraphs = text if isinstance(text, list) else str(text).split("\n")

    out = []
    for p in paragraphs:
        if str(p).strip():
            out.append(
                f'<p class="report-paragraph">{add_word_break_opportunities(str(p))}</p>'
            )
    return "\n".join(out)


def generate_tool_anchor_id(tool_name):
    """Anchor ID for a tool section, matching template convention."""
    return tool_name.lower().replace(" ", "-").replace(".", "-")


def format_multiline_text_as_list(text, tool_name=None):
    """Convert text/list into a ``<ul>``. Optional ``tool_name`` adds anchor links."""
    if not text:
        return ""

    items = text if isinstance(text, list) else str(text).split("\n")
    items = [item for item in items if str(item).strip()]
    if not items:
        return ""

    if tool_name:
        anchor = generate_tool_anchor_id(tool_name)
        list_items = "\n".join(
            f'<li><a href="#tool-{anchor}" '
            f'style="color: inherit; text-decoration: underline; cursor: pointer;">'
            f"{item}</a></li>"
            for item in items
        )
    else:
        list_items = "\n".join(f"<li>{item}</li>" for item in items)

    return f'<ul class="executive-summary-list">\n{list_items}\n</ul>'


# -- image / JSON helpers ----------------------------------------------------


def image_to_base64(image_path):
    """Return a ``data:`` URI for ``image_path``, or None if it doesn't exist."""
    try:
        if not os.path.exists(image_path):
            return None
        with open(image_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(image_path)[1][1:].lower()
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "svg": "image/svg+xml",
        }.get(ext, "image/png")
        return f"data:{mime};base64,{data}"
    except Exception as e:
        logger.warning(f"Failed to encode image {image_path}: {e}")
        return None


def format_json_for_pdf(data, max_depth=3, current_depth=0):
    """Recursively render JSON as nested ``<div>`` for PDF (no <details>)."""
    if data is None:
        return '<span class="json-null">null</span>'

    if current_depth >= max_depth:
        return '<span class="json-truncated">[... truncated ...]</span>'

    try:
        if isinstance(data, dict):
            if not data:
                return '<span class="json-empty">{}</span>'
            items = []
            for key, value in data.items():
                formatted = format_json_for_pdf(value, max_depth, current_depth + 1)
                items.append(
                    f'<div class="json-item"><span class="json-key">"{key}":</span> {formatted}</div>'
                )
            return (
                '<div class="json-object">{<div class="json-contents">'
                + "".join(items)
                + "</div>}</div>"
            )
        elif isinstance(data, list):
            if not data:
                return '<span class="json-empty">[]</span>'
            items = [
                f'<div class="json-item">{format_json_for_pdf(item, max_depth, current_depth + 1)}</div>'
                for item in data
            ]
            return (
                '<div class="json-array">[<div class="json-contents">'
                + "".join(items)
                + "</div>]</div>"
            )
        elif isinstance(data, str):
            escaped = data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if len(escaped) > 80:
                # NOTE: also a target for A9 (CSS-based wrap rather than <wbr>).
                for char in ["/", "?", "&", "=", "-", "_", ".", ":", ";", ","]:
                    escaped = escaped.replace(char, char + "<wbr>")
            if len(escaped) > 500:
                escaped = escaped[:500] + "..."
            return f'<span class="json-string">"{escaped}"</span>'
        elif isinstance(data, bool):
            return f'<span class="json-boolean">{str(data).lower()}</span>'
        elif isinstance(data, (int, float)):
            return f'<span class="json-number">{data}</span>'
        else:
            return f'<span class="json-value">{str(data)}</span>'
    except Exception as e:
        logger.warning(f"Error formatting JSON for PDF: {e}")
        return f'<pre class="json-display">{json.dumps(data, indent=2)}</pre>'
