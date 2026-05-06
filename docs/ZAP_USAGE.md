# ZAP Usage in kast

OWASP ZAP (Zed Attack Proxy) is the engine behind kast's active and passive web-application scanning. This document covers the three execution modes, the internal call flow, the five built-in automation profiles, configuration options, and troubleshooting.

---

## Execution modes

kast supports three ZAP execution modes, controlled by the `zap.execution_mode` config key.

### local

kast manages a ZAP Docker container on the same machine. If a container named `kast-zap-local` (or the configured `container_name`) is already running, kast reuses it. If not, and `auto_start: true` (the default), kast starts one automatically.

**Requirements:**
- Docker installed and running
- `ghcr.io/zaproxy/zaproxy:stable` image pulled (or internet access to pull on first run)

**Best for:** developer workstations, standalone scan machines, situations where no external ZAP is available.

### remote

kast connects to an already-running ZAP instance over HTTP. The ZAP instance can be anywhere — another machine on the network, a container in a cloud environment, or a kast-web-provisioned instance.

**Requirements:**
- ZAP reachable at the configured URL
- ZAP started with `api.filexfer=true` (required for the automation framework upload flow)
- API key configured consistently on both sides (or left empty if ZAP was started without one)

**Best for:** CI/CD pipelines, kast-web cloud scans, shared scanning infrastructure.

### auto

kast selects a mode automatically:

1. If `KAST_ZAP_URL` is set in the environment → use **remote** with that URL
2. If a running Docker container using the ZAP image is found → use **local** (reuse it)
3. If `auto_start: true` → start a new local Docker container

`auto` is the default and works correctly in most environments without any configuration.

---

## Internal call flow

Every scan goes through the same pipeline regardless of mode. The ZAP plugin (`kast/plugins/zap_plugin.py`) owns the flow; `LocalZapProvider` and `RemoteZapProvider` (`kast/scripts/zap_providers.py`) abstract the mode-specific steps.

```
zap_plugin.run()
  │
  ├─ _load_config()          reads zap_config.yaml + CLI --set overrides
  │
  ├─ provider.provision()    mode-specific: start/find/connect to ZAP instance
  │    LocalZapProvider:  _find_running_zap_container() or _start_zap_container()
  │                        waits up to 120 s for ZAP API to respond
  │    RemoteZapProvider: ZAPAPIClient.get_version() — connectivity check only
  │
  ├─ _load_automation_plan() reads the profile YAML from kast/config/
  │
  ├─ provider.upload_automation_plan(plan_content, target_url)
  │    Step 1: POST /OTHER/core/other/fileUpload/
  │              fileContents = plan YAML bytes
  │              fileName     = kast_automation_plan.yaml
  │            → response: {"Uploaded": "/path/on/zap/server/kast_automation_plan.yaml"}
  │
  │    Step 2: POST /JSON/automation/action/runPlan/
  │              filePath = path returned in step 1
  │            → response: {"planId": "42"}    (or {"Result": "OK"} on older ZAP)
  │
  ├─ provider.wait_for_plan_completion(timeout, poll_interval)
  │    Polls GET /JSON/automation/view/planProgress/?planId=42
  │    every poll_interval seconds until "finished" appears or timeout expires
  │    Writes progress snapshots to output_dir/zap_progress_*.json
  │
  ├─ provider.download_results(output_dir, "zap_report.json")
  │    LocalZapProvider:  checks volume-mounted /zap/reports/ first;
  │                       falls back to ZAP JSON report API
  │    RemoteZapProvider: GET /JSON/core/other/jsonreport/ → writes to file
  │
  ├─ post_process()          parses zap_report.json, maps ZAP alerts to
  │                          kast issue registry entries, builds _processed.json
  │
  └─ provider.cleanup()
       LocalZapProvider:  stops and removes container only if cleanup_on_completion: true
       RemoteZapProvider: no-op (kast-web owns lifecycle)
```

---

## Built-in automation profiles

Select a profile with `--set zap.zap_config.automation_plan=<path>` or by editing `zap_config.yaml`.

| Profile | Path | Duration | Active scan | Use case |
|---------|------|----------|-------------|----------|
| standard | `kast/config/zap_automation_plan.yaml` | ~45 min | Yes | Default — balanced development testing |
| quick | `kast/config/zap_automation_quick.yaml` | ~20 min | Yes | CI/CD pipelines, fast checks |
| thorough | `kast/config/zap_automation_thorough.yaml` | ~90 min | Yes | Pre-production, major releases |
| passive | `kast/config/zap_automation_passive.yaml` | ~15 min | **No** | Production-safe, observation only |
| api | `kast/config/zap_automation_api.yaml` | ~30 min | Yes | REST APIs and microservices |

### standard profile

Balanced spider (depth 5, 2 threads, 10 min) → passive scan → active scan (30 min, 2 threads).

