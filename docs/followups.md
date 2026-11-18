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

### Katana crawl tuning

> The earlier suspicion that katana's default `-timeout 10 -retry 1` was
> pathological is **disproven** and has been removed. A controlled four-arm
> comparison (2026-11-18, `donate.wbez.org`, `-rl 30` on every arm, varying
> only those two flags) found the defaults perfectly healthy — first URL at
> 1.0s in every arm. Non-headless totals over 45s: default 71,895,
> `-timeout 5` 83,822, `-retry 0` 65,323, both 87,860. So `-timeout 5` is worth
> roughly +17%, `-retry 0` alone is slightly *negative*, and in **headless
> mode — the plugin's default — all four arms were identical** (3.0s to first
> URL, ~312 URLs). Not worth changing a default for. The original observation
> came from varying several flags at once against a target that was behaving
> erratically; see below.

- **`-pls heuristic`, katana's default page-load strategy, makes headless
  crawling roughly 10x slower for identical results.** Established against a
  local 24-page static site built for the purpose (`/tmp/kt/mksite.py`, served
  on 127.0.0.1 — it cannot rate-limit, cannot deploy bot mitigation, and has a
  known-correct answer of 24 URLs):

  | flags | URLs | time |
  |---|---|---|
  | `-hl` (default `-pls heuristic`) | 23 | **155s** |
  | `-hl -pls load` | 23 | **15s** |
  | `-hl -pls networkidle` | 23 | **15s** |
  | `-hl -dwt 1` | 23 | 155s (no effect) |
  | non-headless | 26 | 12s |

  Reproducible across repeated runs and **identical on katana v1.6.1 and
  v1.8.0**. `-dwt` and `-time-stable` are not the cause; the strategy is. The
  plugin never sets `-pls`, so every headless scan inherits `heuristic`.

  Two things follow. **Headless is enormously more expensive than its benefit
  looks:** on `donate.wbez.org`, non-headless returned 94,139 URLs in 60s while
  headless returned ~320. And on non-JS content headless finds *fewer* URLs
  than non-headless (23 vs 26 locally). The v3.0.15 decision to default
  headless on cited "17 vs 50 URLs on an SPA, 3x" — measured on one SPA, and
  worth revisiting with this cost in view.

  **Before changing the `-pls` default, the JS-coverage question must be
  answered**: does `load` miss content `heuristic` renders? Not yet known —
  the intended SPA target (`microapps.netlify.app`) returned 0 URLs under both
  strategies despite answering curl with HTTP 200, so the comparison could not
  be run.

- **Headless against a real site intermittently produces nothing at all, and
  this is still unexplained.** Against `donate.wbez.org`: six consecutive
  `-hl -pls load` runs returned 313-322 URLs each, then minutes later the same
  command returned 0; a `-hl` heuristic run instrumented with stdout to a plain
  file sat at **0 bytes for 140 seconds** with empty stderr before being
  killed. Throughout, `curl` got HTTP 200 and the local target worked every
  time, so neither the box nor the binary is broken.

  Ruled out by direct test: `-silent` (works perfectly on the local target),
  orphaned Chrome (none accumulate, even after SIGTERM mid-crawl), stdout
  buffering (the file was genuinely 0 bytes, and SIGTERM flushes), and katana
  v1.6.1 vs v1.8.0 (identical). Remaining candidates: target-side bot
  mitigation that engages and disengages, or heuristic's per-page wait being
  unbounded on heavy real pages so nothing is ever emitted. **`-pls load` was
  the only configuration that produced output on every attempt**, which is
  suggestive but not proof.

  This matters because a repeat demo silently returning "0 URLs found" is both
  wrong and embarrassing in the room, and it is the one failure the
  partial-crawl banner cannot catch — a zero-URL crawl reports itself complete.

- **katana v1.8.0 is built and staged at `/opt/katana-1.8.0/katana`**, left
  deliberately outside `PATH` so the v3.0.52 pin at v1.6.1 still governs.
  Every one of the 21 flags the plugin emits exists in 1.8.0, so the argv
  contract holds. It fixes none of the behaviour above. Two changes to validate
  if the pin is ever bumped: v1.7.0 enforced **RDN scope label boundaries**
  (the plugin runs `field_scope=rdn` and derives all host classification from
  it), and v1.7.0 added **content-similarity dedup**, which overlaps
  `VOLATILE_QUERY_PARAMS`.

- **The plugin crawls at katana's default 150 requests/second.** `rate_limit`
  defaults to 150, matching katana's own default, so the plugin passes no `-rl`
  and inherits it. That is aggressive against a prospect's infrastructure and
  sits awkwardly with this project's rule that scans must never look like an
  attack. It is also a plausible trigger for the mitigation theory above. No
  change proposed yet — lowering it trades crawl completeness for politeness,
  and that is a judgement call worth making deliberately rather than as a side
  effect of a bug hunt.

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
