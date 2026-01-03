# ZAP Plugin: CLI Priority and Connectivity Testing Fix

## Overview

This document describes improvements made to the ZAP plugin to ensure CLI arguments always take precedence over auto-discovery and to add proper connectivity testing before scans.

## Issues Fixed

### 1. Auto-Discovery Ignoring Explicit CLI Mode

**Problem**: When users specified `--set zap.execution_mode=remote`, the plugin would still run auto-discovery and potentially select a different mode (like local if Docker was available).

**Root Cause**: The factory didn't distinguish between "auto" mode and explicitly-set modes.

**Solution**: Modified `ZapProviderFactory.create_provider()` to:
- Detect when mode is explicitly set (not "auto")
- Skip auto-discovery for explicit modes
- Log clearly: `"ZAP execution mode: remote (explicit - skipping auto-discovery)"`

### 2. No Connectivity Testing Before Remote Scans

**Problem**: Remote mode would attempt to provision without verifying the ZAP instance was accessible, leading to late failures.

**Root Cause**: No pre-scan validation of remote ZAP connectivity.

**Solution**: Added comprehensive connectivity testing:
- New `get_version()` method in `ZAPAPIClient` with detailed error reporting
- Connection test in `RemoteZapProvider.provision()` before attempting scan
- Logs ZAP version on success: `"✓ Connected to ZAP v2.14.0 at http://zap:8080"`
- Clear error messages on failure with troubleshooting tips

### 3. Missing Configuration Validation

**Problem**: When remote mode was selected but no `api_url` was configured, the plugin would fail with generic errors.

**Root Cause**: No validation of required configuration parameters.

**Solution**: Added configuration validation with helpful error messages:
```
Remote mode selected but no api_url configured
Solutions:
  1. Set environment variable: export KAST_ZAP_URL='http://your-zap:8080'
  2. Use CLI override: --set zap.remote.api_url=http://your-zap:8080
  3. Edit config file: remote.api_url in zap_config.yaml
```

## Files Modified

### 1. `kast/scripts/zap_api_client.py`

**Added**: `get_version()` method

```python
def get_version(self):
    """
    Get ZAP version information with detailed error reporting
    
    :return: Tuple of (success: bool, version: str, error_msg: str)
    """
```

**Features**:
- Returns structured tuple: `(success, version, error_message)`
- Handles specific error types:
  - Connection refused
  - Timeout
  - HTTP 401 (auth failed)
  - HTTP 403 (forbidden)
  - Other HTTP errors
- Provides actionable error messages

### 2. `kast/scripts/zap_providers.py`

**Modified**: `RemoteZapProvider.provision()`

**Changes**:
- Check for `api_url` in config, fall back to `KAST_ZAP_URL` env var
- Check for `api_key` in config, fall back to `KAST_ZAP_API_KEY` env var
- Call `get_version()` to test connectivity before proceeding
- Log ZAP version on successful connection
- Return detailed error on connection failure
- Include ZAP version in `instance_info`

**Before**:
```python
if not self.zap_client.check_connection():
    return False, None, {"error": f"Cannot connect to {api_url}"}
```

**After**:
```python
success, version, error_msg = self.zap_client.get_version()

if not success:
    self.debug(f"ERROR: Failed to connect to ZAP at {api_url}")
    self.debug(f"ERROR: {error_msg}")
    self.debug(f"Test with: curl {api_url}/JSON/core/view/version/")
    return False, None, {"error": f"ZAP connectivity test failed: {error_msg}"}

self.debug(f"✓ Connected to ZAP v{version} at {api_url}")
```

### 3. `kast/scripts/zap_provider_factory.py`

**Modified**: `create_provider()` method

**Changes**:
- Detect when mode is explicitly set vs. "auto"
- Log differently for explicit modes: `"(explicit - skipping auto-discovery)"`
- Maintain existing auto-discovery logic for "auto" mode

**Code**:
```python
execution_mode = self.config.get('execution_mode', 'auto')

# Check if mode was explicitly set (not auto)
is_explicit = execution_mode != 'auto'

if is_explicit:
    self.debug(f"ZAP execution mode: {execution_mode} (explicit - skipping auto-discovery)")
else:
    self.debug(f"ZAP execution mode: {execution_mode}")
```

### 4. `kast/docs/ZAP_REMOTE_MODE_QUICK_START.md`

**Created**: New comprehensive quick start guide for remote mode

**Contents**:
- Problem description (auto-discovery choosing wrong mode)
- Three configuration methods (env vars, CLI, config file)
- Verification steps
- Common issues and solutions
- Complete examples
- Debug checklist

## Expected Behavior After Fix

### Scenario 1: Explicit Remote Mode via CLI

**Command**:
```bash
python kast/main.py --target example.com --plugins zap \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://zap:8080
```

**Expected Logs**:
```
[DEBUG] [zap]: ZAP execution mode: remote (explicit - skipping auto-discovery)
[DEBUG] [zap]: Connecting to remote ZAP instance...
[DEBUG] [zap]: Connecting to http://zap:8080
[DEBUG] [zap]: Testing ZAP connectivity...
[DEBUG] [zap]: ✓ Connected to ZAP v2.14.0 at http://zap:8080
[DEBUG] [zap]: Using remote provider for ZAP scan
```

**NOT**:
- ❌ "Auto-discovering ZAP execution mode..."
- ❌ "Docker is available for local mode"
- ❌ "Using local mode"

### Scenario 2: Remote Mode with Bad URL

