# kast v3 — Design and Migration Plan

Phase 3 deliverable. Synthesizes Phase 1 audit (`01-audit.md`), Phase 2 ideation (`02-ideation.md`), and the five gating decisions confirmed at end of Phase 2 into a concrete v3 architecture and a phased migration plan.

---

## Executive summary

**Posture: incremental refactor, not big-bang rewrite.** kast is in active sales-engineering use; you cannot afford to lose the tool while you rebuild. v3 ships as a series of internally-coherent phases, each one shippable, each one preserving the kast↔kast-web v2.14 contract until the last phase deliberately upgrades it.

**Total effort: ~12–16 weeks of part-time work.** Phase D parallelizes with Phase C, so calendar time is meaningfully shorter than the sum-of-phases.

**Five phases:**

- **Phase A — Foundation refactors (1–2 weeks).** Fix the audit-identified klunk without changing user-visible behavior: PluginRegistry, ExternalToolPlugin base, Severity enum, unified report pipeline, the three v2 bug patches. Tests stay green; output is byte-compatible.
- **Phase B — Surface modernization (2–3 weeks).** New `kast scan / plugins / registry / doctor / self-update` subcommands as an additive layer. v2 argv contract preserved via a wrapper. Migrate two plugins to the new ExternalToolPlugin base as proof.
- **Phase C — Tier 1 capability landings (4–6 weeks).** Build the AI adapter, the kast-web AI service (cost gating + review workflow), the LLM-generated executive summary (A1), the TCO appendix (F1), the WAF feature map (F2), and the extended AI surface detection (B1).
- **Phase D — Cloud migration to kast-web (2–3 weeks, parallel with C).** Move Terraform configs, ZAP providers, SSH executor, infrastructure scripts from kast to kast-web. Add kast-web admin UI for cloud creds. Deprecate `execution_mode: cloud` in kast.
- **Phase E — Polish + release (1–2 weeks).** pipx install model, `kast doctor`, Docker image, documentation rewrite, coordinated kast 3.0 + kast-web 3.0 release.

**What v3 changes for users:**

- SAs get LLM-generated executive summaries, a TCO appendix translating findings into "code fix vs WAF deployment" effort, and an auto-generated "Why Barracuda WAF" section per scan.
- Pure-CLI users without kast-web can still use AI features by configuring their own Anthropic API key.
- Cloud-mode ZAP scans move from a kast CLI invocation to a kast-web operation. SAs running cloud scans interact with kast-web's UI, not the CLI.
- Install is `pipx install kast` plus `kast doctor` for external binaries, replacing ~80% of the current 82KB `install.sh`.

**What v3 does NOT change:**

- The kast↔kast-web contract documented in `docs/web-integration.md` — frozen for v3.0. File-presence state machine, atomic writes, frozen filenames, the `zap_scan_progress.json` channel — all preserved.
- The v2 CLI argv contract — works through v3.0 as a compatibility wrapper. `kast --target X` still works.
- The `_processed.json` per-plugin output convention.
- The issue registry data format (only the workflow around it changes).

**Three v2 patches that can ship to main today** (independent of v3):

1. `Info`/`Informational` severity bug in `report_templates.py:get_severity()` — patch printed previously.
2. `as_completed(futures), None` busy-wait at `orchestrator.py:277`.
3. Relative path for ZAP profile at `main.py:273`.

(Patches 2 and 3 are also printed in section 13 of this document.)

---

## 1. Target architecture

```
                        ┌──────────────────────────────┐
                        │  Anthropic API (default)     │
                        │  OpenAI / Bedrock / Ollama   │  (via adapter)
                        └────────────┬─────────────────┘
                                     │
                ┌────────────────────┴───────────────────────┐
                │                                            │
                │           kast-web v3.0                    │
                │  ┌──────────────────────────────────────┐  │
                │  │  AI Service (cost gate, review,      │  │
                │  │  prompt mgmt, org config)            │  │
                │  ├──────────────────────────────────────┤  │
                │  │  Cloud Orchestrator (Terraform,      │  │
                │  │  ZAP providers, SSH, cleanup)        │  │
                │  ├──────────────────────────────────────┤  │
                │  │  Scan service (Celery)               │  │
                │  │   shells out to kast CLI             │  │
                │  ├──────────────────────────────────────┤  │
                │  │  Web UI (Bootstrap 5 + Jinja)        │  │
                │  │  REST API                            │  │
                │  └──────────────────────────────────────┘  │
                └─────────────┬───────────────┬──────────────┘
                              │               │
                              │ kast↔kast-web │ (frozen contract)
                              │               │
                ┌─────────────▼───────────────▼─────────────┐
                │           kast CLI v3.0                   │
                │  ┌──────────────────────────────────────┐ │
                │  │  Subcommand layer                    │ │
                │  │   scan / plugins / registry /        │ │
                │  │   doctor / self-update               │ │
                │  ├──────────────────────────────────────┤ │
                │  │  v2 argv compatibility wrapper       │ │
                │  ├──────────────────────────────────────┤ │
                │  │  Plugin Registry → Orchestrator      │ │
                │  │   ExternalToolPlugin base            │ │
                │  │   13 plugins (cloud removed)         │ │
                │  ├──────────────────────────────────────┤ │
                │  │  Report Pipeline                     │ │
                │  │   collect → render(html|pdf)         │ │
                │  │   F1 TCO appendix, F2 WAF map        │ │
                │  └──────────────────────────────────────┘ │
                └───────────────────────────────────────────┘
```

