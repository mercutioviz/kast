# OWASP ZAP Plugin - Quick Reference Guide

## Quick Start

### Default Scan (Auto Mode)
```bash
# Auto-detects best execution mode (local → remote → cloud)
python kast/main.py --target https://example.com --run-only zap
```

### Using Built-in Profiles
```bash
# Quick scan for CI/CD (~20 min)
python kast/main.py --target https://example.com --run-only zap --zap-profile quick

# Standard scan - DEFAULT (~45 min)
python kast/main.py --target https://example.com --run-only zap --zap-profile standard

# Thorough scan for pre-production (~90 min)
python kast/main.py --target https://example.com --run-only zap --zap-profile thorough

# API-focused scan (~30 min)
python kast/main.py --target https://api.example.com --run-only zap --zap-profile api

# Passive-only scan - safe for production (~15 min)
python kast/main.py --target https://prod.example.com --run-only zap --zap-profile passive
```

### Debug Mode
```bash
python kast/main.py --target https://example.com --run-only zap --debug
```

---

## Execution Modes

### Auto Mode (Default)
Auto-discovers best available mode:
1. Checks for `KAST_ZAP_URL` env var → **Remote mode**
2. Checks for Docker availability → **Local mode**
3. Falls back to → **Cloud mode**

### Local Mode
Uses Docker ZAP container on your machine.

```bash
# Force local mode
python kast/main.py --target https://example.com --run-only zap \
  --set zap.execution_mode=local
```

### Remote Mode
Connects to existing ZAP instance.

```bash
# Via environment variables (recommended)
export KAST_ZAP_URL="http://zap-server:8080"
export KAST_ZAP_API_KEY="your-api-key"
python kast/main.py --target https://example.com --run-only zap

# Via CLI
python kast/main.py --target https://example.com --run-only zap \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://zap-server:8080 \
  --set zap.remote.api_key=your-api-key
```

### Cloud Mode
Provisions ephemeral cloud infrastructure (AWS/Azure/GCP).

```bash
# Force cloud mode
python kast/main.py --target https://example.com --run-only zap \
  --set zap.execution_mode=cloud
```

---

## Built-in ZAP Profiles

| Profile | Duration | Spider Depth | Active Scan | Use Case |
|---------|----------|--------------|-------------|----------|
| **quick** | ~20 min | 3 (shallow) | 15 min | CI/CD pipelines |
| **standard** | ~45 min | 5 (medium) | 30 min | Regular testing (DEFAULT) |
| **thorough** | ~90 min | 10 (deep) | 60 min | Pre-production |
| **api** | ~30 min | 2 (minimal) | 25 min | REST APIs |
| **passive** | ~15 min | 5 (medium) | None | Production (safe) |

### Profile Usage

**Method 1: CLI Shortcut** (Easiest)
```bash
python kast/main.py --target https://example.com --run-only zap --zap-profile quick
python kast/main.py --target https://example.com --run-only zap --zap-profile standard
python kast/main.py --target https://example.com --run-only zap --zap-profile thorough
python kast/main.py --target https://example.com --run-only zap --zap-profile api
python kast/main.py --target https://example.com --run-only zap --zap-profile passive
```

**Method 2: Direct Path Override**
```bash
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=kast/config/zap_automation_quick.yaml
```

**Method 3: Config File**
```yaml
# In kast_config.yaml or ~/.config/kast/config.yaml
plugins:
  zap:
    zap_config:
      automation_plan: "kast/config/zap_automation_thorough.yaml"
```

---

## Specifying ZAP URL and API Key

### Environment Variables (Recommended for Remote Mode)

```bash
# Set ZAP connection details
export KAST_ZAP_URL="http://zap-server.example.com:8080"
export KAST_ZAP_API_KEY="your-secret-api-key"

# Run scan (auto-detects remote mode)
python kast/main.py --target https://example.com --run-only zap
```

### Via --set Arguments

