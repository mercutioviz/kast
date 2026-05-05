# kast ↔ kast-web Integration Contract

This document defines the **public contract** between kast and kast-web.
All three surfaces below are FROZEN for v3.0 unless an explicit,
versioned, coordinated change is planned.

Baseline reference: `docs/baseline-v2.14/`

---

## Surface 1 — CLI Invocation

kast-web invokes the `kast` binary with command-line arguments and
reads its exit code.

- Flag names, short forms, and semantics: see `docs/baseline-v2.14/help.txt`
- Exit code conventions: celery process launches kast cli and waits for exit
  and looks at return code, 0 is OK, not 0 is failure
- Output directory is specified via [flag, e.g., `-o <dir>`]; kast-web
  creates a fresh directory per scan and passes it in.

## Surface 2 — STDOUT / STDERR

- celery process handles communication; no use of STDOUT vs STDERR at this time
- No ANSI color codes when not attached to a TTY. Verified: kast uses
  `rich.console.Console()` with default settings, which queries
  `sys.stdout.isatty()` at construction time and disables color when stdout
  is a pipe. kast-web invokes kast as a subprocess with stdout captured, so
  the captured output is plain text. Verifiable with:
  ```
  kast --version | cat | xxd | head    # should show no \x1b[ escape codes
  ```
  The Rich library is the only color source; kast does not write ANSI
  escapes directly except in two ZAP error messages
  (`kast/plugins/zap_plugin.py:651,668`) which target the user's terminal,
  not kast-web. v3 should keep the Rich-managed approach and avoid hand-
  rolled ANSI to keep this guarantee structural.

## Surface 3 — Target Output Directory (CRITICAL)

kast-web monitors the output directory by file presence to determine
plugin state. This is the most fragile surface and most behavior-
preserving constraint.

### Plugin State Machine

For each plugin `<name>` (except `zap` — see below), state is determined
by the presence of files in the output directory:

| Files Present                                                    | State     |
|------------------------------------------------------------------|-----------|
| neither `<name>.json`/`<name>.txt` nor `<name>_processed.json`   | pending   |
| `<name>.json` OR `<name>.txt` exists, no `<name>_processed.json` | running   |
| `<name>_processed.json` exists                                   | completed |

### Invariants kast MUST preserve

1. **Raw-output file is created at plugin start**, before the underlying
   tool produces meaningful output. (`.json` if the tool emits JSON
   natively; `.txt` otherwise.) Choice of extension per plugin is fixed.
2. **`<name>_processed.json` is written ONLY after the plugin has fully
   completed**, including any post-processing.
3. **Atomic writes**: `<name>_processed.json` MUST appear atomically.
   Write to `<name>_processed.json.tmp` and `rename(2)` into place, so
   a watcher never sees a partially-written completion file.
4. **No deletion of state-bearing files** mid-scan. Once a state file
   exists, it persists.
5. **Filenames are stable**: the names `<plugin>.json`, `<plugin>.txt`,
   and `<plugin>_processed.json` are part of the contract.
6. **Failure semantics**: a _processed.json file is produced with a "disposition" 
   of "failed"

### Special Case: zap

The `zap` plugin uses the standard state convention AND adds a
real-time progress file. ZAP scans can run for a long time (spider
crawl + active scan), so kast emits a live progress document that
kast-web polls for UI updates.

#### Files

| File                       | Purpose                                                    | Lifecycle                                               |
|----------------------------|------------------------------------------------------------|---------------------------------------------------------|
| `zap.json` or `zap.txt`    | Standard "plugin started" marker                           | Created at plugin start (same as others)                |
| `zap_scan_progress.json`   | Live progress: spider %, active scan %, alert counts, etc. | Created during run; updated repeatedly until completion |
| `zap_processed.json`       | Standard "plugin completed" marker                         | Written atomically at full completion                   |

#### State determination for zap

Same three states as other plugins, with `zap_scan_progress.json` as
an additional **running-state signal** that kast-web uses for richer
UI feedback (progress bars, live alert counts):