**Command**:
```bash
python kast/main.py --target example.com --plugins zap \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://wrong-host:8080
```

**Expected Logs**:
```
[DEBUG] [zap]: ZAP execution mode: remote (explicit - skipping auto-discovery)
[DEBUG] [zap]: Connecting to remote ZAP instance...
[DEBUG] [zap]: Connecting to http://wrong-host:8080
[DEBUG] [zap]: Testing ZAP connectivity...
[DEBUG] [zap]: ERROR: Failed to connect to ZAP at http://wrong-host:8080
[DEBUG] [zap]: ERROR: Connection refused - verify ZAP is running and accessible at http://wrong-host:8080
[DEBUG] [zap]: Test with: curl http://wrong-host:8080/JSON/core/view/version/
[INFO] Plugin zap finished with disposition: fail
```

### Scenario 3: Remote Mode with Missing URL

**Command**:
```bash
python kast/main.py --target example.com --plugins zap \
  --set zap.execution_mode=remote
```

**Expected Logs**:
```
[DEBUG] [zap]: ZAP execution mode: remote (explicit - skipping auto-discovery)
[DEBUG] [zap]: Connecting to remote ZAP instance...
[DEBUG] [zap]: ERROR: Remote mode selected but no api_url configured
Solutions:
  1. Set environment variable: export KAST_ZAP_URL='http://your-zap:8080'
  2. Use CLI override: --set zap.remote.api_url=http://your-zap:8080
  3. Edit config file: remote.api_url in zap_config.yaml
[INFO] Plugin zap finished with disposition: fail
```

### Scenario 4: Auto Mode with Environment Variable

**Command**:
```bash
export KAST_ZAP_URL="http://zap:8080"
python kast/main.py --target example.com --plugins zap
```

**Expected Logs**:
```
[DEBUG] [zap]: ZAP execution mode: auto
[DEBUG] [zap]: Auto-discovering ZAP execution mode...
[DEBUG] [zap]: Found KAST_ZAP_URL: http://zap:8080
[DEBUG] [zap]: Auto-discovery: Using remote mode (env vars found)
[DEBUG] [zap]: Using remote provider for ZAP scan
[DEBUG] [zap]: Testing ZAP connectivity...
[DEBUG] [zap]: ✓ Connected to ZAP v2.14.0 at http://zap:8080
```

## Benefits

### 1. Predictability
- CLI arguments always take precedence
- No surprises from auto-discovery overriding explicit choices
- Clear logging shows which mode was selected and why

### 2. Fast Failure
- Connection issues detected before scan starts
- Saves time by not attempting full scan setup
- Clear error messages point to the problem

### 3. Better Debugging
- ZAP version logged on successful connection
- Specific error types identified (connection refused, timeout, auth failure)
- Troubleshooting commands provided in error messages

### 4. User-Friendly
- Helpful suggestions when configuration is missing
- Multiple configuration methods supported (env vars, CLI, config file)
- Comprehensive documentation with examples

## Testing Recommendations

### Test 1: Explicit Remote Mode Works
```bash
# Start ZAP instance
docker run -d --name test-zap -p 8080:8080 ghcr.io/zaproxy/zaproxy:stable \
  zap.sh -daemon -port 8080 -config api.key=test123

# Test KAST with explicit remote mode
python kast/main.py --target http://example.com --plugins zap \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://localhost:8080 \
  --set zap.remote.api_key=test123 \
  --debug
```

**Verify**: Logs show "explicit - skipping auto-discovery" and connection succeeds

### Test 2: Bad URL Fails Fast
```bash
python kast/main.py --target http://example.com --plugins zap \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://nonexistent:8080 \
  --debug
```

**Verify**: Logs show connection error with helpful message, scan fails immediately

### Test 3: Missing URL Gives Helpful Error
```bash
python kast/main.py --target http://example.com --plugins zap \
  --set zap.execution_mode=remote \
  --debug
```

**Verify**: Logs show error message with 3 suggested solutions

### Test 4: Environment Variable Works in Auto Mode
```bash
export KAST_ZAP_URL="http://localhost:8080"
export KAST_ZAP_API_KEY="test123"
python kast/main.py --target http://example.com --plugins zap --debug
```

**Verify**: Auto-discovery detects env var and uses remote mode

## Migration Notes

### For Existing Users

**No breaking changes** - existing configurations continue to work:
- Auto mode still works as before
- Config files don't need updating
- Environment variables still respected

**New capabilities available**:
- CLI can now explicitly override mode
- Connection testing provides earlier feedback
- Better error messages help troubleshoot issues

### For CI/CD Pipelines

**Recommended approach**:
```bash
# Set in CI secrets
export KAST_ZAP_URL="${ZAP_INSTANCE_URL}"
export KAST_ZAP_API_KEY="${ZAP_API_KEY}"

# Run with auto mode - will detect env vars
python kast/main.py --target "${DEPLOY_URL}" --plugins zap
```

**Alternative (explicit)**:
```bash
python kast/main.py --target "${DEPLOY_URL}" --plugins zap \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url="${ZAP_INSTANCE_URL}" \
  --set zap.remote.api_key="${ZAP_API_KEY}"
```

## Summary

These improvements ensure that:
1. **CLI arguments always take precedence** over auto-discovery
2. **Connection is tested** before attempting scans
3. **Clear error messages** help users fix configuration issues
4. **ZAP version is logged** for debugging
5. **Multiple configuration methods** are supported

The changes maintain backward compatibility while providing better predictability and user experience.
