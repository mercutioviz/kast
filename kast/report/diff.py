"""Scan-to-scan comparison.

Compares two completed scan directories and reports what changed: which
issues are new, which are gone, and how the severity mix moved. The
sales motion this exists for is the before-WAF / after-WAF demo, so the
output is framed around "resolved" rather than raw set arithmetic.

Issue identity is ``(reported_by_tool, issue_id)`` — the unit an SA
presents. Multiple occurrences of the same issue collapse into one entry
with an ``occurrences`` count, so a finding that went from 12 affected
URLs to 2 shows as a persisting issue with a -10 delta rather than
disappearing into the noise.

**Coverage gating.** If a plugin ran in the baseline but not in the
current scan, every issue it reported would look "resolved". That is a
reputational hazard in front of a prospect, so the diff records plugin
coverage on both sides, marks issues whose reporting plugin is missing
as ``coverage_gap``, and excludes them from the headline resolved count.
Callers must surface ``summary["has_coverage_gap"]``.
"""

from __future__ import annotations

import json
from pathlib import Path

from kast.core.severity import Severity, severity_sort_key
from kast.report.data import calculate_waf_statistics
from kast.report_templates import get_issue_metadata

# Severity order used for the delta table, highest first.
SEVERITY_ORDER = [
    Severity.HIGH.value,
    Severity.MEDIUM.value,
    Severity.LOW.value,
    Severity.INFORMATIONAL.value,
    Severity.UNKNOWN.value,
]


class ScanDiffError(Exception):
    """A scan directory could not be loaded for comparison."""


# -- loading -----------------------------------------------------------------