```bash
# Specify URL and API key via CLI
python kast/main.py --target https://example.com --run-only zap \
  --set zap.remote.api_url=http://zap-server:8080 \
  --set zap.remote.api_key=your-api-key
```

### Via Config File

**Option A: Project Config** (`./kast_config.yaml`)
```yaml
plugins:
  zap:
    execution_mode: remote
    remote:
      api_url: "http://zap-server.example.com:8080"
      api_key: "your-api-key"
```

**Option B: Environment Variables in Config**
```yaml
plugins:
  zap:
    execution_mode: remote
    remote:
      api_url: "${KAST_ZAP_URL}"
      api_key: "${KAST_ZAP_API_KEY}"
```

**Option C: Installation Config** (`kast/config/zap_config.yaml`)
```yaml
execution_mode: remote

remote:
  api_url: "${KAST_ZAP_URL}"
  api_key: "${KAST_ZAP_API_KEY}"
  timeout_seconds: 30
```

### Verification

```bash
# Test ZAP connectivity
curl http://your-zap-server:8080/JSON/core/view/version/

# Run with debug to see which mode is used
python kast/main.py --target https://example.com --run-only zap --debug
```

---

## ZAP Configuration Overrides (--set)

### Syntax
```bash
--set zap.<section>.<parameter>=<value>
```

### Execution Mode
```bash
# Switch execution mode
--set zap.execution_mode=local
--set zap.execution_mode=remote
--set zap.execution_mode=cloud
--set zap.execution_mode=auto
```

### Local Mode Options
```bash
# Docker configuration
--set zap.local.docker_image=ghcr.io/zaproxy/zaproxy:stable
--set zap.local.api_port=8080
--set zap.local.api_key=custom-key
--set zap.local.container_name=my-zap-container

# Container behavior
--set zap.local.auto_start=true
--set zap.local.cleanup_on_completion=false

# Automation framework
--set zap.local.use_automation_framework=true
```

### Remote Mode Options
```bash
# Connection settings
--set zap.remote.api_url=http://zap-server:8080
--set zap.remote.api_key=your-api-key
--set zap.remote.timeout_seconds=60
--set zap.remote.verify_ssl=true

# Automation framework
--set zap.remote.use_automation_framework=true
```

### Cloud Mode Options
```bash
# Cloud provider selection
--set zap.cloud.cloud_provider=aws
--set zap.cloud.cloud_provider=azure
--set zap.cloud.cloud_provider=gcp

# Automation framework
--set zap.cloud.use_automation_framework=true
```

### Common ZAP Settings
```bash
# Scan behavior
--set zap.zap_config.timeout_minutes=120
--set zap.zap_config.poll_interval_seconds=30

# Report configuration
--set zap.zap_config.report_name=custom_report.json

# Automation plan (custom YAML file)
--set zap.zap_config.automation_plan=/path/to/custom_plan.yaml
--set zap.zap_config.automation_plan=./my_custom_plan.yaml
--set zap.zap_config.automation_plan=~/zap_plans/custom.yaml
```

### Multiple Overrides
```bash
# Combine multiple --set arguments
python kast/main.py --target https://example.com --run-only zap \
  --set zap.execution_mode=local \
  --set zap.local.api_port=9090 \
  --set zap.local.cleanup_on_completion=true \
  --set zap.zap_config.timeout_minutes=120
```

---

## Specifying Configuration Files

### ZAP Config YAML File

**Config Search Order** (highest to lowest priority):
1. `./kast_config.yaml` (project directory) → `plugins.zap` section
2. `~/.config/kast/config.yaml` (user config) → `plugins.zap` section
3. `/etc/kast/config.yaml` (system-wide) → `plugins.zap` section
4. `kast/config/zap_config.yaml` (installation directory)
5. `kast/config/zap_cloud_config.yaml` (legacy format)

