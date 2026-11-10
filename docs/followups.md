# Follow-ups

Defects and papercuts surfaced while working on something else, deferred rather
than fixed in place to keep changes scoped. Unlike `v3.1-backlog.md` — which is
forward-looking capability ideas — everything here is a known rough edge in
shipped code.

Add an item when you find something real but out of scope for the change in
hand. Remove it when it ships.

## Open

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

### Tooling

- **Katana is not version-pinned.** `tested_tool_version = "1.6.1"` is advisory
  only — nothing fails if the installed binary differs, unlike the ZAP image
  digest pin (`check_zap_image_pin`). An upstream katana change can alter crawl
  behaviour under a demo. Consider a `kast doctor` check.
