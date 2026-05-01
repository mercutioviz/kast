"""Tests for the Severity enum and helpers (kast.core.severity).

Pins down the structural fix for the Info/Informational mismatch surfaced
in the v2 audit (5a.12) and the legacy "Issue ID not found." sentinel
that report_templates.get_severity used to return.
"""

from kast.core.severity import Severity, SEVERITY_ORDER, severity_sort_key


def test_severity_string_equality():
    """Members compare equal to their underlying string values."""
    assert Severity.HIGH == "High"
    assert "High" == Severity.HIGH
    assert Severity.INFORMATIONAL == "Informational"


def test_severity_str_returns_value():
    """str(Severity.X) yields the value, not the enum name."""
    assert str(Severity.HIGH) == "High"
    assert f"{Severity.INFORMATIONAL}" == "Informational"


def test_from_registry_canonical_values():
    for canonical in ["High", "Medium", "Low", "Informational", "Unknown"]:
        assert Severity.from_registry(canonical).value == canonical


def test_from_registry_normalizes_legacy_info():
    """The historical 'Info' spelling normalizes to INFORMATIONAL."""
    assert Severity.from_registry("Info") is Severity.INFORMATIONAL


def test_from_registry_normalizes_sentinel():
    """The legacy 'Issue ID not found.' sentinel falls through to UNKNOWN."""
    assert Severity.from_registry("Issue ID not found.") is Severity.UNKNOWN


def test_from_registry_unknown_string_falls_back_to_unknown():
    assert Severity.from_registry("Critical") is Severity.UNKNOWN
    assert Severity.from_registry("") is Severity.UNKNOWN
    assert Severity.from_registry(None) is Severity.UNKNOWN
    assert Severity.from_registry(42) is Severity.UNKNOWN


def test_from_registry_idempotent_on_severity_instances():
    assert Severity.from_registry(Severity.HIGH) is Severity.HIGH
    assert Severity.from_registry(Severity.UNKNOWN) is Severity.UNKNOWN


def test_severity_order_is_strictly_descending():
    assert SEVERITY_ORDER[Severity.HIGH] < SEVERITY_ORDER[Severity.MEDIUM]
    assert SEVERITY_ORDER[Severity.MEDIUM] < SEVERITY_ORDER[Severity.LOW]
    assert SEVERITY_ORDER[Severity.LOW] < SEVERITY_ORDER[Severity.INFORMATIONAL]
    assert SEVERITY_ORDER[Severity.INFORMATIONAL] < SEVERITY_ORDER[Severity.UNKNOWN]


def test_severity_sort_key_with_strings_and_legacy():
    """Sort key accepts canonical strings, legacy 'Info', and unknowns."""
    items = [
        {"name": "low", "severity": "Low"},
        {"name": "high", "severity": "High"},
        {"name": "info_canonical", "severity": "Informational"},
        {"name": "info_legacy", "severity": "Info"},
        {"name": "unknown", "severity": "Bogus"},
        {"name": "medium", "severity": "Medium"},
    ]
    items.sort(key=lambda x: severity_sort_key(x["severity"]))
    assert items[0]["name"] == "high"
    assert items[1]["name"] == "medium"
    assert items[2]["name"] == "low"
    # info_canonical and info_legacy tie at position 3 (both INFORMATIONAL)
    info_names = {items[3]["name"], items[4]["name"]}
    assert info_names == {"info_canonical", "info_legacy"}
    assert items[5]["name"] == "unknown"
