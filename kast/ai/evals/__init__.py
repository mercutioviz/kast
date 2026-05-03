"""AI prompt eval harness — criteria, runner, and golden-output fixtures.

Usage (no API key needed — just validates golden files):
    from kast.ai.evals.runner import load_scenario, run_golden_eval, SCENARIOS_DIR, GOLDEN_DIR
    for path in SCENARIOS_DIR.glob("*.yaml"):
        scenario = load_scenario(path, golden_dir=GOLDEN_DIR)
        result = run_golden_eval(scenario)
        print(result.summary())

Usage with a real or mocked adapter:
    from kast.ai.evals.runner import load_scenario, run_eval
    result = run_eval(scenario, adapter)
"""
