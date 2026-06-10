# kast plugin authoring guide

This is the practical "write a new plugin" walkthrough. The durable rules and architecture summary live in [`CLAUDE.md`](../../CLAUDE.md) — read its "Plugin authoring rules" and "Architecture and patterns" sections first. This file shows the canonical shape and walks through the two base classes.

## Choosing a base class

| Use this base                 | When                                                              |
|------------------------------ |-------------------------------------------------------------------|
| `ExternalToolPlugin`          | The plugin wraps a CLI tool: invoke via subprocess, read its output. |
| `KastPlugin`                  | Pure-Python: HTTP calls, file analysis, no subprocess.            |

`ExternalToolPlugin` is a subclass of `KastPlugin` that supplies subprocess invocation, return-code handling, atomic processed-dict writes, and standard format hooks. Prefer it for new tool wrappers.

## Getting started

Copy [`template_plugin.py`](template_plugin.py) and adapt it. It already uses the v3 shape: class-attribute identity, the canonical `__init__` signature, timezone-aware timestamps, atomic writes via `kast.core.atomic`. Discovery skips `template_plugin.py` by name, so the copy you make is the one that'll be picked up.

For tool wrappers, also study the reference migrations: [`whatweb_plugin.py`](whatweb_plugin.py) (standard shape) and [`wafw00f_plugin.py`](wafw00f_plugin.py) (overrides `run()` for an HTTPS→HTTP TLS-error retry quirk).

## Canonical shape

```python
from kast.plugins.external_tool import ExternalToolPlugin

class MyToolPlugin(ExternalToolPlugin):
    priority = 50                    # lower runs earlier

    # Identity — class attributes only, never set in __init__
    name = "my_tool"
    display_name = "My Tool"
    description = "What this plugin does."
    website_url = "https://example.com/my_tool"
    scan_type = "passive"            # or "active"
    output_type = "file"             # or "stdout"

    # ExternalToolPlugin plumbing
    tool_binary = "my_tool"          # drives auto is_available() via shutil.which
    output_filename = "my_tool.json"
    output_format = "json"           # or "text"

    config_schema = {
        "type": "object",
        "title": "My Tool Configuration",
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
```

That is a complete, working plugin if the tool emits JSON to the output path. Everything else has sensible defaults.

## ExternalToolPlugin hooks

**Required:**

- `build_command(target, output_path) -> list[str]` — argv list to run.
- `count_findings(findings) -> int` — primary-finding count (drives `findings_count` in the processed dict — kast-web renders it on the scan-details page).

**Optional, with sensible defaults:**

- `parse_findings(raw)` — normalize raw output (default: pass-through).
- `extract_issues(findings) -> list[str]` — issue-registry IDs (default: `[]`).
- `format_summary(findings) -> str` — report summary (default: generic message).
- `format_details(findings) -> str` — report details (default: empty).
- `format_executive_summary(findings, issues) -> str` — exec-summary line (default: empty).
- `extra_processed_fields(findings, issues) -> dict` — extra processed-dict keys (e.g., `{"custom_html": "..."}` for inline HTML widgets).
- `get_dry_run_info(target, output_dir) -> dict` — dry-run preview (default: just the command).

Override `run()` only when there's a tool-specific quirk the base can't cover — see `wafw00f_plugin.py` for the canonical example.

## Pure-Python plugins (KastPlugin)

When the plugin doesn't shell out to a CLI tool — HTTP API calls, file analysis, registry lookups — inherit from `KastPlugin` directly and implement `is_available`, `run`, and `post_process` yourself. See [`mozilla_observatory_plugin.py`](mozilla_observatory_plugin.py) and [`ai_surface_detection_plugin.py`](ai_surface_detection_plugin.py) for the shape.

The same identity, `__init__`, config, and atomic-write rules apply.

## Issue-registry integration

Push registry IDs into `issues` (a list). The report layer resolves IDs to full entries (severity, description, category, talking points) when rendering. Unresolved IDs accumulate in `missing_issue_ids.json` for follow-up via `kast registry promote`.

```python
def extract_issues(self, findings):
    issues = []
    if not findings.get("hsts_present"):
        issues.append("MISSING_HSTS")
    return issues
```

To add a registry entry: `kast registry add ID --severity High --category Headers --description "..." --talking-points "..."` (writes atomically). To bulk-accept what a scan flagged as missing: `kast registry promote SCAN_DIR` (interactive) or `--accept-all` (CI).

## Dependencies

```python
self.dependencies = [
    {"plugin": "mozilla_observatory",
     "condition": lambda r: r.get("disposition") == "success"},
]
```

The orchestrator launches a plugin only when each declared dependency has run *and* its `condition` returns truthy.

## Testing

Add a `kast/tests/test_{plugin_name}.py` covering both success and failure paths. Mock `subprocess.run` and verify:

- `build_command` produces the expected argv.
- `parse_findings` / `count_findings` handle empty, populated, and malformed input.
- `post_process` produces a valid processed dict (`findings_count` integer, expected `issues`, no exceptions on unusual data).
- `is_available()` returns False gracefully when the tool is absent.

Reference: `kast/tests/test_external_tool_base.py` for base-class behavior; `kast/tests/test_whatweb_*.py` for migration coverage.

## Reminders

- Never mutate identity in `__init__` — class attributes only.
- Always use `self.get_result_dict("success" | "fail", results, timestamp)` for return values.
- Always include `findings_count` (integer) in the processed dict.
- Use `kast.core.atomic.write_json_atomic` for state-bearing JSON writes. Never raw `json.dump`.
- Use `kast.core.severity.Severity` for severity values. Never bare strings.
- Use `datetime.now(timezone.utc).isoformat(timespec="milliseconds")` for timestamps. Never `datetime.utcnow()`.
- Use `self.debug(...)` for verbose logging. Never `print()`.
- Never raise out of `is_available()` or `run()` — return a fail-disposition result dict instead. kast-web's state machine depends on the completion marker.

The full rule list with rationale lives in [`CLAUDE.md`](../../CLAUDE.md).
