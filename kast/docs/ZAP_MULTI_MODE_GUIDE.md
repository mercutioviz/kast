# OWASP ZAP Multi-Mode Plugin Guide

## Overview

The KAST ZAP plugin now supports three execution modes, making it significantly more versatile and efficient:

1. **Local Mode**: Uses local Docker ZAP container (fastest, zero cost)
2. **Remote Mode**: Connects to existing ZAP instance (flexible, shared resources)
3. **Cloud Mode**: Provisions ephemeral cloud infrastructure (isolated, production-ready)

The plugin intelligently selects the best available mode or can be configured explicitly.

## Architecture

```
┌─────────────────────────────────────────────┐
│          ZAP Plugin (Entry Point)           │
│  - Load config                              │
│  - Determine execution mode                 │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│      ZapProviderFactory (Auto-Discovery)    │
│  1. Check env vars (KAST_ZAP_URL)          │
│  2. Check local Docker availability         │
│  3. Fall back to cloud                      │
└──────────────────┬──────────────────────────┘
                   ↓
      ┌────────────┴────────────┐
      ↓            ↓             ↓
┌──────────┐ ┌──────────┐ ┌──────────┐
│  Local   │ │  Remote  │ │  Cloud   │
│ Provider │ │ Provider │ │ Provider │
└──────────┘ └──────────┘ └──────────┘
      ↓            ↓             ↓
┌─────────────────────────────────────────────┐
│         ZAP API Client (Common)             │
│  - Monitor scan progress                    │
│  - Download results                         │
│  - Generate reports                         │
└─────────────────────────────────────────────┘
```

## Quick Start

### 1. Local Mode (Recommended for Development)

**Prerequisites**: Docker installed

**Usage**:
```bash
# Auto mode will detect Docker and use local mode
python kast/main.py --target https://example.com --run-only zap --debug

# Or explicitly specify local mode in config
# Set execution_mode: local in zap_config.yaml
```

**Behavior**:
- Checks for running ZAP container
- Starts new container if needed (configurable)
- Keeps container running for reuse (faster subsequent scans)
- Uses mounted volumes for config/reports

**Advantages**:
- ✅ Fastest scan initiation (~30 seconds)
- ✅ Zero cost
- ✅ Container reuse across scans
- ✅ Good for development/testing

### 2. Remote Mode (Shared Infrastructure)

**Prerequisites**: ZAP instance URL and API key

**Setup**:
```bash
# Set environment variables
export KAST_ZAP_URL="http://zap.example.com:8080"
export KAST_ZAP_API_KEY="your-api-key"

# Run scan
python kast/main.py --target https://example.com --run-only zap --debug
```

**Behavior**:
- Connects to existing ZAP instance
- **Uses automation framework with YAML config** (default)
- No provisioning/cleanup needed

**Advantages**:
- ✅ Fast scan initiation (~10 seconds)
- ✅ Share ZAP instance across team
- ✅ Centralized management
- ✅ Good for CI/CD pipelines
- ✅ Consistent scanning via automation framework

### 3. Cloud Mode (Production Scans)

**Prerequisites**: Terraform, cloud credentials (AWS/Azure/GCP)

**Setup**:
```bash
# Configure cloud provider in zap_config.yaml
# execution_mode: cloud

# Set cloud credentials
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"

# Run scan
python kast/main.py --target https://example.com --run-only zap --debug
```

**Behavior**:
- Provisions ephemeral infrastructure
- Deploys ZAP container
- Runs scan
- Tears down infrastructure

**Advantages**:
- ✅ Complete isolation
- ✅ Production-grade scanning
- ✅ No local dependencies
- ✅ Cost-optimized (spot instances)

## Automation Framework (All Modes)

### Overview

**All ZAP plugin modes now default to using the ZAP Automation Framework**, which provides:

- ✅ **Consistent scan configuration** via YAML
- ✅ **Repeatable results** across environments
- ✅ **Advanced scan customization** without code changes
- ✅ **Industry best practices** built-in

### Predefined Test Plan Profiles

KAST provides **5 predefined test plans** optimized for different scenarios:

