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

### Katana output quality

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

### update.sh

Both found while deploying v3.0.52. Neither is new; both make a failed or
partial update look like a successful one, which is the shape of problem that
surfaces at the worst moment.

- **`git pull` failure is swallowed, and then reported as "already up to
  date".** `if ! git pull origin $(git branch --show-current) 2>&1 | tee -a
  "$UPDATE_LOG"` tests the exit status of `tee`, not of `git`, so a failed pull
  always passes. The commit comparison that follows then finds HEAD unchanged
  and logs `Repository is already up to date`. Observed live: under `sudo` the
  SSH key is not available to root, so both `git fetch` and `git pull` died
  with `Permission denied (publickey)` and the script continued as if current.
  Harmless when the working tree is already ahead of origin — which is why the
  v3.0.52 deploy was still correct — but on a box where origin genuinely has
  new commits, update.sh will deploy stale code and report success. Fix with
  `PIPESTATUS[0]` or `set -o pipefail` around the pull.

- **The post-update plugin-count validation cannot fail.** Two bugs stacked:
  it calls `python -m kast.main --list-plugins`, a v2 flag the v3 CLI no longer
  has (now `kast plugins list`), so nothing matches; and
  `grep -c "Plugin:" || echo "0"` appends a second `0` to grep's own `0` when
  grep exits non-zero, producing the literal `0\n0`. That yields
  `./update.sh: line 588: [[: 0\n0: syntax error` and then logs
  `✓ 0\n0 plugins available` as a **success**. A real "no plugins available"
  regression would pass validation unnoticed.

### Plugin internals

- **`katana.json` is deleted when the katana process exits**
  (`katana_plugin.py`, `os.remove(in_progress_file)`), which contradicts
  invariant 4 of the kast↔kast-web contract ("no deletion of state-bearing
  files mid-scan"). It is benign today — `katana.txt` exists by then and is
  the start marker the Directory Layout table actually lists — so this is
  documented as a deliberate exception rather than fixed. Worth revisiting if
  the state machine ever stops treating `.txt` as a start marker, since the
  exception is the only thing keeping katana's "running" state observable.