| Files Present                                                      | State     |
|--------------------------------------------------------------------|-----------|
| neither `zap.json`/`zap.txt` nor `zap_processed.json`              | pending   |
| `zap.json`/`zap.txt` present, `zap_processed.json` absent          | running   |
| ↳ within "running", `zap_scan_progress.json` provides live metrics | running   |
| `zap_processed.json` present                                       | completed |

#### Invariants kast MUST preserve for zap

1. All standard plugin invariants apply (start marker, atomic completion
   marker, frozen filenames).
2. `zap_scan_progress.json` is updated **frequently** while the scan
   runs. Each update MUST be atomic (write-to-tmp + rename) so kast-web
   never reads a half-written progress document.
3. The schema of `zap_scan_progress.json` is part of the contract.
   Documented v2.14 schema (sourced from
   `kast/scripts/zap_api_client.py:540-565`):

   ```json
   {
     "scan_started": "<ISO-8601 timestamp, e.g. 2026-04-29T17:30:00.000>",
     "last_updated": "<ISO-8601 timestamp>",
     "elapsed_seconds": <int>,
     "plan_id": "<string identifier of the ZAP automation plan>",
     "status": "running" | "completed",
     "finished": "" | true,
     "progress": {
       "spider_percent": <int 0-100>,
       "active_scan_percent": <int 0-100>,
       "passive_scan_queue": <int — items remaining in passive queue>
     },
     "alerts": {
       "total": <int>,
       "by_risk": { "<risk-level>": <int>, ... }
     },
     "job_updates": [<string log lines from ZAP automation>],
     "warnings": [<string warning lines>],
     "errors":   [<string error lines>]
   }
   ```

   All top-level keys are always present. `progress.spider_percent` and
   `active_scan_percent` are 0 until the corresponding ZAP phase begins.
   `alerts.by_risk` keys are ZAP risk levels: `"High"`, `"Medium"`,
   `"Low"`, `"Informational"` (note: "Informational", not "Info" —
   matches the issue registry severity vocabulary).
4. `zap_scan_progress.json` MAY persist after completion (kast-web
   should not depend on its disappearance to infer state — completion
   is signaled by `zap_processed.json`).
5. Update frequency: time-based, controlled by the ZAP plugin's
   `zap_config.poll_interval_seconds` configuration value (default 30
   seconds, range 5–300). The progress writer in
   `kast/scripts/zap_api_client.py` is invoked once per poll cycle by
   the monitoring loop, so the file is rewritten every
   `poll_interval_seconds`. The first write occurs at scan start
   (with elapsed_seconds=0), and a final write occurs when the scan
   transitions to `status: "completed"`.
### Directory Layout

Manifest from `docs/baseline-v2.14/sample-scan-1/` (a representative
passive-mode scan, no ZAP). Each file is annotated with its role: **S**
state-bearing (kast-web infers plugin state from its presence), **I**
informational (used for richer UI / detail views but not state),
**R** report artifact, **M** scan-level metadata.