| Profile | Duration | Spider Depth | Active Scan | Use Case |
|---------|----------|--------------|-------------|----------|
| **quick** | ~20 min | 3 (shallow) | 15 min | CI/CD pipelines, quick checks |
| **standard** | ~45 min | 5 (medium) | 30 min | Regular development testing (default) |
| **thorough** | ~90 min | 10 (deep) | 60 min | Pre-production, major releases |
| **api** | ~30 min | 2 (minimal) | 25 min | REST APIs, microservices |
| **passive** | ~15 min | 5 (medium) | None | Production monitoring (safe) |

#### Profile Details

**Quick Profile** (`zap_automation_quick.yaml`)
- **Best for**: CI/CD pipelines, rapid feedback
- **Spider**: 5 minutes, depth 3
- **Active Scan**: 15 minutes
- **Trade-offs**: May miss deeper vulnerabilities, faster feedback

**Standard Profile** (`zap_automation_standard.yaml`) - DEFAULT
- **Best for**: Regular development security testing
- **Spider**: 10 minutes, depth 5
- **Active Scan**: 30 minutes
- **Trade-offs**: Balanced coverage and speed

**Thorough Profile** (`zap_automation_thorough.yaml`)
- **Best for**: Pre-production assessments, major releases
- **Spider**: 20 minutes, depth 10, 4 threads
- **Active Scan**: 60 minutes, 4 threads per host
- **Trade-offs**: Comprehensive but time-consuming

**API Profile** (`zap_automation_api.yaml`)
- **Best for**: REST APIs, microservices, headless apps
- **Spider**: 3 minutes, depth 2 (APIs are flat)
- **Active Scan**: 25 minutes, API-focused checks
- **Special**: Optimized for JSON/REST patterns, no HTML form processing

**Passive Profile** (`zap_automation_passive.yaml`)
- **Best for**: Production monitoring, safe scanning
- **Spider**: 10 minutes, depth 5, single thread
- **Active Scan**: **NONE** (passive only)
- **Safety**: No injection attacks, safe for production

### Using Test Plan Profiles

**Option 1: CLI Shortcut** (Easiest)
```bash
# Quick scan (CI/CD)
python kast/main.py --target https://example.com --run-only zap --zap-profile quick

# Standard scan (default)
python kast/main.py --target https://example.com --run-only zap --zap-profile standard

# Thorough scan (pre-prod)
python kast/main.py --target https://example.com --run-only zap --zap-profile thorough

# API scan
python kast/main.py --target https://api.example.com --run-only zap --zap-profile api

# Passive scan (production)
python kast/main.py --target https://prod.example.com --run-only zap --zap-profile passive
```

**Option 2: Direct Path Override**
```bash
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=kast/config/zap_automation_quick.yaml
```

**Option 3: Config File**
```yaml
# In kast_config.yaml or ~/.config/kast/config.yaml
plugins:
  zap:
    zap_config:
      automation_plan: "kast/config/zap_automation_thorough.yaml"
```

**Option 4: Environment-Based Selection**
```yaml
# In zap_config.yaml
zap_config:
  automation_plan: "kast/config/zap_automation_${SCAN_PROFILE}.yaml"
```
Then: `export SCAN_PROFILE=quick`

### Automation Plan Location

Default: `kast/config/zap_automation_plan.yaml` (symlink to `zap_automation_standard.yaml`)

Available profiles:
- `kast/config/zap_automation_quick.yaml`
- `kast/config/zap_automation_standard.yaml` (default)
- `kast/config/zap_automation_thorough.yaml`
- `kast/config/zap_automation_api.yaml`
- `kast/config/zap_automation_passive.yaml`

Each YAML file defines:
- Spider scan parameters (depth, duration, etc.)
- Passive scan configuration
- Active scan settings (if applicable)
- Report generation templates

### Automation Framework per Mode

| Mode | Uses Automation Framework | Config Option |
|------|--------------------------|---------------|
| **Local** | ✅ Yes (default) | `local.use_automation_framework: true` |
| **Remote** | ✅ Yes (default) | `remote.use_automation_framework: true` |
| **Cloud** | ✅ Yes (default) | `cloud.use_automation_framework: true` |

