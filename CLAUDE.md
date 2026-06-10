# kast / kast-web — Active Context for AI Assistants

This file is auto-loaded by Claude Code on every session in this repo. It is the source of truth for project context, active patterns, and authoring rules.

## Project at a glance

kast is Barracuda's "ETS for web apps" — a Solutions Architect's tool for generating digestible web-application security reports that drive WAF/WaaS sales conversations with prospects. **The audience is internal Barracuda SAs and partner sales engineers, not the broad security community**, even though the README frames it that way.

kast-web (at `/home/mscollins/kast-web/`, a separate repo) is the Flask + Celery + Redis web frontend that shells out to the kast CLI installed at `/usr/local/bin/kast`.

**Reliability and reputational safety are first-class concerns.** An SA cannot run a flaky tool in front of a prospect. Active scans must never look like attacks against the prospect's infrastructure.

Current line: kast `v3.0.20` on `main`; kast-web on its `v2.0` line. v3 shipped via the refactor documented in `docs/v3-planning/01-audit.md` through `04-kast-web-cloud-migration.md` — design history, not active work.

## Frozen contracts

Do not change these surfaces without explicit, coordinated planning:

- **The kast↔kast-web contract** documented in `docs/web-integration.md`. Atomic writes (`.tmp` + `rename(2)`), frozen filenames (`{plugin}.json`, `{plugin}_processed.json`), file-presence state machine, `zap_scan_progress.json` channel.
- **The v2 CLI argv contract** (the `kast --target X --mode passive ...` shape). Preserved via the `_translate_v2_argv()` wrapper.
- **The `_processed.json` per-plugin output format**, including its kebab-case keys (`plugin-name`, `plugin-display-name`, `plugin-website-url`, etc.).
- **The issue registry data format** in `kast/data/issue_registry.json`.

Internal refactoring is free as long as these surfaces stay stable.

## Architecture and patterns

- **Severity enum at `kast/core/severity.py`.** Use `Severity.HIGH | MEDIUM | LOW | INFORMATIONAL | UNKNOWN`; never write bare severity strings. The registry stores `"Informational"`; `Severity.from_registry(value)` normalizes the legacy `"Info"` and the `"Issue ID not found."` sentinel. `severity_counts` dicts and templates key on `"Informational"`. The badge label is rendered as "Info" for brevity — display-only, not a data value.

- **PluginRegistry at `kast/registry.py`.** Single source of truth for plugin discovery, instantiation, and lookup. Construct one per kast invocation: `registry = PluginRegistry(logger, cli_args=args, config_manager=cm)`. Use `discover()` for classes, `all_instances()` for cached instances (priority-sorted), `get(name)` for one, `filter_by_mode(mode)` for instances filtered by `scan_type`. `ScannerOrchestrator` takes a list of plugin **instances** (not classes); `kast/utils.py:show_dependency_tree(registry, scan_mode, log)` takes a registry.

- **ExternalToolPlugin base at `kast/plugins/external_tool.py`.** Tool wrappers inherit from this. Subclass declares `tool_binary` (drives auto `is_available()`), `output_filename`, `output_format` (`"json"` or `"text"`) as class attributes; provides `build_command(target, output_path)` and `count_findings(findings)` as required hooks; optionally overrides `parse_findings`, `extract_issues`, `format_summary`, `format_details`, `format_executive_summary`, `extra_processed_fields`. The base handles subprocess invocation, timeout, return-code checks, missing-output detection, raw-output reading, atomic writes via `write_json_atomic`, and processed-dict assembly. Reference migrations: `whatweb_plugin.py` (standard shape) and `wafw00f_plugin.py` (overrides `run()` for the HTTPS→HTTP TLS-error retry quirk). Two gotchas: (1) `kast/utils.py:discover_plugins` filters `obj.__module__ != module_name` so the imported `ExternalToolPlugin` symbol isn't itself discovered as a plugin; (2) wafw00f's raw output is a top-level list — its `parse_findings` rewraps into `{name, timestamp, disposition, results}` so `report/data.py` keeps working.

- **Class-attribute identity and schemas.** Plugin identity (`name`, `display_name`, `description`, `website_url`, `scan_type`, `output_type`) is declared as **class attributes**, not set in `__init__`. The schema-registration footgun ("set self.name BEFORE super().__init__()") is gone. `ConfigManager.collect_schemas_from_classes(plugin_classes)` registers every plugin's schema without instantiation (used by `kast config schema`, `kast config init`, `kast config show`). All plugins use the canonical `__init__(self, cli_args, config_manager=None)` signature. Plugin classes must declare `name` and `config_schema` as class attributes.

