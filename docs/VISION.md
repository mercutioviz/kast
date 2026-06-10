# kast — Vision and Scope

## What kast is

kast is Barracuda's "ETS for web apps" — a CLI tool that orchestrates a curated set of web-application security scanners (WhatWeb, Wafw00f, TestSSL, Mozilla Observatory, Subfinder, Katana, FTAP, OWASP ZAP, and others) into a single, repeatable, plugin-driven workflow, then renders the findings as a digestible HTML and PDF report. v3 adds an opt-in AI-augmented executive summary, a TCO appendix translating findings into "code-fix vs WAF-deployment" effort, and an "AI surface detection" plugin that flags chatbots and AI-driven search/RAG endpoints.

kast pairs with [kast-web](https://github.com/mercutioviz/kast-web), a Flask + Celery + Redis frontend that drives the kast CLI through a browser, manages cloud-hosted ZAP infrastructure, and (in v2.0+) hosts the centrally-budgeted AI summary service.

## Who it's for

- **Barracuda Solutions Architects and partner sales engineers** — the primary audience. kast is sales enablement: a way to turn a prospect's URL into a credible WAF/WaaS conversation in minutes.
- The kast-web frontend, which drives kast programmatically.
- Authorized security testers running scans against systems they own or are explicitly permitted to test.

The README frames kast for a broader audience, but the product is built around the SA workflow.

## Primary use cases

1. Run a multi-tool scan against a prospect's web target and produce a polished HTML/PDF report that frames findings as WAF/WaaS opportunities.
2. Provide a stable surface that kast-web can drive (CLI argv, file-presence state machine, atomic-write contract).
3. Surface the AI-era attack surface (chatbots, RAG, agent integrations) alongside traditional web vulnerabilities.

## Design tenets

- **Reliability and reputational safety first.** An SA cannot run a flaky tool in front of a prospect; an active scan must never look like an attack against the prospect's infrastructure. Every change weighs against these two constraints.
- **Plugin-driven.** Each tool is an isolated, replaceable unit. New scanners are a single-file effort.
- **Filesystem-first.** All results live as files in an output directory — human-browsable, machine-parseable, atomically written so external watchers never observe partial state.
- **Observable.** kast-web (or any external observer) determines plugin state by file presence alone. No IPC required, no protocol drift.
- **Debian-compatible.** Kali is convenient; not a hard dependency.
- **Deterministic invocation.** The exact command run by each plugin is recorded for auditability.
- **AI is opt-in, gracefully degrading.** `--ai-summary` is off by default. When enabled, a network failure or API outage falls back to the deterministic summary plus a banner — the report always renders.

## Out of scope

- Acting as a network service or daemon (kast-web owns that surface).
- Auto-exploitation. kast scans and reports; it does not exploit.
- Performing unauthorized scanning, enabling evasion, or weakening safety / validation in pursuit of "convenience."
- General-purpose security tooling. kast is a sales-enablement product with a clear audience; it intentionally does not try to be everything to everyone.

## Pointers

- Current architecture, patterns, and house style: [`CLAUDE.md`](../CLAUDE.md)
- v3.1 backlog (deferred Tier 2/3/4 capabilities, plugin candidates): [`docs/v3.1-backlog.md`](v3.1-backlog.md)
- kast↔kast-web boundary contract: [`docs/web-integration.md`](web-integration.md)
- Migration guide for v2.x users: [`docs/MIGRATION_V2_TO_V3.md`](MIGRATION_V2_TO_V3.md)
- v3 design history: [`docs/v3-planning/`](v3-planning/)
