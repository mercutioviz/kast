# Copilot / AI Agent Instructions for KAST

This file gives focused, actionable context so an AI coding agent can be productive immediately.

Summary
- KAST is a small Python CLI that orchestrates per-tool "plugins" to scan a target and produce JSON + HTML reports.
- Key flow: `main.py` (CLI) -> `ScannerOrchestrator` (`orchestrator.py`) -> plugins (`plugins/*_plugin.py`) -> post-process -> `report_builder.py` (Jinja2 HTML).

Quick run examples
- Run a normal (sequential) passive scan: `python3 main.py --target example.com`
- Run in parallel and verbose: `python3 main.py --target example.com --parallel --verbose`
- Dry-run (no external tools executed): add `--dry-run`.
- Generate report-only from existing output JSON dir: `python3 main.py --report-only /path/to/output_dir`

Architecture notes (why things are structured this way)
- Plugin model: each tool is encapsulated as a class inheriting `KastPlugin` (`plugins/base.py`). This decouples orchestration from tool specifics and makes adding tools a single-file job.
- Orchestration: `ScannerOrchestrator` loads plugin classes and runs them either sequentially or with `ThreadPoolExecutor` when `--parallel` is used.
- Post-processing: each plugin is responsible for normalizing/writing a processed JSON file named `<plugin-name>_processed.json` into the output dir. Reports are generated from those results.

Plugin contract (must-follow rules you can infer from code)
- Subclass `KastPlugin` and implement at least: `run(self, target, output_dir, report_only)`, `is_available(self)`, and `post_process(self, raw_output, output_dir)`.
- Provide class attributes: `priority` (int, lower == run earlier), `scan_type` (`"passive"` or `"active"`), and `output_type` (`"stdout"` or `"file"`).
- Use `get_result_dict(disposition, results, timestamp=None)` to return standardized results (fields: `name`, `timestamp`, `disposition`, `results`).
- If a plugin writes a processed JSON, name it `<plugin_name>_processed.json` in `output_dir` (convention used by existing plugins).

Discovery & loading
- `kast.utils.discover_plugins(log)` scans `plugins` for files ending with `_plugin.py` and imports classes which have `run` and `is_available` methods. It sorts by `priority`.

Data flows & artifacts
- Raw execution: plugin `run()` may call external tools (e.g., `wafw00f`, `mdn-http-observatory-scan`) and return a result dict.
- Post-processing: plugin `post_process()` normalizes and writes processed JSON and returns its path.
- Final report: `report_builder.generate_html_report()` expects a list of plugin result dicts and uses `templates/report_template.html` + `data/issue_registry.json` (lookups in `report_templates.py`).

Conventions & patterns to respect
- Use `self.debug(msg)` from `KastPlugin` for verbose debug logging (prints only when `--verbose` is passed).
- Use `shutil.which()` in `is_available()` implementations to check external tool presence.
- Prefer returning structured dicts (not raw strings) from `run()` when possible.

Files to inspect when changing behavior
- `main.py` (CLI parsing, args semantics: `--target`, `--parallel`, `--dry-run`, `--report-only`, `--mode`, `--verbose`)
- `orchestrator.py` (plugin execution model and error handling)
- `plugins/base.py` (plugin API contract)
- `plugins/*_plugin.py` (examples: `wafw00f_plugin.py`, `observatory_plugin.py`)
- `utils.py` (plugin discovery & import behavior)
- `report_builder.py`, `report_templates.py`, `templates/report_template.html`, `data/issue_registry.json`

Developer workflows & quick tips
- To avoid executing external tools when testing changes, use `--dry-run` or `--report-only`.
- To add a plugin: create `plugins/<name>_plugin.py`, subclass `KastPlugin`, set `priority` and implement required methods. Keep side-effects inside `run()` and write processed JSON in `post_process()`.

If anything in this file is unclear or missing examples you'd like added (e.g., more plugin templates or exact JSON shapes), tell me which section to expand and I'll iterate.
