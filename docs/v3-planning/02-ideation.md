# kast v3 — Capability and Ideation Pass

Status: Phase 2 deliverable. Inputs: Phase 1 audit (`01-audit.md`), confirmed scoping decisions (cloud → kast-web, kast↔kast-web contract frozen for v3.0, AI-augmented analysis is the headline AI capability).

This document is **a menu, not a plan**. The goal is to surface every credible capability v3 could include — including ideas Michael hasn't yet considered — so Phase 3 can pick a coherent subset.

Each entry has: short description, value (sales-enablement framing), effort, risk, and any preconditions. A ranking suggestion is at the end.

---

## How to read this document

Capabilities are grouped by theme, not priority. The themes are:

1. **AI-augmented analysis** — the headline AI capability, multiple variants
2. **Sales-enablement moat** — capabilities OSS scanners will never build for you
3. **AI-aware target detection** — turning AI features into WAF talking points
4. **AI-driven orchestration & agent integration** — kast inside the agent ecosystem
5. **Engineering payback from the audit** — non-AI v3 wins that surfaced during Phase 1
6. **Adjacent / speculative** — flagged but not recommended for v3

Effort scale: **S** (1–2 days), **M** (1–2 weeks), **L** (1–2 months), **XL** (multi-month / cross-cutting). Risk scale: **Low / Med / High** with one-line reason.

---

## 1. AI-augmented analysis

The single biggest force multiplier for the SA conversation. Ranked from "most concrete" to "most ambitious."

### A1. LLM-generated executive summary  *(headline candidate)*

**What:** Feed the aggregated findings into an LLM with a "Barracuda WAF Solutions Architect" persona prompt. Produce a 3–5 paragraph narrative that connects findings into a coherent risk story for a non-technical reader, ending with the WAF/WaaS framing.

**Today:** Executive summary is concatenated plugin-emitted strings plus a templated "N issues found, severity breakdown by …".

**Sales-enablement value:** High. The exec summary is the report's most-read section and the springboard for the SA conversation. A model-written narrative outclasses templated concatenation by a wide margin.

**Effort:** M. Prompt engineering, API integration, error/fallback handling, cost gating, and (if shipping with the report) human-review workflow.

**Risk:** Med. Hallucinations could put wrong claims in a customer-facing artifact. Mitigations: ground the prompt strictly in registry data + scan findings, forbid the model from inventing facts, add a "verified against findings" post-pass, ship a deterministic-fallback template if the model call fails.

**Preconditions:** Resolve the AI runtime architecture (self-hosted vs Anthropic API vs user-pluggable) — see open question 5 in audit.

### A2. Pre-meeting briefing for the SA  *(separate artifact, sales-only)*

**What:** A one-page internal document the SA reads before the meeting. Different audience than the customer report. Includes "top 3 issues to lead with," "questions the prospect is likely to ask given these findings," "objection handling notes," and "competitive angles" (e.g., if Cloudflare or Akamai is detected, includes Barracuda-vs-them framing).

**Sales-enablement value:** Very high. This is what an SA actually wants on their second monitor in a discovery call, and **no OSS scanner will ever produce it.** It's the moat.

**Effort:** M–L. Prompt engineering plus a small "competitive intel" knowledge base that has to be Barracuda-curated. Not big; just opinionated.

**Risk:** Med. Internal-only output reduces hallucination blast radius vs A1. Competitive claims need to be carefully sourced.

