# Changelog

All notable changes to kast are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Patch versions v3.0.1 through v3.0.20 are tracked in git commit history only**
> (see `git log --oneline`). Each commit subject names the version it shipped under.
> This CHANGELOG resumes structured release notes at v3.0.21.

## [3.0.42] — 2026-08-19

### Added

- **`Severity.CRITICAL`** — the issue registry has carried five `Critical`
  entries since May (`SSLv2`, `cert-expired`, `exposed-env-file`,
  `exposed-backup-file`, `cors-credentials-with-reflected-origin`), but the
  enum didn't have the member, so `Severity.from_registry("Critical")`
  returned `UNKNOWN`. Consequences in shipped reports: the badge read
  "Unknown"; the findings were excluded from the WAF stats' high/medium/low
  buckets; and because `severity_sort_key` mapped them to the UNKNOWN index,
  an exposed `.env` file sorted *below* every Informational finding. The
  CORS plugin's own widget rendered
  `cors-credentials-with-reflected-origin` as Critical while the main issue
  table of the same report called it Unknown.

  CRITICAL now sorts ahead of HIGH and is rendered in the HTML report
  (severity nav badge, issue section, `.severity-badge-critical`), the PDF
  report (cover-page count box, `Critical Severity Issues` section), the
  scan-diff report, `kast scan diff`'s terminal output, and
  `kast registry list/add`. `calculate_waf_statistics` gained
  `critical_severity_waf`, and the WAF card now reads "Critical & High
  Severity (WAF)".

- **`kast doctor` validates registry severities.** `check_registry_severities`
  fails if any `issue_registry.json` entry carries a severity the `Severity`
  enum doesn't recognize, naming the offending value and up to three issue
  IDs. Nothing caught the Critical gap for three months; this does.

### Changed

- **`zap-sql-injection` and `exposed-git-repository` promoted from High to
  Critical.** SQL injection is reported only after ZAP's *active* scanner
  confirms it, so it is a demonstrated compromise rather than an inferred
  risk — it outranks every pre-existing Critical entry on impact. An exposed
  `.git` directory yields everything `exposed-backup-file` (already Critical)
  does plus the full commit history, so credentials deleted from the current
  code remain recoverable; the two were a tier apart for no defensible
  reason. Both descriptions and the `.git` remediation were extended to say
  why. Registry severity mix is now Critical 7, High 26, Medium 38, Low 39,
  Informational 7.

- `cors_analyzer_plugin` reads severity from the registry via
  `get_severity()` instead of a private `_ISSUE_SEVERITY` dict, removing the
  second source of truth that let the plugin and the report disagree.

## [3.0.41] — 2026-08-19

### Added

- **`kast scan diff BASELINE_DIR CURRENT_DIR`** — compares two completed
  scan directories and reports what changed: issues resolved, issues newly
  appearing, issues present in both (with an occurrence delta), and the
  severity mix on each side. Built for the before-WAF / after-WAF demo, so
  the framing is "resolved" rather than raw set arithmetic. Issue identity
  is `(reporting plugin, issue ID)`; repeat occurrences of the same issue
  collapse into one row with a count.

  Findings whose reporting plugin did not run on **both** sides are marked
  with an asterisk and excluded from the headline resolved/new counts — a
  plugin that was skipped in the second scan cannot prove anything was
  fixed, and claiming otherwise in front of a prospect is a reputational
  hazard. `summary["has_coverage_gap"]` drives an explicit warning block in
  both output formats.

  Flags: `--json` for the full comparison dict, `--html PATH` for a
  self-contained shareable HTML report (CSS inlined, no sidecar files),
  `--show-persisting` to list the unchanged issues in the terminal.

  New modules: `kast/report/diff.py` (`load_scan_snapshot`, `compute_diff`,
  `diff_scans`, `build_headline`) and `kast/report/diff_html.py`
  (`render_diff_html`), plus `kast/templates/diff_template.html`. Closes
  backlog item E5; unblocks A6 (AI narrative over the diff).

- **`kast/tests/test_org_discovery.py`** — 70 tests covering the
  `org_discovery` plugin's apex extraction, crt.sh retry/backoff, CA-issuer
  filtering, whois and amass parsing, Shodan gating, domain correlation and
  confidence scoring, and `post_process` output contract. Several are
  regression guards for the v3.0.26 and v3.0.30 fixes. All network and
  subprocess boundaries are mocked; a captured raw payload lives at
  `kast/tests/fixtures/org_discovery_output.json`.

