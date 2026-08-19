"""Tests for kast.ai.diff_narrative — orchestrator with a mocked adapter.

The coverage-gap tests are the load-bearing ones: a comparison that cannot
support a resolved/new claim must not reach a prospect as if it could.
"""

import json

import pytest

from kast.ai import AIGenerationError, AIResponse
from kast.ai.diff_narrative import _build_context, _issue_context, generate_diff_narrative


class _MockAdapter:
    def __init__(self, response_text, *, model="claude-sonnet-4-6"):
        self._text = response_text
        self._model = model
        self.last_call: dict | None = None

    def generate(self, *, prompt, system="", response_schema=None,
                 max_tokens=2000, temperature=0.3):
        self.last_call = {
            "prompt": prompt, "system": system,
            "response_schema": response_schema,
            "max_tokens": max_tokens, "temperature": temperature,
        }
        return AIResponse(
            text=self._text, tokens_in=120, tokens_out=340,
            model=self._model, latency_ms=55, raw_response=None,
        )


def _entry(issue_id, severity="Medium", tool="testssl", **extra):
    return {
        "id": issue_id,
        "display_name": issue_id.replace("-", " ").title(),
        "severity": severity,
        "category": "Transport Security",
        "waf_addressable": True,
        "reported_by_tool": tool,
        "occurrences": 1,
        "descriptions": [],
        "coverage_gap": False,
        **extra,
    }


def _sample_diff(**overrides):
    diff = {
        "baseline": {
            "path": "/scans/a", "target": "https://example.com",
            "scan_date": "2026-06-01T10:00:00.000+00:00",
            "total_issues": 4, "severity_counts": {"High": 1, "Medium": 3},
        },
        "current": {
            "path": "/scans/b", "target": "https://example.com",
            "scan_date": "2026-08-01T10:00:00.000+00:00",
            "total_issues": 3, "severity_counts": {"High": 0, "Medium": 3},
        },
        "coverage": {
            "baseline_plugins": ["testssl", "whatweb"],
            "current_plugins": ["testssl", "whatweb"],
            "baseline_only": [], "current_only": [],
        },
        "resolved_issues": [_entry("sslv3", "High")],
        "new_issues": [],
        "persisting_issues": [_entry("missing-hsts")],
        "summary": {
            "new_count": 0, "unverifiable_new_count": 0,
            "resolved_count": 1, "unverifiable_resolved_count": 0,
            "persisting_count": 1, "total_delta": -1,
            "severity_deltas": {"High": -1, "Medium": 0, "Low": 0},
            "waf_addressable_delta": -1, "waf_addressable_resolved": 1,
            "has_coverage_gap": False, "target_match": True,
        },
    }
    diff.update(overrides)
    return diff


def _good_response(**extra):
    payload = {
        "headline": "One high-severity transport issue was resolved.",
        "narrative": "SSLv3 is no longer offered.\n\nThe HSTS gap remains.",
        "notable_changes": ["SSLv3 support removed"],
        "caveats": [],
    }
    payload.update(extra)
    return json.dumps(payload)


def test_generate_success():
    adapter = _MockAdapter(_good_response())
    result = generate_diff_narrative(adapter, _sample_diff())

    assert result["headline"].startswith("One high-severity")
    assert result["notable_changes"] == ["SSLv3 support removed"]
    meta = result["_meta"]
    assert meta["model"] == "claude-sonnet-4-6"
    assert meta["tokens_in"] == 120
    assert meta["prompt_name"] == "diff_narrative_v1"
    assert meta["prompt_version"] == 1


def test_generate_passes_schema_to_adapter():
    adapter = _MockAdapter(_good_response())
    generate_diff_narrative(adapter, _sample_diff())

    schema = adapter.last_call["response_schema"]
    assert schema["type"] == "object"
    assert "headline" in schema["required"]
    assert "narrative" in schema["required"]
    assert "caveats" in schema["properties"]


def test_prompt_renders_target_dates_and_issues():
    adapter = _MockAdapter(_good_response())
    generate_diff_narrative(adapter, _sample_diff())

    prompt = adapter.last_call["prompt"]
    assert "https://example.com" in prompt
    assert "2026-06-01 10:00:00" in prompt
    assert "2026-08-01 10:00:00" in prompt
    assert "Sslv3" in prompt
    assert "the comparison is complete" in prompt


def test_prompt_flags_target_mismatch():
    diff = _sample_diff()
    diff["current"]["target"] = "https://other.example"
    diff["summary"]["target_match"] = False
    adapter = _MockAdapter(_good_response(caveats=["Targets differ"]))
    generate_diff_narrative(adapter, diff)

    assert "different targets" in adapter.last_call["prompt"]


def test_invalid_json_raises():
    adapter = _MockAdapter("not json at all")
    with pytest.raises(AIGenerationError, match="not valid JSON"):
        generate_diff_narrative(adapter, _sample_diff())


def test_missing_headline_raises():
    adapter = _MockAdapter(json.dumps({"narrative": "n"}))
    with pytest.raises(AIGenerationError, match="missing required field"):
        generate_diff_narrative(adapter, _sample_diff())


def test_empty_narrative_raises():
    adapter = _MockAdapter(json.dumps({"headline": "h", "narrative": "   "}))
    with pytest.raises(AIGenerationError, match="missing required field"):
        generate_diff_narrative(adapter, _sample_diff())


def test_notable_changes_must_be_list():
    adapter = _MockAdapter(_good_response(notable_changes="nope"))
    with pytest.raises(AIGenerationError, match="must be a list"):
        generate_diff_narrative(adapter, _sample_diff())


def _gapped_diff():
    diff = _sample_diff()
    diff["coverage"]["baseline_only"] = ["nikto"]
    diff["coverage"]["current_plugins"] = ["testssl", "whatweb"]
    diff["resolved_issues"].append(
        _entry("nikto-finding", "Medium", tool="nikto", coverage_gap=True)
    )
    diff["summary"]["has_coverage_gap"] = True
    diff["summary"]["unverifiable_resolved_count"] = 1
    return diff


def test_coverage_gap_without_caveats_raises():
    adapter = _MockAdapter(_good_response(caveats=[]))
    with pytest.raises(AIGenerationError, match="coverage gap"):
        generate_diff_narrative(adapter, _gapped_diff())


def test_coverage_gap_with_caveats_passes():
    adapter = _MockAdapter(_good_response(caveats=["nikto did not re-run"]))
    result = generate_diff_narrative(adapter, _gapped_diff())
    assert result["caveats"] == ["nikto did not re-run"]


def test_coverage_gap_issue_never_reaches_the_prompt():
    adapter = _MockAdapter(_good_response(caveats=["nikto did not re-run"]))
    generate_diff_narrative(adapter, _gapped_diff())

    prompt = adapter.last_call["prompt"]
    assert "Nikto Finding" not in prompt
    assert "COVERAGE GAP" in prompt
    assert "nikto" in prompt


def test_issue_context_caps_the_list():
    issues = [_entry(f"issue-{i}") for i in range(40)]
    assert len(_issue_context(issues)) == 15


def test_build_context_handles_empty_diff():
    ctx = _build_context({})
    assert ctx["target"] == "(unknown)"
    assert ctx["baseline_date"] == "(unknown)"
    assert ctx["resolved"] == []
    assert ctx["has_coverage_gap"] is False
