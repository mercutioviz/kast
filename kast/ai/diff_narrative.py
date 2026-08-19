"""AI narrative for a scan comparison.

Mirrors ``kast.ai.summary``: pull the relevant fields out of
``compute_diff``'s output, render the prompt, call the adapter with a
structured-output schema, validate, return the dict.

Two things are specific to this one. Coverage-gapped issues are filtered out
of the context entirely rather than passed with a flag — the model cannot
misreport a fix it was never shown, and the gap is surfaced separately as an
explicit caveat. And ``_validate_narrative`` rejects a response that claims a
completed comparison when a coverage gap exists, because "we fixed that"
said to a prospect about a plugin that simply did not re-run is the failure
mode this whole subsystem is built to avoid.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from jinja2 import Template

from kast.ai.base import AIAdapter, AIGenerationError
from kast.ai.prompts import load_prompt

logger = logging.getLogger(__name__)


DIFF_NARRATIVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "maxLength": 240},
        "narrative": {"type": "string"},
        "notable_changes": {"type": "array", "items": {"type": "string"}},
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "narrative"],
    "additionalProperties": False,
}


ISSUE_LIMIT = 15


def generate_diff_narrative(
    adapter: AIAdapter,
    diff: dict,
    prompt_name: str = "diff_narrative_v1",
) -> dict:
    """Generate a structured AI narrative for a scan comparison.

    Returns a dict with ``headline / narrative / notable_changes / caveats /
    _meta``. Raises ``AIGenerationError`` on any failure; the caller converts
    that to a banner and falls back to ``build_headline``.
    """
    system, user_template, prompt_meta = load_prompt(prompt_name)

    context = _build_context(diff)
    user_prompt = Template(user_template).render(**context)

    response = adapter.generate(
        prompt=user_prompt,
        system=system,
        response_schema=DIFF_NARRATIVE_SCHEMA,
        max_tokens=int(prompt_meta.get("default_max_tokens", 1500)),
        temperature=float(prompt_meta.get("default_temperature", 0.3)),
    )

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise AIGenerationError(f"AI response was not valid JSON: {e}") from e

    _validate_narrative(parsed, diff)

    parsed["_meta"] = {
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "model": response.model,
        "latency_ms": response.latency_ms,
        "prompt_version": prompt_meta.get("version"),
        "prompt_name": prompt_name,
    }
    return parsed


def _issue_context(issues, limit=ISSUE_LIMIT) -> list[dict]:
    """Trim to the fields the prompt renders, dropping coverage-gapped rows."""
    out = []
    for issue in issues:
        if issue.get("coverage_gap"):
            continue
        out.append({
            "display_name": issue.get("display_name") or issue.get("id"),
            "severity": issue.get("severity"),
            "category": issue.get("category"),
            "reported_by_tool": issue.get("reported_by_tool"),
            "baseline_severity": issue.get("baseline_severity"),
            "severity_changed": issue.get("severity_changed", False),
            "occurrence_delta": issue.get("occurrence_delta", 0),
        })
        if len(out) >= limit:
            break
    return out


def _build_context(diff: dict) -> dict:
    summary = diff.get("summary") or {}
    coverage = diff.get("coverage") or {}
    baseline = diff.get("baseline") or {}
    current = diff.get("current") or {}

    return {
        "target": current.get("target") or baseline.get("target") or "(unknown)",
        "baseline_target": baseline.get("target"),
        "current_target": current.get("target"),
        "target_match": summary.get("target_match", True),
        "baseline_date": (baseline.get("scan_date") or "")[:19].replace("T", " ") or "(unknown)",
        "current_date": (current.get("scan_date") or "")[:19].replace("T", " ") or "(unknown)",
        "summary": summary,
        "has_severity_movement": any((summary.get("severity_deltas") or {}).values()),
        "has_coverage_gap": summary.get("has_coverage_gap", False),
        "baseline_only_plugins": coverage.get("baseline_only") or [],
        "current_only_plugins": coverage.get("current_only") or [],
        "resolved": _issue_context(diff.get("resolved_issues") or []),
        "new": _issue_context(diff.get("new_issues") or []),
        "persisting": _issue_context(diff.get("persisting_issues") or []),
    }


def _validate_narrative(parsed: Any, diff: dict) -> None:
    """Shape validation, plus the coverage-gap guarantee.

    The prompt instructs the model to flag a partial comparison. This turns
    that instruction into an enforced postcondition: a coverage gap that
    reaches a prospect unstated is the report claiming more than it can
    prove.
    """
    if not isinstance(parsed, dict):
        raise AIGenerationError(f"AI response was not a JSON object: {type(parsed).__name__}")
    for key in ("headline", "narrative"):
        if key not in parsed or not isinstance(parsed[key], str) or not parsed[key].strip():
            raise AIGenerationError(f"AI response missing required field '{key}'")
    for key in ("notable_changes", "caveats"):
        if key in parsed and not isinstance(parsed[key], list):
            raise AIGenerationError(f"AI response field '{key}' must be a list")

    if (diff.get("summary") or {}).get("has_coverage_gap") and not parsed.get("caveats"):
        raise AIGenerationError(
            "Comparison has a plugin coverage gap but the AI narrative listed no "
            "caveats; refusing to present it as a complete comparison."
        )
