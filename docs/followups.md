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

- **katana's results against one target became erratic and then went to zero,
  while the site stayed healthy.** Found while running the comparison above,
  and **not explained**. After sustained crawling of `donate.wbez.org`
  (including one 113,698-URL run), identical commands that had returned
  71,895 URLs non-headless and 312 headless began returning **0**, headless and
  non-headless alike, across five consecutive runs. Throughout, `curl` got
  HTTP 200 in ~29 ms, katana crawled `httpbin.org` normally, and katana with
  `-v` still crawled `donate.wbez.org` and printed `GET` lines — so neither the
  site, the network, nor the binary was broken.

  Candidate explanations, none confirmed: target-side bot or WAF mitigation
  keyed to crawl volume; katana state (it writes a resume file per interrupted
  run — 11 had accumulated in `~/.config/katana/`); or an interaction with
  `-silent` and the stdout destination. Worth isolating on a **fresh target
  with no prior crawl history**, changing one variable at a time, rather than
  continuing against a site this box has already hammered.

  This matters more than the timeout question it replaced. A repeat demo
  against the same prospect silently returning "0 URLs found" is both wrong and
  embarrassing in the room, and it is the exact failure mode the partial-crawl
  banner cannot catch, because a zero-URL crawl reports itself as complete.

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
