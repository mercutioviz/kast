# ZAP Remote Mode - Quick Start Guide

## Problem You're Experiencing

If you see logs like this:

```
[DEBUG] [zap]: Using cloud provider: aws
[DEBUG] [zap]: Provisioning cloud infrastructure...
```

When you intended to use remote mode, it means the plugin is falling back to cloud mode because remote configuration wasn't detected properly.

## Solution: Correct Remote Mode Configuration

### Method 1: Environment Variables (Recommended for CI/CD)

```bash
# Set these environment variables
export KAST_ZAP_URL="http://your-zap-instance:8080"
export KAST_ZAP_API_KEY="your-api-key"  # Optional if ZAP has no API key

# Run scan - auto mode will detect and use remote
python kast/main.py --target https://example.com --plugins zap
```

### Method 2: CLI Override

```bash
# Explicitly set execution mode and remote URL via CLI
python kast/main.py --target https://example.com --plugins zap \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://your-zap-instance:8080 \
  --set zap.remote.api_key=your-api-key
```

### Method 3: Config File (Best for Permanent Setup)

**Option A: Unified Config** (Recommended)

Create or edit `./kast_config.yaml`:

```yaml
plugins:
  zap:
    execution_mode: remote
    remote:
      api_url: "http://your-zap-instance:8080"
      api_key: "your-api-key"
      timeout_seconds: 30
      verify_ssl: true
      use_automation_framework: true  # Default, uses YAML test plans
```

**Option B: Standalone Config**

Edit `kast/config/zap_config.yaml`:

```yaml
# Change this from 'auto' or 'cloud' to 'remote'
execution_mode: remote

remote:
  api_url: "http://your-zap-instance:8080"
  api_key: "your-api-key"
  timeout_seconds: 30
  verify_ssl: true
  use_automation_framework: true
```

## Verifying Remote Mode

Run with debug logging to confirm:

```bash
python kast/main.py --target https://example.com --plugins zap --debug
```

You should see:

```
[DEBUG] [zap]: ZAP execution mode: remote
[DEBUG] [zap]: Connecting to remote ZAP instance...
[DEBUG] [zap]: Connecting to http://your-zap-instance:8080
[DEBUG] [zap]: Using remote provider for ZAP scan
```

**NOT** cloud-related messages like:
- ❌ "Using cloud provider: aws"
- ❌ "Provisioning cloud infrastructure..."
- ❌ "Generating SSH keypair..."

## Common Issues

### Issue 1: Still Using Cloud Mode

**Symptom**: Logs show "Using cloud provider" even after setting remote config

**Cause**: Config file location or CLI override path is incorrect

**Solution**: 
1. Verify your config file location matches search order
2. Use CLI override with correct path: `--set zap.execution_mode=remote`
3. Set environment variable: `export KAST_ZAP_URL="http://..."`

### Issue 2: Connection Refused

**Symptom**: "Cannot connect to http://your-zap-instance:8080"

**Solution**:
```bash
# Test ZAP connectivity manually
curl http://your-zap-instance:8080/JSON/core/view/version/

# Check firewall/network rules
# Ensure ZAP is listening on 0.0.0.0, not just 127.0.0.1
```

### Issue 3: API Key Authentication Failed

**Symptom**: "API key authentication failed"

**Solution**:
```bash
# Get ZAP API key from ZAP UI: Tools → Options → API
# Set it correctly:
export KAST_ZAP_API_KEY="the-actual-key-from-zap"
```

### Issue 4: Automation Framework Not Working

**Symptom**: Scan runs but doesn't follow your YAML test plan

**Solution**:
```yaml
# Ensure automation framework is enabled (default)
remote:
  use_automation_framework: true
```

## Configuration Search Order

KAST searches for ZAP config in this order (first match wins):

1. `./kast_config.yaml` (project directory) → `plugins.zap` section
2. `~/.config/kast/config.yaml` (user config) → `plugins.zap` section
3. `/etc/kast/config.yaml` (system-wide) → `plugins.zap` section
4. `kast/config/zap_config.yaml` (installation directory)

## Complete Remote Mode Example

