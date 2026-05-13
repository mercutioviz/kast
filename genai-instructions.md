# KAST GenAI Instructions

This document provides guidance for GenAI assistants working with the KAST (Kali Automated Scan Tool) project. It describes v3 patterns natively and supersedes the v2.x revision of this file.

**Version:** 3.0 (in development on `refactor/v3.0`)
**Last Updated:** May 2026
**Project Repository:** https://github.com/mercutioviz/kast

> **Active-phase context:** while v3 work is in progress, the file `CLAUDE.md` at the repo root is the **authoritative active-phase override**. When the two conflict, `CLAUDE.md` wins. This file describes the **v3 destination**; `CLAUDE.md` describes what is true *right now* on the branch.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture & Design Patterns](#architecture--design-patterns)
3. [Code Style & Conventions](#code-style--conventions)
4. [Plugin Development Guide](#plugin-development-guide)
5. [Configuration System](#configuration-system)
6. [CLI Surface](#cli-surface)
7. [Reporting Pipeline](#reporting-pipeline)
8. [ZAP Integration](#zap-integration)
9. [Testing Standards](#testing-standards)
10. [Common Patterns](#common-patterns)
11. [Key Concepts](#key-concepts)
12. [File Organization](#file-organization)
13. [Integration Points](#integration-points)
14. [Frozen Contracts](#frozen-contracts)
15. [Prompt Engineering Tips](#prompt-engineering-tips)

---

## Project Overview

### What is KAST?

KAST is a modular, extensible Python framework for automating web-application security scanning tools. It orchestrates multiple security tools (Mozilla Observatory, WhatWeb, TestSSL, Wafw00f, Subfinder, Katana, Related Sites, FTAP, OWASP ZAP, AI Chatbot Detection, Org Discovery, Script Detection), aggregates findings, and generates HTML/PDF reports with executive summaries.

KAST is paired with **kast-web** (separate repo at `/home/mscollins/kast-web/`), a Flask + Celery + Redis web frontend that shells out to the kast CLI installed at `/usr/local/bin/kast`. Stability of the kast↔kast-web boundary is a first-class concern — see [Frozen Contracts](#frozen-contracts). The two repos maintain independent version histories (kast 2.14 → 3.0; kast-web 1.5 → 2.0) but release as a coordinated bundle.

### Core Purpose

- Orchestrate multiple security scanning tools in a unified workflow
- Standardize per-plugin output for downstream consumers (kast-web, the report renderer)
- Generate professional HTML and PDF reports with executive summaries
- Centralize security issue definitions with remediation guidance via the issue registry
- Support both parallel and sequential execution
- Configure plugins via YAML with CLI overrides

### Key Features

- Modular plugin architecture with class-attribute identity
- `ExternalToolPlugin` base for tool-wrapper plugins (subprocess + parse + post-process scaffolding lives in the base)
- Parallel execution with dependency resolution and priority scheduling
- Click-based subcommand CLI (`kast scan`, `kast plugins`, `kast registry`, `kast doctor`, `kast self-update`, `kast config`) — with a v2 argv compatibility wrapper for kast-web
- Atomic JSON writes for every state-bearing file (kast-web watchers never see partial writes)
- Issue registry with severity, category, and talking-points, plus a `kast registry` workflow for adding/promoting entries
- Canonical severity values via `Severity` enum
- Unified report pipeline (one data structure → HTML or PDF renderer)
- Report-only mode for regenerating reports from existing scan data (`kast scan rerun`)
- Dry-run mode for previewing execution
- Comprehensive logging
- YAML-based configuration with CLI overrides

---

## Architecture & Design Patterns

### High-Level Architecture

```
CLI dispatcher (kast/cli/main.py — Click)
  -> ConfigManager (kast/config_manager.py)
  -> PluginRegistry (kast/registry.py)
       discovers plugin classes, instantiates once, caches by name, sorts by priority
  -> ScannerOrchestrator (kast/orchestrator.py)
       runs plugin instances; sequential or parallel with dependency gating
  -> Plugin instances:
       KastPlugin subclasses — non-tool-wrapper plugins
       ExternalToolPlugin subclasses — tool wrappers (whatweb, wafw00f, ...)
  -> Report pipeline (kast/report/)
       collect_report_data(plugin_results, target) -> dict
       render_html(data, ...) | render_pdf(data, ...)
```

### Subsystems

- **`kast/cli/`** — Click-based CLI dispatcher and subcommand modules. `kast/main.py` is a 13-line shim into `kast.cli.main()`.
- **`kast/registry.py`** — `PluginRegistry`. Single source of truth for plugin discovery and instantiation. Pass it around instead of instantiating plugins ad hoc.
- **`kast/orchestrator.py`** — `ScannerOrchestrator`. Takes a list of plugin **instances** and runs them. Handles dependencies and parallel scheduling.
- **`kast/plugins/`** — `KastPlugin` base + `ExternalToolPlugin(KastPlugin)` base + the individual plugins.
- **`kast/core/`** — small, focused utilities: `severity.py` (`Severity` enum), `atomic.py` (`write_json_atomic`).
- **`kast/report/`** — unified report pipeline: `data.py`, `helpers.py`, `html.py`, `pdf.py`. `kast.report_builder` is a thin compatibility shim.
- **`kast/config_manager.py`** — YAML config loading, schema collection, override merging.
- **`kast/data/issue_registry.json`** — central issue definitions (severity, category, description, talking points).

### Design Patterns

1. **Strategy** — plugin architecture with `KastPlugin` interface, sub-strategy via `ExternalToolPlugin` for the common subprocess case.
2. **Template Method** — `ExternalToolPlugin.run()` and `.post_process()` define the skeleton; subclass hooks fill in the variation.
3. **Registry** — `PluginRegistry` owns discovery, instantiation, and lookup.
4. **Builder** — `collect_report_data` + `render_*` for reports.
5. **Provider** — `ZapInstanceProvider` ABC with Local and Remote implementations only. Cloud infrastructure was removed in Phase D and now lives in kast-web.

---

## Code Style & Conventions

- **Python 3.11+** is the development baseline (the venv on the dev box is 3.13).
- **Classes:** PascalCase. **Functions:** snake_case. **Constants:** UPPER_SNAKE_CASE. **Private:** `_underscore`.
- **Plugin module names:** `{tool}_plugin.py` under `kast/plugins/`.
- **Plugin class names:** PascalCase ending in `Plugin` (e.g., `WhatWebPlugin`).
- **Plugin `name` attribute:** `lowercase_with_underscores`.
- **Test files:** `test_{module}.py` under `kast/tests/`.
- **Imports:** stdlib, third-party, local — separated by a blank line; absolute imports rooted at `kast.*`.
- **Errors:** never crash the orchestrator. Wrap external calls in try/except; on failure return a `get_result_dict("fail", message, timestamp)` so post-processing can still emit a `_processed.json` with `disposition: fail`. kast-web's state machine depends on the completion marker.
- **Comments:** default to none. Only add a comment when the *why* is non-obvious — a hidden constraint, a subtle invariant, a workaround for a specific bug.
- **Timestamps:** `datetime.now(timezone.utc).isoformat(timespec="milliseconds")`. **Never use the deprecated `datetime.utcnow()`.**
- **Severity values:** use `Severity` enum from `kast/core/severity.py`. Never write bare severity strings in code that produces or compares severity.
- **Atomic writes:** all `*_processed.json`, `kast_info.json`, `zap_scan_progress.json`, and `missing_issue_ids.json` writes go through `write_json_atomic` from `kast/core/atomic.py`.
- **No emojis** in code or generated docs unless explicitly requested.

---

## Plugin Development Guide

### Two base classes

| Use this base                  | When                                                                       |
| ------------------------------ | -------------------------------------------------------------------------- |
| `ExternalToolPlugin`           | The plugin wraps a CLI tool: invoke via subprocess, read its output file.  |
| `KastPlugin` (the abstract base) | The plugin doesn't shell out to a tool — pure Python (e.g., HTTP API calls, file analysis). |

`ExternalToolPlugin` collapses ~300 lines of subprocess/output-reading/processed-dict boilerplate that v2 plugins re-implemented individually. **Prefer it for new tool-wrapper plugins.**

### Identity is class attributes

In v3, plugin identity is **declared as class attributes** — never set in `__init__`. The "set self.name BEFORE super().__init__()" footgun from v2 is gone. Schemas are collected from the class without instantiation via `ConfigManager.collect_schemas_from_classes(...)`.

```python
class MyToolPlugin(ExternalToolPlugin):
    priority = 50

    # Identity (class attributes — never mutated in __init__)
    name = "my_tool"
    display_name = "My Tool"
    description = "What this plugin does."
    website_url = "https://example.com/my_tool"
    scan_type = "passive"          # "passive" | "active"
    output_type = "file"

    # ExternalToolPlugin-specific class attributes
    tool_binary = "my_tool"        # used by auto is_available()
    output_filename = "my_tool.json"
    output_format = "json"         # "json" | "text"

    config_schema = {
        "type": "object",
        "title": "My Tool Configuration",
        "description": "Configuration for the my_tool wrapper",
        "properties": {
            "timeout": {
                "type": "integer", "default": 300, "minimum": 30,
                "description": "Subprocess timeout in seconds",
            },
        },
    }

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self.timeout = self.get_config("timeout", 300)

    def build_command(self, target, output_path):
        return ["my_tool", "-o", output_path, "-t", str(self.timeout), target]

    def count_findings(self, findings):
        return len(findings) if isinstance(findings, list) else 0

    # Optional hooks — sensible defaults exist
    # parse_findings, extract_issues, format_summary, format_details,
    # format_executive_summary, extra_processed_fields, get_dry_run_info
```

### Required and optional `ExternalToolPlugin` hooks

Required:

- `build_command(target, output_path) -> list[str]` — argv list to run.
- `count_findings(findings) -> int` — primary-finding count.

Optional, with sensible defaults:

- `parse_findings(raw)` — normalize raw output (default: pass-through).
- `extract_issues(findings) -> list` — issue-registry IDs (default: `[]`).
- `format_summary(findings)` — report summary (default: generic message).
- `format_details(findings) -> str` — report details (default: empty).
- `format_executive_summary(findings, issues)` — exec-summary line (default: empty).
- `extra_processed_fields(findings, issues) -> dict` — extra processed-dict keys (default: `{}`).
- `get_dry_run_info(target, output_dir) -> dict` — dry-run preview (default: just the command).

The base provides `is_available()` (via `shutil.which(tool_binary)`), `run()` (subprocess + timeout + return-code + missing-output handling), and `post_process()` (atomic processed-dict write through the hooks above). Override `run()` only when there's a tool-specific quirk the base can't cover (the `wafw00f_plugin.py` HTTPS→HTTP TLS-error retry is the canonical example).

### Pure-Python plugins — `KastPlugin` directly

A handful of plugins don't wrap a CLI tool (HTTP API calls, file-system analysis, etc.). These inherit from `KastPlugin` directly and implement `is_available`, `run`, and `post_process` themselves. See `mozilla_observatory_plugin.py` and `ai_surface_detection_plugin.py` for the shape.

### Plugin lifecycle

1. Discovery: `PluginRegistry.discover()` walks `kast/plugins/*_plugin.py` and collects classes whose `__module__` matches the file (so the imported `ExternalToolPlugin` symbol isn't picked up as a plugin).
2. Instantiation: `PluginRegistry.all_instances()` lazily instantiates each class with `cli_args` and `config_manager`, caches by name, sorts by `priority`.
3. Run: `ScannerOrchestrator` calls `run(target, output_dir, report_only)` per plugin (sequential or parallel), respecting `dependencies`.
4. Post-process: orchestrator calls `post_process(raw_output, output_dir)`, which writes `<plugin>_processed.json` atomically.
5. Report: `collect_report_data(plugin_results, target)` builds a single dict; `render_html` and `render_pdf` consume it.

### Dependencies

```python
self.dependencies = [
    {"plugin": "mozilla_observatory",
     "condition": lambda r: r.get("disposition") == "success"},
]
```

The orchestrator gates execution: a plugin is launched only when each declared dependency has run *and* its `condition` returns truthy.

### Available plugins (current)

| Plugin                  | Display Name              | Type    | Priority | Base                  | Dependencies         |
| ----------------------- | ------------------------- | ------- | -------- | --------------------- | -------------------- |
| `org_discovery`         | Organization Discovery    | Passive | 3        | `KastPlugin`          | None                 |
| `mozilla_observatory`   | Mozilla Observatory       | Passive | 5        | `KastPlugin`          | None                 |
| `script_detection`      | External Script Detection | Passive | 10       | `KastPlugin`          | mozilla_observatory  |
| `subfinder`             | Subfinder                 | Passive | 10       | `KastPlugin`          | None                 |
| `wafw00f`               | Wafw00f                   | Passive | 10       | `ExternalToolPlugin`  | None                 |
| `whatweb`               | WhatWeb                   | Passive | 15       | `ExternalToolPlugin`  | None                 |
| `related_sites`         | Related Sites Discovery   | Passive | 45       | `KastPlugin`          | None                 |
| `ftap`                  | Find The Admin Panel      | Passive | 50       | `KastPlugin`          | None                 |
| `testssl`               | Test SSL                  | Passive | 50       | `KastPlugin`          | None                 |
| `katana`                | Katana                    | Passive | 60       | `KastPlugin`          | None                 |
| `ai_surface_detection`  | AI Surface Detection      | Passive | 70       | `KastPlugin`          | None                 |
| `zap`                   | OWASP ZAP                 | Active  | 200      | `KastPlugin`          | None                 |

Lower priority number = runs earlier.

### Creating a new plugin

`kast/plugins/template_plugin.py` is the canonical starting point — it uses the v3 class-attribute identity shape and the canonical `__init__(self, cli_args, config_manager=None)` signature. Discovery deliberately skips this file by name. **For tool-wrapper plugins, copy and adapt; for new plugins, prefer inheriting from `ExternalToolPlugin` rather than `KastPlugin` directly.**

The `kast/scripts/create_plugin.py` wizard exists but predates the `ExternalToolPlugin` base; treat its output as v2-shaped and migrate as you adapt it.

---

## Configuration System

### Overview

YAML-based configuration managed by `ConfigManager` (`kast/config_manager.py`). Plugin schemas are **class attributes** and collected via `ConfigManager.collect_schemas_from_classes(...)` without instantiating plugins. This is the path used by `kast config schema`, `kast config init`, and `kast config show`.

### Priority (highest → lowest)

1. CLI overrides (`--set plugin.key=value`)
2. Project config (`./kast_config.yaml`)
3. User config (`~/.config/kast/config.yaml`)
4. System config (`/etc/kast/config.yaml`)
5. Plugin defaults (from `config_schema`)

### Config file format

```yaml
kast:
  config_version: "1.0"
global:
  timeout: 300
  retry_count: 2
plugins:
  related_sites:
    httpx_rate_limit: 10
    subfinder_timeout: 300
    httpx_ports: [80, 443, 8080, 8443]
  testssl:
    timeout: 600
```

### CLI config commands

```bash
kast config init                                         # write default config
kast config show                                         # show merged config
kast config schema                                       # export merged JSON schema
kast scan --config /path/to/config.yaml --target X       # use a specific config
kast scan --target X --set related_sites.httpx_rate_limit=20  # override one key
```

### `ConfigManager` API (key entries)

- `load(config_file=None)` — load from a path or search the default locations.
- `register_plugin_schema(name, schema)` — register a single schema.
- `collect_schemas_from_classes(classes)` — register every plugin's schema from a list of classes.
- `get_plugin_config(name)` — merged config dict for one plugin.
- `validate_plugin_config(name, config)` — validate against schema.
- `export_schema(format="json")` — export all schemas.
- `create_default_config(path=None)` — write the default config.

### Reading config in a plugin

```python
def __init__(self, cli_args, config_manager=None):
    super().__init__(cli_args, config_manager)
    self.timeout = self.get_config("timeout", 300)
    self.rate_limit = self.get_config("rate_limit", 10)
```

`self.get_config(key, default)` reads from the merged config; `default` only applies if neither config nor schema provide a value.

---

## CLI Surface

The v3 CLI is **Click-based subcommands**. The legacy v2 argv shape (`kast --target X --mode passive ...`) is preserved through a translation wrapper in `kast/cli/__init__.py:_translate_v2_argv()` so kast-web (which still issues v2-style invocations) keeps working unchanged.

```
kast version
kast config (init | show | schema)
kast scan --target TARGET [options]
kast scan list                # list past scans under ~/kast_results
kast scan show DIR            # show details of one past scan
kast scan rerun DIR           # re-render reports from existing scan dir
kast plugins (list | show | deps)
kast registry (list | add | promote)
kast doctor [--json]
kast self-update [options]
```

Notable scan options: `--mode {active|passive|both}`, `--parallel`, `--max-workers N`, `--dry-run`, `--report-only DIR` (deprecated alias of `scan rerun`), `--zap-profile {quick|standard|thorough|api|passive}`, `--run-only PLUGIN[,PLUGIN...]`, `--config FILE`, `--set k=v`, `--logo PATH`, `--output-dir PATH`.

`kast doctor` exit codes: any FAIL → exit 1; all OK or only WARN → exit 0. WARN alone never fails CI.

`kast plugins list --json` is the v3-native discovery endpoint kast-web should migrate to (it currently parses `kast -ls` text output).

### Adding a new subcommand

Create a module under `kast/cli/`, define the Click group/command there, and `add_command` it from `cli/main.py`. Do **not** reintroduce argparse logic in `kast/main.py` — that file is a 13-line shim.

---

## Reporting Pipeline

v3 has a **unified report pipeline**. Both renderers consume the same data structure.

```
collect_report_data(plugin_results, target) -> dict
  render_html(data, output_path, logo_path)
  render_pdf(data, output_path, logo_path)
```

Differences between HTML and PDF:

- Template selection (`report_template.html` vs `report_template_pdf.html`).
- JSON pre-rendering (PDF only).
- CSS placement (HTML copies `kast_style.css` next to the report; PDF embeds via WeasyPrint).
- Logo embedding (PDF base64-inlines; HTML references the file by name).
- Exec-summary anchor links (HTML only — interactive nav).

**Never reintroduce parallel HTML/PDF data-prep code paths.** New shared work goes into `collect_report_data`. The legacy `kast.report_builder` module is a compatibility shim that re-exports from `kast.report`; new code imports from `kast.report` directly.

Helpers (`format_multiline_text`, `format_json_for_pdf`, `infer_issue_metadata`, etc.) live in `kast/report/helpers.py`.

### Custom HTML widgets

In v3, plugins emit a **single rich payload** for report widgets. The v2 dual-field requirement (`custom_html` + `custom_html_pdf`) is gone — the renderers handle format-specific differences. A plugin returning `extra_processed_fields = {"custom_html": "<div>...</div>"}` is enough.

### Long-string wrapping

v3 handles long URLs and other long strings via CSS rules (`overflow-wrap: anywhere` on `.report-paragraph`, `.json-string`, `.json-key`, `.issue-description`, `td`, etc.) in `kast_style.css` and `kast_style_pdf.css`. **Don't reintroduce `<wbr>`-injection in Python.** WeasyPrint accepts `overflow-wrap: anywhere` but rejects `word-break: break-word` (non-standard CSS); use `word-break: break-all` for extra-aggressive PDF breaking.

### Jinja macros

`kast/templates/_macros.html` holds shared rendering primitives. Both report templates do `{% import "_macros.html" as kast %}`. Currently `kast.tool_anchor(name)` is the only macro (anchor-ID generation). Add new macros only when the same logic is duplicated across HTML and PDF templates. `templates/partials/` exists for shared template blocks but is intentionally empty — see its README for criteria.

---

## ZAP Integration

### Execution modes (in kast)

1. **Local** — Docker-based ZAP on the local machine.
2. **Remote** — connect to an existing ZAP via HTTP API.

The **Cloud** mode (Terraform-provisioned infrastructure) was removed in Phase D10. Cloud ZAP provisioning is now handled entirely by kast-web before the kast CLI is invoked; kast receives the resulting URL and API key via `--set zap.execution_mode=remote`.

### Architecture

```
ZapPlugin (kast/plugins/zap_plugin.py)
  +-- ZapProviderFactory (kast/scripts/zap_provider_factory.py)
  |   +-- LocalZapProvider (Docker)
  |   +-- RemoteZapProvider (SSH+API)
  +-- ZAPAPIClient (kast/scripts/zap_api_client.py)
  +-- SSHExecutor (kast/scripts/ssh_executor.py) — remote mode only
  +-- Automation Plans (kast/config/zap_automation_*.yaml)
      quick (~20min), standard (~45min), thorough (~90min),
      api (~30min), passive (~15min)
```

### ZAP profile shortcut

```bash
kast scan --target example.com --mode active --zap-profile quick
kast scan --target example.com --mode active --zap-profile thorough
```

Profile path resolution is rooted at the kast package directory (`Path(__file__).resolve().parent / "config" / ...`), not the cwd — this fixed the v2.14 cwd-dependent bug where running kast from anywhere other than its install dir broke `--zap-profile`.

---

## Testing Standards

### Structure

- **Framework:** pytest (with some legacy unittest-style tests still around).
- **Location:** `kast/tests/test_*.py`.
- **Helpers:** `kast/tests/helpers/config_test_helpers.py`.
- **Baseline scan:** `docs/baseline-v2.14/sample-scan-1/` — reference for processed-dict structure and report output.

### Running tests

```bash
PYTHONPATH=. pytest kast/tests/                   # all tests
PYTHONPATH=. pytest kast/tests/test_cli_scan.py   # one file
PYTHONPATH=. pytest -v kast/tests/                # verbose
PYTHONPATH=. pytest --cov=kast kast/tests/        # coverage
```

### Coverage goals

- Plugin methods: 80%+
- Critical paths: 100%
- Error handling: both success and failure cases
- Config: schema validation, defaults, overrides

### Test groups

- **CLI** — `test_cli_scan`, `test_cli_plugins`, `test_cli_registry`, `test_cli_doctor`, `test_cli_self_update`, `test_cli_v2_compat`
- **Plugin base** — `test_external_tool_base`
- **Per-plugin** — `test_ftap_*`, `test_katana_*`, `test_observatory_*`, `test_related_sites_*`, `test_subfinder_*`, `test_testssl_*`, `test_wafw00f_*`, `test_whatweb_*`, `test_zap_*`, `test_ai_surface_detection`
- **Reports** — `test_report_builder`, `test_report_only`, `test_html_list_structure`, `test_pdf_navigation`, `test_baseline_render`
- **Core** — `test_atomic`, `test_registry`, `test_config_manager_schemas`
- **General** — `test_executive_summary`, `test_kast_info`, `test_tool_index`

---

## Common Patterns

1. **Debug logging:** `self.debug(f"Processing {len(findings)} findings")` — never `print()`.
2. **Result dictionary:** `self.get_result_dict(disposition, results, timestamp)` — never construct manually.
3. **Atomic JSON writes:** `from kast.core.atomic import write_json_atomic; write_json_atomic(path, data)` — never `with open(path, "w"): json.dump(...)` for state-bearing files.
4. **Severity values:** `from kast.core.severity import Severity; severity = Severity.from_registry(value)` — never bare strings.
5. **Subprocess execution:** in `ExternalToolPlugin`, the base handles this. For non-tool plugins, use `subprocess.run(cmd, capture_output=True, text=True, timeout=N, check=False)`.
6. **Issue references:** push registry IDs into `issues`: `issues.append("MISSING_HSTS")`. The report layer resolves them.
7. **Findings count:** always include `findings_count` (integer) in processed output. kast-web uses it on the scan-details page.
8. **Config-aware code:** read every tunable via `self.get_config("key", default)`.
9. **Report-only mode:** every plugin's `run()` must handle `report_only=True` (the `ExternalToolPlugin` base handles this for you).
10. **Thread safety:** when writing to shared state in parallel mode, use `threading.Lock()`.
11. **Timestamps:** `datetime.now(timezone.utc).isoformat(timespec="milliseconds")`.

---

## Key Concepts

### Scan types

- **Passive** — non-intrusive, read-only-from-target's-perspective (default).
- **Active** — intrusive; requires `--mode active`. Active scans must never look like attacks against a customer's infrastructure.

### Execution modes

- **Sequential** — one plugin at a time (default).
- **Parallel** — concurrent with `--parallel`, capped at `--max-workers`.
- **Report-only** — regenerate reports from existing scan data (`kast scan rerun DIR`).
- **Dry-run** — preview without executing tools (`--dry-run`).

### Issue registry

Central database at `kast/data/issue_registry.json`:

- Issue ID
- Display Name
- Description
- Severity (`Critical | High | Medium | Low | Informational`) — note the registry uses `"Informational"`; the v2 spelling `"Info"` is normalized via `Severity.from_registry`. The badge label text is rendered as "Info" for visual brevity, but that's a display-only abbreviation.
- Category (HTTPS, Headers, Configuration, etc.)
- Talking Points (remediation guidance)

Workflow:

```bash
kast registry list                            # list entries
kast registry add ID --severity High --category Headers ...  # add one
kast registry promote SCAN_DIR                # walk through missing_issue_ids.json
kast registry promote SCAN_DIR --accept-all   # CI-friendly accept everything
```

When a plugin reports an issue ID that isn't in the registry, the missing IDs end up in `missing_issue_ids.json` in the scan dir — feed that file to `kast registry promote` to add them.

### Output structure

```
~/kast_results/example.com-20260206-143022/
  kast_report.html
  kast_report.pdf
  kast_info.json
  kast_style.css
  missing_issue_ids.json     (if any)
  zap_scan_progress.json     (during/after a ZAP scan)
  {plugin}.json              (raw tool output)
  {plugin}_processed.json    (post-processed, kast-web/report consumer)
```

---

## File Organization

```
kast/
  main.py              - 13-line shim into kast.cli.main()
  orchestrator.py      - ScannerOrchestrator (plugin lifecycle, parallel exec)
  registry.py          - PluginRegistry (discovery, instantiation, caching)
  config_manager.py    - YAML configuration system
  config.py            - legacy global constants
  utils.py             - discover_plugins, show_dependency_tree
  report_builder.py    - thin compat shim re-exporting from kast.report

  cli/
    __init__.py        - main() entry + _translate_v2_argv
    main.py            - Click root group; subcommand registration
    _shared.py         - cross-module helpers
    scan.py            - scan + list/show/rerun
    plugins.py         - plugins list/show/deps
    registry.py        - registry list/add/promote
    doctor.py          - environment health check
    self_update.py     - update wrapper

  core/
    severity.py        - Severity enum + from_registry()
    atomic.py          - write_json_atomic

  plugins/
    base.py            - KastPlugin ABC
    external_tool.py   - ExternalToolPlugin(KastPlugin) base
    template_plugin.py - canonical v3 starter (skipped by discovery)
    *_plugin.py        - the actual plugins (12 real ones today)

  report/
    __init__.py        - public API: collect_report_data, render_html, render_pdf
    data.py            - collect_report_data
    helpers.py         - format_multiline_text, format_json_for_pdf, ...
    html.py            - render_html
    pdf.py             - render_pdf

  config/
    default_config.yaml      - default configuration
    zap_automation_*.yaml    - ZAP scan profiles (5: quick, standard, thorough, api, passive)
    zap_config.yaml          - ZAP plugin configuration defaults

  data/
    issue_registry.json      - central issue database

  scripts/
    create_plugin.py         - plugin creation wizard (v2-shaped output)
    zap_api_client.py        - ZAP HTTP API wrapper
    zap_providers.py         - LocalZapProvider and RemoteZapProvider

  templates/
    report_template.html         - interactive HTML template
    report_template_pdf.html     - PDF template
    _macros.html                 - shared Jinja macros
    partials/                    - shared blocks (empty, see README)
    kast_style.css               - HTML styles
    kast_style_pdf.css           - PDF styles (WeasyPrint)

  tests/
    test_*.py                    - tests
    helpers/                     - test helpers

docs/
  v3-planning/                   - phase 1-3 planning docs
  baseline-v2.14/                - reference baseline scans
  web-integration.md             - frozen kast↔kast-web contract
```

---

## Integration Points

### Plugin → Orchestrator

`PluginRegistry.discover()` walks `kast/plugins/*_plugin.py` and collects classes inheriting from `KastPlugin` (skipping the imported `ExternalToolPlugin` base via an `__module__` filter). `PluginRegistry.all_instances()` lazily instantiates each class and sorts by `priority`. `ScannerOrchestrator` takes the resulting list of **instances** (not classes) and runs them, filtered by `--mode`.

### Plugin → Report

Each plugin's `post_process()` returns a path to `<name>_processed.json`. `collect_report_data` reads every processed file in the scan dir, extracts the standard fields (findings, summary, details, issues, executive_summary, custom_html, ...), and assembles a single dict. `render_html` and `render_pdf` consume that dict.

### Plugin → Config

Plugins declare `config_schema` as a class attribute. `ConfigManager.collect_schemas_from_classes(plugin_classes)` registers every schema without instantiation. Plugins read merged config via `self.get_config(key, default)`.

### Plugin → Issue Registry

Plugins push registry IDs into `issues` (a list). The report layer resolves IDs to full entries (severity, description, category, talking points) when rendering. Unresolved IDs accumulate in `missing_issue_ids.json` for follow-up via `kast registry promote`.

### kast → kast-web

kast-web watches the scan output directory and parses `*_processed.json` files. The contract is **frozen** for v3.0; see [Frozen Contracts](#frozen-contracts) and `docs/web-integration.md`.

### ZAP provider chain

`ZapPlugin` → `LocalZapProvider | RemoteZapProvider` → `ZAPAPIClient`. `ZapProviderFactory`, `SSHExecutor`, and the Terraform-driven cloud provider chain were removed in Phase D10.

---

## Frozen Contracts

These surfaces are **frozen** for v3.0. Do not change them without explicit, coordinated planning.

1. **kast↔kast-web contract** documented in `docs/web-integration.md`:
    - **Atomic writes** — every state-bearing file goes through `write_json_atomic` (writes `.tmp` then `os.replace`). kast-web watchers must never see a partial JSON file.
    - **Frozen filenames** — `<plugin>.json`, `<plugin>_processed.json`, `kast_info.json`, `zap_scan_progress.json`, `missing_issue_ids.json`.
    - **File-presence state machine** — kast-web infers progress from which files exist.
    - **`zap_scan_progress.json` channel** — used to surface ZAP progress to kast-web.

2. **v2 CLI argv contract** — the `kast --target X --mode passive ...` shape. Preserved through v3.0 via the `_translate_v2_argv()` wrapper. **15 tests pin this contract** (`test_cli_v2_compat.py`).

3. **`_processed.json` per-plugin output format**, including the kebab-case keys (`plugin-name`, `plugin-display-name`, `plugin-website-url`, etc.) and the `findings | findings_count | summary | details | issues | executive_summary | report` shape.

4. **Issue registry data format** in `kast/data/issue_registry.json`.

Internal refactoring is free as long as these surfaces stay stable. Phase B9's two plugin migrations (whatweb, wafw00f) shipped byte-for-byte compatible output against `docs/baseline-v2.14/sample-scan-1/` as proof the contract holds.

---

## Prompt Engineering Tips

When working with KAST as a GenAI assistant:

1. **Read `CLAUDE.md` first** — it's the active-phase override and tells you what's in flight right now.
2. **Then read this file** for v3 patterns and architecture.
3. **For tool-wrapper plugins, prefer `ExternalToolPlugin`** over direct `KastPlugin` subclassing.
4. **Identity is class attributes** — never set `self.name`, `self.display_name`, etc. in `__init__`.
5. **Use `self.get_result_dict()`** — never construct result dicts manually.
6. **Atomic writes for state-bearing files** — `write_json_atomic`, never raw `json.dump`.
7. **Severity via the enum** — `Severity.from_registry(value)`, never bare strings.
8. **Timestamps** — `datetime.now(timezone.utc).isoformat(timespec="milliseconds")`. Never `datetime.utcnow()`.
9. **Handle `report_only=True`** in every `run()` (the `ExternalToolPlugin` base handles this for you).
10. **Always include `findings_count`** (integer) in processed output.
11. **Map findings to issue-registry IDs** where applicable.
12. **`self.debug()`** for verbose logging, not `print()`.
13. **`is_available()`** must return False gracefully when the tool is missing.
14. **Never crash the orchestrator** — wrap external calls in try/except and return a fail-disposition result dict.
15. **Don't change frozen contracts** without explicit coordinated planning — see [Frozen Contracts](#frozen-contracts).
16. **There is no cloud-mode code in kast** — that subsystem was removed in Phase D10 and lives in kast-web.

### Common tasks

- **Add a tool-wrapper plugin:** copy `template_plugin.py`, change the base to `ExternalToolPlugin`, declare `tool_binary` / `output_filename` / `output_format`, implement `build_command` and `count_findings`, override format hooks as needed.
- **Add a non-wrapper plugin:** inherit from `KastPlugin` directly; implement `is_available`, `run`, `post_process`.
- **Add an issue:** `kast registry add ID --severity ... --category ...` (atomic write), or use `kast registry promote SCAN_DIR` to walk through entries from `missing_issue_ids.json`.
- **Add a config option:** add to the plugin's `config_schema`, read it with `self.get_config(key, default)`, and update `kast/config/default_config.yaml` if appropriate.
- **Add a CLI subcommand:** create a module under `kast/cli/`, define the Click group/command, `add_command` it from `cli/main.py`. Don't reintroduce argparse in `kast/main.py`.
- **Fix a report bug:** check `kast/report/data.py` first (shared data prep), then the appropriate template + CSS. Don't introduce parallel HTML/PDF data paths.
- **Investigate a kast-web integration issue:** start at `docs/web-integration.md`. Confirm atomic-write usage and filename stability before changing anything else.