**Component responsibilities:**

| Component | Owns | Does not own |
|---|---|---|
| **kast CLI** | Plugin orchestration, scan execution, report rendering, registry maintenance, local environment doctoring. | Cloud lifecycle, AI cost gating, multi-user auth, scan persistence. |
| **kast-web** | Scan supervision (Celery), persistence, multi-user auth, AI service (cost gating + review), cloud orchestration, REST API, web UI. | The actual scan logic (delegates to kast CLI). |
| **AI adapter** | Vendor-neutral `generate(prompt, system, response_schema=...)`. | Cost gating (that's kast-web's job). |
| **Cloud orchestrator** | Terraform state, ZAP provider lifecycle, SSH execution, infrastructure cleanup, orphan detection. | Scan results parsing (that's kast CLI's job). |

**Data flow for a typical AI-augmented scan:**

```
SA → kast-web UI: "Scan example.com"
  └→ Celery task picks up
     └→ shell out: kast scan -t example.com -o /scans/abc123
        └→ kast runs plugins, writes *_processed.json files atomically
     └→ kast-web detects scan completion (state machine)
     └→ kast-web AI service:
        ├→ check org budget
        ├→ generate cost preview, log
        ├→ call AI adapter → narrative
        ├→ if review-mode: queue for SA review
        └→ if auto-mode: write narrative into report
     └→ kast-web renders final report (HTML + PDF)
  └→ SA reviews / sends to prospect
```

---

## 2. Plugin system v3

The single biggest source of klunk in v2 was the plugin layer: half-finished migration, instantiate-just-to-get-metadata pattern duplicated five times, plugins reimplementing the same wrapper machinery, schemas registered after instantiation.

**v3 design:**

### 2.1 PluginRegistry (collapses the 5-site duplication)

A new `kast/registry.py`:

```python
class PluginRegistry:
    """Single source of truth for plugin discovery and metadata."""

    def __init__(self, logger):
        self._classes: list[type[KastPlugin]] = []
        self._instances: dict[str, KastPlugin] = {}
        self._metadata: dict[str, dict] = {}

    def discover(self) -> None: ...
    def all_classes(self) -> list[type[KastPlugin]]: ...
    def metadata(self, name: str) -> dict: ...        # No instantiation needed
    def instance(self, name: str, cli_args, cm) -> KastPlugin: ...  # Cached
    def filter_by_mode(self, mode: str) -> list[type[KastPlugin]]: ...
```

Replaces every `for plugin_cls in plugins: try: cls(args, cm) except TypeError: cls(args)` block in main.py, orchestrator.py, utils.py.

### 2.2 ExternalToolPlugin base

A second base class for the common case (a plugin that wraps a CLI tool):

```python
class ExternalToolPlugin(KastPlugin):
    """Base for plugins that wrap a CLI tool via subprocess."""

    tool_binary: str = ""            # e.g., "whatweb"
    output_filename: str = ""        # e.g., "whatweb.json"
    output_format: Literal["json", "text"] = "json"

    def is_available(self) -> bool:
        return shutil.which(self.tool_binary) is not None

    def build_command(self, target: str, output_path: str) -> list[str]:
        """Subclass override — return the argv list."""
        raise NotImplementedError

    def parse_findings(self, raw: Any) -> dict:
        """Subclass override — normalize the raw output."""
        raise NotImplementedError

    # run() and post_process() implemented in base, call build_command + parse_findings
```

A WhatWeb plugin in v3 becomes ~80 lines instead of 460. A `related_sites` plugin (which wraps two tools) gets a second base class:

```python
class MultiToolPlugin(KastPlugin):
    """Base for plugins composing 2+ external tools in sequence."""
    tools: list[ToolStep] = []
```

### 2.3 Single canonical `__init__` signature

```python
def __init__(self, cli_args, config_manager, *, name: str, **identity):
    super().__init__(cli_args, config_manager, name=name, **identity)
```

Identity (name, display_name, description, etc.) is passed as kwargs, not set as instance attributes before `super().__init__()`. The `if not hasattr(self, 'name')` footgun goes away.

### 2.4 Schemas as class attributes (not instance-time registration)

`config_schema` already is a class attribute on most plugins. v3 makes it the *only* way:

```python
@classmethod
def get_schema(cls) -> dict:
    return cls.config_schema
```

`kast --config-schema` no longer instantiates anything; it iterates classes. The "MinimalArgs" placeholder hack disappears.

### 2.5 Severity enum

`kast/core/severity.py`:

```python
class Severity(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFORMATIONAL = "Informational"
    UNKNOWN = "Unknown"
```

Used everywhere: registry, reports, badge counts, sort order. The `Info`/`Informational` mismatch becomes structurally impossible.

### 2.6 Plugin issue ID declaration (optional, recommended)

Plugins optionally declare which issue IDs they emit:

```python
class TestSslPlugin(ExternalToolPlugin):
    emits_issues = {"TLSv1.0", "TLSv1.1", "weak-cipher", ...}
```

