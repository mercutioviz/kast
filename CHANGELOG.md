# Changelog

All notable changes to kast are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] — Unreleased

The v3 coordinated release. Released alongside kast-web 2.0.0.

### Added

- **AI-augmented executive summaries** (`kast scan --ai-summary`). The Anthropic adapter ships by default; configure via `KAST_AI_API_KEY` env var or `~/.config/kast/ai.yaml`. On failure, reports still render with the deterministic summary plus a banner. The adapter is pluggable for future OpenAI / Bedrock / Ollama implementations.
- **Click-based subcommand CLI**: `kast scan`, `kast scan list/show/rerun`, `kast plugins list/show/deps`, `kast registry list/add/promote`, `kast doctor`, `kast self-update`, `kast config init/show/schema`, `kast version`. The legacy v2 argv shape is preserved through a translation wrapper.
- **`kast doctor`** — environment health check that walks Python modules, external scanner CLIs, log/results dir permissions, config files, issue registry, and plugin loading. `--fix` applies safe auto-fixes (mkdir, config init); `--json` for machine-readable output. Exit code is CI-friendly (FAIL → 1).
- **`kast self-update`** — Python wrapper around `update.sh`; supports `--check-only`, `--auto`, `--force`, `--dry-run`, `--list-backups`, `--rollback`.
- **`kast registry`** — issue-registry workflow built into the CLI. `list`, `add`, `promote SCAN_DIR` (with `--accept-all` for CI). Replaces the standalone `fix_registry.py`.
- **`kast plugins`** — discovery surface. `list` and `show NAME` and `deps` for the dependency tree. `--json` emits machine-readable output (the kast-web integration target).
- **`PluginRegistry`** at `kast.registry` — single source of truth for plugin discovery, instantiation, caching, priority sorting. Replaces the five duplicated try/except instantiation blocks scattered through v2.
- **`ExternalToolPlugin` base** at `kast.plugins.external_tool` — collapses ~300 lines of boilerplate per tool-wrapper plugin (subprocess invocation, output reading, atomic processed-dict writes, format-hook scaffolding). `whatweb_plugin.py` and `wafw00f_plugin.py` migrated as reference implementations.
- **`Severity` enum** at `kast.core.severity` — canonical severity values (`HIGH`, `MEDIUM`, `LOW`, `INFORMATIONAL`, `UNKNOWN`). `Severity.from_registry(value)` normalizes the legacy `"Info"` and `"Issue ID not found."` sentinel.
- **Atomic JSON writes** via `kast.core.atomic.write_json_atomic`. Every state-bearing file (`*_processed.json`, `kast_info.json`, `zap_scan_progress.json`, `missing_issue_ids.json`) goes through it. POSIX `rename(2)` is atomic, so kast-web watchers never observe a partial file.
- **Unified report pipeline** at `kast.report` — `collect_report_data(plugin_results, target) -> dict`, then `render_html(data, ...)` or `render_pdf(data, ...)`. Both renderers consume the same data structure.
- **Class-attribute plugin identity** — declare `name`, `display_name`, `description`, `website_url`, `scan_type`, `output_type`, and `config_schema` as class attributes. Schemas are collected via `ConfigManager.collect_schemas_from_classes(...)` without instantiation.
- **`pyproject.toml` and pipx packaging** — `pipx install kast` works; the entry point is `kast = kast.cli:main`.
- **Multi-stage `Dockerfile`** — slim runtime image with `whatweb`, `wafw00f`, `testssl.sh`, `sslscan`, fonts, and the kast venv. ZAP is not bundled (use kast-web for managed cloud scans, or mount Docker socket for local-mode).
- **AI metadata in `kast_info.json`** — additive `ai` block reports adapter, model, prompt version, tokens in/out, latency, status, and error. Present (with `enabled: false`) even when `--ai-summary` isn't used.
- **Org Discovery plugin** (`org_discovery`) — WHOIS / Shodan correlation. Ships in v3.
- **AI Chatbot Detection plugin** (`ai_chatbot_detection`) — passive detection of LLM-powered chat widgets. Ships in v3.

### Changed