```yaml
# File: ./kast_config.yaml (recommended location)

plugins:
  zap:
    # Force remote mode (skip auto-discovery)
    execution_mode: remote
    
    # Remote ZAP configuration
    remote:
      api_url: "http://zap-server.internal:8080"
      api_key: "change-me-to-your-actual-key"
      timeout_seconds: 60
      verify_ssl: true
      use_automation_framework: true  # Use YAML-based test plans
    
    # Common ZAP settings
    zap_config:
      timeout_minutes: 60
      poll_interval_seconds: 30
      report_name: "zap_report.json"
      
      # Use a specific test plan profile
      # Options: zap_automation_quick.yaml (CI/CD)
      #         zap_automation_standard.yaml (default)
      #         zap_automation_thorough.yaml (comprehensive)
      #         zap_automation_api.yaml (API testing)
      #         zap_automation_passive.yaml (production safe)
      automation_plan: "kast/config/zap_automation_standard.yaml"
```

Then run:

```bash
python kast/main.py --target https://example.com --plugins zap
```

## Test Plan Profiles for Remote Mode

You can easily switch test plans with CLI shortcut:

```bash
# Quick scan for CI/CD
python kast/main.py --target https://example.com --plugins zap --zap-profile quick

# Standard scan (default)
python kast/main.py --target https://example.com --plugins zap --zap-profile standard

# Thorough scan for pre-production
python kast/main.py --target https://example.com --plugins zap --zap-profile thorough

# API-focused scan
python kast/main.py --target https://api.example.com --plugins zap --zap-profile api

# Passive-only scan (safe for production)
python kast/main.py --target https://prod.example.com --plugins zap --zap-profile passive
```

## Using Custom Automation Plans in Remote Mode

If you've created your own ZAP automation plan YAML file, you can use it in remote mode with any of the configuration methods below.

### Quick Answer: Command Line Syntax

```bash
# Use your custom automation plan with remote ZAP instance
export KAST_ZAP_URL="http://your-zap-server:8080"

python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=/path/to/your/custom_plan.yaml
```

### Method 1: CLI Override (Best for One-Time Scans)

```bash
# Set remote ZAP instance
export KAST_ZAP_URL="http://zap.example.com:8080"
export KAST_ZAP_API_KEY="your-api-key"

# Use absolute path to custom plan
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=/home/user/my_zap_plans/custom_scan.yaml

# Or use relative path (from current directory)
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=./my_custom_scan.yaml

# With debug output to verify
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=./custom.yaml --debug
```

### Method 2: Config File (Best for Permanent Setup)

**Option A: Project Config** (`./kast_config.yaml`)
```yaml
plugins:
  zap:
    execution_mode: remote
    remote:
      api_url: "http://zap-server.internal:8080"
      api_key: "your-api-key"
      use_automation_framework: true
    
    zap_config:
      automation_plan: "/absolute/path/to/custom_plan.yaml"
      # Or relative: "./custom_plans/my_plan.yaml"
      timeout_minutes: 60
      poll_interval_seconds: 30
```

**Option B: User Config** (`~/.config/kast/config.yaml`)
```yaml
plugins:
  zap:
    execution_mode: remote
    remote:
      api_url: "${KAST_ZAP_URL}"
      api_key: "${KAST_ZAP_API_KEY}"
    
    zap_config:
      automation_plan: "~/my_zap_plans/custom_plan.yaml"
```

**Option C: Installation Config** (`kast/config/zap_config.yaml`)
```yaml
execution_mode: remote

remote:
  api_url: "http://your-zap-server:8080"
  api_key: "your-api-key"
  use_automation_framework: true

zap_config:
  automation_plan: "kast/config/my_custom_plan.yaml"
```

### Path Types Supported

**✅ Absolute Paths**:
```bash
--set zap.zap_config.automation_plan=/home/user/plans/custom.yaml
--set zap.zap_config.automation_plan=/opt/security/zap_plans/api_scan.yaml
```

**✅ Relative Paths** (from current working directory):
```bash
--set zap.zap_config.automation_plan=./my_plan.yaml
--set zap.zap_config.automation_plan=../shared_plans/custom.yaml
--set zap.zap_config.automation_plan=security/zap_custom.yaml
```

**✅ Home Directory Paths**:
```bash
--set zap.zap_config.automation_plan=~/zap_plans/custom.yaml
```

### Verifying Your Custom Plan is Used

Run with `--debug` to confirm your custom plan is loaded:

```bash
export KAST_ZAP_URL="http://your-zap:8080"
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=./my_custom.yaml --debug
```

**Look for these log messages**:
```
[DEBUG] [zap]: ZAP execution mode: remote
[DEBUG] [zap]: Connecting to remote ZAP instance...
[DEBUG] [zap]: Remote ZAP API URL: http://your-zap:8080
[DEBUG] [zap]: Automation plan: ./my_custom.yaml
[DEBUG] [zap]: Validating automation plan...
[DEBUG] [zap]: Automation plan validation successful
[DEBUG] [zap]: Uploading automation plan to remote ZAP...
[DEBUG] [zap]: Starting automation framework scan...
```

