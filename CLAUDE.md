# kast / kast-web — Active Context for AI Assistants

This file is auto-loaded by Claude Code on every session in this repo. It is the lightweight "what's true *right now*" override. Comprehensive reference lives in `genai-instructions.md` (rewritten for v3 in Phase B10); this file wins where the two conflict.

## Project at a glance

kast is Barracuda's "ETS for web apps" — a Solutions Architect's tool for generating digestible web-application security reports that drive WAF/WaaS sales conversations with prospects. **The audience is internal Barracuda SAs and partner sales engineers, not the broad security community**, even though the README frames it that way.

kast-web (at `/home/mscollins/kast-web/`, a separate repo) is the Flask + Celery + Redis web frontend that shells out to the kast CLI installed at `/usr/local/bin/kast`.

**Reliability and reputational safety are first-class concerns.** An SA cannot run a flaky tool in front of a prospect. Active scans must never look like attacks against the prospect's infrastructure.

## Current status: v3 refactor in progress

We are on branch `refactor/v3.0`, executing the plan in `docs/v3-planning/`:

- **`01-audit.md`** — Phase 1 audit of v2.14 (what's broken, what to keep)
- **`02-ideation.md`** — Phase 2 capability menu and Tier 1 cut for v3
- **`03-design-and-migration.md`** — Phase 3 v3 design and phased migration plan
- **`04-kast-web-cloud-migration.md`** — Phase D detailed kast-web design (added 2026-05-02 after exploration revealed Phase D is a re-architecture, not a file-relocation)

**Version-history note:** kast goes 2.14 → 3.0 on this branch. **kast-web** has its own independent version line and is going **v1.5 → v2.0** on its `refactor/v2.0` branch. The two repos release as a coordinated bundle, but the version numbers don't match. Earlier sections in `03-design-and-migration.md` that say "kast-web 3.0" were a mistake; they've been corrected to "kast-web 2.0."

**Active phase: E — Release polish + tagging.** Phases A–D are complete. C is partial (C1+C3+C4 shipped; C5/C7/C8–C11/C12 deferred to v3.1). E1–E4, E6–E7 shipped on the kast side; E5 was opportunistically done in B10. **E8 (tags `v3.0.0` and `v2.0.0`) is created locally** — push them after running `docs/RELEASE_VALIDATION.md`'s OS smoke-test on at least one supported OS. E9 is a manual checklist Michael runs on fresh VMs before pushing tags.

## Critical: contracts frozen for v3.0

Do not change these surfaces without explicit, coordinated planning:

- **The kast↔kast-web contract** documented in `docs/web-integration.md`. Atomic writes (`.tmp` + `rename(2)`), frozen filenames (`{plugin}.json`, `{plugin}_processed.json`), file-presence state machine, `zap_scan_progress.json` channel.
- **The v2 CLI argv contract** (the `kast --target X --mode passive ...` shape). Preserved through v3.0 via a wrapper.
- **The `_processed.json` per-plugin output format**, including its kebab-case keys (`plugin-name`, `plugin-display-name`, `plugin-website-url`, etc.).
- **The issue registry data format** in `kast/data/issue_registry.json`.

Internal refactoring is free as long as these surfaces stay stable.

## genai-instructions.md and .clinerules — rewritten for v3 (Phase B10)

Both files were rewritten in Phase B10 to describe v3 patterns natively. The v2 footguns they used to enshrine (set-attrs-before-super-init, `datetime.utcnow`, dual `custom_html`/`custom_html_pdf`, bare severity strings, schema-registration during `__init__`, the 10-plugin list) are gone from the docs. Treat both files as v3-aligned reference material — but **this file (`CLAUDE.md`) still wins where they conflict**, since it tracks active-phase changes that may not yet be reflected in the comprehensive doc.

## v2 bug patches landing in v2.14.x — do not revert

Three independent fixes are being applied to main as the warmup before Phase A:

1. **`Info`/`Informational` severity normalization** in `kast/report_templates.py:get_severity()` — registry stores "Informational"; reports use "Info"; normalization happens at the source.
2. **Busy-wait fix** in `kast/orchestrator.py` parallel scheduler — replaces the discarded-iterator misuse (`done, _ = as_completed(futures), None`) with `next(as_completed(futures))`.
3. **ZAP profile path resolution** in `kast/main.py` — resolves relative to the kast package directory (`Path(__file__).resolve().parent / "config" / ...`), not the cwd.

If you see the old code patterns (e.g., `severity == "Info"` only; `done, _ = as_completed(futures), None`; a relative `kast/config/zap_automation_*.yaml` string), they are regressions and should be re-fixed.

## Active patterns (grows as Phase A lands)

This section starts thin and accumulates as foundation work ships. **Until each item ships, follow whatever pattern exists in current code; once shipped, follow the new pattern everywhere.** Each Phase A deliverable should append to this section in the same PR.

- **Severity enum at `kast/core/severity.py`** — LANDED (Phase A6). Use `Severity.HIGH | MEDIUM | LOW | INFORMATIONAL | UNKNOWN`; never write bare severity strings. The registry stores `"Informational"` (not `"Info"`); `Severity.from_registry(value)` normalizes legacy `"Info"` and the `"Issue ID not found."` sentinel. `severity_counts` dicts in report code now key on `"Informational"`, not `"Info"`. Templates reference `severity_counts.Informational`. The badge *label text* is still rendered as "Info" for visual brevity — that's a display-only abbreviation, not a data value.
- **PluginRegistry at `kast/registry.py`** — LANDED (Phase A3+A4). Construct one per kast invocation: `registry = PluginRegistry(logger, cli_args=args, config_manager=cm)`. Use `registry.discover()` for the class list, `registry.all_instances()` for cached instances (sorted by priority), `registry.get(name)` for a specific plugin, `registry.filter_by_mode(mode)` for instances filtered by `scan_type`. Tolerates the legacy `__init__(cli_args)` signature via internal TypeError fallback (removed in Phase A5). **The five duplicated try/except instantiation blocks in `main.py`, `orchestrator.py`, and `utils.py` are gone** — go through the registry. `ScannerOrchestrator` now takes a list of plugin **instances** (not classes); its `config_manager` constructor parameter has been removed (instances already carry it). `kast/utils.py:show_dependency_tree(registry, scan_mode, log)` now takes a registry, not classes.
- **ExternalToolPlugin base at `kast/plugins/external_tool.py`** — LANDED (Phase B8, first migrations B9). New tool-wrapper plugins should inherit from `ExternalToolPlugin(KastPlugin)` instead of `KastPlugin` directly. Subclass declares `tool_binary` (for auto `is_available()`), `output_filename`, `output_format` (`"json"` or `"text"`) as class attributes; provides `build_command(target, output_path)` and `count_findings(findings)` as required hooks; optionally overrides `parse_findings`, `extract_issues`, `format_summary`, `format_details`, `format_executive_summary`, `extra_processed_fields` (for plugin-specific keys like `custom_html`). The base handles subprocess invocation, timeout, return-code check, missing-output detection, raw-output reading, atomic writes via `write_json_atomic`, and the standard processed-dict assembly. **Migrated in B9:** `whatweb_plugin.py` (458→195 lines, -57%) and `wafw00f_plugin.py` (505→357 lines, -29%; `run()` is overridden for the HTTPS→HTTP TLS-error retry quirk). The remaining legacy plugins still use the direct `KastPlugin` subclass shape and migrate one-by-one. Two B9 gotchas worth knowing: (1) `kast/utils.py:discover_plugins` filters `obj.__module__ != module_name` so the imported `ExternalToolPlugin` symbol isn't picked up as a "plugin" in every file that imports it; (2) wafw00f's raw output is a top-level **list** but post_process expects findings to be a dict — `parse_findings` re-wraps into the v2 `{name, timestamp, disposition, results}` shape so `report/data.py:232` (`plugin.get("findings", {}).get("disposition")`) keeps working. Output is byte-for-byte compatible with the v3 baseline at `docs/baseline-v2.14/sample-scan-1/`.
- **Unified report pipeline at `kast/report/`** — LANDED (Phase A7). Pipeline is `collect_report_data(plugin_results, target) -> dict`, then `render_html(data, output_path, logo_path)` or `render_pdf(data, output_path, logo_path)`. Both renderers consume the SAME data structure; their only differences are template selection, JSON pre-rendering (PDF), CSS placement (HTML copies, PDF embeds), logo embedding (PDF base64, HTML filename ref), and exec-summary anchor links (HTML only). **Never re-introduce parallel HTML/PDF data-prep code paths** — extract any new shared work into `collect_report_data`. The legacy `kast.report_builder` module is now a thin shim that re-exports from `kast.report` for backward compat; new code imports from `kast.report` directly. Helpers (`format_multiline_text`, `format_json_for_pdf`, `infer_issue_metadata`, etc.) live in `kast/report/helpers.py`.
- **Class-attribute identity and schemas** — LANDED (Phase A5). Plugin identity (`name`, `display_name`, `description`, `website_url`, `scan_type`, `output_type`) is declared as **class attributes**, not set in `__init__`. The schema-registration footgun is gone — there is no longer any need to "set self.name BEFORE super().__init__()". Use `ConfigManager.collect_schemas_from_classes(plugin_classes)` to register every plugin's schema without instantiation (the path used by `--config-schema`, `--config-init`, `--config-show`). The TypeError fallback in `PluginRegistry._instantiate` has been removed; all plugins must use the canonical `__init__(self, cli_args, config_manager=None)` signature. Plugin classes are required to declare `name` and `config_schema` as class attributes.
- **Atomic JSON writes via `kast/core/atomic.py`** — LANDED (Phase A11). All state-bearing writes go through `write_json_atomic(path, data, **dump_kwargs)` rather than `with open(path, "w") as f: json.dump(...)`. The helper writes to `<path>.tmp` and `os.replace`s into place — POSIX rename(2) is atomic, so kast-web watchers never observe a partial file. **Don't introduce raw `json.dump(...)` calls for `*_processed.json`, `zap_scan_progress.json`, `kast_info.json`, or `missing_issue_ids.json`** — they violate the contract documented in `docs/web-integration.md`. Use `write_json_atomic` instead. The helper accepts json.dump kwargs (e.g., `default=str` for non-serializable values).
- **CSS-based long-string wrapping** — LANDED (Phase A9). `add_word_break_opportunities` (the v2 helper that injected `<wbr>` tags into rendered text) has been deleted. Long URLs and other strings now wrap via `overflow-wrap: anywhere` rules on `.report-paragraph`, `.json-string`, `.json-key`, `.issue-description`, `td`, etc., in `kast_style.css` and `kast_style_pdf.css`. **Don't reintroduce `<wbr>` injection in Python** — handle wrapping in CSS. If a new section needs aggressive wrapping, add it to the comment-block at the bottom of `kast_style_pdf.css`. Note: WeasyPrint accepts `overflow-wrap: anywhere` but **rejects** `word-break: break-word` (non-standard CSS); use `word-break: break-all` if extra-aggressive breaking is needed in PDF.
- **Jinja macros at `templates/_macros.html`** — LANDED (Phase A8, scaffolded). Both report templates do `{% import "_macros.html" as kast %}` and call shared rendering primitives. Currently the file holds one macro: `kast.tool_anchor(name)` for anchor-ID generation (was duplicated 10 inline sites in v2). Add new macros only when the same logic is duplicated across HTML and PDF templates. `templates/partials/` exists for shared template blocks but is intentionally empty in A8 — see its README for criteria. **Aggressive template inheritance is deferred** beyond Phase A: the two templates have legitimately different layouts (HTML interactive nav, PDF cover page) and we lack a golden-output diff to validate large-scale restructuring.
- **CLI dispatch in `kast/cli/`** — LANDED (Phase B1+B7, expanded by B2/B3/B4/B5). The Click-based dispatcher is at `kast/cli/main.py`. Subcommands now live in their own modules under `kast/cli/`: `scan.py` (the `scan` group + `list/show/rerun`), `plugins.py` (`list/show/deps`), `doctor.py`, `registry.py` (`list/add/promote`). `kast/cli/__init__.py` holds `_translate_v2_argv()` which maps legacy v2 invocations (`kast --target X`, `kast --list-plugins`, etc.) to the v3 subcommand form before Click parses them — preserving the kast↔kast-web argv contract documented in `docs/web-integration.md`. `kast/cli/_shared.py` holds helpers used across modules (e.g., `make_args_namespace`). **`kast/main.py` is a 13-line shim that delegates to `kast.cli.main()`.** When adding a new subcommand, create a module under `kast/cli/`, define the Click group/command there, and `add_command` it from `cli/main.py`. Do NOT reintroduce argparse logic in `kast/main.py`. The `--zap-profile` relative-path bug (audit § 5.3) is **fixed** in the v3 scan subcommand by resolving relative to the package directory.
- **AI adapter abstraction at `kast/ai/`** — LANDED (Phase C1+C3+C4). `kast.ai.base` defines the runtime-checkable `AIAdapter` Protocol and `AIResponse` dataclass; `kast.ai.anthropic_adapter` is the only concrete implementation (default model `claude-sonnet-4-6`, uses SDK 0.97's native `output_config={"format": {"type": "json_schema", "schema": ...}}` for structured output). `kast.ai.config.get_ai_adapter` resolves credentials with precedence env (`KAST_AI_API_KEY` > `KAST_AI_PROVIDER` > `KAST_AI_MODEL`) → `~/.config/kast/ai.yaml` → `AIConfigError`. `kast.ai.prompts.load_prompt(name)` parses YAML frontmatter + `## System` / `## User` sections from `kast/ai/prompts/<name>.md`; the user section is a Jinja2 template the caller renders. `kast.ai.summary.generate_ai_summary(adapter, report_data)` orchestrates: builds context from `collect_report_data`'s output, renders the prompt, calls the adapter with `EXEC_SUMMARY_SCHEMA`, parses+validates the response, returns `{headline, narrative, key_findings, recommended_actions, _meta}`. **Failure mode is "banner + deterministic fallback":** if `--ai-summary` is set but the call fails (no key, network, schema mismatch), `_run_scan` catches the exception, sets `ai_error`, and the report renders the deterministic exec summary plus a banner noting the failure. Templates render the AI block (`.ai-summary` div with `.ai-headline / .ai-narrative / .ai-list / .ai-disclaimer`) only when `ai_summary` is present; when it's absent the `Identified Issues` section + `executive_summary` text are shown (the deterministic path). `kast_info.json` gains an `ai` block (`enabled / status / adapter / model / prompt_version / tokens_in / tokens_out / latency_ms / error`). The `anthropic` SDK is a **required** install-time dependency in `requirements.txt` even though the `--ai-summary` flag is opt-in at runtime — keeps imports unconditional. The kast-web service (cost gating, review workflow, encrypted API keys, admin UI) is C8 and not yet built; for now AI runs purely against the user's own API key.

## Cloud subsystem migration: COMPLETE

**Phase D LANDED in full** (D1–D11 across both repos). The ZAP cloud-deployment subsystem now lives in kast-web at `kast-web/app/cloud/`. The kast CLI no longer has cloud-mode code. ~6,425 lines of cloud-related code were removed from this repo in D10 (`af1610c`): `kast/terraform/`, `zap_provider_factory.py`, `ssh_executor.py`, `terraform_manager.py`, `cleanup_orphaned_resources.py`, `diagnose_infrastructure.py`, `find_zap_url.py`, `monitor_zap.py`, `zap_cloud_config.yaml`, `kast/config/nginx/`, related test scripts, and the `cloud` value of the `zap.execution_mode` enum.

`kast/scripts/zap_providers.py` was kept but trimmed — `LocalZapProvider` and `RemoteZapProvider` remain; `CloudZapProvider` is gone. `kast/plugins/zap_plugin.py` imports `LocalZapProvider`/`RemoteZapProvider` directly (no factory) and dispatches inline.

**Cloud-scan flow now (post–Phase D):** kast-web's `execute_scan_task` calls `cloud_provision_task` (provisions the ZAP instance via Terraform inside kast-web), captures the resulting URL + API key, then spawns the kast CLI with `--set zap.execution_mode=remote --set zap.remote.url=... --set zap.remote.api_key=...`. The kast CLI sees only local/remote/auto. Migration guide for v2.x cloud users at `kast-web/docs/MIGRATION_FROM_KAST_CLOUD.md`.

**Detailed Phase D plan** at `docs/v3-planning/04-kast-web-cloud-migration.md` documents the original design; everything in the "Migration sequence" section has shipped.

## Out of scope for v3.0

Tier 2/3/4 items from the ideation pass (pre-meeting briefing, per-audience remediation, MCP server, "ask the report" agent, adaptive scan plan, sharable URLs, per-partner theming, findings diff, multi-target scan, continuous monitoring, industry benchmarking) are deliberately deferred to v3.1+. See section 8 of `03-design-and-migration.md` for the full deferred list.

## Working in this codebase

- **Run tests:** `python -m pytest kast/tests/` (30 tests today; target ~150 by end of v3)
- **Plugin discovery:** plugins live at `kast/plugins/*_plugin.py`, auto-discovered (see `kast/utils.py:discover_plugins`)
- **Issue registry:** `kast/data/issue_registry.json` (68+ entries, almost all marked `waf_addressable`)
- **Issue registry workflow:** `kast registry list/add/promote` (Phase B4). `kast registry add ID --severity ... --category ...` adds an entry. `kast registry promote SCAN_DIR` reads `missing_issue_ids.json` and walks the operator through accepting candidate entries (use `--accept-all` for CI). Both write atomically. The legacy `fix_registry.py` was deleted in B4.
- **Sample scan baseline:** `docs/baseline-v2.14/sample-scan-1/` — reference for expected kast output structure
- **kast-web:** at `/home/mscollins/kast-web/`; shells out to `/usr/local/bin/kast`; today parses `kast -ls` text output (Phase B replaces with `kast plugins list --json`)

## House style

- No emojis in code or docs unless explicitly requested
- Default to no comments unless the WHY is non-obvious; never write block comments or multi-paragraph docstrings unprompted
- Don't add backwards-compat hacks for code that doesn't need them
- Don't add error handling, fallbacks, or validation for scenarios that can't happen — trust internal code, only validate at system boundaries
- For UI/frontend changes, verify in a browser before reporting "done"
- Match the scope of changes to what was requested — bug fixes don't need surrounding cleanup

## Lifecycle of this file

`CLAUDE.md` is the active-phase override. It will shrink to a thin pointer once v3.0 ships and `genai-instructions.md` is rewritten to describe v3 patterns natively. Until then, treat this file as the source of truth for "what's actually being built right now."
