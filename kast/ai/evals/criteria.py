"""Quality criteria for AI executive summary outputs.

Each criterion is a callable ``(output: dict, *, context: dict | None = None)
-> CriterionResult``.  The ``context`` kwarg carries the scenario's
``report_data`` for criteria that need to cross-reference the input (e.g.
confirming the target domain appears in the output).

Add new criteria to STANDARD_CRITERIA to have them applied by default.
"""

from __future__ import annotations

from dataclasses import dataclass


# Phrases the prompt explicitly forbids — they signal lazy, non-specific output.
_FORBIDDEN_PHRASES = [
    "various security issues",
    "multiple concerns",
    "several issues",
    "a number of vulnerabilities",
    "best practices",
    "world-class",
    "comprehensive",
]


@dataclass
class CriterionResult:
    name: str
    passed: bool
    message: str

    def __bool__(self) -> bool:
        return self.passed


# ---------------------------------------------------------------------------
# Individual criteria
# ---------------------------------------------------------------------------


def check_schema(output: dict, *, context: dict | None = None) -> CriterionResult:
    """Required fields present and non-empty."""
    for key in ("headline", "narrative"):
        if key not in output:
            return CriterionResult("schema", False, f"Missing required field '{key}'")
        if not isinstance(output[key], str) or not output[key].strip():
            return CriterionResult("schema", False, f"Field '{key}' is empty or not a string")
    for key in ("key_findings", "recommended_actions"):
        if key in output and not isinstance(output[key], list):
            return CriterionResult("schema", False, f"Field '{key}' must be a list, got {type(output[key]).__name__}")
    return CriterionResult("schema", True, "All required fields present and well-typed")


def check_headline_length(output: dict, *, context: dict | None = None, max_chars: int = 240) -> CriterionResult:
    """Headline fits within max_chars (prompt schema: maxLength 240)."""
    headline = output.get("headline", "")
    n = len(headline)
    if n <= max_chars:
        return CriterionResult("headline_length", True, f"Headline length {n} <= {max_chars}")
    return CriterionResult("headline_length", False, f"Headline too long: {n} chars (max {max_chars})")


def check_headline_not_generic(output: dict, *, context: dict | None = None) -> CriterionResult:
    """Headline is not a placeholder or obvious generic string."""
    headline = output.get("headline", "").strip().lower()
    generic = {"", "n/a", "executive summary", "security scan results", "summary"}
    if headline in generic:
        return CriterionResult("headline_not_generic", False, f"Headline is a generic placeholder: {headline!r}")
    return CriterionResult("headline_not_generic", True, "Headline appears non-generic")


def check_narrative_length(output: dict, *, context: dict | None = None,
                            min_chars: int = 150) -> CriterionResult:
    """Narrative is substantive (at least min_chars)."""
    narrative = output.get("narrative", "")
    n = len(narrative.strip())
    if n >= min_chars:
        return CriterionResult("narrative_length", True, f"Narrative length {n} >= {min_chars}")
    return CriterionResult("narrative_length", False, f"Narrative too short: {n} chars (min {min_chars})")


def check_key_findings_count(output: dict, *, context: dict | None = None,
                              min_count: int = 2, max_count: int = 8) -> CriterionResult:
    """key_findings list has a reasonable number of entries."""
    findings = output.get("key_findings", [])
    if not isinstance(findings, list):
        return CriterionResult("key_findings_count", False, "key_findings is not a list")
    n = len(findings)
    if min_count <= n <= max_count:
        return CriterionResult("key_findings_count", True, f"{n} key findings (expected {min_count}-{max_count})")
    return CriterionResult("key_findings_count", False,
                           f"{n} key findings, expected {min_count}-{max_count}")


def check_recommended_actions_count(output: dict, *, context: dict | None = None,
                                    min_count: int = 1, max_count: int = 6) -> CriterionResult:
    """recommended_actions list has a reasonable number of entries."""
    actions = output.get("recommended_actions", [])
    if not isinstance(actions, list):
        return CriterionResult("recommended_actions_count", False, "recommended_actions is not a list")
    n = len(actions)
    if min_count <= n <= max_count:
        return CriterionResult("recommended_actions_count", True,
                               f"{n} recommended actions (expected {min_count}-{max_count})")
    return CriterionResult("recommended_actions_count", False,
                           f"{n} recommended actions, expected {min_count}-{max_count}")


def check_target_mentioned(output: dict, *, context: dict | None = None) -> CriterionResult:
    """Target domain appears in headline or narrative (prompt goal: be specific)."""
    if context is None:
        return CriterionResult("target_mentioned", True, "Skipped — no context provided")
    target = (context.get("target") or "").lower().lstrip("https://").lstrip("http://").split("/")[0]
    if not target:
        return CriterionResult("target_mentioned", True, "Skipped — target is empty")
    text = (output.get("headline", "") + " " + output.get("narrative", "")).lower()
    if target in text:
        return CriterionResult("target_mentioned", True, f"Target '{target}' mentioned in output")
    return CriterionResult("target_mentioned", False,
                           f"Target '{target}' not mentioned in headline/narrative")


def check_no_forbidden_phrases(output: dict, *, context: dict | None = None) -> CriterionResult:
    """Output avoids vague filler phrases that the prompt explicitly discourages."""
    text = " ".join([
        output.get("headline", ""),
        output.get("narrative", ""),
    ]).lower()
    found = [p for p in _FORBIDDEN_PHRASES if p in text]
    if not found:
        return CriterionResult("no_forbidden_phrases", True, "No forbidden filler phrases found")
    return CriterionResult("no_forbidden_phrases", False, f"Forbidden phrase(s) found: {found}")


# ---------------------------------------------------------------------------
# Default criteria set
# ---------------------------------------------------------------------------

STANDARD_CRITERIA = [
    check_schema,
    check_headline_length,
    check_headline_not_generic,
    check_narrative_length,
    check_key_findings_count,
    check_recommended_actions_count,
    check_target_mentioned,
    check_no_forbidden_phrases,
]