### Custom Plan Structure

Your custom automation plan should follow this structure:

```yaml
# my_custom_plan.yaml
env:
  contexts:
    - name: "My Custom Security Scan"
      urls:
        - "${TARGET_URL}"
      includePaths:
        - ".*"
      excludePaths:
        - ".*logout.*"
        - ".*signout.*"

jobs:
  # Spider the application
  - type: spider
    parameters:
      maxDuration: 15
      maxDepth: 8
      maxChildren: 20
  
  # Wait for passive scan to complete
  - type: passiveScan-wait
    parameters:
      maxDuration: 5
  
  # Run active scan
  - type: activeScan
    parameters:
      maxScanDurationInMins: 45
      threadPerHost: 3
  
  # Generate report
  - type: report
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

### Common Customizations

**1. Authenticated Scanning**:
```yaml
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
```

**2. Production-Safe Scanning** (passive only):
```yaml
jobs:
  - type: spider
    parameters:
      maxDuration: 10
      maxDepth: 5
  
  - type: passiveScan-wait
    parameters:
      maxDuration: 10
  
  # NO activeScan job = passive only, safe for production
  
  - type: report
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

**3. API-Focused Scanning**:
```yaml
jobs:
  - type: spider
    parameters:
      maxDuration: 5
      maxDepth: 2  # APIs are flat
  
  - type: activeScan
    parameters:
      policy: "API-Minimal"
      maxScanDurationInMins: 30
```

**4. Deep Comprehensive Scan**:
```yaml
jobs:
  - type: spider
    parameters:
      maxDuration: 30
      maxDepth: 15
      maxChildren: 50
      threadCount: 4
  
  - type: activeScan
    parameters:
      maxScanDurationInMins: 120
      threadPerHost: 4
      maxRuleDurationInMins: 10
```

### Troubleshooting Custom Plans

**Problem**: "Automation plan file not found"
```bash
# Solution: Verify the path
ls -la /path/to/your/custom_plan.yaml

# For relative paths, check your current directory
pwd
ls -la ./custom_plan.yaml

# Use absolute path if relative doesn't work
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=/absolute/path/to/plan.yaml
```

**Problem**: "Invalid automation plan YAML"
```bash
# Solution: Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('custom_plan.yaml'))"

# Common issues:
# - Missing colons after keys
# - Incorrect indentation (must use spaces, not tabs)
# - Missing quotes around strings with special characters
```

**Problem**: "Scan runs but doesn't use custom plan"
```bash
# Solution: Verify automation framework is enabled (default)
export KAST_ZAP_URL="http://your-zap:8080"
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=./custom.yaml \
  --set zap.remote.use_automation_framework=true \
  --debug
```

**Problem**: "Custom plan validation fails"
```bash
# Solution: Check for required sections
# Your plan MUST have:
# - env section with at least one context
# - jobs section with at least one job
# - Each job must have a 'type' field

# Example minimal valid plan:
cat > minimal_plan.yaml << 'EOF'
env:
  contexts:
    - name: "test"
      urls: ["${TARGET_URL}"]

jobs:
  - type: spider
    parameters:
      maxDuration: 5
  
  - type: report
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
EOF
```

### Creating Your First Custom Plan

**Step 1**: Start with a predefined template
```bash
# Copy a template to modify
cp kast/config/zap_automation_standard.yaml ./my_custom_plan.yaml
```

**Step 2**: Edit for your needs
```bash
nano ./my_custom_plan.yaml

# Modify:
# - Spider duration and depth
# - Active scan duration
# - Add exclusion paths
# - Add authentication if needed
```

**Step 3**: Test with debug output
```bash
export KAST_ZAP_URL="http://your-zap:8080"
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=./my_custom_plan.yaml --debug
```

**Step 4**: Monitor the scan
```bash
# Watch for:
# - "Automation plan validation successful"
# - "Uploading automation plan to remote ZAP..."
# - "Starting automation framework scan..."
# - Progress updates during scan
```

### Environment-Specific Plans

Use environment variables to switch between plans:

```yaml
# In kast_config.yaml
plugins:
  zap:
    zap_config:
      automation_plan: "./zap_plans/${ENVIRONMENT}_scan.yaml"
```

Then:
```bash
# Development scan
export ENVIRONMENT=dev
python kast/main.py --target https://dev.example.com --plugins zap

# Production scan (different plan)
export ENVIRONMENT=prod
python kast/main.py --target https://prod.example.com --plugins zap
```

