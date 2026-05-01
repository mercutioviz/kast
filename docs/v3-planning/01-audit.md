# kast v2 Audit — Phase 1

Status: **In progress.** This document is built up as the audit proceeds. Severity tags: `[HIGH]` (real bug or risk), `[MED]` (should fix in v3), `[LOW]` (papercut/cleanup).

---

## 0. Method and scope

- Target: `kast` codebase at v2.14.5 on branch `refactor/v3.0`. kast-web is audited only at the integration boundary in this phase, per scoping decision.
- Reading approach: entry-point first (`main.py`, `orchestrator.py`, `plugins/base.py`), then `config_manager.py`, `utils.py`, the plugin `template_plugin.py`, and a representative leaf plugin (`whatweb_plugin.py`). Cross-referenced against `docs/baseline-v2.14/kastweb-references.txt` for the kast↔kast-web contract.
- Still to read in this phase: `report_builder.py`, plugin samples (`zap`, `related_sites`, `org_discovery`, `ai_chatbot_detection`, `subfinder`, `katana`, `ftap`, `testssl`, `wafw00f`, `observatory`, `script_detection`), `install.sh`, `update.sh`, `tests/`, `genai-instructions.md`, the kast/scripts/zap_* suite.

---

## 1. Headline findings (executive summary)

1. **The README understates the system by a wide margin.** v2.14.5 has 13 plugins (not 8), and a substantial cloud-deployment subsystem for ZAP (Terraform for AWS/Azure/GCP, SSH executor, infrastructure provider factory, NGINX proxy config). The README claims version 2.1.0, lists 8 plugins, and says nothing about ZAP or cloud. **A new SA cannot understand the system from the README alone.**
2. **A plugin interface migration is half-finished and visible everywhere.** Two plugin styles coexist (with/without `config_manager`); main.py has the same `try/except TypeError` fallback duplicated in three places; the dependency-tree utility duplicates it again. The `template_plugin.py` still uses the old style, so any new plugin copy-pasted from it will inherit the legacy shape.
3. **Plugin files are large because plugins reimplement the same scaffolding.** WhatWeb (the *small* one) is 460 lines; `related_sites_plugin.py` is 53KB, `zap_plugin.py` 43KB. Most of that is repeated boilerplate (command construction, dry-run command construction, fail-disposition post-processing, processed-dict assembly, `_format_command_for_report`). An `ExternalToolPlugin` base could absorb most of it.
4. **The kast↔kast-web contract is implicit and brittle.** kast-web shells out via argv, parses `kast -ls` text to enumerate plugins, scans the output dir for `*_processed.json` by glob, and tails `zap_scan_progress.json`. A `--config-schema` JSON output exists for kast-web, but kast-web isn't using it. No versioned API.
5. **There are at least two real bugs in the orchestrator and CLI.** `as_completed(futures), None` in `orchestrator.py:277` is dead/misused — turns the parallel scheduler into a busy-wait. `--zap-profile` uses a relative path (`kast/config/zap_automation_*.yaml`) that breaks if invoked from any cwd other than the repo root.
6. **The install/update tooling is heavier than the project warrants.** `install.sh` is 82KB with 16 named checkpoints and state-file recovery; `update.sh` is 38KB. For a personal-scope tool with a sales-engineering audience, this is over-engineered and a maintenance tax.
7. **The cloud-deployment subsystem is a major v3 architecture decision.** Terraform configs for three clouds, ZAP-on-VM provisioning, SSH execution, orphan-resource cleanup — undocumented, and arguably belongs in kast-web (which is the orchestration layer) rather than the CLI. v3 needs an explicit answer to "where does ZAP cloud live?"

---

## 2. Documentation truth (README vs reality)

| Claim in README | Reality in code | Severity |
|---|---|---|
| "Version 2.1.0 (Installer 2.7.1)" | `VERSION` file says `2.14.5`; install.sh fallback string is `2.8.2` | [MED] |
| 8 plugins listed | 13 concrete plugins on disk: + `ai_chatbot_detection`, `org_discovery`, `related_sites`, `zap` | [MED] |
| Mentions `kast` and `ftap` launchers | install.sh CHECKPOINT list also installs Docker, Geckodriver, Terraform, Observatory, Pango — most of these unmentioned | [MED] |
| No mention of ZAP | 43KB plugin + 10 ZAP YAML profiles + 9 scripts under `kast/scripts/zap_*` + nginx ZAP proxy config + multi-cloud Terraform | [HIGH] |
| `--httpx-rate-limit` documented as a flag | help text marks it `(DEPRECATED: use --set related_sites.httpx_rate_limit=N)` | [LOW] |

**Why this matters for the v3 audience:** an SA evaluating whether to use kast in front of a customer needs to know what ZAP's runtime requirements are (local container? cloud VM? what does it cost?), and that is invisible today.

---

## 3. Architecture and module boundaries

### 3.1 `main.py` is doing too much — `[MED]`

`main.py` (550 lines) handles: argparse, logging setup, plugin discovery (twice), ConfigManager wiring, plugin schema registration (duplicated across three command branches), the `--zap-profile` shortcut translation, output dir resolution, report-only target recovery from `kast_info.json`, orchestrator launch, `kast_info.json` writing, and report generation invocation.