- **ZAP SQL-injection and session-ID issue mapping** — `zap-sql-injection`
  (mapping ZAP plugin IDs `40018`/`40019`/`40020`/`40021`/`40022`/`40024`
  — the generic, MySQL, Hypersonic, Oracle, PostgreSQL, and SQLite active
  rules) and `zap-session-id-in-url` (passive rule `3`, Session ID in URL
  Rewrite) added to `_ZAP_PLUGINID_TO_KAST_ISSUE` and to the issue
  registry. Registry is now 117 entries.

### Changed

- **CHANGELOG backfilled for v3.0.26 through v3.0.40** — 15 releases that
  previously existed only as commit subjects now have structured entries.
- **`CLAUDE.md` accuracy pass** — the stated version was 4 months and 20
  patches stale (`3.0.20` vs `3.0.40`), the registry count was `107` vs the
  actual 117, and two Open threads were wrong: the test `sys.path` hygiene
  cleanup was already complete (0 remaining), and the ruff finding count was
  18 vs the actual 3. Replaced with accurate threads covering ZAP subsystem
  churn, the 6 unresolved IDs in `missing_issue_ids.json`, and the 2 registry
  entries missing `waf_deployment_timeframe`.

---

## [3.0.40] — 2026-07-29

### Fixed

- **Stall-detection false positive on `spiderClient` jobs** — same root
  cause as the `spiderAjax` fix in v3.0.38. While a client spider crawls,
  no active scan is running, so `ascan/view/status/` returns HTTP 400. The
  exception was caught, `ascan_pct` stayed `None`, and the `else` branch
  counted a stall cycle; after 2 cycles (~60s) the plan aborted. The
  spider exemption now covers `spiderAjax` **and** `spiderClient`. Fixes a
  live failure (scan id 45, plan aborted after 64s).

### Tests

- `test_spider_client_no_stall` added to `test_zap_stall_detection.py`
  (5 tests total).

---

## [3.0.39] — 2026-07-29

### Added

- **8 ZAP passive-scan issues added to the registry** — alert strings that
  were surfacing as "not in the issue registry" warnings in scan reports:
  Cross-Domain Misconfiguration [Medium], Retrieved from Cache
  [Informational], Timestamp Disclosure - Unix [Low], Loosely Scoped
  Cookie [Informational], Information Disclosure - Information in Browser
  localStorage [Informational], User Agent Fuzzer [Informational], Server
  Leaks Version Information via "Server" HTTP Response Header Field [Low],
  and Private IP Disclosure [Low]. Each carries WAF framing, remediation
  approach, and TCO timeframes. localStorage disclosure is
  `waf_addressable: false` (code fix required); Server-header version
  disclosure is `waf_addressable: true` with a WAF-only remediation
  approach.

---

## [3.0.38] — 2026-07-28

### Fixed

- **`spiderAjax` stall-detection false positive, and cancel-on-stall** —
  the automation-framework code path for `spiderAjax`
  (`SpiderThread`/`DummyPlugin`) never updates `ajaxSpider/view/status/`;
  that endpoint returns `stopped` for the whole crawl. The previous guard
  polled it, always read `stopped`, and aborted the scan as stalled after
  2 cycles (~60s). Stall detection is now skipped entirely when the last
  `planProgress.info` message mentions `spiderAjax`, deferring to the
  caller-supplied plan timeout. The `ajaxSpider/view/status/` probe is
  removed — it was never a reliable signal on this path.
- **ZAP CLI script fixes.**

---

## [3.0.37] — 2026-07-27

### Fixed

- **`newSession` POST must use `data=`, not `params=`** — ZAP action
  endpoints require a form-encoded POST body. `_make_request` only sets
  `Content-Type` and injects the API key when `data` or `files` is truthy,
  so passing `params=` left the body empty and ZAP returned HTTP 400
  `content_type_not_supported`. The session was therefore never reset
  between scans. Verified: `params=` → 400; `data=` → `{"Result":"OK"}`.
- **Job type name corrected** from `ajaxSpider` to `spiderAjax` to match
  the automation-framework job identifier.

---

## [3.0.36] — 2026-07-27

### Added

