# Changelog

All notable changes to kast are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Patch versions v3.0.1 through v3.0.20 are tracked in git commit history only**
> (see `git log --oneline`). Each commit subject names the version it shipped under.
> This CHANGELOG resumes structured release notes at v3.0.21.

## [3.0.25] — 2026-06-10

### Fixed

- **`kast/__init__.py` version resolution** — `kast -V` reported a stale
  version on editable installs (e.g. `/opt/kast`) whenever `VERSION` was
  bumped without re-running `pip install -e .`. The previous logic read
  `importlib.metadata` first (which holds the version frozen at the last
  `pip install`) and only fell back to the `VERSION` file if the metadata
  import failed. Inverted the precedence: `VERSION` is tried first via
  `Path(__file__).resolve().parent.parent / "VERSION"`; `importlib.metadata`
  is the fallback for pipx / wheel installs where no parallel `VERSION`
  file exists alongside the package. Bumping `VERSION` is now sufficient
  — no `pip install` required to see the change in `kast -V`.

---

## [3.0.24] — 2026-06-10

CORS analyzer plugin coverage and documentation. End-to-end verification
in v3.0.23 confirmed the plugin was functional and v3-compliant but had
no test file and was missing from the README plugin table.

### Added

- **`kast/tests/test_cors_analyzer.py`** (24 tests, 9 TestCase groups):
  identity / config schema / `is_available`; `_normalize_target` URL
  handling; `post_process` with empty findings, mixed findings, repeated
  finding types (uniqueness), severity ordering, JSONP-only input,
  worst-finding naming in the summary; fail-disposition shape;
  executive-summary variants for the canonical issue types;
  `get_dry_run_info` shape; `report_only` mode (existing results +
  missing results); registry coverage (every issue ID the plugin can
  emit must be in `kast/data/issue_registry.json`, and every ID in
  `_ISSUE_SEVERITY` must have a slot in `_ISSUE_SEVERITY_ORDER`).
- **`README.md` plugin table**: added the `cors_analyzer` row between
  `whatweb` (priority 15) and `related_sites` (priority 45). CORS
  analyzer's priority is 30.

### Tests

- 576 passed (was 552; +24 from `test_cors_analyzer.py`), 0 skipped,
  3 xfailed, 0 warnings, 0 ruff findings.

---

## [3.0.23] — 2026-06-10

Test hygiene and doc-drift sweep. 552 passed, 0 skipped, 3 xfailed,
0 warnings (was 4 — the urllib3 InsecureRequestWarnings are now
filtered out at the pytest level), 0 ruff findings.

### Removed

- **20 `if __name__ == "__main__":` blocks** from test files. v2-era
  dead-code paths: pytest is the test runner and these blocks added
  noise, broke during sys.path cleanups, and confused readers. The
  one elaborate manual harness in `test_executive_summary.py` (a try
  / finally tmpdir setup) is also gone.

### Changed

- **`pyproject.toml`**: added `[tool.pytest.ini_options]` with a
  `filterwarnings` rule to ignore `urllib3.exceptions.InsecureRequestWarning`.
  The CORS plugin makes real HTTPS calls to `example.com` with
  `verify=False` during tests (probing CORS bypass); urllib3's warning
  isn't actionable in our code.
- **Phase X archaeology purged from code docstrings** (29 sites across
  module docstrings, test docstrings, CLI option help text, and two
  xfail markers). v3 has shipped; "(Phase A4)", "(Phase B8)",
  "(Phase C8)" etc. are design history and add no value to a reader
  trying to understand current code. The relevant historical docs
  remain at `docs/v3-planning/`.

### Tests

- 552 passed, 0 skipped, 3 xfailed, 0 warnings, 4 subtests passed.
- 0 ruff findings.

---

## [3.0.22] — 2026-06-10

Bug fix and lint baseline cleanup. Ruff findings: 9 → 0.

### Fixed

- **`kast/ai/evals/criteria.py:114`** — `check_target_mentioned` used
  `.lstrip("https://")` which strips characters rather than the substring.
  `"https://htp.example.com".lstrip("https://")` would yield `".example.com"`,
  causing the "target mentioned" eval criterion to misjudge targets whose
  hostnames start with characters from the URL-scheme set. Replaced with
  `.removeprefix("https://").removeprefix("http://")`.

### Changed

- **`kast/scripts/zap_api_client.py:246`** and **`kast/scripts/zap_providers.py:100,115`**
  — replaced bare `except:` with specific exception lists
  (`(ValueError, TypeError)` for int-parse paths;
  `(subprocess.TimeoutExpired, FileNotFoundError, OSError)` for subprocess paths).
- **`kast/plugins/script_detection_plugin.py:128-129`** — `is_available()` now
  uses `importlib.util.find_spec(...)` instead of try-import. Drops the
  unused-import flags ruff was raising.
- **`kast/orchestrator.py:246`** — dependency-deadlock loop iterates
  `pending_plugins.values()` instead of `.items()` (the key was unused).
- **`kast/plugins/base.py:107`** — `KastPlugin.setup`: collapsed two-line
  docstring + `pass` to a single-line docstring (Python convention for
  intentional-no-op methods), with a `# noqa: B027` to acknowledge the
  optional-override design.