- **Atomic JSON writes via `kast/core/atomic.py`.** All state-bearing writes go through `write_json_atomic(path, data, **dump_kwargs)`. The helper writes to `<path>.tmp` and `os.replace`s into place — POSIX rename(2) is atomic, so kast-web watchers never observe a partial file. **Don't introduce raw `json.dump(...)` calls for `*_processed.json`, `zap_scan_progress.json`, `kast_info.json`, or `missing_issue_ids.json`** — they violate the contract in `docs/web-integration.md`. The helper accepts json.dump kwargs (e.g., `default=str` for non-serializable values).

- **Unified report pipeline at `kast/report/`.** `collect_report_data(plugin_results, target) -> dict`, then `render_html(data, output_path, logo_path)` or `render_pdf(data, output_path, logo_path)`. Both renderers consume the SAME data structure; differences are template selection, JSON pre-rendering (PDF), CSS placement (HTML copies, PDF embeds), logo embedding (PDF base64, HTML filename ref), and exec-summary anchor links (HTML only). **Never reintroduce parallel HTML/PDF data-prep paths** — extract new shared work into `collect_report_data`. Helpers (`format_multiline_text`, `format_json_for_pdf`, `infer_issue_metadata`, etc.) live in `kast/report/helpers.py`. One-shot ergonomic entrypoints `generate_html_report` and `generate_pdf_report` are exposed from `kast.report` for callers that want collect-and-render in one call.

- **CSS-based long-string wrapping.** Long URLs and other strings wrap via `overflow-wrap: anywhere` on `.report-paragraph`, `.json-string`, `.json-key`, `.issue-description`, `td`, etc., in `kast_style.css` and `kast_style_pdf.css`. **Don't reintroduce `<wbr>` injection in Python.** New sections needing aggressive wrapping go in the comment-block at the bottom of `kast_style_pdf.css`. WeasyPrint accepts `overflow-wrap: anywhere` but rejects `word-break: break-word` (non-standard CSS); use `word-break: break-all` for extra-aggressive PDF breaking.

- **Jinja macros at `templates/_macros.html`.** Both report templates do `{% import "_macros.html" as kast %}`. Currently one macro: `kast.tool_anchor(name)` for anchor-ID generation. Add new macros only when the same logic is duplicated across HTML and PDF templates. `templates/partials/` exists for shared template blocks; see its README for criteria. The two templates have legitimately different layouts (HTML interactive nav, PDF cover page); aggressive template inheritance is not pursued without golden-output diff coverage.

- **CLI dispatch in `kast/cli/`.** Click-based dispatcher at `kast/cli/main.py`. Subcommands live in their own modules: `scan.py` (the `scan` group + `list/show/rerun`), `plugins.py` (`list/show/deps`), `doctor.py`, `registry.py` (`list/add/promote`). `kast/cli/__init__.py` holds `_translate_v2_argv()` which maps legacy v2 invocations to the v3 subcommand form before Click parses them — preserving the kast↔kast-web argv contract. `kast/cli/_shared.py` holds cross-module helpers. **`kast/main.py` is a 13-line shim that delegates to `kast.cli.main()`.** When adding a new subcommand, create a module under `kast/cli/`, define the Click group/command there, and `add_command` it from `cli/main.py`. Do NOT reintroduce argparse logic in `kast/main.py`. `--zap-profile` paths resolve relative to the kast package directory, not the cwd.