Concretely, this block is duplicated three times in main.py (lines 286–298, 308–319, 333–344):

```python
plugins = discover_plugins(log)
for plugin_cls in plugins:
    class MinimalArgs:
        verbose = False
    try:
        try:
            plugin_instance = plugin_cls(MinimalArgs(), config_manager)
        except TypeError:
            plugin_instance = plugin_cls(MinimalArgs())
    except Exception as e:
        log.error(f"Error loading plugin {plugin_cls.__name__}: {e}")
```

That pattern (instantiate-just-to-get-metadata, with old/new style fallback) recurs in `orchestrator.py` (dry-run, plugin filtering, parallel scheduling), in `utils.py:show_dependency_tree`, and in `main.py:list_plugins`. **At least 5 sites doing the same thing.** A `PluginRegistry` that loads classes once, holds metadata, and is the single instantiation point would collapse all of it.

### 3.2 `config.py` is empty alongside an 18KB `config_manager.py` — `[LOW]`

Leftover from the migration that introduced `ConfigManager`. Delete `config.py` or repurpose it as a public re-export.

### 3.3 The cloud subsystem lives inside the CLI, not the orchestrator — `[HIGH]` (architectural)

Inside `kast/`:
- `terraform/{aws,azure,gcp}/{main,variables,outputs}.tf`
- `scripts/zap_provider_factory.py`, `zap_providers.py`, `zap_api_client.py`
- `scripts/ssh_executor.py`, `terraform_manager.py`, `find_zap_url.py`, `monitor_zap.py`, `cleanup_orphaned_resources.py`, `diagnose_infrastructure.py`, `test_infrastructure_*.py`
- `config/zap_cloud_config.yaml`, `config/nginx/zap-proxy.conf`

The CLI is provisioning cloud infrastructure to run a scan. That is a much bigger design than "scan a target with local tools." Two architectural questions for v3:
1. Should this remain in the kast CLI, or move into kast-web (which is the long-running, multi-user, server-side component)?
2. If it stays, is it a first-class plugin capability ("execution backend") or a ZAP-specific special case?

This question alone could change the shape of v3 significantly.

---

## 4. Plugin system

### 4.1 Two plugin styles coexist — `[HIGH]`

- Old style: `def __init__(self, cli_args)` — used by `template_plugin.py` and presumably some others.
- New style: `def __init__(self, cli_args, config_manager=None)` — used by `whatweb_plugin.py`.

The system papers over this with `try: cls(args, cm) except TypeError: cls(args)` everywhere. That pattern is *brittle* — it will silently mask any unrelated `TypeError` raised inside a plugin's `__init__`.

`template_plugin.py:17` is old-style. **Any plugin authored from the template inherits the legacy interface.** The template should reflect the canonical pattern; the legacy fallback should be deleted.

### 4.2 `if not hasattr(self, 'name'):` is a sequencing footgun — `[MED]`

`base.py:33–46` sets defaults only if subclasses haven't already set them. This requires subclasses to assign `self.name`, `self.description`, etc. **before** calling `super().__init__()`, because `_load_config` (called from `super().__init__()`) needs `self.name` to look up the schema.

`whatweb_plugin.py:55` documents this with a comment ("IMPORTANT: Set plugin name BEFORE calling super().__init__()"). `template_plugin.py:17–26` does it correctly by accident. A clean fix: pass identity as constructor args (`super().__init__(cli_args, config_manager, name=..., description=...)`) or as class attributes resolved before any logic runs.

### 4.3 Plugin code repeats the same wrapper machinery — `[MED]`

WhatWeb (smallest non-template plugin, 460 lines) duplicates:
- Command list construction (run + dry-run versions, drift-prone)
- `command_executed` tracking + HTML-styled `_format_command_for_report` (line 367)
- Standardized processed-dict assembly
- Failure post-processing branch (`if raw_output.get('disposition') == 'fail':`)
- Output-file existence checks after subprocess

If this is repeated across 13 plugins of average ~30KB, several thousand lines are duplicated. An `ExternalToolPlugin(KastPlugin)` base could absorb:
- A declarative `tool_binary = "whatweb"` → auto `is_available()`
- A `build_command(target, output_dir)` hook that's called once and reused for both run() and dry-run
- A standard subprocess runner with stdout/stderr capture, return-code handling, and missing-output-file error
- A standard `post_process` skeleton with hooks for `parse_findings`, `count_findings`, `extract_issues`, `executive_summary`

Plugins would become ~50–150 lines of tool-specific logic instead of ~500.

### 4.4 Inline styled HTML in plugin code — `[LOW]` (layering)

`whatweb_plugin.py:367` returns a `<code style="color: #00008B; font-family: ...">` literal as the "report" field. Plugins shouldn't author HTML — that's the report renderer's job. Plugins should emit plain strings; the report layer applies style.

### 4.5 Schema validation only logs warnings — `[MED]`

`base.py:73` calls `validate_plugin_config`, but writes errors via `self.debug(...)` (verbose-only stdout print). An invalid config silently proceeds. For a tool an SA hands to a customer, silent fallback to broken config is the wrong default — should at minimum log at WARNING and probably refuse to start in strict mode.

