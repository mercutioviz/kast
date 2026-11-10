# Follow-ups

Defects and papercuts surfaced while working on something else, deferred rather
than fixed in place to keep changes scoped. Unlike `v3.1-backlog.md` — which is
forward-looking capability ideas — everything here is a known rough edge in
shipped code.

Add an item when you find something real but out of scope for the change in
hand. Remove it when it ships.

## Open

### Config

- **`kast scan rerun` rejects `--set`.** You cannot re-render an existing scan
  under different plugin config (e.g. `katana.report_scope`) without re-running
  the crawl. `kast scan rerun` takes only `SCAN_DIR`; `--set` is a `kast scan`
  option. Surfaced while validating katana's `report_scope` against a completed
  scan — the workaround was to drive `post_process` directly from Python.

- **`kast config init` freezes defaults, so schema default changes never reach
  existing users.** The generated `~/.config/kast/config.yaml` writes out every
  schema default as an explicit value. Once written, a later change to a
  `config_schema` default is silently overridden on that machine. Concretely:
  the dev box's config pins `katana.crawl_duration: 0`, so katana's new bounded
  default of 300s does not apply there — only the `max_runtime` backstop does.
  Options: emit only non-default values, write the file commented-out, or record
  a schema version and re-sync on upgrade.

### kast-web integration

- **`katana_progress.json` gained a `termination` field and a `"terminated"`
  status.** kast-web's crawl progress view treats the file as
  `crawling | stalled | done`; a crawl stopped by `max_runtime` or
  `stall_timeout` now reports `"terminated"` and should be shown as a partial
  result rather than a completed one.

- **`katana_processed.json` gained a `crawl_scope` block.** Per-host breakdown
  (classification, unique URL counts, `reported` flag) plus
  `reported/excluded/unique` totals and a `complete` flag. The HTML and PDF
  reports render it; kast-web's scan-details page does not.

### Katana output quality

- **JavaScript concatenation fragments are reported as URLs.** Katana extracts
  string literals out of JS and emits things like
  `/files/wbez/js/'+e.iframeSrc+'` as discovered paths. Harmless but visibly
  wrong in a prospect-facing report. Needs a filter for URLs containing JS
  operator syntax.

- **Crawl volume is dominated by share links and CDN image transforms.** On
  donate.wbez.org, katana wrote 115,532 lines for 14,263 unique URLs (8.1x
  duplication). `?url=` accounted for 20,654 occurrences, almost all
  `cst.brightspotcdn.com/dims4/.../resize/...?url=` image variants and
  `twitter.com/intent/tweet?url=` share buttons. A default `extension_filter`
  or a query-parameter-aware dedupe would cut crawl time and output size
  substantially.

- **Cache-busting query parameters create an unbounded crawl frontier.** The
  headless browser mints a fresh `_ga` client ID and `?_=<timestamp>` on every
  page load, so katana sees a new URL each time and never exhausts the frontier
  — observed looping between `www.wbez.org/?_ga=...` and
  `api-static.wbez.org/scripts/libphonenumber-min.js?_=...`. The `max_runtime`
  and `stall_timeout` bounds now stop the hang, but the underlying waste
  remains. Katana's `-cos` (crawl-out-scope regex) or stripping known volatile
  params before the frontier check would address the cause.

### Tooling

- **Katana is not version-pinned.** `tested_tool_version = "1.6.1"` is advisory
  only — nothing fails if the installed binary differs, unlike the ZAP image
  digest pin (`check_zap_image_pin`). An upstream katana change can alter crawl
  behaviour under a demo. Consider a `kast doctor` check.

- **Dev dependencies are missing from the installed venv.** `/opt/kast/venv`
  has neither `pytest` nor `ruff` despite both being declared dev deps, and the
  system `python3` lacks `tldextract`, so neither interpreter can run the suite
  as documented in CLAUDE.md. Running tests currently requires bridging the two
  (`PYTHONPATH=~/.local/lib/python3.13/site-packages /opt/kast/venv/bin/python -m pytest`).
