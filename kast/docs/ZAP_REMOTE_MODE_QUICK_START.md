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