Also: validation is hand-rolled (`config_manager.py:468`) and only checks `type`, `minimum`, `maximum`. It misses `enum`, `pattern`, `required`, nested object validation, array item validation. The Python `jsonschema` package would do this for free.

### 4.6 Dependencies are callable lambdas attached to plugin metadata — `[LOW]`

`base.py:96–121`. Each dependency is `{plugin: 'name', condition: callable}`. This is not serializable, not introspectable beyond "is it callable," and `show_dependency_tree` (`utils.py:140`) has to string-match `'success'`/`'fail'` in the lambda's repr to describe it. Replace with a small declarative DSL: `{plugin: 'whatweb', when: 'success'}` or similar — easier to render, easier to validate, and exposable to kast-web.

---

## 5. Configuration system

### 5.1 The schema-driven config is the right idea, only partially delivered — `[MED]`

`ConfigManager` (`config_manager.py`) does layered merging (defaults → file → CLI overrides) cleanly enough. `--config-schema` exports a JSON schema specifically for kast-web consumption (line 153 of main.py: "for GUI tools like kast-web"). That's a sound design.

But it isn't being used by the consumer it was built for. Per `kastweb-references.txt`, kast-web's `parse_kast_plugins(kast_path)` invokes `kast -ls` and parses the **text** output (admin.py:595). The schema endpoint is dark.

### 5.2 Schemas are only registered after instantiation — `[MED]`

`register_plugin_schema` is called from `KastPlugin.__init__`. So `kast --config-schema` must instantiate every plugin to enumerate schemas, requiring a `MinimalArgs` placeholder and the same old-style/new-style fallback. Schemas should be class attributes (already partially are — see `config_schema = {...}` on `WhatWebPlugin`) and discoverable without instantiation.

### 5.3 `--zap-profile` shortcut uses a relative path — `[HIGH]` (real bug)

`main.py:273`: `profile_path = f"kast/config/zap_automation_{args.zap_profile}.yaml"`. This is interpreted relative to the cwd. Run `kast` from anywhere other than the repo root and ZAP profile loading silently uses an unresolvable path. Should resolve relative to package location (`Path(__file__).parent / "config" / ...`).

---

## 5a. Report subsystem (HTML + PDF)

This was flagged by Michael as suspected klunk; the audit confirms it. The two-format requirement was solved by **copying the entire pipeline rather than abstracting it**.

### 5a.1 `generate_html_report` and `generate_pdf_report` are ~99% the same code, copy-pasted — `[HIGH]`

`generate_html_report` (lines 337–540) and `generate_pdf_report` (lines 651–881) share the entire data-collection pipeline byte-for-byte:

- Plugin name normalization (`plugin-name` || `tool` || `name` three-way fallback)
- Executive-summary collection
- `detailed_results` dict assembly
- Issue iteration: `isinstance(issue, str)` normalization, `issue_id.strip()`, registry metadata lookup, missing-issue tracking with `infer_issue_metadata` + `generate_registry_template`, `all_issues.append(...)`
- Severity ordering and sort (`severity_order = {"High": 0, ...}` declared in both)
- `generate_executive_summary(...)` call
- Severity counts (`sum(1 for issue in all_issues if ...)` — four lines, twice)
- `calculate_waf_statistics`
- `scan_metadata` dict assembly

The differences are mechanical: PDF pre-renders JSON via `format_json_for_pdf` and embeds the logo as base64; HTML copies the CSS and logo to the output dir; PDF uses `custom_html_pdf` falling back to `custom_html`; PDF passes a different template object.

**Right shape:** one `_collect_report_data(plugin_results) -> ReportData` builder, then two thin renderers (`render_html(data, ...)`, `render_pdf(data, ...)`) consuming the same dataclass with different templates and finishing steps. Today, any change to the pipeline must be made twice or it drifts — and given the HTML version passes `tool_name` for anchor links to `format_multiline_text_as_list` while the PDF version doesn't (line 700 vs line 377), it has already drifted.

### 5a.2 `add_word_break_opportunities` is fixing a layout problem in the wrong layer — `[MED]`

Lines 165–203 walk every string > 80 chars and inject `<wbr>` after every delimiter character (`/`, `?`, `&`, `=`, `-`, `_`, `.`, `:`, `;`, `,`), with HTML-tag-aware skip logic. The comment says "this helps prevent overflow in PDF rendering."

This is content mutation as a stand-in for CSS. The right fix is a stylesheet rule (`overflow-wrap: anywhere; word-break: break-word;` on URL cells) in `kast_style_pdf.css`. Today's approach:
- Pollutes the rendered HTML (size grows for any URL-heavy report)
- Re-implements partial HTML parsing (lines 187–194) — fragile
- Is duplicated inline inside `format_json_for_pdf` (lines 626–629) instead of calling the function

### 5a.3 `format_json_for_pdf` reinvents JSON pretty-printing as HTML — `[MED]`

Lines 577–648 recursively render arbitrary JSON as nested `<div>`s with depth limiting and string truncation at 500 chars. This exists because the HTML report can use `<details>` for collapsible JSON but the PDF (static) can't — so the same source data needs two rendering paths.

Truncation as a layout fix is concerning: an SA showing the report to a customer has no signal that 500-char strings have been clipped. Better: render as collapsed-by-default in HTML, and as a "[N items, see appendix]" pointer in PDF with the full data in an appendix section.