- **`zap.local.memory_limit` config option** — `--set
  zap.local.memory_limit=<value>` (e.g. `2g`, `512m`) passes `--memory` to
  `docker run` when kast starts the ZAP container. Empty string (the
  default) applies no limit.

---

## [3.0.35] — 2026-07-23

### Added

- **Orthogonal spider-type selection** — `--set
  zap.spider_type=traditional|ajax|client` injects the chosen spider into
  the automation plan YAML at runtime, independent of the scan profile.
  kast probes live ZAP for spider availability via the corresponding API
  endpoints, falls back to the best available type with a log warning,
  reports requested-vs-used in the scan output and report when they
  differ, and preserves profile timing/depth settings across all spider
  types.
- **`kast/config/zap_automation_standard.yaml`** — 2× the depth and
  duration of the quick profile, plus `addQueryParam` and a larger
  passive/active budget. Foundation for future scan-profile work.

---

## [3.0.34] — 2026-07-23

### Fixed

- **ZAP add-on auto-update disabled during scans** —
  `-config autoupdate.checkOnStart=false` is now passed to `docker run`,
  so ZAP does not hot-swap add-ons mid-scan. Prevents the
  `NoClassDefFoundError` crash where the report job referenced a
  classloader that `DownloadInstaller` had already replaced.
- **Stall detection for silent plan crashes** — `wait_for_plan_completion`
  now detects when `planProgress.info` stops growing while the last entry
  ends with `started`. It checks active-scan status: if ascan is still
  under 100% the scan is legitimately running and kast keeps waiting; if
  ascan is done or unavailable for 2 consecutive cycles, kast aborts
  rather than blocking for the full 3600s timeout.

---

## [3.0.33] — 2026-07-22

### Fixed

- **ZAP 2.17 / ExtensionNetwork compatibility (local Docker)** — ZAP 2.14+
  binds to localhost inside the container by default, which blocks Docker
  port mapping. `network.localServers.mainProxy.address=0.0.0.0` is now
  added to the `docker run` command so the mapped port is reachable from
  the host. All `ZAPAPIClient` requests are routed through the ZAP proxy
  session using the `http://zap/` API hostname, required in 2.14+ where
  ExtensionNetwork serves the API via the proxy interface rather than
  directly at the bound port.
- **`post_process` handles the flat alerts list** returned by the ZAP API
  (`findings['alerts']`) in addition to the older site-tree XML report
  format (`findings['site']`), including the `riskcode`/`pluginId` field
  naming difference between the two.
- **`zap_watch_live.py` proxy-based API access** — `build_url` constructs
  `http://zap/` URLs and `fetch_json` routes through a `ProxyHandler`, for
  the same ExtensionNetwork reason.

---

## [3.0.32] — 2026-06-12

### Fixed

- **`script_detection` missing `findings_count`** on the failure path in
  `post_process`. kast-web's scan-details page requires the field on every
  processed dict.
- **`script_detection` user agent** changed from
  `KAST-Security-Scanner/1.0` to a Chrome UA — sites blocking obvious
  scanner strings no longer return 404.

### Tests

- `test_doctor_updates`: observatory mock updated to `npm list -g` output
  format; `test_no_other_spec_has_a_resolver` updated to include
  `mdn-http-observatory-scan`.
- `test_related_sites_error_handling`: `executive_summary` assertion
  corrected from `list` to `str`.
- `test_script_detection_config`: two user-agent default assertions
  updated.

---

## [3.0.31] — 2026-06-11

### Added

- **`kast doctor` tool-version drift check** — each plugin wrapping an
  external tool declares `tested_tool_version` as a class attribute (the
  version it was last validated against). A new `check_tested_versions()`
  pass runs by default, no flag needed: **OK** when installed matches
  tested-against, **WARN** on drift (with a hint to run `--check-syntax`),
  **INFO** when the version can't be read. Covered: testssl (3.3), whatweb
  (0.6.4), wafw00f (2.4.2), katana (1.6.1), subfinder (2.14.0),
  mdn-http-observatory (1.6.2). Visibility only — `--check-syntax` remains
  the enforcement gate.

---

## [3.0.30] — 2026-06-11

### Fixed

- **`org_discovery` CA skip used exact matching** — `_CA_SKIP_SUBSTRINGS`
  replaces the exact-match `_CA_SKIP` set, so `DigiCert`, `DigiCert Inc`,
  and `DigiCert, Inc.` all match. The old set held `digicert inc`, but
  certificates often carry just `DigiCert`, causing the CA to be
  identified as the site owner and passed on to amass and Shodan.