def _resolve_issue_for_diff(issue, tool_name):
    """Normalize a raw issue entry into the fields the diff needs.

    Mirrors ``kast.report.data._resolve_issue`` but skips remediation
    lookup and missing-issue tracking — the diff only needs identity,
    severity, and a human label.
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
        display_name = metadata.get("display_name") or issue_id
        severity = Severity.from_registry(metadata.get("severity")).value
        category = metadata.get("category") or "Uncategorized"
        waf_addressable = bool(metadata.get("waf_addressable", False))
    else:
        display_name = issue_id
        severity = Severity.UNKNOWN.value
        category = "Uncategorized"
        waf_addressable = False

    return {
        "id": issue_id,
        "display_name": display_name,
        "description": issue_dict.get("description", ""),
        "severity": severity,
        "category": category,
        "waf_addressable": waf_addressable,
        "reported_by_tool": tool_name,
    }


def load_scan_snapshot(scan_dir) -> dict:
    """Read one scan directory into a comparable snapshot.

    Returns a dict with ``path``, ``target``, ``scan_date``,
    ``kast_version``, ``mode``, ``plugins`` (set of plugin names that
    produced a ``_processed.json``), ``issues`` (list of normalized issue
    records), ``severity_counts``, and ``waf_statistics``.

    Raises ``ScanDiffError`` if the directory holds no processed plugin
    output — comparing against an empty scan produces misleading deltas.
    """
    path = Path(scan_dir)
    if not path.is_dir():
        raise ScanDiffError(f"Not a directory: {path}")

    processed_files = sorted(path.glob("*_processed.json"))
    if not processed_files:
        raise ScanDiffError(f"No *_processed.json files in {path} — not a completed scan")

    plugins = set()
    issues = []
    for pf in processed_files:
        try:
            data = json.loads(pf.read_text())
        except (json.JSONDecodeError, OSError) as e:
            raise ScanDiffError(f"Could not read {pf.name}: {e}") from e
        tool_name = data.get("plugin-name") or pf.stem.removesuffix("_processed")
        plugins.add(tool_name)
        for issue in data.get("issues", []) or []:
            issues.append(_resolve_issue_for_diff(issue, tool_name))

    info = {}
    info_path = path / "kast_info.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text())
        except (json.JSONDecodeError, OSError):
            info = {}
    cli_args = info.get("cli_arguments") or {}

    severity_counts = {s.value: 0 for s in Severity}
    for issue in issues:
        severity_counts[Severity.from_registry(issue["severity"]).value] += 1

    return {
        "path": str(path),
        "target": cli_args.get("target") or path.name,
        "scan_date": info.get("start_timestamp"),
        "kast_version": info.get("kast_version"),
        "mode": cli_args.get("mode"),
        "plugins": plugins,
        "issues": issues,
        "total_issues": len(issues),
        "severity_counts": severity_counts,
        "waf_statistics": calculate_waf_statistics(issues),
    }


# -- comparison --------------------------------------------------------------


def _group_by_identity(issues) -> dict:
    """Collapse issue records into ``(tool, id)`` → aggregate entry."""
    grouped = {}
    for issue in issues:
        key = (issue["reported_by_tool"], issue["id"])
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {
                "id": issue["id"],
                "display_name": issue["display_name"],
                "severity": issue["severity"],
                "category": issue["category"],
                "waf_addressable": issue["waf_addressable"],
                "reported_by_tool": issue["reported_by_tool"],
                "occurrences": 1,
                "descriptions": [issue["description"]] if issue["description"] else [],
            }
        else:
            entry["occurrences"] += 1
            desc = issue["description"]
            if desc and desc not in entry["descriptions"]:
                entry["descriptions"].append(desc)
    return grouped


def _sorted_entries(entries):
    """Severity-first ordering, then occurrence count, then name."""
    return sorted(
        entries,
        key=lambda e: (
            severity_sort_key(e["severity"]),
            -e.get("occurrences", 0),
            (e.get("display_name") or "").lower(),
        ),
    )


def compute_diff(baseline: dict, current: dict) -> dict:
    """Compare two snapshots from ``load_scan_snapshot``.

    Returns a dict with ``baseline`` / ``current`` metadata blocks,
    ``new_issues`` / ``resolved_issues`` / ``persisting_issues`` lists,
    a ``coverage`` block, and a ``summary`` block. Every list is sorted
    highest-severity first.
    """
    base_grouped = _group_by_identity(baseline["issues"])
    curr_grouped = _group_by_identity(current["issues"])

    dropped_plugins = baseline["plugins"] - current["plugins"]
    added_plugins = current["plugins"] - baseline["plugins"]

    # A plugin that did not run on both sides cannot support a
    # new-vs-resolved claim about the issues it reports.
    new_issues = _sorted_entries([
        {**entry, "coverage_gap": entry["reported_by_tool"] in added_plugins}
        for key, entry in curr_grouped.items() if key not in base_grouped
    ])
    resolved_issues = _sorted_entries([
        {**entry, "coverage_gap": entry["reported_by_tool"] in dropped_plugins}
        for key, entry in base_grouped.items() if key not in curr_grouped
    ])
    persisting_issues = _sorted_entries([
        {
            **curr_grouped[key],
            "baseline_occurrences": entry["occurrences"],
            "occurrence_delta": curr_grouped[key]["occurrences"] - entry["occurrences"],
            "baseline_severity": entry["severity"],
            "severity_changed": entry["severity"] != curr_grouped[key]["severity"],
        }
        for key, entry in base_grouped.items() if key in curr_grouped
    ])

    confirmed_resolved = [i for i in resolved_issues if not i["coverage_gap"]]
    unverifiable_resolved = [i for i in resolved_issues if i["coverage_gap"]]
    confirmed_new = [i for i in new_issues if not i["coverage_gap"]]

    baseline_only_plugins = sorted(dropped_plugins)
    current_only_plugins = sorted(added_plugins)

    severity_deltas = {
        sev: current["severity_counts"].get(sev, 0) - baseline["severity_counts"].get(sev, 0)
        for sev in SEVERITY_ORDER
    }

    base_waf = baseline["waf_statistics"]
    curr_waf = current["waf_statistics"]

    summary = {
        "new_count": len(confirmed_new),
        "unverifiable_new_count": len(new_issues) - len(confirmed_new),
        "resolved_count": len(confirmed_resolved),
        "unverifiable_resolved_count": len(unverifiable_resolved),
        "persisting_count": len(persisting_issues),
        "total_delta": current["total_issues"] - baseline["total_issues"],
        "severity_deltas": severity_deltas,
        "waf_addressable_delta": (
            curr_waf["waf_addressable_count"] - base_waf["waf_addressable_count"]
        ),
        "waf_addressable_resolved": len(
            [i for i in confirmed_resolved if i["waf_addressable"]]
        ),
        "has_coverage_gap": bool(baseline_only_plugins or current_only_plugins),
        "target_match": baseline["target"] == current["target"],
    }

    return {
        "baseline": {k: v for k, v in baseline.items() if k not in ("issues", "plugins")},
        "current": {k: v for k, v in current.items() if k not in ("issues", "plugins")},
        "coverage": {
            "baseline_plugins": sorted(baseline["plugins"]),
            "current_plugins": sorted(current["plugins"]),
            "baseline_only": baseline_only_plugins,
            "current_only": current_only_plugins,
            "shared": sorted(baseline["plugins"] & current["plugins"]),
        },
        "new_issues": new_issues,
        "resolved_issues": resolved_issues,
        "persisting_issues": persisting_issues,
        "summary": summary,
    }


def diff_scans(baseline_dir, current_dir) -> dict:
    """Load both directories and compare them. One-shot entrypoint."""
    return compute_diff(load_scan_snapshot(baseline_dir), load_scan_snapshot(current_dir))


# -- narrative ---------------------------------------------------------------


def build_headline(diff: dict) -> str:
    """One-sentence plain-language framing of the comparison."""
    s = diff["summary"]
    target = diff["current"]["target"]
    resolved, new = s["resolved_count"], s["new_count"]

    if resolved and not new:
        return (
            f"{resolved} issue type(s) previously found on {target} are no longer "
            f"detected, and no new issues appeared."
        )
    if resolved and new:
        return (
            f"{resolved} issue type(s) on {target} are no longer detected, "
            f"while {new} new issue type(s) appeared."
        )
    if new and not resolved:
        return f"{new} new issue type(s) appeared on {target}; none were resolved."
    if s["persisting_count"]:
        return f"No change in the issue set for {target}."
    return f"No issues detected in either scan of {target}."