| Size (B) | File                                    | Role | Notes |
|---------:|-----------------------------------------|:----:|-------|
| 663      | `ai_surface_detection_processed.json`   | S    | completion marker for `ai_surface_detection` |
| 2,223    | `ftap.json`                             | S    | start marker for `ftap` |
| 8,036    | `ftap_processed.json`                   | S    | completion marker for `ftap` |
| 2,855    | `kast_info.json`                        | M    | scan metadata (cli args, timings, version) |
| 86,089   | `kast_report.html`                      | R    | rendered HTML report |
| 1,618,817| `kast_report.pdf`                       | R    | rendered PDF report |
| 21,005   | `kast_style.css`                        | R    | CSS stylesheet copied next to HTML report |
| 461      | `katana.txt`                            | S    | start marker for `katana` (text output) |
| 6,181    | `katana_processed.json`                 | S    | completion marker for `katana` |
| 1,874    | `org_discovery_processed.json`          | S    | completion marker for `org_discovery` |
| 882      | `org_discovery_raw.json`                | I    | raw org discovery output (debug detail) |
| 4,164    | `related_sites.json`                    | S    | start marker for `related_sites` |
| 5,792    | `related_sites_httpx.json`              | I    | intermediate httpx output |
| 26,043   | `related_sites_processed.json`          | S    | completion marker for `related_sites` |
| 726      | `related_sites_subfinder.json`          | I    | intermediate subfinder output |
| 193      | `related_sites_targets.txt`             | I    | intermediate target list |
| 1,600    | `script_detection.json`                 | S    | start marker for `script_detection` |
| 3,256    | `script_detection_processed.json`       | S    | completion marker for `script_detection` |
| 2        | `subfinder.json`                        | S    | start marker for `subfinder` (often `[]`) |
| 923      | `subfinder_processed.json`              | S    | completion marker for `subfinder` |
| 0        | `subfinder_tmp.json`                    | I    | scratch file; may be 0 bytes or absent |
| 27,334   | `testssl.json`                          | S    | start marker for `testssl` |
| 873      | `testssl_processed.json`                | S    | completion marker for `testssl` |
| 154      | `wafw00f.json`                          | S    | start marker for `wafw00f` |
| 1,336    | `wafw00f_processed.json`                | S    | completion marker for `wafw00f` |
| 39,142   | `wafw00f_stdout.txt`                    | I    | captured wafw00f stdout (debug detail) |
| 861      | `whatweb.json`                          | S    | start marker for `whatweb` |
| 3,554    | `whatweb_processed.json`                | S    | completion marker for `whatweb` |

A ZAP-included scan additionally produces `zap.json` (start marker, **S**),
`zap_processed.json` (completion marker, **S**), and
`zap_scan_progress.json` (live progress, **I** — schema documented
above). The PDF/HTML report files (R) and `kast_info.json` (M) appear
only after every plugin completes and the report is generated; their
absence does NOT mean the scan failed mid-flight.

**Naming rules kast-web depends on:**

- `<plugin>.json` or `<plugin>.txt` is the start marker
- `<plugin>_processed.json` is the completion marker
- Files matching `<plugin>_*` (where the suffix is not exactly
  `processed`) are intermediate / informational and MUST NOT be treated
  as state by kast-web
- `kast_report.{html,pdf}`, `kast_style.css`, `kast_info.json` are
  scan-level outputs and are not plugin-keyed

---

## Surface 4 — Implementation history (gaps closed against the contract)

This section tracks contract-violating implementation details that
existed in v2 and have since been brought into compliance. Keep the
entries here so future work doesn't re-introduce the violations.

### Atomic-write requirement (RESOLVED in v3 Phase A11)

The contract requires atomic writes for `_processed.json` (state
machine § Invariants 3) and for `zap_scan_progress.json` (ZAP § Invariant
2). v2.14 wrote both directly via `with open(path, 'w') ... json.dump(...)`,
which left a window where a kast-web reader could observe a partial write.

**v3 fix:** `kast/core/atomic.py:write_json_atomic(path, data, **kwargs)`
writes to `<path>.tmp` then `os.replace`s into place. Migration of all
27 v2 call sites in `kast/plugins/*`, `kast/main.py`,
`kast/report_builder.py`, and `kast/scripts/zap_api_client.py` was the
A11 commit. Plugin authoring docs (`kast/plugins/README.md`) updated
to teach the new pattern.

**Excluded from migration (deliberately):** `kast/scripts/zap_providers.py`
and `kast/scripts/cleanup_orphaned_resources.py` are part of the cloud
subsystem migrating to kast-web in Phase D; their writes go with the
subsystem.

---

## Change-Control Rules for v3.0

- INTERNAL refactoring of how kast produces these artifacts: **free**.
- WHAT artifacts are produced, their names, locations, and formats:
  **frozen** for v3.0.
- ADDITIVE changes (new files alongside existing ones): allowed if they
  do not change the meaning of the existing state files.
- Any breaking change requires: (a) an explicit version bump, (b) a
  coordinated kast-web update plan, (c) a migration note in CHANGELOG.
