"""Tests for the AI prompt eval harness (Phase C12).

Three layers:
1. Unit tests for individual criterion functions — verify pass/fail logic.
2. Runner tests — verify run_eval and run_golden_eval orchestration using a
   mocked adapter (no real API calls).
3. Golden file regression tests — run_golden_eval over every scenario in
   SCENARIOS_DIR and confirm the stored golden files pass all criteria.
   If a golden file is missing or hand-edited to break a criterion, this fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kast.ai import AIResponse
from kast.ai.evals.criteria import (
    CriterionResult,
    check_headline_length,
    check_headline_not_generic,
    check_key_findings_count,
    check_narrative_length,
    check_no_forbidden_phrases,
    check_recommended_actions_count,
    check_schema,
    check_target_mentioned,
)
from kast.ai.evals.runner import (
    GOLDEN_DIR,
    SCENARIOS_DIR,
    EvalScenario,
    load_scenario,
    run_eval,
    run_golden_eval,
    write_golden,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_output(**overrides):
    base = {
        "headline": "Deprecated TLS and missing headers expose example.com to interception.",
        "narrative": (
            "The scan found several transport security issues on example.com.\n\n"
            "TLS 1.0 is active and should be disabled. The missing X-Frame-Options "
            "header leaves the site open to clickjacking."
        ),
        "key_findings": [
            "TLS 1.0 is enabled and vulnerable to POODLE/BEAST.",
            "X-Frame-Options header absent — clickjacking risk.",
            "75% of findings are WAF-addressable.",
        ],
        "recommended_actions": [
            "Disable TLS 1.0/1.1 and enforce TLS 1.2 minimum.",
            "Add X-Frame-Options: SAMEORIGIN to all responses.",
        ],
    }
    base.update(overrides)
    return base


def _make_adapter(output_dict):
    """Return a minimal mock that looks like an AIAdapter."""
    adapter = MagicMock()
    adapter.generate.return_value = AIResponse(
        text=json.dumps(output_dict),
        tokens_in=100,
        tokens_out=200,
        model="claude-sonnet-4-6",
        latency_ms=42,
        raw_response=None,
    )
    return adapter


def _minimal_report_data(target="example.com"):
    return {
        "target": target,
        "all_issues": [],
        "scan_metadata": {
            "total_issues": 0,
            "severity_counts": {"High": 0, "Medium": 0, "Low": 0, "Informational": 0, "Unknown": 0},
            "waf_statistics": {
                "total_issues": 0, "waf_addressable_count": 0,
                "waf_addressable_percentage": 0.0, "non_waf_count": 0,
                "high_severity_waf": 0, "medium_severity_waf": 0, "low_severity_waf": 0,
            },
        },
        "plugin_executive_summaries": [],
    }


# ---------------------------------------------------------------------------
# CriterionResult basics
# ---------------------------------------------------------------------------


def test_criterion_result_bool_true():
    assert CriterionResult("x", True, "ok")


def test_criterion_result_bool_false():
    assert not CriterionResult("x", False, "fail")


# ---------------------------------------------------------------------------
# check_schema
# ---------------------------------------------------------------------------


def test_check_schema_valid():
    result = check_schema(_make_valid_output())
    assert result.passed


def test_check_schema_missing_headline():
    out = _make_valid_output()
    del out["headline"]
    result = check_schema(out)
    assert not result.passed
    assert "headline" in result.message


def test_check_schema_empty_narrative():
    result = check_schema(_make_valid_output(narrative="   "))
    assert not result.passed


def test_check_schema_key_findings_not_list():
    result = check_schema(_make_valid_output(key_findings="not a list"))
    assert not result.passed


# ---------------------------------------------------------------------------
# check_headline_length
# ---------------------------------------------------------------------------


def test_headline_length_within_limit():
    result = check_headline_length(_make_valid_output())
    assert result.passed


def test_headline_length_exactly_at_limit():
    out = _make_valid_output(headline="A" * 240)
    result = check_headline_length(out)
    assert result.passed


def test_headline_length_over_limit():
    out = _make_valid_output(headline="A" * 241)
    result = check_headline_length(out)
    assert not result.passed
    assert "241" in result.message


# ---------------------------------------------------------------------------
# check_headline_not_generic
# ---------------------------------------------------------------------------


def test_headline_not_generic_passes_normal():
    result = check_headline_not_generic(_make_valid_output())
    assert result.passed


@pytest.mark.parametrize("generic", ["", "n/a", "executive summary", "security scan results"])
def test_headline_not_generic_fails_on_placeholder(generic):
    result = check_headline_not_generic(_make_valid_output(headline=generic))
    assert not result.passed


# ---------------------------------------------------------------------------
# check_narrative_length
# ---------------------------------------------------------------------------


def test_narrative_length_passes():
    result = check_narrative_length(_make_valid_output())
    assert result.passed


def test_narrative_length_fails_on_stub():
    result = check_narrative_length(_make_valid_output(narrative="Short."))
    assert not result.passed


# ---------------------------------------------------------------------------
# check_key_findings_count
# ---------------------------------------------------------------------------


def test_key_findings_count_passes():
    assert check_key_findings_count(_make_valid_output()).passed


def test_key_findings_count_fails_too_few():
    result = check_key_findings_count(_make_valid_output(key_findings=["one"]), min_count=2)
    assert not result.passed


def test_key_findings_count_fails_too_many():
    result = check_key_findings_count(_make_valid_output(key_findings=["x"] * 9), max_count=8)
    assert not result.passed


# ---------------------------------------------------------------------------
# check_recommended_actions_count
# ---------------------------------------------------------------------------


def test_recommended_actions_passes():
    assert check_recommended_actions_count(_make_valid_output()).passed


def test_recommended_actions_fails_empty():
    result = check_recommended_actions_count(_make_valid_output(recommended_actions=[]), min_count=1)
    assert not result.passed


# ---------------------------------------------------------------------------
# check_target_mentioned
# ---------------------------------------------------------------------------


def test_target_mentioned_passes(tmp_path):
    context = _minimal_report_data("example.com")
    result = check_target_mentioned(_make_valid_output(), context=context)
    assert result.passed, result.message


def test_target_mentioned_fails_when_absent(tmp_path):
    context = _minimal_report_data("myspecialsite.example.org")
    result = check_target_mentioned(_make_valid_output(), context=context)
    assert not result.passed


def test_target_mentioned_skipped_when_no_context():
    result = check_target_mentioned(_make_valid_output(), context=None)
    assert result.passed  # skipped, not a failure


# ---------------------------------------------------------------------------
# check_no_forbidden_phrases
# ---------------------------------------------------------------------------


def test_no_forbidden_phrases_passes():
    assert check_no_forbidden_phrases(_make_valid_output()).passed


@pytest.mark.parametrize("phrase", ["various security issues", "best practices", "world-class"])
def test_no_forbidden_phrases_fails(phrase):
    out = _make_valid_output(narrative=f"The site has {phrase} that need attention.")
    result = check_no_forbidden_phrases(out)
    assert not result.passed


# ---------------------------------------------------------------------------
# run_eval with mocked adapter
# ---------------------------------------------------------------------------


def test_run_eval_passes_on_valid_output():
    scenario = EvalScenario(
        name="test",
        report_data=_minimal_report_data("example.com"),
    )
    adapter = _make_adapter(_make_valid_output())
    result = run_eval(scenario, adapter)
    assert result.passed, result.summary()


def test_run_eval_fails_on_bad_schema():
    # generate_ai_summary._validate_schema raises AIGenerationError for a
    # missing required field before eval criteria are applied; the eval result
    # should still reflect failure.
    scenario = EvalScenario(
        name="test",
        report_data=_minimal_report_data("example.com"),
    )
    adapter = _make_adapter({"narrative": "ok"})  # missing headline
    result = run_eval(scenario, adapter)
    assert not result.passed
    # The error is surfaced as result.error (AIGenerationError path)
    assert result.error is not None
    assert "headline" in result.error.lower()


def test_run_eval_records_output():
    scenario = EvalScenario(name="test", report_data=_minimal_report_data())
    out = _make_valid_output()
    adapter = _make_adapter(out)
    result = run_eval(scenario, adapter)
    assert result.output is not None
    assert result.output.get("headline") == out["headline"]


def test_run_eval_captures_generation_error():
    from kast.ai.base import AIGenerationError
    scenario = EvalScenario(name="test", report_data=_minimal_report_data())
    adapter = MagicMock()
    adapter.generate.side_effect = AIGenerationError("API unavailable")
    result = run_eval(scenario, adapter)
    assert not result.passed
    assert result.error is not None
    assert "API unavailable" in result.error


# ---------------------------------------------------------------------------
# run_golden_eval
# ---------------------------------------------------------------------------


def test_run_golden_eval_passes_on_valid_golden(tmp_path):
    golden = _make_valid_output()
    golden_file = tmp_path / "test.json"
    golden_file.write_text(json.dumps(golden))
    scenario = EvalScenario(
        name="test",
        report_data=_minimal_report_data("example.com"),
        golden_path=golden_file,
    )
    result = run_golden_eval(scenario)
    assert result.passed, result.summary()


def test_run_golden_eval_fails_on_missing_golden():
    scenario = EvalScenario(
        name="test",
        report_data=_minimal_report_data(),
        golden_path=Path("/nonexistent/golden.json"),
    )
    result = run_golden_eval(scenario)
    assert not result.passed
    assert result.error is not None


def test_run_golden_eval_fails_on_corrupt_golden(tmp_path):
    golden_file = tmp_path / "bad.json"
    golden_file.write_text('{"headline": ""}')  # empty headline fails schema
    scenario = EvalScenario(
        name="bad",
        report_data=_minimal_report_data(),
        golden_path=golden_file,
    )
    result = run_golden_eval(scenario)
    assert not result.passed


# ---------------------------------------------------------------------------
# write_golden
# ---------------------------------------------------------------------------


def test_write_golden_round_trips(tmp_path):
    out = _make_valid_output()
    # Simulate a result with _meta (should be stripped on write)
    out["_meta"] = {"tokens_in": 1, "model": "test"}
    scenario = EvalScenario(name="test", report_data=_minimal_report_data())
    adapter = _make_adapter(out)
    eval_result = run_eval(scenario, adapter)

    golden_path = tmp_path / "golden.json"
    write_golden(eval_result, golden_path)
    written = json.loads(golden_path.read_text())
    assert "_meta" not in written
    assert "headline" in written


# ---------------------------------------------------------------------------
# load_scenario
# ---------------------------------------------------------------------------


def test_load_scenario_baseline(tmp_path):
    scenario_path = SCENARIOS_DIR / "baseline_scan.yaml"
    scenario = load_scenario(scenario_path, golden_dir=GOLDEN_DIR)
    assert scenario.name == "baseline_scan"
    assert scenario.report_data["target"] == "example.com"
    assert len(scenario.report_data["all_issues"]) > 0
    assert scenario.golden_path is not None and scenario.golden_path.is_file()


def test_load_scenario_clean(tmp_path):
    scenario_path = SCENARIOS_DIR / "clean_scan.yaml"
    scenario = load_scenario(scenario_path, golden_dir=GOLDEN_DIR)
    assert scenario.name == "clean_scan"
    assert scenario.golden_path is not None and scenario.golden_path.is_file()


# ---------------------------------------------------------------------------
# Golden regression tests — all scenarios in SCENARIOS_DIR must pass
# ---------------------------------------------------------------------------


def _all_scenario_paths():
    return list(SCENARIOS_DIR.glob("*.yaml")) if SCENARIOS_DIR.is_dir() else []


@pytest.mark.parametrize("scenario_path", _all_scenario_paths(),
                         ids=lambda p: p.stem)
def test_golden_passes_criteria(scenario_path):
    """Every golden file must pass all standard criteria.

    This is the regression guard: if you modify a golden file by hand and
    break a quality criterion, this test fails and forces you to fix it or
    update the criterion intentionally.
    """
    scenario = load_scenario(scenario_path, golden_dir=GOLDEN_DIR)
    assert scenario.golden_path is not None, (
        f"No golden file found for scenario '{scenario.name}'. "
        f"Expected: {GOLDEN_DIR / scenario_path.stem}.json"
    )
    result = run_golden_eval(scenario)
    assert result.passed, (
        f"Golden file for '{scenario.name}' failed criteria:\n{result.summary()}"
    )


@pytest.mark.parametrize("scenario_path", _all_scenario_paths(),
                         ids=lambda p: p.stem)
def test_eval_with_golden_as_adapter_response(scenario_path):
    """Mocked adapter returns the golden output; the eval must pass.

    This verifies the golden → adapter → run_eval round-trip works end-to-end.
    If the golden file passes run_golden_eval but fails run_eval, something is
    wrong with how the adapter response is threaded through generate_ai_summary.
    """
    scenario = load_scenario(scenario_path, golden_dir=GOLDEN_DIR)
    assert scenario.golden_path is not None
    golden = json.loads(scenario.golden_path.read_text())
    adapter = _make_adapter(golden)
    result = run_eval(scenario, adapter)
    assert result.passed, (
        f"run_eval failed for '{scenario.name}' even though golden passes criteria:\n"
        f"{result.summary()}"
    )


def test_eval_result_summary_format():
    """EvalResult.summary() produces readable multi-line output."""
    scenario = EvalScenario(name="fmt_test", report_data=_minimal_report_data("example.com"))
    adapter = _make_adapter(_make_valid_output())
    result = run_eval(scenario, adapter)
    summary = result.summary()
    assert "fmt_test" in summary
    assert "PASS" in summary or "FAIL" in summary
    assert "\n" in summary  # multi-line


def test_failed_criteria_property():
    # Use an output that passes JSON-schema validation (headline present) but
    # fails criteria (headline over the char limit) so failed_criteria is set.
    scenario = EvalScenario(name="test", report_data=_minimal_report_data())
    adapter = _make_adapter(_make_valid_output(headline="A" * 300))
    result = run_eval(scenario, adapter)
    assert not result.passed
    assert len(result.failed_criteria) > 0
    for fc in result.failed_criteria:
        assert not fc.passed