**Format 1: Unified Config** (Recommended)
```yaml
# File: ./kast_config.yaml or ~/.config/kast/config.yaml
plugins:
  zap:
    execution_mode: auto
    local:
      docker_image: "ghcr.io/zaproxy/zaproxy:stable"
      auto_start: true
    remote:
      api_url: "${KAST_ZAP_URL}"
      api_key: "${KAST_ZAP_API_KEY}"
    zap_config:
      automation_plan: "kast/config/zap_automation_standard.yaml"
```

**Format 2: Standalone Config** (Backward compatibility)
```yaml
# File: kast/config/zap_config.yaml
execution_mode: auto

local:
  docker_image: "ghcr.io/zaproxy/zaproxy:stable"
  auto_start: true

remote:
  api_url: "${KAST_ZAP_URL}"
  api_key: "${KAST_ZAP_API_KEY}"

zap_config:
  automation_plan: "kast/config/zap_automation_standard.yaml"
```

### ZAP Automation Plan File

**Default Location:**
```
kast/config/zap_automation_plan.yaml
```
(Symlink to `zap_automation_standard.yaml`)

**Available Built-in Plans:**
- `kast/config/zap_automation_quick.yaml`
- `kast/config/zap_automation_standard.yaml` (default)
- `kast/config/zap_automation_thorough.yaml`
- `kast/config/zap_automation_api.yaml`
- `kast/config/zap_automation_passive.yaml`

**Specifying Custom Automation Plan:**

**Method 1: CLI Override**
```bash
# Absolute path
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=/home/user/custom_plan.yaml

# Relative path (from current directory)
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=./my_custom_plan.yaml

# Home directory
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=~/zap_plans/custom.yaml
```

**Method 2: Config File**
```yaml
plugins:
  zap:
    zap_config:
      automation_plan: "/absolute/path/to/custom_plan.yaml"
      # Or: "./relative/path/custom_plan.yaml"
      # Or: "~/path/custom_plan.yaml"
```

**Method 3: Environment-Based Selection**
```yaml
# In config file
plugins:
  zap:
    zap_config:
      automation_plan: "kast/config/zap_automation_${SCAN_PROFILE}.yaml"
```

```bash
# Then set environment variable
export SCAN_PROFILE=quick
python kast/main.py --target https://example.com --run-only zap
```

**Custom Automation Plan Structure:**
```yaml
# File: my_custom_plan.yaml
env:
  contexts:
    - name: "My Custom Scan"
      urls:
        - "${TARGET_URL}"
      includePaths:
        - ".*"
      excludePaths:
        - ".*logout.*"
        - ".*admin.*"

jobs:
  - type: spider
    parameters:
      maxDuration: 15
      maxDepth: 8
  
  - type: passiveScan-wait
    parameters:
      maxDuration: 5
  
  - type: activeScan
    parameters:
      maxScanDurationInMins: 45
      threadPerHost: 3
  
  - type: report
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

---

## Common Usage Patterns

### Development Workflow (Local Mode)
```bash
# First run - starts Docker container
python kast/main.py --target https://dev.example.com --run-only zap \
  --set zap.execution_mode=local \
  --set zap.local.cleanup_on_completion=false

# Subsequent runs - reuses container (much faster!)
python kast/main.py --target https://staging.example.com --run-only zap
```

### CI/CD Pipeline (Remote Mode)
```bash
# In .gitlab-ci.yml or .github/workflows/security.yml
export KAST_ZAP_URL="http://zap-server.internal:8080"
export KAST_ZAP_API_KEY="${ZAP_API_KEY}"  # From CI secrets

# Quick scan for fast feedback
python kast/main.py --target $DEPLOY_URL --run-only zap --zap-profile quick
```

### Production Assessment (Cloud Mode)
```bash
# Provisions isolated cloud infrastructure
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"

python kast/main.py --target https://production.example.com --run-only zap \
  --set zap.execution_mode=cloud \
  --zap-profile passive  # Safe for production