A `kast registry verify` command checks that every declared ID is in the registry. New plugins fail the check until the registry catches up. Removes the "silently inferred metadata" path for plugins that opt in.

---

## 3. Report pipeline v3

The audit's section 5a documented the worst code in the project. v3 replaces it with the right shape:

```python
@dataclass
class ReportData:
    target: str
    scan_metadata: ScanMetadata
    plugins: list[PluginReport]
    issues: list[Issue]
    waf_stats: WafStatistics
    severity_counts: SeverityCounts
    executive_summary: ExecutiveSummary    # may include AI narrative
    waf_feature_map: WafFeatureMap | None
    tco_appendix: TcoAppendix | None

def collect_report_data(plugin_results, registry, ai_service=None) -> ReportData: ...

def render_html(data: ReportData, *, output_path, custom_logo=None) -> None: ...
def render_pdf(data: ReportData, *, output_path, custom_logo=None) -> None: ...
```

The 235-line copy-pasted block in `generate_html_report`/`generate_pdf_report` collapses into one builder. The renderers are thin (~60 lines each) — the only differences are pre-rendering JSON for PDF and base64-embedding the logo.

### 3.1 Jinja template inheritance

```
templates/
  base.html                  # shared structure
  report_html.html           # extends base, browser-specific blocks
  report_pdf.html            # extends base, PDF-specific blocks
  partials/
    executive_summary.html
    issues_table.html
    plugin_section.html
    tco_appendix.html        # NEW (F1)
    waf_feature_map.html     # NEW (F2)
```

CSS:

```
templates/
  base.css                   # shared
  html.css                   # @media screen overrides
  pdf.css                    # @media print overrides + PDF-specific rules
```

`add_word_break_opportunities` is deleted; replaced by `overflow-wrap: anywhere; word-break: break-word;` on URL-bearing cells in `pdf.css`.

`format_json_for_pdf` is replaced by either:
- A `<details>` collapsed-by-default in HTML; collapsed-with-truncation in PDF, with a "see appendix" link to the full JSON in a structured appendix.
- Or just the full JSON in the appendix and a summary in the inline section.

### 3.2 New report sections (Tier 1)

**F1: TCO appendix.** Renderer reads the registry's existing `code_fix_timeframe` and `waf_deployment_timeframe` per finding, aggregates totals, renders a side-by-side table:

> Addressing all detected issues in code: estimated 6–8 weeks of development effort.
> With Barracuda WAF/WaaS: 1–2 days to baseline coverage.

Plus a per-issue table showing the trade-off explicitly. Pure rendering — no AI required.

**F2: WAF feature map.** New content layer at `kast/data/waf_content/feature_map.yaml`:

```yaml
content_version: "1.0"
features:
  bot_mitigation:
    display_name: "Bot Mitigation"
    description: "Protects against automated attacks..."
    addresses_categories: ["Reconnaissance", "Information Disclosure"]
    addresses_issues: ["No WAF Detected"]
  ddos_protection:
    display_name: "Application DDoS Protection"
    addresses_categories: ["Encryption"]
    addresses_issues: []
  # ...
```

Renderer correlates scan findings with feature definitions to produce a "Why Barracuda" section: *"The following Barracuda WAF features address findings in your scan: [Bot Mitigation: 3 findings; SQL Injection Protection: 2 findings; ...]"*.

**A1: LLM-generated executive summary.** When AI is available and enabled, the LLM is called *during* `collect_report_data` to produce the narrative, which is stored on `ReportData.executive_summary.ai_narrative`. The renderer treats it as just another data field.

---

## 4. AI integration architecture

### 4.1 Adapter abstraction

`kast/ai/adapter.py`:

```python
class AIAdapter(Protocol):
    def generate(
        self,
        *,
        prompt: str,
        system: str,
        response_schema: dict | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> AIResponse: ...

@dataclass
class AIResponse:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: int
```

Implementations:
- `kast/ai/anthropic_adapter.py` — default, uses Claude Sonnet 4.6 or Opus 4.7
- `kast/ai/openai_adapter.py` — alternative for OpenAI/Azure/LiteLLM
- `kast/ai/bedrock_adapter.py` — AWS-native deployments
- `kast/ai/ollama_adapter.py` — self-hosted (vLLM/Ollama)

Adapter selection via config: `ai.adapter: anthropic` (default), credentials via env var or kast-web admin UI.

### 4.2 Prompt management

`kast/ai/prompts/` directory, versioned:

```
prompts/
  exec_summary_v1.md
  pre_meeting_briefing_v1.md     # Phase C+, Tier 2
  remediation_audience_v1.md     # Phase C+, Tier 2
```

Each prompt is a markdown file with frontmatter (model preference, temperature, max_tokens). Output of the AI call records which prompt version was used, so reports are reproducible.

### 4.3 kast-web AI service

New module `kast-web/app/ai/`:

```python
class AIService:
    def estimate_cost(self, scan_id: int) -> CostEstimate: ...
    def check_budget(self, org_id: int, estimated_cost: float) -> bool: ...
    def generate_summary(self, scan_id: int, *, mode: Literal["auto", "review"]) -> AISummaryRecord: ...
    def submit_review(self, summary_id: int, edited_text: str, action: Literal["accept", "regenerate"]) -> None: ...
```