```yaml
# kast/config/zap_automation_plan.yaml
env:
  contexts:
    - name: "target-context"
      urls:
        - "${TARGET_URL}"
      includePaths:
        - "${TARGET_URL}.*"
      excludePaths:
        - ".*logout.*"
        - ".*signout.*"
  parameters:
    failOnError: true
    failOnWarning: false
    progressToStdout: true

jobs:
  - type: "spiderClient"
    parameters:
      maxDuration: 10      # minutes
      maxDepth: 5
      threadCount: 2
      parseComments: true
      parseGit: true
      parseRobotsTxt: true
      parseSitemapXml: true

  - type: "passiveScan-config"
    parameters:
      maxAlertsPerRule: 10
      scanOnlyInScope: true

  - type: "passiveScan-wait"
    parameters:
      maxDuration: 10

  - type: "activeScan"
    parameters:
      context: "target-context"
      maxRuleDurationInMins: 5
      maxScanDurationInMins: 30
      handleAntiCSRFTokens: true
      threadPerHost: 2

  - type: "report"
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

### quick profile

Uses the traditional (non-Ajax) spider at depth 3 for speed. Active scan capped at 15 minutes. Suited for automated checks on every pull request.

```yaml
# kast/config/zap_automation_quick.yaml
jobs:
  - type: "spider"            # traditional spider — faster than spiderClient
    parameters:
      maxDuration: 5
      maxDepth: 3
      threadCount: 2

  - type: "passiveScan-config"
    parameters:
      maxAlertsPerRule: 5
      scanOnlyInScope: true

  - type: "passiveScan-wait"
    parameters:
      maxDuration: 5

  - type: "activeScan"
    parameters:
      maxRuleDurationInMins: 3
      maxScanDurationInMins: 15
      threadPerHost: 2

  - type: "report"
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

### thorough profile

Ajax spider at depth 10 with 4 threads and a 60-minute active scan window. Run before major releases or demos against targets where comprehensive coverage matters more than speed.

```yaml
# kast/config/zap_automation_thorough.yaml
jobs:
  - type: "spiderClient"
    parameters:
      maxDuration: 20
      maxDepth: 10
      threadCount: 4
      handleODataParametersVisited: true

  - type: "passiveScan-config"
    parameters:
      maxAlertsPerRule: 20
      scanOnlyInScope: true
      enableTags: true

  - type: "passiveScan-wait"
    parameters:
      maxDuration: 15

  - type: "activeScan"
    parameters:
      maxRuleDurationInMins: 10
      maxScanDurationInMins: 60
      threadPerHost: 4

  - type: "report"
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

### passive profile

**No `activeScan` job.** ZAP only crawls and observes — it never injects payloads. This is the only profile safe to run against a live production site.

```yaml
# kast/config/zap_automation_passive.yaml
jobs:
  - type: "spiderClient"
    parameters:
      maxDuration: 10
      maxDepth: 5
      threadCount: 1          # single thread — gentle on production
      requestWaitTime: 300    # 300 ms between requests

  - type: "passiveScan-config"
    parameters:
      maxAlertsPerRule: 10
      scanOnlyInScope: true

  - type: "passiveScan-wait"
    parameters:
      maxDuration: 10

  # No activeScan block — intentionally omitted

  - type: "report"
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

### api profile

Optimized for REST APIs: shallow spider (depth 2), no HTML form processing, `addQueryParam: true` for parameter injection, `handleAntiCSRFTokens: false` (APIs use bearer tokens, not form CSRF tokens). The context `includePaths` pattern matches `/api/` and versioned paths like `/v1/`, `/v2/`.

```yaml
# kast/config/zap_automation_api.yaml
env:
  contexts:
    - name: "api-context"
      urls:
        - "${TARGET_URL}"
      includePaths:
        - "${TARGET_URL}/api/.*"
        - "${TARGET_URL}/v[0-9]+/.*"
      excludePaths:
        - ".*logout.*"

jobs:
  - type: "spiderClient"
    parameters:
      maxDuration: 3
      maxDepth: 2
      postForm: false         # APIs don't use HTML forms
      processForm: false
      handleODataParametersVisited: true

  - type: "passiveScan-config"
    parameters:
      maxAlertsPerRule: 10
      scanOnlyInScope: true

  - type: "passiveScan-wait"
    parameters:
      maxDuration: 5

  - type: "activeScan"
    parameters:
      context: "api-context"
      maxScanDurationInMins: 25
      addQueryParam: true         # inject into query string parameters
      handleAntiCSRFTokens: false
      scanHeadersAllRequests: true
      threadPerHost: 3

  - type: "report"
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

---

## Configuration reference

The master config file is `kast/config/zap_config.yaml`. Any key can be overridden at scan time with `--set zap.<key>=<value>`.

```yaml
execution_mode: auto   # auto | local | remote

auto_discovery:
  prefer_local: true
  check_env_vars: true  # reads KAST_ZAP_URL and KAST_ZAP_API_KEY

local:
  docker_image: "ghcr.io/zaproxy/zaproxy:stable"
  auto_start: true
  api_port: 8080
  api_key: "kast-local"
  container_name: "kast-zap-local"
  cleanup_on_completion: false  # keep container for reuse between scans

