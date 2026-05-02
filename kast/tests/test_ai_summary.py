"""Tests for kast.ai.summary — orchestrator with mocked adapter."""

import json

import pytest

from kast.ai import AIGenerationError, AIResponse
from kast.ai.summary import _build_context, generate_ai_summary


class _MockAdapter:
    """Adapter stub with a configurable response."""

    def __init__(self, response_text, *, model="claude-sonnet-4-6",
                 tokens_in=100, tokens_out=200):
        self._text = response_text
        self._model = model
        self._tokens_in = tokens_in
        self._tokens_out = tokens_out
        self.last_call: dict | None = None

    def generate(self, *, prompt, system="", response_schema=None,
                 max_tokens=2000, temperature=0.3):
        self.last_call = {
            "prompt": prompt, "system": system,
            "response_schema": response_schema,
            "max_tokens": max_tokens, "temperature": temperature,
        }
        return AIResponse(
            text=self._text, tokens_in=self._tokens_in,
            tokens_out=self._tokens_out, model=self._model,
            latency_ms=42, raw_response=None,
        )


def _sample_report_data():
    return {
        "target": "example.com",
        "all_issues": [
            {"id": "MISSING_HSTS", "display_name": "Missing HSTS",
             "severity": "Medium", "category": "Headers",
             "reported_by": "TestSSL", "description": "HSTS not enforced"},
        ],
        "plugin_executive_summaries": [
            {"plugin_name": "Wafw00f", "tool_name": "wafw00f",
             "summary": "No WAF detected"},
        ],
        "scan_metadata": {
            "total_issues": 1,
            "severity_counts": {"High": 0, "Medium": 1, "Low": 0,
                                "Informational": 0, "Unknown": 0},
            "waf_statistics": {
                "total_issues": 1, "waf_addressable_count": 1,
                "waf_addressable_percentage": 100.0,
                "high_severity_waf": 0, "medium_severity_waf": 1,
                "low_severity_waf": 0,
            },
        },
    }


def _good_response_text():
    return json.dumps({
        "headline": "Missing HSTS leaves login flow vulnerable.",
        "narrative": "The scan found that HSTS is not enforced...",
        "key_findings": ["No HSTS header present"],
        "recommended_actions": ["Enable HSTS with preload"],
    })


def test_generate_ai_summary_success():
    adapter = _MockAdapter(_good_response_text())
    result = generate_ai_summary(adapter, _sample_report_data())

    assert result["headline"].startswith("Missing HSTS")
    assert result["key_findings"] == ["No HSTS header present"]
    assert result["recommended_actions"] == ["Enable HSTS with preload"]

    meta = result["_meta"]
    assert meta["model"] == "claude-sonnet-4-6"
    assert meta["tokens_in"] == 100
    assert meta["tokens_out"] == 200
    assert meta["latency_ms"] == 42
    assert meta["prompt_name"] == "exec_summary_v1"
    assert meta["prompt_version"] == 1


def test_generate_ai_summary_passes_schema_to_adapter():
    adapter = _MockAdapter(_good_response_text())
    generate_ai_summary(adapter, _sample_report_data())

    schema = adapter.last_call["response_schema"]
    assert schema["type"] == "object"
    assert "headline" in schema["properties"]
    assert "narrative" in schema["properties"]
    assert "headline" in schema["required"]


def test_generate_ai_summary_renders_target_into_prompt():
    adapter = _MockAdapter(_good_response_text())
    generate_ai_summary(adapter, _sample_report_data())
    assert "example.com" in adapter.last_call["prompt"]


def test_generate_ai_summary_invalid_json_raises():
    adapter = _MockAdapter("not actually json")
    with pytest.raises(AIGenerationError, match="not valid JSON"):
        generate_ai_summary(adapter, _sample_report_data())


def test_generate_ai_summary_missing_headline_raises():
    adapter = _MockAdapter(json.dumps({"narrative": "n"}))
    with pytest.raises(AIGenerationError, match="missing required field"):
        generate_ai_summary(adapter, _sample_report_data())


def test_generate_ai_summary_empty_headline_raises():
    adapter = _MockAdapter(json.dumps({"headline": "  ", "narrative": "n"}))
    with pytest.raises(AIGenerationError, match="missing required field"):
        generate_ai_summary(adapter, _sample_report_data())


def test_generate_ai_summary_findings_must_be_list():
    bad = json.dumps({
        "headline": "h", "narrative": "n",
        "key_findings": "should be a list",
    })
    adapter = _MockAdapter(bad)
    with pytest.raises(AIGenerationError, match="must be a list"):
        generate_ai_summary(adapter, _sample_report_data())


def test_build_context_caps_top_issues():
    rd = {
        "target": "x",
        "all_issues": [{"id": f"X{i}", "display_name": f"x{i}",
                        "severity": "Low", "category": "C",
                        "reported_by": "p", "description": "d"}
                       for i in range(50)],
        "plugin_executive_summaries": [],
        "scan_metadata": {"total_issues": 50, "severity_counts": {},
                          "waf_statistics": {}},
    }
    ctx = _build_context(rd)
    assert len(ctx["top_issues"]) == 10


def test_build_context_handles_missing_keys():
    """Doesn't blow up if scan_metadata or fields are absent."""
    ctx = _build_context({"target": "y"})
    assert ctx["target"] == "y"
    assert ctx["total_issues"] == 0
    assert ctx["severity_counts"] == {}
    assert ctx["top_issues"] == []
    assert ctx["plugin_summaries"] == []
    assert ctx["waf_stats"] == {}