### Disabling Automation Framework

If you need to use direct API calls instead (legacy behavior):

```bash
# Via CLI override
python kast/main.py --target https://example.com --run-only zap \
  --config zap.remote.use_automation_framework=false

# Or edit zap_config.yaml
remote:
  use_automation_framework: false
```

**Note**: If automation framework is enabled but the plan is invalid or missing, the scan will fail (not fall back to API).

### Using Custom Automation Plans

If you've created your own ZAP automation plan YAML file, you can use it with any of the three execution modes (local, remote, or cloud).

#### Quick Answer: The `--set` Syntax

```bash
# Use your custom automation plan
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=/path/to/your/custom_plan.yaml
```

**Key Points**:
- ✅ Works with **absolute paths**: `/home/user/my_plans/custom.yaml`
- ✅ Works with **relative paths**: `./my_custom_plan.yaml` or `../plans/custom.yaml`
- ✅ Path is relative to **current working directory** when running KAST
- ✅ Works in **all modes**: local, remote, and cloud

#### Method 1: CLI Override (Recommended for Ad-Hoc Scans)

```bash
# Absolute path
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=/home/user/zap_plans/my_custom_scan.yaml

# Relative path (from current directory)
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=./my_custom_scan.yaml

# With debug output to verify it's being used
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=/path/to/custom.yaml --debug
```

#### Method 2: Config File (Recommended for Permanent Setup)

Edit your configuration file (any of these locations work):

**Option A: Project-specific config** (`./kast_config.yaml`)
```yaml
plugins:
  zap:
    zap_config:
      automation_plan: "/absolute/path/to/custom_plan.yaml"
      # Or relative: "./custom_plans/my_plan.yaml"
```

**Option B: User config** (`~/.config/kast/config.yaml`)
```yaml
plugins:
  zap:
    zap_config:
      automation_plan: "~/zap_plans/custom_plan.yaml"
```

**Option C: Installation config** (`kast/config/zap_config.yaml`)
```yaml
zap_config:
  automation_plan: "kast/config/my_custom_plan.yaml"
```

#### Method 3: Environment-Based Plans

```yaml
# In zap_config.yaml
zap_config:
  automation_plan: "kast/config/zap_automation_${SCAN_PROFILE}.yaml"
```

Then switch profiles:
```bash
export SCAN_PROFILE=my_custom_profile
python kast/main.py --target https://example.com --run-only zap
```

#### Verifying Your Custom Plan is Used

Run with `--debug` to see which plan is loaded:

```bash
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=./my_plan.yaml --debug
```

**Look for these log messages**:
```
[DEBUG] [zap]: Automation plan: ./my_plan.yaml
[DEBUG] [zap]: Validating automation plan...
[DEBUG] [zap]: Automation plan validation successful
[DEBUG] [zap]: Uploading automation plan to ZAP...
```

#### Custom Plan Validation

The plugin automatically validates your custom automation plan:

**✅ Valid Plan Structure**:
```yaml
env:
  contexts:
    - name: "My Custom Scan"
      urls:
        - "${TARGET_URL}"
      includePaths:
        - ".*"

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
  
  - type: report
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

**❌ Common Validation Errors**:

1. **Missing required sections**:
```
Error: Automation plan missing required 'env' section
Error: Automation plan missing required 'jobs' section
```

2. **Invalid YAML syntax**:
```
Error: Failed to parse automation plan: invalid YAML at line 15
```

3. **Missing job type**:
```
Error: Job at index 2 missing required 'type' field
```

4. **File not found**:
```
Error: Automation plan file not found: /path/to/custom.yaml
```

#### Troubleshooting Custom Plans

**Problem**: Plan file not found
```bash
# Solution: Verify path and check from KAST directory
ls -la /path/to/your/custom_plan.yaml

# For relative paths, run from correct directory
pwd  # Should show your project root
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=./custom_plan.yaml
```

**Problem**: Scan runs but ignores custom plan
```bash
# Solution: Verify automation framework is enabled
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=./custom.yaml \
  --set zap.remote.use_automation_framework=true \
  --debug