Persistence:
- `Org` table: AI enabled flag, monthly token budget, current period usage, default mode (auto/review), API key (encrypted at rest)
- `AISummary` table: scan_id, prompt_version, raw_output, edited_output (if review mode), reviewed_by, status, token_in/out, cost

UI:
- Admin → Organization → AI settings (enable, budget, default mode, API key)
- Scan detail → AI summary section → edit / regenerate / accept (review mode) or just the rendered narrative (auto mode)
- Per-scan "this scan's AI summary will cost ~$0.04" preview before generation

### 4.4 kast CLI passthrough

`kast scan -t example.com --ai-summary` resolves the AI adapter in priority order:

1. `--ai-endpoint URL` flag → call kast-web's `/api/ai/generate` endpoint
2. `KAST_AI_PROVIDER=anthropic` + `KAST_AI_API_KEY=...` env vars → direct adapter call
3. `~/.config/kast/ai.yaml` config file → direct adapter call
4. None of the above → AI is off; report uses deterministic exec summary

This keeps pure-CLI use working while making kast-web the managed offering.

---

## 5. CLI surface v3

### 5.1 New subcommand structure

```
kast scan -t example.com [--mode passive] [--ai-summary] [-o DIR]
kast scan list [--limit 20] [--target PATTERN]
kast scan show SCAN_DIR
kast scan rerun SCAN_DIR

kast plugins list [--json]
kast plugins show PLUGIN_NAME

kast registry list [--category CAT] [--severity SEV]
kast registry add ID --severity SEV --category CAT [--from-template] ...
kast registry promote SCAN_DIR    # reads missing_issue_ids.json

kast doctor [--fix]
kast self-update [--check-only]
kast version
kast config show / kast config init / kast config schema
```

CLI built with **Click** or **Typer** — Click is more battle-tested; Typer is more modern. Pick Click for v3 unless you have a strong Typer preference.

### 5.2 v2 argv compatibility wrapper

In `kast/cli/__init__.py`:

```python
def main():
    argv = sys.argv[1:]
    if _is_v2_argv(argv):
        # Translate to v3 subcommand and re-dispatch
        translated = _translate_v2_to_v3(argv)
        sys.argv = [sys.argv[0]] + translated
    return v3_main()
```

`kast --target example.com --mode passive` → `kast scan -t example.com --mode passive` internally. Existing kast-web invocations and SA muscle memory continue to work through v3.0.

### 5.3 What gets deprecated

- `--httpx-rate-limit` (already marked deprecated; finally removed in v3.0)
- `--zap-profile` is kept but reframed: stays for the local/remote ZAP modes, but errors out with cloud mode (cloud lives in kast-web).

---

## 6. kast-web v3 additions

The audit treated kast-web as the integration boundary; this plan re-introduces it as the home for new capability.

### 6.1 New modules

```
kast-web/app/
  ai/                          # NEW (Phase C)
    __init__.py
    service.py                 # AIService class
    routes.py                  # /api/ai/* endpoints
    forms.py                   # Org AI config forms
    review.py                  # Review workflow logic
  cloud/                       # NEW (Phase D)
    __init__.py
    orchestrator.py            # Replaces kast/scripts/zap_provider_factory.py
    providers/
      aws.py
      azure.py
      gcp.py
    terraform_manager.py       # Moved from kast/scripts/
    ssh_executor.py            # Moved from kast/scripts/
    cleanup.py                 # Orphan cleanup, scheduled via Celery beat
    routes.py                  # /api/cloud/* and /admin/cloud/*
```

### 6.2 New database tables (Phase C/D)

```sql
ai_orgs (org_id, ai_enabled, monthly_budget_tokens, current_period_tokens,
         default_mode, anthropic_api_key_encrypted, ...)

ai_summaries (id, scan_id, prompt_version, raw_text, edited_text,
              reviewed_by_user_id, status, tokens_in, tokens_out,
              cost_usd, generated_at)

cloud_credentials (id, org_id, provider, credentials_encrypted, region, ...)

cloud_scans (id, scan_id, provider, instance_id, terraform_state,
             status, started_at, torn_down_at)

cloud_orphans (id, provider, resource_id, detected_at, cleanup_scheduled_for, status)
```

Migrations via the existing `migrate_db.py` flow.

### 6.3 New admin UI screens (Phase C/D)

- **Org → AI settings**: enable, budget, default mode, API key entry (write-only — display "•••• 1234" after entry)
- **Scan detail → AI summary panel**: review/edit/regenerate UI (review mode); rendered narrative (auto mode)
- **Cloud → Credentials**: add/remove cloud creds per provider per org
- **Cloud → Active scans**: live view of provisioned cloud resources
- **Cloud → Orphan resources**: detected resources, scheduled cleanup

### 6.4 Frozen contract preservation

All of the above is purely **additive** to kast-web. The kast↔kast-web contract documented in `docs/web-integration.md` does not change in v3.0:

- kast-web still shells out to `kast` CLI for scans
- kast still writes `*_processed.json` files
- kast-web still uses the file-presence state machine
- ZAP `zap_scan_progress.json` polling channel preserved

---

## 7. Migration plan

### Phase A — Foundation refactors (1–2 weeks)