```

### Authenticated Scanning
```yaml
# Create custom_auth_plan.yaml
env:
  contexts:
    - name: "Authenticated Scan"
      urls:
        - "${TARGET_URL}"
      authentication:
        method: "form"
        parameters:
          loginUrl: "${TARGET_URL}/login"
          loginRequestData: "username={%username%}&password={%password%}"
      users:
        - name: "test_user"
          credentials:
            username: "testuser"
            password: "testpass"

jobs:
  - type: spider
    parameters:
      user: "test_user"
      maxDuration: 15
  # ... rest of jobs
```

```bash
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=./custom_auth_plan.yaml
```

### API-Focused Scanning
```bash
# Use built-in API profile
python kast/main.py --target https://api.example.com --run-only zap --zap-profile api

# Or create custom API plan
python kast/main.py --target https://api.example.com --run-only zap \
  --set zap.zap_config.automation_plan=./api_custom_plan.yaml
```

### Multi-Target Scanning
```bash
# Scan multiple targets sequentially
for target in dev.example.com staging.example.com; do
  python kast/main.py --target https://$target --run-only zap --zap-profile quick
done
```

### Long-Running Comprehensive Scan
```bash
# Thorough scan with extended timeout
python kast/main.py --target https://example.com --run-only zap \
  --zap-profile thorough \
  --set zap.zap_config.timeout_minutes=180
```

---

## Quick Troubleshooting

### Issue: Wrong Execution Mode Detected

**Symptom:** Logs show cloud mode when you wanted remote mode
```
[DEBUG] [zap]: Using cloud provider: aws
[DEBUG] [zap]: Provisioning cloud infrastructure...
```

**Solution:**
```bash
# Explicitly set remote mode and URL
export KAST_ZAP_URL="http://your-zap:8080"
python kast/main.py --target https://example.com --run-only zap --debug

# OR force via CLI
python kast/main.py --target https://example.com --run-only zap \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://your-zap:8080
```

### Issue: Cannot Connect to Remote ZAP

**Symptom:** Connection refused or timeout
```
Error: Cannot connect to http://zap-server:8080
```

**Solutions:**
```bash
# Test connectivity manually
curl http://zap-server:8080/JSON/core/view/version/

# Check ZAP is listening on correct interface
# ZAP must listen on 0.0.0.0, not 127.0.0.1

# Verify firewall/network rules
ping zap-server
telnet zap-server 8080

# Increase timeout
python kast/main.py --target https://example.com --run-only zap \
  --set zap.remote.timeout_seconds=60
```

### Issue: Custom Automation Plan Not Found

**Symptom:** File not found error
```
Error: Automation plan file not found: /path/to/custom.yaml
```

**Solutions:**
```bash
# Verify file exists
ls -la /path/to/custom_plan.yaml

# Check current directory for relative paths
pwd
ls -la ./custom_plan.yaml

# Use absolute path instead
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=$(pwd)/custom_plan.yaml
```

### Issue: Custom Plan Validation Fails

**Symptom:** Invalid YAML structure
```
Error: Automation plan missing required 'env' section
```

**Solutions:**
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('custom_plan.yaml'))"

# Check for required sections
# Your plan MUST have:
# - env section with at least one context
# - jobs section with at least one job
# - Each job must have a 'type' field

# Start with a template
cp kast/config/zap_automation_standard.yaml ./my_custom_plan.yaml
nano ./my_custom_plan.yaml
```

### Issue: Docker Container Won't Start (Local Mode)

**Symptom:** Container fails to start
```
Error: Failed to start ZAP Docker container
```

**Solutions:**
```bash
# Check Docker is running
docker ps

# Check port availability
sudo netstat -tuln | grep 8080

# Remove stale container
docker rm -f kast-zap-local

# Check Docker logs
docker logs kast-zap-local

# Try different port
python kast/main.py --target https://example.com --run-only zap \
  --set zap.local.api_port=9090
```

### Issue: Scan Timeout

**Symptom:** Scan exceeds timeout limit
```
Error: ZAP scan timeout after 60 minutes
```