```

**Problem**: YAML validation fails
```bash
# Solution: Validate YAML syntax separately
python -c "import yaml; yaml.safe_load(open('custom_plan.yaml'))"

# Or use online YAML validator
# https://www.yamllint.com/
```

#### Creating Your First Custom Plan

Start with one of the predefined templates:

```bash
# Copy a template to customize
cp kast/config/zap_automation_standard.yaml ./my_custom_scan.yaml

# Edit the copy
nano ./my_custom_scan.yaml

# Test it
python kast/main.py --target https://example.com --run-only zap \
  --set zap.zap_config.automation_plan=./my_custom_scan.yaml --debug
```

**Common Customizations**:

1. **Longer scan duration**:
```yaml
jobs:
  - type: activeScan
    parameters:
      maxScanDurationInMins: 90  # Increase from default
```

2. **Exclude sensitive paths**:
```yaml
env:
  contexts:
    - name: "Production Safe Scan"
      excludePaths:
        - ".*logout.*"
        - ".*delete.*"
        - ".*admin.*"
```

3. **Add authentication**:
```yaml
env:
  contexts:
    - name: "Authenticated Scan"
      authentication:
        method: "form"
        parameters:
          loginUrl: "${TARGET_URL}/login"
          loginRequestData: "username={%username%}&password={%password%}"
```

4. **API-focused scanning**:
```yaml
jobs:
  - type: spider
    parameters:
      maxDuration: 5
      maxDepth: 2  # APIs are typically flat
  
  - type: activeScan
    parameters:
      policy: "API-Minimal"  # Use API-specific policy
```

### Predefined vs Custom Plans

**When to use predefined profiles** (`--zap-profile quick/standard/thorough/api/passive`):
- ✅ Standard security testing
- ✅ Quick setup, no YAML editing
- ✅ Well-tested configurations
- ✅ Good for most use cases

**When to create custom plans**:
- ✅ Specific authentication requirements
- ✅ Complex exclusion rules
- ✅ Non-standard scan durations
- ✅ Custom reporting formats
- ✅ Integration with specific workflows

### Automation Plan Validation

The plugin automatically validates automation plans before use:

- ✅ Valid YAML syntax
- ✅ Required sections present (`env`, `jobs`)
- ✅ Each job has a `type` field
- ❌ Invalid plans cause scan failure with clear error messages

### Example Automation Plan Customizations

#### Increase Scan Depth

```yaml
jobs:
  - type: "spiderClient"
    parameters:
      maxDuration: 20  # Default: 10
      maxDepth: 10     # Default: 5
```

#### Adjust Active Scan Duration

```yaml
jobs:
  - type: "activeScan"
    parameters:
      maxScanDurationInMins: 60  # Default: 30
      threadPerHost: 4            # Default: 2
```

#### Exclude URLs from Scan

```yaml
env:
  contexts:
    - name: "target-context"
      excludePaths:
        - ".*logout.*"
        - ".*signout.*"
        - ".*admin.*"  # Add custom exclusions
```

## Configuration

### Unified Configuration System

The ZAP plugin now uses the **same configuration search paths** as the main KAST config system:

**Search Order** (highest to lowest priority):
1. `./kast_config.yaml` (project-specific) - `plugins.zap` section
2. `~/.config/kast/config.yaml` (user config) - `plugins.zap` section  
3. `/etc/kast/config.yaml` (system-wide) - `plugins.zap` section
4. `kast/config/zap_config.yaml` (installation directory - backward compatibility)
5. `kast/config/zap_cloud_config.yaml` (legacy format - backward compatibility)

**Two Configuration Formats Supported:**

**Format 1: Unified Config** (Recommended - consistent with other plugins)
```yaml
# In ./kast_config.yaml, ~/.config/kast/config.yaml, or /etc/kast/config.yaml
plugins:
  zap:
    execution_mode: auto
    local:
      docker_image: "ghcr.io/zaproxy/zaproxy:stable"
      # ... other settings