**Preconditions:** A1 architecture decided. A small Barracuda competitive-intel YAML (could start from Michael's existing notes).

### A3. Tailored remediation by audience

**What:** Each issue today has one remediation string. Generate audience-specific phrasings: technical (precise config), business/risk owner (business-impact framing), developer (code-level), and SA-talking-point. The registry's base remediation seeds the model, the audience selector swaps the rendering.

**Sales-enablement value:** High. The customer's CTO and CISO read the same report — making it speak to both is a real win.

**Effort:** M. Mostly templating + prompt design. Cost scales linearly with issue count per scan.

**Risk:** Low–Med. Bounded by the source remediation; less generative than A1.

**Preconditions:** A1 architecture decided.

### A4. Tech-stack-aware narrative

**What:** Combine WhatWeb (detected tech) + TestSSL (TLS posture) + Observatory (headers) + ZAP (active findings) into a single narrative *per detected platform*. "Your Apache 2.4.41 + Drupal 9 stack has these specific exposures: …" instead of generic listing.

**Sales-enablement value:** High. Story-driven exec summaries beat list-driven ones in customer comprehension.

**Effort:** M. Cross-plugin findings aggregation + LLM rendering.

**Risk:** Med. Tech stack mis-attribution (e.g., "Drupal 9" detected but actually on a CDN cached page) could mislead.

**Preconditions:** A clean cross-plugin findings model (engineering payback E1 helps).

### A5. WAF-relevance scoring & "lead with these issues"

**What:** Today every issue is `waf_addressable: true | false`. Extend to a numerical "pitch score" combining severity, waf_addressable, and pattern-match to Barracuda WAF feature set. Output: top-5 issues to lead with. Could be deterministic (algorithm + Barracuda feature YAML) or LLM-augmented.

**Sales-enablement value:** High. Tells the SA exactly where to spend their first 10 minutes in the conversation.

**Effort:** S–M. Deterministic version is small; LLM version adds dependency.

**Risk:** Low. Internal scoring; doesn't go to customer directly unless we surface the ranking in the executive summary.

### A6. "What changed since the last scan" narrative

**What:** When kast-web has multiple scans of the same target, the LLM authors a delta narrative: "Since your last scan in March, you've fixed 3 issues, introduced 2 new exposures, and 4 remain unchanged. Most notable: …"

**Sales-enablement value:** High for repeat conversations and renewal pitches. Strong angle for partners running periodic scans for managed-service customers.

**Effort:** M. Requires kast-web persistence + a diff engine (engineering payback E5).

**Risk:** Low. Narrowly scoped on actual data.

---

## 2. Sales-enablement moat

Capabilities that **only kast/kast-web can build for Barracuda**, because the surrounding industry isn't going to.

### F1. "Code fix vs WAF deployment" TCO appendix  *(strongest moat)*

**What:** The registry already has `code_fix_timeframe` and `waf_deployment_timeframe`. Auto-generate an appendix: *"Addressing all detected issues in code: estimated 6–8 weeks of development effort. With Barracuda WAF/WaaS: 1–2 days to baseline coverage."* Plus a per-issue side-by-side table.

**Sales-enablement value:** Maximum. This is the WAF pitch translated into numbers a CFO can read. Nobody else's scanner does this — they have no incentive to.

**Effort:** S. The data already exists in the registry. The work is rendering the appendix and verifying the timeframes are consistent.

**Risk:** Low. Quantitative, not generative; defendable.

**Sub-question to resolve:** Are the timeframes in the current registry calibrated, or were they typed in once and never reviewed? Worth a sanity pass with the field team.

### F2. Barracuda WAF feature → findings map

**What:** A YAML map of Barracuda WAF/WaaS feature names to the categories of findings each addresses. e.g., *"Bot Mitigation → addresses these detected issues: [list]"*, *"Application DDoS Protection → these: …"*. Auto-generate a "Why Barracuda" section in the report listing the matched features.

**Sales-enablement value:** Very high. Translates findings into product placement language the prospect's procurement team understands.

**Effort:** S–M. The map itself is content (maintained by Michael / Barracuda product marketing); the rendering is straightforward.

**Risk:** Low. Bounded by the curated map.

**Compounds with:** A1 (LLM-generated exec summary can reference these features by name).

### F3. Shareable scan-result URL with view tracking

**What:** kast-web exposes a public-readable URL for a completed scan that the SA can share with the prospect. Records views (did the prospect open it? when?). Optional comments / inline questions.

**Sales-enablement value:** High. Replaces "I'll email you a 1.6 MB PDF" with "here's a link." Plus the SA learns whether the prospect engaged — concrete signal for follow-up timing.

**Effort:** M (kast-web side, not kast). Auth, expirable links, view tracking, optional comments.

**Risk:** Med. Prospect data on a sharable URL needs reasonable security posture (UUID-style tokens, revocability, optional access codes).

### F4. Per-partner / per-customer report theming

**What:** v2 already supports `--logo`. Extend to a YAML profile: header/footer text, color scheme, custom intro paragraph, custom outro / call-to-action, replacement for the default "Why Barracuda" section. Useful for partner sales engineers presenting under their own branding with a Barracuda backstop.

**Sales-enablement value:** High for the partner channel — partners want to lead with their own brand. Lower-friction adoption.

**Effort:** S–M.

**Risk:** Low.

### F5. Comparative benchmarking against industry / region

**What:** Anonymized aggregate of past scans → "Your security posture compared to industry peers: 2nd quartile." Or by region, by industry vertical, etc.

**Sales-enablement value:** Very high *if it can be done credibly*. "Your peers are doing X" is a powerful closing argument.

**Effort:** L. Requires (a) enough scan history, (b) consistent industry/region tagging, (c) statistical rigor to avoid misleading conclusions, (d) privacy-preserving aggregation.

**Risk:** High. Bad statistics in a customer-facing artifact is worse than no statistics. Easy to overstate.

**Recommendation:** Flag for v3.1 or later. Premature now.

---

## 3. AI-aware target detection

Topical (2026) and well-aligned with Barracuda's evolving WAF AI-protection messaging.

### B1. AI / chatbot / LLM-API surface detection  *(extends v2 ai_chatbot_detection)*

**What:** Detect chatbots, LLM-powered assistants, embedded AI features, exposed model endpoints (OpenAI proxies, custom inference servers, public Anthropic/Bedrock endpoints, etc.). v2 already has a starting plugin (`ai_chatbot_detection_plugin.py`); v3 broadens it.

**WAF angle:** *"Your AI-powered customer support is a new attack surface — prompt injection, jailbreaks, model exfiltration. Barracuda WAF can apply LLM-specific protections."* Strong 2026 talking point.

**Effort:** M. Detection signatures, fingerprints, output formatting.

**Risk:** Low. Detection-only; no active probing.

### B2. MCP server / public agent endpoint detection

**What:** Identify public MCP servers, exposed agent endpoints, n8n/zapier/zapier-like exposed automation flows. Increasingly common as agents proliferate; rarely auth'd properly.

**WAF angle:** Same as B1 plus zero-trust messaging.

**Effort:** S–M. New detection rules, mostly.

**Risk:** Low.

### B3. AI-content / RAG / AI-search surface mapping

**What:** Identify whether the site uses RAG-based search, AI-generated content, vector-DB-backed features. Each has its own risk profile (training-data poisoning, retrieval prompt injection, etc.).

**WAF angle:** Newer, more speculative. Probably v3.1+ unless Barracuda has explicit messaging here today.

**Effort:** M.

**Risk:** Med. Detection is harder; false positives more likely.

---

## 4. AI-driven orchestration and agent integration

### C1. Adaptive scan plan

**What:** First-pass passive scan finds Drupal → second pass adds Drupal-specific scanners. Finds an exposed API → kicks off API-specific scanning (e.g., 42Crunch, OpenAPI fuzzing). LLM as a "scan planner" that reads early findings and emits a follow-up plan.

**Value:** Med–High. Scans find more without manual intervention.

**Effort:** L. Requires a real plan-execution layer; risks expensive/slow scans driven by bad LLM decisions.

**Risk:** Med–High. Cost / runtime predictability suffers if the planner picks aggressive followups.

**Recommendation:** Flag for v3.1 — promising but premature.

### C2. Cross-plugin findings clustering

**What:** TestSSL says TLSv1.0; Observatory says weak TLS; WhatWeb sees Apache version with known TLS issues. Cluster these into a single "TLS modernization required" finding instead of presenting three.

**Value:** High. Reduces report noise; makes severity counts more meaningful.

**Effort:** M. Either deterministic (registry-driven, by category) or LLM-augmented.

**Risk:** Low for the deterministic version.

### D1. Expose kast as an MCP server  *(agent ecosystem play)*

**What:** Implement the Model Context Protocol so other agents (Claude Code, Anthropic API users, custom agents) can call `kast.scan(target)`, `kast.list_plugins()`, `kast.get_findings(scan_id)` as tools.

**Value:** Strategic. Two specific use-cases:
- An SA in Claude says *"scan barracuda.com and tell me about its AI exposure,"* and Claude orchestrates kast.
- A customer integrates kast into their own AI-assistant workflow ("our agent runs nightly scans against our domain").

**Effort:** M. MCP is a small protocol; the work is exposing the right surfaces, auth, rate-limiting.

**Risk:** Med. Public MCP server is also a new attack surface; needs careful auth / quota design.

**Strategic note:** First-mover positioning in "WAF tooling exposed via MCP" is plausibly defensible.

### D2. Built-in "ask the report" agent

**What:** kast-web exposes a chat interface over completed scans. *"What would Barracuda WAF actually do for finding #4?"* / *"Summarize this report for our CFO."* / *"Generate a remediation Jira ticket for the High severity issues."*

**Value:** High for repeat-engagement value of kast-web.

**Effort:** M. Mostly kast-web frontend + LLM API + grounding the LLM in scan data.

**Risk:** Med (same hallucination concerns as A1).

---

## 5. Engineering payback from the audit

Non-AI v3 wins surfaced during Phase 1. These don't add capability per se — they make capabilities cheaper to add.

### E1. `ExternalToolPlugin` base + plugin authoring revival

Collapse 30–50KB plugins to ~150 lines. Enables faster addition of new tools (sqlmap, nikto, nuclei, gobuster, feroxbuster, droopescan, etc.). **Pays back per future plugin added** — and you'll add more during v3 capability work.

**Effort:** M. Real but bounded.

### E2. Issue-registry workflow CLI

`kast registry promote <output_dir>` reads `missing_issue_ids.json` and produces draft entries (using the inferred metadata) for review. `kast registry add <issue_id> --severity ...` for direct adds. Eliminates the `fix_registry.py` workflow.

**Effort:** S–M. Strong bang for the buck.

### E3. Versioned, JSON-everywhere CLI subcommand structure

`kast scan ...`, `kast plugins list --json`, `kast registry add/promote/list`, `kast doctor`, `kast self-update`. Backward-compatibility via wrapper for the v2 argv contract during v3.0.

**Effort:** M. Lots of small pieces.

### E4. Single severity enum + cross-pipeline normalization

Solves the `Info` vs `Informational` bug at the source. Prevents recurrence.

**Effort:** S. Three to four files.

### E5. Findings diff between scans

"Compared to last quarter: 2 new, 5 fixed, 3 unchanged." Strong sales angle (and **prerequisite** for A6 LLM-narrated diffs).

**Effort:** M. kast or kast-web; probably the latter since it has the persistence.

### E6. Webhook on scan completion

Slack/Teams/Jira/etc. integration. Cheap; useful for kast-web's enterprise / partner users.

**Effort:** S. Single endpoint, configurable URL + payload shape.

### E7. Multi-target scan in one invocation

`kast scan --targets a.com,b.com,c.com` for "scan our 5 main domains." Cross-target deduplication of findings (one TLS issue across all subdomains becomes one finding).

**Effort:** M.

### E8. Unified report pipeline (HTML + PDF)

Eliminate the copy-pasted parallel pipelines (audit 5a.1). Shared `_collect_report_data()` + thin renderers. **Required** for many of the AI-augmented capabilities above to land cleanly.

**Effort:** M. Real; pays back forever.

### E9. Better install model (pipx + `kast doctor` + optional Docker)

Replaces ~80% of `install.sh`. Covers SAs (single-laptop install) and partners (sealed environment).

**Effort:** M.

---

## 6. Adjacent and speculative

Flagged for awareness; not recommended for v3.

### Z1. Continuous monitoring mode

Re-scan periodically, alert on changes. **Different product position** (managed assessment vs one-shot threat scan). Probably out of scope for v3 but a logical v3.1 extension if customer feedback demands it.

### Z2. Comparative benchmarking (= F5)

Already covered. Hard to do credibly; defer.

### Z3. Self-attack simulation

Run actual exploit tooling (responsibly, with explicit prospect authorization) to demonstrate a vulnerability rather than just describe it. Reputationally risky for the same reasons "active mode" is — magnified. Probably never.

### Z4. White-label SaaS offering

kast-web as a hosted multi-tenant service, sold to MSSPs. Big undertaking; very different product. Definitely not v3.

---

## 7. Suggested ranking for v3 inclusion

If I had to pick the v3 cut today, ordered by recommended priority:

**Tier 1 — must-do, high value, manageable effort:**

1. **A1. LLM-generated executive summary** — the headline AI capability you've already prioritized.
2. **F1. "Code fix vs WAF" TCO appendix** — pure moat; data already exists.
3. **F2. Barracuda WAF feature → findings map** — pure moat; small content effort.
4. **B1. AI surface detection (extended)** — topical 2026 angle; foundation already in v2.
5. **E8. Unified report pipeline** — required infrastructure for A1, A3, A4.
6. **E2. Issue-registry workflow CLI** — unblocks registry currency.
7. **E1. ExternalToolPlugin base** — pays back per future plugin.

**Tier 2 — strong value, defer if bandwidth tight:**

8. A2. Pre-meeting SA briefing
9. A3. Tailored remediation by audience
10. A5. WAF-relevance scoring + "lead with these"
11. F3. Shareable scan-result URL (kast-web side)
12. F4. Per-partner/customer theming
13. E3. JSON-everywhere CLI subcommand structure
14. E5/E6. Findings diff + webhook (kast-web side)
15. C2. Cross-plugin findings clustering
16. E4. Severity enum unification

**Tier 3 — strategic but timing uncertain:**

17. D1. MCP server interface (depends on Anthropic agent ecosystem trajectory)
18. A4. Tech-stack-aware narrative (compounds well with A1 once stable)
19. A6. "What changed since last scan" narrative (depends on E5)
20. D2. "Ask the report" agent (kast-web side)

**Tier 4 — defer to v3.1+:**

21. B2. MCP / agent endpoint detection
22. B3. AI-content / RAG mapping
23. C1. Adaptive scan plan
24. F5. Industry benchmarking
25. E7. Multi-target scan
26. Z1. Continuous monitoring

---

## 8. Open questions that ideation surfaces

- **AI runtime architecture**: Anthropic API call from the SA's laptop? From kast-web (server-side)? Self-hosted small model? User-pluggable adapter layer? Affects A1, A2, A3, A4, A6, C1, D2.
- **Cost gating**: at scale, LLM-augmented reports cost real money per scan. Per-customer caps? Optional? Free-tier vs paid-tier?
- **Output review workflow**: do LLM-generated narratives need SA approval before they go to the prospect, or do we trust the prompt + grounding? Affects velocity of the SA's workflow.
- **kast vs kast-web split for AI**: most AI-augmented capabilities are easier to land in kast-web (server-side, persistent, multi-user, cost gating) than in kast (single-shot CLI). Does v3 keep AI in kast at all, or is it all kast-web?
- **Barracuda product-marketing alignment**: F1 and F2 require Barracuda-curated content. Who owns the WAF feature → findings map? Is there an existing Barracuda asset to seed from?

These need decisions before Phase 3 lands a coherent design.
