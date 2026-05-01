# kast / kast-web — Active Context for AI Assistants

This file is auto-loaded by Claude Code on every session in this repo. It is the lightweight "what's true *right now*" override. Comprehensive reference lives in `genai-instructions.md` (and will be rewritten in Phase A); this file wins where the two conflict.

## Project at a glance

kast is Barracuda's "ETS for web apps" — a Solutions Architect's tool for generating digestible web-application security reports that drive WAF/WaaS sales conversations with prospects. **The audience is internal Barracuda SAs and partner sales engineers, not the broad security community**, even though the README frames it that way.

kast-web (at `/home/mscollins/kast-web/`, a separate repo) is the Flask + Celery + Redis web frontend that shells out to the kast CLI installed at `/usr/local/bin/kast`.

**Reliability and reputational safety are first-class concerns.** An SA cannot run a flaky tool in front of a prospect. Active scans must never look like attacks against the prospect's infrastructure.

## Current status: v3 refactor in progress

We are on branch `refactor/v3.0`, executing the plan in `docs/v3-planning/`:

- **`01-audit.md`** — Phase 1 audit of v2.14 (what's broken, what to keep)
- **`02-ideation.md`** — Phase 2 capability menu and Tier 1 cut for v3
- **`03-design-and-migration.md`** — Phase 3 v3 design and phased migration plan

**Active phase: A — Foundation refactors.** Goal: fix audit-identified klunk without changing user-visible behavior. See section 7, Phase A in `03-design-and-migration.md` for the deliverable list.

## Critical: contracts frozen for v3.0

Do not change these surfaces without explicit, coordinated planning:

- **The kast↔kast-web contract** documented in `docs/web-integration.md`. Atomic writes (`.tmp` + `rename(2)`), frozen filenames (`{plugin}.json`, `{plugin}_processed.json`), file-presence state machine, `zap_scan_progress.json` channel.
- **The v2 CLI argv contract** (the `kast --target X --mode passive ...` shape). Preserved through v3.0 via a wrapper.
- **The `_processed.json` per-plugin output format**, including its kebab-case keys (`plugin-name`, `plugin-display-name`, `plugin-website-url`, etc.).
- **The issue registry data format** in `kast/data/issue_registry.json`.

Internal refactoring is free as long as these surfaces stay stable.

## Outdated guidance — IGNORE these in `genai-instructions.md` and `.clinerules`

Both files were authored against v2 and enshrine patterns v3 explicitly changes. **When they conflict with this file or with the v3 design doc, this file wins.**

Specifically, ignore:

1. **"Set attrs BEFORE `super().__init__()`."** v3 plugins declare identity (`name`, `display_name`, `description`, etc.) as **class attributes** — not set in `__init__` at all. Phase A5 lifted all 12 real plugins. The sequencing footgun is gone.
2. **"Use `datetime.utcnow().isoformat(timespec='milliseconds')`."** That API is deprecated. Use `datetime.now(timezone.utc).isoformat(timespec='milliseconds')`.
3. **"Provide both `custom_html` and `custom_html_pdf`."** v3 unifies the report pipeline (`collect → render(html|pdf)`); plugins emit a single rich payload, renderers handle format-specific differences.
4. **"Use bare severity strings (`"High"`, `"Info"`, etc.)."** v3 has a `Severity` enum at `kast/core/severity.py`; never use bare severity strings.
5. **"Copy `template_plugin.py` as the starting point."** Phase A5 migrated `template_plugin.py` to the v3 shape: identity as class attributes, canonical `__init__(self, cli_args, config_manager=None)` signature. Use it as a starting point — but note that A7+ will introduce `ExternalToolPlugin` as the proper base for tool-wrapper plugins.
6. **".clinerules" lists 10 plugins.** Reality is 13: add `ai_chatbot_detection`, `org_discovery`, `related_sites`.
7. **"Plugins register their schema during `__init__`."** v3 schemas are class attributes; `kast --config-schema` (and `--config-init`, `--config-show`) call `ConfigManager.collect_schemas_from_classes(...)` instead. No instantiation required.

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
- **TBD: ExternalToolPlugin base at `kast/plugins/external_tool.py`** — once landed, new tool-wrapper plugins inherit from it; legacy plugins migrate one-by-one through Phase B.
- **TBD: Unified report pipeline at `kast/report/`** (`data.py` + `html.py` + `pdf.py`) — once landed, never re-introduce parallel HTML/PDF code paths.
- **Class-attribute identity and schemas** — LANDED (Phase A5). Plugin identity (`name`, `display_name`, `description`, `website_url`, `scan_type`, `output_type`) is declared as **class attributes**, not set in `__init__`. The schema-registration footgun is gone — there is no longer any need to "set self.name BEFORE super().__init__()". Use `ConfigManager.collect_schemas_from_classes(plugin_classes)` to register every plugin's schema without instantiation (the path used by `--config-schema`, `--config-init`, `--config-show`). The TypeError fallback in `PluginRegistry._instantiate` has been removed; all plugins must use the canonical `__init__(self, cli_args, config_manager=None)` signature. Plugin classes are required to declare `name` and `config_schema` as class attributes.
- **Atomic JSON writes via `kast/core/atomic.py`** — LANDED (Phase A11). All state-bearing writes go through `write_json_atomic(path, data, **dump_kwargs)` rather than `with open(path, "w") as f: json.dump(...)`. The helper writes to `<path>.tmp` and `os.replace`s into place — POSIX rename(2) is atomic, so kast-web watchers never observe a partial file. **Don't introduce raw `json.dump(...)` calls for `*_processed.json`, `zap_scan_progress.json`, `kast_info.json`, or `missing_issue_ids.json`** — they violate the contract documented in `docs/web-integration.md`. Use `write_json_atomic` instead. The helper accepts json.dump kwargs (e.g., `default=str` for non-serializable values).

## Cloud subsystem is being migrated out of kast

The ZAP cloud-deployment subsystem is moving to kast-web in Phase D. The migrating code:

- `kast/terraform/{aws,azure,gcp}/`
- `kast/scripts/zap_provider_factory.py`, `zap_providers.py`, `zap_api_client.py`
- `kast/scripts/{ssh_executor,terraform_manager,monitor_zap,cleanup_orphaned_resources,diagnose_infrastructure,find_zap_url}.py`
- `kast/config/zap_cloud_config.yaml`, `kast/config/nginx/`
- The `cloud` execution mode of `kast/plugins/zap_plugin.py`

**Do not add new features or fix non-critical bugs in this code within kast.** Bug fixes that affect cloud-mode users should be planned as part of the kast-web side of the migration. The `local` and `remote` execution modes of the ZAP plugin stay in kast.

## Out of scope for v3.0

Tier 2/3/4 items from the ideation pass (pre-meeting briefing, per-audience remediation, MCP server, "ask the report" agent, adaptive scan plan, sharable URLs, per-partner theming, findings diff, multi-target scan, continuous monitoring, industry benchmarking) are deliberately deferred to v3.1+. See section 8 of `03-design-and-migration.md` for the full deferred list.

## Working in this codebase

- **Run tests:** `python -m pytest kast/tests/` (30 tests today; target ~150 by end of v3)
- **Plugin discovery:** plugins live at `kast/plugins/*_plugin.py`, auto-discovered (see `kast/utils.py:discover_plugins`)
- **Issue registry:** `kast/data/issue_registry.json` (65 entries, ~64 marked `waf_addressable`)
- **Issue registry workflow today is ad-hoc** (`fix_registry.py` is a one-shot script with hardcoded entries) — being replaced in Phase B with `kast registry add` / `kast registry promote`
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
