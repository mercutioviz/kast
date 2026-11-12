# Follow-ups

Defects and papercuts surfaced while working on something else, deferred rather
than fixed in place to keep changes scoped. Unlike `v3.1-backlog.md` — which is
forward-looking capability ideas — everything here is a known rough edge in
shipped code.

Add an item when you find something real but out of scope for the change in
hand. Remove it when it ships.

## Open

### kast-web integration

Both items below are **kast-web work in `/home/mscollins/kast-web/`**, not kast
work. The kast side is finished: `docs/web-integration.md` now documents both
documents under "Special Case: katana", and
`kast/tests/test_katana_web_contract.py` pins the key sets so the doc cannot
drift from what the plugin emits. Worth batching with the other two open
kast-web threads in CLAUDE.md (the `kast -ls` → `kast plugins list --json`
migration, and the AI service).

**Open decision for that session:** whether katana progress mirrors ZAP's
DB-backed shape (`ZapScanProgress` in `app/models.py`, plus the preservation
step in `app/tasks.py`) or is read through from `katana_progress.json` per
request. ZAP's model survives scan-directory cleanup and keeps the two progress
surfaces consistent; read-through needs no migration. Deliberately left open —
it depends on kast-web conventions, not on anything kast decides.

- **kast-web does not read `katana_progress.json` at all.** It has no katana
  progress view — only ZAP has one (`app/models.py:821`,
  `app/tasks.py:855`) — so a crawl shows as an opaque "in progress" for its
  whole duration. When it gains one, `status: "terminated"` (and equivalently
  `crawl_scope.complete: false`) MUST render as a partial result, not a
  completed one.

- **kast-web's scan-details page does not render `crawl_scope`.** Per-host
  breakdown plus `reported/excluded/unique` totals and the `complete` flag.
  Both report formats render it; the web UI does not. Note the rule from the
  contract doc: report `reported_url_count`, never `unique_url_count`, as
  "URLs found".

### Katana stall detection

- **Stall detection counts lines in `katana.txt`, which katana writes through a
  32 KiB buffer — so a working crawl gets killed as stalled.** `_count_lines`
  polls the `-o` file every 3s and `stall_timeout` fires when the count has not
  moved. katana flushes that file only when its 32 KiB buffer fills, so the
  count reports flush events, not discovery.

  **Mechanism confirmed by direct measurement** (2026-11-12, katana v1.6.1,
  harness at `/tmp/kt/probe.py` — sampled the `-o` file, stdout, and process-
  tree CPU once per second). Crawling `donate.wbez.org` with `-hl`, over 70
  seconds the output file took **exactly two sizes: 0 and 32768 bytes**, while
  stdout advanced continuously:

  | t | `-o` file | stdout | lag |
  |---|---|---|---|
  | 8s  | 0 bytes / 0 lines      | 32 lines  | 32 lines |
  | 24s | 32768 bytes / 258 lines| 278 lines | 20 lines |
  | 70s | 32768 bytes / 258 lines| 302 lines | 44 lines |

  The detector saw **zero** URLs for the first 23 seconds and a frozen 258 for
  the following 46, while the crawl was working the whole time. That is exactly
  the live incident on 2026-11-10: 251 frozen, `stall_timeout` at 228.1s, then
  305 once the buffer flushed at kill.

  **The fix is to read stdout instead of the `-o` file.** The same run proves
  stdout is not subject to that buffer — it tracked discovery closely even when
  redirected to a file. Two earlier guesses are now ruled out: file **mtime is
  useless** as a second signal (it only changes on flush, so it carries exactly
  the same information as the line count), and **process-tree CPU**, while a
  valid liveness signal (~1.0-1.8 s/s while crawling, 11-12 processes under
  `-hl`), is unnecessary complexity once stdout is available.

  **Severity is higher than it looks: it only bites in headless mode, which is
  the default.** The same crawl *without* `-hl` produced 113,698 URLs in 75s,
  so the buffer refilled constantly and the file tracked stdout to within 3
  lines — the defect is invisible there. Headless crawls are low-volume
  (302 URLs in 70s), so they sit below the flush threshold for minutes at a
  time. Any site yielding under 32 KiB of URLs per `stall_timeout` window is
  liable to be cut short while working.

- **katana's default `-timeout 10 -retry 1` may be pathological on dead hosts.**
  Noticed while building the harness above, and **not yet confirmed**: manual
  runs using katana's defaults hung for 45-150s against `example.com` and
  `donate.wbez.org` producing nothing at all, while the same commands with
  `-timeout 5 -retry 0` began emitting URLs immediately. The plugin passes
  neither flag, so it inherits the defaults. Could be a slow-host tail, could
  be environmental; needs a controlled comparison before anything is changed.

### Katana output quality

- **Percent-encoded JS template literals reach the report.**
  `allegro.wbez.org/$%7BdonateUrl%7D` was reported as a URL on the same crawl.
  `JS_SOURCE_ARTIFACT` deliberately matches only a literal `${`, because `%7B`
  is legal in a URL and treating it as a fragment risks dropping real ones.
  Cosmetic rather than wrong, and much rarer than the raw `'+e.x+'` form the
  filter does catch, but it is the same class of defect.

- **Cache-busting parameters still reach the crawl frontier.** Report-time
  canonicalization (`VOLATILE_QUERY_PARAMS`) now collapses the duplicates, and
  the default `extension_filter` keeps static assets out of the output, but
  neither stops katana *requesting* a cache-busted URL it has already seen. The
  headless browser mints a fresh `_ga` client ID and `?_=<timestamp>` per page
  load, so the frontier still has no fixed point — observed looping between
  `www.wbez.org/?_ga=...` and
  `api-static.wbez.org/scripts/libphonenumber-min.js?_=...`. `max_runtime` and
  `stall_timeout` bound the hang; the waste remains. Katana's `-cos`
  (crawl-out-scope regex) is the candidate fix, and needs validating against a
  live site first: a regex that over-matches silently shrinks the reported
  surface, which is worse than the waste it removes.

### Plugin internals

- **`katana.json` is deleted when the katana process exits**
  (`katana_plugin.py`, `os.remove(in_progress_file)`), which contradicts
  invariant 4 of the kast↔kast-web contract ("no deletion of state-bearing
  files mid-scan"). It is benign today — `katana.txt` exists by then and is
  the start marker the Directory Layout table actually lists — so this is
  documented as a deliberate exception rather than fixed. Worth revisiting if
  the state machine ever stops treating `.txt` as a start marker, since the
  exception is the only thing keeping katana's "running" state observable.
