# Migrating from kast v2.x to v3.0

This guide is for kast users moving from v2.14.x to v3.0. Most user-visible behavior is preserved — the v2 CLI argv shape still works, scan output is structurally compatible with v2 baseline, and existing scripts that wrap kast keep functioning. A handful of things changed, mostly internals plus one user-facing surface (cloud-mode ZAP).

If you also operate kast-web, read [`kast-web/docs/MIGRATION_FROM_KAST_CLOUD.md`](https://github.com/mercutioviz/kast-web/blob/refactor/v2.0/docs/MIGRATION_FROM_KAST_CLOUD.md) — it covers the cloud-side migration.

## TL;DR

| If you... | Then... |
| --------- | ------- |
| Run `kast --target X --mode passive ...` from a script or kast-web | No change. Legacy argv still works via a translation wrapper. |
| Use cloud-mode ZAP (`--set zap.execution_mode=cloud` or `kast/config/zap_cloud_config.yaml`) | **Breaking.** Cloud mode is gone in v3. Use kast-web 2.0 for managed cloud scans, or run ZAP yourself and use `--set zap.execution_mode=remote`. |
| Use local-mode or remote-mode ZAP | No change. Both still supported. |
| Have custom plugins inheriting from `KastPlugin` | Mostly works as-is. Optional: migrate tool wrappers to `ExternalToolPlugin` for less boilerplate. See plugin authoring updates below. |
| Use the `fix_registry.py` script | Replaced by `kast registry list / add / promote`. |
| Read scan output (`*_processed.json`, `kast_info.json`) from external code | Output structure unchanged. v3 adds an additive `ai` block to `kast_info.json` you can ignore. |
| Want the new AI-augmented executive summary | Opt in via `--ai-summary` and provide an Anthropic API key. |

---

## Breaking changes

### Cloud-mode ZAP removed

The `cloud` value of `zap.execution_mode` is gone. The ~6,400 lines of Terraform/SSH/provisioning code under `kast/scripts/` and `kast/terraform/` are deleted. The `kast/config/zap_cloud_config.yaml` and `kast/config/nginx/` directories are removed.

**Why:** kast is a CLI; long-running infrastructure provisioning belongs in a service. kast-web 2.0 owns the cloud lifecycle (provision → scan → teardown → orphan cleanup) and spawns kast in remote mode against the resulting ZAP instance.

**What to do:**

- **If you used kast-web for cloud scans:** upgrade kast-web to 2.0 and you're done. The user-visible UI flow is unchanged.
- **If you invoked cloud mode directly via `kast --set zap.execution_mode=cloud`:** stand up your own ZAP (in EC2, Docker, etc.) and switch to remote mode:
  ```bash
  kast --target X --mode active \
       --set zap.execution_mode=remote \
       --set zap.remote.url=http://your-zap:8080 \
       --set zap.remote.api_key=$ZAP_API_KEY
  ```
- **If you have custom Terraform / cleanup scripts that wrap kast cloud mode:** those are now orphaned. Re-target them at kast-web's `app/cloud/` module if you've adopted kast-web; otherwise drive Terraform directly without going through kast.

### `fix_registry.py` removed

The standalone script is gone; the workflow is now built into the CLI.

```bash
# Old:
python kast/scripts/fix_registry.py

# New:
kast registry list                         # see all entries
kast registry add ID --severity High --category Headers ...
kast registry promote SCAN_DIR             # walk through missing_issue_ids.json
kast registry promote SCAN_DIR --accept-all   # CI-friendly accept everything
```

The new commands write the registry atomically and integrate with the same scan output (`missing_issue_ids.json`).

### Python 3.11+ required

kast 2.14.x ran on Python 3.7+. v3 requires **Python 3.11 or later** (3.13 is the dev target). If you're on an older Python, upgrade your interpreter or pin to kast 2.14.x.

---

## CLI changes

### Subcommand structure (additive — v2 argv still works)

v3 has Click-based subcommands:

```
kast version
kast config (init | show | schema)
kast scan --target TARGET [options]
kast scan list | show DIR | rerun DIR
kast plugins (list | show | deps)
kast registry (list | add | promote)
kast doctor [--fix] [--json]
kast self-update [...]
```

The legacy v2 argv shape (`kast --target X --mode passive ...`, `kast --list-plugins`, `kast --report-only DIR ...`) still works — `kast.cli.__init__._translate_v2_argv()` maps it to the subcommand form before Click parses. Existing scripts and kast-web's subprocess invocations don't need to change.

The v3 form is preferred for new automation.

### `--ai-summary` (new, opt-in)

```bash
export KAST_AI_API_KEY=sk-ant-...
kast scan --target example.com --ai-summary
```

Off by default. When enabled, kast calls Claude with the scan results and produces a structured executive summary (headline, narrative, key findings, recommended actions) that lands in the report. If the API call fails, the report still renders with the deterministic summary and a banner noting the failure.

Configuration alternatives: `~/.config/kast/ai.yaml`, `KAST_AI_PROVIDER`, `KAST_AI_MODEL` env vars. See the README for details.

### `kast doctor --fix`

```bash
kast doctor --fix
```

Applies safe auto-fixes (mkdir for results / log dirs, `kast config init`, scaffold `~/.config/kast/ai.yaml`) and prints a checklist of system-mutating fixes (`sudo apt install ...`, `go install ...`) for you to run manually.

### `kast self-update`

In-place upgrades with backups and rollback. Wraps the existing `update.sh` with a Python-friendly interface.

### `--zap-profile` path resolution fixed

In v2.x, `--zap-profile quick` resolved its YAML config relative to the **current working directory** — running kast from anywhere except the install dir broke it. v3 resolves relative to the kast package directory. No action needed; just notably less brittle.

---

## Plugin authoring changes

These only matter if you've written custom plugins. The v2 plugin shape still works; the v3 patterns are recommended for new plugins.

### `ExternalToolPlugin` base (recommended for tool wrappers)

In v2, every tool-wrapper plugin re-implemented subprocess invocation, output reading, post-processing, atomic-write-of-processed-dict. Roughly 300 lines of boilerplate per plugin. v3 adds `kast.plugins.external_tool.ExternalToolPlugin`:

```python
class MyPlugin(ExternalToolPlugin):
    name = "mytool"
    display_name = "My Tool"
    description = "What it does"
    website_url = "https://example.com/mytool"
    scan_type = "passive"
    output_type = "file"

    tool_binary = "mytool"
    output_filename = "mytool.json"
    output_format = "json"

    config_schema = { ... }

    def build_command(self, target, output_path):
        return ["mytool", "-o", output_path, target]

    def count_findings(self, findings):
        return len(findings)
```

The base handles is_available (via `shutil.which(tool_binary)`), the subprocess call, return-code/timeout/missing-output handling, raw-output read, atomic processed-dict write, and standard format hooks. You override `build_command` and `count_findings`; everything else has sensible defaults you can override (`parse_findings`, `extract_issues`, `format_summary`, `format_details`, `format_executive_summary`, `extra_processed_fields`).

The reference migrations in this release are `kast/plugins/whatweb_plugin.py` (458→195 lines) and `kast/plugins/wafw00f_plugin.py` (505→357 lines, with a `run()` override for the HTTPS→HTTP TLS-error retry quirk).

### Identity is class attributes

The v2 footgun where you had to set `self.name` **before** `super().__init__()` is gone. v3 declares identity as class attributes:

```python
# v2 (deprecated; the v2 shape still works but is footgun-prone):
class MyPlugin(KastPlugin):
    def __init__(self, cli_args, config_manager=None):
        self.name = "mytool"
        self.display_name = "My Tool"
        self.description = "..."
        super().__init__(cli_args, config_manager)  # registers schema, needs self.name

# v3:
class MyPlugin(KastPlugin):
    name = "mytool"
    display_name = "My Tool"
    description = "..."
    config_schema = { ... }

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self.timeout = self.get_config("timeout", 300)
```

Schemas are collected via `ConfigManager.collect_schemas_from_classes(...)` without instantiating plugins. `kast --config-schema` (and the new `kast config schema`, `kast config init`, `kast config show`) all use this path.

### `Severity` enum

Use `kast.core.severity.Severity` instead of bare strings.

```python
from kast.core.severity import Severity

severity = Severity.from_registry(value)   # canonical, normalizes legacy "Info" → INFORMATIONAL
sort_key = severity_sort_key(severity_value)  # for sorting issue lists
```

The registry stores `"Informational"`; v2 stored `"Info"`. `Severity.from_registry` normalizes both. The badge text in reports is rendered as "Info" for visual brevity but the data value is always canonical.

### Atomic JSON writes

All state-bearing JSON files (`*_processed.json`, `kast_info.json`, `zap_scan_progress.json`, `missing_issue_ids.json`) must be written via:

```python
from kast.core.atomic import write_json_atomic
write_json_atomic(path, data)
```

This writes to `<path>.tmp` and `os.replace`s into place — the kast↔kast-web contract requires that watchers never observe a partial file. Don't use raw `with open(path, "w"): json.dump(...)` for these files.

### Single rich report payload (no `custom_html_pdf`)

In v2, plugins emitted both `custom_html` (interactive) and `custom_html_pdf` (static for WeasyPrint) widgets. v3 unifies the report pipeline: plugins emit a **single rich payload** via `extra_processed_fields(...)` and the renderers handle format-specific differences. Existing plugins that still emit both fields keep working — the v3 PDF renderer prefers `custom_html_pdf` if provided — but new plugins should just emit `custom_html`.

### `datetime.now(timezone.utc)`, not `datetime.utcnow()`

`datetime.utcnow()` is deprecated in Python 3.12+. v3 uses `datetime.now(timezone.utc).isoformat(timespec="milliseconds")` everywhere. If you copy-paste timestamp code from v2 plugins, update the API.

---

## Internal-API changes (only if you import from kast)

These will affect you only if you `import kast.something` from your own code. End users running kast from the CLI don't see them.

### `kast.report_builder` is a compatibility shim

The report pipeline split into `kast/report/`:
- `kast.report.data.collect_report_data(plugin_results, target)` — assembles the shared dict
- `kast.report.html.render_html(report_data, ...)` and `kast.report.pdf.render_pdf(report_data, ...)`
- Helpers in `kast.report.helpers`

Existing imports (`from kast.report_builder import generate_html_report, generate_pdf_report, ...`) still work — the shim re-exports — but new code should import directly from `kast.report`.

### `PluginRegistry`

Plugin discovery / instantiation / caching is now centralized:

```python
from kast.registry import PluginRegistry

registry = PluginRegistry(logger, cli_args=args, config_manager=cm)
all_instances = registry.all_instances()         # sorted by priority
plugin = registry.get("whatweb")
filtered = registry.filter_by_mode("passive")
```

The five duplicated try/except instantiation blocks in v2's `main.py`, `orchestrator.py`, and `utils.py` are gone. `ScannerOrchestrator` now takes a list of plugin **instances** (not classes) and no longer needs a `config_manager` parameter (instances carry it).

`kast/utils.py:show_dependency_tree(registry, scan_mode, log)` now takes a registry, not classes.

---

## Output structure

`*_processed.json`, `kast_info.json`, `zap_scan_progress.json`, and `missing_issue_ids.json` retain their v2 shape — kebab-case keys, the same field set, the same atomic-write contract documented in `docs/web-integration.md`. The only output change is **additive**:

`kast_info.json` gains an `ai` block when `--ai-summary` is used:

```json
{
  ...
  "ai": {
    "enabled": true,
    "status": "success",
    "adapter": "anthropic",
    "model": "claude-sonnet-4-6",
    "prompt_version": 1,
    "tokens_in": 1119,
    "tokens_out": 643,
    "latency_ms": 19996,
    "error": null
  }
}
```

When `--ai-summary` isn't passed, the block reports `enabled: false, status: "disabled"`. Existing parsers that don't expect this field can ignore it.

---

## Upgrade procedure

### From a kast 2.14.x installer-based install

```bash
cd /path/to/kast-repo
git fetch origin
git checkout main          # or a specific v3.x tag
git pull
sudo ./update.sh
```

The update script preserves your config, takes a backup, and runs the migration. Roll back with `sudo ./update.sh --rollback BACKUP_TIMESTAMP` if needed.

### From scratch (recommended on a fresh box)

```bash
# Option A: pipx
pipx install kast
kast doctor --fix

# Option B: install.sh
git clone https://github.com/mercutioviz/kast.git
cd kast
sudo ./install.sh
```

### If you used kast-web

Upgrade kast and kast-web together. The two repos release as a coordinated bundle:

- kast `v3.0.0` and kast-web `v2.0.0` are designed to work together.
- Older kast-web (1.5.x) drives kast 2.14.x via the v2 argv contract — that combination still works.
- New kast-web (2.0.x) shells out to kast 3.0 for both passive and remote-mode active scans, and uses kast-web's internal cloud module for cloud scans.

Don't mix kast 3.0 with kast-web 1.5.x for cloud scans — kast-web 1.5 expects kast to provide cloud mode, which it no longer does.

---

## Getting help

- Issues: https://github.com/mercutioviz/kast/issues
- README: [`README.md`](../README.md)
- v3 design history: [`docs/v3-planning/`](v3-planning/)
- kast↔kast-web boundary contract: [`docs/web-integration.md`](web-integration.md)
- Plugin authoring guide: [`kast/plugins/README.md`](../kast/plugins/README.md)
- AI-assistant context: [`CLAUDE.md`](../CLAUDE.md)
