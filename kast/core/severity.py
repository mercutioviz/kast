"""Canonical severity vocabulary for kast.

The Severity enum is the single source of truth for severity values across
plugin findings, issue-registry consumption, report badge counts, sort order,
and template rendering.

Historically, the issue registry stored "Informational" while report code
checked for "Info" (see audit 5a.12). The from_registry() classmethod
normalizes both legacy and current spellings, making the Info/Informational
mismatch structurally impossible.

Usage:
    from kast.core.severity import Severity, severity_sort_key

    sev = Severity.from_registry(registry_entry["severity"])
    counts = {s: 0 for s in Severity}
    issues.sort(key=lambda i: severity_sort_key(i["severity"]))
"""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    """Severity levels in kast.

    Inherits from str so members compare equal to their string values:
    `Severity.HIGH == "High"` is True. `__str__` returns the value (not the
    enum name) so f-strings and template rendering produce "High", not
    "Severity.HIGH".
    """

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFORMATIONAL = "Informational"
    UNKNOWN = "Unknown"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_registry(cls, value: object) -> Severity:
        """Parse a severity value with normalization.

        Accepts:
        - Canonical values: "Critical", "High", "Medium", "Low",
          "Informational", "Unknown"
        - Legacy "Info" (normalized to INFORMATIONAL — historical mismatch)
        - The legacy "Issue ID not found." sentinel (normalized to UNKNOWN)
        - Already-Severity instances (returned as-is)
        - Anything else (normalized to UNKNOWN — defensive)
        """
        if isinstance(value, cls):
            return value
        if value == "Info":
            return cls.INFORMATIONAL
        try:
            return cls(value)
        except (ValueError, TypeError):
            return cls.UNKNOWN


# Sort order for "highest severity first" sorting; lower index = higher.
SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFORMATIONAL: 4,
    Severity.UNKNOWN: 5,
}


def severity_sort_key(value: object) -> int:
    """Sort key for `list.sort(key=...)` accepting strings or Severity members.

    Lower return value = higher severity (sorts first). Unknown values sort
    last.
    """
    return SEVERITY_ORDER[Severity.from_registry(value)]