- **CLI argv shape preserved** — the legacy `kast --target X --mode passive ...` form continues to work via `_translate_v2_argv()` in `kast/cli/__init__.py`. 15 tests pin this contract (`test_cli_v2_compat.py`).
- **Plugin discovery** — `kast/utils.py:discover_plugins` now filters `obj.__module__ != module_name` so the `ExternalToolPlugin` symbol imported by tool-wrapper plugins isn't itself picked up as a plugin.
- **Report pipeline** — `kast.report_builder` is now a thin compatibility shim that re-exports from `kast.report`. Existing imports keep working; new code should import from `kast.report`.
- **`--zap-profile` path resolution** — the YAML config is now resolved relative to the kast package directory (`Path(__file__).resolve().parent / "config" / ...`), not the current working directory. Fixes the v2.14 cwd-dependent bug.
- **Long-string wrapping** — handled via CSS (`overflow-wrap: anywhere` rules in `kast_style.css` and `kast_style_pdf.css`), not via the v2 `<wbr>`-injection helper. The helper is removed.
- **Severity counts** — `severity_counts` dicts in report code key on `"Informational"` (canonical) rather than `"Info"`. Templates reference `severity_counts.Informational`. Badge text still renders as "Info" for visual brevity.
- **WhatWeb plugin** — migrated to `ExternalToolPlugin` base. 458 → 195 lines (-57%). Output is byte-for-byte compatible with the v3 baseline at `docs/baseline-v2.14/sample-scan-1/`.
- **Wafw00f plugin** — migrated to `ExternalToolPlugin` base. 505 → 357 lines (-29%). `run()` is overridden for the HTTPS→HTTP TLS-error retry quirk.
- **`genai-instructions.md` and `.clinerules`** — rewritten for v3 patterns natively. The v2 footguns (set-attrs-before-super-init, `datetime.utcnow`, dual `custom_html`/`custom_html_pdf`, bare severity strings, schema-registration during `__init__`, the 10-plugin list) are gone from the docs.

### Removed

- **Cloud execution mode** for ZAP. `kast/scripts/zap_provider_factory.py`, `kast/scripts/{ssh_executor, terraform_manager, cleanup_orphaned_resources, diagnose_infrastructure, find_zap_url, monitor_zap}.py`, `kast/terraform/{aws,azure,gcp}/`, `kast/config/zap_cloud_config.yaml`, `kast/config/nginx/`, related test scripts, and `CloudZapProvider` from `kast/scripts/zap_providers.py`. The `cloud` value of `zap.execution_mode` is removed from the config schema enum. ~6,425 lines deleted across 29 files. Cloud-mode ZAP scans are now managed by kast-web 2.0; see `docs/MIGRATION_V2_TO_V3.md` for migration guidance.
- **`fix_registry.py`** standalone script. Replaced by `kast registry` subcommands.
- **`add_word_break_opportunities`** Python helper for `<wbr>` injection. Replaced by CSS `overflow-wrap: anywhere`.

### Fixed

- **`Info`/`Informational` severity normalization** in `kast/report_templates.py:get_severity()` — registry stores `"Informational"`; reports use `"Info"` for the badge label only; normalization happens at the source.
- **Busy-wait** in `kast/orchestrator.py` parallel scheduler — replaces the discarded-iterator misuse (`done, _ = as_completed(futures), None`) with `next(as_completed(futures))`.
- **`--zap-profile` relative-path resolution** — see "Changed" above.
- **WhatWeb domain-redirect detection** — preserves v2 byte-compat (the v2 logic emits a malformed recommendation when `RedirectLocation` is a relative URL; that quirk is intentionally preserved for output compatibility).

### Migration

See [`docs/MIGRATION_V2_TO_V3.md`](docs/MIGRATION_V2_TO_V3.md) for the full migration guide. The big watch item is cloud-mode ZAP — if you used it via the kast CLI directly, you'll need to either upgrade to kast-web 2.0 or switch to remote-mode ZAP with your own infrastructure.

### Tests

- 398 passed, 2 skipped, 3 xfailed (was ~30 in v2.14).
- New test groups: CLI subcommands (`test_cli_*`), v2-argv compatibility (`test_cli_v2_compat`), `ExternalToolPlugin` base (`test_external_tool_base`), `Severity` enum, atomic writes, AI adapter (mocked), AI prompts, AI summary, AI config, baseline render, registry workflow.

### Known issues

- Cloud-mode ZAP scans launched from kast-web require kast-web 2.0. kast-web 1.5.x expects kast to provide cloud execution mode, which it no longer does. Don't mix versions across the boundary.

---

## Prior versions

For changes in v2.x and earlier, see git history. The v2 line predates this CHANGELOG; see `docs/v3-planning/01-audit.md` for the v2.14 baseline audit.
