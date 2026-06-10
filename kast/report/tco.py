"""TCO (Total Cost of Ownership) appendix renderer (Phase C5 / F1).

Reads ``code_fix_timeframe`` and ``waf_deployment_timeframe`` from each
issue's registry entry, aggregates totals, and produces the data structure
that the report templates render as the TCO appendix.

The appendix surfaces the trade-off explicitly: "addressing in code takes
N weeks; with a WAF, M days." It's the most concrete sales-enablement
section in the report — pure rendering, no AI required.

Timeframes in the registry are strings like ``"1-2 weeks"``, ``"4-6 weeks"``,
``"1 week"``, ``"1-2 days"``, or ``"N/A"`` / ``None``. We parse them into
``(min_days, max_days)`` tuples for aggregation, then format back to
human-readable strings.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from kast.report_templates import get_issue_metadata

_TIMEFRAME_RE = re.compile(
    r"^\s*(\d+)(?:\s*-\s*(\d+))?\s*(day|days|week|weeks)\s*$",
    re.IGNORECASE,
)
_DAYS_PER_UNIT = {
    "day": 1,
    "days": 1,
    "week": 7,
    "weeks": 7,
}


def parse_timeframe(value: str | None) -> tuple[int, int] | None:
    """Parse ``"1-2 weeks"`` / ``"1 week"`` / ``"1-2 days"`` to ``(min_days, max_days)``.

    Returns ``None`` for ``"N/A"``, ``None``, or anything unparseable.
    """
    if not value:
        return None
    s = str(value).strip()
    if not s or s.upper() == "N/A":
        return None
    m = _TIMEFRAME_RE.match(s)
    if not m:
        return None
    low = int(m.group(1))
    high = int(m.group(2)) if m.group(2) else low
    unit_days = _DAYS_PER_UNIT[m.group(3).lower()]
    return (low * unit_days, high * unit_days)


def format_days(low: int, high: int) -> str:
    """Format a ``(min_days, max_days)`` tuple to a compact human string.

    Prefers weeks when the value is large enough to be cleanly weekly; falls
    back to days otherwise. Single-value ranges drop the dash.
    """
    def _one(value: int) -> tuple[int, str]:
        if value >= 7 and value % 7 == 0:
            return value // 7, "week"
        return value, "day"

    if low == high:
        n, unit = _one(low)
        plural = unit + ("s" if n != 1 else "")
        return f"{n} {plural}"

    # Pick the bigger unit if both values are in whole weeks.
    if low >= 7 and high >= 7 and low % 7 == 0 and high % 7 == 0:
        return f"{low // 7}-{high // 7} weeks"
    return f"{low}-{high} days"


def compute_tco(all_issues: Iterable[dict]) -> dict:
    """Compute the TCO appendix data from a list of resolved issue records.

    ``all_issues`` is the ``report_data["all_issues"]`` list — each entry has
    ``id``, ``display_name``, ``severity``, ``category``, ``description``,
    ``reported_by``, etc.

    Returns a dict with:

    - ``per_issue`` — list of ``{id, display_name, severity, category,
      code_fix_range, waf_deploy_range, code_fix_days, waf_deploy_days}``.
      ``*_range`` are human-readable strings; ``*_days`` are ``(min, max)``
      tuples or ``None``.
    - ``totals`` — ``{code_fix_min_days, code_fix_max_days,
      waf_deploy_min_days, waf_deploy_max_days, code_fix_summary,
      waf_deploy_summary}``.
    - ``issue_count`` — total issues.
    - ``code_fix_count`` / ``waf_deploy_count`` — how many had parseable
      timeframes (the totals are over these only).
    - ``has_data`` — True if at least one parseable timeframe in either
      column. False means the appendix should not render.
    """
    per_issue: list[dict] = []
    code_fix_min_total = 0
    code_fix_max_total = 0
    waf_deploy_min_total = 0
    waf_deploy_max_total = 0
    code_fix_count = 0
    waf_deploy_count = 0

    for issue in all_issues:
        issue_id = issue.get("id")
        meta = get_issue_metadata(issue_id) if issue_id else None
        code_raw = (meta or {}).get("code_fix_timeframe")
        waf_raw = (meta or {}).get("waf_deployment_timeframe")

        code_days = parse_timeframe(code_raw)
        waf_days = parse_timeframe(waf_raw)

        if code_days:
            code_fix_count += 1
            code_fix_min_total += code_days[0]
            code_fix_max_total += code_days[1]
        if waf_days:
            waf_deploy_count += 1
            waf_deploy_min_total += waf_days[0]
            waf_deploy_max_total += waf_days[1]

        per_issue.append({
            "id": issue_id,
            "display_name": issue.get("display_name", issue_id or "Unknown"),
            "severity": issue.get("severity"),
            "category": issue.get("category"),
            "code_fix_range": code_raw if code_raw and str(code_raw).upper() != "N/A" else "N/A",
            "waf_deploy_range": waf_raw if waf_raw and str(waf_raw).upper() != "N/A" else "N/A",
            "code_fix_days": code_days,
            "waf_deploy_days": waf_days,
        })

    has_data = code_fix_count > 0 or waf_deploy_count > 0
    code_fix_summary = (
        format_days(code_fix_min_total, code_fix_max_total) if code_fix_count else "N/A"
    )
    waf_deploy_summary = (
        format_days(waf_deploy_min_total, waf_deploy_max_total) if waf_deploy_count else "N/A"
    )

    return {
        "per_issue": per_issue,
        "totals": {
            "code_fix_min_days": code_fix_min_total,
            "code_fix_max_days": code_fix_max_total,
            "waf_deploy_min_days": waf_deploy_min_total,
            "waf_deploy_max_days": waf_deploy_max_total,
            "code_fix_summary": code_fix_summary,
            "waf_deploy_summary": waf_deploy_summary,
        },
        "issue_count": len(per_issue),
        "code_fix_count": code_fix_count,
        "waf_deploy_count": waf_deploy_count,
        "has_data": has_data,
    }