```

**Format 2: Standalone Config** (Backward compatibility)
```yaml
# In kast/config/zap_config.yaml
execution_mode: auto
local:
  docker_image: "ghcr.io/zaproxy/zaproxy:stable"
  # ... other settings
```

Both formats work, with unified format taking precedence based on the search order above.

### Configuration File: `zap_config.yaml`

```yaml
# Execution mode: auto, local, remote, cloud
execution_mode: auto

# Auto-discovery settings
auto_discovery:
  prefer_local: true
  check_env_vars: true

# Local mode settings
local:
  docker_image: "ghcr.io/zaproxy/zaproxy:stable"
  auto_start: true
  api_port: 8080
  api_key: "kast-local"
  container_name: "kast-zap-local"
  cleanup_on_completion: false  # Keep running for reuse

# Remote mode settings
remote:
  api_url: "${KAST_ZAP_URL}"
  api_key: "${KAST_ZAP_API_KEY}"
  timeout_seconds: 30

# Cloud mode settings (existing)
cloud:
  cloud_provider: aws
  aws:
    region: us-east-1
    instance_type: t3.medium
```

## Auto-Discovery Logic

When `execution_mode: auto` is set, the plugin follows this priority:

1. **Check for Remote ZAP**:
   - Look for `KAST_ZAP_URL` environment variable
   - If found, use Remote mode

2. **Check for Local Docker**:
   - Verify Docker is installed
   - Look for running ZAP container
   - If available, use Local mode

3. **Fall Back to Cloud**:
   - If neither above is available, use Cloud mode
   - Requires Terraform and cloud credentials

## Comparison Table

| Feature | Local Mode | Remote Mode | Cloud Mode |
|---------|------------|-------------|------------|
| **Setup Time** | ~30s | ~10s | ~5-10min |
| **Cost** | Free | Variable | $0.02-0.07/hr |
| **Isolation** | Low | Medium | High |
| **Reusability** | High | High | Low (ephemeral) |
| **Dependencies** | Docker | Network access | Terraform, Cloud |
| **Best For** | Development | CI/CD, Shared | Production, Isolated |

## Usage Examples

### Example 1: Development Workflow (Local)

```bash
# First run - starts container
python kast/main.py --target https://dev.example.com --run-only zap --debug
# Container: kast-zap-local started

# Subsequent runs - reuses container
python kast/main.py --target https://staging.example.com --run-only zap
# Container: kast-zap-local reused (much faster!)
```

### Example 2: CI/CD Pipeline (Remote)

```yaml
# .gitlab-ci.yml or .github/workflows/security.yml
env:
  KAST_ZAP_URL: "http://zap-server.internal:8080"
  KAST_ZAP_API_KEY: $ZAP_API_KEY  # From CI secrets

script:
  - python kast/main.py --target $DEPLOY_URL --run-only zap
```

### Example 3: Production Assessment (Cloud)

```bash
# Run isolated scan in cloud
python kast/main.py \
  --target https://production.example.com \
  --run-only zap \
  --debug

# Infrastructure provisioned → Scan → Auto-cleanup
```

### Example 4: Explicit Mode Selection

```bash
# Force local mode
# Edit zap_config.yaml: execution_mode: local
python kast/main.py --target https://example.com --run-only zap

# Force remote mode with inline config
export KAST_ZAP_URL="http://localhost:8080"
# Edit zap_config.yaml: execution_mode: remote
python kast/main.py --target https://example.com --run-only zap

# Force cloud mode
# Edit zap_config.yaml: execution_mode: cloud
python kast/main.py --target https://example.com --run-only zap
```

## Environment Variables

The plugin supports the following environment variables:

- `KAST_ZAP_URL`: Remote ZAP instance URL (e.g., `http://zap.example.com:8080`)
- `KAST_ZAP_API_KEY`: API key for remote ZAP authentication
- Cloud credentials (AWS/Azure/GCP) - see cloud config section

## Troubleshooting

### Local Mode Issues