**Solutions:**
```bash
# Increase timeout
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.timeout_minutes=180

# Or use a faster profile
python kast/main.py --target https://example.com --run-only zap --zap-profile quick

# Or create custom plan with shorter durations
# Edit automation plan: reduce spider/active scan durations
```

---

## Configuration Precedence

When multiple configuration sources are present, they are applied in this order (later overrides earlier):

1. **Default values** (in plugin code)
2. **Config file** (searched in order: `./kast_config.yaml` → `~/.config/kast/config.yaml` → `/etc/kast/config.yaml` → `kast/config/zap_config.yaml`)
3. **Environment variables** (`KAST_ZAP_URL`, `KAST_ZAP_API_KEY`, etc.)
4. **CLI overrides** (`--set` arguments) - **Highest priority**

### Example of Precedence

```yaml
# File: ~/.config/kast/config.yaml
plugins:
  zap:
    remote:
      api_url: "http://zap-default:8080"
      timeout_seconds: 30
```

```bash
# Environment variables override config file
export KAST_ZAP_URL="http://zap-env:8080"

# CLI overrides everything
python kast/main.py --target https://example.com --run-only zap \
  --set zap.remote.api_url=http://zap-cli:8080 \
  --set zap.remote.timeout_seconds=60

# Result: Uses http://zap-cli:8080 with 60 second timeout
```

---

## Complete Configuration Examples

### Example 1: Development Environment (Local Mode)

```yaml
# File: ./kast_config.yaml
plugins:
  zap:
    execution_mode: local
    
    local:
      docker_image: "ghcr.io/zaproxy/zaproxy:stable"
      api_port: 8080
      api_key: "dev-local-key"
      container_name: "kast-zap-dev"
      auto_start: true
      cleanup_on_completion: false  # Keep running for reuse
      use_automation_framework: true
    
    zap_config:
      automation_plan: "kast/config/zap_automation_quick.yaml"  # Fast scans for dev
      timeout_minutes: 60
      poll_interval_seconds: 15
```

**Usage:**
```bash
python kast/main.py --target https://dev.example.com --run-only zap
```

### Example 2: CI/CD Pipeline (Remote Mode)

```yaml
# File: ~/.config/kast/config.yaml (on CI/CD runner)
plugins:
  zap:
    execution_mode: remote
    
    remote:
      api_url: "${KAST_ZAP_URL}"  # Set in CI secrets
      api_key: "${KAST_ZAP_API_KEY}"  # Set in CI secrets
      timeout_seconds: 60
      verify_ssl: true
      use_automation_framework: true
    
    zap_config:
      automation_plan: "kast/config/zap_automation_quick.yaml"  # Fast for CI
      timeout_minutes: 45
      poll_interval_seconds: 30
```

**GitLab CI:**
```yaml
# .gitlab-ci.yml
security_scan:
  stage: security
  variables:
    KAST_ZAP_URL: "http://zap-server.internal:8080"
    KAST_ZAP_API_KEY: $ZAP_API_KEY  # From CI/CD secrets
  script:
    - python kast/main.py --target $DEPLOY_URL --run-only zap
```

**GitHub Actions:**
```yaml
# .github/workflows/security.yml
- name: Security Scan
  env:
    KAST_ZAP_URL: http://zap-server:8080
    KAST_ZAP_API_KEY: ${{ secrets.ZAP_API_KEY }}
  run: |
    python kast/main.py --target ${{ secrets.TARGET_URL }} --run-only zap
```

### Example 3: Production Assessment (Cloud Mode)

```yaml
# File: ./prod_scan_config.yaml
plugins:
  zap:
    execution_mode: cloud
    
    cloud:
      cloud_provider: aws
      use_automation_framework: true
    
    zap_config:
      automation_plan: "kast/config/zap_automation_passive.yaml"  # Safe for prod
      timeout_minutes: 120
      poll_interval_seconds: 60
```

