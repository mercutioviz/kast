# Kast — Vision and Scope

## What Kast Is
Kast is a CLI tool that orchestrates a curated set of security scanning
tools (commonly distributed with Kali Linux, but installable on Debian)
into a single, repeatable, plugin-driven workflow. Each underlying tool
(nmap, nikto, gobuster, zap, etc.) is wrapped as a kast "plugin."

## Who It's For
- Authorized security testers running scans against systems they own
  or are explicitly permitted to test
- Operators who want CLI-first, scriptable, reproducible scans
- The kast-web front-end, which drives kast programmatically

## Primary Use Cases
1. Run a multi-tool scan against a target and collect all artifacts
   into a single, structured output directory
2. Provide a stable surface that kast-web can drive and observe
3. (Future) Empower CLI power users with utilities for analysis,
   reporting, comparison, and automation on top of scan results

## Design Tenets
- **Plugin-driven**: each tool is an isolated, replaceable unit
- **Filesystem-first**: all results live as files in an output directory,
  human-browsable and machine-parseable
- **Observable**: external observers (kast-web) can determine state by
  looking at files alone — no IPC required
- **Debian-compatible**: Kali is not a hard dependency
- **Deterministic invocation**: the exact command run by each plugin
  is recorded for auditability

## Out of Scope
- Acting as a network service or daemon
- Replacing or wrapping kast-web functionality
- Performing unauthorized scanning, enabling evasion, or weakening
  safety/validation in pursuit of "convenience"
- Auto-exploitation (kast scans and reports; it does not exploit)

## Refactor Goals (v3.0)
1. Clean, modular architecture with a clear core/plugin/CLI separation
2. Maintainability and extensibility (adding a new plugin should be
   small, obvious, and well-documented)
3. Thorough documentation: every public function, every plugin contract,
   every output artifact
4. 100% behavioral compatibility with v2.14 for the kast-web contract
5. New CLI utilities for power users (scope TBD in architecture phase)
6. No "AI slop": no speculative abstractions, no untested code, no
   silent behavior changes
