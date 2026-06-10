"""Tests for ``kast registry`` group.

Closes the audit § 5a.5 gap: the v2 ``fix_registry.py`` workflow is
replaced by ``kast registry add`` and ``kast registry promote``. These
tests use a tmp_path-backed REGISTRY_PATH so the real registry isn't
mutated.
"""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kast.cli.registry import registry as registry_group


@pytest.fixture
def tmp_registry(tmp_path):
    """A patched-in tmp registry file; yields the Path."""
    path = tmp_path / "issue_registry.json"
    path.write_text(json.dumps({}))
    with patch("kast.cli.registry.REGISTRY_PATH", path):
        yield path


# -- registry list ----------------------------------------------------------


def test_registry_list_real_registry_succeeds():
    """The real shipped registry should list cleanly."""
    runner = CliRunner()
    result = runner.invoke(registry_group, ["list"])
    assert result.exit_code == 0
    # 68+ entries after the testssl promotion in the validation phase
    assert "Issue Registry" in result.output


def test_registry_list_json_against_real_registry():
    runner = CliRunner()
    result = runner.invoke(registry_group, ["list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "registry" in payload
    assert "count" in payload
    assert payload["count"] >= 60
    # Each entry includes the id and the canonical fields
    sample = payload["registry"][0]
    assert "id" in sample
    assert "severity" in sample
    assert "category" in sample


def test_registry_list_filters_by_severity(tmp_registry):
    tmp_registry.write_text(json.dumps({
        "high1": {"severity": "High", "category": "X", "waf_addressable": True},
        "med1": {"severity": "Medium", "category": "Y", "waf_addressable": False},
        "high2": {"severity": "High", "category": "Z", "waf_addressable": True},
    }))
    runner = CliRunner()
    result = runner.invoke(registry_group, ["list", "--severity", "High", "--json"])
    payload = json.loads(result.output)
    assert payload["count"] == 2
    assert {r["id"] for r in payload["registry"]} == {"high1", "high2"}


def test_registry_list_filters_by_waf_addressable(tmp_registry):
    tmp_registry.write_text(json.dumps({
        "yes": {"severity": "High", "category": "X", "waf_addressable": True},
        "no":  {"severity": "Medium", "category": "Y", "waf_addressable": False},
    }))
    runner = CliRunner()
    result = runner.invoke(registry_group, ["list", "--waf-addressable", "--json"])
    payload = json.loads(result.output)
    assert {r["id"] for r in payload["registry"]} == {"yes"}

    result = runner.invoke(registry_group, ["list", "--no-waf-addressable", "--json"])
    payload = json.loads(result.output)
    assert {r["id"] for r in payload["registry"]} == {"no"}


def test_registry_list_filters_by_category_substring(tmp_registry):
    tmp_registry.write_text(json.dumps({
        "tls1": {"severity": "High", "category": "Encryption", "waf_addressable": True},
        "h1":   {"severity": "Medium", "category": "HTTP Headers", "waf_addressable": True},
        "h2":   {"severity": "Low", "category": "Header Configuration", "waf_addressable": False},
    }))
    runner = CliRunner()
    # case-insensitive substring "header" → 2 entries
    result = runner.invoke(registry_group, ["list", "--category", "header", "--json"])
    payload = json.loads(result.output)
    assert {r["id"] for r in payload["registry"]} == {"h1", "h2"}


# -- registry add -----------------------------------------------------------


def test_registry_add_creates_entry(tmp_registry):
    runner = CliRunner()
    result = runner.invoke(registry_group, [
        "add", "TEST-001",
        "--severity", "High",
        "--category", "Encryption",
        "--waf-addressable",
    ])
    assert result.exit_code == 0
    data = json.loads(tmp_registry.read_text())
    assert "TEST-001" in data
    entry = data["TEST-001"]
    assert entry["severity"] == "High"
    assert entry["category"] == "Encryption"
    assert entry["waf_addressable"] is True
    # display_name derived from id
    assert entry["display_name"] == "Test 001"


def test_registry_add_rejects_existing_without_force(tmp_registry):
    tmp_registry.write_text(json.dumps({"TEST-001": {"severity": "High"}}))
    runner = CliRunner()
    result = runner.invoke(registry_group, [
        "add", "TEST-001",
        "--severity", "Medium",
        "--category", "X",
    ])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_registry_add_force_overwrites(tmp_registry):
    tmp_registry.write_text(json.dumps({
        "TEST-001": {
            "severity": "High",
            "category": "Old",
            "display_name": "Old",
            "waf_addressable": False,
        }
    }))
    runner = CliRunner()
    result = runner.invoke(registry_group, [
        "add", "TEST-001",
        "--severity", "Low",
        "--category", "New",
        "--force",
    ])
    assert result.exit_code == 0
    data = json.loads(tmp_registry.read_text())
    assert data["TEST-001"]["severity"] == "Low"
    assert data["TEST-001"]["category"] == "New"


def test_registry_add_invalid_severity_rejected(tmp_registry):
    runner = CliRunner()
    result = runner.invoke(registry_group, [
        "add", "TEST-001",
        "--severity", "Critical",  # not a canonical severity
        "--category", "X",
    ])
    assert result.exit_code != 0
    assert "Invalid value" in result.output or "Critical" in result.output


# -- registry promote -------------------------------------------------------


def _missing_issue_payload(issue_ids: list[str]) -> dict:
    """Build a minimal missing_issue_ids.json structure."""
    return {
        "scan_metadata": {
            "scan_date": "2026-05-01 12:00:00",
            "target": "example.com",
            "total_missing_issues": len(issue_ids),
            "total_occurrences": len(issue_ids),
        },
        "missing_issues": [
            {
                "issue_id": iid,
                "plugin_name": "testssl",
                "plugin_display_name": "Test SSL",
                "occurrence_count": 1,
                "first_seen": "2026-05-01T12:00:00",
                "descriptions": ["a description"],
                "suggested_metadata": {
                    "display_name": iid.replace("_", " ").title(),
                    "category": "Encryption",
                    "severity": "Medium",
                    "waf_addressable": True,
                    "remediation": f"Address {iid}.",
                },
                "registry_template": {},
            }
            for iid in issue_ids
        ],
    }


def test_registry_promote_no_missing_file(tmp_path, tmp_registry):
    runner = CliRunner()
    result = runner.invoke(registry_group, ["promote", str(tmp_path)])
    assert result.exit_code == 0
    assert "No missing_issue_ids.json" in result.output


def test_registry_promote_accept_all(tmp_path, tmp_registry):
    """--accept-all promotes every candidate without prompting."""
    missing_path = tmp_path / "missing_issue_ids.json"
    missing_path.write_text(json.dumps(_missing_issue_payload(["NEW-001", "NEW-002"])))
    runner = CliRunner()
    result = runner.invoke(registry_group, ["promote", str(tmp_path), "--accept-all"])
    assert result.exit_code == 0, result.output
    data = json.loads(tmp_registry.read_text())
    assert "NEW-001" in data
    assert "NEW-002" in data
    assert data["NEW-001"]["category"] == "Encryption"
    assert data["NEW-001"]["severity"] == "Medium"


def test_registry_promote_dry_run(tmp_path, tmp_registry):
    missing_path = tmp_path / "missing_issue_ids.json"
    missing_path.write_text(json.dumps(_missing_issue_payload(["NEW-A"])))
    runner = CliRunner()
    result = runner.invoke(
        registry_group,
        ["promote", str(tmp_path), "--accept-all", "--dry-run"],
    )
    assert result.exit_code == 0
    # Registry unchanged
    data = json.loads(tmp_registry.read_text())
    assert data == {}
    assert "Dry run" in result.output


def test_registry_promote_skips_already_in_registry(tmp_path, tmp_registry):
    """A candidate already in the registry is silently skipped, not duplicated."""
    tmp_registry.write_text(json.dumps({
        "EXISTING": {"severity": "High", "category": "X"}
    }))
    missing_path = tmp_path / "missing_issue_ids.json"
    missing_path.write_text(json.dumps(_missing_issue_payload(["EXISTING", "NEW"])))
    runner = CliRunner()
    result = runner.invoke(registry_group, ["promote", str(tmp_path), "--accept-all"])
    assert result.exit_code == 0
    data = json.loads(tmp_registry.read_text())
    # EXISTING preserved; NEW added
    assert data["EXISTING"]["severity"] == "High"
    assert data["EXISTING"]["category"] == "X"
    assert "NEW" in data