**Usage:**
```bash
# Set AWS credentials
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"

# Run scan with custom config
python kast/main.py --target https://production.example.com --run-only zap \
  --config ./prod_scan_config.yaml
```

### Example 4: Multi-Environment Setup

```yaml
# File: ~/.config/kast/config.yaml
plugins:
  zap:
    execution_mode: "${ZAP_MODE:-auto}"  # Environment-specific
    
    local:
      docker_image: "ghcr.io/zaproxy/zaproxy:stable"
      cleanup_on_completion: false
    
    remote:
      api_url: "${KAST_ZAP_URL}"
      api_key: "${KAST_ZAP_API_KEY}"
    
    zap_config:
      automation_plan: "kast/config/zap_automation_${SCAN_PROFILE:-standard}.yaml"
      timeout_minutes: "${ZAP_TIMEOUT:-60}"
```

**Usage:**
```bash
# Development (local)
export ZAP_MODE=local
export SCAN_PROFILE=quick
python kast/main.py --target https://dev.example.com --run-only zap

# CI/CD (remote)
export ZAP_MODE=remote
export KAST_ZAP_URL="http://zap-ci:8080"
export SCAN_PROFILE=quick
python kast/main.py --target https://staging.example.com --run-only zap

# Production (remote, passive only)
export ZAP_MODE=remote
export KAST_ZAP_URL="http://zap-prod:8080"
export SCAN_PROFILE=passive
export ZAP_TIMEOUT=180
python kast/main.py --target https://production.example.com --run-only zap
```

---

## Related Documentation

- **[ZAP_MULTI_MODE_GUIDE.md](ZAP_MULTI_MODE_GUIDE.md)** - Comprehensive guide to all execution modes
- **[ZAP_CLOUD_PLUGIN_GUIDE.md](ZAP_CLOUD_PLUGIN_GUIDE.md)** - Detailed cloud mode documentation
- **[ZAP_REMOTE_MODE_QUICK_START.md](ZAP_REMOTE_MODE_QUICK_START.md)** - Remote mode setup guide
- **[ZAP_CONFIG_MIGRATION.md](ZAP_CONFIG_MIGRATION.md)** - Configuration system details
- **[genai-instructions.md](../genai-instructions.md)** - Complete KAST project guide

---

## Summary Cheat Sheet

### Quick Commands
```bash
# Default scan
python kast/main.py --target https://example.com --run-only zap

# With profile
python kast/main.py --target https://example.com --run-only zap --zap-profile quick

# Remote mode
export KAST_ZAP_URL="http://zap:8080"
python kast/main.py --target https://example.com --run-only zap

# Custom plan
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=./custom.yaml

# Debug
python kast/main.py --target https://example.com --run-only zap --debug
```

### Key Environment Variables
```bash
KAST_ZAP_URL          # Remote ZAP instance URL
KAST_ZAP_API_KEY      # Remote ZAP API key
AWS_ACCESS_KEY_ID     # AWS credentials (cloud mode)
AWS_SECRET_ACCESS_KEY # AWS credentials (cloud mode)
```

### Common --set Overrides
```bash
--set zap.execution_mode=local|remote|cloud|auto
--set zap.remote.api_url=http://zap:8080
--set zap.remote.api_key=your-key
--set zap.zap_config.timeout_minutes=120
--set zap.zap_config.automation_plan=./plan.yaml
--set zap.local.cleanup_on_completion=false
```

### Built-in Profiles
- `quick` - CI/CD (20 min)
- `standard` - Default (45 min)
- `thorough` - Pre-prod (90 min)
- `api` - REST APIs (30 min)
- `passive` - Production safe (15 min)

### Config File Locations (Priority Order)
1. `./kast_config.yaml` → `plugins.zap`
2. `~/.config/kast/config.yaml` → `plugins.zap`
3. `/etc/kast/config.yaml` → `plugins.zap`
4. `kast/config/zap_config.yaml`

---

**For detailed information on any topic, consult the related documentation files listed above.**