### Best Practices

**✅ DO**:
- Start with a predefined template and modify it
- Use version control for your custom plans
- Test plans in development before production
- Document what each custom plan does
- Use meaningful names: `api_deep_scan.yaml`, `prod_passive.yaml`

**❌ DON'T**:
- Create overly complex plans without testing
- Use active scans on production without approval
- Forget to exclude logout/delete endpoints
- Hardcode sensitive credentials in plans

### Example: Complete Remote Mode with Custom Plan

```bash
# Set up remote ZAP
export KAST_ZAP_URL="http://zap-server.internal:8080"
export KAST_ZAP_API_KEY="your-secure-api-key"

# Create custom plan
cat > ./api_security_scan.yaml << 'EOF'
env:
  contexts:
    - name: "API Security Scan"
      urls:
        - "${TARGET_URL}"
      includePaths:
        - ".*/api/.*"
      excludePaths:
        - ".*/api/health.*"

jobs:
  - type: spider
    parameters:
      maxDuration: 5
      maxDepth: 2
  
  - type: passiveScan-wait
    parameters:
      maxDuration: 3
  
  - type: activeScan
    parameters:
      maxScanDurationInMins: 30
      policy: "API-Minimal"
  
  - type: report
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
EOF

# Run the scan
python kast/main.py --target https://api.example.com --plugins zap \
  --set zap.zap_config.automation_plan=./api_security_scan.yaml --debug
```

## Quick Debug Checklist

If remote mode isn't working:

- [ ] Is `execution_mode: remote` set in config?
- [ ] Is `remote.api_url` pointing to correct ZAP instance?
- [ ] Can you curl the ZAP API: `curl http://your-zap:8080/JSON/core/view/version/`?
- [ ] Is API key correct (if ZAP requires one)?
- [ ] Are you running from the correct directory (for relative config paths)?
- [ ] Did you check `--debug` output for actual mode being used?

## NGINX Reverse Proxy Mode (Recommended)

### Why Use NGINX?

When running ZAP in remote mode, using NGINX as a reverse proxy solves critical issues:

**The Problem**: ZAP functions as both a web proxy and an API server on the same port. Without port differentiation in the `Host` header, ZAP can confuse API requests with proxy traffic, leading to proxy loop errors and scan failures.

**The Solution**: NGINX listens on the external port (8080) and proxies to ZAP on an internal port (8081), ensuring the `Host` header always includes the port number.

```
Client → NGINX :8080 → ZAP :8081 (localhost only)
```

### Quick Setup with launch-zap.sh

The project includes a ready-to-use script that sets up ZAP with nginx proxy mode:

```bash
# Location: kast/scripts/launch-zap.sh
# This script:
# 1. Starts ZAP Docker container on 127.0.0.1:8081
# 2. Expects nginx to be installed and configured
# 3. Exposes ZAP via nginx on :8080

# Install nginx first
sudo apt-get install -y nginx

# Copy the nginx config
sudo cp kast/config/nginx/zap-proxy.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/zap-proxy /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

# Run the launch script
kast/scripts/launch-zap.sh
```

Now connect to ZAP via: `http://your-server:8080`

### Benefits

- ✅ **Prevents Proxy Loops**: ZAP sees `Host: localhost:8081`, won't try to proxy API requests
- ✅ **Better Security**: ZAP only binds to localhost, not exposed directly
- ✅ **Consistent Headers**: All requests appear from 127.0.0.1
- ✅ **Standard Pattern**: Well-established reverse proxy architecture
- ✅ **Better Performance**: NGINX handles timeouts and buffering optimally

### Configuration Reference

See `kast/config/nginx/` for:
- **zap-proxy.conf**: Ready-to-use nginx configuration
- **README.md**: Detailed explanation, troubleshooting, and architecture

### Cloud Mode Auto-Configuration

When using cloud mode, nginx is automatically installed and configured by Terraform for all providers (AWS, Azure, GCP). No manual setup needed.

## Summary

**To use remote mode, you MUST either:**

1. Set `KAST_ZAP_URL` environment variable, OR
2. Set `execution_mode: remote` + `remote.api_url` in config file, OR  
3. Use CLI override: `--set zap.execution_mode=remote --set zap.remote.api_url=http://...`

Without one of these, auto-discovery will default to local (if Docker available) or cloud (fallback).

**For Production Remote Instances**: Use nginx reverse proxy mode (see above) to prevent proxy loop issues.