**Goal:** fix audit-identified klunk without changing user-visible behavior.

**Deliverables:**

| # | Item | Files touched |
|---|---|---|
| A1 | Apply three v2 patches to main | `report_templates.py`, `orchestrator.py`, `main.py` |
| A2 | Complete `docs/web-integration.md` TODOs | `docs/web-integration.md`, sample baseline |
| A3 | `PluginRegistry` class | `kast/registry.py` (new) |
| A4 | Replace 5 sites of try/except duplication with PluginRegistry | `main.py`, `orchestrator.py`, `utils.py` |
| A5 | Schemas as class attributes only (no instance-time registration) | `plugins/base.py`, `config_manager.py` |
| A6 | Severity enum | `kast/core/severity.py` (new), all plugins, report code |
| A7 | Split `report_builder.py` into collector + renderers | `kast/report/` (new module) |
| A8 | Jinja template inheritance | `templates/base.html`, `report_html.html`, `report_pdf.html`, `partials/` |
| A9 | CSS @media print rules; remove `add_word_break_opportunities` | `templates/*.css` |
| A10 | Replace `datetime.utcnow()` everywhere | all `*.py` (use `datetime.now(timezone.utc)`) |

**Success criteria:**
- All 30 existing tests pass
- A scan against a known target produces a report that diffs cleanly against baseline (modulo expected timestamp/content version differences)
- No user-visible behavior change

**Validation tests to add:**
- Test for severity enum normalization (the Info/Informational case)
- Test that `kast --config-schema` does not instantiate plugins (verifiable via mock)
- Test that report data builder produces identical structure for the same plugin results

**Rollback:** Foundation work is internal. Each item is a separate PR; revert the offending one.

### Phase B — Surface modernization (2–3 weeks)

**Goal:** add v3 CLI subcommand structure as additive layer; preserve v2 contract.

**Deliverables:**

| # | Item | Files touched |
|---|---|---|
| B1 | Click-based subcommand dispatcher | `kast/cli/main.py` (new) |
| B2 | `kast scan` (and `list`/`show`/`rerun`) | `kast/cli/scan.py` (new) |
| B3 | `kast plugins` subcommands with `--json` output | `kast/cli/plugins.py` (new) |
| B4 | `kast registry` (list, add, promote) | `kast/cli/registry.py` (new), `kast/registry_io.py` (new) |
| B5 | `kast doctor` — env check, tool binary detection, config sanity | `kast/cli/doctor.py` (new) |
| B6 | `kast self-update` — Python wrapper around update logic | `kast/cli/self_update.py` (new) |
| B7 | v2 argv compatibility wrapper | `kast/cli/__init__.py` |
| B8 | `ExternalToolPlugin` base class | `kast/plugins/external_tool.py` (new) |
| B9 | Migrate `whatweb_plugin.py` and `wafw00f_plugin.py` to new base | those two files |
| B10 | Update `genai-instructions.md` for v3 patterns | `genai-instructions.md` |

**Success criteria:**
- Existing `kast --target X` invocations still work identically (smoke-tested via kast-web)
- `kast scan -t X` produces equivalent output
- `kast plugins list --json` produces a parseable manifest (kast-web admin can use this instead of regexing `kast -ls` output)
- Two plugins migrated with reduced LOC (target: ~80 lines for whatweb, down from 460)
- New `kast registry promote SCAN_DIR` works against a real `missing_issue_ids.json`
- `kast doctor` correctly identifies missing external binaries

**Validation tests to add:**
- v2-argv-compatibility test suite (every documented v2 invocation still works)
- ExternalToolPlugin contract tests (subclass produces correct subprocess command, parses output, post-processes)
- Registry CLI tests (add, list, promote)

**Rollback:** New CLI is purely additive. Old entry points remain. Plugin migrations are per-plugin; one breakage rolls back one plugin.

### Phase C — Tier 1 capability landings (4–6 weeks)

**Goal:** ship the seven Tier 1 features.

**Deliverables:**

| # | Item | Where |
|---|---|---|
| C1 | AI adapter abstraction + Anthropic implementation | `kast/ai/` (new) |
| C2 | OpenAI / Bedrock / Ollama adapter stubs | `kast/ai/` |
| C3 | Prompt: `exec_summary_v1.md` (the headline prompt) | `kast/ai/prompts/` |
| C4 | LLM-augmented exec summary integration in report pipeline | `kast/report/data.py` |
| C5 | F1 TCO appendix renderer | `kast/report/tco.py`, `templates/partials/tco_appendix.html` |
| C6 | F2 WAF feature map content + renderer | `kast/data/waf_content/feature_map.yaml` (new), `kast/report/waf_feature_map.py`, partial template |
| C7 | B1 extended AI surface detection | extend `plugins/ai_chatbot_detection_plugin.py` (rename to `ai_surface_detection_plugin.py`) |
| C8 | kast-web AI service (cost gate, review workflow) | `kast-web/app/ai/` (new) |
| C9 | kast-web Org AI settings admin UI | `kast-web/app/templates/admin/ai/`, routes |
| C10 | kast-web AI summary panel on scan detail | `kast-web/app/templates/scan_detail.html` partials |
| C11 | DB migration for AI tables | `kast-web/migrate_db.py` |
| C12 | AI prompt eval harness (golden outputs) | `kast/tests/ai/eval/` (new) |