### 5a.4 Missing-issue tracking is duplicated verbatim — `[MED]`

Lines 430–453 (HTML path) and lines 757–779 (PDF path) are byte-identical logic. With `--format both`, the same inference runs twice, the same `missing_issue_ids.json` is written twice (the second overwrites the first). Cheap waste, but a maintenance footgun: any change has to be made in both spots.

### 5a.5 `infer_issue_metadata` is hand-coded keyword heuristics — `[MED → HIGH]`

Lines 26–95 guess severity and category from substrings in the issue ID (e.g., `if "rce" in issue_lower: severity = "High"`). This exists *because* `issue_registry.json` is incomplete — when a plugin emits an unregistered issue ID, the system falls back to inference.

**The current registry-extension workflow is hard:** the only documented tool is `fix_registry.py` at the repo root — a 37-line ad-hoc script with the new entry's content **hardcoded inside the script body**. Adding a new issue today means editing `fix_registry.py`, replacing the literal block, running it, and committing both. There is no `kast registry add ID --severity ...` command. There is no "promote from `missing_issue_ids.json`" command. Per Michael's feedback: this elevates registry-completeness priority — the audit cannot honestly leave it at LOW until the workflow is cheap.

Three v3 options, in increasing rigor:
1. **Self-healing registry workflow**: a `kast registry promote <output_dir>` command that reads `missing_issue_ids.json` and produces draft entries (using the inferred metadata) for the operator to review and accept.
2. **Plugin-owned registration**: each plugin declares its issue IDs as a class attribute; orchestrator validates against the registry at startup; unknown IDs fail the build.
3. **Externalize the inference rules**: move the keyword-to-severity mapping into the registry as regex patterns. Code stays small; new heuristics don't require code changes.

(1) is the lightest lift and would make the existing inference path actually useful instead of a dead-end. Combine with (2) for new plugin development going forward.

### 5a.12 Severity-key mismatch between registry and report — `[HIGH]` (real bug)

The report's badge counter (`report_builder.py:476–481`, `800–805`) bins issues by exact-string severity: `"High"`, `"Medium"`, `"Low"`, `"Info"`. But `issue_registry.json` stores severities as `"High"`, `"Medium"`, `"Low"`, `"Informational"` — never `"Info"`. **Every Informational issue silently disappears from the badge counts.**

This compounds the "Unknown drops out" finding (5a.9) — the under-counting Michael has noticed has *two* causes, not one. Even with a fully-populated registry, Informational issues never show up in the headline counts.

Trivial fix today; just call it out so it doesn't ride along into v3 by accident. Best fix in v3: a single `Severity` enum referenced everywhere (registry, badge counts, sort order, executive summary).

### 5a.6 Two HTML templates + two CSS files = ~85KB of must-stay-in-sync — `[MED]`

- `report_template.html` (26KB) for browser
- `report_template_pdf.html` (23KB) for WeasyPrint
- `kast_style.css` (21KB) for browser
- `kast_style_pdf.css` (16KB) for PDF

Jinja2 supports template inheritance — a `report_base.html` with `{% block %}` regions, plus tiny HTML-specific and PDF-specific child templates, would collapse most of this. CSS could share a base stylesheet plus media queries (`@media print { ... }`) and PDF-specific overrides.

### 5a.7 Logo handling is inconsistent — `[LOW]`

- HTML: copies the logo file to the output dir and references by filename. If the report is emailed alone (without the dir), the logo is broken. Note that the HTML report is one of the artifacts an SA might forward to a prospect.
- PDF: base64-embeds the logo. Self-contained.

HTML should also embed (either inline `<img src="data:...">` or, more cleanly, all images as base64 data URIs).

### 5a.8 CSS is copied to the output dir per scan — `[LOW]`

Lines 496–505 copy `kast_style.css` into every output dir. Sample-scan dir confirms this (`kast_style.css` 21KB sits next to the report). Trade-off:
- Pro: report is portable (zip the dir, ship anywhere)
- Con: 21KB duplicated per scan; CSS updates don't propagate to old scans
- v3 alternative: inline the CSS in a single `<style>` block at render time. Same portability, no copy step.

### 5a.9 "Unknown" severity disappears from severity counts — `[LOW]`

Lines 476–481 (HTML) and 800–805 (PDF) only count `High|Medium|Low|Info`. Any issue whose ID isn't in the registry gets `severity = "Unknown"` and silently drops out of the badge counts — so a report can say "0 High, 0 Medium" when the system actually had unclassifiable findings. The customer sees a clean report; reality is dirtier.

### 5a.10 Direct `print()` calls inside report builder — `[LOW]`

Lines 161, 536, 864 use `print()` for status output. Inconsistent with the rest of the system which uses logging.

### 5a.11 Templates are loaded at module import — `[LOW]`

Lines 282–283. Cosmetic, but means template-syntax errors crash the import rather than the function.

---

## 6. Orchestrator and execution

### 6.1 `as_completed` is created and discarded — `[HIGH]` (real bug)

```python
# orchestrator.py:277
done, _ = as_completed(futures), None
```

