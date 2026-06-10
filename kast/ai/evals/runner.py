"""Eval scenario runner for AI executive summary prompts.

Two execution modes:
- ``run_eval(scenario, adapter)``   — calls a real or mocked adapter, checks criteria
- ``run_golden_eval(scenario)``     — validates the stored golden JSON without any API call

Golden files live next to scenario YAML files under ``golden/<scenario_name>.json``.
To refresh a golden file after intentionally changing the prompt, run with a real
adapter, inspect the output, and if it looks good write it to the golden path.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from kast.ai.base import AIAdapter, AIGenerationError
from kast.ai.evals.criteria import STANDARD_CRITERIA, CriterionResult
from kast.ai.summary import generate_ai_summary

EVALS_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = EVALS_DIR / "scenarios"
GOLDEN_DIR = EVALS_DIR / "golden"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EvalScenario:
    name: str
    report_data: dict
    criteria: list[Callable] = field(default_factory=lambda: list(STANDARD_CRITERIA))
    golden_path: Path | None = None


@dataclass
class EvalResult:
    scenario_name: str
    passed: bool
    criterion_results: list[CriterionResult]
    output: dict | None = None
    error: str | None = None

    @property
    def failed_criteria(self) -> list[CriterionResult]:
        return [r for r in self.criterion_results if not r.passed]

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"[{status}] {self.scenario_name}"]
        for r in self.criterion_results:
            mark = "+" if r.passed else "x"
            lines.append(f"  [{mark}] {r.name}: {r.message}")
        if self.error:
            lines.append(f"  [!] error: {self.error}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_scenario(path: Path, golden_dir: Path | None = None) -> EvalScenario:
    """Load a scenario from a YAML file.

    The YAML must have a ``report_data`` key whose structure matches the dict
    that ``collect_report_data`` returns (target, all_issues, scan_metadata,
    plugin_executive_summaries).  A ``name`` key is optional; the filename stem
    is used as a fallback.
    """
    data = yaml.safe_load(Path(path).read_text())
    name = data.get("name", Path(path).stem)

    if golden_dir is None:
        golden_dir = GOLDEN_DIR
    golden_path = Path(golden_dir) / f"{Path(path).stem}.json"
    if not golden_path.is_file():
        golden_path = None

    return EvalScenario(
        name=name,
        report_data=data["report_data"],
        golden_path=golden_path,
    )


def run_eval(
    scenario: EvalScenario,
    adapter: AIAdapter,
    prompt_name: str = "exec_summary_v1",
) -> EvalResult:
    """Run a scenario against a live (or mocked) adapter and check criteria."""
    try:
        output = generate_ai_summary(adapter, scenario.report_data, prompt_name=prompt_name)
    except AIGenerationError as e:
        return EvalResult(scenario.name, False, [], output=None, error=str(e))

    criterion_results = _apply_criteria(output, scenario)
    passed = all(r.passed for r in criterion_results)
    return EvalResult(scenario.name, passed, criterion_results, output=output)


def run_golden_eval(scenario: EvalScenario) -> EvalResult:
    """Validate the stored golden output against criteria — no API call needed.

    Useful in CI to pin structural quality requirements on pre-approved golden
    files: if a golden file drifts (e.g. someone hand-edits it badly), this
    will catch it.  Also useful to ensure the criteria themselves are sensible.
    """
    if scenario.golden_path is None or not Path(scenario.golden_path).is_file():
        return EvalResult(
            scenario.name, False, [],
            error=f"Golden file missing: {scenario.golden_path}",
        )
    golden = json.loads(Path(scenario.golden_path).read_text())
    criterion_results = _apply_criteria(golden, scenario)
    passed = all(r.passed for r in criterion_results)
    return EvalResult(scenario.name, passed, criterion_results, output=golden)


def write_golden(result: EvalResult, path: Path) -> None:
    """Persist a live eval's output as the new golden for this scenario.

    Call this manually after a successful live eval to refresh the golden file.
    """
    if result.output is None:
        raise ValueError("Cannot write golden from a failed eval with no output")
    output = {k: v for k, v in result.output.items() if not k.startswith("_")}
    Path(path).write_text(json.dumps(output, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_criteria(output: dict, scenario: EvalScenario) -> list[CriterionResult]:
    results = []
    for fn in scenario.criteria:
        import inspect
        sig = inspect.signature(fn)
        if "context" in sig.parameters:
            results.append(fn(output, context=scenario.report_data))
        else:
            results.append(fn(output))
    return results