**Success criteria:**
- `kast scan -t example.com --ai-summary` (with API key configured) produces a report containing an AI-generated exec summary
- kast-web shows cost preview before AI call; respects org budget
- Review-mode flow: SA edits and accepts → narrative lands in report
- Auto-mode flow: narrative goes straight to report
- F1 TCO appendix renders correct totals from registry data
- F2 "Why Barracuda" section renders feature → findings correlations
- B1 detects 5+ AI surface types on a curated test corpus (target list TBD)
- Eval harness shows AI summary quality stable across prompt revisions

**Validation tests to add:**
- AI adapter unit tests (mocked API responses)
- Cost gating tests (over-budget, under-budget, denied requests)
- Review workflow tests (edit, regenerate, accept paths)
- F1/F2 renderer tests (golden output)
- Plugin tests for B1's extended detection rules

**Rollback:** AI features are off by default. Disabling at the org level reverts to deterministic summaries. F1 and F2 are render-only — bugs revert via template fix.

### Phase D — Cloud migration to kast-web (2–3 weeks, parallel with C)

**Goal:** move the ~2,452 lines of cloud subsystem from kast to kast-web.

**Deliverables:**

| # | Item | Where |
|---|---|---|
| D1 | Move Terraform configs | `kast/terraform/` → `kast-web/app/cloud/terraform/` |
| D2 | Move provider implementations | `kast/scripts/zap_*` → `kast-web/app/cloud/providers/` |
| D3 | Move SSH executor and Terraform manager | `kast/scripts/{ssh_executor,terraform_manager}.py` → `kast-web/app/cloud/` |
| D4 | New Celery tasks for cloud lifecycle | `kast-web/app/tasks.py` additions |
| D5 | Celery Beat for orphan-cleanup scheduling | `kast-web/celery_worker.py` |
| D6 | Admin UI: cloud credentials | `kast-web/app/templates/admin/cloud/` |
| D7 | Admin UI: active cloud scans, orphan resources | same |
| D8 | API: `/api/cloud/scans/*`, `/admin/cloud/*` | `kast-web/app/cloud/routes.py` |
| D9 | Add deprecation warning to `kast.zap_plugin` cloud mode | `kast/plugins/zap_plugin.py` |
| D10 | Remove cloud mode from `kast.zap_plugin` for v3.0 | same |
| D11 | Migration guide for v2 cloud users | `kast-web/docs/MIGRATION_FROM_KAST_CLOUD.md` (new) |

**Success criteria:**
- A cloud scan launched from kast-web v3.0 successfully provisions, scans, fetches results, tears down
- Orphan cleanup correctly identifies and cleans a deliberately abandoned scan
- kast v3.0 with `execution_mode: cloud` returns a clear error pointing to kast-web
- v2.x kast still supports cloud mode (deprecation warning only) until kast-web v3.0 ships

**Validation tests to add:**
- End-to-end cloud scan test (against a test target, in a controlled cloud account)
- Orphan detection test (deliberate orphan + cleanup verification)
- Migration test: a kast v2.14 cloud scan and a kast-web v3.0 cloud scan produce equivalent reports

**Rollback:** Cloud migration is staged. Until kast-web v3.0 cloud is proven, kast retains its cloud mode. Migration cuts over only when kast-web v3.0 is reliable. If kast-web v3.0 cloud has issues post-release, revert to v2.x → kast retains cloud mode.

### Phase E — Polish + release (1–2 weeks)

**Goal:** ship coordinated v3.0 release.

**Deliverables:**

| # | Item | Where |
|---|---|---|
| E1 | `pipx install kast` setup (`pyproject.toml`, console_scripts) | `pyproject.toml`, `setup.cfg` |
| E2 | Docker image (`Dockerfile`, multi-stage build) | `Dockerfile` (new) |
| E3 | `kast doctor --fix` for one-shot env setup | `kast/cli/doctor.py` |
| E4 | README rewrite (v3 reality, all 13 plugins, install paths, AI features) | `README.md` |
| E5 | `genai-instructions.md` v3 rewrite | `genai-instructions.md` |
| E6 | Migration guide for v2 → v3 users | `docs/MIGRATION_V2_TO_V3.md` (new) |
| E7 | v3.0 release notes / breaking changes | `CHANGELOG.md` |
| E8 | Coordinated kast 3.0 + kast-web 3.0 release tagging | git tags, release artifacts |
| E9 | Smoke tests on Debian 12, 13, Ubuntu 24.04, Kali 2024+ | CI matrix |

**Success criteria:**
- Clean Debian 13 box: `pipx install kast && kast doctor && kast scan -t example.com` works end-to-end
- Tier 1 features all documented
- Migration guide covers cloud-mode users specifically (their workflow changes most)
- v3.0 release tags both kast and kast-web simultaneously

**Rollback:** Tagged releases. Critical post-release issues → tag v3.0.1 quickly; severe issues → recommend pinning to v2.14.x.

---

## 8. What's deliberately deferred to v3.1+

From ideation, these don't make the v3.0 cut:

- **A2 — Pre-meeting SA briefing** (Tier 2). Compelling but new artifact type; lands in v3.1 once A1 is stable.
- **A3 — Tailored remediation by audience** (Tier 2). Compounds well with A1 but doubles AI cost per scan; defer.
- **A6 — "What changed since last scan"** (Tier 3). Depends on E5 findings-diff; v3.1.
- **D1 — Expose kast as MCP server** (Tier 3). Strategic but premature; v3.1 or v3.2 depending on agent ecosystem trajectory.
- **D2 — "Ask the report" agent** (Tier 3). v3.1.
- **C1 — Adaptive scan plan** (Tier 3). Expensive bad-LLM-decisions risk; defer.
- **F3 — Shareable scan-result URL** (Tier 2). Solid v3.1 candidate.
- **F4 — Per-partner theming** (Tier 2). Solid v3.1 candidate.
- **F5 — Industry benchmarking** (Tier 4). Premature.
- **E5 — Findings diff between scans** (Tier 2). v3.1.
- **E7 — Multi-target scan** (Tier 4). v3.1.
- **Z1–Z4 — Continuous monitoring, benchmarking, exploit demo, white-label SaaS.** v3.2+ or never.

---

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AI prompt quality regresses over time as Claude models change | Med | High | Eval harness with golden outputs; pin model version per prompt; monitor regression daily during Phase C |
| AI cost overruns on a partner's account | Low (with budgets) | Med | Off-by-default; per-org budget enforcement; cost preview before each call; usage alerts |
| Hallucinations in customer-facing executive summary | Med | High | Review-by-default mode; ground prompt strictly in scan data; post-pass verification step ("does this claim appear in findings?"); deterministic fallback if AI fails |
| Plugin migration breaks tests | Med | Med | Migrate one plugin at a time; keep old base class through Phase B; CI on every plugin change |
| Cloud migration loses Terraform state during cutover | Low | High | Backup state before migration; staged cutover (kast retains cloud mode through transition); migration guide explicit on state preservation |
| Schedule slippage on F1/F2 content | High | Low | Ship with Michael-curated placeholder content; iterate post-release |
| kast↔kast-web contract accidentally violated during refactor | Low (with tests) | High | Contract test suite asserting the file-presence state machine, atomic writes, frozen filenames; runs on every PR |
| Backward compatibility wrapper for v2 argv breaks edge cases | Med | Med | Comprehensive v2-argv test suite; document any unsupported v2 invocations explicitly |
| kast-web complexity ballooning with AI + cloud additions | Med | Med | Clear module boundaries (`app/ai/`, `app/cloud/`); separate Celery queues for AI vs cloud vs scans; dedicated review on each PR |
| Anthropic API outage during a customer demo | Low | Med | Graceful fallback to deterministic exec summary; cache last successful AI summary if regenerating |
| `genai-instructions.md` not updated → AI assistants keep producing v2-shaped code | High | Med | Update genai-instructions.md as a Phase A/B deliverable, not Phase E |

---

## 10. Decisions still pending

After this plan, the open items are:

1. **Click vs Typer** for the v3 CLI dispatcher. Recommend Click (battle-tested). Easy to flip.
2. **Default Anthropic model**: Claude Sonnet 4.6 (cheaper, fast) or Opus 4.7 (highest quality). Recommend Sonnet for the standard exec-summary task; Opus available as opt-in for higher-value scans.
3. **Cost preview rounding**: show "<$0.01" vs exact "$0.0042"? UX call.
4. **Review-mode default for new orgs**: Review-then-Send (safer) vs Auto (faster). Plan recommends Review default.
5. **kast-web AI auth**: per-user API keys vs shared org-level key? Recommend org-level key with per-user audit logging — simpler ops, still traceable.
6. **B1 detection scope**: only chatbots/LLM endpoints, or also "AI-generated content," "RAG search," etc.? Phase C deliverable should pick a concrete starting set.
7. **Are there v2 plugins we want to retire in v3?** (Audit didn't surface any; flagging for explicit confirmation.)

None block Phase A or B. Items 2–6 should be answered before Phase C lands.

---

## 11. Effort and calendar

Sum-of-phases (sequential): A (1-2w) + B (2-3w) + C (4-6w) + D (2-3w) + E (1-2w) = **10–16 weeks**.

With Phase D parallelizing against late Phase B and Phase C: **calendar ~9–13 weeks** at part-time pace.

This assumes solo development with AI assistance. Adding a second contributor (or partial Barracuda product-marketing input on F2 content) could compress Phase C by 1–2 weeks.

No deadline → recommend **starting Phase A this week**, completing Phase A as a single coherent PR, and reassessing pace after.

---

## 12. Cross-cutting concerns

### 12.1 Testing strategy through the migration

- Phase A: existing 30 tests must pass; add ~10 tests for new abstractions (registry, severity enum, report data builder)
- Phase B: add v2-argv-compat test suite (~15 tests); add CLI smoke tests per subcommand (~20 tests)
- Phase C: add AI adapter contract tests (~10 tests); review workflow tests (~5 tests); F1/F2 renderer tests (~10 tests); B1 detection tests (~10 tests); eval harness golden-output tests (~5 prompts × 3 representative scans = 15 evals)
- Phase D: end-to-end cloud scan test (per provider); orphan cleanup test
- Phase E: smoke tests on each supported OS

End-of-v3 test count target: ~150–200 tests, up from 30 today.

### 12.2 Documentation discipline

- Every phase ends with documentation updates **in the same PR**, not a separate "docs phase"
- `genai-instructions.md` is updated continuously, not at the end
- Migration guide for v2→v3 users is started in Phase A, completed in Phase E
- README rewrite happens in Phase E only (no point updating it five times)

### 12.3 Backward-compatibility commitments

- kast 3.x supports v2 argv via wrapper indefinitely (low maintenance cost)
- kast 3.x continues to write v2-format `*_processed.json` files (the contract)
- kast 3.x removes `execution_mode: cloud` (this is the only v3.0 breaking change for cloud users)
- Issue registry format unchanged (just the workflow around it)
- kast-web 3.x maintains its REST API surface; deprecation cycle for any future changes

### 12.4 What v3 does NOT promise

- Backward compatibility past v3.0 (v3.1+ may revisit)
- Performance improvements (beyond fixing the busy-wait)
- Reduced disk footprint
- Windows / macOS support (Linux-only stays the deployment target)

---

## 13. v2 patches (independent of v3)

These three patches can ship to main today as v2.14.x.

### 13.1 `Info`/`Informational` severity bug

Already printed previously. File: `kast/report_templates.py`, function `get_severity()`.

### 13.2 Busy-wait in parallel scheduler

**File:** `kast/orchestrator.py`, around line 277.

**Current code (broken — busy-wait):**

```python
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Keep submitting plugins as dependencies are satisfied
            while pending_plugins or futures:
                # Submit plugins whose dependencies are satisfied
                newly_submitted = False
                for plugin_cls in list(pending_plugins.keys()):
                    # ... (submission logic) ...

                # If no plugins were submitted and we still have pending plugins,
                # check if we're in a deadlock situation
                if not newly_submitted and pending_plugins and not futures:
                    # ... (deadlock handling) ...
                    break

                # Wait for at least one plugin to complete
                if futures:
                    done, _ = as_completed(futures), None
                    for future in list(futures.keys()):
                        if future.done():
                            plugin_cls, plugin = futures[future]
                            # ... (handle completion) ...
                            del futures[future]
                            break  # Break to check for newly submittable plugins
```

**Corrected code (proper blocking wait):**

```python
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            while pending_plugins or futures:
                # Submit plugins whose dependencies are satisfied
                newly_submitted = False
                for plugin_cls in list(pending_plugins.keys()):
                    # ... (submission logic — unchanged) ...

                # Deadlock check (unchanged)
                if not newly_submitted and pending_plugins and not futures:
                    # ... (deadlock handling — unchanged) ...
                    break

                # Block until at least one future completes, then process it
                if futures:
                    # Use next(as_completed(futures)) to block on the first
                    # completion without iterating the entire iterator.
                    done_future = next(as_completed(futures))
                    plugin_cls, plugin = futures[done_future]
                    plugin_name = plugin.name
                    try:
                        result = done_future.result()
                        results.append(result)
                        completed_plugins[plugin_name] = result
                        self.log.info(f"Plugin {plugin_name} completed with disposition: {result.get('disposition')}")
                    except Exception as e:
                        self.log.error(f"Plugin {plugin_name} raised an exception: {e}")
                        error_result = plugin.get_result_dict("fail", f"Future exception: {str(e)}")
                        results.append(error_result)
                        completed_plugins[plugin_name] = error_result
                    del futures[done_future]
```

The change replaces the misleading `done, _ = as_completed(futures), None` (which discards the iterator) and the busy `for future in list(futures.keys()): if future.done():` poll with a single `next(as_completed(futures))` call that blocks until a future is actually done.

### 13.3 Relative path for ZAP profile

**File:** `kast/main.py`, around line 273.

**Current code (broken — cwd-dependent):**

```python
    if args.zap_profile:
        profile_path = f"kast/config/zap_automation_{args.zap_profile}.yaml"
        log.info(f"Using ZAP profile: {args.zap_profile} ({profile_path})")
```

**Corrected code (resolves relative to package location):**

```python
    if args.zap_profile:
        # Resolve relative to the kast package directory, not the cwd.
        # This makes --zap-profile work regardless of where kast is invoked from.
        package_dir = Path(__file__).resolve().parent
        profile_path = str(package_dir / "config" / f"zap_automation_{args.zap_profile}.yaml")
        log.info(f"Using ZAP profile: {args.zap_profile} ({profile_path})")
```

The `Path(__file__).resolve().parent` resolves to `/path/to/kast/kast/`, so `kast/config/zap_automation_quick.yaml` becomes the absolute `/path/to/kast/kast/config/zap_automation_quick.yaml` regardless of `os.getcwd()`.

---

## 14. Closing

This plan is concrete enough to drive sprint planning, and structured to permit continuous shipping rather than a stop-the-world rewrite. Each phase has a clear scope, success criteria, and rollback plan. The single load-bearing assumption is that the kast↔kast-web contract documented in `docs/web-integration.md` is genuinely frozen for v3.0 — that decision is what makes the incremental approach viable.

Phase A is small enough to start this week. Recommend kicking off with the three v2 patches (sections 13.1–13.3) as a warmup PR, then proceeding through the rest of Phase A.
