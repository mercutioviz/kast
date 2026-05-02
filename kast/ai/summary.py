"""High-level AI summary orchestrator.

Pulls the relevant fields out of ``collect_report_data``'s output, renders
the prompt template, calls the adapter with the structured-output schema,
parses and validates the response, and returns the summary dict.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from jinja2 import Template

from kast.ai.base import AIAdapter, AIGenerationError
from kast.ai.prompts import load_prompt


logger = logging.getLogger(__name__)


EXEC_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "maxLength": 240},
        "narrative": {"type": "string"},
        "key_findings": {"type": "array", "items": {"type": "string"}},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "narrative"],
    "additionalProperties": False,
}


TOP_ISSUES_LIMIT = 10


def generate_ai_summary(
    adapter: AIAdapter,
    report_data: dict,
    prompt_name: str = "exec_summary_v1",
) -> dict:
    """Generate a structured AI executive summary.

    Returns a dict with ``headline / narrative / key_findings /
    recommended_actions / _meta``. Raises ``AIGenerationError`` on any
    failure (the caller is expected to catch and convert to ``ai_error``).
    """
    system, user_template, prompt_meta = load_prompt(prompt_name)

    context = _build_context(report_data)
    user_prompt = Template(user_template).render(**context)

    response = adapter.generate(
        prompt=user_prompt,
        system=system,
        response_schema=EXEC_SUMMARY_SCHEMA,
        max_tokens=int(prompt_meta.get("default_max_tokens", 2000)),
        temperature=float(prompt_meta.get("default_temperature", 0.3)),
    )

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise AIGenerationError(f"AI response was not valid JSON: {e}") from e

    _validate_schema(parsed)

    parsed["_meta"] = {
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "model": response.model,
        "latency_ms": response.latency_ms,
        "prompt_version": prompt_meta.get("version"),
        "prompt_name": prompt_name,
    }
    return parsed


def _build_context(report_data: dict) -> dict:
    scan_meta = report_data.get("scan_metadata") or {}
    all_issues = report_data.get("all_issues") or []
    plugin_summaries = report_data.get("plugin_executive_summaries") or []
    return {
        "target": report_data.get("target") or "(unknown)",
        "total_issues": scan_meta.get("total_issues", len(all_issues)),
        "severity_counts": scan_meta.get("severity_counts") or {},
        "top_issues": [
            {
                "id": i.get("id"),
                "display_name": i.get("display_name"),
                "severity": i.get("severity"),
                "category": i.get("category"),
                "reported_by": i.get("reported_by"),
                "description": (i.get("description") or "")[:400],
            }
            for i in all_issues[:TOP_ISSUES_LIMIT]
        ],
        "plugin_summaries": [
            {
                "plugin_name": s.get("plugin_name") or s.get("tool_name"),
                "summary": s.get("summary"),
            }
            for s in plugin_summaries
        ],
        "waf_stats": scan_meta.get("waf_statistics") or {},
    }


def _validate_schema(parsed: Any) -> None:
    """Lightweight validation; raises AIGenerationError on shape mismatch."""
    if not isinstance(parsed, dict):
        raise AIGenerationError(f"AI response was not a JSON object: {type(parsed).__name__}")
    for key in ("headline", "narrative"):
        if key not in parsed or not isinstance(parsed[key], str) or not parsed[key].strip():
            raise AIGenerationError(f"AI response missing required field '{key}'")
    for key in ("key_findings", "recommended_actions"):
        if key in parsed and not isinstance(parsed[key], list):
            raise AIGenerationError(f"AI response field '{key}' must be a list")