- **`amass -org` flag removed** — dropped in amass v4/v5, causing exit
  code 1 on v5.1.1. Passive `-d` enumeration is unaffected.
- **crt.sh 502 retry** — added alongside the existing 503 retry; both are
  transient server-side errors that benefit from exponential backoff.

---

## [3.0.28] — 2026-06-11

### Fixed

- **`ftap` returned `disposition=fail` on zero results** — ftap exits 0
  and logs "No results to export" without writing its output file when no
  admin panels are found. The plugin pre-creates an empty `ftap.json` as a
  progress marker, so `json.load()` on a 0-byte file raised
  `JSONDecodeError` and was caught as a failure. The file is now read as a
  string first and parsed only if non-empty, otherwise an empty dict is
  used. This also unblocks the sensitive-path and login-portal probes,
  which never ran while the exception short-circuited `run()`. Confirmed
  via live scan: `/server-status` (200) now surfaces under
  `exposed-debug-endpoint`.
- **`aiohttp` added to `requirements.txt`** — ftap's launcher at
  `/usr/local/bin/ftap` activates the kast venv, so its async HTTP
  dependency must be installed there. Without it ftap crashed on startup
  with `ModuleNotFoundError` and `is_available()` returned False.
- **`whatweb` output fields** — `format_summary` now returns a string (was
  a list); `count_findings` counts URLs analyzed (was unique tech names);
  `format_executive_summary` reports EOL detections instead of being empty
  on non-redirect scans; `extract_issues` refactored onto a shared
  `_collect_eol_detections` helper.
- **`related_sites` executive summary** returned the `summary_points` list
  directly instead of joining it into a string.
- **`observatory` output** — removed a spurious `-= ... =-` prefix from
  `executive_summary`; added `_generate_details()` describing each failing
  test with its result code and score modifier, so `details` is no longer
  empty on a successful scan.

### Tests

- 4 regression tests in `test_plugin_parsing.py` covering the above.

---

## [3.0.26] — 2026-06-11

### Added

- **Regression-prevention framework.** `kast doctor --check-syntax` calls
  `check_plugin_commands()`: for each plugin exposing `get_dry_run_info()`
  it builds the command, extracts the `--flags`, and verifies each appears
  in the binary's `--help` output — catching upstream flag renames before
  they reach production.
- **`kast/tests/fixtures/`** — 5 real scan outputs (wafw00f, whatweb,
  testssl, cors_analyzer, observatory) committed as parsing fixtures.
- **`kast/tests/test_plugin_parsing.py`** — 22 fixture-based tests
  covering the full `parse` → `extract_issues` → `post_process` pipeline
  without requiring the tools to be installed, including a dedicated
  regression test for the testssl false-all-clear-on-failure bug.

### Fixed

- **`testssl`**: replaced the removed `--connect-timeout` with
  `--socket-timeout` (a 3.3dev change); added a fail-disposition guard in
  `post_process()`, which previously fell through to the normal path and
  emitted a misleading "no issues found" summary on failure.
- **`whatweb`**: `_EOL_TECHNOLOGIES` key `"jQuery"` → `"JQuery"` to match
  WhatWeb's actual output — jQuery 1.x EOL detections were silently
  missing.
- **`ftap`**: `is_available()` probes `ftap --version` instead of only
  `shutil.which()`, catching a broken runtime (missing `aiohttp`) that
  `which` cannot detect.
- **`org_discovery`**: strips leading and trailing quotes from the
  `org_name` extracted from the crt.sh `issuer_name` field
  (`O="DigiCert"` → `DigiCert`).
- **Third-party tool installation consistency** (`install.sh`): Go tools
  install to `GOBIN=/usr/local/bin`; whatweb and testssl.sh install from
  git with symlinks; wafw00f installs via pipx to `/usr/local/bin`;
  Node.js upgraded 22 → 24 (required by mdn-http-observatory >= 1.4.9);
  bare `cd` calls in `install_golang_manual` and `install_ftap` fixed;
  `*.egg-info` excluded from rsync so stale metadata no longer lands in
  `/opt/kast`.
- **`doctor.py`**: reads the observatory installed version via
  `npm list -g` instead of `--version` (the binary hard-codes 1.0.0
  regardless of package version); install and update hints updated per
  tool.

---

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