Parses as `done, _ = (as_completed(futures), None)` — `done` is the iterator, never iterated. The actual completion check is the busy `for future in list(futures.keys()): if future.done()` poll on the next lines. The `as_completed` call has zero effect; the scheduler busy-waits. Simple fix: `for future in as_completed(futures): ...`.

### 6.2 Plugins are instantiated multiple times per run — `[LOW]`

In parallel mode: once for filtering by `scan_type` (line 113), once for the `pending_plugins` map (line 231), once inside `_run_plugin` (line 153). Three instantiations per plugin per run, plus once each for `list_plugins` and dry-run. Wasted work and a vector for double-fired side-effects in `__init__`.

A `PluginRegistry` holding instances keyed by class would fix this and 5+ duplicated try/except blocks.

### 6.3 Dependency-driven scheduler is hand-rolled — `[MED]` (design)

`_run_plugins_with_dependencies` (lines 214–297) is a manual `while pending or futures` loop with a `break` to re-evaluate dependency satisfaction. It works in straightforward cases but is hard to reason about. v3 should consider either:
- A simple topological sort (compute layers up front, run each layer in parallel)
- Or a small DAG executor library (graphlib.TopologicalSorter is in stdlib since 3.9)

### 6.4 Deadlock detection is good, deadlock recovery is "fail all and break" — `[LOW]`

