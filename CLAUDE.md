# Kast — CLI Tool

## Project Identity
Kast (current v2.14) is a CLI tool that orchestrates security scanning
plugins (nmap, nikto, zap, etc.) on Debian. A separate web front-end
(`kast-web`, in `~/kast-web`) consumes kast. Kast must NEVER depend on
kast-web.

See `docs/VISION.md` for full scope and tenets.

## Current Effort: Refactor to v3.0
Goals:
1. Maintain 100% behavioral compatibility with v2.14 for the kast-web
   contract (see `docs/web-integration.md`)
2. Clean architecture: core / plugin framework / CLI / utilities
3. Maintainability, extensibility, thorough documentation
4. New CLI utilities for power users (scope decided in Phase 1)
5. No "AI slop", no spaghetti, no speculative abstractions

Working branch: `refactor/v3.0`
Baseline behavior captured in: `docs/baseline-v2.14/`

## Domain Context — Security Tooling
Kast automates offensive security tools used in authorized testing.
- NEVER weaken or remove input validation on targets, ports, or flags
- NEVER make defaults more aggressive (rate, scope, intrusiveness)
  without explicit instruction
- NEVER remove confirmations, dry-run modes, timeouts, or rate limits
- The installer is security-sensitive: no `curl|bash`, verify checksums
  where present, flag any new privileged operations
- Every underlying tool invocation must remain auditable (log the exact
  command executed)

## The kast-web Contract (CRITICAL — read before editing)
kast-web depends on THREE public surfaces:
1. CLI args, flags, exit codes
2. STDOUT / STDERR content
3. Target output directory artifacts (plugin state machine)

Plugin state is inferred by kast-web from file presence:
- `<plugin>.json` or `<plugin>.txt` absent → pending
- `<plugin>.json`/`.txt` present, `<plugin>_processed.json` absent → running
- `<plugin>_processed.json` present → completed

Invariants:
- Raw output file is created at plugin start
- `_processed.json` is written ONLY at full completion
- `_processed.json` MUST be created atomically (write-to-tmp + rename)
- Filenames `<plugin>.json`, `<plugin>.txt`, `<plugin>_processed.json`
  are FROZEN
- The `zap` plugin is a documented special case — see web-integration.md

Full contract: `docs/web-integration.md`

## Architectural Principles
- Strict separation: core engine / plugin interface / CLI presentation /
  filesystem I/O
- Plugins are isolated, replaceable units behind a clear interface
- Public APIs have docstrings: purpose, args, returns, raises, examples
- Prefer pure functions and composition; avoid inheritance trees
- One responsibility per module; one reason to change

## Coding Standards
- [language-specific style: e.g., PEP8 + ruff / gofmt + golangci-lint]
- Type annotations required on public APIs
- Tests required for new logic; refactors require behavioral tests first
- No dead code, no commented-out code, no orphan TODOs

## Workflow Rules for Claude
- ALWAYS produce a written plan before editing more than one file;
  wait for approval
- ALWAYS show diffs for architectural changes; do not bulk-rewrite
- NEVER add a dependency without asking
- NEVER introduce an abstraction (base class, plugin meta-framework,
  config layer) until at least TWO concrete use cases require it
- NEVER change a contract surface (see above) silently — propose a
  versioned, additive path instead
- Prefer many small, reviewable commits over sweeping rewrites
- After each meaningful change: run linter and tests; report results
- If intent is unclear, ASK — do not guess

## What "Done" Looks Like (per phase)
- Lints clean, tests pass
- Behavioral baseline still matches (`docs/baseline-v2.14/`)
- kast-web smoke test passes against the new build
- Public docs updated; CHANGELOG entry written
- Diff is small enough for a human to review in one sitting

## Phases (high level)
- Phase 0: Audit only, read-only. Output: `docs/audit-v2.14.md`
- Phase 1: Architecture proposal. Output: `docs/ARCHITECTURE.md` and
  a phased migration plan
- Phase 2: Phased refactor execution
- Phase 3: CLI power-user utilities (scope from Phase 1)
- Phase 4 (separate effort, separate repo): kast-web v2.0
