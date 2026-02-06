# KAST GenAI Instructions

This document provides comprehensive guidance for GenAI assistants working with the KAST (Kali Automated Scan Tool) project.

**Version:** 2.14.3
**Last Updated:** February 2026
**Project Repository:** https://github.com/mercutioviz/kast

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture & Design Patterns](#architecture--design-patterns)
3. [Code Style & Conventions](#code-style--conventions)
4. [Plugin Development Guide](#plugin-development-guide)
5. [Configuration System](#configuration-system)
6. [ZAP Integration & Cloud Infrastructure](#zap-integration--cloud-infrastructure)
7. [Testing Standards](#testing-standards)
8. [Common Patterns](#common-patterns)
9. [Key Concepts](#key-concepts)
10. [File Organization](#file-organization)
11. [Integration Points](#integration-points)
12. [Prompt Engineering Tips](#prompt-engineering-tips)

---

## Project Overview

### What is KAST?

KAST is a modular, extensible Python framework for automating web application security scanning tools. It orchestrates multiple security tools (Script Detection, WhatWeb, TestSSL, Wafw00f, Subfinder, Katana, Observatory, Related Sites, FTAP, OWASP ZAP), aggregates findings, and generates comprehensive HTML and PDF reports with executive summaries.

### Core Purpose

- **Orchestrate** multiple security scanning tools in a unified workflow
- **Standardize** output formats across different tools
- **Generate** professional reports (HTML/PDF) with executive summaries
- **Centralize** security issue definitions with remediation guidance
- **Enable** both parallel and sequential execution modes
- **Support** active and passive scanning methodologies
- **Configure** plugins via YAML config files with CLI overrides
- **Provision** cloud infrastructure for remote ZAP scanning (AWS/Azure/GCP)

### Key Features

- Modular plugin architecture for easy extensibility
- Parallel execution with dependency resolution
- Priority-based plugin scheduling
- Issue registry with severity ratings and remediation guidance
- Report-only mode for regenerating reports from existing data
- Dry-run mode for previewing execution
- Rich CLI with progress indicators
- Comprehensive logging infrastructure
- YAML-based configuration system with CLI overrides
- ZAP multi-mode scanning (local Docker, remote, cloud)
- Cloud infrastructure provisioning via Terraform
- Plugin dependency tree visualization (`--show-deps`)
- Plugin creation wizard (`kast/scripts/create_plugin.py`)

---

## Architecture & Design Patterns

### High-Level Architecture

```
CLI Entry Point (kast/main.py)
  -> Configuration Manager (kast/config_manager.py)
    -> Scan Orchestrator (kast/orchestrator.py)
      -> Plugin System (kast/plugins/*.py)
        -> External Tools | Internal Plugins | ZAP Provider System
      -> Report Builder (kast/report_builder.py)
```

**ConfigManager:** YAML config loading, plugin schema registration, CLI override merging, config export.
**Orchestrator:** Plugin lifecycle, parallel/sequential execution, dependency resolution, timing.
**Plugins:** Each wraps a security tool, inherits KastPlugin, implements is_available/run/post_process/get_dry_run_info.
**ZAP Providers:** Local (Docker), Remote (SSH+API), Cloud (Terraform for AWS/Azure/GCP).
**Report Builder:** Aggregates results, executive summaries, HTML+PDF dual-template reports via Jinja2.

### Design Patterns

1. **Strategy** - Plugin architecture with KastPlugin interface
2. **Template Method** - Base class lifecycle with overridable methods
3. **Factory** - ZapProviderFactory for provider creation
4. **Observer** - Plugin dependency system
5. **Builder** - ReportBuilder for complex reports
6. **Provider** - ZapInstanceProvider ABC with Local/Remote/Cloud

### PDF Reports

Dual-template: `report_template.html` + `kast_style.css` for interactive HTML; `report_template_pdf.html` + `kast_style_pdf.css` for static PDF via WeasyPrint. Plugins provide both `custom_html` and `custom_html_pdf` fields.

---

## Code Style & Conventions

- **Python 3.9+** (tested 3.9-3.11), modern type hints
- **Classes:** PascalCase, **Functions:** snake_case, **Constants:** UPPER_SNAKE_CASE, **Private:** _underscore
- **Plugin names:** lowercase_with_underscores
- **Files:** `{tool}_plugin.py`, `test_{module}.py`, `UPPERCASE_TITLE.md`
- **Imports:** stdlib, third-party, local
- **Errors:** try-except, `self.get_result_dict("fail", msg)`, never crash orchestrator

---

## Plugin Development Guide

### Lifecycle

1. `__init__(cli_args, config_manager=None)` - Set attrs BEFORE `super().__init__()`
2. `is_available()` - Check tool in PATH
3. `setup(target, output_dir)` - Optional
4. `run(target, output_dir, report_only)` - Execute scan, handle report-only
5. `post_process(raw_output, output_dir)` - Normalize output to JSON
6. `get_dry_run_info(target, output_dir)` - Preview mode

### Creating Plugins

Use `python kast/scripts/create_plugin.py` or copy `kast/plugins/template_plugin.py`.

### Required Structure

```python
class MyPlugin(KastPlugin):
    priority = 50
    config_schema = {
        "type": "object", "title": "My Plugin Configuration",
        "properties": {
            "timeout": {"type": "integer", "default": 300, "minimum": 30}
        }
    }

    def __init__(self, cli_args, config_manager=None):
        self.name = "my_plugin"
        self.display_name = "My Plugin"
        self.description = "What this plugin does"
        self.website_url = "https://tool.com"
        self.scan_type = "passive"
        self.output_type = "file"
        self.dependencies = []
        super().__init__(cli_args, config_manager)
        self._load_plugin_config()

    def _load_plugin_config(self):
        self.timeout = self.get_config("timeout", 300)

    def is_available(self): return shutil.which("toolname") is not None

    def run(self, target, output_dir, report_only):
        # Handle report_only first, then execute command
        return self.get_result_dict("success", results, timestamp)

    def post_process(self, raw_output, output_dir):
        # Return processed JSON with required fields
        processed = {
            "plugin-name": self.name, "plugin-display-name": self.display_name,
            "plugin-description": self.description, "plugin-website-url": self.website_url,
            "timestamp": "...", "findings": {}, "findings_count": 0,
            "summary": "...", "details": "...", "issues": [],
            "executive_summary": [], "custom_html": "...", "custom_html_pdf": "..."
        }
        # Save and return path

    def get_dry_run_info(self, target, output_dir):
        return {"commands": [...], "description": self.description, "operations": "..."}
```

### Dependencies

```python
self.dependencies = [{'plugin': 'mozilla_observatory',
    'condition': lambda r: r.get('disposition') == 'success'}]
```

### Available Plugins (v2.14.3)

| Plugin | Display Name | Type | Priority | Dependencies |
|--------|--------------|------|----------|--------------|
| mozilla_observatory | Mozilla Observatory | Passive | 5 | None |
| script_detection | External Script Detection | Passive | 10 | mozilla_observatory |
| subfinder | Subfinder | Passive | 10 | None |
| wafw00f | Wafw00f | Passive | 10 | None |
| whatweb | WhatWeb | Passive | 15 | None |
| related_sites | Related Sites Discovery | Passive | 45 | None |
| ftap | Find The Admin Panel | Passive | 50 | None |
| testssl | Test SSL | Passive | 50 | None |
| katana | Katana | Passive | 60 | None |
| zap | OWASP ZAP | Active | 200 | None |

### Priority: 5 (Observatory) -> 10 (Script/Sub/WAF) -> 15 (WhatWeb) -> 45-50 (Related/FTAP/SSL) -> 60 (Katana) -> 200 (ZAP)

> **Note:** `template_plugin.py` uses old signature. New plugins: `def __init__(self, cli_args, config_manager=None):`


---

## Configuration System

### Overview

YAML-based config managed by `ConfigManager` (`kast/config_manager.py`).

### Priority (highest to lowest)

1. CLI overrides (`--set plugin.key=value`)
2. Legacy CLI arguments (deprecated)
3. Project config (`./kast_config.yaml`)
4. User config (`~/.config/kast/config.yaml`)
5. System config (`/etc/kast/config.yaml`)
6. Plugin defaults (from `config_schema`)

### Config File Format

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

### CLI Config Commands

```bash
kast --config-init                # Create default config
kast --config-show                # Show merged config
kast --config-schema              # Export JSON schema
kast --config /path/to/config.yaml --target example.com
kast --target example.com --set related_sites.httpx_rate_limit=20
```

### ConfigManager API

- `load(config_file=None)` - Load config from file or search defaults
- `register_plugin_schema(name, schema)` - Register plugin schema
- `get_plugin_config(name)` - Get merged config for plugin
- `validate_plugin_config(name, config)` - Validate against schema
- `export_schema(format="json")` - Export all schemas
- `create_default_config(path=None)` - Generate default config file
- `show_current_config(plugin=None)` - Show current merged config

---

## ZAP Integration & Cloud Infrastructure

### Execution Modes

1. **Local** - Docker-based ZAP on local machine
2. **Remote** - Connect to existing ZAP via SSH/API
3. **Cloud** - Terraform-provisioned infrastructure (AWS/Azure/GCP)

### Architecture

```
ZapPlugin (kast/plugins/zap_plugin.py)
  +-- ZapProviderFactory (kast/scripts/zap_provider_factory.py)
  |   +-- LocalZapProvider (Docker)
  |   +-- RemoteZapProvider (SSH+API)
  |   +-- CloudZapProvider (Terraform)
  +-- ZAPAPIClient (kast/scripts/zap_api_client.py)
  +-- TerraformManager (kast/scripts/terraform_manager.py)
  |   +-- AWS, Azure, GCP (kast/terraform/*)
  +-- SSHExecutor (kast/scripts/ssh_executor.py)
  +-- Automation Plans (kast/config/zap_automation_*.yaml)
      quick (~20min), standard (~45min), thorough (~90min), api (~30min), passive (~15min)
```

### ZAP Profile Shortcut

```bash
kast --target example.com --mode active --zap-profile quick
kast --target example.com --mode active --zap-profile thorough
```

### Cloud Features

- Spot/preemptible instances with on-demand fallback
- Auto SSH key generation and infrastructure state tracking
- Orphaned resource cleanup (`cleanup_orphaned_resources.py`)
- Infrastructure diagnostics (`diagnose_infrastructure.py`)

### ZAP Docs

See `kast/docs/`: ZAP_MULTI_MODE_GUIDE.md, ZAP_CLOUD_PLUGIN_GUIDE.md, ZAP_PLUGIN_QUICK_REFERENCE.md, ZAP_REMOTE_MODE_QUICK_START.md, ZAP_SPOT_FALLBACK_FEATURE.md

---

## Testing Standards

### Structure

- Framework: Python unittest
- Location: `kast/tests/test_*.py`
- Config helpers: `kast/tests/helpers/config_test_helpers.py`

### Running Tests

```bash
python -m pytest kast/tests/                    # All tests
python -m pytest kast/tests/test_ftap_config.py # Specific
python -m pytest -v kast/tests/                 # Verbose
python -m pytest --cov=kast kast/tests/         # Coverage
```

### Coverage Goals

- Plugin methods: 80%+
- Critical paths: 100%
- Error handling: Both success and failure cases
- Config: Schema validation, defaults, overrides

### Existing Test Files

- **FTAP:** test_ftap_plugin, test_ftap_config, test_ftap_post_process
- **Katana:** test_katana_config
- **Observatory:** test_observatory_config
- **Related Sites:** test_related_sites_config, test_related_sites_error_handling, test_related_sites_filtering
- **Reports:** test_report_builder, test_report_only
- **Script Detection:** test_script_detection_config
- **Subfinder:** test_subfinder_config
- **TestSSL:** test_testssl_plugin, test_testssl_config, test_testssl_connection_failure, test_testssl_clientproblem
- **Wafw00f:** test_wafw00f_config
- **WhatWeb:** test_whatweb_config, test_whatweb_full_integration, test_whatweb_redirect
- **ZAP:** test_zap_config, test_zap_unified_config
- **General:** test_executive_summary, test_html_list_structure, test_pdf_navigation, test_kast_info, test_tool_index

---

## Common Patterns

1. **Debug Logging:** `self.debug(f"Processing {len(findings)} findings")`
2. **Result Dictionary:** Always use `self.get_result_dict(disposition, results, timestamp)`
3. **JSON File Handling:** Check `os.path.exists()` before `json.load()`
4. **Command Execution:** `subprocess.run(cmd, capture_output=True, text=True, timeout=N, check=False)`
5. **Issue Registry:** Reference by ID: `issues.append("MISSING_HSTS")`
6. **Executive Summary:** Return list of strings: `["Found 3 critical issues"]`
7. **Custom HTML Widgets:** Provide both `custom_html` (JS) and `custom_html_pdf` (static)
8. **Observatory Correlation:** Read Observatory results from output_dir
9. **Thread Safety:** Use `threading.Lock()` for shared data in parallel mode
10. **Command Formatting:** Include formatted command in processed output
11. **Config-Aware:** Use `self.get_config("key", default)` throughout

---

## Key Concepts

### Scan Types

- **Passive:** Non-intrusive, read-only (default)
- **Active:** Intrusive, requires `--mode active`

### Execution Modes

- **Sequential:** One at a time (default, safe)
- **Parallel:** Concurrent with `--parallel`
- **Report-Only:** Regenerate from data with `--report-only dir`
- **Dry-Run:** Preview with `--dry-run`

### Issue Registry

Central database (`kast/data/issue_registry.json`):
- Issue ID, Display Name, Description
- Severity: Critical, High, Medium, Low, Info
- Category: HTTPS, Headers, Configuration, etc.
- Talking Points (remediation guidance)

### Output Structure

```
~/kast_results/example.com-20260206-143022/
  kast_report.html
  kast_report.pdf
  kast_info.json
  kast_style.css
  {plugin}.json / {plugin}_processed.json (per plugin)
```

---

## File Organization

```
kast/
  main.py              - CLI entry point, argument parsing
  orchestrator.py      - Plugin lifecycle and execution
  report_builder.py    - HTML/PDF report generation
  report_templates.py  - Report template helpers
  config.py            - Legacy configuration
  config_manager.py    - YAML configuration system
  utils.py             - Utilities, plugin discovery, dep tree

  plugins/
    base.py            - KastPlugin ABC
    template_plugin.py - New plugin template
    *_plugin.py        - Individual plugins (10 total)

  config/
    default_config.yaml      - Default configuration
    zap_config.yaml          - ZAP configuration
    zap_cloud_config.yaml    - Cloud ZAP config
    zap_automation_*.yaml    - ZAP scan profiles (5)
    nginx/                   - Nginx configs for ZAP proxy

  data/
    issue_registry.json      - Central issue database

  scripts/
    create_plugin.py         - Plugin creation wizard
    zap_providers.py         - ZAP provider implementations
    zap_provider_factory.py  - Provider factory
    zap_api_client.py        - ZAP API client
    terraform_manager.py     - Terraform provisioning
    ssh_executor.py          - SSH command execution
    monitor_zap.py           - ZAP monitoring
    cleanup_orphaned_resources.py - Cloud cleanup
    diagnose_infrastructure.py    - Infra diagnostics

  templates/
    report_template.html     - Interactive HTML template
    report_template_pdf.html - PDF template
    kast_style.css           - HTML styles
    kast_style_pdf.css       - PDF styles

  terraform/
    aws/, azure/, gcp/       - Cloud provider modules

  tests/
    test_*.py                - Unit tests
    helpers/                 - Test helpers

  docs/
    *.md                     - Feature documentation
```

---

## Integration Points

### Plugin-to-Orchestrator

Orchestrator discovers plugins via `utils.discover_plugins()`, which scans `kast/plugins/` for classes inheriting from `KastPlugin`. Plugins are sorted by `priority` and filtered by scan type (`--mode`).

### Plugin-to-Report

Each plugin's `post_process()` returns a path to `{name}_processed.json`. The report builder loads all processed files, extracts `custom_html`/`custom_html_pdf`, `executive_summary`, `issues`, and assembles the final report.

### Plugin-to-Config

Plugins define `config_schema` at class level. During `super().__init__()`, the schema is registered with `ConfigManager`. Plugins read config via `self.get_config(key, default)`.

### Plugin-to-Issue Registry

Plugins map findings to issue IDs from `kast/data/issue_registry.json`. The report builder resolves IDs to full issue details (severity, description, remediation).

### ZAP Provider Chain

`ZapPlugin` -> `ZapProviderFactory` -> Provider (Local/Remote/Cloud) -> `ZAPAPIClient` for scan control. Cloud mode additionally uses `TerraformManager` + `SSHExecutor`.

---

## Prompt Engineering Tips

When working with KAST as a GenAI assistant:

1. **Always read `genai-instructions.md` first** for project context
2. **Check `.clinerules`** for quick reference and conventions
3. **Review existing plugins** (especially `related_sites_plugin.py`, `zap_plugin.py`) for patterns
4. **Use `self.get_result_dict()`** - never construct result dicts manually
5. **Handle report-only mode** in every plugin's `run()` method
6. **Include `findings_count`** (integer) in all processed output
7. **Provide dual HTML** (`custom_html` + `custom_html_pdf`) for reports
8. **Test both execution modes** (sequential and parallel)
9. **Define `config_schema`** for any configurable parameters
10. **Map findings to issue registry** entries where applicable
11. **Use `self.debug()`** for verbose logging, not `print()`
12. **Check `is_available()`** returns False gracefully when tool missing
13. **Timestamp format:** `datetime.utcnow().isoformat(timespec="milliseconds")`
14. **Never crash the orchestrator** - wrap external calls in try/except

### Common Tasks

- **Add a plugin:** Use `create_plugin.py`, follow lifecycle, add tests
- **Add an issue:** Edit `issue_registry.json`, reference in plugin
- **Add config option:** Add to `config_schema`, `_load_plugin_config()`, `default_config.yaml`
- **Fix a report bug:** Check both HTML and PDF templates/styles
- **Debug parallel issues:** Check thread safety, use `self.debug()` for logging
