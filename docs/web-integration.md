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
- Exit code conventions: [TODO: enumerate from v2.14 source]
- Required vs. optional args: [TODO: enumerate]
- Output directory is specified via [flag, e.g., `-o <dir>`]; kast-web
  creates a fresh directory per scan and passes it in.

## Surface 2 — STDOUT / STDERR

- STDOUT format: see `docs/baseline-v2.14/scan*.stdout`
- STDERR format: see `docs/baseline-v2.14/scan*.stderr`
- kast-web parses STDOUT for [TODO: list patterns found via grep of
  kast-web source]
- No ANSI color codes when not attached to a TTY (verify current behavior)

## Surface 3 — Target Output Directory (CRITICAL)

kast-web monitors the output directory by file presence to determine
plugin state. This is the most fragile surface and most behavior-
preserving constraint.

### Plugin State Machine

For each plugin `<name>` (except `zap` — see below), state is determined
by the presence of files in the output directory:

| Files Present                                           | State     |
|--------------------------------------------------------|-----------|
| neither `<name>.json`/`<name>.txt` nor `<name>_processed.json` | pending   |
| `<name>.json` OR `<name>.txt` exists, no `<name>_processed.json` | running   |
| `<name>_processed.json` exists                         | completed |

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
6. **Failure semantics**: [TODO: confirm from v2.14 — does a failed
   plugin still produce `_processed.json`? With what content? Is there
   a `<name>_failed.json` or similar? Document the observed behavior.]

### Special Case: zap

The `zap` plugin uses the standard state convention AND adds a
real-time progress file. ZAP scans can run for a long time (spider
crawl + active scan), so kast emits a live progress document that
kast-web polls for UI updates.

#### Files

| File                       | Purpose                                  | Lifecycle                                  |
|----------------------------|------------------------------------------|--------------------------------------------|
| `zap.json` or `zap.txt`    | Standard "plugin started" marker         | Created at plugin start (same as others)   |
| `zap_scan_progress.json`   | Live progress: spider %, active scan %, alert counts, etc. | Created during run; updated repeatedly until completion |
| `zap_processed.json`       | Standard "plugin completed" marker       | Written atomically at full completion      |

#### State determination for zap

Same three states as other plugins, with `zap_scan_progress.json` as
an additional **running-state signal** that kast-web uses for richer
UI feedback (progress bars, live alert counts):

| Files Present                                                    | State     |
|-----------------------------------------------------------------|-----------|
| neither `zap.json`/`zap.txt` nor `zap_processed.json`           | pending   |
| `zap.json`/`zap.txt` present, `zap_processed.json` absent       | running   |
| ↳ within "running", `zap_scan_progress.json` provides live metrics | running   |
| `zap_processed.json` present                                    | completed |

#### Invariants kast MUST preserve for zap

1. All standard plugin invariants apply (start marker, atomic completion
   marker, frozen filenames).
2. `zap_scan_progress.json` is updated **frequently** while the scan
   runs. Each update MUST be atomic (write-to-tmp + rename) so kast-web
   never reads a half-written progress document.
3. The schema of `zap_scan_progress.json` is part of the contract.
   Document its current fields exactly as v2.14 emits them. Known
   fields include (verify against baseline):
  * spider progress (%)
  * active scan progress (%)
  * alert counts (by severity)
  * [TODO: capture full schema from a live baseline scan]
4. `zap_scan_progress.json` MAY persist after completion (kast-web
   should not depend on its disappearance to infer state — completion
   is signaled by `zap_processed.json`).
5. Update frequency: [TODO: measure from baseline — is it polled-on-
   change, time-based, every N seconds? Document and preserve.]
### Directory Layout

[TODO: paste the `find ... | sort` manifest from a representative
baseline scan, annotated with which files are state-bearing vs.
informational.]

---

## Change-Control Rules for v3.0

- INTERNAL refactoring of how kast produces these artifacts: **free**.
- WHAT artifacts are produced, their names, locations, and formats:
  **frozen** for v3.0.
- ADDITIVE changes (new files alongside existing ones): allowed if they
  do not change the meaning of the existing state files.
- Any breaking change requires: (a) an explicit version bump, (b) a
  coordinated kast-web update plan, (c) a migration note in CHANGELOG.