remote:
  api_url: "${KAST_ZAP_URL}"      # env var expanded at runtime
  api_key: "${KAST_ZAP_API_KEY}"  # omit or set "" for keyless ZAP
  timeout_seconds: 30
  verify_ssl: true

zap_config:
  automation_plan: "kast/config/zap_automation_plan.yaml"
  report_name: "zap_report.json"
  timeout_minutes: 60
  poll_interval_seconds: 30
```

### Environment variables

| Variable | Effect |
|----------|--------|
| `KAST_ZAP_URL` | Sets `remote.api_url`; also triggers auto-mode to select remote |
| `KAST_ZAP_API_KEY` | Sets `remote.api_key` |

### CLI overrides

```bash
# Use the quick profile for this scan only
kast scan -t https://example.com \
  --set zap.zap_config.automation_plan=kast/config/zap_automation_quick.yaml

# Force remote mode with a one-time URL
kast scan -t https://example.com \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://192.168.1.50:8080 \
  --set zap.remote.api_key=mysecret

# Increase timeout for a slow target
kast scan -t https://example.com \
  --set zap.zap_config.timeout_minutes=120
```

---

## kast-web integration (remote mode)

When kast-web provisions a cloud ZAP instance, it passes the resulting URL and API key to the kast CLI via `--set` overrides:

```bash
# kast-web's execute_scan_task calls kast like this:
kast scan \
  --target https://prospect.example.com \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://10.0.1.42:8080 \
  --set zap.remote.api_key=ephemeral-key-abc123
```

kast does not know or care that the ZAP instance is cloud-hosted — from its perspective this is identical to any other remote mode scan. kast-web owns the Terraform provisioning lifecycle before the scan starts and the teardown after `kast_info.json` signals completion.

---

## Writing a custom automation plan

Any YAML file following the ZAP Automation Framework schema can be used. The minimum viable plan:

```yaml
env:
  contexts:
    - name: "my-context"
      urls:
        - "${TARGET_URL}"        # kast substitutes the real URL at runtime
      includePaths:
        - "${TARGET_URL}.*"
  parameters:
    failOnError: true
    progressToStdout: true

jobs:
  - type: "spiderClient"
    parameters:
      maxDuration: 5
      maxDepth: 3
      threadCount: 2

  - type: "passiveScan-config"
    parameters:
      scanOnlyInScope: true

  - type: "passiveScan-wait"
    parameters:
      maxDuration: 5

  - type: "activeScan"
    parameters:
      maxScanDurationInMins: 20
      threadPerHost: 2

  - type: "report"
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"     # must be /zap/reports in local mode (mounted volume)
      reportFile: "zap_report.json" # must match zap_config.report_name
```

**Key constraints:**
- `${TARGET_URL}` is the only template variable — kast performs a string substitution before uploading the plan.
- `reportDir` must be `/zap/reports` in local mode; in remote mode ZAP writes to its own filesystem and kast downloads the report via the JSON API.
- `reportFile` must match `zap_config.report_name` (default: `zap_report.json`).
- ZAP must be started with `-config api.filexfer=true` for the file-upload API to work. The local provider's `_start_zap_container()` includes this flag automatically.

To use a custom plan:
```bash
kast scan -t https://example.com \
  --set zap.zap_config.automation_plan=/path/to/my_plan.yaml
```

---

## Troubleshooting

### "Docker not available"
Docker is not installed or the daemon is not running. Install Docker or switch to remote mode.

### ZAP container starts but scan never begins
The container may not be ready within the 120-second wait window. Check container logs:
```bash
docker logs kast-zap-local
```
ZAP prints `ZAP is now listening` when the API is ready.

### "Failed to upload automation plan file"
ZAP was not started with `api.filexfer=true`. If using remote mode with a manually-started ZAP instance, restart it with:
```bash
zap.sh -daemon -port 8080 -config api.key=yourkey -config api.filexfer=true
```

### "ZAP connectivity test failed"
In remote mode, kast cannot reach the ZAP API. Test manually:
```bash
curl http://your-zap-host:8080/JSON/core/view/version/
```
Common causes: firewall blocking port 8080, ZAP not started, wrong `api_url`.

### "No running ZAP container found and auto_start disabled"
Either start ZAP manually, set `local.auto_start: true`, or provide a remote URL via `KAST_ZAP_URL`.

### Scan times out before completing
Increase the timeout:
```bash
kast scan -t https://example.com --set zap.zap_config.timeout_minutes=120
```
Or switch to the `quick` profile for a faster run.

### ZAP finds no issues / very few issues
The Ajax spider (`spiderClient`) requires a browser. If the local Docker container cannot launch a headless browser, fall back to the traditional `spider` job type (as used in the quick profile). Check the ZAP container logs for `Failed to start browser`.

### Port conflict on localhost:8080
Another process is using port 8080. Change the local ZAP port:
```bash
kast scan -t https://example.com \
  --set zap.local.api_port=8090
```
