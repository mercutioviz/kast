# Release validation — kast 3.0.0 / kast-web 2.0.0

This is the manual smoke-test checklist (Phase E9 of the v3 release plan). Tags are created locally; this is the pre-push validation.

The two repos release as a coordinated bundle:

- **kast**: tag `v3.0.0` on `refactor/v3.0` (latest commit).
- **kast-web**: tag `v2.0.0` on `refactor/v2.0` (latest commit).

Don't push the tags until at least one supported OS passes the smoke-test below. If pushing the tag would be irreversible (mirrored CI, automatic release builders), validate first.

---

## OS smoke-test matrix

Run on each supported OS at least once before declaring the release shippable.

| OS | Status | Notes |
| -- | ------ | ----- |
| Debian 13 (Trixie) | TODO | Recommended primary |
| Debian 12 (Bookworm) | TODO | Recommended secondary |
| Ubuntu 24.04 LTS | TODO | |
| Kali Linux 2025.x | TODO | |

For each OS, run the test sequence below on a fresh VM or container. A clean `git clone` + installer pass + sample scan is the bar.

---

## Smoke-test sequence

### 1. Install

Pick one install path. The recommended sequence for SA / production use:

```bash
# Fresh box
git clone https://github.com/mercutioviz/kast.git
cd kast
git checkout v3.0.0
sudo ./install.sh --auto       # non-interactive; expect to take 10-20 minutes
```

Alternative for kast-CLI-only:

```bash
pipx install kast==3.0.0
kast doctor --fix
```

### 2. Verify environment

```bash
kast --version                 # expect 3.0.0
kast doctor                    # expect 0 FAIL; some WARN is acceptable for missing optional tools
kast plugins list              # expect 12 plugins
```

### 3. Run a passive scan

```bash
kast scan --target example.com --output-dir /tmp/smoke-passive
```

Confirm:
- Scan completes without uncaught exceptions
- `/tmp/smoke-passive/kast_report.html` exists and renders correctly in a browser
- `/tmp/smoke-passive/kast_report.pdf` exists and opens cleanly
- `/tmp/smoke-passive/kast_info.json` is well-formed JSON
- Per-plugin `*_processed.json` files exist for every plugin that ran

### 4. Run with `--ai-summary` (optional, requires API key)

```bash
export KAST_AI_API_KEY=sk-ant-...
kast scan --target example.com --ai-summary --output-dir /tmp/smoke-ai
```

Confirm:
- `kast_info.json` contains `ai.status == "success"` and non-zero `tokens_in`/`tokens_out`
- HTML report contains the `<div class="ai-summary">` block with `headline`, `narrative`, `key_findings`, `recommended_actions`
- The deterministic "Identified Issues" block is hidden when AI summary is present

### 5. Verify failure mode

```bash
KAST_AI_API_KEY=invalid kast scan --target example.com --ai-summary --output-dir /tmp/smoke-ai-fail
```

Confirm:
- Scan still completes, report still renders
- `kast_info.json` contains `ai.status == "error"` with a populated `error` field
- HTML contains the `.ai-error-banner` and the deterministic `executive_summary` block

### 6. kast-web (if applicable)

If the box is hosting kast-web 2.0:

```bash
cd /home/mscollins/kast-web
git fetch && git checkout v2.0.0
sudo bash deployment/deploy-v2.sh         # or your deployment script
```

Confirm:
- DB migration runs cleanly (`utils/migrate_cloud_v2.py` adds CloudCredential / CloudScan / CloudOrphan)
- Web UI loads at the configured URL
- Login + scan submission still works (passive scan is the simplest case)
- `/admin/cloud/credentials` admin page renders and accepts a test credential
- A cloud-mode ZAP scan (with real cloud credentials) provisions, scans, and tears down

---

## After all OS targets pass

Push the tags:

```bash
cd /home/mscollins/kast
git push origin refactor/v3.0
git push origin v3.0.0

cd /home/mscollins/kast-web
git push origin refactor/v2.0
git push origin v2.0.0
```

Then announce / merge to main per your release process.

---

## Rollback

If a critical issue is found after tagging but before pushing:

```bash
# kast
cd /home/mscollins/kast
git tag -d v3.0.0

# kast-web
cd /home/mscollins/kast-web
git tag -d v2.0.0
```

Fix, recommit, re-tag.

If a critical issue is found **after** pushing tags:

- Tag a `v3.0.1` / `v2.0.1` patch as soon as the fix is ready.
- For severe regressions, recommend users pin to the prior stable release (v2.14.x for kast, v1.5.x for kast-web).
- Don't force-push to remove a tag that's been pushed; that breaks anyone who already pulled.