**Problem**: "Docker not available"
```bash
# Solution: Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

**Problem**: "Port 8080 already in use"
```bash
# Solution: Change port in config
# Edit zap_config.yaml: local.api_port: 8081
```

**Problem**: Container won't start
```bash
# Check Docker logs
docker logs kast-zap-local

# Remove stale container
docker rm -f kast-zap-local
```

### Remote Mode Issues

**Problem**: "Cannot connect to remote ZAP"
```bash
# Solution: Verify URL and connectivity
curl http://your-zap-url:8080/JSON/core/view/version

# Check API key
export KAST_ZAP_API_KEY="correct-key"
```

**Problem**: "Connection timeout"
```bash
# Solution: Increase timeout in config
# Edit zap_config.yaml: remote.timeout_seconds: 60
```

### Cloud Mode Issues

See existing `ZAP_CLOUD_PLUGIN_GUIDE.md` for cloud-specific troubleshooting.

## Migration Guide

### From Legacy Cloud-Only Plugin

The new plugin is backward compatible. If you have existing `zap_cloud_config.yaml`:

1. Plugin automatically detects and adapts legacy config
2. Consider migrating to new `zap_config.yaml` format:

```bash
# Copy and adapt your config
cp kast/config/zap_cloud_config.yaml kast/config/zap_config.yaml

# Update structure (see configuration section above)
```

## Best Practices

### For Development
- Use **local mode** with `cleanup_on_completion: false`
- Container stays running between scans
- Fastest iteration cycle

### For CI/CD
- Use **remote mode** with shared ZAP instance
- Set `KAST_ZAP_URL` in CI secrets
- Consistent environment across builds

### For Production
- Use **cloud mode** for isolation
- Enable spot/preemptible instances for cost savings
- Set appropriate scan timeouts

### For Testing
- Use **auto mode** to adapt to environment
- Works locally (Docker) and in CI (remote) automatically

## Performance Comparison

Based on typical scan of a medium-sized web application:

| Mode | Provisioning | Scan Time | Total Time | Cost |
|------|--------------|-----------|------------|------|
| Local | 30s | 15min | 15.5min | $0 |
| Remote | 10s | 15min | 15.2min | $0* |
| Cloud | 8min | 15min | 25min | $0.05 |

\* Cost depends on remote instance hosting

## Advanced Configuration

### Custom Local Container

```yaml
local:
  docker_image: "your-registry/custom-zap:latest"
  # Mount custom scripts
  # Add custom addons
```

### Multiple Remote Instances

```yaml
# Use different remotes based on environment
remote:
  api_url: "${ZAP_URL_${ENVIRONMENT}}"  # ZAP_URL_DEV, ZAP_URL_STAGING
```

### Hybrid Approach

```yaml
# Development: Use local
# CI: Use remote (via env var)
# Production: Force cloud
execution_mode: auto  # Adapts automatically
```

## Security Considerations

### Local Mode
- Container has access to host network
- API key should be unique per project
- Consider network isolation for sensitive scans

### Remote Mode
- Use HTTPS with valid certificates in production
- Rotate API keys regularly
- Implement IP whitelisting on ZAP instance

### Cloud Mode
- Security groups restrict access to SSH + ZAP API
- Ephemeral instances minimize attack surface
- No persistent data after teardown

## Future Enhancements

Planned improvements:
- [ ] Kubernetes provider (deploy to K8s cluster)
- [ ] Result caching (avoid re-scanning unchanged resources)
- [ ] Parallel scanning (multiple targets simultaneously)
- [ ] Smart mode selection based on target complexity
- [ ] WebSocket support for real-time progress
- [ ] Integration with ZAP marketplace addons

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review debug logs (`--debug` flag)
3. Consult ZAP documentation: https://www.zaproxy.org/docs/
4. Report KAST-specific issues using `/reportbug` command

## Summary

The multi-mode ZAP plugin provides flexibility for different scenarios:

- **Development**: Fast local scanning with Docker
- **CI/CD**: Shared remote instance for consistency  
- **Production**: Isolated cloud scanning for security

The auto-discovery mode makes it work seamlessly across environments without configuration changes.