- **`kast/tests/test_ftap_plugin.py`** — deleted two TODO-stub tests
  (`test_run_success`, `test_run_failure`) that just `pass`'d. The
  `post_process` behavior they were meant to cover is exhaustively
  tested in the 4 `test_post_process_*` tests already in the file.

### Tests

- 552 passed (down 2 from the deleted TODO stubs), 0 skipped, 3 xfailed.
- 0 ruff findings.

---

## [3.0.21] — 2026-06-10

End-of-v3.0 housekeeping pass. No user-visible behavior changes; all changes are
internal cleanup, doc refreshes, and a lint baseline. Tests stay green throughout
(555 passed, 0 skipped, 3 xfailed).

### Removed

- **`kast/scripts/create_plugin.py`** — v2-era plugin wizard. `template_plugin.py`
  plus the `whatweb_plugin.py` / `wafw00f_plugin.py` reference migrations cover
  the workflow.
- **`kast/scripts/run_report_builder_test.py`** and **`demo_executive_summary.py`**
  (+ tracked `demo_executive_summary_report.html` artifact) — demo scripts that
  imported the now-deleted `report_builder` shim.
- **`kast/scripts/TEST_SCRIPTS_README.md`** (596 lines) — documented the Terraform
  cloud-mode test scripts deleted in Phase D10.
- **`kast/report_builder.py`** — backward-compat shim retained during v3.0 development.
  No external (kast-web) consumers; the 7 internal importers were migrated to
  `kast.report` in this release.
- **Six dead test files** (~755 lines total): `test_html_list_structure.py` and
  `test_whatweb_full_integration.py` (self-admitted `@pytest.mark.skip` with
  comment that the assertions are covered elsewhere); `test_tool_index.py`,
  `test_testssl_plugin.py`, `test_testssl_clientproblem.py`, and
  `demo_ftap_processing.py` (script-only with no test functions and hardcoded
  `/home/kali/...` paths).
- **Six unused dependencies** removed from `requirements.txt` and `pyproject.toml`:
  `paramiko` (cloud SSH executor moved to kast-web), `aiohttp`, `aioquic`,
  `diskcache`, `langdetect`, `scikit-learn`. Verified zero imports in `kast/`.
- **`genai-instructions.md`**, **`.clinerules`**, and **`kast/.github/copilot-instructions.md`**
  — non–Claude Code GenAI configuration that the project no longer needs.
  All v3 patterns and rules are consolidated into `CLAUDE.md`.
- **53 stale v2-era docs** under `kast/docs/` (cloud subsystem narratives,
  one-time config migrations, historical fix recipes). The three active
  installer references (`DEBIAN_13_INSTALLER_FIX.md`, `UBUNTU_24_COMPATIBILITY.md`,
  `INSTALL_SCRIPT_IMPROVEMENTS.md`) remain.

### Changed

- **Doc audit**: `README.md`, `docs/VISION.md`, `docs/MIGRATION_V2_TO_V3.md`,
  `docs/web-integration.md`, `docs/ZAP_USAGE.md`, and `kast/plugins/README.md`
  refreshed against current v3 reality. The plugin authoring guide previously
  taught the v2 footguns (set-attrs-before-super-init, `datetime.utcnow`, no
  `ExternalToolPlugin`); rewritten as a concise v3 guide.
- **`CLAUDE.md`** rewritten for post-ship reality: dropped pre-ship status
  framing and "LANDED Phase X" tags; added explicit "Open threads" section
  and reorganized rules into "Architecture and patterns" + "Plugin authoring
  rules" sections. v3.1 deferred candidates moved to `docs/v3.1-backlog.md`.
- **Test import paths**: 10 test files migrated from `sys.path.insert(...)` +
  `from plugins.X import Y` (worked only by sys.path side-effect) to the proper
  `from kast.plugins.X import Y` form.

### Added

- **Ruff lint baseline** (`pyproject.toml` `[tool.ruff]`): line-length 100,
  target-version `py311`, rules `E/F/W/I/UP/B` (with `E501`/`B008` ignored,
  `E402` allowed under `tests/`). 2,326 auto-fixes applied across ~80 files
  (whitespace, import sorting, pyupgrade, f-string-without-placeholders).
- **`docs/v3.1-backlog.md`** — deferred Tier 2/3/4 capability candidates
  (`A2` pre-meeting briefing, `A3` per-audience remediation, `F3` shareable
  URLs, `F4` per-partner theming, `E5` findings diff, etc.) plus a fresh
  plugin-candidates section (CDN fingerprint, API surface detection, auth/SSO
  discovery, bot signals, third-party scripts).

### Fixed

- **`kast/plugins/org_discovery_plugin.py:504`** — list comprehension had its
  `if` clause referencing `h` before the `for h in ...` clause that defined it,
  causing `NameError` whenever Shodan service filtering ran for a related
  domain. Caught by ruff's `F821` undefined-name check.
- **`kast/tests/test_tool_index.py:153`** — missing `import sys` for `sys.exit`
  call in the script's error path. (File subsequently deleted in this release.)

### Known followups

- ~12 test files still have hardcoded `sys.path.insert(0, '/opt/kast')` or
  similar hacks. Tests pass today because of import-order accident; worth a
  mechanical cleanup pass.
- 18 ruff findings remain (7 `F401` unused-import, 3 `B904` raise-without-from,
  3 `E722` bare-except, plus minor `B005/B007/B027/UP035`). None are bugs.

---

## [3.0.0] — 2026-05

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