- **AI adapter abstraction at `kast/ai/`.** `kast.ai.base` defines the `AIAdapter` Protocol and `AIResponse` dataclass. `kast.ai.anthropic_adapter` is the default implementation (default model `claude-sonnet-4-6`; uses Anthropic SDK 0.97's `output_config={"format": {"type": "json_schema", "schema": ...}}` for structured output). `kast.ai.http_adapter.HttpAdapter` routes requests through the kast-web AI service via `POST <url>/api/ai/generate`. `kast.ai.config.get_ai_adapter` resolves credentials: `endpoint_url` kwarg / `KAST_AI_ENDPOINT` env → `HttpAdapter`; otherwise `KAST_AI_API_KEY` / `~/.config/kast/ai.yaml` → `AnthropicAdapter`. Optional bearer token via `KAST_AI_ENDPOINT_TOKEN`. `kast.ai.prompts.load_prompt(name)` parses YAML frontmatter + `## System` / `## User` sections from `kast/ai/prompts/<name>.md`; the user section is a Jinja2 template the caller renders. `kast.ai.summary.generate_ai_summary(adapter, report_data)` orchestrates: builds context from `collect_report_data`'s output, renders the prompt, calls the adapter with `EXEC_SUMMARY_SCHEMA`, parses+validates the response, returns `{headline, narrative, key_findings, recommended_actions, _meta}`.

  **Failure mode is "banner + deterministic fallback":** if `--ai-summary` is set but the call fails, `_run_scan` catches the exception, sets `ai_error`, and the report renders the deterministic exec summary plus a banner. Templates render the AI block (`.ai-summary` div) only when `ai_summary` is present; absent, the `Identified Issues` section + `executive_summary` text are shown. `kast_info.json` carries an `ai` block (`enabled / status / adapter / model / prompt_version / tokens_in / tokens_out / latency_ms / error / endpoint`). The `anthropic` SDK is a **required** install-time dependency even though `--ai-summary` is opt-in at runtime — keeps imports unconditional.

- **TCO appendix at `kast/report/tco.py`.** `compute_tco(all_issues)` reads `code_fix_timeframe` and `waf_deployment_timeframe` from the issue registry and returns a `tco` dict with per-issue rows + aggregated totals. `collect_report_data` calls it and includes `"tco"` in the returned dict. Both HTML and PDF templates render the appendix via `kast/templates/partials/tco_appendix.html` when `tco.has_data` is true. `parse_timeframe` / `format_days` handle string-to-day-range round-tripping.

- **AI Surface Detection plugin at `kast/plugins/ai_surface_detection_plugin.py`.** Plugin name `ai_surface_detection`. Covers chatbots/virtual agents (`AI_CHATBOT_SCRIPT_PATTERNS` + `AI_CHATBOT_URL_PATTERNS` + `WHATWEB_CHAT_INDICATORS`) **and** AI semantic search / RAG platforms (`AI_SEARCH_RAG_SCRIPT_PATTERNS` + `AI_SEARCH_RAG_URL_PATTERNS` + `WHATWEB_SEARCH_INDICATORS`). Each detection carries a `detection_type` field (`"chatbot"` or `"ai_search"`). `post_process` emits `AI-CHATBOT-001`/`AI-CHATBOT-002` for chatbots and `AI-SEARCH-001` for search/RAG. The plugin replaced the old `ai_chatbot_detection_plugin.py`; the old name is gone everywhere.

- **AI prompt eval harness at `kast/ai/evals/`.** `kast.ai.evals.criteria` provides 8 quality criterion functions (`check_schema`, `check_headline_length`, `check_headline_not_generic`, `check_narrative_length`, `check_key_findings_count`, `check_recommended_actions_count`, `check_target_mentioned`, `check_no_forbidden_phrases`), each returning `CriterionResult`. `kast.ai.evals.runner` provides `EvalScenario` / `EvalResult` dataclasses and two run modes: `run_eval(scenario, adapter)` (live/mocked API) and `run_golden_eval(scenario)` (validates stored golden file, no API call). Scenarios live at `kast/ai/evals/scenarios/*.yaml`; golden outputs at `kast/ai/evals/golden/*.json`. The parametrized `test_golden_passes_criteria` in `test_ai_evals.py` automatically picks up new scenarios.

- **Cloud ZAP lives in kast-web, not kast.** The kast CLI sees only local and remote ZAP modes; the cloud subsystem (Terraform, providers, SSH executor, infrastructure scripts) moved to `kast-web/app/cloud/`. kast-web's `execute_scan_task` calls `cloud_provision_task` (provisions the ZAP instance), captures the resulting URL + API key, then spawns the kast CLI with `--set zap.execution_mode=remote --set zap.remote.url=... --set zap.remote.api_key=...`. `kast/scripts/zap_providers.py` retains `LocalZapProvider` and `RemoteZapProvider`; `kast/plugins/zap_plugin.py` imports them directly and dispatches inline. Migration guide for v2.x cloud users: `kast-web/docs/MIGRATION_FROM_KAST_CLOUD.md`.

## Open threads

Loose ends from the v3.0 ship — tracked but not blocking active work:

- **kast-web AI service (C8–C11).** The kast side of the AI hook landed (`--ai-endpoint URL` flag + `HttpAdapter`), but the kast-web service itself — cost gating, admin UI, DB migration — has not been built. Done in a kast-web session.
- **kast-web plugin-discovery migration.** kast-web still parses `kast -ls` text output (`/home/mscollins/kast-web/app/routes/admin.py:634`). The v3-native endpoint is `kast plugins list --json`. Migrate when convenient.
- **F2 "Why Barracuda" WAF feature map (C6).** Deferred until other v3 work shipped. Now unblocked but waiting on Barracuda product-marketing content.
- **Test sys.path hygiene.** ~12 test files still have hardcoded `sys.path.insert(0, '/opt/kast')` (or similar) plus a couple of bare imports that work only by side-effect. Tests pass today because the dev venv has `pip install -e .` and pytest's collection happens to import in the right order. Worth a mechanical cleanup pass to remove the hacks and rely on the proper package install.
- **18 ruff findings remain.** After the v3.0.21 baseline pass: 7 `F401` unused-import (some may be intentional re-exports), 3 `B904` raise-without-from, 3 `E722` bare-except, plus minor `B005/B007/B027/UP035`. None are bugs; all are judgment calls. Decide per finding when next touching the file.

## v3.1 backlog

Deferred capability candidates live in `docs/v3.1-backlog.md`. Reference that file when prioritizing v3.1 work.

## Working in this codebase

- **Run tests:** `python -m pytest kast/tests/`
- **Plugin discovery:** plugins live at `kast/plugins/*_plugin.py`, auto-discovered (see `kast/utils.py:discover_plugins`)
- **Issue registry:** `kast/data/issue_registry.json` (107 entries, almost all marked `waf_addressable`)
- **Issue registry workflow:** `kast registry list/add/promote`. `kast registry add ID --severity ... --category ...` adds an entry. `kast registry promote SCAN_DIR` reads `missing_issue_ids.json` and walks the operator through accepting candidate entries (use `--accept-all` for CI). Both write atomically.
- **Sample scan baseline:** `docs/baseline-v2.14/sample-scan-1/` — reference for expected kast output structure.
- **kast-web:** at `/home/mscollins/kast-web/`; shells out to `/usr/local/bin/kast`.

## House style

- Python 3.11+ baseline (dev box runs 3.13)
- Timestamps: `datetime.now(timezone.utc).isoformat(timespec="milliseconds")` — never the deprecated `datetime.utcnow()`
- Logging: `self.debug(...)` inside plugins; never `print()`
- No emojis in code or docs unless explicitly requested
- Default to no comments unless the WHY is non-obvious; never write block comments or multi-paragraph docstrings unprompted
- Don't add backwards-compat hacks for code that doesn't need them
- Don't add error handling, fallbacks, or validation for scenarios that can't happen — trust internal code, only validate at system boundaries
- For UI/frontend changes, verify in a browser before reporting "done"
- Match the scope of changes to what was requested — bug fixes don't need surrounding cleanup

## Plugin authoring rules

Durable invariants for any new plugin or change to an existing one. The architecture-and-patterns section above describes the underlying machinery; these are the rules you follow when writing a plugin.

- **Choose the base:** tool wrappers inherit from `ExternalToolPlugin` (subprocess + atomic write + processed-dict scaffolding); pure-Python plugins (HTTP API calls, file analysis) inherit from `KastPlugin` directly. Both use the canonical `__init__(self, cli_args, config_manager=None)` signature.
- **Identity is class attributes** (`name`, `display_name`, `description`, `website_url`, `scan_type`, `output_type`) — never set in `__init__`. `config_schema` is also a class attribute.
- **Result dicts:** always `self.get_result_dict(disposition, results, timestamp)`; never construct manually.
- **`findings_count` integer is required** in every processed dict — kast-web's scan-details page renders it.
- **Read config via `self.get_config(key, default)`** — reads the merged stack (CLI > project > user > system > schema defaults).
- **`is_available()` returns False gracefully** when the underlying tool is missing — never raise.
- **Never crash the orchestrator.** Wrap external calls in try/except; on failure return `self.get_result_dict("fail", message, timestamp)` so `post_process` still emits a `_processed.json` with `disposition: fail`. **kast-web's file-presence state machine depends on the completion marker.**
- **Dependencies** are declared on the instance as a list of `{"plugin": name, "condition": lambda r: ...}` dicts; the orchestrator gates execution until each dependency has run and its condition returns truthy.
- **Report widgets emit a single rich payload** (e.g., `extra_processed_fields = {"custom_html": "..."}`). The v2 dual `custom_html` / `custom_html_pdf` requirement is gone — the renderers handle format-specific differences.
- **Starter file:** `kast/plugins/template_plugin.py` is the canonical starter (deliberately skipped by discovery). `whatweb_plugin.py` and `wafw00f_plugin.py` are the reference `ExternalToolPlugin` migrations.