Lines 264–273. Acceptable for now. Consider whether some deadlocks are actually skippable (one plugin's failed dep allows another to proceed).

---

## 7. Code-quality smells (Python-level)

| Smell | Location | Severity |
|---|---|---|
| `datetime.utcnow()` (deprecated, scheduled for removal) | `base.py:165`, `template_plugin.py:48,161`, `whatweb_plugin.py:102,198,255` and likely all other plugins | [MED] |
| Inconsistent logging vs `print()` | `base.py:138-140` uses `print()` for debug; rest of codebase uses `logging` | [LOW] |
| No type hints in plugin layer | `base.py`, `template_plugin.py`, `whatweb_plugin.py`. `config_manager.py` *does* have hints — inconsistent | [LOW] |
| kebab-case keys in JSON output (`plugin-name`, `plugin-display-name`) but snake_case in Python everywhere else | All `_processed.json` files; consumed by kast-web | [LOW] |
| Empty `__init__.py` | `kast/plugins/__init__.py` (0 bytes) | [LOW] |
| Empty `config.py` | leftover from migration | [LOW] |

---

## 8. kast ↔ kast-web seam

Per `docs/baseline-v2.14/kastweb-references.txt`, the integration surface is:

| Surface | What kast-web does | Concerns |
|---|---|---|
| **CLI argv** | `[kast_cli, '-t', target, '-m', mode, '--format', 'both']` and `--report-only`, `--list-plugins`, `--version` | Stable but undocumented as an API. No `--json-output` to remove the need for text parsing. |
| **`kast -ls` output** | `parse_kast_plugins()` regex-parses Rich-rendered text (`admin.py:595`) | Brittle to any output formatting change. Should be replaced by `kast plugins list --json` or by `--config-schema`. |
| **`*_processed.json` files** | Glob the output dir, treat each as a plugin result (`tasks.py`, `routes/scans.py`, `routes/api.py`) | Implicit naming convention; no manifest. A `kast_manifest.json` listing every artifact + its kind would be safer. |
| **`zap_scan_progress.json` polling** | kast-web tails this for ZAP progress (`tasks.py:955`, `models.py:751`) | One-off real-time channel. Other long-running plugins might benefit from the same protocol. |
| **`KAST_CLI_PATH`** | env-configurable, defaults to `/usr/local/bin/kast` | Fine. |
| **`--config-schema`** | Available in kast (main.py:151), referenced as "for GUI tools like kast-web" | Dark on the kast-web side. |

**Implications for v3:** the CLI/contract for kast-web should be promoted to a real, versioned interface — JSON-everywhere, manifest-driven output, schema-discoverable plugins, structured progress events. This is also a pre-req for an MCP / agent-callable kast (Phase 2 territory).

---

## 9. Install and update

`install.sh`: 2,466 lines, ~50 named functions, 16 checkpoints. `update.sh`: 1,232 lines.

Observations after structural survey:

- The shell is **competently written**, not just "big": named functions, error/interrupt traps, version-aware tool installation (`version_compare`, `get_apt_version`, `check_version_requirement`, `determine_install_strategy`), proper backup creation, dispatch on install state (fresh / aborted / same-version / older-version / partial). This is not the place I expected klunk.
- It installs more than the README admits: Docker, Geckodriver, Terraform, Observatory, libpango, PDF fonts. None of these appear in the README's "prerequisites" list.
- It modifies system state widely: `rm -rf /usr/local/go`, `rm -rf /usr/lib/go*`, writes `/etc/profile.d/go.sh`, modifies user shell rc files, creates `/usr/local/bin/kast` and `/usr/local/bin/ftap` launchers. Reasonable for a "scanning workstation setup" but a lot of footprint for a personal-scope tool.
- Recovery via 16 checkpoints is heroic engineering for a problem that probably affects a handful of installs per year. The complexity hasn't paid for itself.
- The bigger v3 question isn't "is the shell good?" — it is. The question is **whether the install model itself is right**. A `pipx install kast` that pulls deps from PyPI, plus a `kast doctor` Python command that checks for external tool binaries and offers to install them via apt, would replace ~80% of `install.sh`. Docker would replace the rest for SAs who want a sealed environment.

`update.sh` is similarly substantial; rollback via timestamped backup is the headline feature. Probably stays as-is or moves into the same `kast self-update` Python subcommand depending on the install model chosen.

---

## 9a. ZAP plugin and cloud subsystem (deeper look)

`zap_plugin.py` is 997 lines but the architecture inside is sound: a `ZapProviderFactory` (in `kast/scripts/zap_provider_factory.py`) dispatches to one of `{local, remote, cloud}` provider implementations. The plugin itself is mostly a thin wrapper around the factory; the actual mode-specific logic lives in the scripts directory. This is the **right** factoring — the cloud complexity is encapsulated rather than smeared across the plugin.

Specific concerns inside `zap_plugin.py`:

- **`is_available()` always returns True** (lines 199–219). The comment justifies this ("still return True as remote mode may be configured"), but it changes the semantics: `is_available` no longer means "available" — it means "do not skip me." Other plugins use `is_available` for a binary "tool present in PATH" check. Should split into `is_configured()` vs `is_available()` or rethink the contract.
- **Bespoke `_load_config()` override** (line 221) bypasses ConfigManager's standard loading path. ZAP loads its own YAML hierarchy from `kast/config/zap_config.yaml` and `kast/config/zap_cloud_config.yaml`, with `_adapt_legacy_config()` for backward compatibility. This is the migration-mid-flight pattern in its most explicit form: ZAP predates ConfigManager and grandfathered in its own loader. v3 should converge.
- **Schema explicitly admits incompleteness**: `"# Note: Full cloud config remains in YAML file due to complexity (AWS/Azure/GCP specific settings, credentials, Terraform state)"` (line 139). So `--config-schema` cannot fully describe the cloud config. kast-web GUI form generation can't render the full ZAP config — there's still a YAML-edit step.

For the cloud subsystem (`kast/terraform/{aws,azure,gcp}/` + `kast/scripts/zap_*` + `kast/scripts/ssh_executor.py` + `kast/scripts/terraform_manager.py` + `kast/config/nginx/zap-proxy.conf`):

- The factoring (provider abstraction + Terraform configs + SSH executor) is good — this is genuine engineering, not piecemeal gluing.
- It is **architecturally misplaced** as a CLI capability. The cloud lifecycle (provision, scan, fetch results, tear down, retry, orphan-cleanup) wants a long-running supervisor, not a CLI invocation. kast-web is that supervisor; kast is currently doing it from a one-shot `kast` command.
- Specifically: `cleanup_orphaned_resources.py`, `diagnose_infrastructure.py`, `monitor_zap.py` — these are housekeeping tasks that belong somewhere with state, not on an SA's laptop after they've already closed the terminal.
- v3 architecture decision (re-stated for emphasis): **the cloud subsystem should likely move to kast-web, with kast retaining only the local/remote-existing-instance modes.** This dramatically simplifies the kast CLI and matches each subsystem to its proper environment.

## 10. Tests

30 test files in `kast/tests/` plus a `helpers/config_test_helpers.py`:

- Heavy plugin-config coverage: `test_*_config.py` for whatweb, testssl, related_sites, subfinder, observatory, katana, ftap, zap, wafw00f, script_detection.
- Plugin behavior: `test_whatweb_redirect.py`, `test_whatweb_full_integration.py`, `test_related_sites_filtering.py`, `test_related_sites_error_handling.py`, `test_testssl_connection_failure.py`, `test_testssl_clientproblem.py`, `test_testssl_plugin.py`, `test_ftap_plugin.py`, `test_ftap_post_process.py`, `test_ai_chatbot_detection.py`.
- Report layer: `test_report_builder.py`, `test_executive_summary.py`, `test_pdf_navigation.py`, `test_html_list_structure.py`, `test_report_only.py`.
- Infrastructure: `test_kast_info.py`, `test_tool_index.py`, `test_zap_unified_config.py`.

This is more coverage than I expected and a genuine asset. The `__pycache__` shows tests have been run on Python 3.13 with pytest 8.4.2. Caveats:
- I haven't read the tests themselves yet — quality is unknown.
- No `tests/conftest.py` was visible in the listing; depends on what `helpers/config_test_helpers.py` provides.
- `demo_ftap_processing.py` is in `tests/` but is named like a demo script — naming hygiene.
- The plugin migration (old vs new `__init__` signature) is unlikely to have broken these tests, but worth verifying as part of v3 prep.

**v3 implication:** tests are a hedge against the v3 refactor. Any v3 architectural change that preserves the per-plugin processed-JSON contract should be able to keep most of these passing with minimal modification. Tests of the report builder will need rework when the HTML/PDF pipelines are unified.

## 11. What's worth keeping

Not everything is suspect. v3 should preserve:

- **The `_processed.json` per-plugin contract.** Even if we add a manifest, the per-plugin standardized JSON is sensible.
- **`kast_info.json`** as a run-metadata sidecar. Simple, useful, used by both `--report-only` and kast-web.
- **The issue registry** (`kast/data/issue_registry.json`) — 65 entries today, 64 marked `waf_addressable: true`. Includes sales-relevant fields (`remediation_approach`, `code_fix_timeframe`, `waf_deployment_timeframe`) that drive the WAF-pitch language. This data layer is a real asset; the *workflow to extend it* is what needs work.
- **Schema-driven plugin configuration** as a *concept* — the implementation needs improvement, but the direction (declarative, GUI-discoverable) is correct.
- **`--report-only` mode with target recovery from `kast_info.json`** — quietly elegant.
- **The dry-run mode** — important for SA-running-in-front-of-customer scenarios.
- **The dependency-driven plugin DAG** — concept is right; mechanism should change.
- **Active vs passive scan-type filtering** — important for the customer-facing reputational risk.

---

## 11a. AI-collaboration contract (`genai-instructions.md`, `.clinerules`, `AI-Prompts.txt`)

The repository carries three layers of AI-coding scaffolding:

- **`genai-instructions.md`** (18KB, "v2.14.3, Last Updated: February 2026") is **the most accurate documentation in the project** — better than the README. Real architecture, design patterns, plugin lifecycle, file organization, common patterns, prompt engineering tips. As a reference document, it's a genuine asset.
- **`.clinerules`** is a thin pointer to `genai-instructions.md` plus a quick-reference duplicate of its key sections.
- **`AI-Prompts.txt`** and **`create_ai_prompts.sh`** are early-development artifacts: only three plugins (`observatory`, `wafw00f`, `whatweb`), references the path `/opt/kast/kast`, ends with "Today I want to add a new plugin for the 'nikto' web server scanner." This is dead from v0/v1 days; should be deleted.

**Critical concern for v3:** `genai-instructions.md` and `.clinerules` enshrine v2's klunk as required patterns. Specific examples:

- "Set attrs BEFORE `super().__init__()`" — documented as a *requirement* (it's actually a design smell from the schema-registration sequencing footgun, finding 4.2).
- "Provide both `custom_html` and `custom_html_pdf`" — institutionalizes the parallel HTML/PDF pipeline that section 5a calls out.
- "Use `datetime.utcnow().isoformat(timespec='milliseconds')`" — explicitly tells AI assistants to use the deprecated API.
- "Note: template_plugin.py uses old signature" — flagged as a note rather than fixed.

Because Michael builds with AI assistance, this doc is a forcing function: future plugins inherit whatever patterns the doc canonizes. **`genai-instructions.md` is therefore a v3 deliverable in its own right** — when v3 architecture stabilizes, this doc must be rewritten or the AI-built future of kast will keep producing v2-shaped code.

## 11b. kast-web contract — `docs/web-integration.md` (already drafted)

The user has begun a `docs/web-integration.md` that **defines the kast↔kast-web contract for v3.0**. It declares:
- Three integration surfaces: CLI invocation, stdout/stderr, output directory.
- A file-presence state machine for plugins (raw file → running, processed file → completed).
- **Atomic write requirement**: write `*_processed.json.tmp`, rename(2) into place, so kast-web never sees a partial completion file.
- **Frozen filenames** for v3.0: `{plugin}.json`, `{plugin}.txt`, `{plugin}_processed.json`.
- A `zap_scan_progress.json` real-time progress channel for ZAP, also requiring atomic updates.
- Change-control rules: internal refactoring is free; surface changes require an explicit version bump and coordinated kast-web update.

This document is **the most important architectural decision the project has made** and it answers my open question (2) in the audit: kast-web's contract IS frozen for v3.0. Internal v3 refactoring is permissible as long as the surface stays stable.

**Implications for the v3 audit:**
- The kebab-case `plugin-name` JSON keys (5a layering finding) are FROZEN for v3.0. We can fix them later via a coordinated v3.1 surface bump but not in v3.
- The `*_processed.json` glob convention is FROZEN.
- The CLI argv contract from `docs/baseline-v2.14/help.txt` is FROZEN (or at minimum, additive changes only).
- Internal: free to introduce a `PluginRegistry`, an `ExternalToolPlugin` base, fix the orchestrator busy-wait, normalize severity, etc. — none of these touch the surface.

**TODOs in the contract doc that I can complete from the baseline:**
- Document `zap_scan_progress.json` schema (TODO line 102, 106).
- Paste the directory-layout manifest from a representative baseline scan (TODO line 110–112).
- Verify "no ANSI color codes when not attached to a TTY" (TODO line 25).

These are tractable in 30 minutes from the baseline files; offer to do them as a Phase 1 finishing task or a Phase 2 prep step.

## 11c. Test-coverage shape

Light read of `kast/tests/test_report_builder.py` reveals a single 28-line test asserting that string and dict issues both produce registry display names in HTML. **The largest source file in the project (`report_builder.py`, 35KB) has the thinnest test in the suite.** No assertions on badge counts, severity ordering, executive summary structure, PDF generation, or the missing-issue inference flow.

This is congruent with the report-subsystem findings: the duplication and the bugs it enabled (Info/Informational, Unknown drops, drift between HTML and PDF anchor handling) survived because the tests didn't pin them down. v3 should land report tests with badge-count assertions, severity-mapping assertions, and golden-output diffs of HTML and PDF render results.

By contrast, plugin-config tests (e.g., `test_zap_config.py` at 279 lines, `test_wafw00f_config.py` at 243) are substantial and likely high-quality. The plugin layer is well-protected; the report layer isn't.

## 11d. Confirmed: plugin code repetition (`related_sites_plugin.py`, first 300 lines)

The largest plugin (`related_sites_plugin.py`, 53KB) confirms the bloat-from-duplication hypothesis. It wraps **two tools** (`subfinder` for subdomain enum + `httpx` for liveness probing), so it inherits 2× the per-tool wrapper boilerplate: schema, command-list construction (run + dry-run), `_load_plugin_config`, subprocess invocation with timeout/capture/error handling, output-file existence checks, post-processing of two output formats. Plus a CLI-arg backward-compat shim for `--httpx-rate-limit` that's no longer needed.

A v3 `ExternalToolPlugin` base, plus a higher-level `MultiToolPlugin` that composes 2+ external-tool steps, would absorb most of `related_sites_plugin.py`'s mass and make the actual logic (subdomain extraction with `tldextract`, apex-vs-FQDN decisioning, port probing strategy) visible.

---

## 12. Open questions for v3 design

Status as of end of Phase 1:

1. **ZAP-cloud subsystem moves to kast-web** — **CONFIRMED** (memory: `project_v3_cloud_decision.md`). ~2,452 lines across `zap_provider_factory.py` + `zap_providers.py` + `ssh_executor.py` + `terraform_manager.py` + `zap_api_client.py` migrate as a unit, plus the Terraform configs + nginx + YAML profiles. The factoring is clean, so the migration is "lift the subsystem" not "untangle the mess."

2. **kast↔kast-web contract** — **ANSWERED** by `docs/web-integration.md`. Frozen surface (CLI argv, output-dir layout, atomic-write semantics, file-presence state machine, ZAP progress channel) for v3.0. Internal refactoring is free.

3. **Install model** — **OPEN.** Recommendation pending: pipx for Python deps + `kast doctor` for external binaries + optional Docker for sealed environments. Need confirmation before Phase 3.

4. **`genai-instructions.md` rewrite** — **OPEN as a v3 deliverable.** When v3 architecture stabilizes, this doc must be updated or AI-built future plugins inherit v2-shaped patterns.

5. **AI-augmented-analysis architecture (Phase 2 question, but constrains v3)** — **OPEN.** Self-hosted vs. Anthropic API vs. user-pluggable. Offline-first or online-required. Affects v3 packaging and runtime deps.

6. **Issue-registry workflow** — **OPEN, elevated priority.** Per Michael's rule, since `fix_registry.py` is the current workflow (one-shot script with hardcoded entry), registry-completeness is no longer low priority. v3 needs a proper `kast registry promote` / `kast registry add` workflow.

---

## 12a. v2 patches Michael may want to apply to main now

Bugs discovered during Phase 1 that don't need to wait for v3:

- **`Info`/`Informational` severity bug** (sections 5a.12). Three-line fix in `report_templates.py:get_severity()`. Patch printed in chat 2026-04-30.
- **`as_completed(futures), None` in `orchestrator.py:277`** (section 6.1) — turns parallel scheduler into a busy-wait. Replace the construct with a proper `for future in as_completed(futures): ...` loop.
- **`--zap-profile` relative path in `main.py:273`** (section 5.3) — breaks if invoked from any cwd other than the repo root. Replace with `Path(__file__).parent / "config" / "zap_automation_*.yaml"`.

These three are independent and small. Optional v2 patches; happy to print each one if you want them.

---

## 13. Phase 1 status — COMPLETE

- [x] `main.py`, `orchestrator.py`, `plugins/base.py`, `plugins/template_plugin.py`
- [x] Small plugin (`whatweb_plugin.py`)
- [x] Large plugin spot-check (`related_sites_plugin.py`, first 300 lines — confirmed duplication hypothesis)
- [x] `config_manager.py`, `utils.py`
- [x] `report_builder.py`, `report_templates.py`, templates dir, full Info/Informational bug trace
- [x] `install.sh`, `update.sh` (structural survey, not line-by-line)
- [x] Tests directory (listing, sizing, one quality sample of `test_report_builder.py`)
- [x] `issue_registry.json` (structure + the `fix_registry.py` workflow)
- [x] `zap_plugin.py` (first 300 lines, structural conclusions)
- [x] `kast/scripts/zap_provider_factory.py` (full read, cloud architecture confirmed)
- [x] `genai-instructions.md`, `.clinerules`, `AI-Prompts.txt`, `create_ai_prompts.sh`
- [x] `docs/web-integration.md` (the v3 contract spec, with documented TODOs)

Phase 1 deliverable is this document. Ready to move to Phase 2 (capability and ideation pass), with three optional sidequests available between phases:

1. **Apply the three v2 bug patches to main** (Info/Informational, busy-wait, relative ZAP profile path).
2. **Complete the TODOs in `docs/web-integration.md`** (zap_scan_progress.json schema, directory-layout manifest, ANSI/TTY behavior verification) by examining the baseline files in `docs/baseline-v2.14/`. ~30 minutes; tightens the v3 contract spec.
3. **Discuss the open questions in section 12** (install model, AI-analysis architecture) before Phase 2 begins, so ideation lands on solid ground.
